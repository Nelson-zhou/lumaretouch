// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useId, useMemo, useRef, useState, useSyncExternalStore} from 'react';
import {TetherController} from './controller';
import {defaultImportFormat, deviceStartBlocker, IMPORT_FORMATS, ingestionTargetBlocker, NAMING_MODES, namingError, permittedFormats, SESSION_LABELS, sessionIsOpen, TRANSFER_LABELS, transferCanRetry} from './model';
import type {TetherAction, TetherCapability, TetherDestination, TetherHostPort, TetherImportFormat, TetherImportNotice, TetherNaming, TetherPreviewMode, TetherTransfer} from './protocol';
import './tetherCapture.css';

export interface TetherCapturePanelProps {
  host?: TetherHostPort | null;
  unavailableReason?: string;
  /** Host already imported the asset; this callback is navigation/refresh only. */
  onImportedDocument?: (notice: TetherImportNotice) => void;
}
const ACTION_LABELS: Record<TetherAction, string> = {
  probe_device: '验证设备', start: '启动会话', stop: '停止会话', retry_transfer: '重试传输',
  set_preview_mode: '更改预览行为', start_live_view: '开启实时取景', stop_live_view: '关闭实时取景', capture: '遥控快门',
};
const CAPABILITY_LABELS: Record<TetherCapability['state'], string> = {
  unknown: '未确认', driver_advertised: '设备声明，尚未验证', verified: '当前运行时已验证', unsupported: '不可用',
};
function Capability({label, value}: {label: string; value: TetherCapability}) {
  return <li><span>{label}</span><span>{CAPABILITY_LABELS[value.state]}</span>{value.reason && <small>{value.reason}</small>}</li>;
}
function TransferProgress({transfer}: {transfer: TetherTransfer}) {
  const received = transfer.bytes_received, total = transfer.bytes_total;
  const measured = typeof received === 'number' && Number.isFinite(received) && received >= 0;
  const bounded = measured && typeof total === 'number' && Number.isFinite(total) && total > 0 && received <= total;
  return <>{bounded && <progress value={received} max={total} aria-label={`${transfer.camera_filename} 已传输字节`}/>}
    {measured && <small>{received.toLocaleString()} 字节{bounded ? ` / ${total.toLocaleString()} 字节` : '，总大小尚未确认'}</small>}</>;
}
function SafetyNotice() {
  return <p className="tether-policy">只接收与保存原片，不删除相机文件，不修改相机设置，不覆盖已有文件。首次实际文件传输才能验证原片下载；会话启动不代表已验证下载。下载完成、导入完成和画质验收是不同状态。</p>;
}
export function TetherCapturePanel(props: TetherCapturePanelProps) {
  if (!props.host) return <section className="tether-capture-panel" aria-label="有线联机拍摄">
    <h3>有线联机拍摄</h3><p role="status">{props.unavailableReason || '联机拍摄运行时尚未连接。需要真实设备运行时及设备验证，当前没有可用相机。'}</p>
    <SafetyNotice/><p>不会用演示相机、占位照片或模拟进度代替设备连接。</p>
  </section>;
  return <ConnectedTetherPanel key={props.host.host_id} {...props} host={props.host}/>;
}
function ConnectedTetherPanel({host, onImportedDocument}: TetherCapturePanelProps & {host: TetherHostPort}) {
  const controller = useMemo(() => new TetherController(host), [host]);
  const importCallback = useRef(onImportedDocument); importCallback.current = onImportedDocument;
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const id = useId();
  const [deviceId, setDeviceId] = useState('');
  const [destination, setDestination] = useState<TetherDestination | null>(null);
  const [naming, setNaming] = useState<TetherNaming>({mode: 'original', custom_name: '', counter_start: 1});
  const [importFormat, setImportFormat] = useState<TetherImportFormat | null>(null);
  const [previewMode, setPreviewMode] = useState<TetherPreviewMode>(host.supported_preview_modes?.[0] ?? 'follow_latest');
  useEffect(() => controller.connect(notice => importCallback.current?.(notice)), [controller]);
  const snapshot = state.snapshot, session = snapshot?.session ?? null;
  const sessionOpen = sessionIsOpen(session), active = session?.phase === 'active';
  const device = snapshot?.devices.find(item => item.device_id === (sessionOpen ? session?.device_id : deviceId));
  const waiting = state.pending.length > 0;
  const setupLocked = sessionOpen || waiting || state.picking_destination;
  const runtimeReady = !!snapshot?.availability.available;
  const selectedFormats = permittedFormats(device?.recording_format ?? 'unknown');
  useEffect(() => {
    if (!deviceId && snapshot?.devices.length === 1) setDeviceId(snapshot.devices[0].device_id);
  }, [deviceId, snapshot?.devices]);
  useEffect(() => {
    const format = device?.recording_format ?? 'unknown';
    setImportFormat(defaultImportFormat(format));
  }, [device?.device_id, device?.recording_format]);
  useEffect(() => {
    if (!session) return;
    setDeviceId(session.device_id); setDestination(session.destination); setNaming(session.naming);
    setImportFormat(session.import_format); setPreviewMode(session.preview_mode);
  }, [session?.session_id]);
  const startBlocker = !snapshot ? '正在读取设备状态。' : !runtimeReady ? snapshot.availability.reason || '运行时不可用。' :
    deviceStartBlocker(device) || ingestionTargetBlocker(snapshot.ingestion_target) || (!destination ? '请选择原片保存位置。' : null) || namingError(naming) ||
    (!importFormat || !selectedFormats.includes(importFormat) ? '请选择相机实际保存的照片格式。' : null);
  const currentPreviewMode = sessionOpen && session ? session.preview_mode : previewMode;
  const remote = device?.capabilities.remote_shutter, liveView = device?.capabilities.live_view;
  const declared = (capability: TetherCapability | undefined) => capability && ['verified', 'driver_advertised'].includes(capability.state);
  const transfers = snapshot?.transfers.filter(transfer => session && transfer.session_id === session.session_id && transfer.session_generation === session.generation) ?? [];
  const captured = transfers.filter(transfer => transfer.phase === 'imported').length;
  const visibleTarget = sessionOpen ? session?.ingestion_target : snapshot?.ingestion_target;
  const sameTarget = !sessionOpen || !!session && session.ingestion_target.project_id === snapshot?.ingestion_target?.project_id && session.ingestion_target.path === snapshot?.ingestion_target?.path;
  const admitted = sameTarget && !ingestionTargetBlocker(snapshot?.ingestion_target);
  return <section className="tether-capture-panel" aria-labelledby={`${id}-title`} data-tool-anchor="联机拍摄/有线联机">
    <header className="tether-heading"><div><h3 id={`${id}-title`}>有线联机拍摄</h3><p>{session ? SESSION_LABELS[session.phase] : '准备相机与保存位置'}</p></div>
      <button type="button" disabled={state.refreshing} onClick={() => void controller.refresh()}>{state.refreshing ? '正在读取…' : '刷新设备与状态'}</button></header>
    {!runtimeReady && <p className="tether-notice" role="status">{snapshot?.availability.reason || '等待真实宿主状态，尚未确认可用设备。'}</p>}
    <SafetyNotice/>

    <fieldset className="tether-section" disabled={setupLocked}><legend>1. 相机连接</legend>
      <label htmlFor={`${id}-device`}>选择设备</label>
      <select id={`${id}-device`} value={sessionOpen ? session?.device_id ?? '' : deviceId} onChange={event => setDeviceId(event.target.value)}>
        <option value="">{snapshot?.devices.length ? '请选择相机' : '尚未检测到相机'}</option>
        {snapshot?.devices.map(item => <option key={item.device_id} value={item.device_id} disabled={!item.connected || !item.detected_by_runtime}>{item.label}{!item.connected ? '（未连接）' : !item.detected_by_runtime ? '（未验证）' : ''}</option>)}
      </select>
      <button type="button" disabled={!runtimeReady || !device?.connected || !device.detected_by_runtime} onClick={() => device && void controller.send({action: 'probe_device', device_id: device.device_id})}>验证所选设备</button>
      <p>验证仅打开设备、读取参数与有限等待设备事件，不拍照、不下载、不修改设置。事件接口可用不等于已验收实体快门传输。</p>
    </fieldset>
    {device && <div className="tether-device-details"><p>{device.connected && device.detected_by_runtime ? '当前运行时已检测到连接' : '设备连接尚未验证'} · {device.label}</p>
      <ul className="tether-capabilities">
        <Capability label="文件事件读取" value={device.capabilities.event_polling}/><Capability label="原片下载" value={device.capabilities.original_download}/>
        <Capability label="遥控快门" value={device.capabilities.remote_shutter}/><Capability label="实时取景" value={device.capabilities.live_view}/>
      </ul>
      {device.settings.length > 0 && <dl className="tether-camera-settings">{device.settings.map((setting, index) => <div key={`${setting.label}-${index}`}><dt>{setting.label}</dt><dd>{setting.value}</dd></div>)}</dl>}
    </div>}

    <fieldset className="tether-section" disabled={setupLocked}><legend>2. 拍摄导入</legend>
      <div className="tether-project-target"><strong>导入目标项目{sessionOpen ? '（本会话已冻结）' : ''}</strong>
        {visibleTarget ? <><p>{visibleTarget.name || visibleTarget.project_id}</p><output className="tether-destination">{visibleTarget.path}</output><small>项目标识：{visibleTarget.project_id}</small></> : <p>没有已保存并获准接收照片的目标项目。</p>}
        {sameTarget && snapshot?.ingestion_target && <p>{Number.isSafeInteger(snapshot.ingestion_target.remaining_operations) ? `剩余导入操作额度：${snapshot.ingestion_target.remaining_operations}` : '导入操作额度尚未确认'}{!snapshot.ingestion_target.available ? ' · 暂不可导入' : ''}</p>}
        {sameTarget && snapshot?.ingestion_target?.reason && <p>{snapshot.ingestion_target.reason}</p>}
        {!sameTarget && <p role="alert">当前项目与本会话目标不同，不会切换编辑器项目或将原片改导入到其他项目。请停止并核对。</p>}
      </div>
      <label htmlFor={`${id}-format`}>传输照片格式</label>
      <select id={`${id}-format`} value={sessionOpen && session ? session.import_format : importFormat ?? ''} onChange={event => setImportFormat(event.target.value as TetherImportFormat)}>
        {!importFormat && <option value="">等待读取相机保存格式</option>}
        {IMPORT_FORMATS.map(item => <option key={item.value} value={item.value} disabled={!device || !selectedFormats.includes(item.value)}>{device?.recording_format === 'unknown' && item.value === 'raw_jpeg' ? '导入实际收到的 RAW/JPEG（格式未识别）' : item.label}</option>)}
      </select>
      <p>{device?.recording_format === 'raw_jpeg' ? '相机保存 RAW 和 JPEG，可传输两种或只传输一种；不会删除未选格式的相机文件。' :
        device?.recording_format === 'raw' ? '相机仅保存 RAW，因此只能导入 RAW。' : device?.recording_format === 'jpeg' ? '相机仅保存 JPEG，因此只能导入 JPEG。' :
          device ? '相机保存格式未识别，将导入实际收到的 RAW/JPEG；不能选择单一格式，不推断相机保存模式，也不生成缺失的另一种格式。' : '请先选择实际检测到的相机。'}</p>
      {device?.recording_format === 'unknown' && device.recording_format_reason && <p>{device.recording_format_reason}</p>}
      <label>保存位置<output className="tether-destination">{destination?.display_path || '尚未选择文件夹'}</output></label>
      <button type="button" disabled={!snapshot} onClick={() => { void controller.pickDestination().then(result => { if (result) setDestination(result); }); }}>{state.picking_destination ? '正在选择…' : '选择原片保存文件夹'}</button>
      <label htmlFor={`${id}-naming`}>照片命名方式</label>
      <select id={`${id}-naming`} value={naming.mode} onChange={event => setNaming({...naming, mode: event.target.value as TetherNaming['mode']})}>
        {NAMING_MODES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}
      </select>
      {naming.mode.startsWith('custom_') && <label htmlFor={`${id}-custom`}>自定义名称<input id={`${id}-custom`} maxLength={80} value={naming.custom_name} onChange={event => setNaming({...naming, custom_name: event.target.value})}/></label>}
      {naming.mode.endsWith('_counter') && <label htmlFor={`${id}-counter`}>计数器起始值<input id={`${id}-counter`} type="number" min={1} max={999999999} step={1} value={Number.isFinite(naming.counter_start) ? naming.counter_start : ''} onChange={event => setNaming({...naming, counter_start: event.target.valueAsNumber})}/></label>}
      <p>这些命名规则用于暂存原片及工程显示名；所选托管目录内仍使用既有 UUID 文件名，不是按该规则直接交付文件。设置在启动时冻结；若在相机端更改保存格式，请停止后重新验证。</p>
    </fieldset>

    {host.supported_preview_modes?.length === 1 && host.supported_preview_modes[0] === 'keep_current' && <p>当前接入会话固定编辑器选片，只支持保持位置。最新照片定位尚未接通；实时取景不是已导入原片预览。</p>}
    <fieldset className="tether-section" disabled={waiting || !!session && ['starting', 'stopping', 'error'].includes(session.phase)}><legend>3. 预览行为</legend>
      <label htmlFor={`${id}-preview`}>照片导入后</label>
      <select id={`${id}-preview`} value={currentPreviewMode} onChange={event => {
        const value = event.target.value as TetherPreviewMode;
        if (active) void controller.send({action: 'set_preview_mode', preview_mode: value}); else setPreviewMode(value);
      }}><option value="follow_latest" disabled={!!host.supported_preview_modes && !host.supported_preview_modes.includes('follow_latest')}>定位到最新</option><option value="keep_current">保持预览位置</option></select>
      <p>{currentPreviewMode === 'follow_latest' ? '仅在真实文件完成托管导入后，通知主界面定位到新照片。' : '继续接收照片，但不改变当前选中的照片。'}</p>
    </fieldset>

    <div className="tether-session-actions">
      {!sessionOpen ? <button type="button" className="tether-primary" disabled={!!startBlocker || waiting || state.picking_destination} onClick={() => {
        const target = snapshot?.ingestion_target;
        if (device && destination && importFormat && target) void controller.send({action: 'start', device_id: device.device_id, ingestion_target: {project_id: target.project_id, path: target.path}, destination, naming: {...naming}, import_format: importFormat, preview_mode: previewMode});
      }}>开始接收照片</button> : <button type="button" disabled={state.pending.some(request => request.action === 'stop') || session?.phase === 'stopping'} onClick={() => void controller.send({action: 'stop'})}>停止联机接收</button>}
      {!sessionOpen && startBlocker && <p>{startBlocker}</p>}
      {active && <p>{admitted ? '现在可按相机实体快门。只有相机报告的新文件经过下载、校验和导入后，才会出现在照片列表。' : '当前导入目标或额度未就绪，请先停止并核对；不会改用其他项目接收。'}</p>}
      {session?.error && <p role="alert">{session.error}</p>}
    </div>

    {active && <section className="tether-section" aria-label="可选相机控制">
      <h4>可选相机控制</h4><div className="tether-button-row">
        {declared(remote) ? <button type="button" disabled={waiting || !runtimeReady || !device?.connected || !admitted} onClick={() => void controller.send({action: 'capture'})}>{remote?.state === 'verified' ? '遥控拍摄一张' : '尝试遥控拍摄一张'}</button> : <p>遥控快门不可用：{remote?.reason || '设备未提供可验证的遥控快门能力。'}</p>}
        {session?.live_view !== 'off' ? <button type="button" disabled={waiting || session?.live_view === 'stopping'} onClick={() => void controller.send({action: 'stop_live_view'})}>关闭实时取景</button> : declared(liveView) ?
          <button type="button" disabled={waiting || !runtimeReady || !device?.connected} onClick={() => void controller.send({action: 'start_live_view'})}>{liveView?.state === 'verified' ? '开启实时取景' : '尝试开启实时取景'}</button> : <p>实时取景不可用：{liveView?.reason || '设备未提供可验证的实时取景能力。'}</p>}
      </div>
      {(remote?.state === 'driver_advertised' || liveView?.state === 'driver_advertised') && <p>“尝试”表示设备驱动声明支持，但此操作尚未实际验证。不会自动触发快门。</p>}
      {state.frame ? <figure className="tether-live-frame"><img src={state.frame.image_url} width={state.frame.width} height={state.frame.height} alt="当前相机实时取景"/><figcaption>相机实时取景，不是导入原片或画质验收结果。</figcaption></figure> : session?.live_view === 'on' || session?.live_view === 'starting' ? <p role="status">等待当前会话的真实相机画面，尚未收到可显示帧。</p> : null}
    </section>}

    {state.pending.length > 0 && <section className="tether-pending" aria-label="待确认请求"><h4>请求回执</h4>
      <p>未确认的操作不会自动重发。找不到回执也不表示未执行，先查询原请求。</p>
      <ul>{state.pending.map(request => <li key={request.request_id}><div>{ACTION_LABELS[request.action]} · {request.state === 'sending' ? '正在发送' : request.state === 'outcome_unknown' ? '结果未确认' : '处理中'}</div>
        {request.error && <p>{request.error}</p>}<small>请求标识：{request.request_id}</small>
        <button type="button" disabled={request.state === 'sending' || state.querying.includes(request.request_id)} onClick={() => void controller.query(request.request_id)}>{state.querying.includes(request.request_id) ? '正在查询…' : '查询原操作结果'}</button></li>)}</ul>
    </section>}

    <section className="tether-section" aria-label="照片传输队列"><h4>传输队列{transfers.length ? ` · 已导入 ${captured} / ${transfers.length}` : ''}</h4>
      {transfers.length === 0 ? <p>{active ? '等待相机的新文件事件。没有模拟照片或模拟进度。' : '尚无当前会话的传输记录。'}</p> :
        <ol className="tether-transfer-list">{transfers.map(transfer => <li key={transfer.transfer_id}>
          <div className="tether-transfer-title"><strong>{transfer.local_filename || transfer.camera_filename}</strong><span>{TRANSFER_LABELS[transfer.phase]}</span></div>
          {transfer.local_filename && transfer.local_filename !== transfer.camera_filename && <small>相机原文件名：{transfer.camera_filename}</small>}
          <TransferProgress transfer={transfer}/>
          {transfer.error && <p role={transfer.phase === 'failed' ? 'alert' : undefined}>{transfer.error}</p>}
          {transfer.phase === 'outcome_unknown' && <p>请刷新状态或查询上方原请求，不会重新下载或重复导入。</p>}
          {transferCanRetry(transfer, session) && <button type="button" disabled={waiting || !runtimeReady || !admitted} onClick={() => void controller.send({action: 'retry_transfer', transfer_id: transfer.transfer_id})}>重试此文件</button>}
        </li>)}</ol>}
    </section>
    {state.message && <p className="tether-message" role="status" aria-live="polite">{state.message}</p>}
    <p className="tether-policy">待接入：下一张同步效果、预设自动应用、叠加层与 AI 挑图。当前不会显示无效控制，也不会自动改图。</p>
  </section>;
}
