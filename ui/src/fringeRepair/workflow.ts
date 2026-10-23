import {receiptKey, sourceKey, validDraft, validStroke, MAX_STROKES, MAX_TOTAL_POINTS, type FringeDraft, type FringeMutation,
  type FringeReceipt, type FringeRequest, type FringeReview, type FringeStroke} from './model';
import {acknowledgeReview, awaitReview, bounded, type FringeTransport, type PreviewIdentity} from './protocol';
import {awaitReceipt, readInventory, type AuditEntry} from './receipts';

export interface FringeContext {
  enabled: boolean; canStart?: boolean; documentId: string; contextKey: string; reason?: string;
}
export interface FringeState {
  open: boolean;
  phase: 'idle' | 'preparing' | 'loading' | 'editing' | 'ready' | 'confirming' | 'sending' | 'uncertain' | 'success' | 'failure';
  inventory: 'pending' | 'ready' | 'failed'; audit: AuditEntry[];
  draft: FringeDraft | null; review: FringeReview | null; previewId: string | null; reviewPreviewId: string | null;
  dirty: boolean; presented: boolean; strokeActive: boolean; message: string;
  request: FringeRequest | null; receipt: FringeReceipt | null; querying: boolean;
}
interface Options {
  prepare?: () => void | Promise<void>; beforeSubmit?: () => void | Promise<void>;
  refresh: () => Promise<void>; id?: () => string; timeoutMs?: number; sleep?: (ms: number) => Promise<void>;
}
interface Session {id: string; document: string; context: string}
const initial = (): FringeState => ({open: false, phase: 'idle', inventory: 'pending', audit: [],
  draft: null, review: null, previewId: null, reviewPreviewId: null, dirty: false, presented: false,
  strokeActive: false, message: '', request: null, receipt: null, querying: false});

/** Draft gestures never mutate a document. Only an explicitly reviewed candidate
 * enters the single native receipt owner; failures after that boundary are read-only. */
export function createFringeWorkflow(api: FringeTransport, options: Options) {
  let state = initial(), context: FringeContext = {enabled: false, documentId: '', contextKey: ''};
  let session: Session | null = null, alive = true, life = 0, revision = 0, generation: string | null = null;
  let inventoryToken: symbol | null = null, queryToken: symbol | null = null, ackToken: symbol | null = null;
  const listeners = new Set<(value: FringeState) => void>();
  const id = options.id ?? (() => crypto.randomUUID().replaceAll('-', ''));
  const timeout = options.timeoutMs ?? 120000;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)));
  const publish = (patch: Partial<FringeState>) => {state = {...state, ...patch}; if (alive) listeners.forEach(listener => listener(state));};
  const busy = () => state.inventory !== 'ready' || state.audit.some(entry => entry.unresolved) ||
    state.phase === 'sending' || state.phase === 'uncertain';
  const canStart = () => context.canStart !== false;
  const current = (owner: Session) => alive && session === owner && context.enabled &&
    context.documentId === owner.document && context.contextKey === owner.context;
  const identity = (owner: Session, preview: string): PreviewIdentity => ({preview, session: owner.id, document: owner.document});
  function release(cancelNative = true) {
    const old = session, preview = state.previewId;
    session = null; revision++; ackToken = null;
    if (cancelNative && old && preview) void api.preview('cancel', preview, old.id, old.document).catch(() => {});
  }
  function clear(patch: Partial<FringeState>) {
    publish({...initial(), inventory: state.inventory, audit: state.audit, receipt: state.receipt, ...patch});
  }
  async function initialize() {
    if (!alive || state.inventory === 'ready' || inventoryToken) return;
    const token = Symbol('fringe-inventory'), mounted = life; inventoryToken = token;
    const valid = () => alive && mounted === life && inventoryToken === token;
    publish({inventory: 'pending', message: '正在核对本次应用进程的祛边原操作记录…'});
    try {
      const raw = await bounded(api.audit(), Math.min(timeout, 10000)); if (!valid()) return;
      const inventory = readInventory(raw); generation = inventory.generation;
      const pending = inventory.entries.find(entry => entry.unresolved);
      publish({inventory: 'ready', audit: inventory.entries, request: pending?.original_request ?? null,
        phase: pending ? 'uncertain' : 'idle', message: pending ? '仍有祛边原操作待确认，只能查询，不会重发。' : ''});
    } catch (error) {if (valid()) publish({inventory: 'failed', message: `原操作登记不可用，继续保护编辑：${String(error)}`});}
    finally {if (inventoryToken === token) inventoryToken = null;}
  }
  function cancel(message = '未应用的祛边草稿已丢弃，照片未修改') {
    if (busy()) {publish({open: false, message: '关闭窗口不会撤回已发送的操作；原操作仍保留，确认结果前保护编辑。'}); return;}
    release(); clear({message});
  }
  function failed(error: unknown, preview?: string) {
    if ((preview !== undefined && preview !== state.previewId) || busy()) return;
    revision++; ackToken = null;
    publish({phase: 'failure', presented: false, strokeActive: false, dirty: true, message: String(error)});
  }
  async function render(mutation: FringeMutation) {
    const owner = session;
    if (!owner || !current(owner) || busy() || state.strokeActive ||
        (mutation.action === 'set' && !validDraft(mutation))) return;
    const sequence = ++revision, preview = id(); ackToken = null;
    const proposal = structuredClone(mutation);
    const valid = () => current(owner) && sequence === revision && state.previewId === preview;
    publish({phase: 'loading', previewId: preview, presented: false, dirty: false,
      message: '正在按当前来源的全尺寸数据计算祛边，再生成缩小审核图…'});
    try {
      await bounded(api.preview('preview', preview, owner.id, owner.document, proposal), timeout);
      if (!valid()) return;
      const review = await awaitReview(api, identity(owner, preview), {timeout, sleep, current: valid});
      if (!valid() || !review) return;
      if (state.review && (review.recipe_document_id !== state.review.recipe_document_id ||
          review.recipe_revision !== state.review.recipe_revision || sourceKey(review.source) !== sourceKey(state.review.source)))
        throw Error('祛边草稿的来源或基线配方已变化，请重新进入');
      const draft: FringeDraft = proposal.action === 'enter'
        ? {enabled: true, strength: review.recipe.strength, strokes: [], reset_coverage: false}
        : {enabled: proposal.enabled, strength: proposal.strength, strokes: proposal.strokes, reset_coverage: proposal.reset_coverage};
      if (proposal.action === 'enter' && !review.recipe.enabled) throw Error('进入祛边时未返回默认启用效果');
      publish({phase: 'ready', draft, review, reviewPreviewId: preview, dirty: false,
        message: '请检查真实前后对照。添加或擦除只改变草稿，须点更新效果，再确定应用。'});
    } catch (error) {if (valid()) failed(error, preview);}
  }
  async function start() {
    if (!alive || busy() || state.open || state.phase === 'preparing' || !context.enabled || !canStart() || !context.documentId) return;
    release(); const sequence = revision, mounted = life, document = context.documentId;
    clear({phase: 'preparing', message: '正在等待已有编辑结束…'});
    try {
      await bounded(Promise.resolve(options.prepare?.()), timeout);
      if (!alive || life !== mounted || revision !== sequence) return;
      if (!context.enabled || !canStart() || context.documentId !== document) throw Error(context.reason || '照片状态已变化，请重新进入祛边');
      session = {id: id(), document, context: context.contextKey};
      publish({open: true}); await render({action: 'enter'});
    } catch (error) {if (alive && life === mounted && revision === sequence) failed(error);}
  }
  function edit(next: FringeDraft) {
    if (!session || !current(session) || busy() || !validDraft(next) ||
        ['loading', 'confirming'].includes(state.phase) || state.strokeActive) return;
    revision++; ackToken = null;
    publish({draft: structuredClone(next), dirty: true, presented: false, phase: 'editing',
      message: '范围或程度有未计算修改。请点更新效果，旧预览不能直接应用。'});
  }
  async function presented(preview: string) {
    const owner = session, review = state.review;
    if (!owner || !review || !current(owner) || busy() || state.phase !== 'ready' || state.previewId !== preview || state.reviewPreviewId !== preview ||
        state.dirty || state.strokeActive || state.presented || ackToken) return;
    const token = Symbol('fringe-presented'), sequence = revision; ackToken = token;
    const valid = () => current(owner) && sequence === revision && state.previewId === preview && state.phase === 'ready' && !state.dirty;
    try {
      const accepted = await acknowledgeReview(api, identity(owner, preview), review, {timeout, sleep, current: valid});
      if (valid() && accepted) publish({presented: true});
    } catch (error) {if (valid()) failed(error, preview);}
    finally {if (ackToken === token) ackToken = null;}
  }
  async function check() {
    const request = state.request;
    if (!alive || !request || queryToken || state.inventory !== 'ready') return;
    const token = Symbol('fringe-receipt'), mounted = life; queryToken = token;
    const valid = () => alive && life === mounted && queryToken === token && state.request === request;
    publish({querying: true});
    try {
      const receipt = await awaitReceipt(api, request, {timeout, sleep, current: valid}); if (!valid() || !receipt) return;
      const entry = state.audit.find(row => row.original_request.request_id === request.request_id);
      if (entry?.original_receipt && receiptKey(entry.original_receipt) !== receiptKey(receipt))
        throw Error('后续回执与保留的祛边原始结果矛盾，不能解除编辑保护');
      publish({receipt, audit: state.audit.map(row => row.original_request.request_id === request.request_id
        ? {...row, original_receipt: row.original_receipt ?? receipt, unresolved: receipt.outcome_unknown || receipt.requires_reload} : row)});
      if (receipt.outcome_unknown || receipt.requires_reload) throw Error(receipt.error || '引擎原结果仍未知，不能通过重复修改恢复');
      release(false);
      const remaining = state.audit.find(row => row.unresolved), message = !receipt.success ? receipt.error || '祛边应用未成功'
        : receipt.no_change ? '配方未改变，未新增历史。' : '祛边效果已应用，可在照片历史中撤销。';
      publish({open: false, phase: remaining ? 'uncertain' : receipt.success ? 'success' : 'failure',
        request: remaining?.original_request ?? null, draft: null, review: null, previewId: null, reviewPreviewId: null,
        presented: false, dirty: false, message});
      // Unlock this observer before refresh so an old finally cannot own a new query.
      queryToken = null; publish({querying: false});
      if (receipt.success) {
        const refreshedRevision = revision;
        try {await bounded(options.refresh(), 5000);} catch (error) {
          if (alive && life === mounted && revision === refreshedRevision && !state.request)
            publish({message: `${message} 界面刷新未完成：${String(error)}`});
        }
      }
    } catch (error) {if (valid()) publish({phase: 'uncertain', presented: false, message: `祛边原操作结果待确认：${String(error)}`});}
    finally {if (queryToken === token) {queryToken = null; if (alive && life === mounted) publish({querying: false});}}
  }
  const reviewCommittable = (preview: string) => state.phase === 'ready' && state.reviewPreviewId === preview &&
    state.presented && !state.dirty && !state.strokeActive;
  async function confirm() {
    const owner = session, preview = state.previewId, clientGeneration = generation;
    if (!owner || !preview || !clientGeneration || !current(owner) || busy() || !canStart() || !reviewCommittable(preview)) return;
    const sequence = revision, mounted = life;
    publish({phase: 'confirming', message: '正在核对已显示的祛边候选…'});
    try {
      await bounded(Promise.resolve(options.beforeSubmit?.()), timeout);
      if (!alive || life !== mounted || !current(owner) || revision !== sequence || state.phase !== 'confirming' ||
          state.previewId !== preview || !state.presented || generation !== clientGeneration) return;
      if (!canStart()) throw Error(context.reason || '其他操作尚未结束，请稍后重新审核');
      const request: FringeRequest = {request_id: `fringe-${id()}`, preview_id: preview, session_id: owner.id, document_id: owner.document};
      publish({phase: 'sending', request, message: '已开始应用这一份审核结果，正在等待原操作回执…',
        audit: [...state.audit, {original_request: request, original_receipt: null, engine_state: 'same_live_engine', unresolved: true}]});
      try {await bounded(api.submit(request, clientGeneration), timeout);} catch {/* Never resend an uncertain apply. */}
      if (alive && life === mounted) await check();
    } catch (error) {if (alive && life === mounted && current(owner) && sequence === revision) failed(error);}
  }
  return {
    snapshot: () => state, subscribe(listener: (value: FringeState) => void) {listeners.add(listener); return () => {listeners.delete(listener);};},
    initialize, start, cancel, failed, presented, confirm, check, busy,
    edit, update: () => state.draft ? render({action: 'set', ...state.draft}) : Promise.resolve(),
    beginStroke() {
      if (!session || !current(session) || !state.draft || busy() || state.strokeActive ||
          !['ready', 'editing'].includes(state.phase)) return false;
      if (state.draft.strokes.length >= MAX_STROKES || state.draft.strokes.reduce((total, stroke) => total + stroke.points.length, 0) >= MAX_TOTAL_POINTS) {
        publish({message: '范围草稿已达到笔迹或总点数预算，请先删除部分草稿或重置为自动范围。'}); return false;
      }
      revision++; ackToken = null; publish({strokeActive: true, presented: false}); return true;
    },
    endStroke(stroke: FringeStroke) {
      if (!state.strokeActive) return;
      publish({strokeActive: false});
      if (state.draft && validStroke(stroke) && validDraft({...state.draft, strokes: [...state.draft.strokes, stroke]}))
        edit({...state.draft, strokes: [...state.draft.strokes, stroke]});
      else failed('范围笔迹无效或超过总预算，未保存本笔；可删除部分草稿后重新更新。');
    },
    cancelStroke(message = '本笔已取消，未改变草稿范围') {
      if (!state.strokeActive) return;
      publish({strokeActive: false, message});
    },
    context(next: FringeContext) {
      const owner = session; context = next;
      if (owner && (!next.enabled || next.documentId !== owner.document || next.contextKey !== owner.context)) {
        if (busy()) publish({open: false, review: null, reviewPreviewId: null, draft: null, presented: false,
          message: '照片或编辑状态已变化，仍保留原祛边操作回执；不会重发。'});
        else cancel(next.reason || '照片、来源或上游编辑已变化，原祛边草稿已失效，请重新进入。');
      }
    },
    externalEdit() {if (session && !busy()) cancel('照片正在调整，未应用的祛边草稿已取消。');},
    activate() {alive = true;},
    stop() {
      const cancelNative = state.request === null;
      alive = false; life++; release(cancelNative); inventoryToken = queryToken = ackToken = null; generation = null;
      state = initial(); // Native inventory, not this component, owns any sent operation.
    },
  };
}
