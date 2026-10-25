// SPDX-License-Identifier: GPL-3.0-or-later
/** App-lifetime lens owner. AUTHORED / UNRUN. Mounting never captures or infers depth. */
import {useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import {settleCurveEdit} from '../curveEditBarrier';
import {sameLensOwner, type LensCapability, type LensReceipt, type LensWriteCommand} from './model';
import {createLensNativePort, unavailableLensCapability, type LensCurrentReply, type LensNativePort} from './nativePort';
import {createLensBlurWorkflow, type LensBlurWorkflow} from './workflow';

/** Existing App/native identities only. hostRevision is a UI invalidation counter, NOT the canonical document revision. */
export interface LensWorkspaceContext {
  sourceUid: string; loadId: string; engineKey: string; hostRevision: number;
  active: boolean; available: boolean; externalBusy: boolean; queueBusy: boolean;
}
export interface LensAcquisition {request_id: string; phase: 'working' | 'pending' | 'unknown' | 'cancelling'; cancel_requested: boolean}
interface CurrentTask {request_id: string; scope: string; cancel_requested: boolean}
interface OwnerState {
  capability: LensCapability; acquisition: LensAcquisition | null; starting: boolean;
  current_scope: string | null; message: string; refreshing: boolean; last_result: LensReceipt | null;
}
type Refresh = (receipt: LensReceipt, command: LensWriteCommand) => Promise<void>;
const scope = (c: LensWorkspaceContext) => JSON.stringify([c.engineKey, c.sourceUid, c.loadId, c.hostRevision]);
const usable = (c: LensWorkspaceContext) => !!c.engineKey && !!c.sourceUid && !!c.loadId && Number.isSafeInteger(c.hostRevision)
  && c.hostRevision >= 0 && c.available && !c.externalBusy;
const reason = (error: unknown) => error instanceof Error ? error.message : String(error);

/** Owns receipts across panel visibility changes, source switches and engine changes. */
export class LensBlurOwner {
  readonly workflow: LensBlurWorkflow;
  readonly native: LensNativePort;
  private context: LensWorkspaceContext;
  private state: OwnerState;
  private listeners = new Set<() => void>();
  private task: CurrentTask | null = null;
  private generation = 0;
  private checking: Promise<void> | null = null;
  private readonly pollWrite: () => Promise<void>;
  constructor(context: LensWorkspaceContext, private readonly changed: Refresh) {
    this.context = {...context};
    this.state = {capability: unavailableLensCapability('请明确获取当前完整来源；不会自动分析或下载景深模型。'),
      acquisition: null, starting: false, current_scope: null, message: '请明确获取当前完整修图结果，再选择人工散焦。', refreshing: false, last_result: null};
    this.native = createLensNativePort({engineKey: () => this.context.engineKey,
      beforeRead: async command => {
        await settleCurveEdit(); this.requireCurrent(true);
        const current = this.workflow.snapshot().context;
        if (!current || current.session_id !== command.session_id || !sameLensOwner(current.owner, command.owner))
          throw Error('镜头读取不属于当前保留来源，未发送。');
      },
      beforeWrite: async command => {
        if (command.action === 'cancel') {
          // Stop heavy reads out of band, then let the exact serialized Cancel own the session outcome.
          try {await this.native.cancelReads();} catch (error) {this.publish({message: `原读取停止尚未确认：${reason(error)}；仍等待会话取消回执。`});}
          return;
        }
        await settleCurveEdit(); this.requireCurrent(true);
        const current = this.workflow.snapshot().context;
        if (!current || current.session_id !== command.session_id || !sameLensOwner(current.owner, command.owner))
          throw Error('照片、来源或会话已变化，未提交新副本。');
      }});
    const workflow = createLensBlurWorkflow(this.native, {timeoutMs: 145000, onTerminal: async (receipt, command) => {
      if (receipt.phase !== 'done') throw Error('不能用非终态回执刷新为成功。');
      const applied = receipt.outcome === 'applied';
      this.publish({refreshing: true, ...(applied ? {last_result: structuredClone(receipt)} : {}),
        message: applied ? `新副本 ${receipt.result_document_id} 已确认，正在刷新真实文档列表和画面。` : '原镜头请求已确认，正在刷新编辑器状态。'});
      try {
        // The callback receives actual post-copy identity, never a guessed source-row revision.
        await this.changed(structuredClone(receipt), structuredClone(command));
        this.publish({...(receipt.outcome === 'rejected' ? {} : {current_scope: null}),
          message: applied ? `新副本 ${receipt.result_document_id} 已创建并完成编辑器刷新，原片文件未覆盖；项目保存和图片导出另行操作。`
            : receipt.outcome === 'cancelled' ? '本次镜头编辑已取消，没有创建新副本。' : receipt.message});
      } catch (error) {
        this.publish({message: `原请求已有确定回执，但编辑器刷新未完成：${reason(error)}。不要重复保存，只重试刷新。`});
        throw error;
      } finally {this.publish({refreshing: false});}
    }});
    this.pollWrite = workflow.check;
    this.workflow = {...workflow, check: () => {
      const request = workflow.snapshot().request;
      if (request) this.native.requestReconciliation(request);
      return workflow.check();
    }};
    this.native.subscribe(() => this.publish({}));
  }
  snapshot = (): OwnerState => this.state;
  subscribe = (listener: () => void): (() => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private publish(patch: Partial<OwnerState>): void {this.state = {...this.state, ...patch}; this.listeners.forEach(listener => listener());}
  private taskState(phase: LensAcquisition['phase'], message: string): void {
    this.publish({acquisition: this.task ? {request_id: this.task.request_id, phase, cancel_requested: this.task.cancel_requested} : null, message});
  }
  private requireCurrent(admission = false): void {
    if (!usable(this.context) || !this.context.active || this.state.current_scope !== scope(this.context)
      || (admission && (this.context.queueBusy || this.native.pendingReads()))) throw Error('当前照片或其他编辑尚未稳定，旧镜头来源不可用；未发送新操作。');
  }
  updateContext(next: LensWorkspaceContext): void {
    const changed = scope(next) !== scope(this.context), lost = usable(this.context) && !usable(next);
    this.context = {...next};
    // queueBusy is admission-only. Our own queued capture/preview/write MUST NOT cancel itself.
    // Panel visibility is also not receipt ownership: hiding keeps status observation alive.
    if (!changed && !lost) return;
    ++this.generation;
    this.publish({current_scope: null, message: '照片、加载会话、引擎、修订或其他工具状态已变化，旧来源复核已作废；不会自动重新捕获。'});
    // A completed copy keeps its terminal receipt until explicit acquisition, including a delayed React refresh commit.
    if (['applied', 'cancelled'].includes(this.workflow.snapshot().phase)) this.workflow.releasePresentation();
    else void this.workflow.setContext(null); // An unresolved write keeps its original owner and command.
    if (!next.available) {
      const capability = unavailableLensCapability('当前引擎或镜头协议不可用；原写入回执仍保留，不会自动重试。');
      this.publish({capability}); this.workflow.setCapability(capability);
    }
    if (this.task) {this.task.cancel_requested = true; this.taskState('cancelling', '旧来源获取已作废，等待原只读任务退出；不宣称已经停止。');}
    void this.native.cancelReads().catch(error => this.publish({message: `旧读取停止请求尚未确认：${reason(error)}。继续查询原请求，不重新渲染。`}));
  }
  canAcquire(): boolean {
    const s = this.workflow.snapshot();
    return usable(this.context) && this.context.active && !this.context.queueBusy && !this.state.starting && !this.task
      && !this.native.pendingReads() && !this.workflow.unresolved() && !this.state.refreshing
      && s.terminal_refresh !== 'refreshing' && !['loading', 'previewing'].includes(s.phase);
  }
  acquireCurrent = async (): Promise<void> => {
    if (!this.canAcquire()) {this.publish({message: '请先等待或查询原任务，并保持当前照片就绪；不会重复捕获。'}); return;}
    const generation = ++this.generation, expected = scope(this.context);
    this.publish({starting: true, message: '正在核验原生镜头模块；随后仅获取一次完整当前修图来源，不进行 AI 景深分析。'});
    try {
      await settleCurveEdit();
      const capability = await this.native.refreshCapability(); this.publish({capability}); this.workflow.setCapability(capability);
      if (capability.status !== 'available') {this.publish({message: capability.reason}); return;}
      if (generation !== this.generation || expected !== scope(this.context) || !usable(this.context) || !this.context.active || this.context.queueBusy) {
        this.publish({message: '能力核验期间上下文已变化，未开始来源捕获。'}); return;
      }
      const task: CurrentTask = {request_id: crypto.randomUUID(), scope: expected, cancel_requested: false};
      this.task = task; this.publish({current_scope: null}); await this.workflow.setContext(null);
      this.taskState('working', '正在读取完整当前修图结果；不修改原片，不合成景深，不降级透明度或 HDR。');
      try {await this.acceptCurrent(await this.native.acquireCurrent(task.request_id), task);}
      catch (error) {if (this.task === task) this.taskState(task.cancel_requested ? 'cancelling' : 'unknown', `原来源获取尚未确认：${reason(error)}。只查询原请求。`);}
    } catch (error) {
      const capability = unavailableLensCapability(reason(error));
      this.publish({capability, message: reason(error)}); this.workflow.setCapability(capability);
    }
    finally {this.publish({starting: false});}
  };
  private async acceptCurrent(reply: LensCurrentReply, task: CurrentTask): Promise<void> {
    if (this.task !== task || reply.request_id !== task.request_id) return;
    if (reply.status === 'pending' || reply.status === 'unknown') {
      this.taskState(task.cancel_requested ? 'cancelling' : reply.status, reply.message);
      if (task.cancel_requested) try {await this.native.cancelCurrent(task.request_id);} catch (error) {this.taskState('cancelling', reason(error));}
      return;
    }
    this.task = null; this.publish({acquisition: null});
    if (reply.status === 'rejected' || reply.status === 'cancelled') {this.publish({message: reply.message}); return;}
    if (reply.status !== 'ready') return;
    this.publish({capability: reply.capability}); this.workflow.setCapability(reply.capability);
    if (task.cancel_requested || task.scope !== scope(this.context) || !usable(this.context)) {
      this.publish({message: '原来源获取已结束，但来源已作废，未采用晚到结果，也不会自动重新捕获。'}); return;
    }
    const current = reply.context;
    if (!current) {this.publish({message: reply.message || reply.capability.reason}); return;}
    if (current.owner.document_id !== this.context.sourceUid) {
      this.publish({message: '来源回执属于另一文档，未用于镜头编辑。'}); return;
    }
    // loadId + hostRevision are held by task.scope; canonical revision/hash come ONLY from current.owner.
    this.publish({current_scope: task.scope, message: current.message});
    await this.workflow.setContext(current);
  }
  cancelCurrent = async (): Promise<void> => {
    if (!this.task) {
      if (this.state.starting) {++this.generation; this.publish({message: '尚未发送的来源获取已取消，不会开始捕获。'});}
      return;
    }
    const task = this.task; task.cancel_requested = true;
    this.taskState('cancelling', '已请求停止原来源获取，仍须等待实际退出回执；没有修改照片。');
    try {await this.native.cancelCurrent(task.request_id); await this.acceptCurrent(await this.native.currentStatus(task.request_id), task);}
    catch (error) {if (this.task === task) this.taskState('cancelling', `原读取取消尚未确认：${reason(error)}。不会重发取消。`);}
  };
  private observe(explicit: boolean): Promise<void> {
    const request = this.workflow.snapshot().request;
    if (explicit && request) this.native.requestReconciliation(request);
    if (this.checking) return this.checking;
    const operation = (async () => {
      const task = this.task;
      if (task) try {await this.acceptCurrent(await this.native.currentStatus(task.request_id), task);}
      catch (error) {if (this.task === task) this.taskState(task.cancel_requested ? 'cancelling' : 'unknown', reason(error));}
      try {await this.native.checkReads();} catch (error) {this.publish({message: `原镜头读取状态仍待确认：${reason(error)}`});}
      if (this.workflow.unresolved()) await this.pollWrite();
    })();
    this.checking = operation;
    void operation.then(() => {if (this.checking === operation) this.checking = null;}, () => {if (this.checking === operation) this.checking = null;});
    return operation;
  }
  check = (): Promise<void> => this.observe(true);
  poll = (): Promise<void> => this.observe(false);
}

/** Call unconditionally from App, never from the transient lens panel. No auto capture, inference or model download. */
export function useLensBlur(context: LensWorkspaceContext, onChanged: Refresh) {
  const changed = useRef(onChanged); changed.current = onChanged;
  const owner = useMemo(() => new LensBlurOwner(context, (receipt, command) => changed.current(receipt, command)), []);
  const value = useSyncExternalStore(owner.subscribe, owner.snapshot, owner.snapshot);
  const state = useSyncExternalStore(owner.workflow.subscribe, owner.workflow.snapshot, owner.workflow.snapshot);
  const key = scope(context);
  useLayoutEffect(() => owner.updateContext(context), [owner, key, context.active, context.available, context.externalBusy, context.queueBusy]);
  const pending = !!value.acquisition || owner.native.pendingReads() || owner.workflow.unresolved();
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {void owner.poll().catch(() => {/* Keep the original receipt owner and visible uncertainty. */});}, 1200);
    return () => clearInterval(timer);
  }, [owner, pending]);
  return {workflow: owner.workflow, state, capability: value.capability, acquisition: value.acquisition,
    canAcquire: owner.canAcquire(), busy: value.starting || pending || value.refreshing || ['loading', 'previewing'].includes(state.phase),
    message: value.message, refreshing: value.refreshing, lastResult: value.last_result,
    acquireCurrent: owner.acquireCurrent, cancelCurrent: owner.cancelCurrent, check: owner.check};
}
export type LensBlurWorkspaceOwner = ReturnType<typeof useLensBlur>;
