// SPDX-License-Identifier: GPL-3.0-or-later
import {
  checkedAnchors, checkedCurrent, checkedPreview, checkedReceipt, checkedRules, checkedWorkspaceReopened, emptyRules,
  imageKey, point, record, PortraitCropNotSentError,
  type AnchorName, type Anchors, type Current, type Preview, type Receipt, type Request,
  type RuleDraft, type Transport,
} from './model.ts';
export type PortraitCropState = {
  phase: 'idle' | 'working' | 'uncertain'; checking: boolean; enabled: boolean; message: string;
  current: Current | null; selectedFace: string | null; anchors: Partial<Anchors>; rules: RuleDraft;
  confirmations: Record<AnchorName, boolean>; sourceReady: boolean;
  preview: Preview | null; beforeReady: boolean; afterReady: boolean; reviewConfirmed: boolean;
  pending: {request_id: string; action: Request['action']} | null;
  historicalUnknown: {request_id: string; action: Request['action']; document_id: string | null; reopened_project_id: string} | null;
};
type Pending = {request: Request; context: string; digest: string | null; discarded: boolean; documentId: string | null; documentRevision: string | number | null};
const clearConfirmations = () => ({crown: false, chin: false, face_center: false});
const errorText = (error: unknown) => error instanceof Error ? error.message : '操作结果尚未确认，请查询原请求。';
const clone = <T,>(value: T): T => structuredClone(value);
/** Keep ONE controller alive at App scope. Closing the panel never forgets an unknown write. */
export class PortraitCropController {
  private context: string | null = null;
  private active: Pending | null = null;
  private checking: Promise<void> | null = null;
  private listeners = new Set<() => void>();
  private value: PortraitCropState = {
    phase: 'idle', checking: false, enabled: false, message: '', current: null,
    selectedFace: null, anchors: {}, rules: emptyRules(), confirmations: clearConfirmations(), sourceReady: false,
    preview: null, beforeReady: false, afterReady: false, reviewConfirmed: false, pending: null, historicalUnknown: null,
  };
  constructor(private transport: Transport, private onCommitted: (receipt: Receipt) => void | Promise<unknown> = () => undefined) {}
  snapshot = (): PortraitCropState => this.value;
  subscribe = (listener: () => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private emit(patch: Partial<PortraitCropState>) {this.value = {...this.value, ...patch}; this.listeners.forEach(listener => listener());}
  private reset(): Partial<PortraitCropState> {
    return {current: null, selectedFace: null, anchors: {}, confirmations: clearConfirmations(), sourceReady: false,
      preview: null, beforeReady: false, afterReady: false, reviewConfirmed: false};
  }
  /** Identity must cover the current document/source/edit/repair/analysis revisions, not a path. */
  setContext(key: string | null) {
    if (key === this.context) return;
    this.context = key;
    if (this.active) this.active.discarded = true;
    this.emit({...this.reset(), message: this.active ? '照片或编辑状态已变化。仍保留旧原请求供查询，不会应用其迟到预览。' : ''});
  }
  setEnabled(enabled: boolean) {if (enabled !== this.value.enabled) this.emit({enabled});}
  private idle() {
    if (this.active) throw Error('请先等待或查询原请求，不能重复提交。');
    if (!this.context || !this.value.enabled) throw Error('请等待当前照片、引擎与其他编辑工具就绪。');
  }
  private current(): Current {
    this.idle(); if (!this.value.current) throw Error('请先捕获当前完整编辑照片。'); return this.value.current;
  }
  private invalidate() {return {preview: null, beforeReady: false, afterReady: false, reviewConfirmed: false};}
  selectFace(faceId: string) {
    const current = this.current();
    if (!current.source.faces.some(face => face.face_id === faceId)) throw Error('所选人脸不属于本次当前照片分析。');
    // Selecting a detection never measures or confirms the genuine hair crown.
    this.emit({selectedFace: faceId, anchors: {}, confirmations: clearConfirmations(), ...this.invalidate(), message: ''});
  }
  useFaceProposal() {
    const current = this.current();
    if (!this.value.sourceReady) throw Error('请先等待当前照片图像校验完成。');
    const face = current.source.faces.find(item => item.face_id === this.value.selectedFace);
    if (!face) throw Error('请明确选择本次构图的人脸。');
    this.emit({anchors: {version: 1, chin: [...face.chin_proposal], face_center: [...face.center_proposal]}, confirmations: clearConfirmations(), ...this.invalidate(), message: '已采用人脸中心及下巴提议，仍须人工确认。头顶必须在照片上单独测量。'});
  }
  mark(name: AnchorName, coordinate: [number, number]) {
    const current = this.current();
    if (!this.value.sourceReady || !this.value.selectedFace) throw Error('请先加载当前照片并明确选择人脸。');
    if (!point(coordinate, current.source.width, current.source.height)) throw Error('坐标必须位于当前完整来源像素范围内。');
    this.emit({anchors: {...this.value.anchors, version: 1, [name]: [...coordinate]}, confirmations: clearConfirmations(), ...this.invalidate(), message: ''});
  }
  invalidateMeasurement() {this.current(); this.emit({confirmations: clearConfirmations(), ...this.invalidate()});}
  clearAnchors() {this.current(); this.emit({anchors: {}, confirmations: clearConfirmations(), ...this.invalidate(), message: ''});}
  confirmAnchor(name: AnchorName, confirmed: boolean) {
    this.current();
    if (!this.value.sourceReady || !this.value.anchors[name]) throw Error('先测量并检查该锚点，不能确认空白或未加载的照片。');
    this.emit({confirmations: {...this.value.confirmations, [name]: confirmed}, ...this.invalidate()});
  }
  setRules(rules: RuleDraft) {this.current(); this.emit({rules: clone(rules), ...this.invalidate(), message: ''});}
  sourceImageReady(key: string, ready: boolean) {
    const current = this.value.current;
    if (!current || key !== `${current.session_id}:${imageKey(current.source.image)}`) return;
    this.emit({sourceReady: ready, ...(!ready ? {confirmations: clearConfirmations(), ...this.invalidate()} : {})});
  }
  previewImageReady(token: string, side: 'before' | 'after', key: string, ready: boolean) {
    const preview = this.value.preview;
    if (!preview || preview.preview_token !== token || imageKey(preview[side]) !== key) return;
    this.emit({[side === 'before' ? 'beforeReady' : 'afterReady']: ready, ...(!ready ? {reviewConfirmed: false} : {})});
  }
  confirmReview(confirmed: boolean) {
    this.current();
    if (!this.value.preview || !this.value.beforeReady || !this.value.afterReady) throw Error('必须先校验并查看本候选完整的前后照片。');
    this.emit({reviewConfirmed: confirmed});
  }
  private request(action: Request['action'], payload: Record<string, unknown> = {}): Request {
    return {cmd: 'portrait_crop', action, request_id: `portrait-crop-${crypto.randomUUID()}`, ...clone(payload)};
  }
  async acquire(): Promise<void> {
    this.idle();
    if (this.value.current) {
      const oldContext = this.context;
      await this.cancel();
      if (this.active || oldContext !== this.context || this.value.current) return;
    }
    this.emit({...this.reset(), message: ''});
    await this.run(this.request('current'));
  }
  async prepare(): Promise<void> {
    const current = this.current();
    if (!this.value.sourceReady || !this.value.selectedFace || Object.values(this.value.confirmations).some(v => !v)) throw Error('请加载真实照片，明确选择人脸，并分别确认真实头顶、下巴及人脸中心。');
    const anchors = checkedAnchors(this.value.anchors, current.source.width, current.source.height), rules = checkedRules(this.value.rules);
    this.emit({...this.invalidate(), message: ''});
    await this.run(this.request('preview', {session_id: current.session_id, capture_sha256: current.capture_sha256,
      face_id: this.value.selectedFace, anchors, rules,
      anchor_review: {image_sha256: current.source.image.sha256, crown_confirmed: true, chin_confirmed: true, center_confirmed: true}}));
  }
  async apply(): Promise<void> {
    const current = this.current(), preview = this.value.preview;
    if (!preview || preview.capture_sha256 !== current.capture_sha256 || !this.value.beforeReady || !this.value.afterReady || !this.value.reviewConfirmed) throw Error('请先明确核对并确认完整前后候选图。');
    await this.run(this.request('apply', {session_id: current.session_id, capture_sha256: current.capture_sha256,
      preview_request_id: preview.preview_request_id, preview_token: preview.preview_token,
      candidate_sha256: preview.candidate_sha256, before_image_sha256: preview.before.sha256,
      after_image_sha256: preview.after.sha256, review: 'full_before_after_confirmed'}));
  }
  async cancel(): Promise<void> {
    if (this.active) {
      // A close or cancel never converts an unknown apply into a no-write result.
      const original = this.active;
      if (original.request.action === 'apply') {this.emit({message: '应用原请求仍待确认。关闭不会撤销或重新发送它，请查询原请求。'}); return;}
      original.discarded = true;
      this.emit({...this.reset(), message: '已放弃显示此候选；正在核对原准备请求，尚未声称它已取消。'});
      if (original.digest && this.transport.cancelRead) {
        try {await this.transport.cancelRead(clone(original.request), original.digest);} catch { /* Query, never infer no write. */ }
      }
      await this.reconcile(); return;
    }
    if (!this.value.current) {this.emit({...this.reset(), message: ''}); return;}
    const session = this.value.current.session_id;
    this.emit({reviewConfirmed: false});
    await this.run(this.request('cancel', {session_id: session}));
  }
  /** Safe to call on Escape, close and route dismissal. Original requests remain queryable. */
  dismiss(): void {
    this.emit({reviewConfirmed: false});
    if (this.active) {
      if (this.active.request.action !== 'apply') this.active.discarded = true;
      this.emit({...this.reset(), message: this.active.request.action === 'apply' ? '窗口已关闭，应用结果仍待查询；不会重复提交。' : '窗口已关闭，迟到预览不会恢复。'});
      void this.cancel().catch(error => this.emit({message: errorText(error)}));
    } else if (this.value.current) {void this.cancel().catch(error => this.emit({message: errorText(error)}));}
  }
  private async run(request: Request): Promise<void> {
    if (request.action === 'cancel') {if (this.active) throw Error('请先核对原请求。');}
    else this.idle();
    const pending: Pending = {request: clone(request), context: this.context ?? '', digest: null, discarded: false, documentId: this.value.current?.binding.document_id ?? null, documentRevision: this.value.current?.binding.revision ?? null};
    this.active = pending;
    this.emit({phase: 'working', pending: {request_id: request.request_id, action: request.action}, message: ''});
    try {
      const reply = await this.transport.send(clone(pending.request), value => {
        if (this.active !== pending) return;
        try {this.accept(pending, value);} catch (error) {this.uncertain(pending, error);}
      });
      if (this.active === pending) this.accept(pending, reply);
    } catch (error) {
      if (this.active === pending && error instanceof PortraitCropNotSentError) {
        this.active = null;
        this.emit({phase: 'idle', pending: null, reviewConfirmed: false, message: error.message});
      } else this.uncertain(pending, error);
    }
  }
  private uncertain(pending: Pending, error: unknown) {
    if (this.active !== pending) return;
    this.emit({phase: 'uncertain', reviewConfirmed: false, message: errorText(error)});
  }
  private accept(pending: Pending, value: unknown): void {
    if (this.active !== pending) return;
    // Only native-verified authoritative reopen can retire a workspace lock.
    // A changed context, process restart or missing receipt is not such evidence.
    if (record(value) && value.workspace_reopened === true) {
      const reopened = checkedWorkspaceReopened(value, pending.request);
      this.active = null;
      this.emit({...this.reset(), phase: 'idle', pending: null,
        historicalUnknown: {request_id: pending.request.request_id, action: pending.request.action,
          document_id: pending.documentId, reopened_project_id: reopened.authoritative_event.project_id},
        message: pending.request.action === 'apply'
          ? '工程已通过原生通道确认重新打开，已解除旧工作区编辑锁。原应用操作的历史结果仍未知，不能视为已应用、已取消或未写入；新操作必须重新捕获并复核。'
          : '工程已通过原生通道确认重新打开，已解除旧工作区准备锁。原来源/候选准备或会话清理的历史结果仍未知，不能称为已完成或已取消；它不是裁剪应用请求。新操作必须重新捕获并复核。'});
      return;
    }
    // Native status may unwrap for us; otherwise only accept a well-formed status wrapper.
    if (record(value) && value.phase === 'status' && value.action === 'status') {
      if (!record(value.original_request) || value.original_request.target_request_id !== pending.request.request_id || value.request_id !== value.original_request.request_id) throw Error('查询包装不属于本次原请求。');
      checkedReceipt(value, value.original_request as Request, null);
      value = value.receipt;
    }
    const receipt = checkedReceipt(value, pending.request, pending.digest);
    pending.digest = receipt.command_sha256;
    if (receipt.phase === 'working') {
      if (!['current', 'preview'].includes(pending.request.action) || receipt.no_write !== true) throw Error('准备回执缺少明确未写入凭据。');
      this.emit({phase: 'working', message: '正在准备真实照片候选；尚未修改照片。'}); return;
    }
    if (receipt.phase === 'unknown') {this.emit({phase: 'uncertain', reviewConfirmed: false, message: receipt.message ?? receipt.error ?? '原请求结果未知，请查询；不会重复提交。'}); return;}
    let patch: Partial<PortraitCropState> = {};
    let publication: Receipt | null = null;
    const relevant = !pending.discarded && pending.context === this.context;
    if (receipt.phase === 'rejected' || receipt.phase === 'cancelled') {
      if (receipt.no_write !== true) throw Error('拒绝或取消回执缺少明确未写入凭据。');
      patch = {message: receipt.message ?? receipt.error ?? (receipt.phase === 'cancelled' ? '已取消，照片未改变。' : '本次请求被拒绝，照片未改变。'), reviewConfirmed: false};
      if (pending.request.action === 'cancel' || pending.discarded) patch = {...patch, ...this.reset()};
    } else if (pending.request.action === 'current' && receipt.phase === 'current_ready') {
      const current = checkedCurrent(receipt.current);
      if (relevant) patch = {...this.reset(), current, message: current.source.faces.length ? '请选择人脸，并在真实当前照片上测量头顶。' : '本次真实分析未找到可用人脸，不能假造中心或头顶。'};
    } else if (pending.request.action === 'preview' && receipt.phase === 'ready') {
      if (relevant) {
        const current = this.value.current;
        if (!current || current.session_id !== pending.request.session_id || current.capture_sha256 !== pending.request.capture_sha256) throw Error('候选所属捕获已失效。');
        const preview = checkedPreview(receipt.preview, current, pending.request);
        patch = {preview, beforeReady: false, afterReady: false, reviewConfirmed: false, message: '实际完整候选已生成，尚未应用。请查看并明确确认前后照片。'};
      }
    } else if (pending.request.action === 'apply' && receipt.phase === 'committed') {
      if (!receipt.result || !['applied', 'no_change'].includes(receipt.result.status) || receipt.original_request_id !== pending.request.request_id || receipt.preview_token !== pending.request.preview_token || receipt.candidate_sha256 !== pending.request.candidate_sha256 || !this.validCommitDocument(pending, receipt)) throw Error('应用回执缺少一致的原请求、文档或实际候选发布凭据。');
      patch = {...this.reset(), message: `${relevant ? '' : '旧照片的原请求已核对。'}${receipt.result.status === 'applied' ? '已通过现有裁剪历史应用核对后的构图。' : '核对后的裁剪与当前相同，没有新增修改。'}`};
      publication = receipt;
    } else throw Error('原请求收到不符合其动作的终态，仍需查询。');
    this.active = null;
    if (!relevant && pending.request.action !== 'apply') patch = {...this.reset(), message: '旧准备请求已核对；迟到结果不会恢复到当前照片。'};
    this.emit({phase: 'idle', pending: null, ...patch});
    if (publication) {
      // Refresh errors never turn a confirmed publication back into a pending mutation.
      const refreshFailed = () => this.emit({message: '裁剪发布已确认，但照片刷新失败；请刷新查看，不要重复应用。'});
      try {void Promise.resolve(this.onCommitted(publication)).catch(refreshFailed);} catch {refreshFailed();}
    }
  }
  private validCommitDocument(pending: Pending, receipt: Receipt): boolean {
    // The captured document is retained independently of UI closure or photo changes.
    const expected = pending.documentId;
    const result = receipt.result;
    if (!expected || pending.documentRevision === null || result?.document_id !== expected ||
      !((typeof result.revision === 'string' && /^\d{1,20}$/.test(result.revision)) || (Number.isSafeInteger(result.revision) && Number(result.revision) >= 0))) return false;
    const before = BigInt(pending.documentRevision), after = BigInt(result.revision);
    return result.status === 'applied' ? after > before : after === before;
  }
  reconcile(): Promise<void> {
    if (this.checking) return this.checking;
    const pending = this.active; if (!pending) return Promise.resolve();
    this.emit({checking: true});
    const query = (async () => {
      try {const reply = await this.transport.status(clone(pending.request)); if (this.active === pending) this.accept(pending, reply);}
      catch (error) {this.uncertain(pending, error);}
      finally {this.checking = null; this.emit({checking: false});}
    })();
    this.checking = query; return query;
  }
}
