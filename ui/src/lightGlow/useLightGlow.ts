// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore} from 'react';
import {LightGlowController, glowBounded} from './controller';
import {freezeGlow, glowKey, unavailableGlowCapability, validGlowCapability, validGlowCurrentReply,
  type GlowCapability, type GlowCurrentReply, type GlowReceipt, type GlowWriteCommand, type LightGlowPort} from './model';

/** These are existing App state identities, never reconstructed from a filename. */
export interface LightGlowWorkspaceContext {
  sourceUid: string; loadId: string; engineKey: string; hostRevision: number;
  active: boolean; available: boolean; externalBusy: boolean; queueBusy: boolean;
}
export interface GlowAcquisition {request_id: string; phase: 'working' | 'pending' | 'unknown' | 'cancelling'; cancel_requested: boolean}
interface CurrentTask {request_id: string; scope: string; cancel_requested: boolean; cancel_sent: boolean}
interface OwnerState {
  capability: GlowCapability; acquisition: GlowAcquisition | null; starting: boolean; current_scope: string | null;
  refreshing: boolean; last_result: GlowReceipt | null; message: string;
}
export type GlowRefresh = (receipt: GlowReceipt, command: GlowWriteCommand) => Promise<void>;
const scope = (context: LightGlowWorkspaceContext): string => glowKey([context.engineKey, context.sourceUid, context.loadId, context.hostRevision]);
const usable = (context: LightGlowWorkspaceContext): boolean => !!context.sourceUid && !!context.loadId && !!context.engineKey
  && Number.isSafeInteger(context.hostRevision) && context.hostRevision >= 0 && context.available && !context.externalBusy;
const reason = (error: unknown): string => error instanceof Error ? error.message : String(error);

export class LightGlowOwner {
  readonly controller: LightGlowController;
  private context: LightGlowWorkspaceContext;
  private state: OwnerState;
  private task: CurrentTask | null = null;
  private generation = 0;
  private checking: Promise<void> | null = null;
  private readonly listeners = new Set<() => void>();
  constructor(readonly port: LightGlowPort, context: LightGlowWorkspaceContext, private readonly changed: GlowRefresh) {
    this.context = {...context};
    this.state = freezeGlow({capability: unavailableGlowCapability('尚未取得原生发光能力。'), acquisition: null, starting: false,
      current_scope: null, refreshing: false, last_result: null, message: '请明确获取当前完整修图结果；打开面板不会自动捕获或计算。'});
    this.controller = new LightGlowController(port, {onTerminal: async (receipt, command) => {
      this.publish({refreshing: true, ...(receipt.phase === 'done' && receipt.outcome === 'applied' ? {last_result: receipt} : {}),
        message: '原请求已有确定回执，正在读取真实文档列表与编辑器状态。'});
      try {
        await this.changed(receipt, command);
        this.publish({current_scope: receipt.phase === 'done' && receipt.outcome === 'rejected' ? this.state.current_scope : null,
          message: receipt.phase === 'done' && receipt.outcome === 'applied'
            ? `独立新图 ${receipt.result_document_id} 已创建并刷新编辑器状态；原片不覆盖，图片文件需另行导出。` : receipt.message});
      } catch (error) {
        this.publish({message: `已收到确定回执，但编辑器状态刷新失败：${reason(error)}。不要重复提交。`}); throw error;
      } finally {this.publish({refreshing: false});}
    }});
    port.subscribe(() => this.publish({}));
  }
  snapshot = (): OwnerState => this.state;
  subscribe = (listener: () => void): (() => void) => {this.listeners.add(listener); return () => {this.listeners.delete(listener);};};
  private publish(patch: Partial<OwnerState>): void {this.state = freezeGlow({...this.state, ...patch}); this.listeners.forEach(listener => listener());}
  private taskState(phase: GlowAcquisition['phase'], message: string): void {
    this.publish({acquisition: this.task ? {request_id: this.task.request_id, phase, cancel_requested: this.task.cancel_requested} : null, message});
  }
  updateContext(next: LightGlowWorkspaceContext): void {
    const changed = scope(next) !== scope(this.context), lost = usable(this.context) && !usable(next);
    this.context = {...next};
    if (!changed && !lost) return;
    ++this.generation;
    this.publish({current_scope: null, message: '照片、引擎、加载会话或修订已变化，旧来源已作废。'});
    this.controller.markStale();
    if (this.task) {this.task.cancel_requested = true; this.taskState('cancelling', '旧来源获取已请求取消，仍需查询原任务终态。'); void this.cancelTask(this.task);}
    void this.port.cancelReads().catch(error => this.publish({message: `原读取停止尚未确认：${reason(error)}。未宣称已取消。`}));
  }
  adapterChanged(): void {
    this.controller.markStale('原生接口实例被替换，保留旧请求归属；不能把原请求交给新接口重发。');
    this.controller.setCapability(unavailableGlowCapability('请保持原生接口实例的 App 生命周期。'));
  }
  canAcquire = (): boolean => usable(this.context) && this.context.active && !this.context.queueBusy && !this.state.starting
    && !this.task && !this.state.refreshing && this.controller.canDetach();
  acquireCurrent = async (): Promise<void> => {
    if (!this.canAcquire()) return;
    const expected = scope(this.context), generation = ++this.generation;
    this.publish({starting: true, message: '正在核验发光模块；不会自动下载或进行 AI 推理。'});
    try {
      const value = await glowBounded(this.port.refreshCapability(), 10000);
      const capability = validGlowCapability(value) ? value : unavailableGlowCapability('发光模块能力回执无效。');
      this.publish({capability}); this.controller.setCapability(capability);
      if (capability.status !== 'available') {this.publish({message: capability.reason ?? '发光模块不可用。'}); return;}
      if (generation !== this.generation || expected !== scope(this.context) || !usable(this.context) || !this.context.active || this.context.queueBusy) return;
      this.controller.markStale('正在取得明确请求的新来源，旧对比不能继续使用。');
      this.publish({current_scope: null});
      const task: CurrentTask = {request_id: crypto.randomUUID(), scope: expected, cancel_requested: false, cancel_sent: false};
      this.task = task;
      this.taskState('working', '正在取得完整当前修图结果与真实来源证据；保留原编辑状态和历史。');
      try {await this.acceptCurrent(await glowBounded(this.port.acquireCurrent(task.request_id), 145000), task);}
      catch (error) {if (this.task === task) this.taskState(task.cancel_requested ? 'cancelling' : 'unknown', `来源获取未确认：${reason(error)}。只能查询原请求。`);}
    } catch (error) {this.publish({message: reason(error)});}
    finally {this.publish({starting: false});}
  };
  private async acceptCurrent(value: unknown, task: CurrentTask): Promise<void> {
    if (this.task !== task) return;
    if (!validGlowCurrentReply(value, task.request_id)) {this.taskState(task.cancel_requested ? 'cancelling' : 'unknown', '来源回执协议或请求身份不匹配，保留原请求等待核对。'); return;}
    const reply: GlowCurrentReply = value;
    if (reply.status === 'pending' || reply.status === 'unknown') {
      this.taskState(task.cancel_requested ? 'cancelling' : reply.status, reply.message);
      if (task.cancel_requested) await this.cancelTask(task);
      return;
    }
    this.task = null; this.publish({acquisition: null});
    if (reply.status !== 'ready') {this.publish({message: reply.message}); return;}
    if (task.cancel_requested || task.scope !== scope(this.context) || !usable(this.context)) {
      this.publish({message: '来源获取已结束，但结果已失效，未采用晚到图像，也不会自动重新获取。'}); return;
    }
    const context = reply.context;
    if (context.owner.document_id !== this.context.sourceUid || context.source_evidence.load_id !== this.context.loadId) {
      this.publish({message: '真实来源归属或加载会话与当前照片不匹配，未用于发光。'}); return;
    }
    // Canonical document revision comes only from native owner/evidence, never hostRevision.
    this.publish({current_scope: task.scope, capability: context.capability, message: context.message});
    await this.controller.setContext(context);
  }
  private async cancelTask(task: CurrentTask): Promise<void> {
    if (this.task !== task || task.cancel_sent) return;
    task.cancel_sent = true;
    try {await this.port.cancelCurrent(task.request_id); await this.acceptCurrent(await this.port.currentStatus(task.request_id), task);}
    catch (error) {if (this.task === task) this.taskState('cancelling', `原读取取消未确认：${reason(error)}。不会重发取消或捕获。`);}
  }
  cancelCurrent = async (): Promise<void> => {
    if (!this.task) {if (this.state.starting) {++this.generation; this.publish({message: '尚未发送的来源获取已作废。'});} return;}
    const task = this.task; task.cancel_requested = true;
    this.taskState('cancelling', '已请求取消原来源获取；接受请求不代表已停止，仍等待终态。');
    await this.cancelTask(task);
  };
  private observe(explicit: boolean): Promise<void> {
    if (this.checking) return this.checking;
    const operation = (async () => {
      const task = this.task;
      if (task) try {await this.acceptCurrent(await glowBounded(this.port.currentStatus(task.request_id), 10000), task);}
      catch (error) {if (this.task === task) this.taskState(task.cancel_requested ? 'cancelling' : 'unknown', reason(error));}
      try {await glowBounded(this.port.checkReads(), 10000);} catch (error) {this.publish({message: `原读取仍待确认：${reason(error)}`});}
      if (this.controller.unresolved()) await this.controller.check(explicit);
    })();
    this.checking = operation;
    void operation.then(() => {if (this.checking === operation) this.checking = null;}, () => {if (this.checking === operation) this.checking = null;});
    return operation;
  }
  check = (): Promise<void> => this.observe(true);
  poll = (): Promise<void> => this.observe(false);
}

/** Call unconditionally above the transient panel, using one stable real port instance. */
export function useLightGlow(context: LightGlowWorkspaceContext, port: LightGlowPort, onChanged: GlowRefresh) {
  const changed = useRef(onChanged); changed.current = onChanged;
  const owner = useMemo(() => new LightGlowOwner(port, context, (receipt, command) => changed.current(receipt, command)), []);
  const value = useSyncExternalStore(owner.subscribe, owner.snapshot, owner.snapshot);
  const state = useSyncExternalStore(owner.controller.subscribe, owner.controller.snapshot, owner.controller.snapshot);
  const key = scope(context);
  useLayoutEffect(() => {owner.updateContext(context);}, [owner, key, context.active, context.available, context.externalBusy, context.queueBusy]);
  useLayoutEffect(() => {if (port !== owner.port) owner.adapterChanged();}, [owner, port]);
  const pending = !!value.acquisition || owner.port.pendingReads() || owner.controller.unresolved();
  useEffect(() => {
    if (!pending) return;
    // Read-only observation survives hiding. It never starts a fresh render or replays a write.
    const timer = setInterval(() => {void owner.poll().catch(() => { /* Owner keeps uncertainty and exact request. */ });}, 1200);
    return () => clearInterval(timer);
  }, [owner, pending]);
  return {controller: owner.controller, state, capability: value.capability, acquisition: value.acquisition,
    canAcquire: owner.canAcquire(), busy: value.starting || pending || value.refreshing || ['verifying', 'previewing', 'cancelling'].includes(state.phase),
    message: value.message, lastResult: value.last_result, refreshing: value.refreshing,
    acquireCurrent: owner.acquireCurrent, cancelCurrent: owner.cancelCurrent, check: owner.check};
}
export type LightGlowWorkspaceOwner = ReturnType<typeof useLightGlow>;
