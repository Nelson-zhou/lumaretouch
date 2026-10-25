// SPDX-License-Identifier: GPL-3.0-or-later
/** Real Tauri transport only. AUTHORED / UNRUN; no fallback renderer or inferred write success. */
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {LENS_OPERATION, LENS_PROTOCOL, lensKey, lensRequestFits, object, token, validLensCapability,
  validLensContext, validLensOwner, validLensRecipe, validLensReview, validLensReceipt, validLensWriteCommand,
  type LensBlurPort, type LensCapability, type LensContext, type LensManualPlaneCommand, type LensPreviewCommand,
  type LensReceipt, type LensWriteCommand} from './model';

const EVENT = 'lens_blur_result' as const;
const READ_WAIT_MS = 130000;
const MAX_IDENTITIES = 256;
type ReadAction = 'current' | 'prepare_manual_plane' | 'preview';
type ReadCommand = LensManualPlaneCommand | LensPreviewCommand;
type OuterRequest = {cmd: 'lens_blur'; action: ReadAction | 'submit' | 'receipt'; request_id: string; command?: ReadCommand | LensWriteCommand};
export type LensCurrentReply = {event: typeof EVENT; request_id: string} & (
  | {status: 'ready'; capability: LensCapability; context: LensContext | null; message?: string}
  | {status: 'pending' | 'unknown' | 'rejected' | 'cancelled'; message: string}
);
interface ReadTask {request: OuterRequest; engineKey: string; admitted: boolean; terminal: boolean; cancelled: boolean; cancelSent: boolean; checking: Promise<Record<string, unknown>> | null}
interface WriteTask {command: LensWriteCommand; engineKey: string; queryId: string | null; reconcileRequested: boolean; last: LensReceipt | null}
export interface LensNativePort extends LensBlurPort {
  refreshCapability(): Promise<LensCapability>;
  acquireCurrent(requestId: string): Promise<LensCurrentReply>;
  currentStatus(requestId: string): Promise<LensCurrentReply>;
  cancelCurrent(requestId: string): Promise<void>;
  cancelReads(): Promise<void>;
  checkReads(): Promise<void>;
  /** Explicit user check permits another readback; background polling never consumes unbounded query IDs. */
  requestReconciliation(command: LensWriteCommand): void;
  pendingReads(): boolean;
  subscribe(listener: () => void): () => void;
}
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).sort().join('|') === [...keys].sort().join('|');
const message = (v: unknown): v is string => typeof v === 'string' && v.length <= 4096 && !v.includes('\0');
const reason = (error: unknown) => error instanceof Error ? error.message : String(error);
const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
function bounded<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('原生镜头接口未确认；只查询原请求，不重发。')), 10000);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}
function envelope(value: unknown, id: string): Record<string, unknown> {
  if (!object(value) || value.event !== EVENT || value.request_id !== id) throw Error('镜头原生回执外层身份不匹配。');
  return value;
}
function readPacket(value: unknown, task: ReadTask): Record<string, unknown> {
  const v = envelope(value, task.request.request_id), base = ['event', 'request_id', 'status'];
  if (['pending', 'unknown', 'rejected', 'cancelled'].includes(String(v.status))) {
    if (!exact(v, [...base, 'message']) || !message(v.message)) throw Error('镜头读取状态字段无效。');
    return v;
  }
  if (v.status !== 'ready') throw Error('镜头读取没有已确认的结果。');
  if (task.request.action === 'current') {
    if (!exact(v, [...base, 'capability', 'context', ...(v.message === undefined ? [] : ['message'])])
      || !validLensCapability(v.capability) || (v.message !== undefined && !message(v.message))
      || (v.context === null ? v.capability.status !== 'unavailable' : v.capability.status !== 'available' || !validLensContext(v.context))) throw Error('当前完整来源或模块能力回执无效。');
  } else if (task.request.action === 'prepare_manual_plane') {
    if (!exact(v, [...base, 'context']) || !validLensContext(v.context)) throw Error('人工编辑基准面回执无效。');
  } else if (task.request.action === 'preview') {
    if (!exact(v, [...base, 'review']) || !validLensReview(v.review, task.request.command as LensPreviewCommand)) throw Error('真实前后图与原镜头预览请求不匹配。');
  } else throw Error('不是保留的镜头只读请求。');
  return v;
}
function localReceipt(command: LensWriteCommand, phase: 'unknown' | 'rejected', text: string): LensReceipt {
  const identity = {version: LENS_PROTOCOL, request_id: command.request_id, session_id: command.session_id,
    action: command.action, owner: structuredClone(command.owner), token: command.token, message: text.slice(0, 4096).replaceAll('\0', '')};
  return phase === 'unknown' ? {...identity, phase: 'unknown', outcome_unknown: true}
    : {...identity, phase: 'done', outcome_unknown: false, outcome: 'rejected'};
}

export function createLensNativePort(options: {
  engineKey: () => string;
  beforeRead?: (command: ReadCommand) => Promise<void> | void;
  beforeWrite?: (command: LensWriteCommand) => Promise<void> | void;
}): LensNativePort {
  const reads = new Map<string, ReadTask>(), writes = new Map<string, WriteTask>(), listeners = new Set<() => void>();
  const publish = () => listeners.forEach(listener => listener());
  const nativeStatus = async (id: string) => envelope(await bounded(invoke<unknown>('lens_blur_status', {requestId: id})), id);
  function retainRead(request: OuterRequest): ReadTask {
    if (!token(request.request_id)) throw Error('镜头读取请求 ID 无效。');
    const prior = reads.get(request.request_id);
    if (prior) {if (lensKey(prior.request) !== lensKey(request)) throw Error('同一镜头请求不能更换内容。'); return prior;}
    if (reads.size >= MAX_IDENTITIES) throw Error('镜头读取身份已达上限，旧请求不会重发或删除以绕过保护。');
    const task: ReadTask = {request: structuredClone(request), engineKey: options.engineKey(), admitted: false, terminal: false, cancelled: false, cancelSent: false, checking: null};
    reads.set(request.request_id, task); publish(); return task;
  }
  function acceptRead(value: unknown, task: ReadTask): Record<string, unknown> {
    const packet = readPacket(value, task);
    if (packet.status !== 'unknown') task.admitted = true;
    const terminal = !['pending', 'unknown'].includes(String(packet.status));
    if (task.terminal !== terminal) {task.terminal = terminal; publish();}
    return packet;
  }
  async function statusRead(task: ReadTask): Promise<Record<string, unknown>> {
    if (task.checking) return task.checking;
    const result = nativeStatus(task.request.request_id).then(value => acceptRead(value, task));
    task.checking = result;
    try {return await result;} finally {if (task.checking === result) task.checking = null;}
  }
  async function sendRead(request: OuterRequest): Promise<Record<string, unknown>> {
    const prior = reads.get(request.request_id), task = retainRead(request);
    if (prior) return statusRead(task); // Never re-enter a read whose send may have happened.
    try {
      const value = await bounded(invoke<unknown>('lens_blur_request', {request: task.request}));
      task.admitted = true;
      return acceptRead(value, task);
    }
    catch {return statusRead(task);}
  }
  async function cancelRead(task: ReadTask): Promise<void> {
    task.cancelled = true;
    if (!task.admitted || task.terminal || task.cancelSent || task.engineKey !== options.engineKey()) return;
    task.cancelSent = true; publish(); // An uncertain cancellation acknowledgement is never resent.
    const value = await bounded(invoke<unknown>('lens_blur_cancel', {requestId: task.request.request_id}));
    if (!object(value) || value.request_id !== task.request.request_id || typeof value.requested !== 'boolean' || !message(value.message))
      throw Error('停止原读取的接受回执无效，仍须查询原请求实际终态。');
    await statusRead(task); // requested:true is not proof of cancellation or unwind.
  }
  async function waitRead(command: ReadCommand): Promise<Record<string, unknown>> {
    command = structuredClone(command);
    if (command.version !== LENS_PROTOCOL || !token(command.request_id) || !token(command.session_id)
      || !validLensOwner(command.owner) || !lensRequestFits(command)
      || (command.action === 'preview' && !validLensRecipe(command.recipe))) throw Error('镜头只读命令身份或参数无效，未发送。');
    await options.beforeRead?.(command);
    let packet = await sendRead({cmd: 'lens_blur', action: command.action, request_id: command.request_id, command});
    const task = reads.get(command.request_id)!, deadline = Date.now() + READ_WAIT_MS;
    while (['pending', 'unknown'].includes(String(packet.status))) {
      if (Date.now() >= deadline) throw Error('原镜头读取仍未终结；继续查询原请求，不会自动重新渲染。');
      await pause(400); packet = await statusRead(task);
    }
    if (packet.status !== 'ready') throw Error(String(packet.message || '原镜头读取已拒绝或取消。'));
    if (task.cancelled || task.engineKey !== options.engineKey()) throw Error('原镜头读取已作废，晚到结果不会用于复核。');
    return packet;
  }
  function receiptPacket(value: unknown, outerId: string, task: WriteTask): LensReceipt {
    if (task.last?.phase === 'done') return structuredClone(task.last);
    const packet = envelope(value, outerId);
    if (packet.status === 'ready' && exact(packet, ['event', 'request_id', 'status', 'receipt']) && validLensReceipt(packet.receipt, task.command)) {
      task.last = structuredClone(packet.receipt); return structuredClone(task.last);
    }
    if (packet.status === 'unknown' && exact(packet, ['event', 'request_id', 'status', 'message']) && message(packet.message))
      return localReceipt(task.command, 'unknown', packet.message);
    throw Error('原镜头写入缺少完全匹配的真实回执；不能确认保存或取消。');
  }
  async function statusWrite(task: WriteTask): Promise<LensReceipt> {
    return receiptPacket(await nativeStatus(task.command.request_id), task.command.request_id, task);
  }
  async function reconcile(task: WriteTask): Promise<LensReceipt> {
    if (task.last?.phase === 'done') return structuredClone(task.last);
    let original: LensReceipt;
    try {original = await statusWrite(task);} catch (error) {original = localReceipt(task.command, 'unknown', reason(error));}
    if (original.phase === 'done' || original.phase === 'pending') return original;
    if (task.engineKey !== options.engineKey()) return localReceipt(task.command, 'unknown', '引擎已更换，保留原写入身份；不会在新引擎重发或猜测结果。');
    // A query is a new READ-ONLY outer request, never a resubmission of the original write.
    if (task.queryId) {
      const result = receiptPacket(await nativeStatus(task.queryId), task.queryId, task);
      if (result.phase === 'done' || result.phase === 'pending') return result;
      if (!task.reconcileRequested) return result;
      task.queryId = null;
    }
    if (!task.reconcileRequested) return original;
    const queryId = crypto.randomUUID(); task.queryId = queryId; task.reconcileRequested = false;
    const request: OuterRequest = {cmd: 'lens_blur', action: 'receipt', request_id: queryId, command: structuredClone(task.command)};
    try {return receiptPacket(await bounded(invoke<unknown>('lens_blur_request', {request})), queryId, task);}
    catch {return receiptPacket(await nativeStatus(queryId), queryId, task);}
  }
  return {
    protocol: LENS_PROTOCOL,
    subscribe(listener) {listeners.add(listener); return () => {listeners.delete(listener);};},
    pendingReads: () => [...reads.values()].some(task => !task.terminal),
    async refreshCapability() {
      const value = await bounded(invoke<unknown>('lens_blur_capability'));
      if (!validLensCapability(value)) throw Error('原生镜头能力回执无效，不能启用编辑。');
      return structuredClone(value);
    },
    async acquireCurrent(requestId) {return await sendRead({cmd: 'lens_blur', action: 'current', request_id: requestId}) as unknown as LensCurrentReply;},
    async currentStatus(requestId) {
      const task = reads.get(requestId); if (!task || task.request.action !== 'current') throw Error('没有保留的原完整来源获取请求。');
      return await statusRead(task) as unknown as LensCurrentReply;
    },
    async cancelCurrent(requestId) {
      const task = reads.get(requestId); if (!task || task.request.action !== 'current') throw Error('不能取消未知的来源获取。');
      await cancelRead(task);
    },
    async cancelReads() {await Promise.all([...reads.values()].filter(task => !task.terminal).map(cancelRead));},
    async checkReads() {
      await Promise.all([...reads.values()].filter(task => !task.terminal).map(async task => {
        await statusRead(task);
        if (task.cancelled && !task.terminal) await cancelRead(task);
      }));
    },
    requestReconciliation(command) {
      const task = writes.get(command.request_id);
      if (task && lensKey(task.command) === lensKey(command) && task.last?.phase !== 'done') task.reconcileRequested = true;
    },
    async prepareManualPlane(command) {return (await waitRead(command)).context;},
    async preview(command) {return (await waitRead(command)).review;},
    async submit(command) {
      command = structuredClone(command);
      if (!validLensWriteCommand(command)) throw Error('镜头写入命令无效，未发送。');
      const prior = writes.get(command.request_id);
      if (prior) {if (lensKey(prior.command) !== lensKey(command)) throw Error('原写入请求 ID 不能改换内容。'); return reconcile(prior);}
      // This is the sole local no-send proof: a failed preflight before retaining/dispatching the native operation.
      try {await options.beforeWrite?.(command);} catch (error) {return localReceipt(command, 'rejected', `本地提交前检查拒绝，未发送：${reason(error)}`);}
      if (writes.size >= MAX_IDENTITIES) return localReceipt(command, 'rejected', '原写入身份容量已满，未发送新操作；既有结果仍保留。');
      const task: WriteTask = {command: structuredClone(command), engineKey: options.engineKey(), queryId: null, reconcileRequested: true, last: null};
      writes.set(command.request_id, task); // Must precede invoke, whose failure can be uncertain.
      if (command.action === 'apply') notifyInspectionEditIntent();
      const request: OuterRequest = {cmd: 'lens_blur', action: 'submit', request_id: command.request_id, command: task.command};
      try {return receiptPacket(await bounded(invoke<unknown>('lens_blur_request', {request})), request.request_id, task);}
      catch {return statusWrite(task);}
    },
    async receipt(command) {
      const task = writes.get(command.request_id);
      if (!task || lensKey(task.command) !== lensKey(command)) throw Error('没有匹配的原镜头写入，不能重新构造或发送。');
      return reconcile(task);
    },
  };
}

export const unavailableLensCapability = (reason: string): LensCapability => ({version: 2, operation_id: LENS_OPERATION,
  status: 'unavailable', kernels: [], renderers: [], reason: reason.slice(0, 4096).replaceAll('\0', '')});
