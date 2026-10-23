import {validInventory, PEOPLE_TRANSFER_LIMITS, type InventorySource, type PeopleInventoryResult} from './transferInventory.ts';

export type InventoryMailbox = {request_id: string; phase: string; result?: unknown; error?: string};
export type InventoryTransport = {request: (docs: string[], requestId: string) => Promise<{requested: boolean}>;
  read: (requestId: string) => Promise<InventoryMailbox>};
export type InventoryContext = {key: string; enabled: boolean; docs: string[]; source?: InventorySource};
export type InventoryUi = {phase: 'idle' | 'loading' | 'ready' | 'uncertain' | 'error'; contextKey: string;
  requestId: string; result: PeopleInventoryResult | null; message: string};
/** A read-only inventory request is separate from the existing batch transaction owner. */
export function createInventoryWorkflow(api: InventoryTransport, publish: (value: InventoryUi) => void,
  options: {uuid?: () => string; now?: () => number; pause?: (ms: number) => Promise<void>; timeoutMs?: number} = {}) {
  const uuid = options.uuid ?? (() => crypto.randomUUID()), now = options.now ?? (() => performance.now());
  const pause = options.pause ?? (ms => new Promise<void>(resolve => setTimeout(resolve, ms)));
  let context: InventoryContext = {key: '', enabled: false, docs: []}, generation = 0, disposed = false;
  let pending: {id: string; generation: number; context: InventoryContext} | null = null;
  let state: InventoryUi = {phase: 'idle', contextKey: '', requestId: '', result: null, message: ''};
  const set = (patch: Partial<InventoryUi>) => {state = {...state, ...patch}; if (!disposed) publish(state);};
  const active = (g: number) => !disposed && g === generation;
  function cancel() {
    generation++; pending = null;
    set({phase: 'idle', contextKey: context.key, requestId: '', result: null, message: ''});
  }
  function updateContext(next: InventoryContext) {
    const changed = next.key !== context.key || next.enabled !== context.enabled;
    context = {...next, docs: [...next.docs]};
    if (changed) cancel();
  }
  function bounded<T>(promise: Promise<T>, deadline: number): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('人脸列表尚未确认返回，可继续查询同一只读请求。')), Math.max(1, deadline - now()));
      promise.then(value => {clearTimeout(timer); resolve(value);}, error => {clearTimeout(timer); reject(error);});
    });
  }
  async function poll(request: NonNullable<typeof pending>, deadline = now() + (options.timeoutMs ?? 60000)) {
    try {
      while (active(request.generation)) {
        const reply = await bounded(api.read(request.id), deadline);
        if (!active(request.generation)) return;
        if (reply.request_id !== request.id) throw Error('人脸列表回执身份不匹配，未采用任何人脸。');
        if (reply.phase === 'done') {
          const body = reply.result as {request_id?: unknown; action?: unknown; success?: unknown; error?: unknown} | undefined;
          if (!body || body.request_id !== request.id || body.action !== 'people_targets' || typeof body.success !== 'boolean')
            throw Error('人脸列表回执不完整，未采用任何人脸。');
          if (!body.success) {
            pending = null; set({phase: 'error', message: typeof body.error === 'string' ? body.error : '引擎未提供可审核的人脸列表。'}); return;
          }
          if (!request.context.source || !validInventory(body, request.id, request.context.docs, request.context.source)) {
            pending = null; set({phase: 'error', message: '人脸、源图证据或目标名单不匹配，请重新读取；没有自动选择目标。'}); return;
          }
          pending = null; set({phase: 'ready', result: body, message: ''}); return;
        }
        if (reply.phase !== 'pending') throw Error(reply.error ?? '人脸列表暂不可查，可继续查询或取消本次只读请求。');
        if (now() >= deadline) throw Error('人脸列表等待超时，尚未修改照片。请查询同一请求，或取消读取。');
        await pause(150);
      }
    } catch (error) { if (active(request.generation)) set({phase: 'uncertain', message: String(error)}); }
  }
  async function start() {
    if (disposed || pending || !context.enabled || !context.source) return;
    if (!context.docs.length || context.docs.length > PEOPLE_TRANSFER_LIMITS.targets || new Set(context.docs).size !== context.docs.length) {
      set({phase: 'error', result: null, message: '请在胶片栏选择 1–16 张不同目标照片；不会截断选择。'}); return;
    }
    const request = {id: uuid(), generation: ++generation, context}, deadline = now() + (options.timeoutMs ?? 60000);
    pending = request;
    set({phase: 'loading', contextKey: context.key, requestId: request.id, result: null, message: ''});
    try {
      const accepted = await bounded(api.request([...context.docs], request.id), deadline);
      if (!active(request.generation)) return;
      if (!accepted.requested) throw Error('人脸列表请求未确认入队，请查询或取消，不会自动重发。');
      await poll(request, deadline);
    } catch (error) {if (active(request.generation)) set({phase: 'uncertain', message: String(error)});}
  }
  async function query() {
    if (state.phase !== 'uncertain' || !pending) return;
    const request = pending; set({phase: 'loading', message: ''}); await poll(request);
  }
  return {updateContext, start, query, cancel, snapshot: () => state,
    dispose: () => {disposed = true; generation++; pending = null;}};
}
