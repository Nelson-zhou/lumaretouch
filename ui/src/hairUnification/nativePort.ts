// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import type {PeopleView} from '../people/model';
import {OPERATION, binding, checkDraft, checkRecipe, hasSample, key, object,
  readPresented, readReference, readResult, readReview, readWorkspaceReopened, reviewAck,
  type Action, type Binding, type Draft, type Mailbox, type Reference, type Request, type Result, type Review} from './model';

export type Workspace = {binding: Binding; reference: Reference; draft: Draft; review: Review | null};
export type RetiredOperation = {request: Request; receipt: Result; binding: Binding | null; draft: Draft | null};
export type PortState = {
  open: boolean; phase: 'idle' | 'loading' | 'editing' | 'review' | 'sending' | 'uncertain' | 'success' | 'failure';
  binding: Binding; workspace: Workspace | null; stale: boolean; request: Request | null;
  pending: boolean; uncertain: boolean; checking: boolean; preparing: boolean; refreshing: boolean;
  imagesReady: boolean; reviewed: boolean; presented: boolean; message: string; lastResult: Result | null;
  workspaceReopened: boolean; retired_request: Request | null; retired_receipt: Result | null;
  /** Unknown originals remain archived across subsequent contexts; no PNGs or shadow history. */
  retired_operations: RetiredOperation[];
};
export type Transport = {submit: (request: Request) => Promise<unknown>; status: (requestId: string) => Promise<unknown>};
const native: Transport = {submit: request => invoke('hair_unification', {request}),
  status: requestId => invoke('hair_unification_status', {request_id: requestId})};
function bounded<T>(promise: Promise<T>, ms = 10000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('原请求尚未确认；保留草稿，只查询，不重发。')), Math.max(1, ms));
    promise.then(value => {clearTimeout(timer); resolve(value);}, error => {clearTimeout(timer); reject(error);});
  });
}
const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
const MAX_RETIRED_OPERATIONS = 32, MAX_RETIRED_BYTES = 16 * 1024 * 1024;

/** App lifetime owner of drafts and original IDs. Native/engine alone owns graph, banks and history. */
export function createHairUnificationPort(canUse: () => boolean, refresh: () => Promise<void>, api: Transport = native) {
  let state: PortState = {open: false, phase: 'idle', binding: binding(null), workspace: null, stale: false, request: null,
    pending: false, uncertain: false, checking: false, preparing: false, refreshing: false,
    imagesReady: false, reviewed: false, presented: false, message: '', lastResult: null,
    workspaceReopened: false, retired_request: null, retired_receipt: null, retired_operations: []};
  let reading: Promise<void> | null = null;
  let retiredBytes = 0;
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<PortState>) => {state = {...state, ...patch}; listeners.forEach(listener => listener());};
  const locked = () => state.pending || state.checking || state.preparing || state.refreshing;
  const current = () => !!state.workspace && state.workspace.binding.key === state.binding.key && !state.stale;
  function requireTarget(active: boolean) {
    if (!canUse() || !state.binding.targetReady || !state.binding.context) throw Error(state.binding.reason || '请等待当前照片与其他操作就绪。');
    if (active && !state.binding.measured) throw Error(state.binding.reason);
  }
  function failed(error: unknown) {publish({phase: state.pending ? 'uncertain' : 'failure', uncertain: state.pending,
    message: String(error), imagesReady: false, reviewed: false, presented: false});}
  function consume(request: Request, result: Result) {
    const value = result.payload, workspace = state.workspace;
    if (!result.success) return;
    if (request.action === 'context') {
      const reference = readReference(value, request.people_context);
      if (!requestBinding) throw Error('原请求缺少保留的照片人物绑定。');
      const owned: Binding = structuredClone(requestBinding);
      // The request carries its original context even if navigation happened while loading.
      publish({workspace: {binding: owned, reference, review: null, draft: {recipe: reference.recipe,
        root_sample: reference.root_sample, tip_sample: reference.tip_sample, ownership_confirmed: false}},
        stale: owned.key !== state.binding.key, phase: 'editing', imagesReady: false, reviewed: false, presented: false,
        message: '在源图手绘本人发根或发尾参考样本，再生成完整照片对照。样本不会跨人物或跨照片复制。'});
    } else if (request.action === 'preview') {
      if (!workspace || key(request.people_context) !== key(workspace.binding.context)) throw Error('原样本草稿已丢失，不能接受候选。');
      const review = readReview(value, workspace.reference, workspace.draft);
      publish({workspace: {...workspace, review}, phase: 'review', imagesReady: false, reviewed: false, presented: false,
        message: '候选尚未应用。请完整查看干净前后照片，并确认本人样本及作用范围。'});
    } else if (request.action === 'presented') {
      if (!workspace?.review) throw Error('缺少与显示确认对应的候选。');
      readPresented(value, workspace.review);
      publish({phase: 'review', presented: true, message: '这份完整前后图及本人样本的显示确认已核对；现在可应用到当前人物。'});
    } else {
      if (!object(value) || value.committed !== true || value.kind !== (request.action === 'clear' ? 'cleared' : 'confirmed'))
        throw Error('原修改回执缺少确切提交结果，不能用其他照片状态证明成功。');
      const recipe = checkRecipe(value.recipe);
      if (request.action === 'clear' ? recipe.amount !== 0 : !workspace?.review
        || key(recipe) !== key(workspace.review.recipe) || value.asset_sha256 !== workspace.review.sample_asset_sha256)
        throw Error('原修改回执与本次审核配方或源照片不一致。');
      publish({phase: 'success', workspace: null, stale: false, imagesReady: false, reviewed: false, presented: false,
        message: request.action === 'clear' ? '原请求对应人物的发色统一已恢复中性；未更改原发色、光泽或其他编辑。'
          : '原请求对应照片的发色统一已应用。历史由该照片统一管理，可在主画布检查原尺寸并撤销。'});
    }
  }
  let requestBinding: Binding | null = null;
  async function poll(): Promise<void> {
    const request = state.request;
    if (!request) return;
    const end = Date.now() + 120000;
    while (state.request === request) {
      const raw = await bounded(api.status(request.request_id), Math.min(10000, end - Date.now()));
      if (!object(raw) || raw.request_id !== request.request_id) throw Error('原发色统一请求登记身份不匹配。');
      const box = raw as unknown as Mailbox;
      if (box.phase === 'done') {
        const reopened = readWorkspaceReopened(box.result, request);
        if (reopened) {
          publish({workspaceReopened: true, retired_receipt: reopened, phase: 'uncertain', pending: true, uncertain: true,
            imagesReady: false, reviewed: false, presented: false,
            message: '原生宿主已确认工程重新打开，但原操作结果仍未知。原请求和样本继续保留；只有明确确认结束旧会话保护后，才能重新载入当前工程。'});
          return;
        }
        if (state.workspaceReopened) throw Error('后续回执与已核对的旧会话未知结果矛盾，继续保留原操作保护。');
        const result = readResult(box.result, request);
        consume(request, result);
        publish({request: null, pending: false, uncertain: false, lastResult: result,
          ...(result.success ? {} : {phase: 'failure' as const, imagesReady: false, reviewed: false, presented: false,
            message: result.error || '本次请求被明确拒绝；保留原样本草稿，照片未确认改变。'})});
        requestBinding = null;
        if (result.success && (request.action === 'commit' || request.action === 'clear')) {
          publish({refreshing: true});
          try {await bounded(refresh());}
          catch {publish({message: `${state.message} 照片刷新失败，请刷新查看，不能重复提交这次修改。`});}
          finally {publish({refreshing: false});}
        }
        return;
      }
      if (box.phase !== 'pending') throw Error(box.error || '原请求不可查询；保留草稿和原编号，不重复提交。');
      if (Date.now() >= end) throw Error('原请求仍未确认；保留草稿，只能继续查询。');
      await pause(150);
    }
  }
  function recover(): Promise<void> {
    if (state.preparing) return Promise.resolve();
    if (!state.request) return Promise.resolve();
    if (!reading) {
      publish({checking: true});
      reading = poll().catch(failed).finally(() => {reading = null; publish({checking: false});});
    }
    return reading;
  }
  function canDismissReopened(): boolean {
    if (!state.workspaceReopened || !state.request || !state.retired_receipt || state.checking || state.preparing || state.refreshing) return false;
    try {return readWorkspaceReopened(state.retired_receipt, state.request) !== null;} catch {return false;}
  }
  async function send(action: Action, payload: Record<string, unknown>): Promise<void> {
    if (locked()) return;
    try {
      requireTarget(action !== 'clear');
      const context = structuredClone(state.binding.context!), originalKey = state.binding.key;
      const request: Request = {cmd: 'hair_unification', protocol: 1, operation_id: OPERATION,
        request_id: `hair-unification-${crypto.randomUUID()}`, action, people_context: context, payload: structuredClone(payload)};
      if (new TextEncoder().encode(JSON.stringify(request)).byteLength > 512 * 1024) throw Error('样本草稿超过请求预算；未提交，请先减少笔迹。');
      requestBinding = structuredClone(state.binding);
      publish({request, pending: true, preparing: true, uncertain: false, phase: 'loading', message: '正在准备本次发色统一请求。'});
      try {
        await settleCurveEdit();
        requireTarget(action !== 'clear');
        if (state.binding.key !== originalKey) throw Error('照片、人物或上游编辑已变化；请求尚未提交，草稿仍保留。');
        if (action === 'presented' || action === 'commit') {
          const review = state.workspace?.review;
          if (!state.open || !current() || !state.imagesReady || !state.reviewed || !review
            || review.preview_id !== payload.preview_id || review.review_token !== payload.review_token
            || action === 'commit' && !state.presented)
            throw Error('发送前完整审核图、本人确认或精确显示回执已失效；请求尚未提交，草稿仍保留。');
        }
      } catch (error) {
        requestBinding = null;
        publish({request: null, pending: false, preparing: false}); throw error;
      }
      publish({preparing: false, phase: action === 'commit' || action === 'clear' ? 'sending' : 'loading',
        message: '等待这一个原请求的确认；关闭面板不会丢失草稿或重发修改。'});
      if (action === 'commit' || action === 'clear') notifyInspectionEditIntent();
      try {
        const admission = await bounded(api.submit(request));
        if (object(admission) && admission.requested === false && admission.not_sent === true && admission.request_id === request.request_id) {
          requestBinding = null;
          publish({request: null, pending: false, phase: 'failure', imagesReady: false, reviewed: false, presented: false,
            message: typeof admission.error === 'string' ? admission.error : '原请求明确未发出；草稿仍保留。'});
          return;
        }
      } catch {/* Lost enqueue response is not authority to repeat the request. */}
      await recover();
    } catch (error) {failed(error);}
  }
  return {
    snapshot: () => state,
    subscribe(listener: () => void) {listeners.add(listener); return () => {listeners.delete(listener);};},
    pending: () => locked(), uncertain: () => state.uncertain, recover, canDismissReopened,
    /** Explicit UI action only after native proof; no resend, rollback claim or success refresh. */
    dismissReopened() {
      if (!canDismissReopened() || !state.request || !state.retired_receipt) return;
      const request = structuredClone(state.request), receipt = structuredClone(state.retired_receipt);
      const entry: RetiredOperation = {request, receipt, binding: requestBinding ? structuredClone(requestBinding) : null,
        draft: state.workspace ? structuredClone(state.workspace.draft) : null};
      const bytes = new TextEncoder().encode(JSON.stringify(entry)).byteLength;
      if (state.retired_operations.length >= MAX_RETIRED_OPERATIONS || retiredBytes + bytes > MAX_RETIRED_BYTES) {
        publish({message: '旧未知操作存档已达到本次应用的保留预算；没有删除旧记录，也未解除当前操作保护。请保留当前工程并使用明确的工程恢复流程。'});
        return;
      }
      retiredBytes += bytes;
      requestBinding = null;
      publish({request: null, pending: false, uncertain: false, workspaceReopened: false, workspace: null, stale: true,
        imagesReady: false, reviewed: false, presented: false, phase: 'idle', lastResult: null,
        retired_request: request, retired_receipt: receipt, retired_operations: [...state.retired_operations, entry],
        message: '已按明确确认结束旧工程会话的操作保护。原操作仍未知，原请求、回执和样本已保留，未当作成功、拒绝或撤销，也不会重发。请重新载入当前工程人物并重新审核。'});
    },
    context(people: PeopleView | null | undefined) {
      const next = binding(people);
      if (next.key === state.binding.key) return;
      const stale = !!state.workspace && state.workspace.binding.key !== next.key;
      publish({binding: next, stale, imagesReady: false, reviewed: false, presented: false,
        ...(stale ? {message: state.pending ? '照片或人物已变化；保留原样本与原请求，仅查询原结果。'
          : '原样本仍保留，但来源或人物状态已变化，不能应用；可丢弃旧草稿后重新载入。'} : {})});
    },
    open() {
      publish({open: true});
      if (!state.workspace && !locked()) void send('context', {});
    },
    close() {publish({open: false, imagesReady: false, reviewed: false, presented: false,
      message: state.pending ? '面板已关闭，原请求与样本草稿仍保留；请查询原结果，不重发。' : '未应用的样本草稿已保留。'});},
    discard() {
      if (locked()) return;
      publish({workspace: null, stale: false, imagesReady: false, reviewed: false, presented: false, phase: 'idle',
        message: '未应用的样本草稿已丢弃，没有写入照片。'});
    },
    edit(next: Draft) {
      if (locked() || !current() || !state.workspace) return;
      try {
        const draft = checkDraft(next), previous = state.workspace.draft;
        if (key(draft.root_sample) !== key(previous.root_sample) || key(draft.tip_sample) !== key(previous.tip_sample)) draft.ownership_confirmed = false;
        publish({workspace: {...state.workspace, draft, review: null}, phase: 'editing', imagesReady: false, reviewed: false, presented: false,
          message: '样本或程度草稿已改变，必须重新生成完整前后图。'});
      } catch (error) {failed(error);}
    },
    preview() {
      if (locked() || !state.open || !current() || !state.workspace) return Promise.resolve();
      const {reference, draft} = state.workspace;
      if (!reference.native_available || !reference.support_sha256 || !reference.semantic_evidence_sha256
        || !draft.ownership_confirmed || draft.recipe.amount === 0
        || !hasSample(draft.recipe.amount < 0 ? draft.tip_sample : draft.root_sample)) {
        failed('请先审核此人物的真实头发范围，手绘所用的本人发根或发尾样本，确认归属并选择非零程度。');
        return Promise.resolve();
      }
      publish({imagesReady: false, reviewed: false, presented: false});
      return send('preview', {...draft, ownership_confirmed: true});
    },
    imagesReady(previewId: string, ready: boolean) {
      if (state.workspace?.review?.preview_id !== previewId) return;
      publish({imagesReady: ready, ...(!ready ? {reviewed: false, presented: false} : {})});
    },
    reviewed(previewId: string, checked: boolean) {
      if (locked() || !current() || state.workspace?.review?.preview_id !== previewId || !state.imagesReady) return;
      publish({reviewed: checked, presented: false});
    },
    acknowledge() {
      const review = state.workspace?.review;
      if (locked() || !state.open || !current() || !review || !state.imagesReady || !state.reviewed || state.presented) return Promise.resolve();
      return send('presented', reviewAck(review));
    },
    commit() {
      const review = state.workspace?.review;
      if (locked() || !state.open || !current() || !review || !state.imagesReady || !state.reviewed || !state.presented) return Promise.resolve();
      return send('commit', {preview_id: review.preview_id, review_token: review.review_token, confirmed: true});
    },
    clear() {
      if (state.workspace && !current()) {
        failed('当前显示的样本属于旧人物或旧照片状态；请先丢弃旧草稿，再为当前人物恢复中性。');
        return Promise.resolve();
      }
      return send('clear', {});
    },
    failed,
  };
}
export type HairUnificationPort = ReturnType<typeof createHairUnificationPort>;
