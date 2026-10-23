import {mutationValid, object, readRecipe, readReview, type Mutation, type RecipeIdentity, type Request, type Review} from './model.ts';
import {applyReceipt, auditInventory, readbackStatus, unavailableReadback, unresolvedMessage, type Audit, type ReadbackPhase, type ReadbackRequest, type ReadbackStatus} from './readback.ts';

export interface Context {enabled: boolean; canStart?: boolean; documentId: string; contextKey: string; reason?: string; readbackEnabled?: boolean; engineKey?: string}
export interface Transport {
  preview: (action: 'preview' | 'presented' | 'cancel', preview: string, session: string, document: string, mutation?: Mutation) => Promise<unknown>;
  status: (preview: string) => Promise<unknown>;
  submit: (request: Request, clientGeneration: string) => Promise<unknown>;
  result: (request: string) => Promise<unknown>;
  readback?: (request: ReadbackRequest) => Promise<unknown>;
  readbackStatus?: (readbackId: string) => Promise<unknown>;
  audit: () => Promise<unknown>;
}
export interface State {
  open: boolean; phase: 'idle' | 'preparing' | 'loading' | 'ready' | 'confirming' | 'sending' | 'uncertain' | 'failure' | 'success';
  image: Review | null; recipe: RecipeIdentity | null; mutation: Mutation | null;
  previewId: string | null; presented: boolean; committable: boolean; message: string; request: Request | null;
  receiptQueryPending: boolean; readbackPending: boolean; readbackId: string | null; readbackPhase: ReadbackPhase | null; audit: Audit[];
  inventoryPhase: 'pending' | 'ready' | 'failed'; inventoryMessage: string; unresolved: Request[];
}
interface Options {prepare?: () => Promise<void>; beforeSubmit?: () => Promise<void>; id?: () => string; timeoutMs?: number; sleep?: (ms: number) => Promise<void>}
const initial = (): State => ({open: false, phase: 'idle', image: null, recipe: null, mutation: null,
  previewId: null, presented: false, committable: false, message: '', request: null,
  receiptQueryPending: false, readbackPending: false, readbackId: null, readbackPhase: null, audit: [],
  inventoryPhase: 'ready', inventoryMessage: '', unresolved: []});
function bounded<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('等待超时')), Math.max(1, ms));})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}

export function createWorkflow(api: Transport, refresh: () => Promise<void>, options: Options = {}) {
  let state: State = {...initial(), inventoryPhase: 'pending'}, context: Context = {enabled: false, documentId: '', contextKey: ''};
  let session: {id: string; document: string; context: string} | null = null;
  let alive = true, generation = 0, lifetime = 0, acknowledging: string | null = null;
  let queryToken: symbol | null = null, readbackToken: symbol | null = null, inventoryToken: symbol | null = null, confirmationToken: symbol | null = null;
  let clientGeneration: string | null = null;
  const listeners = new Set<(s: State) => void>();
  const id = options.id ?? (() => crypto.randomUUID().replaceAll('-', ''));
  const timeout = options.timeoutMs ?? 120000;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)));
  const publish = (patch: Partial<State>) => {state = {...state, ...patch}; if (alive) listeners.forEach(f => f(state));};
  const reset = (patch: Partial<State>) => publish({...initial(), audit: state.audit, inventoryPhase: state.inventoryPhase, inventoryMessage: state.inventoryMessage, ...patch});
  const audit = (request: Request, update: (entry: Audit) => Audit) => publish({audit: state.audit.map(entry =>
    entry.original_request.request_id === request.request_id ? update(entry) : entry)});
  const busy = () => state.inventoryPhase !== 'ready' || state.unresolved.length > 0 || state.phase === 'sending' || state.phase === 'uncertain';
  async function initialize() {
    if (!alive || state.inventoryPhase === 'ready' || inventoryToken) return;
    const token = Symbol('common-inventory'), mounted = lifetime; inventoryToken = token;
    // Inventory owns process-level identities, not the asynchronously arriving UI PID.
    // Each item carries native engine_state; readback itself still fences engine changes.
    const valid = () => alive && lifetime === mounted && inventoryToken === token;
    publish({inventoryPhase: 'pending', inventoryMessage: '正在读取本次应用进程保留的原操作记录，确认前暂时保护编辑…'});
    try {
      const raw = await bounded(api.audit(), Math.min(timeout, 10000));
      if (!valid()) return;
      const restored = auditInventory(raw);
      clientGeneration = restored.clientGeneration;
      const restoredAudit = restored.audit;
      const request = restored.unresolved[0] ?? null;
      publish({...initial(), audit: restoredAudit, unresolved: restored.unresolved, request, inventoryPhase: 'ready',
        phase: request ? 'uncertain' : 'idle', inventoryMessage: '已读取本次应用进程的原操作登记；这不是磁盘持久化回执。',
        message: request ? `恢复了 ${restored.unresolved.length} 笔待确认原操作，请逐笔查询或同引擎核对；不会重发修改。` : ''});
    } catch (error) {if (valid()) publish({inventoryPhase: 'failed', inventoryMessage: `原操作登记读取失败，继续保护编辑：${String(error)}`});}
    finally {if (inventoryToken === token) inventoryToken = null;}
  }
  const current = (s: NonNullable<typeof session>) => context.enabled && context.documentId === s.document && context.contextKey === s.context;
  function release() {
    const old = session, preview = state.previewId;
    session = null; generation++; acknowledging = null; confirmationToken = null;
    if (old && preview) void api.preview('cancel', preview, old.id, old.document).catch(() => {});
  }
  function cancel(message = '未确定的换底效果已取消，照片未修改') {
    if (busy()) {publish({open: false, message: state.request ? '操作已经发送，关闭窗口不撤销操作；可查询原操作结果，不会重复提交' : '原操作登记尚未核实，关闭窗口不解除编辑保护'}); return;}
    release(); reset({message});
  }
  function failed(error: unknown, previewId?: string) {
    if (previewId !== undefined && previewId !== state.previewId) return;
    if (busy()) return; // A late image event is not evidence about a sent mutation.
    release(); publish({phase: 'failure', image: null, recipe: null, previewId: null,
      presented: false, committable: false, message: String(error)});
  }
  function identity(raw: unknown, preview: string, s: NonNullable<typeof session>): Record<string, unknown> {
    if (!object(raw) || raw.protocol !== 1 || raw.preview_id !== preview ||
        raw.session_id !== s.id || raw.document_id !== s.document) throw Error('换底预览身份或协议变化');
    return raw;
  }
  async function render(mutation: Mutation) {
    const s = session;
    if (!alive || !s || busy() || !current(s)) return;
    if (!mutationValid(mutation)) {failed('背景参数超出允许范围'); return;}
    const previous = state.previewId, token = ++generation, preview = id();
    if (previous) void api.preview('cancel', previous, s.id, s.document).catch(() => {});
    const proposal = structuredClone(mutation);
    publish({phase: 'loading', image: null, recipe: null, mutation: proposal, previewId: preview,
      presented: false, committable: false, message: '正在计算本次调整前后的真实照片…'});
    try {
      await bounded(api.preview('preview', preview, s.id, s.document, proposal), timeout);
      const deadline = Date.now() + timeout;
      while (alive && session === s && generation === token) {
        if (Date.now() >= deadline) throw Error('等待换底预览超时');
        const raw = await bounded(api.status(preview), deadline - Date.now());
        if (!alive || session !== s || generation !== token) return;
        const result = identity(raw, preview, s);
        if (result.state === 'running' || result.state === 'pending') {await sleep(100); continue;}
        if (result.state !== 'ready' || result.success !== true) throw Error(typeof result.error === 'string' ? result.error : '换底预览不可用');
        const recipe = readRecipe(result), image = readReview(result.image);
        publish({phase: 'ready', recipe, image, committable: true,
          message: proposal.action === 'clear' ? '请对照检查还原后的照片，确认后才会清除换底' : '请对照检查人物、发丝与衣物边缘，确认后才会应用'});
        return;
      }
    } catch (error) {if (alive && session === s && generation === token) failed(error);}
  }
  async function start(mutation: Mutation) {
    if (!alive || busy() || state.phase === 'preparing' || !context.enabled || context.canStart === false || !context.documentId) return;
    release(); const token = generation, document = context.documentId;
    // Do not acquire visible review ownership until the peer-owner preflight succeeds.
    // Otherwise rejecting a launch could itself disable and discard another editor's draft.
    reset({phase: 'preparing', mutation: structuredClone(mutation), message: '正在等待已有编辑完成…'});
    try {
      await bounded(options.prepare?.() ?? Promise.resolve(), timeout);
      if (!alive || generation !== token) return;
      if (!context.enabled || context.documentId !== document || context.canStart === false) throw Error(context.reason || '照片或编辑状态已变化，请重新预览');
      session = {id: id(), document, context: context.contextKey};
      publish({open: true});
      await render(mutation);
    } catch (error) {if (alive && generation === token) failed(error);}
  }
  async function presented(preview: string) {
    const s = session, recipe = state.recipe;
    if (!alive || !s || !recipe || preview !== state.previewId || state.phase !== 'ready' ||
        !state.committable || state.presented || acknowledging === preview || !current(s)) return;
    acknowledging = preview;
    try {
      // The native command must accept the acknowledgment, then the retained engine receipt must agree.
      await bounded(api.preview('presented', preview, s.id, s.document), Math.min(timeout, 10000));
      const deadline = Date.now() + Math.min(timeout, 10000);
      while (alive && session === s && state.previewId === preview && state.phase === 'ready') {
        if (Date.now() >= deadline) throw Error('等待换底显示确认超时');
        const raw = await bounded(api.status(preview), deadline - Date.now());
        if (!alive || session !== s || state.previewId !== preview || state.phase !== 'ready') return;
        const result = identity(raw, preview, s), proof = readRecipe(result);
        if (proof.recipe_document_id !== recipe.recipe_document_id || proof.recipe_revision !== recipe.recipe_revision) throw Error('换底效果与当前配方版本不一致');
        if (result.state === 'presented' && result.success === true) {publish({presented: true}); return;}
        if (result.state !== 'ready' || result.success !== true) throw Error('换底效果显示确认失败');
        await sleep(60);
      }
    } catch (error) {if (alive && session === s && state.previewId === preview) failed(error);}
    finally {if (acknowledging === preview) acknowledging = null;}
  }
  async function settleReceipt(request: Request, raw: unknown, source: 'original-receipt' | 'readback') {
    const result = applyReceipt(raw, request);
    audit(request, entry => ({...entry, authoritative_result: structuredClone(result),
      settled_by: result.outcome_unknown || result.requires_reload ? null : source}));
    if (result.outcome_unknown || result.requires_reload) throw Error(source === 'readback'
      ? unresolvedMessage('found') : result.error || '原操作结果未知或需要重新载入照片');
    const remaining = state.unresolved.filter(item => item.request_id !== request.request_id);
    const previousPhoto = context.documentId !== request.document_id;
    const message = `${previousPhoto ? '上一张照片：' : ''}${source === 'readback' ? '同引擎原记录已核实。' : ''}${!result.success
      ? result.error || '换底修改未成功' : result.no_change ? '参数未改变，未新增历史' : '换底操作已保存，可撤销'}`;
    // Release only this completed observer before publishing unlocked state.
    // A new reviewed apply must not lose its own receipt query behind a stale refresh.
    if (source === 'readback') readbackToken = null; else queryToken = null;
    release(); reset({phase: remaining.length ? 'uncertain' : result.success ? 'success' : 'failure',
      request: remaining[0] ?? null, unresolved: remaining, message: remaining.length ? `${message}。还有 ${remaining.length} 笔原操作待逐笔核对。` : message});
    if (!result.success) return;
    const settledGeneration = generation, settledLifetime = lifetime;
    try {await bounded(refresh(), 5000);} catch (error) {
      if (alive && lifetime === settledLifetime && generation === settledGeneration && state.phase === 'success' && state.request === null) {
        publish({message: `${message}。界面刷新未完成：${String(error)}`});
      }
    }
  }
  async function query(request: Request) {
    if (!alive || queryToken || readbackToken) return;
    const token = Symbol('original-receipt'), mounted = lifetime; queryToken = token;
    const valid = () => alive && lifetime === mounted && queryToken === token && state.request === request;
    publish({receiptQueryPending: true});
    try {
      const deadline = Date.now() + timeout;
      while (valid()) {
        if (Date.now() >= deadline) throw Error('等待原操作回执超时');
        const raw = await bounded(api.result(request.request_id), deadline - Date.now());
        if (!valid()) return;
        if (!object(raw) || raw.request_id !== request.request_id) throw Error('换底操作回执身份不符');
        if (raw.phase === 'pending') {await sleep(100); continue;}
        audit(request, entry => ({...entry, latest_original_receipt: structuredClone(raw)}));
        if (raw.phase !== 'done' || !object(raw.result)) throw Error('原操作回执尚未找到，不会重复提交');
        const original = applyReceipt(raw.result, request);
        audit(request, entry => ({...entry, original_receipt: entry.original_receipt ?? structuredClone(original)}));
        await settleReceipt(request, raw.result, 'original-receipt');
        return;
      }
    } catch (error) {if (valid()) publish({phase: 'uncertain', committable: false, message: `原操作结果待确认：${String(error)}`});}
    finally {if (queryToken === token) {queryToken = null; if (alive && lifetime === mounted) publish({receiptQueryPending: false});}}
  }
  async function readback() {
    const request = state.request;
    if (!alive || !request || state.phase !== 'uncertain' || readbackToken || queryToken) return;
    if (!context.readbackEnabled || !api.readback || !api.readbackStatus) {
      publish({message: '当前引擎未提供同引擎原结果核对能力；原操作仍待确认，不会重发。'}); return;
    }
    const entry = state.audit.find(item => item.original_request.request_id === request.request_id);
    if (!entry) {publish({message: '原操作身份记录缺失，不能核对或重新提交。'}); return;}
    if (entry.engine_state === 'epoch_changed' || (entry.engine_key !== undefined && context.engineKey !== entry.engine_key)) {
      publish({readbackPhase: 'epoch_changed', message: unresolvedMessage('epoch_changed')}); return;
    }
    const last = entry.readbacks.at(-1);
    const resume = !!last && last.request.readback_id === state.readbackId && state.readbackPhase === 'pending';
    const readRequest: ReadbackRequest = resume ? last.request : {...request, readback_id: id()};
    if (!/^[0-9a-f]{32}$/.test(readRequest.readback_id) || /^0+$/.test(readRequest.readback_id)) {
      publish({message: '核对操作身份无效，未发送核对请求。'}); return;
    }
    if (!resume) audit(request, item => ({...item, readbacks: [...item.readbacks, {request: structuredClone(readRequest), status: null, error: null}]}));
    const token = Symbol('common-readback'), mounted = lifetime, engine = context.engineKey;
    readbackToken = token;
    const valid = () => alive && lifetime === mounted && readbackToken === token && state.request === request && context.engineKey === engine;
    const record = (status: ReadbackStatus | null, error: string | null) => audit(request, item => ({...item,
      original_receipt: item.original_receipt ?? (status ? structuredClone(status.original_receipt) : null),
      readbacks: item.readbacks.map(value => value.request.readback_id === readRequest.readback_id
        ? {...value, status: status ? structuredClone(status) : value.status, error} : value)}));
    publish({readbackPending: true, readbackId: readRequest.readback_id, readbackPhase: 'pending', message: '正在只读核对同一引擎保存的原操作结果，不会重发修改…'});
    try {
      if (!resume) {try {await bounded(api.readback(readRequest), Math.min(timeout, 10000));} catch {/* A lost readback send is checked by its own ID, not repeated. */}}
      const deadline = Date.now() + timeout;
      while (valid()) {
        if (Date.now() >= deadline) throw Error('等待同引擎核对超时；可继续查询本次核对，不会重发修改');
        const raw = await bounded(api.readbackStatus(readRequest.readback_id), deadline - Date.now());
        if (!valid()) return;
        if (unavailableReadback(raw, readRequest.readback_id)) {
          record(null, '核对身份未登记，不能据此判断原操作是否执行');
          publish({phase: 'uncertain', readbackPhase: 'unavailable', message: '本次只读核对回执未登记。原操作仍待确认，不会重发；可明确发起新的只读核对。'}); return;
        }
        const status = readbackStatus(raw, readRequest); record(status, null); publish({readbackPhase: status.phase});
        if (status.phase === 'pending') {await sleep(100); continue;}
        if (status.phase !== 'found') {publish({phase: 'uncertain', message: unresolvedMessage(status.phase)}); return;}
        await settleReceipt(request, status.result, 'readback'); return;
      }
    } catch (error) {if (valid()) {record(null, String(error)); publish({phase: 'uncertain', committable: false, message: `同引擎核对未能确认：${String(error)}`});}}
    finally {if (readbackToken === token) {readbackToken = null; if (alive && lifetime === mounted) publish({readbackPending: false});}}
  }
  async function confirm() {
    const s = session;
    if (!alive || !s || confirmationToken || !clientGeneration || state.inventoryPhase !== 'ready' || state.phase !== 'ready' ||
        !state.presented || !state.committable || !state.previewId || !state.recipe || !current(s) || context.canStart === false) return;
    const token = Symbol('common-confirmation'), mounted = lifetime, generated = generation;
    const preview = state.previewId, recipe = state.recipe, admissionGeneration = clientGeneration;
    confirmationToken = token;
    const valid = () => alive && lifetime === mounted && generation === generated && confirmationToken === token && session === s;
    publish({phase: 'confirming', message: '正在确认已有编辑已完成；尚未发送换底操作，可取消…'});
    try {
      await bounded(options.beforeSubmit?.() ?? Promise.resolve(), timeout);
      if (!valid()) return;
      if (!current(s) || context.canStart === false || state.previewId !== preview || state.recipe !== recipe ||
          !state.presented || !state.committable || state.inventoryPhase !== 'ready' || clientGeneration !== admissionGeneration) throw Error('审核或编辑状态已变化，尚未发送换底操作，请重新预览');
    } catch (error) {if (valid()) failed(`未发送换底操作：${String(error)}`); return;}
    finally {if (confirmationToken === token) confirmationToken = null;}
    if (!alive || lifetime !== mounted || generation !== generated || session !== s) return;
    const request: Request = {request_id: `common-bg-${id()}`, preview_id: preview, session_id: s.id, document_id: s.document};
    publish({phase: 'sending', request, committable: false, message: '正在保存已审核的换底效果…',
      unresolved: [...state.unresolved, request], audit: [...state.audit, {original_request: structuredClone(request), original_receipt: null, latest_original_receipt: null,
        engine_key: context.engineKey, readbacks: [], authoritative_result: null, settled_by: null}]});
    // No unowned asynchronous barrier is permitted between this registration and native admission.
    try {await bounded(api.submit(request, admissionGeneration), timeout);} catch {/* Never resubmit after any uncertain transport outcome. */}
    if (alive && lifetime === mounted && state.request === request) await query(request);
  }
  return {
    snapshot: () => state,
    subscribe: (f: (s: State) => void) => {listeners.add(f); return () => {listeners.delete(f);};},
    start, render, presented, confirm, cancel, failed, busy, readback, initialize,
    dirty() {if (!busy()) publish({committable: false, message: '参数已改变，请更新并重新检查前后对照'});},
    context(next: Context) {
      const engineChanged = context.engineKey !== next.engineKey;
      context = next;
      if (engineChanged && readbackToken) {
        readbackToken = null;
        publish({readbackPending: false, readbackPhase: 'epoch_changed', message: unresolvedMessage('epoch_changed')});
      }
      if (session && !current(session)) {
        if (busy()) publish({open: false, image: null, presented: false, message: engineChanged ? unresolvedMessage('epoch_changed') : '照片或编辑状态已变化，仍保留原操作回执；不会重发'});
        else cancel(next.reason || '照片或编辑版本变化，未确定的换底效果已取消');
      }
    },
    check: async () => {if (state.request) await query(state.request);},
    externalEdit() {if (session && !busy()) cancel('其他编辑开始，未确定的换底效果已取消');},
    activate() {alive = true;},
    stop() {
      // Unmount never sends cancel for a submitted operation and never loses its original receipt.
      alive = false; lifetime++; generation++; acknowledging = null; confirmationToken = null; queryToken = null; readbackToken = null; inventoryToken = null;
      if (busy()) state = {...state, open: false, phase: 'uncertain', committable: false, receiptQueryPending: false, readbackPending: false};
      else {release(); state = {...initial(), audit: state.audit, inventoryPhase: state.inventoryPhase, inventoryMessage: state.inventoryMessage};}
    },
  };
}
