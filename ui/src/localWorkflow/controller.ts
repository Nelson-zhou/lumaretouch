import {checkedSemanticArchive, sameSemanticArchive} from './semanticArchive';
import {checkedHandoff, fetchReviewImage, reviewAck, reviewKey, type ReviewImages, type ReviewSide, type ReviewStep} from './presetReview';
import {checkedCatalogue, type PresetCatalogue} from './presetCatalogue';
// SPDX-License-Identifier: GPL-3.0-or-later
import type {DefinitionSummary, PendingWorkflowRequest, PreflightReport, ProjectLease, ReturnedExportProfile, RunSummary, WorkflowCapabilities,
  WorkflowCommand, WorkflowDefinition, WorkflowExportProfile, WorkflowHostPort, WorkflowReceipt, WorkflowRun} from './contracts';
import {isRunActive, leaseMatches, newDefinition, validateGraph} from './model.ts';

export interface WorkflowViewState {
  draft: WorkflowDefinition;
  dirty: boolean;
  ready: boolean;
  busy: boolean;
  capabilities: WorkflowCapabilities | null;
  definitions: DefinitionSummary[];
  runs: RunSummary[];
  active_run: WorkflowRun | null;
  inspected_run: WorkflowRun | null;
  pending: PendingWorkflowRequest[];
  lease: ProjectLease | null;
  preflight: PreflightReport | null;
  export_profile: ReturnedExportProfile | null;
  export_profiles: ReturnedExportProfile[];
  profile_pending: boolean;
  preset_catalogue: PresetCatalogue | null;
  review_images: ReviewImages | null;
  /** Ephemeral current-start consent; never persisted with a graph or restored. */
  automatic_start_ack: string | null;
  message: string;
  error: string;
}
const commandKinds: WorkflowCommand['kind'][] = ['save_definition', 'acquire_project_lease', 'release_project_lease', 'start', 'stop', 'open_review', 'review_step'];
const failureMessage = (error: unknown) => error instanceof Error ? error.message : String(error);
function exactObjectKeys(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const actual = Object.keys(value);
  return actual.length === keys.length && actual.every(key => keys.includes(key));
}
function returnedProfile(hash?: string, profile?: WorkflowExportProfile): ReturnedExportProfile | null {
  if (!hash || !/^[a-f\d]{64}$/.test(hash) || !profile ||
    !exactObjectKeys(profile, ['profile', 'export_options', 'destination', 'watermark', 'layout']) ||
    profile.watermark !== null || profile.layout !== null) return null;
  const options = profile.export_options, destination = profile.destination;
  if (!exactObjectKeys(options, ['format', 'quality', 'tile', 'bit_depth', 'scale', 'upscale_backend', 'sharpen',
    'output_profile', 'metadata_include_gps', 'conflict_policy', 'tiff_compression']) ||
    options.tile !== 1024 ||
    options.scale !== 1 || options.upscale_backend !== 'lanczos3' || options.sharpen !== 0 || options.output_profile !== 'srgb' ||
    options.metadata_include_gps !== false || options.conflict_policy !== 'skip_and_report' ||
    !exactObjectKeys(destination, ['mode', 'retain_hierarchy', 'conflict', 'create_missing']) ||
    destination.mode !== 'chosen_root' || destination.retain_hierarchy !== false || destination.conflict !== 'ask' || destination.create_missing !== false) return null;
  const choices = {
    'lrt.workflow-export.jpeg-srgb.v1': ['jpg', 95, 8, 'deflate'],
    'lrt.workflow-export.jpeg80-srgb.v1': ['jpg', 80, 8, 'deflate'],
    'lrt.workflow-export.jpeg100-srgb.v1': ['jpg', 100, 8, 'deflate'],
    'lrt.workflow-export.png8-srgb.v1': ['png', 95, 8, 'deflate'],
    'lrt.workflow-export.tiff16-srgb.v1': ['tif', 95, 16, 'none'],
  };
  if (!Object.prototype.hasOwnProperty.call(choices, profile.profile) ||
      JSON.stringify(choices[profile.profile]) !== JSON.stringify([options.format, options.quality, options.bit_depth, options.tiff_compression])) return null;
  // No flattening, omitted settings or client-side hash substitution. The engine owns the exact digest.
  if (new TextEncoder().encode(JSON.stringify(profile)).length > 8192) return null;
  return {recipe_sha256: hash, recipe_profile: structuredClone(profile)};
}

export function checkedExportProfiles(value: unknown): ReturnedExportProfile[] {
  if (!Array.isArray(value) || value.length > 5) return [];
  const rows = value.map(row => row && exactObjectKeys(row, ['recipe_sha256', 'recipe_profile'])
    ? returnedProfile(row.recipe_sha256 as string, row.recipe_profile as WorkflowExportProfile) : null);
  if (rows.some(row => !row) || new Set(rows.map(row => row?.recipe_sha256)).size !== rows.length ||
      new Set(rows.map(row => row?.recipe_profile.profile)).size !== rows.length) return [];
  return rows as ReturnedExportProfile[];
}

/** Retain one controller per host scope outside the panel. Unmounting does not cancel or replay a host write. */
export class WorkflowController {
  private listeners = new Set<() => void>();
  private epoch = 0;
  private inspectionEpoch = 0;
  private disposed = false;
  private workspaceRevision = -1;
  private workspaceRefreshNeeded = false;
  private commands = new Map<string, WorkflowCommand>();
  private queryCursor = 0;
  private imageEpoch = 0;
  private value: WorkflowViewState;
  private readonly host: WorkflowHostPort | null;
  private readonly newId: () => string;
  constructor(host: WorkflowHostPort | null, initial?: WorkflowDefinition,
    newId: () => string = () => globalThis.crypto.randomUUID()) {
    this.host = host;
    this.newId = newId;
    this.value = {draft: structuredClone(initial ?? newDefinition(newId())), dirty: !initial?.storage_revision,
      ready: false, busy: false, capabilities: null, definitions: [], runs: [], active_run: null,
      inspected_run: null, pending: this.restorePending(), lease: null, preflight: null, export_profile: null, export_profiles: [], profile_pending: false, preset_catalogue: null,
      review_images: null, automatic_start_ack: null, message: '', error: !host ? '本地工作流宿主尚未接入。可编辑草稿，但不能保存、检测或运行。' : ''};
  }
  async selectSemanticArchive(nodeId: string, path: string): Promise<void> {
    if (!this.host?.inspectSemanticArchive || this.editingLocked) return;
    const node = this.value.draft.graph.nodes.find(row => row.id === nodeId);
    if (node?.operation.kind !== 'automatic_preset' || !node.operation.intent.semantic_scope) return;
    const epoch = this.epoch, graphId = this.value.draft.graph.workflow_id, revision = this.value.draft.graph.revision;
    this.patch({busy: true, automatic_start_ack: null, preflight: null, error: ''});
    try {
      const archive = checkedSemanticArchive(await this.host.inspectSemanticArchive(path));
      if (this.disposed || epoch !== this.epoch || this.value.draft.graph.workflow_id !== graphId || this.value.draft.graph.revision !== revision) return;
      if (!archive || archive.path !== path) throw new Error('语义追色归档回执无效或不属于所选文件。');
      this.patch({busy: false});
      this.updateDraft(value => ({...value, graph: {...value.graph, nodes: value.graph.nodes.map(row => row.id === nodeId && row.operation.kind === 'automatic_preset' ?
        {...row, operation: {...row.operation, preset_id: `semantic:${archive.file_sha256}`, preset_sha256: archive.file_sha256,
          intent: {...row.operation.intent, semantic_archive: archive}}} : row)}}));
      this.patch({message: '已验证完整 .lrtcolour 和便携意图；尚未启动推理或应用。保存并检测后，再确认本次启动。'});
    } catch (error) {if (epoch === this.epoch) this.patch({error: failureMessage(error)});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  async refreshCatalogue(): Promise<void> {
    if (!this.host?.refreshCatalogue || this.disposed) return;
    try { await this.host.refreshCatalogue(); await this.refresh(); }
    catch (error) { if (!this.disposed) this.patch({ready: false, automatic_start_ack: null, error: failureMessage(error)}); }
  }
  getState = (): WorkflowViewState => this.value;
  subscribe = (listener: () => void): (() => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private patch(patch: Partial<WorkflowViewState>): void {
    if (this.disposed) return;
    const consentBinding = this.automaticStartBinding();
    this.value = {...this.value, ...patch};
    if (patch.ready === false || patch.capabilities?.available === false || consentBinding !== this.automaticStartBinding())
      this.value = {...this.value, automatic_start_ack: null};
    const run = this.value.active_run, handoff = run?.handoff;
    if (this.value.review_images && (!run || handoff?.phase !== 'reviewing' || this.value.review_images.key !== reviewKey(run.run_id, handoff))) {
      this.imageEpoch += 1;
      this.value = {...this.value, review_images: null};
    }
    this.listeners.forEach(listener => listener());
  }
  private get storageKey(): string {return `lrt:local-workflow:v1:${this.host?.scope_id ?? 'unconnected'}`;}
  private restorePending(): PendingWorkflowRequest[] {
    try {
      if (typeof sessionStorage === 'undefined') return [];
      const parsed: unknown = JSON.parse(sessionStorage.getItem(this.storageKey) ?? '[]');
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((entry): entry is PendingWorkflowRequest => !!entry && typeof entry === 'object' &&
        typeof entry.request_id === 'string' && entry.request_id.length > 0 && entry.request_id.length <= 256 && commandKinds.includes(entry.command_kind));
    } catch {return [];}
  }
  private setPending(pending: PendingWorkflowRequest[]): void {
    this.patch({pending});
    try {if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(this.storageKey, JSON.stringify(pending));}
    catch {/* The host journal is mandatory; browser storage is only an additional recovery hint. */}
  }
  private usableHost(): WorkflowHostPort | null {
    if (this.disposed) return null;
    if (!this.host || this.host.version !== 1 || !this.host.scope_id) {
      this.patch({error: '需要兼容 v1 的真实本地工作流宿主。'}); return null;
    }
    return this.host;
  }
  get editingLocked(): boolean {
    return this.disposed || this.value.busy || this.value.pending.length > 0 || isRunActive(this.value.active_run) ||
      (!!this.host && !this.value.ready);
  }
  updateDraft(update: (definition: WorkflowDefinition) => WorkflowDefinition): void {
    if (this.editingLocked) return;
    const next = update(structuredClone(this.value.draft));
    next.graph.revision = this.value.draft.graph.revision + 1;
    this.patch({draft: next, dirty: true, preflight: null, error: '', message: '草稿已修改，需要重新保存并检测。'});
  }
  newWorkflow(): void {
    if (this.editingLocked) return;
    this.patch({draft: newDefinition(this.newId()), dirty: true, preflight: null, error: '', message: '新建的是未保存草稿；已持有的工程租约不会被静默释放。'});
  }
  async refresh(): Promise<void> {
    const host = this.usableHost();
    if (!host || this.value.busy) return;
    const epoch = this.epoch;
    this.patch({busy: true, error: ''});
    try {
      const workspace = await host.readWorkspace();
      if (this.disposed || epoch !== this.epoch) return;
      if (workspace.port_version !== 1 || !Number.isSafeInteger(workspace.workspace_revision)) throw new Error('宿主状态版本无效。');
      if (workspace.host_scope_id !== undefined && workspace.host_scope_id !== host.scope_id) throw new Error('宿主恢复身份与当前连接不匹配。');
      if (workspace.workspace_revision < this.workspaceRevision) return;
      this.workspaceRevision = workspace.workspace_revision;
      this.workspaceRefreshNeeded = false;
      const pending = new Map(this.value.pending.map(item => [item.request_id, item]));
      workspace.unresolved_requests.forEach(item => pending.set(item.request_id, item));
      this.setPending([...pending.values()]);
      const leasePatch: Partial<WorkflowViewState> = workspace.lease === undefined ? {} : {lease: workspace.lease,
        ...(workspace.lease?.lease_id !== this.value.lease?.lease_id ? {preflight: null} : {})};
      this.patch({ready: true, capabilities: workspace.capabilities, definitions: workspace.definitions,
        runs: workspace.runs, active_run: this.newerRun(workspace.active_run, this.value.active_run),
        preset_catalogue: checkedCatalogue(workspace.preset_catalogue),
        export_profiles: checkedExportProfiles(workspace.export_profiles),
        export_profile: returnedProfile(workspace.recipe_sha256, workspace.recipe_profile), profile_pending: workspace.recipe_profile_pending === true,
        ...leasePatch,
        message: pending.size ? '存在未确认操作。请查询原操作，不要重新提交。' : this.value.message});
    } catch (error) {if (epoch === this.epoch) this.patch({ready: false, error: failureMessage(error)});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  private newerRun(next: WorkflowRun | null, current: WorkflowRun | null): WorkflowRun | null {
    // Never erase an active run from an incomplete/stale read. A terminal run must be explicitly returned.
    if (!next) return isRunActive(current) ? current : null;
    if (next.handoff != null && !checkedHandoff(next.handoff)) throw new Error('宿主预设交接内容无效；保留原运行，不能批准或释放。');
    if (current?.run_id === next.run_id && current.sequence >= next.sequence) return current;
    return next;
  }
  async load(workflowId: string): Promise<void> {
    const host = this.usableHost();
    if (!host || this.editingLocked) return;
    const epoch = this.epoch;
    this.patch({busy: true, automatic_start_ack: null, error: ''});
    try {
      const definition = await host.readDefinition(workflowId);
      if (this.disposed || epoch !== this.epoch) return;
      if (definition.graph.workflow_id !== workflowId || definition.graph.schema_version !== 1 || !definition.storage_revision)
        throw new Error('宿主返回的保存定义不匹配。');
      this.patch({draft: structuredClone(definition), dirty: false, preflight: null, message: '已读取保存的定义；已持有的租约仍保留，运行前须核对当前工程并检测。'});
    } catch (error) {if (epoch === this.epoch) this.patch({error: failureMessage(error)});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  private mayWrite(): boolean {
    return !!this.usableHost() && this.value.ready && !this.value.busy && !this.value.pending.length;
  }
  async save(): Promise<void> {
    if (!this.mayWrite() || this.editingLocked || !this.value.capabilities?.can_save || !this.value.draft.name.trim()) return;
    await this.submit({kind: 'save_definition', definition: structuredClone(this.value.draft), expected_storage_revision: this.value.draft.storage_revision});
  }
  async acquireLease(): Promise<void> {
    if (!this.mayWrite() || this.editingLocked || !this.value.capabilities?.available || !this.value.capabilities.can_run) return;
    if (this.value.lease) {this.patch({error: '已持有工程租约，请先明确释放，再重新取得。'}); return;}
    const imported = this.value.draft.graph.nodes.find(node => node.operation.kind === 'managed_import')?.operation;
    if (imported?.kind !== 'managed_import' || !imported.project_id || !imported.project_path) {
      this.patch({error: '请先填写当前已加载、已保存且没有未保存修改的工程标识与绝对路径。'}); return;
    }
    await this.submit({kind: 'acquire_project_lease', project_id: imported.project_id, project_path: imported.project_path});
  }
  canReleaseLease(): boolean {
    return !!this.host && this.host.version === 1 && !this.disposed && this.value.ready && !this.value.busy &&
      this.value.pending.length === 0 && !!this.value.lease && !isRunActive(this.value.active_run);
  }
  async releaseLease(): Promise<void> {
    if (!this.canReleaseLease()) return;
    await this.submit({kind: 'release_project_lease', lease_id: this.value.lease!.lease_id});
  }
  selectedExportProfile(): ReturnedExportProfile | null {
    const output = this.value.draft.graph.nodes.find(node => node.operation.kind === 'export')?.operation;
    if (output?.kind !== 'export') return null;
    return [...this.value.export_profiles, ...(this.value.export_profile ? [this.value.export_profile] : [])]
      .find(profile => profile.recipe_sha256 === output.recipe_sha256) ?? null;
  }
  useReturnedExportProfile(selectedHash?: string): void {
    const automatic = this.value.draft.graph.nodes.some(node => node.operation.kind === 'automatic_preset');
    const profile = selectedHash ? this.value.export_profiles.find(row => row.recipe_sha256 === selectedHash) : this.value.export_profile;
    if (this.editingLocked || !profile || (!automatic && profile.recipe_profile.profile !== 'lrt.workflow-export.jpeg-srgb.v1')) return;
    const hash = profile.recipe_sha256;
    const output = this.value.draft.graph.nodes.find(node => node.operation.kind === 'export')?.operation;
    if (output?.kind !== 'export' || output.recipe_sha256 === hash) return;
    this.updateDraft(value => ({...value, graph: {...value.graph, nodes: value.graph.nodes.map(node => node.operation.kind === 'export' ?
      {...node, operation: {...node.operation, recipe_sha256: hash}} : node)}}));
    this.patch({message: '已将宿主实际返回的导出配方指纹写入草稿。请保存并重新检测；没有启动导出。'});
  }
  async check(): Promise<void> {
    const host = this.usableHost();
    if (!host || !this.mayWrite() || this.editingLocked || !this.value.capabilities?.available || !this.value.capabilities.can_run) return;
    const {draft, lease, capabilities} = this.value;
    if (validateGraph(draft.graph, capabilities ?? undefined).some(item => item.severity === 'error') || !leaseMatches(draft.graph, lease)) {
      this.patch({error: '请先修复图结构和参数，并取得匹配当前已保存工程的独占租约。'}); return;
    }
    const epoch = this.epoch, graph = structuredClone(draft.graph), leaseId = lease!.lease_id;
    this.patch({busy: true, preflight: null, error: ''});
    try {
      const report = await host.preflight({port_version: 1, graph, lease_id: leaseId});
      if (this.disposed || epoch !== this.epoch || this.value.draft.graph.revision !== graph.revision || this.value.draft.graph.workflow_id !== graph.workflow_id) return;
      if (report.workflow_id !== graph.workflow_id || report.graph_revision !== graph.revision || report.lease_id !== leaseId)
        throw new Error('检测结果不属于当前图或工程租约。');
      const profile = returnedProfile(report.recipe_sha256, report.recipe_profile);
      this.patch({preflight: report, ...(profile ? {export_profile: profile} : {}),
        message: report.can_start ? '宿主检测完成。启动时仍会核验图、目录及租约。' : '检测未通过，请查看诊断。'});
    } catch (error) {if (epoch === this.epoch) this.patch({error: failureMessage(error)});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  private automaticStartBinding(): string | null {
    const {draft, preflight, lease} = this.value;
    const automatic = draft.graph.nodes.find(node => node.operation.kind === 'automatic_preset')?.operation;
    const disclosedExport = this.selectedExportProfile();
    if (automatic?.kind === 'automatic_preset' && !disclosedExport) return null;
    let disclosedReference: unknown = null;
    if (automatic?.kind === 'automatic_preset' && automatic.intent.semantic_scope) {
      if (!sameSemanticArchive(automatic.intent.semantic_archive, preflight?.semantic_archive)) return null;
      disclosedReference = automatic.intent.semantic_archive;
    }
    if (automatic?.kind === 'automatic_preset' && automatic.intent.reference_scope) {
      const catalogue = this.value.preset_catalogue;
      const preset = catalogue?.presets.find(row => row.id === automatic.preset_id && row.preset_sha256 === automatic.preset_sha256);
      if (!catalogue?.complete || !preset?.automatic_reference || preset.automatic_supported !== true
          || preset.module_ids.length !== 1 || preset.module_ids[0] !== 'lnx.reference_color.v1') return null;
      disclosedReference = preset.automatic_reference;
    }
    if (!draft.graph.nodes.some(node => node.operation.kind === 'automatic_preset') || typeof preflight?.graph_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(preflight.graph_sha256)) return null;
    return JSON.stringify([this.host?.scope_id, preflight.preflight_token, preflight.graph_sha256, lease?.lease_id, draft.graph, disclosedReference, disclosedExport]);
  }
  canAcknowledgeAutomaticStart(): boolean {return this.automaticStartBinding() !== null && this.canStart(Date.now(), false);}
  acknowledgeAutomaticStart(accepted: boolean): void {
    this.patch({automatic_start_ack: accepted && this.canAcknowledgeAutomaticStart() ? this.automaticStartBinding() : null});
  }
  canStart(now = Date.now(), requireAutomaticAck = true): boolean {
    const {draft, capabilities, preflight, lease} = this.value;
    return !!this.host && this.value.ready && !this.editingLocked && !this.value.dirty && !!draft.storage_revision &&
      !!capabilities?.available && capabilities.can_run && leaseMatches(draft.graph, lease, now) &&
      !!preflight?.can_start && !!preflight.preflight_token && preflight.workflow_id === draft.graph.workflow_id &&
      preflight.graph_revision === draft.graph.revision && preflight.lease_id === lease?.lease_id &&
      Date.parse(preflight.valid_until) > now && !preflight.diagnostics.some(item => item.severity === 'error') &&
      !validateGraph(draft.graph, capabilities).some(item => item.severity === 'error') &&
      (!draft.graph.nodes.some(node => node.operation.kind === 'automatic_preset') ||
        (this.automaticStartBinding() !== null && (!requireAutomaticAck || this.value.automatic_start_ack === this.automaticStartBinding())));
  }
  async start(): Promise<void> {
    if (!this.canStart() || !this.mayWrite()) return;
    const automatic = this.value.draft.graph.nodes.some(node => node.operation.kind === 'automatic_preset');
    const acknowledgment = automatic ? {schema: 'lrt.automatic-batch-start.v1' as const, graph_sha256: this.value.preflight!.graph_sha256!, accepted: true as const} : undefined;
    // Consume UI consent before dispatch; a lost response is queried, never started again.
    this.patch({automatic_start_ack: null});
    await this.submit({kind: 'start', graph: structuredClone(this.value.draft.graph), lease_id: this.value.lease!.lease_id,
      preflight_token: this.value.preflight!.preflight_token, ...(acknowledgment ? {automatic_ack: acknowledgment} : {})});
  }
  async stop(): Promise<void> {
    const run = this.value.active_run;
    if (!this.canStop()) return;
    await this.submit({kind: 'stop', run_id: run!.run_id});
  }
  canStop(): boolean {
    // A known active run may be explicitly stopped even if its original start response is unresolved.
    // This is a distinct safe-boundary action, never a replay of that original start.
    return !!this.host && this.host.version === 1 && !this.disposed && this.value.ready && !this.value.busy &&
      !!this.value.active_run && !this.value.active_run.handoff && ['running', 'paused'].includes(this.value.active_run.status) &&
      !this.value.pending.some(item => item.command_kind === 'stop');
  }
  async openReview(): Promise<void> {
    const run = this.value.active_run;
    if (!this.mayWrite() || !this.value.capabilities?.can_open_review || run?.status !== 'paused' || !run.review) return;
    await this.submit({kind: 'open_review', run_id: run.run_id, review_id: run.review.review_id});
  }
  canReviewStep(step: ReviewStep): boolean {
    const run = this.value.active_run, handoff = run?.handoff;
    if (!this.host || this.disposed || !this.value.ready || !this.value.capabilities?.available || !this.value.capabilities.can_open_review || this.value.busy || this.value.pending.length || !run || !handoff || handoff.mode === 'automatic' || !checkedHandoff(handoff)) return false;
    if (run.diagnostics.some(item => item.code === 'owner_outcome_unknown' || item.code === 'native_host_fence')) return false;
    if (step === 'open_target') return handoff.phase === 'awaiting_open';
    if (step === 'prepare_skin') return handoff.phase === 'awaiting_preparation';
    if (step === 'save_project') return handoff.phase === 'awaiting_save';
    if (step === 'return_target') return ['awaiting_open', 'awaiting_preparation', 'reviewing', 'awaiting_return'].includes(handoff.phase);
    const images = this.value.review_images;
    return handoff.phase === 'reviewing' && !!handoff.review && !!images && images.key === reviewKey(run.run_id, handoff) &&
      !images.loading && !images.error && !!images.before && !!images.after && images.displayed.before && images.displayed.after && images.acknowledged;
  }
  async reviewStep(step: ReviewStep): Promise<void> {
    if (!this.canReviewStep(step)) return;
    const run = this.value.active_run!, handoff = run.handoff!;
    await this.submit({kind: 'review_step', run_id: run.run_id, operation_id: handoff.operation_id, step,
      payload: step === 'approve' ? reviewAck(handoff.review!) : {}});
  }
  async loadReviewImages(): Promise<void> {
    const host = this.usableHost(), run = this.value.active_run, handoff = run?.handoff;
    if (!host?.readReviewImage || !this.value.capabilities?.available || !run || handoff?.phase !== 'reviewing' || !handoff.review || this.value.review_images?.loading) return;
    const key = reviewKey(run.run_id, handoff), generation = ++this.imageEpoch;
    const current = () => !this.disposed && generation === this.imageEpoch && this.value.active_run?.run_id === run.run_id &&
      this.value.active_run.handoff?.phase === 'reviewing' && reviewKey(run.run_id, this.value.active_run.handoff) === key;
    this.patch({review_images: {key, loading: true, error: '', before: null, after: null, displayed: {before: false, after: false}, acknowledged: false}});
    try {
      // Complete page sequences remain bounded. No ACK is sent by this read.
      const before = await fetchReviewImage(run.run_id, handoff, 'before', input => host.readReviewImage!(input), current);
      const after = await fetchReviewImage(run.run_id, handoff, 'after', input => host.readReviewImage!(input), current);
      if (current()) this.patch({review_images: {key, loading: false, error: '', before, after, displayed: {before: false, after: false}, acknowledged: false}});
    } catch (error) {
      if (current()) this.patch({review_images: {key, loading: false, error: failureMessage(error), before: null, after: null, displayed: {before: false, after: false}, acknowledged: false}});
    }
  }
  reviewImageDisplayed(key: string, side: ReviewSide, complete: boolean, width: number, height: number): void {
    const images = this.value.review_images, report = this.value.active_run?.handoff?.review;
    if (!images || images.key !== key || images.loading || !images[side] || !report) return;
    const ready = complete && width === report[side].width && height === report[side].height;
    this.patch({review_images: {...images, displayed: {...images.displayed, [side]: ready}, acknowledged: ready ? images.acknowledged : false,
      error: ready ? images.error : '审核图像未完整解码，或实际显示尺寸与报告不符；不能批准。可重新读取图像。'}});
  }
  clearReviewPresentation(key: string): void {
    const images = this.value.review_images;
    if (!images || images.key !== key) return;
    this.imageEpoch += 1;
    this.patch({review_images: null});
  }
  acknowledgeReview(key: string, accepted: boolean): void {
    const images = this.value.review_images;
    if (!images || images.key !== key || images.loading || images.error || !images.displayed.before || !images.displayed.after) return;
    this.patch({review_images: {...images, acknowledged: accepted}});
  }
  private async submit(command: WorkflowCommand): Promise<void> {
    const host = this.usableHost();
    if (!host || !(command.kind === 'stop' ? this.canStop() : this.mayWrite())) return;
    const epoch = this.epoch;
    const pending: PendingWorkflowRequest = {request_id: this.newId(), command_kind: command.kind};
    this.commands.set(pending.request_id, command);
    this.setPending([...this.value.pending, pending]);
    this.patch({busy: true, error: '', message: '操作已提交，等待真实回执。'});
    try {
      const receipt = await host.submit({port_version: 1, request_id: pending.request_id, command});
      if (!this.disposed && epoch === this.epoch) this.acceptReceipt(receipt, pending);
    } catch (error) {
      if (epoch === this.epoch) this.patch({error: failureMessage(error), message: '响应中断，结果未知。只能查询原请求，不能重复执行。'});
    } finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  private acceptReceipt(receipt: WorkflowReceipt, expected: PendingWorkflowRequest): void {
    if (receipt.request_id !== expected.request_id || receipt.command_kind !== expected.command_kind) {
      this.patch({error: '回执标识不匹配。已保留原请求，禁止重试写入。'}); return;
    }
    if (receipt.status === 'pending' || receipt.status === 'unknown') {
      this.patch({message: receipt.message ?? '原请求仍在处理或结果未知，请继续查询。'}); return;
    }
    if (receipt.status === 'succeeded') {
      if (receipt.outcome.kind !== expected.command_kind) {this.patch({error: '回执结果类型不匹配，必须继续查询原请求。'}); return;}
      const result = receipt.outcome;
      const original = this.commands.get(expected.request_id);
      if (result.kind === 'release_project_lease' && (result.released !== true || !result.lease_id ||
        (original?.kind === 'release_project_lease' && result.lease_id !== original.lease_id))) {
        this.patch({error: '释放租约的回执不属于原操作。原请求与租约仍保留。'}); return;
      }
      if (result.kind === 'save_definition' && (!result.definition.storage_revision || (original?.kind === 'save_definition' &&
        (result.definition.graph.workflow_id !== original.definition.graph.workflow_id || result.definition.graph.revision !== original.definition.graph.revision)))) {
        this.patch({error: '保存回执缺少存储版本或不属于原定义。原请求仍保留。'}); return;
      }
      if ((result.kind === 'start' || result.kind === 'stop') && (!result.run.run_id || !Number.isSafeInteger(result.run.sequence) || result.run.sequence < 0 ||
        (original?.kind === 'start' && (result.run.workflow_id !== original.graph.workflow_id || result.run.graph_revision !== original.graph.revision || result.run.lease_id !== original.lease_id)) ||
        (original?.kind === 'stop' && result.run.run_id !== original.run_id))) {
        this.patch({error: '运行回执不属于原操作。原请求仍保留。'}); return;
      }
      if (result.kind === 'review_step' && (!result.run_id || !result.operation_id || !['open_target', 'prepare_skin', 'approve', 'save_project', 'return_target'].includes(result.step) ||
        (original?.kind === 'review_step' && (result.run_id !== original.run_id || result.operation_id !== original.operation_id || result.step !== original.step)))) {
        this.patch({error: '交接步骤回执与原请求不匹配；继续保留并查询原请求。'}); return;
      }
      switch (result.kind) {
        case 'save_definition':
          this.workspaceRefreshNeeded = true;
          if (result.definition.graph.workflow_id === this.value.draft.graph.workflow_id && result.definition.graph.revision === this.value.draft.graph.revision) {
            this.patch({draft: structuredClone(result.definition), dirty: false, preflight: null});
          }
          this.patch({message: '宿主已确认定义保存。'}); break;
        case 'acquire_project_lease':
          this.patch({lease: result.lease, preflight: null, message: leaseMatches(this.value.draft.graph, result.lease) ?
            '已取得当前已保存工程的独占租约。交互编辑应由宿主锁定；没有自动切换或保存工程。' : '返回的租约不匹配当前工程，不能运行；可明确释放该租约。'}); break;
        case 'release_project_lease':
          this.workspaceRefreshNeeded = true;
          this.patch({...(this.value.lease?.lease_id === result.lease_id ? {lease: null} : {}), preflight: null,
            message: '宿主已确认释放该工程租约；未自动保存、切换或关闭工程。'}); break;
        case 'start': case 'stop': {
          const current = this.newerRun(result.run, this.value.active_run)!;
          this.patch({active_run: current, runs: [current, ...this.value.runs.filter(item => item.run_id !== current.run_id)], preflight: null,
            message: result.kind === 'stop' ? '已收到停止操作回执，请以运行状态为准。已开始的安全提交可能完成。' : '已收到启动回执，请以运行记录为准。'}); break;
        }
        case 'review_step':
          this.workspaceRefreshNeeded = true;
          this.patch({review_images: null, message: result.message || '已收到实际交接步骤回执，正在核对原操作。'}); break;
        case 'open_review':
          this.patch({message: result.message || (result.opened ? '已打开人工审核。完成真实审核后，由宿主核验并继续。' : '宿主未打开审核界面。')}); break;
      }
    } else this.patch({error: receipt.message, message: receipt.status === 'cancelled' ? '宿主确认操作已取消。' : '宿主确认操作失败。'});
    this.commands.delete(expected.request_id);
    this.setPending(this.value.pending.filter(item => item.request_id !== expected.request_id));
  }
  async queryPending(): Promise<void> {
    const host = this.usableHost();
    if (!host || !this.value.pending.length || this.value.busy) return;
    const expected = this.value.pending[this.queryCursor % this.value.pending.length];
    this.queryCursor += 1;
    const epoch = this.epoch;
    this.patch({busy: true, error: ''});
    try {
      const receipt = await host.queryRequest(expected.request_id);
      if (!this.disposed && epoch === this.epoch) this.acceptReceipt(receipt, expected);
    } catch (error) {if (epoch === this.epoch) this.patch({error: failureMessage(error), message: '查询失败，原请求仍保留；没有重新执行。'});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  async inspectRun(runId: string): Promise<void> {
    const host = this.usableHost();
    if (!host || this.value.busy) return;
    const epoch = this.epoch, inspectionEpoch = ++this.inspectionEpoch;
    this.patch({busy: true, error: ''});
    try {
      const run = await host.readRun(runId);
      if (this.disposed || epoch !== this.epoch || inspectionEpoch !== this.inspectionEpoch) return;
      if (run.run_id !== runId) throw new Error('运行记录标识不匹配。');
      this.patch({inspected_run: this.newerRun(run, this.value.inspected_run),
        ...(this.value.active_run?.run_id === runId ? {active_run: this.newerRun(run, this.value.active_run)} : {})});
    } catch (error) {if (epoch === this.epoch && inspectionEpoch === this.inspectionEpoch) this.patch({error: failureMessage(error)});}
    finally {if (epoch === this.epoch) this.patch({busy: false});}
  }
  clearInspection(): void {this.inspectionEpoch += 1; this.patch({inspected_run: null});}
  /** Read-only follow-up; never invokes start/stop/approval on a timer. */
  async tick(): Promise<void> {
    if (this.value.busy || this.disposed) return;
    if (this.value.pending.length) {
      await this.queryPending();
      if (this.disposed || this.value.busy) return;
      // Read-only discovery keeps a real, already-started run stoppable after a lost Start response.
      if (!this.value.active_run && this.value.pending.some(item => item.command_kind === 'start')) await this.refresh();
    }
    if (this.disposed || this.value.busy) return;
    if (this.workspaceRefreshNeeded || this.value.profile_pending || (!this.value.ready && isRunActive(this.value.active_run))) await this.refresh();
    if (this.disposed || this.value.busy) return;
    if (isRunActive(this.value.active_run)) {
      const host = this.usableHost(), runId = this.value.active_run!.run_id, epoch = this.epoch;
      if (!host) return;
      this.patch({busy: true});
      try {
        const run = await host.readRun(runId);
        if (this.disposed || epoch !== this.epoch || this.value.active_run?.run_id !== runId) return;
        if (run.run_id !== runId) throw new Error('运行记录标识不匹配。');
        const current = this.newerRun(run, this.value.active_run);
        this.patch({active_run: current, runs: this.value.runs.map(item => item.run_id === runId ? current! : item)});
      } catch (error) {if (epoch === this.epoch) this.patch({error: failureMessage(error)});}
      finally {if (epoch === this.epoch) this.patch({busy: false});}
    }
  }
  /** Host scope replacement only, not ordinary panel dismissal. */
  dispose(): void {this.disposed = true; this.epoch += 1; this.listeners.clear();}
}
