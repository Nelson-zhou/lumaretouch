// SPDX-License-Identifier: GPL-3.0-or-later
import {deviceStartBlocker, ingestionTargetBlocker, namingError, permittedFormats, sessionIsOpen, transferCanRetry} from './model';
import {TETHER_HOST_PROTOCOL} from './protocol';
import type {TetherCommand, TetherDestination, TetherHostEvent, TetherHostPort, TetherImportNotice, TetherLiveFrame, TetherPendingRequest, TetherReceipt, TetherRequest, TetherSnapshot} from './protocol';

export interface TetherPendingOperation extends TetherPendingRequest {
  state: 'sending' | 'pending' | 'outcome_unknown';
  error?: string;
}
export interface TetherControllerState {
  snapshot: TetherSnapshot | null;
  pending: ReadonlyArray<TetherPendingOperation>;
  querying: ReadonlyArray<string>;
  refreshing: boolean;
  picking_destination: boolean;
  message: string;
  frame: TetherLiveFrame | null;
}
const errorText = (error: unknown) => error instanceof Error ? error.message : '请求未完成，请读取状态后核对。';
const REQUEST_WAIT_MS = 12000;
function deadline<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(new Error('等待回执超时，结果仍不确定；只查询原请求，不会自动重发。')), REQUEST_WAIT_MS);
  })]).finally(() => { if (timer !== undefined) clearTimeout(timer); });
}
function sameIdentity(a: TetherPendingRequest, b: TetherPendingRequest): boolean {
  return a.request_id === b.request_id && a.action === b.action &&
    a.expected_session_id === b.expected_session_id && a.expected_generation === b.expected_generation;
}
function validFrame(frame: TetherLiveFrame): boolean {
  return Number.isSafeInteger(frame.sequence) && frame.sequence >= 0 &&
    Number.isSafeInteger(frame.width) && frame.width > 0 && Number.isSafeInteger(frame.height) && frame.height > 0 &&
    (/^blob:/.test(frame.image_url) || /^data:image\/(?:jpeg|png|webp);base64,/.test(frame.image_url));
}

/** One controller per mounted panel. The HOST owns durable pending identities,
 * session lifetime and import deduplication. Unmount only detaches observers; it
 * cannot silently stop a camera or discard an uncertain mutation. */
export class TetherController {
  private state: TetherControllerState = {snapshot: null, pending: [], querying: [], refreshing: false, picking_destination: false, message: '', frame: null};
  private listeners = new Set<() => void>();
  private epoch = 0;
  private connected = false;
  private detach: (() => void) | null = null;
  private receiptTimer: ReturnType<typeof setInterval> | null = null;
  private highestGeneration = -1;
  private readSerial = 0;
  private readonly deliveredImports = new Set<string>();
  private readonly resolvedRequests = new Set<string>();
  private onImported: ((notice: TetherImportNotice) => void) | undefined;
  constructor(private readonly port: TetherHostPort) {}
  snapshot = (): TetherControllerState => this.state;
  subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private update(patch: Partial<TetherControllerState>) {
    this.state = {...this.state, ...patch};
    for (const listener of this.listeners) listener();
  }
  connect(onImported?: (notice: TetherImportNotice) => void): () => void {
    this.disconnect();
    this.connected = true;
    this.onImported = onImported;
    const epoch = this.epoch;
    if (this.port.protocol_version !== TETHER_HOST_PROTOCOL || !this.port.host_id) {
      this.update({message: '联机拍摄宿主协议不可用，需要配套的 TetherHostPort v1。'});
      return () => this.disconnect();
    }
    try {
      this.detach = this.port.subscribe(event => { if (this.connected && epoch === this.epoch) this.receive(event); });
      this.receiptTimer = setInterval(() => {
        if (this.isCurrent(epoch)) for (const pending of this.state.pending) void this.query(pending.request_id);
      }, 1000);
      void this.refresh();
    } catch (error) { this.update({message: errorText(error)}); }
    return () => { if (epoch === this.epoch) this.disconnect(); };
  }
  private disconnect() {
    this.connected = false;
    if (this.receiptTimer !== null) clearInterval(this.receiptTimer);
    this.receiptTimer = null;
    this.epoch++;
    this.readSerial++;
    const detach = this.detach; this.detach = null;
    try { detach?.(); } catch { /* Detachment never becomes a camera mutation. */ }
    this.onImported = undefined;
    this.update({querying: [], refreshing: false, picking_destination: false, frame: null,
      pending: this.state.pending.map(pending => ({...pending, state: 'outcome_unknown'}))});
  }
  private isCurrent(epoch: number) { return this.connected && this.epoch === epoch; }
  private adopt(next: TetherSnapshot): boolean {
    if (next.protocol_version !== TETHER_HOST_PROTOCOL || next.host_id !== this.port.host_id ||
        !Number.isSafeInteger(next.revision) || next.revision < 0) throw new Error('宿主回读身份或版本无效，未采用。');
    const previous = this.state.snapshot;
    if (previous && next.revision < previous.revision) return false;
    // A revision identifies one immutable snapshot. Same-revision replies may
    // accompany events, but cannot replace newer local receipt bookkeeping.
    if (previous && next.revision === previous.revision) return true;
    if (next.session) {
      if (!Number.isSafeInteger(next.session.generation) || next.session.generation < 0) throw new Error('会话代次无效，未采用。');
      if (next.session.generation < this.highestGeneration) return false;
      if (previous && !previous.session && next.session.generation <= this.highestGeneration) return false;
      if (previous?.session && next.session.generation === previous.session.generation && next.session.session_id !== previous.session.session_id) throw new Error('会话标识与代次冲突，未采用。');
      if (previous?.session?.generation === next.session.generation &&
          (previous.session.phase === 'stopped' && next.session.phase !== 'stopped' ||
           previous.session.phase === 'stopping' && ['starting', 'active'].includes(next.session.phase))) return false;
      this.highestGeneration = Math.max(this.highestGeneration, next.session.generation);
    }
    const pending = [...this.state.pending];
    for (const request of next.pending_requests) {
      if (this.resolvedRequests.has(request.request_id)) continue;
      const existing = pending.find(item => item.request_id === request.request_id);
      if (existing && !sameIdentity(existing, request)) throw new Error('宿主待确认请求身份冲突。');
      if (!existing) pending.push({...request, state: 'pending'});
    }
    const frame = this.state.frame;
    const keepFrame = frame && next.session?.phase === 'active' && next.session.live_view === 'on' &&
      frame.session_id === next.session.session_id && frame.session_generation === next.session.generation;
    this.update({snapshot: next, pending, frame: keepFrame ? frame : null});
    return true;
  }
  private receive(event: TetherHostEvent) {
    try {
      if (event.type === 'live_frame') {
        const frame = event.frame, session = this.state.snapshot?.session;
        const device = this.state.snapshot?.devices.find(item => item.device_id === session?.device_id);
        if (frame.host_id !== this.port.host_id || !session || session.phase !== 'active' || session.live_view !== 'on' ||
            device?.capabilities.live_view.state !== 'verified' || frame.session_id !== session.session_id ||
            frame.session_generation !== session.generation || !validFrame(frame)) return;
        if (this.state.pending.some(request => request.expected_session_id === session.session_id && ['stop', 'stop_live_view'].includes(request.action))) return;
        if (this.state.frame && frame.sequence <= this.state.frame.sequence) return;
        this.update({frame});
        return;
      }
      if (!this.adopt(event.snapshot) || event.type !== 'imported_document') return;
      const receipt = event.receipt, session = this.state.snapshot?.session;
      if (!session || session.phase !== 'active' || session.session_id !== receipt.session_id || session.generation !== receipt.session_generation ||
          receipt.project_id !== session.ingestion_target.project_id || receipt.project_path !== session.ingestion_target.path ||
          !receipt.import_receipt_id || !receipt.document_id || !receipt.managed_path || !/^[a-f0-9]{64}$/i.test(receipt.sha256) ||
          !Number.isSafeInteger(receipt.bytes) || receipt.bytes <= 0 || this.deliveredImports.has(receipt.import_receipt_id)) return;
      if (this.state.pending.some(request => request.expected_session_id === session.session_id && request.action === 'stop')) return;
      const transfer = this.state.snapshot?.transfers.find(item => item.transfer_id === receipt.transfer_id && item.session_id === receipt.session_id && item.session_generation === receipt.session_generation);
      const recorded = transfer?.imported_document;
      if (transfer?.phase !== 'imported' || !recorded || recorded.import_receipt_id !== receipt.import_receipt_id ||
          recorded.document_id !== receipt.document_id || recorded.sha256 !== receipt.sha256 || recorded.bytes !== receipt.bytes ||
          recorded.project_id !== receipt.project_id || recorded.project_path !== receipt.project_path ||
          recorded.managed_path !== receipt.managed_path) return;
      this.deliveredImports.add(receipt.import_receipt_id);
      const changingPreview = this.state.pending.some(request => request.expected_session_id === session.session_id && request.action === 'set_preview_mode');
      const currentTarget = this.state.snapshot?.ingestion_target;
      const sameTarget = !!currentTarget && currentTarget.project_id === receipt.project_id && currentTarget.path === receipt.project_path;
      this.onImported?.({receipt, make_current: sameTarget && !changingPreview && session.preview_mode === 'follow_latest'});
    } catch (error) { this.update({message: errorText(error)}); }
  }
  async refresh(): Promise<void> {
    if (!this.connected) return;
    const epoch = this.epoch, serial = ++this.readSerial;
    this.update({refreshing: true});
    try {
      const snapshot = await deadline(this.port.readSnapshot());
      if (this.isCurrent(epoch) && serial === this.readSerial) { this.adopt(snapshot); this.update({message: ''}); }
    } catch (error) { if (this.isCurrent(epoch) && serial === this.readSerial) this.update({message: errorText(error)}); }
    finally { if (this.isCurrent(epoch) && serial === this.readSerial) this.update({refreshing: false}); }
  }
  async pickDestination(): Promise<TetherDestination | null> {
    if (!this.connected || this.state.picking_destination || this.state.pending.length || sessionIsOpen(this.state.snapshot?.session ?? null)) return null;
    const epoch = this.epoch, snapshot = this.state.snapshot;
    this.update({picking_destination: true});
    try {
      const result = await this.port.pickDestination();
      if (!this.isCurrent(epoch) || sessionIsOpen(this.state.snapshot?.session ?? null) || this.state.pending.length || !snapshot ||
          snapshot.session?.session_id !== this.state.snapshot?.session?.session_id || snapshot.session?.generation !== this.state.snapshot?.session?.generation) return null;
      if (result && (!result.destination_id || !result.display_path)) throw new Error('文件夹选择器未返回可用的目标授权。');
      return result;
    } catch (error) { if (this.isCurrent(epoch)) this.update({message: errorText(error)}); return null; }
    finally { if (this.isCurrent(epoch)) this.update({picking_destination: false}); }
  }
  private commandBlocker(command: TetherCommand): string | null {
    const state = this.state.snapshot, session = state?.session;
    if (!this.connected || !state) return '请先读取联机拍摄状态。';
    if (command.action === 'stop') {
      if (this.state.pending.some(request => request.action === 'stop')) return '原停止请求尚未完成，请查询原请求。';
      return sessionIsOpen(session ?? null) ? null : '没有需要停止的会话。';
    }
    if (this.state.pending.length) return '有请求结果尚未确认，请查询原操作，不要重复提交。';
    if (this.state.picking_destination) return '请先完成或取消文件夹选择。';
    if (command.action === 'stop_live_view') return session && session.live_view !== 'off' ? null : '实时取景已经关闭。';
    if (this.state.refreshing) return '正在回读设备状态，请等待回读完成。';
    if (!state.availability.available) return state.availability.reason || '当前设备运行时不可用。';
    if (command.action === 'probe_device') {
      if (sessionIsOpen(session ?? null)) return '请先停止当前会话再验证设备。';
      const device = state.devices.find(item => item.device_id === command.device_id);
      return device?.connected && device.detected_by_runtime ? null : '请选择当前运行时实际检测到的已连接设备。';
    }
    if (command.action === 'start') {
      if (sessionIsOpen(session ?? null)) return '请先停止当前会话。';
      const targetBlocker = ingestionTargetBlocker(state.ingestion_target);
      if (targetBlocker) return targetBlocker;
      if (command.ingestion_target.project_id !== state.ingestion_target?.project_id || command.ingestion_target.path !== state.ingestion_target?.path) return '目标项目已变化，未启动联机接收。';
      const device = state.devices.find(item => item.device_id === command.device_id);
      const blocker = deviceStartBlocker(device) || namingError(command.naming);
      if (blocker) return blocker;
      if (!command.destination.destination_id || !command.destination.display_path) return '请使用文件夹选择器选择保存位置。';
      if (!device || !permittedFormats(device.recording_format).includes(command.import_format)) return '导入格式不符合相机当前保存格式。';
      return null;
    }
    if (!session || session.phase !== 'active') return '当前会话尚未启动或已经停止。';
    if (command.action === 'set_preview_mode') return null;
    if (command.action === 'capture' || command.action === 'retry_transfer') {
      const targetBlocker = ingestionTargetBlocker(state.ingestion_target);
      if (targetBlocker) return targetBlocker;
      if (state.ingestion_target?.project_id !== session.ingestion_target.project_id || state.ingestion_target?.path !== session.ingestion_target.path) return '当前项目与会话目标不同，请停止并重新核对目标项目。';
    }
    const device = state.devices.find(item => item.device_id === session.device_id);
    if (!device?.connected || !device.detected_by_runtime) return '相机连接尚未确认。';
    if (command.action === 'retry_transfer') {
      const transfer = state.transfers.find(item => item.transfer_id === command.transfer_id);
      return transfer && transferCanRetry(transfer, session) ? null : '仅可重试当前会话中已确认失败且允许重试的文件。';
    }
    if (command.action === 'start_live_view') return ['driver_advertised', 'verified'].includes(device.capabilities.live_view.state) && session.live_view === 'off' ? null : '设备未声明实时取景能力，或取景已在运行。';
    return ['driver_advertised', 'verified'].includes(device.capabilities.remote_shutter.state) ? null : '设备未声明遥控快门能力。';
  }
  async send(command: TetherCommand): Promise<void> {
    const blocker = this.commandBlocker(command);
    if (blocker) { this.update({message: blocker}); return; }
    const snapshot = this.state.snapshot!;
    let requestId: string;
    try { requestId = crypto.randomUUID(); }
    catch { this.update({message: '无法创建唯一请求标识，未发送操作。'}); return; }
    const request: TetherRequest = {...command, protocol_version: TETHER_HOST_PROTOCOL, host_id: this.port.host_id,
      request_id: requestId, expected_revision: snapshot.revision,
      expected_session_id: snapshot.session?.session_id ?? null, expected_generation: snapshot.session?.generation ?? null};
    const epoch = this.epoch;
    this.update({message: '', pending: [...this.state.pending, {...request, state: 'sending'}],
      frame: command.action === 'stop' || command.action === 'stop_live_view' ? null : this.state.frame});
    try {
      const receipt = await deadline(this.port.send(request));
      if (this.isCurrent(epoch)) this.acceptReceipt(request, receipt);
    } catch (error) {
      if (this.isCurrent(epoch)) this.markUnknown(request.request_id, errorText(error));
    }
  }
  private markUnknown(id: string, error: string) {
    this.update({message: error, pending: this.state.pending.map(item => item.request_id === id ? {...item, state: 'outcome_unknown', error} : item)});
  }
  private acceptReceipt(request: TetherPendingRequest, receipt: TetherReceipt) {
    if (receipt.protocol_version !== TETHER_HOST_PROTOCOL || receipt.host_id !== this.port.host_id || !sameIdentity(request, receipt)) throw new Error('回执与原请求身份不匹配，仍需查询原请求。');
    if (receipt.snapshot) this.adopt(receipt.snapshot);
    if (receipt.outcome_unknown || receipt.phase !== 'done') {
      this.update({pending: this.state.pending.map(item => item.request_id === request.request_id ? {...item, state: receipt.outcome_unknown ? 'outcome_unknown' : 'pending', error: receipt.error} : item),
        message: receipt.error || '原请求仍在处理，只能查询其结果。'});
      return;
    }
    this.resolvedRequests.add(request.request_id);
    this.update({pending: this.state.pending.filter(item => item.request_id !== request.request_id),
      message: receipt.success ? '' : receipt.error || '宿主确认操作未完成。'});
    // A receipt is not pixel review or proof of a rendered frame. Read back the
    // authoritative session; never synthesize a success state from the request.
    if (receipt.success && !receipt.snapshot) void this.refresh();
  }
  async query(requestId: string): Promise<void> {
    const request = this.state.pending.find(item => item.request_id === requestId);
    if (!this.connected || !request || this.state.querying.includes(requestId)) return;
    const epoch = this.epoch;
    this.update({querying: [...this.state.querying, requestId]});
    try {
      const receipt = await deadline(this.port.queryReceipt(requestId));
      if (!this.isCurrent(epoch)) return;
      if (receipt) this.acceptReceipt(request, receipt);
      else this.markUnknown(requestId, '暂未查到原回执，不代表操作未执行；未自动重发。');
    } catch (error) { if (this.isCurrent(epoch)) this.markUnknown(requestId, errorText(error)); }
    finally { if (this.isCurrent(epoch)) this.update({querying: this.state.querying.filter(id => id !== requestId)}); }
  }
}
