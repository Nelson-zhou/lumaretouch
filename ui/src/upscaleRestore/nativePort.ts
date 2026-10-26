// SPDX-License-Identifier: GPL-3.0-or-later
/** Real dedicated transport. AUTHORED / UNRUN. Never renders or fabricates successful receipts. */
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {UPSCALE_OPERATION, UPSCALE_PROTOCOL, freezeUpscale, upscaleExact, upscaleId, upscaleKey, upscaleObject, upscaleRequestFits,
  sameUpscaleOwner, validUpscaleCapability, validUpscaleCurrentReply, validUpscaleOwner, validUpscaleRecipe, validUpscaleReceipt,
  validUpscaleReview, validUpscaleWriteCommand,
  type UpscaleCapability, type UpscaleContext, type UpscaleCurrentReply, type UpscalePng, type UpscalePreviewCommand,
  type UpscaleReceipt, type UpscaleReview, type UpscaleWriteCommand, type UpscaleRestorePort} from './model';

const EVENT = 'upscale_restore_result' as const;
// Worker hard wall is 610 seconds; keep this original read alive through completion.
const READ_WAIT_MS = 630000;
const MAX_READS = 256;
const MAX_WRITES = 128;
type SourceProof = Pick<UpscaleContext, 'session_id' | 'owner' | 'source_evidence'> & {
  before: Pick<UpscalePng, 'sha256' | 'width' | 'height'>;
};
type OuterRequest = {cmd: 'upscale_restore'; action: 'current' | 'preview' | 'submit' | 'receipt'; request_id: string;
  command?: UpscalePreviewCommand | UpscaleWriteCommand};
interface ReadTask {
  request: OuterRequest; engineKey: string; generation: number; source: SourceProof | null;
  sent: boolean; admitted: boolean; terminal: boolean; cancelled: boolean; cancelSent: boolean;
  starting: Promise<Record<string, unknown>> | null; checking: Promise<Record<string, unknown>> | null;
  localTerminal: Record<string, unknown> | null;
}
interface WriteTask {
  command: UpscaleWriteCommand; engineKey: string; sent: boolean; queryId: string | null; reconcileRequested: boolean;
  starting: Promise<UpscaleReceipt> | null; checking: Promise<UpscaleReceipt> | null; last: UpscaleReceipt | null;
}
export interface UpscaleRestoreNativeOptions {
  /** Live App engine identity; never a source filename or a hard-coded constant. */
  engineKey: () => string;
  beforeRead?: (command: UpscalePreviewCommand) => Promise<void> | void;
  beforeWrite?: (command: UpscaleWriteCommand) => Promise<void> | void;
}
export interface UpscaleRestoreNativePort extends UpscaleRestorePort {
  refreshCapability(): Promise<UpscaleCapability>;
  acquireCurrent(requestId: string): Promise<UpscaleCurrentReply>;
  currentStatus(requestId: string): Promise<UpscaleCurrentReply>;
  preview(command: UpscalePreviewCommand): Promise<UpscaleReview>;
  submit(command: UpscaleWriteCommand): Promise<UpscaleReceipt>;
  receipt(command: UpscaleWriteCommand): Promise<UpscaleReceipt>;
  requestReconciliation(command: UpscaleWriteCommand): void;
}
const message = (value: unknown): value is string => typeof value === 'string' && value.length <= 4096 && !value.includes('\0');
const reason = (error: unknown): string => (error instanceof Error ? error.message : String(error)).slice(0, 3000).replaceAll('\0', '');
const pause = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));
function bounded<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(Error('原生AI 超清接口未确认；只查询原请求，不重发。')), 10000);
  })]).finally(() => {if (timer !== undefined) clearTimeout(timer);});
}
function envelope(value: unknown, id: string): Record<string, unknown> {
  if (!upscaleObject(value) || value.event !== EVENT || value.request_id !== id) throw Error('AI 超清原生回执外层身份不匹配。');
  return value;
}
function proof(context: UpscaleContext): SourceProof {
  return freezeUpscale({session_id: context.session_id, owner: context.owner, source_evidence: context.source_evidence,
    before: {sha256: context.before.sha256, width: context.before.width, height: context.before.height}});
}
function localReceipt(command: UpscaleWriteCommand, phase: 'pending' | 'unknown' | 'rejected', text: string): UpscaleReceipt {
  const identity = {version: UPSCALE_PROTOCOL, operation_id: UPSCALE_OPERATION, request_id: command.request_id,
    session_id: command.session_id, action: command.action, owner: command.owner, token: command.token,
    message: text.slice(0, 4096).replaceAll('\0', '')};
  const receipt: UpscaleReceipt = phase === 'rejected'
    ? {...identity, phase: 'done', outcome_unknown: false, outcome: 'rejected'}
    : {...identity, phase, outcome_unknown: true};
  return freezeUpscale(receipt);
}

/** Keep this instance for the App lifetime, not the visible panel lifetime.
 * Late results and exact write identities remain queryable when the panel hides.
 * The engine alone creates canonical new documents; no original is overwritten. */
export function createUpscaleRestoreNativePort(options: UpscaleRestoreNativeOptions): UpscaleRestoreNativePort {
  const reads = new Map<string, ReadTask>(), writes = new Map<string, WriteTask>(), listeners = new Set<() => void>();
  let generation = 0;
  let source: {proof: SourceProof; engineKey: string; generation: number} | null = null;
  const publish = (): void => {for (const listener of listeners) {try {listener();} catch { /* UI callbacks cannot undo transport retention. */ }}};
  const nativeStatus = async (id: string): Promise<Record<string, unknown>> => envelope(await bounded(invoke<unknown>('upscale_restore_status', {requestId: id})), id);
  function localRead(task: ReadTask, status: 'rejected' | 'cancelled', why: string): Record<string, unknown> {
    // This path is used only before invoke; no host outcome is inferred.
    const value = {event: EVENT, request_id: task.request.request_id, status, message: why.slice(0, 4096).replaceAll('\0', '')};
    task.localTerminal = freezeUpscale(value); task.terminal = true; publish(); return value;
  }
  function acceptRead(value: unknown, task: ReadTask): Record<string, unknown> {
    const packet = envelope(value, task.request.request_id);
    if (task.request.action === 'current') {
      if (!validUpscaleCurrentReply(packet, task.request.request_id)) throw Error('AI 超清当前完整来源或版本 3 证据无效。');
      if (packet.status === 'ready' && packet.context.capability.status !== 'available') throw Error('来源回执没有可用的真实AI 超清能力。');
    } else if (packet.status === 'ready') {
      if (!upscaleExact(packet, ['event', 'request_id', 'status', 'review']) || !task.source
        || !validUpscaleReview(packet.review, task.request.command as UpscalePreviewCommand, task.source)
        || packet.review.before.width !== task.source.before.width || packet.review.before.height !== task.source.before.height)
        throw Error('真实三图、版本 3 来源证据或原AI 超清预览身份不匹配。');
    } else if (!upscaleExact(packet, ['event', 'request_id', 'status', 'message'])
      || !['pending', 'unknown', 'rejected', 'cancelled'].includes(String(packet.status)) || !message(packet.message)) {
      throw Error('AI 超清读取回执字段无效。');
    }
    const terminal = !['pending', 'unknown'].includes(String(packet.status));
    if (task.terminal && !terminal) throw Error('已终结的原读取不能退回未知或再次运行。');
    if (packet.status !== 'unknown') task.admitted = true;
    if (task.request.action === 'current' && packet.status === 'ready' && !task.cancelled
      && task.engineKey === options.engineKey() && task.generation === generation) {
      source = {proof: proof(packet.context as UpscaleContext), engineKey: task.engineKey, generation: task.generation};
    }
    if (task.terminal !== terminal) {task.terminal = terminal; publish();}
    return packet;
  }
  async function statusRead(task: ReadTask): Promise<Record<string, unknown>> {
    if (task.localTerminal) return structuredClone(task.localTerminal);
    if (!task.sent && task.starting) return task.starting;
    if (task.checking) return task.checking;
    const operation = nativeStatus(task.request.request_id).then(value => acceptRead(value, task));
    task.checking = operation;
    try {return await operation;} finally {if (task.checking === operation) task.checking = null;}
  }
  async function sendRead(request: OuterRequest): Promise<Record<string, unknown>> {
    if (!upscaleId(request.request_id) || !upscaleRequestFits(request)) throw Error('AI 超清读取身份或字节上限无效。');
    if (writes.has(request.request_id)) throw Error('读取身份已属于原写入，不能重新使用。');
    const prior = reads.get(request.request_id);
    if (prior) {
      if (upscaleKey(prior.request) !== upscaleKey(request)) throw Error('同一AI 超清读取不能更换内容。');
      return prior.starting ?? statusRead(prior);
    }
    if (reads.size >= MAX_READS) throw Error('AI 超清读取身份已达上限；旧请求不会删除或重发以绕过保护。');
    const engineKey = options.engineKey();
    if (!engineKey) throw Error('没有有效引擎身份，未发送来源读取。');
    const retainedSource = source && source.engineKey === engineKey && source.generation === generation ? source.proof : null;
    const task: ReadTask = {request: freezeUpscale(request), engineKey, generation: request.action === 'current' ? ++generation : generation,
      source: retainedSource, sent: false, admitted: false, terminal: false, cancelled: false, cancelSent: false,
      starting: null, checking: null, localTerminal: null};
    if (request.action === 'current') source = null;
    reads.set(request.request_id, task); publish(); // Reserve identity BEFORE any await/preflight.
    const operation = (async (): Promise<Record<string, unknown>> => {
      try {
        if (request.action === 'preview') {
          const command = task.request.command as UpscalePreviewCommand;
          if (!task.source || task.source.session_id !== command.session_id || !sameUpscaleOwner(task.source.owner, command.owner))
            throw Error('缺少本接口保留且完全匹配的当前来源证据。');
          await options.beforeRead?.(command);
        }
        if (task.cancelled) return localRead(task, 'cancelled', '原读取在发送前已取消，没有进入引擎。');
        if (task.engineKey !== options.engineKey() || task.generation !== generation) throw Error('引擎或来源在提交前变化，未发送旧读取。');
      } catch (error) {return localRead(task, 'rejected', `本地读取前检查拒绝，未发送：${reason(error)}`);}
      task.sent = true;
      let packet: Record<string, unknown>;
      try {
        const value = await bounded(invoke<unknown>('upscale_restore_request', {request: task.request}));
        task.admitted = true; packet = acceptRead(value, task);
      } catch {packet = await statusRead(task);}
      if (task.cancelled && !task.terminal) await cancelRead(task);
      return packet;
    })();
    task.starting = operation;
    try {return await operation;} finally {if (task.starting === operation) task.starting = null;}
  }
  async function cancelRead(task: ReadTask): Promise<void> {
    task.cancelled = true; publish();
    if (!task.sent || task.terminal || task.cancelSent || task.engineKey !== options.engineKey()) return;
    if (!task.admitted) await statusRead(task);
    if (!task.admitted || task.terminal || task.cancelSent) return;
    task.cancelSent = true; // A failed/late acknowledgement never permits a repeat.
    const ack = await bounded(invoke<unknown>('upscale_restore_cancel', {requestId: task.request.request_id}));
    if (!upscaleObject(ack) || !upscaleExact(ack, ['requested', 'request_id', 'message'])
      || ack.request_id !== task.request.request_id || typeof ack.requested !== 'boolean' || !message(ack.message))
      throw Error('停止原读取的接受回执无效，仍须查询实际终态。');
    await statusRead(task); // requested:true is not cancellation, unwind or rollback proof.
  }
  async function waitPreview(command: UpscalePreviewCommand): Promise<UpscaleReview> {
    command = freezeUpscale(command);
    if (!upscaleExact(command as unknown as Record<string, unknown>, ['version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'recipe'])
      || command.version !== UPSCALE_PROTOCOL || command.operation_id !== UPSCALE_OPERATION || command.action !== 'preview'
      || !upscaleId(command.request_id) || !upscaleId(command.session_id) || !validUpscaleOwner(command.owner)
      || !validUpscaleRecipe(command.recipe) || !upscaleRequestFits(command)) throw Error('AI 超清预览命令身份或参数无效，未发送。');
    let packet = await sendRead({cmd: 'upscale_restore', action: 'preview', request_id: command.request_id, command});
    const task = reads.get(command.request_id)!, deadline = Date.now() + READ_WAIT_MS;
    while (['pending', 'unknown'].includes(String(packet.status))) {
      if (Date.now() >= deadline) throw Error('原AI 超清预览仍未终结；继续查询原请求，不会自动重新渲染。');
      await pause(400); packet = await statusRead(task);
    }
    if (packet.status !== 'ready') throw Error(String(packet.message || '原AI 超清预览已拒绝或取消。'));
    if (task.cancelled || task.engineKey !== options.engineKey() || task.generation !== generation) throw Error('原读取已作废，晚到结果不会用于复核。');
    return freezeUpscale(packet.review as UpscaleReview);
  }
  function receiptPacket(value: unknown, outerId: string, task: WriteTask): UpscaleReceipt {
    if (task.last?.phase === 'done') return freezeUpscale(task.last);
    const packet = envelope(value, outerId);
    if (packet.status === 'ready' && upscaleExact(packet, ['event', 'request_id', 'status', 'receipt']) && validUpscaleReceipt(packet.receipt, task.command)) {
      // Unknown must not be overwritten by a less informative queued receipt.
      if (task.last?.phase === 'unknown' && packet.receipt.phase === 'pending') return freezeUpscale(task.last);
      task.last = freezeUpscale(packet.receipt);
      if (task.last.phase === 'done') {
        if (task.last.outcome === 'applied' || task.last.outcome === 'cancelled') source = null;
        publish();
      }
      return freezeUpscale(task.last);
    }
    if (packet.status === 'unknown' && upscaleExact(packet, ['event', 'request_id', 'status', 'message']) && message(packet.message)) {
      task.last = localReceipt(task.command, 'unknown', packet.message); return freezeUpscale(task.last);
    }
    throw Error('原AI 超清写入缺少完全匹配的真实回执；不能确认保存或取消。');
  }
  async function statusWrite(task: WriteTask): Promise<UpscaleReceipt> {
    if (task.last?.phase === 'done') return freezeUpscale(task.last);
    if (!task.sent && task.starting) return task.starting;
    return receiptPacket(await nativeStatus(task.command.request_id), task.command.request_id, task);
  }
  async function reconcile(task: WriteTask): Promise<UpscaleReceipt> {
    if (task.last?.phase === 'done') return freezeUpscale(task.last);
    if (!task.sent && task.starting) return task.starting;
    if (task.checking) return task.checking;
    const operation = (async (): Promise<UpscaleReceipt> => {
      let original: UpscaleReceipt;
      try {original = await statusWrite(task);} catch (error) {original = localReceipt(task.command, 'unknown', reason(error));}
      if (original.phase === 'done') return original;
      if (task.engineKey !== options.engineKey()) return localReceipt(task.command, 'unknown', '引擎已更换；保留原写入，只查原回执，不能向新引擎重发。');
      if (task.queryId) {
        const result = receiptPacket(await nativeStatus(task.queryId), task.queryId, task);
        if (result.phase === 'done' || result.phase === 'pending' || !task.reconcileRequested) return result;
        task.queryId = null;
      }
      if (!task.reconcileRequested) return original;
      task.queryId = crypto.randomUUID(); task.reconcileRequested = false;
      const queryId = task.queryId;
      const request: OuterRequest = {cmd: 'upscale_restore', action: 'receipt', request_id: queryId, command: task.command};
      // New outer READ-ONLY query, exact old inner command. Never reissue apply.
      try {return receiptPacket(await bounded(invoke<unknown>('upscale_restore_request', {request})), queryId, task);}
      catch {return receiptPacket(await nativeStatus(queryId), queryId, task);}
    })();
    task.checking = operation;
    try {return await operation;} finally {if (task.checking === operation) task.checking = null;}
  }
  return {
    protocol: UPSCALE_PROTOCOL,
    subscribe(listener) {listeners.add(listener); return () => {listeners.delete(listener);};},
    pendingReads: () => [...reads.values()].some(task => !task.terminal),
    async refreshCapability() {
      const value = await bounded(invoke<unknown>('upscale_restore_capability'));
      if (!validUpscaleCapability(value)) throw Error('原生AI 超清能力或运行条件无效，不能启用编辑。');
      return freezeUpscale(value);
    },
    async acquireCurrent(requestId) {return await sendRead({cmd: 'upscale_restore', action: 'current', request_id: requestId}) as unknown as UpscaleCurrentReply;},
    async currentStatus(requestId) {
      const task = reads.get(requestId);
      if (!task || task.request.action !== 'current') throw Error('没有保留的原完整来源获取请求。');
      return await statusRead(task) as unknown as UpscaleCurrentReply;
    },
    async cancelCurrent(requestId) {
      const task = reads.get(requestId);
      if (!task || task.request.action !== 'current') throw Error('不能取消未知的来源获取。');
      await cancelRead(task);
    },
    async cancelReads() {await Promise.all([...reads.values()].filter(task => !task.terminal).map(cancelRead));},
    async checkReads() {
      await Promise.all([...reads.values()].filter(task => !task.terminal).map(async task => {
        await statusRead(task);
        if (task.cancelled && !task.terminal) await cancelRead(task);
      }));
    },
    preview: waitPreview,
    requestReconciliation(command) {
      const task = writes.get(command.request_id);
      if (task && upscaleKey(task.command) === upscaleKey(command) && task.last?.phase !== 'done') task.reconcileRequested = true;
    },
    async submit(command) {
      command = freezeUpscale(command);
      if (!validUpscaleWriteCommand(command)) throw Error('AI 超清写入命令无效，未发送。');
      if (reads.has(command.request_id)) throw Error('写入身份已属于原读取，不能重新使用。');
      const prior = writes.get(command.request_id);
      if (prior) {
        if (upscaleKey(prior.command) !== upscaleKey(command)) throw Error('原AI 超清写入身份不能改换内容。');
        return prior.starting ?? reconcile(prior);
      }
      if (writes.size >= MAX_WRITES) return localReceipt(command, 'rejected', '原写入身份容量已满，未发送新操作；既有结果仍保留。');
      const task: WriteTask = {command, engineKey: options.engineKey(), sent: false, queryId: null, reconcileRequested: true,
        starting: null, checking: null, last: null};
      writes.set(command.request_id, task); // Reserve before preflight so repeated clicks cannot dispatch twice.
      const operation = (async (): Promise<UpscaleReceipt> => {
        try {
          if (!task.engineKey) throw Error('没有有效的原引擎身份。');
          await options.beforeWrite?.(task.command);
          if (task.engineKey !== options.engineKey()) throw Error('引擎在提交前已变化。');
          if (task.command.action === 'apply') notifyInspectionEditIntent();
        } catch (error) {
          task.last = localReceipt(task.command, 'rejected', `本地提交前检查拒绝，未发送：${reason(error)}`); return freezeUpscale(task.last);
        }
        const request: OuterRequest = {cmd: 'upscale_restore', action: 'submit', request_id: task.command.request_id, command: task.command};
        task.sent = true; // A rejection/timeout AFTER this point is never a no-send proof.
        try {return receiptPacket(await bounded(invoke<unknown>('upscale_restore_request', {request})), request.request_id, task);}
        catch {
          try {return await statusWrite(task);} catch (error) {
            task.last = localReceipt(task.command, 'unknown', `原提交结果未确认：${reason(error)}`); return freezeUpscale(task.last);
          }
        }
      })();
      task.starting = operation;
      try {return await operation;} finally {if (task.starting === operation) task.starting = null;}
    },
    async receipt(command) {
      const task = writes.get(command.request_id);
      if (!task || upscaleKey(task.command) !== upscaleKey(command)) throw Error('没有匹配的原AI 超清写入，不能重新构造或发送。');
      return reconcile(task);
    },
  };
}
