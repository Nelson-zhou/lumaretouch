// SPDX-License-Identifier: GPL-3.0-or-later
import {SELECTION_LIMITS, SELECTION_PROTOCOL, SELECTION_REVIEW_IMAGES, emptySelectionRecipe, freezeSelection,
  selectionHash, selectionKey, selectionReplyMatches, validSelectionBinding, validSelectionContext, validSelectionRecipe, validSelectionReview,
  type CreativeSelectionPort, type SelectionApplyRequest, type SelectionBinding, type SelectionCancelRequest, type SelectionContext,
  type SelectionImageRole, type SelectionMaskPolicy, type SelectionOperation, type SelectionPreviewRequest, type SelectionRecipe,
  type SelectionReply, type SelectionRequest, type SelectionReview} from './model.ts';
import {verifySelectionImage} from './imagery.ts';

export interface CreativeSelectionWorkspaceContext {
  /** Include the real engine key and source-load epoch; never derive this from a filename. */
  scope: string; binding: SelectionBinding | null; active: boolean; available: boolean; busy: boolean;
}
export interface SelectionState {
  phase: 'empty' | 'acquiring' | 'verifying' | 'editing' | 'previewing' | 'review' | 'applying' | 'pending' | 'unknown' | 'applied' | 'cancelled' | 'failed';
  context: SelectionContext | null; recipe: SelectionRecipe | null; mask_policy: SelectionMaskPolicy | null; review: SelectionReview | null;
  stale: boolean; source_verified: boolean; source_presented: boolean; images_presented: Record<SelectionImageRole, boolean>; reviewed: boolean;
  undo: SelectionRecipe[]; redo: SelectionRecipe[]; request: SelectionRequest | null; cancel_request: SelectionCancelRequest | null;
  checking: boolean; refresh: 'none' | 'working' | 'ready' | 'failed'; receipt: SelectionReply | null; message: string;
  retired_request: SelectionRequest | null; retired_cancel_request: SelectionCancelRequest | null; retired_receipt: SelectionReply | null;
}
const images = (): Record<SelectionImageRole, boolean> => ({before_mask: false, after_mask: false, before_composite: false, after_composite: false});
const unreviewed = () => ({review: null, images_presented: images(), reviewed: false});
const initial = (): SelectionState => ({phase: 'empty', context: null, recipe: null, mask_policy: null, review: null,
  stale: false, source_verified: false, source_presented: false, images_presented: images(), reviewed: false, undo: [], redo: [],
  request: null, cancel_request: null, checking: false, refresh: 'none', receipt: null,
  retired_request: null, retired_cancel_request: null, retired_receipt: null,
  message: '请获取当前选中图片图层的真实画布。选区只属于该来源，不跨照片复制。'});
const reason = (error: unknown) => error instanceof Error ? error.message : String(error);
const identity = (value: CreativeSelectionWorkspaceContext) => selectionKey([value.scope, value.binding]);
interface ControllerOptions {requestId?: () => string; timeoutMs?: number;
  onApplied?: (reply: SelectionReply, request: SelectionApplyRequest) => Promise<void> | void}
export function selectionBounded<T>(promise: Promise<T>, milliseconds = 145000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('原请求尚未确认；不会重新发送。')), milliseconds);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}

/** App-lifetime owner. Local vector undo is deliberately NOT the canonical document undo stack. */
export class CreativeSelectionController {
  private state: SelectionState = freezeSelection(initial());
  private workspace: CreativeSelectionWorkspaceContext;
  private generation = 0;
  private requestScope: string | null = null;
  private heldPreview: {request: SelectionPreviewRequest; review: SelectionReview} | null = null;
  private cancelClearsDraft = true;
  private cancelChecking = false;
  private terminal: {reply: SelectionReply; request: SelectionApplyRequest} | null = null;
  private readonly listeners = new Set<() => void>();
  readonly port: CreativeSelectionPort;
  private readonly options: ControllerOptions;
  constructor(port: CreativeSelectionPort, context: CreativeSelectionWorkspaceContext, options: ControllerOptions = {}) {
    this.port = port; this.options = options; this.workspace = {...context};
  }
  snapshot = (): SelectionState => this.state;
  subscribe = (listener: () => void): (() => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private publish(patch: Partial<SelectionState>): void {this.state = freezeSelection({...this.state, ...patch}); this.listeners.forEach(listener => listener());}
  private emptyState(): SelectionState {return {...initial(), retired_request: this.state.retired_request,
    retired_cancel_request: this.state.retired_cancel_request, retired_receipt: this.state.retired_receipt};}
  private id(): string {return this.options.requestId?.() ?? crypto.randomUUID();}
  private available(): boolean {return this.port.protocol === SELECTION_PROTOCOL && this.workspace.available && this.workspace.active
    && !this.workspace.busy && !!this.workspace.scope && validSelectionBinding(this.workspace.binding);}
  unresolved = (): boolean => !!this.state.request || !!this.state.cancel_request;
  canAcquire = (): boolean => this.available() && !!this.port.context && !this.unresolved()
    && !['working', 'failed'].includes(this.state.refresh) && this.state.phase !== 'verifying';
  editable = (): boolean => this.available() && !!this.state.context && !!this.state.recipe && !this.state.stale
    && this.state.source_verified && this.state.source_presented && !this.unresolved()
    && !['verifying', 'applied', 'cancelled'].includes(this.state.phase) && !['working', 'failed'].includes(this.state.refresh);
  canPreview = (): boolean => this.editable() && !!this.port.preview && !!this.state.mask_policy && !!this.state.recipe?.operations.length;
  canApply = (): boolean => this.editable() && !!this.port.apply && this.state.phase === 'review' && !!this.state.review
    && this.state.reviewed && SELECTION_REVIEW_IMAGES.every(role => this.state.images_presented[role]);
  updateContext(value: CreativeSelectionWorkspaceContext): void {
    const changed = identity(value) !== identity(this.workspace), unavailable = this.workspace.available && !value.available;
    const operational = value.active !== this.workspace.active || value.available !== this.workspace.available || value.busy !== this.workspace.busy;
    this.workspace = {...value};
    if (changed || unavailable) {
      ++this.generation; this.publish({stale: true, source_presented: false, ...unreviewed(),
        message: '来源、选中图层、变换、修订或引擎发生变化。旧草稿不可应用；重新获取会清空草稿。未决操作仍保留原身份。'});
      if ((this.state.request && this.state.request.action !== 'apply') || (!this.state.request && this.heldPreview)) void this.cancel();
    } else if (operational) this.publish({});
  }
  adapterChanged(): void {this.updateContext({...this.workspace, available: false}); this.publish({message: '选区接口被替换。请保留原 App 生命周期接口核对未决请求，不能换接口重发。'});}
  private current(): boolean {return this.requestScope === identity(this.workspace) && this.workspace.available;}
  private unknown(message: string): void {this.publish({phase: 'unknown', checking: false, reviewed: false, message: `${message} 只能查询原请求，不会重复应用。`});}
  private release(request: SelectionRequest): void {
    if (this.port.release) void this.port.release(request).catch(() => { /* Terminal outcome is retained. Cleanup failure is not a failed write. */ });
  }
  private async retirePreview(): Promise<boolean> {
    if (!this.heldPreview) return true;
    await this.requestCancellation(false); return this.heldPreview === null;
  }

  async acquire(): Promise<void> {
    if (!this.canAcquire() || !this.workspace.binding || !this.port.context) return;
    if (!(await this.retirePreview()) || !this.canAcquire() || !this.workspace.binding) return;
    ++this.generation; this.terminal = null;
    const request = freezeSelection({...this.workspace.binding, action: 'context' as const, request_id: this.id()});
    this.publish({...this.emptyState(), phase: 'acquiring', message: '正在冻结选中图片图层与真实画布，尚未修改文档。'});
    await this.send(request, () => this.port.context!(request));
  }
  sourcePresented(hash: string, width: number, height: number, visible: boolean): void {
    const image = this.state.context?.canvas_image;
    if (!image || image.sha256 !== hash || !this.state.source_verified || this.state.stale) return;
    const ready = visible && width === image.width && height === image.height;
    if (ready !== this.state.source_presented) this.publish({source_presented: ready, reviewed: false});
  }
  presented(role: SelectionImageRole, token: string, width: number, height: number, visible: boolean): void {
    const review = this.state.review; if (!review || review.preview_token !== token || this.state.stale || this.state.phase !== 'review') return;
    const image = review[role], ready = visible && image.width === width && image.height === height;
    if (this.state.images_presented[role] !== ready) this.publish({images_presented: {...this.state.images_presented, [role]: ready}, reviewed: false});
  }
  releasePresentation(): void {this.publish({source_presented: false, images_presented: images(), reviewed: false});}
  acknowledge(value: boolean): void {this.publish({reviewed: value && this.editable() && this.state.phase === 'review'
    && !!this.state.review && SELECTION_REVIEW_IMAGES.every(role => this.state.images_presented[role])});}
  private replace(recipe: SelectionRecipe, direction: 'edit' | 'undo' | 'redo'): boolean {
    const old = this.state.recipe;
    if (!this.editable() || !old || !validSelectionRecipe(recipe) || selectionKey(old.canvas) !== selectionKey(recipe.canvas)) return false;
    if (selectionKey(old) === selectionKey(recipe)) return true;
    ++this.generation;
    this.publish({recipe, phase: 'editing', ...unreviewed(),
      undo: direction === 'undo' ? this.state.undo.slice(0, -1) : [...this.state.undo, old].slice(-SELECTION_LIMITS.undo),
      redo: direction === 'undo' ? [...this.state.redo, old].slice(-SELECTION_LIMITS.undo) : direction === 'redo' ? this.state.redo.slice(0, -1) : [],
      message: '选区草稿已更改，旧对比与确认失效。原图层、蒙版与历史尚未写入。'}); return true;
  }
  append(operation: SelectionOperation): boolean {
    const recipe = this.state.recipe; if (!recipe) return false;
    const next = {...recipe, operations: [...recipe.operations, operation]};
    if (!validSelectionRecipe(next)) {this.notice('本笔超过安全边界，整笔未提交；请分段绘制。'); return false;}
    return this.replace(next, 'edit');
  }
  feather(value: number): boolean {return !!this.state.recipe && this.replace({...this.state.recipe, feather_radius: value}, 'edit');}
  deselect(): boolean {return !!this.state.recipe && this.replace({...this.state.recipe, operations: []}, 'edit');}
  undo(): boolean {const recipe = this.state.undo.at(-1); return !!recipe && this.replace(recipe, 'undo');}
  redo(): boolean {const recipe = this.state.redo.at(-1); return !!recipe && this.replace(recipe, 'redo');}
  policy(value: SelectionMaskPolicy | null): void {
    if (!this.editable() || !this.state.context || value === this.state.mask_policy) return;
    const exists = this.state.context.proof.existing_mask_id !== null;
    if (value !== null && (exists ? !['replace', 'union', 'subtract', 'intersect'].includes(value) : value !== 'create')) return;
    ++this.generation;
    this.publish({mask_policy: value, phase: 'editing', ...unreviewed(), message: '已更改现有蒙版处理方式，请重新生成实际前后对比。'});
  }
  notice(message: string): void {this.publish({message});}
  async preview(): Promise<void> {
    if (!this.canPreview() || !this.state.context || !this.state.recipe || !this.state.mask_policy || !this.port.preview) return;
    if (!(await this.retirePreview()) || !this.canPreview() || !this.state.context || !this.state.recipe || !this.state.mask_policy) return;
    const request: SelectionPreviewRequest = freezeSelection({action: 'preview', request_id: this.id(), source_uid: this.state.context.proof.source_uid,
      proof: this.state.context.proof, recipe: this.state.recipe, mask_policy: this.state.mask_policy});
    if (new TextEncoder().encode(JSON.stringify(request)).length > SELECTION_LIMITS.requestBytes) {this.notice('选区请求过大，未发送。'); return;}
    ++this.generation; this.publish({phase: 'previewing', ...unreviewed(), message: '正在计算真实覆盖率、源蒙版和完整合成前后图，尚未写入历史。'});
    await this.send(request, () => this.port.preview!(request));
  }
  async apply(): Promise<void> {
    if (!this.canApply() || !this.state.review || !this.port.apply) return;
    const review = this.state.review, request: SelectionApplyRequest = freezeSelection({action: 'apply', request_id: this.id(),
      source_uid: review.proof.source_uid, proof: review.proof, preview_token: review.preview_token, ack: review.ack, reviewed: true});
    this.publish({phase: 'applying', reviewed: false, message: '正在将已审核的真实不可变蒙版提交给现有图层历史。不会重复发送。'});
    await this.send(request, () => this.port.apply!(request));
  }
  private async send(request: SelectionRequest, operation: () => Promise<SelectionReply>): Promise<void> {
    if (this.unresolved()) return;
    this.requestScope = identity(this.workspace); this.publish({request});
    try {await this.receive(await selectionBounded(operation(), this.options.timeoutMs), request);}
    catch (error) {if (this.state.request?.request_id === request.request_id) this.unknown(reason(error));}
  }
  private async receive(reply: SelectionReply, request: SelectionRequest): Promise<void> {
    if (this.state.request?.request_id !== request.request_id) return;
    if (!selectionReplyMatches(reply, request)) {this.unknown('回执身份不符。'); return;}
    if (reply.status === 'pending' || reply.status === 'unknown') {this.publish({phase: reply.status, checking: false,
      ...(reply.status === 'unknown' && reply.workspace_reopened === true ? {retired_receipt: reply} : {}),
      message: reply.message || '原操作尚未完成。'}); return;}
    if (reply.status === 'rejected' || reply.status === 'cancelled') {
      this.publish({request: null, checking: false, phase: reply.status === 'cancelled' ? 'cancelled' : 'failed', reviewed: false,
        message: reply.message || (reply.status === 'cancelled' ? '原请求已确认取消。' : '宿主已拒绝操作，未发布新蒙版。')}); this.release(request); return;
    }
    if (request.action === 'apply') {
      if (!['applied', 'no_change'].includes(reply.status) || !reply.proof || selectionKey(reply.proof) !== selectionKey(request.proof)
        || reply.preview_token !== request.preview_token || !Number.isSafeInteger(reply.revision) || reply.revision! < request.proof.expected_revision
        || (reply.status === 'applied' && reply.revision! <= request.proof.expected_revision)
        || !reply.mask_id || !selectionHash(reply.mask_sha256)
        || !this.heldPreview || reply.mask_id !== this.heldPreview.review.output_mask_id || reply.mask_sha256 !== this.heldPreview.review.output_mask_sha256) {
        this.unknown('应用回执没有绑定原审核蒙版、来源或有效修订。'); return;
      }
      this.terminal = {reply, request}; const previewRequest = this.heldPreview.request; this.heldPreview = null;
      this.publish({request: null, checking: false, phase: 'applied', receipt: reply, ...unreviewed(),
        message: '真实蒙版已由宿主确认。草稿撤销不能撤销此次应用；请使用工作区统一历史。'});
      this.release(request); this.release(previewRequest); await this.refresh(); return;
    }
    if (!this.current()) {this.publish({request: null, checking: false, phase: 'empty', stale: true, message: '旧来源读取已结束，未带入当前照片。'});
      if (request.action === 'context') this.release(request); return;}
    const generation = this.generation;
    if (request.action === 'context' && reply.status === 'ready' && validSelectionContext(reply.context, request)) {
      const context = freezeSelection(reply.context);
      this.publish({phase: 'verifying'});
      const verified = (await Promise.all([verifySelectionImage(context.canvas_image),
        context.existing_mask_image ? verifySelectionImage(context.existing_mask_image) : Promise.resolve(true)])).every(Boolean);
      if (this.state.request?.request_id !== request.request_id) return;
      this.publish({request: null, checking: false});
      this.release(request);
      if (generation !== this.generation || !this.current()) return;
      if (!verified) {this.publish({phase: 'failed', message: '真实画布或已有蒙版的 PNG 内容摘要校验失败，编辑被锁定。'}); return;}
      this.publish({context, recipe: emptySelectionRecipe(context.proof.canvas), mask_policy: context.proof.existing_mask_id ? null : 'create',
        phase: 'editing', stale: false, source_verified: true, source_presented: false, undo: [], redo: [], ...unreviewed(),
        message: context.proof.existing_mask_id ? '已冻结真实来源。已有蒙版不会被覆盖，请明确选择组合或替换方式。' : '已冻结真实来源。绘制选区后，生成真实前后对比。'}); return;
    }
    if (request.action === 'preview' && reply.status === 'ready' && validSelectionReview(reply.review, request)) {
      const review = freezeSelection(reply.review); this.heldPreview = {request, review}; this.publish({phase: 'verifying'});
      const verified = (await Promise.all(SELECTION_REVIEW_IMAGES.map(role => verifySelectionImage(review[role])))).every(Boolean);
      if (this.state.request?.request_id !== request.request_id) return;
      this.publish({request: null, checking: false});
      if (generation !== this.generation || !this.current()) return;
      if (!verified) {this.publish({phase: 'failed', ...unreviewed(), message: '前后图或蒙版图摘要校验失败，不能应用。'}); return;}
      this.publish({phase: 'review', review, images_presented: images(), reviewed: false,
        message: '请查看真实完整合成前后图和源像素蒙版，明确确认后才会写入图层历史。'}); return;
    }
    this.unknown('宿主返回的来源或预览协议不匹配。');
  }
  async check(): Promise<void> {
    if (this.state.checking || this.state.phase === 'verifying' || !this.port.receipt) return;
    const request = this.state.request; if (!request) {if (this.state.cancel_request) await this.checkCancel(); return;}
    this.publish({checking: true});
    try {await this.receive(await selectionBounded(this.port.receipt(request), this.options.timeoutMs), request);}
    catch (error) {if (this.state.request?.request_id === request.request_id) this.unknown(reason(error));}
    finally {this.publish({checking: false});}
    if (this.state.cancel_request) await this.checkCancel();
  }
  canDismissRetiredWorkspace(): boolean {
    const reply = this.state.retired_receipt, request = this.state.request;
    return !!request && !!reply && reply.workspace_reopened === true && reply.status === 'unknown' && selectionReplyMatches(reply, request);
  }
  /** Explicit user dismissal only after the native authority proves an actual project reopen. No inferred rollback. */
  dismissRetiredWorkspace(): void {
    if (!this.canDismissRetiredWorkspace()) return;
    const retired_request = this.state.request, retired_cancel_request = this.state.cancel_request, retired_receipt = this.state.retired_receipt;
    ++this.generation; this.heldPreview = null; this.terminal = null;
    this.publish({...initial(), phase: 'empty', stale: true, retired_request, retired_cancel_request, retired_receipt,
      message: '已按你的确认关闭旧工程会话的操作锁。旧操作结果仍为未知，未当作成功、拒绝或撤销，也不会重发。请重新获取当前工程的真实图层画布。'});
  }
  /** Cancel targets an existing original request. It never means undo and never hides an uncertain apply. */
  async cancel(): Promise<void> {await this.requestCancellation(true);}
  private async requestCancellation(clearDraft: boolean): Promise<void> {
    if (this.state.cancel_request) return;
    const target = this.state.request ?? this.heldPreview?.request;
    if (!target) {
      if (this.state.phase === 'verifying') return;
      ++this.generation; this.publish({...this.emptyState(), phase: 'cancelled', message: '本地选区草稿已放弃，图层历史未改变。'}); return;
    }
    if (!this.port.cancel) {this.notice('宿主未提供原任务取消能力；保留原请求，不能假装已取消。'); return;}
    const request: SelectionCancelRequest = freezeSelection({action: 'cancel', request_id: this.id(), source_uid: target.source_uid,
      target_request_id: target.request_id, ...(this.heldPreview?.request.request_id === target.request_id ? {preview_token: this.heldPreview.review.preview_token} : {})});
    this.cancelClearsDraft = clearDraft;
    this.publish({cancel_request: request, reviewed: false, message: '正在请求取消原任务；未确认前不宣称已取消，也不回滚已应用蒙版。'});
    try {this.receiveCancel(await selectionBounded(this.port.cancel(request), this.options.timeoutMs), request);}
    catch (error) {this.publish({message: `原取消请求尚未确认：${reason(error)}`});}
  }
  private receiveCancel(reply: SelectionReply, request: SelectionCancelRequest): void {
    if (this.state.cancel_request?.request_id !== request.request_id) return;
    if (!selectionReplyMatches(reply, request) || reply.target_request_id !== request.target_request_id) {
      this.publish({message: '取消回执身份不匹配，保留原请求继续核对。'}); return;
    }
    if (reply.status === 'pending' || reply.status === 'unknown') {this.publish({message: reply.message || '取消仍待原任务真正结束。'}); return;}
    if (!['cancelled', 'rejected', 'applied', 'no_change'].includes(reply.status)) {this.publish({message: '取消回执尚未给出确定结果。'}); return;}
    this.publish({cancel_request: null, message: reply.message || '取消请求已有确定结果，继续核对原操作。'});
    this.release(request);
    if (reply.status === 'cancelled') {
      ++this.generation;
      const target = this.state.request;
      if (this.heldPreview?.request.request_id === request.target_request_id) {this.release(this.heldPreview.request); this.heldPreview = null;}
      if (!target || (target.request_id === request.target_request_id && target.action !== 'apply')) {
        if (target) this.release(target);
        if (this.cancelClearsDraft) this.publish({...this.emptyState(), phase: 'cancelled', message: '原读取任务已实际结束，本次选区草稿已取消，图层历史未改变。'});
        else this.publish({request: null, phase: 'editing', ...unreviewed(), message: '旧审核预览已释放，草稿保留。'});
      }
      // Even a cancellation reply must not erase an apply whose outcome is not known.
    }
  }
  private async checkCancel(): Promise<void> {
    const request = this.state.cancel_request; if (!request || !this.port.receipt || this.cancelChecking) return;
    this.cancelChecking = true;
    try {this.receiveCancel(await selectionBounded(this.port.receipt(request), this.options.timeoutMs), request);}
    catch (error) {this.publish({message: `取消结果仍待核对：${reason(error)}`});}
    finally {this.cancelChecking = false;}
  }
  async refresh(): Promise<void> {
    const terminal = this.terminal;
    if (!terminal || this.state.refresh === 'working' || this.state.refresh === 'ready') return;
    if (!this.options.onApplied) {this.publish({refresh: 'failed', message: '真实蒙版已应用，但未接入宿主状态回读。请勿重复应用。'}); return;}
    this.publish({refresh: 'working'});
    try {await selectionBounded(Promise.resolve(this.options.onApplied(terminal.reply, terminal.request)), this.options.timeoutMs);
      if (terminal === this.terminal) this.publish({refresh: 'ready'});
    } catch (error) {if (terminal === this.terminal) this.publish({refresh: 'failed', message: `已应用，但工作区回读失败：${reason(error)}。只能重试回读。`});}
  }
}
