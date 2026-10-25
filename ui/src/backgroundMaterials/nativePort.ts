import { invoke as tauriInvoke } from '@tauri-apps/api/core';
import { createBackgroundMaterialPort, type RequestOptions } from './adapter';
import { MaterialError } from './model';

type NativeRequest = { method: string; [key: string]: unknown };
type NativeAction = { action: 'request' | 'status' | 'cancel' | 'release'; request_id: string; request?: NativeRequest };
type Envelope = { protocol: 1; request_id: string; action: 'request'; success: boolean;
  outcome_unknown: boolean; error?: string; error_code?: string; committed: boolean | null; result?: unknown };
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('背景素材传输回执格式无效。');
  return value as Record<string, unknown>;
}
function terminalReply(value: unknown, id: string): Envelope | null {
  const receipt = record(value);
  if (receipt.request_id !== id) throw new Error('背景素材回执身份不匹配。');
  if (receipt.phase !== 'done') return null;
  const reply = record(receipt.result) as unknown as Envelope;
  if (record(receipt.result).event !== 'background_material_result' || reply.protocol !== 1 || reply.request_id !== id || reply.action !== 'request' ||
    typeof reply.success !== 'boolean' || typeof reply.outcome_unknown !== 'boolean' ||
    (typeof reply.committed !== 'boolean' && reply.committed !== null)) throw new Error('背景素材回执协议不匹配。');
  return reply;
}
function deadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  // A transport deadline is not a rollback. The caller classifies sent writes as unknown.
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('背景素材本机通信未在时限内确认。')), ms);
    promise.then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); });
  });
}
/** Bounds native payload reservations, including separately lazy thumbnails. */
function limiter(maximum: number) {
  let active = 0;
  const queue: Array<() => void> = [];
  return <T,>(task: () => Promise<T>): Promise<T> => new Promise((resolve, reject) => {
    const start = () => {
      active++;
      void task().then(resolve, reject).finally(() => { active--; queue.shift()?.(); });
    };
    if (active < maximum) start(); else queue.push(start);
  });
}
export function createNativeBackgroundMaterialLibrary(canUse: () => boolean) {
  const schedule = limiter(4);
  // A confirmed cancel response also fences any late, not-yet-admitted invocation.
  const unresolvedWrites = new Map<string, boolean>();
  const unresolvedReads = new Set<string>();
  const releasePending = new Set<string>();
  const invoke = (request: NativeAction) => deadline(tauriInvoke<unknown>('background_material_library', { request }), 10_000);
  const release = async (id: string): Promise<void> => {
    releasePending.add(id);
    try {
      const result = record(await invoke({ action: 'release', request_id: id }));
      if (result.request_id === id && result.released === true) releasePending.delete(id);
    } catch { /* Retain terminal ownership for the next explicit refresh. */ }
  };
  const request = (body: NativeRequest, mutating: boolean, options: RequestOptions): Promise<unknown> => schedule(async () => {
    if (!canUse()) throw new MaterialError('当前引擎尚未提供本地背景素材库，请启动配套引擎。', 'unavailable');
    if (options.signal.aborted) throw new MaterialError('操作已取消，尚未发送请求。', 'cancelled');
    if (mutating && unresolvedWrites.size) throw new MaterialError('旧写入尚未核对，不能再次提交。', 'unresolved', 'unknown');
    const id = `material-${crypto.randomUUID()}`;
    let sent = false, terminalSeen = false, cancelConfirmed = false;
    let cancelPromise: Promise<void> | null = null, cancelReceipt: unknown = null;
    const consume = async (raw: unknown): Promise<unknown> => {
      const reply = terminalReply(raw, id);
      if (!reply) throw new Error('背景素材终态回执缺失。');
      terminalSeen = true;
      try {
        if (!reply.success || reply.outcome_unknown) throw new MaterialError(reply.error || '背景素材请求未完成，请核对目录。',
          reply.error_code || 'request_failed', reply.outcome_unknown || reply.committed !== false ? 'unknown' : 'not-applied');
        if (!Object.prototype.hasOwnProperty.call(reply, 'result')) throw new Error('背景素材成功回执缺少结果。');
        return reply.result;
      } finally {
        // Release failure never turns a confirmed commit into a failed mutation.
        await release(id);
      }
    };
    const cancel = (): Promise<void> => {
      if (!sent) return Promise.resolve();
      if (!cancelPromise) cancelPromise = invoke({ action: 'cancel', request_id: id }).then(raw => {
        const reply = record(raw), terminal = terminalReply(reply, id);
        if (terminal) { cancelReceipt = raw; cancelConfirmed = true; }
        else cancelConfirmed = reply.phase === 'pending' && reply.cancel_requested === true;
      }).catch(() => undefined);
      // This requests real cancellation, not rollback. Still observe the terminal.
      return cancelPromise;
    };
    options.signal.addEventListener('abort', cancel);
    const end = Date.now() + (mutating ? 15 * 60_000 : 2 * 60_000);
    try {
      let raw: unknown;
      sent = true;
      try { raw = await invoke({ action: 'request', request_id: id, request: body }); }
      catch { raw = null; } // A lost enqueue acknowledgment is reconciled by ID, never resent.
      if (options.signal.aborted) cancel();
      let pause = 120;
      while (Date.now() < end) {
        if (raw !== null) {
          const receipt = record(raw);
          if (receipt.request_id !== id) throw new Error('背景素材回执身份不匹配。');
          if (receipt.phase === 'done') return await consume(receipt);
          if (receipt.phase === 'unavailable') throw new Error('该请求回执已不可查询，请核对目录，勿重复提交。');
          if (receipt.phase !== 'pending') throw new Error('背景素材请求状态无效。');
        }
        await sleep(pause); pause = Math.min(800, pause + 80);
        try { raw = await invoke({ action: 'status', request_id: id }); }
        catch { raw = null; }
      }
      cancel();
      throw new Error('等待背景素材最终回执超时。已请求停止，写入可能已经保存；请刷新并核对目录。');
    } catch (error) {
      if (!terminalSeen) {
        // Covers unavailable status after a lost enqueue acknowledgment: native
        // records a pre-admission tombstone before a delayed request can enqueue.
        await cancel();
        if (cancelReceipt !== null) return await consume(cancelReceipt);
        if (mutating) unresolvedWrites.set(id, cancelConfirmed);
        else unresolvedReads.add(id);
      }
      if (error instanceof MaterialError) throw error;
      throw new MaterialError(error instanceof Error ? error.message : String(error), 'transport', mutating ? 'unknown' : 'not-applied');
    } finally { options.signal.removeEventListener('abort', cancel); }
  });
  const port = createBackgroundMaterialPort({
    async snapshot(options) {
      for (const id of [...releasePending]) await release(id);
      // A detached read never blocks write reconciliation, but its mailbox slot
      // remains owned until its terminal is observed and explicitly released.
      for (const id of [...unresolvedReads]) {
        try {
          const raw = await invoke({ action: 'cancel', request_id: id });
          if (terminalReply(raw, id)) { await release(id); unresolvedReads.delete(id); }
        } catch { /* Keep the ID, not the preview payload. */ }
      }
      // A timed-out write may still be queued. A fresh read cannot unlock acknowledgment
      // until every retained request is terminal, including proven pre-admission cancellation.
      for (const [id, barrierConfirmed] of [...unresolvedWrites]) {
        if (!barrierConfirmed) {
          // Retry cancellation/status only, never the original mutation. A failed
          // cancel or unavailable status cannot fence an unseen delayed admission.
          const barrier = record(await invoke({ action: 'cancel', request_id: id }));
          if (terminalReply(barrier, id)) {
            await release(id);
            unresolvedWrites.delete(id); continue;
          }
          if (barrier.phase !== 'pending' || barrier.cancel_requested !== true) {
            throw new MaterialError('旧请求的停止屏障尚未确认，不能解除写入保护，请稍后刷新。', 'unresolved');
          }
          unresolvedWrites.set(id, true);
        }
        const status = record(await invoke({ action: 'status', request_id: id }));
        if (!terminalReply(status, id)) {
          throw new MaterialError('旧写入尚无可核对的最终回执；等待后再刷新，不能重复提交。', 'pending');
        }
        await release(id);
        unresolvedWrites.delete(id);
      }
      return request({ method: 'snapshot' }, false, options);
    },
    page: (query, expected_revision, options) => request({ method: 'page', query, expected_revision }, false, options),
    command: (command, expected_revision, options) => request({ method: 'command', ...command, expected_revision }, true, options),
    select: (id, expected_revision, options) => request({ method: 'select', id, expected_revision }, false, options),
    thumbnail: (id, expected_revision, options) => request({ method: 'thumbnail', id, expected_revision }, false, options),
    async chooseImportPaths(kind, options) {
      if (!canUse() || options.signal.aborted) throw new MaterialError('文件选择已取消或引擎不可用。', 'cancelled');
      try { return await tauriInvoke<string[] | null>('background_material_choose', { kind }); }
      catch (cause) { throw new MaterialError(cause instanceof Error ? cause.message : String(cause), 'picker_failed'); }
    },
  });
  return { port };
}
