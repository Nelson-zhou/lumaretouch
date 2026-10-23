import {mutationValid, object, readRecipe, readReview, type Mutation, type RecipeIdentity, type Request, type Review} from './model.ts';

export interface Context {enabled: boolean; canStart?: boolean; documentId: string; contextKey: string; reason?: string}
export interface Transport {
  preview: (action: 'preview' | 'presented' | 'cancel', preview: string, session: string, document: string, mutation?: Mutation) => Promise<unknown>;
  status: (preview: string) => Promise<unknown>;
  submit: (request: Request) => Promise<unknown>;
  result: (request: string) => Promise<unknown>;
}
export interface State {
  open: boolean; phase: 'idle' | 'preparing' | 'loading' | 'ready' | 'sending' | 'uncertain' | 'failure' | 'success';
  image: Review | null; recipe: RecipeIdentity | null; mutation: Mutation | null;
  previewId: string | null; presented: boolean; committable: boolean; message: string; request: Request | null;
}
interface Options {prepare?: () => Promise<void>; id?: () => string; timeoutMs?: number; sleep?: (ms: number) => Promise<void>}
const initial = (): State => ({open: false, phase: 'idle', image: null, recipe: null, mutation: null,
  previewId: null, presented: false, committable: false, message: '', request: null});
function bounded<T>(promise: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('等待超时')), Math.max(1, ms));})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}

export function createWorkflow(api: Transport, refresh: () => Promise<void>, options: Options = {}) {
  let state = initial(), context: Context = {enabled: false, documentId: '', contextKey: ''};
  let session: {id: string; document: string; context: string} | null = null;
  let alive = true, generation = 0, querying = false, acknowledging: string | null = null;
  const listeners = new Set<(s: State) => void>();
  const id = options.id ?? (() => crypto.randomUUID().replaceAll('-', ''));
  const timeout = options.timeoutMs ?? 120000;
  const sleep = options.sleep ?? ((ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms)));
  const publish = (patch: Partial<State>) => {state = {...state, ...patch}; if (alive) listeners.forEach(f => f(state));};
  const busy = () => state.phase === 'sending' || state.phase === 'uncertain';
  const current = (s: NonNullable<typeof session>) => context.enabled && context.documentId === s.document && context.contextKey === s.context;
  function release() {
    const old = session, preview = state.previewId;
    session = null; generation++; acknowledging = null;
    if (old && preview) void api.preview('cancel', preview, old.id, old.document).catch(() => {});
  }
  function cancel(message = '未确定的换底效果已取消，照片未修改') {
    if (busy()) {publish({open: false, message: '操作已经发送，关闭窗口不撤销操作；可查询原操作结果，不会重复提交'}); return;}
    release(); publish({...initial(), message});
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
    publish({...initial(), phase: 'preparing', mutation: structuredClone(mutation), message: '正在等待已有编辑完成…'});
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
  async function query(request: Request) {
    if (!alive || querying) return;
    querying = true;
    try {
      const deadline = Date.now() + timeout;
      while (alive && state.request === request) {
        if (Date.now() >= deadline) throw Error('等待原操作回执超时');
        const raw = await bounded(api.result(request.request_id), deadline - Date.now());
        if (!alive || state.request !== request) return;
        if (!object(raw) || raw.request_id !== request.request_id) throw Error('换底操作回执身份不符');
        if (raw.phase === 'pending') {await sleep(100); continue;}
        if (raw.phase !== 'done' || !object(raw.result)) throw Error('原操作回执尚未找到，不会重复提交');
        const r = raw.result;
        if (r.protocol !== 1 || r.action !== 'apply' || r.request_id !== request.request_id ||
            r.preview_id !== request.preview_id || r.session_id !== request.session_id || r.document_id !== request.document_id ||
            typeof r.success !== 'boolean' || typeof r.outcome_unknown !== 'boolean' || typeof r.requires_reload !== 'boolean') throw Error('换底修改回执不完整');
        if (r.outcome_unknown || r.requires_reload) throw Error(typeof r.error === 'string' ? r.error : '结果未知或需要重新载入照片');
        if (!r.success) {
          release(); publish({phase: 'failure', request: null, image: null, recipe: null, previewId: null,
            presented: false, committable: false, message: typeof r.error === 'string' ? r.error : '换底修改未成功'});
          return;
        }
        if (typeof r.no_change !== 'boolean' || !object(r.history) ||
            ![r.history.undo_steps, r.history.redo_steps].every(v => Number.isSafeInteger(v) && Number(v) >= 0)) throw Error('换底修改缺少历史证据');
        const previousPhoto = context.documentId !== request.document_id;
        const message = `${previousPhoto ? '上一张照片：' : ''}${r.no_change ? '参数未改变，未新增历史' : '换底操作已保存，可撤销'}`;
        release(); publish({...initial(), phase: 'success', message});
        try {await bounded(refresh(), 5000);} catch (error) {
          if (alive && state.phase === 'success' && state.request === null) publish({message: `${message}。界面刷新未完成：${String(error)}`});
        }
        return;
      }
    } catch (error) {if (alive && state.request === request) publish({phase: 'uncertain', committable: false, message: `原操作结果待确认：${String(error)}`});}
    finally {querying = false;}
  }
  async function confirm() {
    const s = session;
    if (!alive || !s || state.phase !== 'ready' || !state.presented || !state.committable || !state.previewId || !current(s) || context.canStart === false) return;
    const request: Request = {request_id: `common-bg-${id()}`, preview_id: state.previewId, session_id: s.id, document_id: s.document};
    publish({phase: 'sending', request, committable: false, message: '正在保存已审核的换底效果…'});
    try {await bounded(api.submit(request), timeout);} catch {/* Never resubmit after any uncertain transport outcome. */}
    if (alive && state.request === request) await query(request);
  }
  return {
    snapshot: () => state,
    subscribe: (f: (s: State) => void) => {listeners.add(f); return () => {listeners.delete(f);};},
    start, render, presented, confirm, cancel, failed, busy,
    dirty() {if (!busy()) publish({committable: false, message: '参数已改变，请更新并重新检查前后对照'});},
    context(next: Context) {
      context = next;
      if (session && !current(session)) {
        if (busy()) publish({open: false, image: null, presented: false, message: '照片或编辑状态已变化，仍保留原操作回执；不会重发'});
        else cancel(next.reason || '照片或编辑版本变化，未确定的换底效果已取消');
      }
    },
    check: async () => {if (state.request) await query(state.request);},
    externalEdit() {if (session && !busy()) cancel('其他编辑开始，未确定的换底效果已取消');},
    activate() {alive = true;},
    stop() {
      // Unmount never sends cancel for a submitted operation and never loses its original receipt.
      alive = false; generation++; acknowledging = null;
      if (busy()) state = {...state, open: false, phase: 'uncertain', committable: false};
      else {release(); state = initial();}
    },
  };
}
