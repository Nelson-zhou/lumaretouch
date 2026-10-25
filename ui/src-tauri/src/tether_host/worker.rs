//! One owner thread for libgphoto2, ingestion lease and occurrence accounting.
use super::{runtime::{Command, Host}, storage::{self, Directory}, wire::{self, Action, Naming, Request}};
use crate::AppState;
use lrt_tether_capture::{CancellationToken, DeviceCapabilities, DeviceEvent, DeviceId,
    LinuxGphotoDevice, SettingValue, StagingRequest, Support, TetherDevicePort};
use serde_json::{json, Value};
use base64::Engine;
use sha2::{Digest, Sha256};
use std::{collections::HashMap, sync::{atomic::Ordering, mpsc::{Receiver, RecvTimeoutError}, Arc}, time::{Duration, Instant}};
use tauri::Emitter;

const POLL: Duration = Duration::from_millis(200);
const READ_INTERVAL: Duration = Duration::from_millis(750);
const LEASE_FRESH: Duration = Duration::from_secs(3);

struct Session {
    id: String,
    generation: u64,
    device_id: String,
    binding: Value,
    engine_id: Option<String>,
    destination: Arc<Directory>,
    stage: Directory,
    naming: Naming,
    date: String,
    ordinal: u64,
    remaining: u64,
    max_operations: u64,
    token: CancellationToken,
    live: bool,
    frame: u64,
    last_frame: Instant,
}
enum FlightKind { Arm(Request), Import { transfer: String, proof: Value }, Release(Request) }
struct Flight { id: String, operation: Option<String>, payload: Value, kind: FlightKind }
struct Read { id: String, query: bool, issued: Instant, serial: u64 }
struct Owner {
    host: Arc<Host>,
    state: Arc<AppState>,
    device: LinuxGphotoDevice,
    devices: HashMap<String, DeviceId>,
    session: Option<Session>,
    flight: Option<Flight>,
    read: Option<Read>,
    stop: Option<Request>,
    optional: Option<Request>,
    driver_open: bool,
    lease_checked: Option<Instant>,
    lease_ok: bool,
    last_read: Instant,
    next_read: bool,
    bytes: u64,
    refresh_devices: bool,
    epoch_lost: bool,
    lease_serial: u64,
    last_observed: Option<(String, Value)>,
}

pub(super) fn run(host: Arc<Host>, state: Arc<AppState>, rx: Receiver<Command>) -> Result<(), String> {
    // Construct here. Rc/opaque native pointers never leave this stack/thread.
    let device = LinuxGphotoDevice::load().map_err(|e| e.to_string())?;
    let mut owner = Owner { host, state, device, devices: HashMap::new(), session:None,
        flight:None,read:None,stop:None,optional:None,driver_open:false,
        lease_checked:None,lease_ok:false,last_read:Instant::now(),next_read:true,
        bytes:0,refresh_devices:true,epoch_lost:false,lease_serial:0,last_observed:None };
    owner.enumerate()?;
    loop {
        if owner.host.closing.load(Ordering::Acquire) { break; }
        match rx.recv_timeout(Duration::from_millis(25)) {
            Ok(Command::Shutdown) | Err(RecvTimeoutError::Disconnected) => break,
            Ok(Command::Refresh) => {
                owner.next_read = true;
                if owner.session.is_none() { owner.refresh_devices = true; }
            }
            Ok(Command::User(request)) => {
                if let Err(error) = owner.command(request.clone()) {
                    let unknown = owner.flight.is_some();
                    owner.host.settle(&request, false, unknown, Some(&error))?;
                }
            }
            Err(RecvTimeoutError::Timeout) => (),
        }
        owner.tick()?;
    }
    if let Some(session) = owner.session.as_ref() { session.token.cancel(); }
    // May block in C. Shutdown never joins this thread or promises a hard stop.
    let _ = owner.device.close();
    Ok(())
}

fn cap(support: Support, operation: &str) -> Value {
    let (state, evidence) = match support {
        Support::Unknown => ("unknown", "当前连接未验证"),
        Support::DriverAdvertised => ("driver_advertised", "驱动声明支持；仍需当前相机实际操作验证"),
        Support::Verified => ("verified", "当前运行时实际调用成功；不代表所有相机模式均可用"),
        Support::Unsupported => ("unsupported", "驱动未支持此操作"),
    };
    json!({"state":state,"reason":format!("{operation}：{evidence}")})
}
fn capabilities(caps: &DeviceCapabilities) -> Value {
    json!({"event_polling":cap(caps.events,"事件轮询（超时只验证读取接口，不证明物理快门）"),
        "original_download":cap(caps.original_download,"原片下载"),
        "remote_shutter":cap(caps.remote_trigger,"事件式远程快门"),"live_view":cap(caps.preview,"实时取景")})
}
fn unknown_capabilities() -> Value {
    json!({"event_polling":cap(Support::Unknown,"事件轮询"),"original_download":cap(Support::Unknown,"原片下载"),
        "remote_shutter":cap(Support::Unknown,"远程快门"),"live_view":cap(Support::Unknown,"实时取景")})
}
fn settings_value(value: SettingValue) -> String {
    match value { SettingValue::Text(v) => v, SettingValue::Number(v) => v.to_string(),
        SettingValue::Toggle(v) => if v { "是" } else { "否" }.into(), SettingValue::Timestamp(v) => v.to_string() }
}
fn terminal_unknown(result: &Value) -> bool { result["status"] == "unknown" }

impl Owner {
    fn enumerate(&mut self) -> Result<(), String> {
        self.refresh_devices = false;
        if self.driver_open || self.session.is_some() { return Ok(()); }
        let found = self.device.enumerate(&CancellationToken::default()).map_err(|e| e.to_string())?;
        let previous = self.host.snapshot()?;
        let mut map = HashMap::new();
        let mut rows = Vec::new();
        for device in found {
            let id = format!("usb-{:x}", Sha256::digest(format!("{}\0{}", device.model, device.port).as_bytes()));
            let mut row = json!({"device_id":id,"label":format!("{} ({})",device.model,device.port),
                "connected":true,"detected_by_runtime":true,"recording_format":"unknown",
                "recording_format_reason":"设置为厂商文本，未作不可靠推断；仅接收实际 RAW/JPEG，不承诺相机记录两种格式。",
                "capabilities":unknown_capabilities(),"settings":[]});
            // A snapshot read does not invalidate evidence for an uninterrupted
            // detected model/USB address. Missing/reappearing keys lose evidence;
            // every Start still reopens and re-verifies polling. USB addresses
            // are explicitly not physical serial identities.
            if let Some(old) = previous["devices"].as_array().and_then(|all| all.iter().find(|old| old["device_id"] == id)) {
                row["capabilities"] = old["capabilities"].clone(); row["settings"] = old["settings"].clone();
            }
            rows.push(row);
            map.insert(id, device);
        }
        self.devices = map;
        self.host.edit(false, |shared| {
            shared.snapshot["devices"] = json!(rows);
            shared.snapshot["availability"] = json!({"available":true,"reason":"已加载真实 Linux libgphoto2 适配器；请先验证选中设备"});
            Ok(())
        })?;
        Ok(())
    }
    fn update_device(&self, id: &str, caps: Option<DeviceCapabilities>, settings: Option<Vec<Value>>) -> Result<(), String> {
        self.host.edit(false, |shared| {
            if let Some(rows) = shared.snapshot["devices"].as_array_mut() {
                if let Some(row) = rows.iter_mut().find(|row| row["device_id"] == id) {
                    if let Some(caps) = caps { row["capabilities"] = capabilities(&caps); }
                    if let Some(settings) = settings { row["settings"] = json!(settings); }
                }
            }
            Ok(())
        })?;
        Ok(())
    }
    fn settings(&mut self) -> Option<Vec<Value>> {
        let token = self.session.as_ref().map(|s| s.token.clone()).unwrap_or_default();
        self.device.read_settings(&token).ok().map(|rows| rows.into_iter()
            .map(|row| json!({"label":row.label,"value":settings_value(row.value)})).collect())
    }
    fn command(&mut self, request: Request) -> Result<(), String> {
        match request.action.clone() {
            Action::ProbeDevice { device_id } => {
                if self.session.is_some() || self.flight.is_some() { return Err("请先结束原会话再验证设备".into()); }
                let device = self.devices.get(&device_id).ok_or("设备不在实际检测列表中")?.clone();
                let token = CancellationToken::default();
                let result = (|| {
                    self.device.open_selected(&device, &token).map_err(|e| e.to_string())?;
                    self.driver_open = true;
                    let settings = self.settings();
                    // Discarding a probe event never deletes the camera original
                    // and never pretends to import files before session admission.
                    self.device.wait_event(POLL, &token).map_err(|e| e.to_string())?;
                    let caps = self.device.capabilities().map_err(|e| e.to_string())?;
                    self.update_device(&device_id, Some(caps), settings)
                })();
                let closed = self.device.close().map_err(|e| e.to_string());
                self.driver_open = false;
                result?; closed?;
                self.host.settle(&request, true, false, None)
            }
            Action::Start { device_id, ingestion_target, destination, naming, import_format, preview_mode } => {
                if self.session.is_some() || self.flight.is_some() { return Err("原会话尚未结束；不会替换或转移工程".into()); }
                wire::validate_naming(&naming)?; wire::preview_mode(&preview_mode)?;
                if preview_mode != "keep_current" { return Err("跟随最新照片预览尚未接入；当前工程租约禁止自动切换编辑照片，请选择保持当前照片".into()); }
                if import_format != "raw_jpeg" { return Err("当前驱动记录格式未知，只允许接收实际 RAW/JPEG 全部原片".into()); }
                let (binding, target, directory, max_operations, generation, stage) = {
                    let shared = self.host.shared.lock().map_err(|_| "联机状态锁不可用")?;
                    let target = &shared.snapshot["ingestion_target"];
                    if target["available"] != true || target["project_id"] != ingestion_target.project_id
                        || target["path"] != ingestion_target.path { return Err("当前可见已保存工程与请求不符，未开始".into()); }
                    let binding = request.admitted_binding.clone().ok_or("缺少接受请求时可见的已保存工程完整绑定")?;
                    if shared.binding.as_ref() != Some(&binding) { return Err("排队期间已保存工程绑定变化，未自动采用新状态".into()); }
                    let device = shared.snapshot["devices"].as_array().and_then(|rows| rows.iter().find(|r| r["device_id"] == device_id)).ok_or("相机未检测")?;
                    if device["capabilities"]["event_polling"]["state"] != "verified"
                        || device["capabilities"]["original_download"]["state"] == "unsupported" {
                        return Err("请先实际验证设备事件；已明确不支持原片下载的设备不能开始".into());
                    }
                    let directory = shared.destinations.get(&destination.destination_id).cloned().ok_or("目录授权已失效，请用系统选择器重新选择")?;
                    if directory.path.to_str() != Some(destination.display_path.as_str()) { return Err("目录令牌与显示路径不符".into()); }
                    directory.writable()?;
                    let used = shared.snapshot["transfers"].as_array().map_or(0, Vec::len);
                    let budget = target["remaining_operations"].as_u64().unwrap_or(0).min((wire::MAX_TRANSFERS - used.min(wire::MAX_TRANSFERS)) as u64);
                    if budget == 0 || self.bytes >= wire::MAX_BYTES { return Err("宿主或工程接入额度已耗尽；不会丢弃回执或自动轮换工程".into()); }
                    let generation = shared.snapshot["session"]["generation"].as_u64().unwrap_or(0).checked_add(1).filter(|v| *v <= wire::MAX_SAFE).ok_or("会话代次已耗尽")?;
                    let stage = shared.ledger.directory.child(&format!("session-{}", storage::uuid()?))?;
                    (binding, target.clone(), directory, budget.min(64), generation, stage)
                };
                let session_id = storage::uuid()?;
                let token = CancellationToken::default();
                self.session = Some(Session { id:session_id.clone(),generation,device_id:device_id.clone(),binding:binding.clone(),
                    engine_id:None,destination:directory,stage,naming:naming.clone(),date:storage::utc_date()?,ordinal:0,
                    remaining:max_operations,max_operations,token:token.clone(),live:false,frame:0,last_frame:Instant::now() });
                self.host.edit(true, |shared| {
                    shared.cancel = token;
                    shared.snapshot["session"] = json!({"session_id":session_id,"generation":generation,"device_id":device_id,
                        "ingestion_target":{"project_id":target["project_id"],"path":target["path"],"name":target["name"]},
                        "phase":"starting","destination":destination,"naming":naming,"import_format":import_format,
                        "preview_mode":preview_mode,"live_view":"off"});
                    Ok(())
                })?;
                self.lease_ok = false;
                let id = storage::uuid()?;
                self.submit(Flight { id:id.clone(),operation:None,kind:FlightKind::Arm(request),
                    payload:json!({"cmd":"ingest_session","action":"arm","request_id":id,"owner":"tether","expected":binding,"max_operations":max_operations}) })
            }
            Action::Stop => {
                if self.stop.is_some() { return Err("原停止请求仍在等待驱动或工程终态".into()); }
                if self.session.is_none() {
                    return self.host.settle(&request, true, false, None);
                }
                self.stop = Some(request);
                self.close_driver()?;
                self.maybe_release()
            }
            Action::SetPreviewMode { preview_mode } => {
                wire::preview_mode(&preview_mode)?;
                if preview_mode != "keep_current" { return Err("跟随最新照片预览尚未接入；不会自动改变当前编辑照片".into()); }
                self.require_active()?;
                self.host.edit(true, |shared| { shared.snapshot["session"]["preview_mode"] = json!(preview_mode); Ok(()) })?;
                self.host.settle(&request, true, false, None)
            }
            Action::RetryTransfer { .. } => Err("此宿主不重试相机来源或已提交导入；请查询原操作。失败时保留原片和回执。".into()),
            Action::StopLiveView => {
                self.require_active()?;
                if let Some(session) = self.session.as_mut() { session.live = false; }
                self.host.edit(true, |shared| { shared.snapshot["session"]["live_view"] = json!("off"); Ok(()) })?;
                self.host.settle(&request, true, false, None)
            }
            Action::Capture | Action::StartLiveView => {
                self.require_active()?;
                if self.flight.is_some() || self.optional.is_some() { return Err("原传输尚未完成；不能触发另一操作".into()); }
                self.optional = Some(request);
                self.lease_serial += 1;
                self.lease_ok = false; self.next_read = true;
                Ok(())
            }
        }
    }
    fn require_active(&self) -> Result<(), String> {
        let snap = self.host.snapshot()?;
        if self.session.is_none() || !self.driver_open || snap["session"]["phase"] != "active" {
            return Err("会话当前不能接收或触发相机操作".into());
        }
        Ok(())
    }
    fn submit(&mut self, flight: Flight) -> Result<(), String> {
        if self.flight.is_some() { return Err("原引擎操作仍在进行或结果未知".into()); }
        let payload = flight.payload.clone();
        self.host.edit(true, |shared| {
            if shared.engine_records.len() >= 256 { return Err("引擎意图日志额度已满；不丢弃原操作".into()); }
            shared.engine_pending = payload.clone();
            shared.engine_records.insert(flight.id.clone(), json!({"request":payload,"receipt":null}));
            Ok(())
        })?;
        self.flight = Some(flight);
        self.last_observed = None;
        self.lease_serial += 1;
        self.lease_ok = false;
        let (cancelled_before_send, outcome) = {
            let shared = self.host.shared.lock().map_err(|_| "联机状态锁不可用")?;
            let cancelled = payload["action"] == "import" && (shared.snapshot["session"]["phase"] != "active"
                || shared.cancel.is_cancelled() || self.host.closing.load(Ordering::Acquire));
            // Admission is serialized with stop acceptance. No stop intent can
            // become durable between this check and the actual engine send.
            (cancelled, if cancelled { Ok(Value::Null) } else { crate::ingest_session_api::submit(&self.state, payload) })
        };
        if cancelled_before_send {
            self.host.edit(true, |shared| {
                if let Some(record) = shared.engine_records.get_mut(shared.engine_pending["request_id"].as_str().unwrap_or("")) {
                    record["cancelled_before_send"] = json!(true);
                }
                Ok(())
            })?;
            if let Some(Flight { kind:FlightKind::Import { transfer, .. }, .. }) = self.flight.take() {
                self.transfer_error(&transfer,"cancelled","停止在引擎发送之前生效；未提交新导入")?;
            }
            self.clear_engine_pending()?;
            return Ok(());
        }
        if let Err(error) = outcome {
            // Even a transport error is not evidence that a write was not sent.
            self.pause(&format!("引擎发送结果待核对，只查询原身份：{error}"), true)?;
        }
        self.next_read = true;
        Ok(())
    }
    fn pause(&mut self, error: &str, unknown: bool) -> Result<(), String> {
        self.lease_ok = false;
        if let Some(session) = self.session.as_mut() { session.live = false; }
        self.host.edit(true, |shared| {
            if shared.snapshot["session"].is_object() {
                if shared.snapshot["session"]["phase"] != "stopping" { shared.snapshot["session"]["phase"] = json!("error"); }
                shared.snapshot["session"]["error"] = json!(error);
                shared.snapshot["session"]["live_view"] = json!("off");
            }
            if let Some(Flight { kind:FlightKind::Import { transfer, .. }, .. }) = self.flight.as_ref() {
                if let Some(row) = transfer_mut(&mut shared.snapshot, transfer) {
                    if unknown { row["phase"] = json!("outcome_unknown"); }
                    row["error"] = json!(error); row["retryable"] = json!(false);
                }
            }
            if shared.snapshot["ingestion_target"].is_object() {
                shared.snapshot["ingestion_target"]["available"] = json!(false);
                shared.snapshot["ingestion_target"]["reason"] = json!(error);
            }
            Ok(())
        })?;
        Ok(())
    }
    fn tick(&mut self) -> Result<(), String> {
        let stop = { self.host.shared.lock().map_err(|_| "联机状态锁不可用")?.stop_intent.take() };
        if let Some(request) = stop {
            if let Err(error) = self.command(request.clone()) { self.host.settle(&request, false, true, Some(&error))?; }
        }
        if self.refresh_devices && self.session.is_none() { self.enumerate()?; }
        self.observe_flight()?;
        self.observe_read()?;
        if self.stop.is_some() { self.maybe_release()?; }
        if self.epoch_lost { return Ok(()); }
        let due = self.next_read || self.last_read.elapsed() >= READ_INTERVAL;
        if self.read.is_none() && due { self.begin_read()?; }
        let active = self.host.snapshot()?["session"]["phase"] == "active";
        let fresh = self.lease_checked.map_or(false, |time| time.elapsed() <= LEASE_FRESH);
        if active && self.lease_ok && fresh && self.flight.is_none() && self.stop.is_none() && self.optional.is_none() {
            self.poll_camera()?;
            if self.flight.is_none() { self.live_frame()?; }
        }
        Ok(())
    }
}
fn transfer_mut<'a>(snapshot: &'a mut Value, id: &str) -> Option<&'a mut Value> {
    snapshot["transfers"].as_array_mut()?.iter_mut().find(|row| row["transfer_id"] == id)
}

mod lease;

mod capture;
