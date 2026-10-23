// SPDX-License-Identifier: GPL-3.0-or-later
import {bindingFor, previewMatches, sameOwner, validRevision,
  type CreativeAuthority, type CreativeBinding, type CreativeCommand, type CreativePorts, type CreativePreview,
  type CreativeReceipt, type CreativeRequest} from './model.ts';

export interface CreativeClientState {
  phase: 'idle' | 'sending' | 'awaiting_snapshot' | 'uncertain' | 'reconciling' | 'stale';
  message: string;
  request_id: string | null;
}
interface Pending {request: CreativeRequest; label: string; revision: number | null; generation: number; ownerTransition: boolean; nextOwner?: string}
type Operation = (request: CreativeRequest) => Promise<CreativeReceipt>;

/**
 * Serialization and receipt fencing, NOT a second layer-document/history store.
 * The host must enforce the envelope at commit time, own request receipts across
 * unmount/navigation, and publish an immutable authoritative snapshot afterward.
 */
export class CreativeLayerClient {
  private state: CreativeClientState = {phase: 'idle', message: '', request_id: null};
  private readonly listeners = new Set<() => void>();
  private pending: Pending | null = null;
  private observed: CreativeBinding | null = null;
  private generation = 0;
  private active = true;
  private readonly authority: () => CreativeAuthority | null;
  private readonly ports: () => CreativePorts;
  private readonly id: () => string;

  constructor(
    authority: () => CreativeAuthority | null,
    ports: () => CreativePorts,
    id: () => string = () => crypto.randomUUID(),
  ) {this.authority = authority; this.ports = ports; this.id = id;}

  getState = (): CreativeClientState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener); return () => {this.listeners.delete(listener);};
  };
  private publish(next: CreativeClientState) {
    if (!this.active) return;
    this.state = next; this.listeners.forEach(listener => listener());
  }
  private current(pending: Pending): boolean {
    const authority = this.authority();
    return this.active && this.pending === pending && this.generation === pending.generation &&
      !!authority && sameOwner(bindingFor(authority), pending.request);
  }
  private finish(message: string) {
    this.pending = null; this.publish({phase: 'idle', request_id: null, message});
  }
  private uncertain(pending: Pending, message: string) {
    if (!this.current(pending)) return;
    this.publish({phase: 'uncertain', request_id: pending.request.request_id,
      message: `${message} 原操作结果待确认，已暂停后续操作；不会自动重发。`});
  }

  /** Call when the host's authoritative identity/revision changes. */
  synchronize() {
    const pending = this.pending, authority = this.authority();
    const next = authority ? bindingFor(authority) : null;
    if (!next || !this.observed || !sameOwner(next, this.observed)) {
      this.observed = next;
      if (!pending && this.state.phase === 'stale') this.finish('已切换到新的编辑上下文。');
    } else if (next.expected_revision < this.observed.expected_revision) {
      if (pending) this.uncertain(pending, '宿主文档修订号倒退，不能确认当前状态。');
      else this.publish({phase: 'stale', request_id: null, message: '宿主文档修订号倒退，已暂停编辑。请回读最新状态，不会覆盖较新的修订。'});
      return;
    } else {
      this.observed = next;
      if (!pending && this.state.phase === 'stale') this.finish('最新文档状态已恢复。');
    }
    if (!pending) return;
    if (authority && pending.nextOwner && pending.revision !== null &&
        authority.document.document_id === pending.request.document_id && authority.document.source_uid === pending.request.source_uid &&
        authority.ownership_token === pending.nextOwner && authority.document.revision >= pending.revision) {
      this.finish(`${pending.label}已确认。`); return;
    }
    if (!authority || !sameOwner(bindingFor(authority), pending.request)) {
      // This is not cancellation. The host retains the old operation and its receipt.
      ++this.generation; this.finish('编辑上下文已切换；旧操作的结果由宿主继续核对。'); return;
    }
    if (this.state.phase === 'awaiting_snapshot' && !pending.nextOwner && pending.revision !== null &&
        authority.document.revision >= pending.revision) this.finish(`${pending.label}已确认。`);
  }

  private settle(pending: Pending, reply: CreativeReceipt) {
    if (!this.current(pending)) return;
    const expected = pending.request;
    if (!reply || reply.request_id !== expected.request_id || reply.document_id !== expected.document_id ||
        reply.source_uid !== expected.source_uid || reply.ownership_token !== expected.ownership_token ||
        reply.expected_revision !== expected.expected_revision) {
      this.uncertain(pending, '操作回执身份不匹配。'); return;
    }
    if (reply.status === 'rejected') {
      this.finish(`${pending.label}未执行：${reply.message || '宿主拒绝了操作。'}`); this.synchronize(); return;
    }
    if (reply.status === 'unknown') {this.uncertain(pending, reply.message || '操作结果未知。'); return;}
    const ownerChanged = (reply.status === 'applied' || reply.status === 'no_change') && pending.ownerTransition &&
      typeof reply.next_ownership_token === 'string' && !!reply.next_ownership_token && reply.next_ownership_token !== expected.ownership_token;
    if ((reply.status !== 'applied' && reply.status !== 'no_change') ||
        !validRevision(reply.revision) || (reply.revision < expected.expected_revision && !ownerChanged)) {
      this.uncertain(pending, '操作回执缺少有效修订号。'); return;
    }
    pending.revision = reply.revision;
    if (ownerChanged) {
      pending.nextOwner = reply.next_ownership_token;
      this.publish({phase: 'awaiting_snapshot', request_id: expected.request_id, message: `${pending.label}已确认，等待新的历史所有权状态。`});
      this.synchronize(); return;
    }
    const authority = this.authority();
    if (authority && (authority.document.revision < expected.expected_revision ||
        (this.observed && sameOwner(this.observed, expected) && authority.document.revision < this.observed.expected_revision))) {
      this.uncertain(pending, '宿主文档状态早于操作起始修订。'); return;
    }
    if (authority && authority.document.revision >= reply.revision) {
      this.finish(reply.status === 'no_change' ? `${pending.label}未产生改动。` : `${pending.label}已确认。`);
    } else {
      this.publish({phase: 'awaiting_snapshot', request_id: expected.request_id,
        message: `${pending.label}已收到回执，正在等待宿主发布确认后的文档状态。`});
    }
  }

  private async run(label: string, operation: Operation | undefined, ownerTransition = false): Promise<void> {
    if (!this.active) return;
    this.synchronize();
    const authority = this.authority();
    if (this.pending || authority?.busy || this.state.phase === 'stale') return;
    if (!authority || !authority.ownership_token) {this.finish('当前没有可编辑的图层文档。'); return;}
    if (!operation) {this.finish(`${label}接口未接入，未执行。`); return;}
    const request = {...bindingFor(authority), request_id: this.id()};
    const pending: Pending = {request, label, revision: null, generation: this.generation, ownerTransition};
    this.pending = pending;
    this.publish({phase: 'sending', request_id: request.request_id, message: `正在${label}…`});
    try {this.settle(pending, await operation(request));}
    catch (error) {this.uncertain(pending, error instanceof Error ? error.message : String(error));}
  }

  execute(command: CreativeCommand, label = '更新图层'): Promise<void> {
    const send = this.ports().command;
    return this.run(label, send ? request => send({...request, command}) : undefined);
  }
  importImage(file: File): Promise<void> {
    const send = this.ports().importImage;
    return this.run('导入图片图层', send ? request => send({...request, file}) : undefined);
  }
  attachMask(layer_id: string, file: File): Promise<void> {
    const send = this.ports().attachMask;
    return this.run('附加栅格蒙版', send ? request => send({...request, layer_id, file}) : undefined);
  }
  removeMask(layer_id: string): Promise<void> {
    const send = this.ports().removeMask;
    return this.run('移除栅格蒙版', send ? request => send({...request, layer_id}) : undefined);
  }
  undo(): Promise<void> {return this.run('撤销', this.ports().undo, true);}
  redo(): Promise<void> {return this.run('重做', this.ports().redo, true);}
  returnImage(mode: 'new' | 'update', preview: CreativePreview): Promise<void> {
    const authority = this.authority();
    if (!authority || !previewMatches(preview, authority)) {
      if (!this.pending) this.finish('当前渲染预览已失效，请等待本修订的真实合成画面。');
      return Promise.resolve();
    }
    const send = mode === 'new' ? this.ports().returnNew : this.ports().updateOriginal;
    return this.run(mode === 'new' ? '返回新图片' : '更新原图片',
      send ? request => send({...request, render_id: preview.render_id}) : undefined, true);
  }
  async reconcile(): Promise<void> {
    this.synchronize();
    const pending = this.pending, query = this.ports().reconcile;
    if (!pending || !query || !this.current(pending) ||
        !['sending', 'uncertain', 'awaiting_snapshot'].includes(this.state.phase)) return;
    this.publish({phase: 'reconciling', request_id: pending.request.request_id, message: '正在查询原操作回执，不会重发操作…'});
    try {this.settle(pending, await query(pending.request));}
    catch (error) {this.uncertain(pending, error instanceof Error ? error.message : String(error));}
  }
  /** Do not invoke a native cancellation or undo merely because a panel unmounts. */
  dispose() {this.active = false; ++this.generation; this.listeners.clear();}
}
