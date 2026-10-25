//! Native tether host. Driver objects never cross the dedicated owner thread.
//! All runtime/hardware acceptance fixtures are authored UNRUN.
mod wire;
#[cfg(target_os = "linux")] mod storage;
#[cfg(target_os = "linux")] mod worker;
#[cfg(all(test, target_os = "linux"))] mod tests_unrun;

use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;
use crate::AppState;

pub const EVENT: &str = "tether-capture://event";

#[cfg(target_os = "linux")]
mod runtime {
    use super::*;
    use std::{collections::{BTreeMap, HashMap}, sync::{atomic::{AtomicBool, Ordering}, mpsc::{self, SyncSender}, Mutex, OnceLock}};
    use tauri::{Emitter, Manager};
    use lrt_tether_capture::CancellationToken;
    use super::{storage::{Directory, Ledger}, wire::{Action, Request}};

    pub(super) enum Command { User(Request), Refresh, Shutdown }
    pub(super) struct Shared {
        pub snapshot: Value,
        pub requests: BTreeMap<String, (Request, Value)>,
        pub destinations: HashMap<String, Arc<Directory>>,
        pub binding: Option<Value>,
        pub engine_pending: Value,
        pub engine_records: BTreeMap<String, Value>,
        pub ledger: Ledger,
        pub recovery_blocked: bool,
        pub cancel: CancellationToken,
        pub stop_intent: Option<Request>,
    }
    impl Shared {
        pub fn pending(&mut self) {
            self.snapshot["pending_requests"] = json!(self.requests.values().filter(|(_, value)|
                value["phase"] != "done" || value["outcome_unknown"] == true).map(|(request, _)| request.pending()).collect::<Vec<_>>());
        }
        pub fn persist(&self) -> Result<(), String> {
            if self.recovery_blocked { return Err("原会话需要恢复核对；未覆盖其持久化日志".into()); }
            self.ledger.save(&json!({"schema":1,"host_id":self.snapshot["host_id"],
                "pending_requests":self.snapshot["pending_requests"],"session":self.snapshot["session"],
                "transfers":self.snapshot["transfers"],"engine_pending":self.engine_pending,
                "engine_records":self.engine_records,
                "requests":self.requests.values().map(|(request, receipt)| json!({"request":request,"receipt":receipt,
                    "admitted_binding":request.admitted_binding})).collect::<Vec<_>>() }))
        }
    }
    pub(super) struct Host {
        pub shared: Mutex<Shared>,
        pub tx: SyncSender<Command>,
        pub closing: AtomicBool,
        pub app: tauri::AppHandle,
    }
    impl Host {
        pub fn edit(&self, durable: bool, change: impl FnOnce(&mut Shared) -> Result<(), String>) -> Result<Value, String> {
            let snapshot = {
                let mut shared = self.shared.lock().map_err(|_| "联机会话状态锁不可用")?;
                let previous = shared.snapshot.clone();
                change(&mut shared)?;
                shared.pending();
                if shared.snapshot != previous {
                    let next = shared.snapshot["revision"].as_u64().unwrap_or(0).checked_add(1).filter(|v| *v <= wire::MAX_SAFE).ok_or("宿主修订已耗尽")?;
                    shared.snapshot["revision"] = json!(next);
                }
                if durable {
                    if let Err(error) = shared.persist() {
                        shared.cancel.cancel();
                        shared.snapshot["availability"] = json!({"available":false,"reason":format!("持久化失败，已暂停；结果需核对：{error}")});
                        if shared.snapshot["session"].is_object() {
                            shared.snapshot["session"]["phase"] = json!("error");
                            shared.snapshot["session"]["error"] = json!(&error);
                        }
                        return Err(error);
                    }
                }
                shared.snapshot.clone()
            };
            if !self.closing.load(Ordering::Acquire) {
                let _ = self.app.emit(EVENT, json!({"type":"snapshot","snapshot":snapshot}));
            }
            Ok(snapshot)
        }
        pub fn snapshot(&self) -> Result<Value, String> {
            Ok(self.shared.lock().map_err(|_| "联机会话状态锁不可用")?.snapshot.clone())
        }
        pub fn settle(&self, request: &Request, success: bool, unknown: bool, error: Option<&str>) -> Result<(), String> {
            self.edit(true, |shared| {
                let row = shared.requests.get_mut(&request.request_id).ok_or("原生请求身份丢失")?;
                if row.1["phase"] == "done" && row.1["outcome_unknown"] == false { return Ok(()); }
                row.1 = request.receipt(!unknown, unknown, success, error);
                Ok(())
            })?;
            Ok(())
        }
        pub fn receipt(&self, id: &str) -> Result<Value, String> {
            if id.is_empty() || id.len() > 128 || id.chars().any(char::is_control) { return Err("无效原生请求身份".into()); }
            let shared = self.shared.lock().map_err(|_| "联机会话状态锁不可用")?;
            Ok(match shared.requests.get(id) {
                Some((_, value)) => { let mut value = value.clone(); value["snapshot"] = shared.snapshot.clone(); value },
                None => Value::Null,
            })
        }
        pub fn enqueue(&self, mut request: Request) -> Result<Value, String> {
            let stop = matches!(&request.action, Action::Stop);
            {
                let mut shared = self.shared.lock().map_err(|_| "联机会话状态锁不可用")?;
                if let Some((previous, _)) = shared.requests.get(&request.request_id) {
                    if serde_json::to_value(previous).ok() != serde_json::to_value(&request).ok() { return Err("请求身份与原始参数冲突；未执行".into()); }
                    drop(shared); return self.receipt(&request.request_id); // Lookup, never replay.
                }
                let admission: Result<(), &str> = (|| {
                    if self.closing.load(Ordering::Acquire) || shared.recovery_blocked { return Err("宿主已关闭或原会话需要恢复核对"); }
                    if shared.requests.len() >= wire::MAX_REQUESTS { return Err("原生回执容量已满；不删除回执、不重发"); }
                    if !stop && shared.requests.len() >= wire::MAX_REQUESTS - 16 { return Err("普通请求额度已满；剩余额度预留停止和恢复核对"); }
                    let snap = &shared.snapshot;
                    if request.host_id != snap["host_id"].as_str().unwrap_or("")
                        || request.expected_revision != snap["revision"].as_u64().unwrap_or(u64::MAX)
                        || request.expected_session_id.as_deref() != snap["session"]["session_id"].as_str()
                        || request.expected_generation != snap["session"]["generation"].as_u64() {
                        return Err("宿主、修订或会话已变化；未执行，请读取状态后重新决定");
                    }
                    if !stop && (snap["availability"]["available"] != true
                        || shared.requests.values().any(|(_, r)| r["phase"] != "done" || r["outcome_unknown"] == true)) {
                        return Err("宿主不可用或原请求结果待核对；仅允许停止和查询");
                    }
                    if stop && !snap["session"].is_object() { return Err("没有可停止的会话"); }
                    if stop && shared.requests.values().any(|(r, receipt)| matches!(&r.action, Action::Stop)
                        && (receipt["phase"] != "done" || receipt["outcome_unknown"] == true)) {
                        return Err("原停止请求仍在等待终态；请查询原请求");
                    }
                    Ok(())
                })();
                if let Err(error) = admission {
                    let mut receipt = request.receipt(true, false, false, Some(error));
                    let rejection_limit = if stop { wire::MAX_REQUESTS } else { wire::MAX_REQUESTS - 16 };
                    if shared.requests.len() < rejection_limit && !shared.recovery_blocked {
                        shared.requests.insert(request.request_id.clone(), (request, receipt.clone()));
                        shared.pending();
                        shared.snapshot["revision"] = json!(shared.snapshot["revision"].as_u64().unwrap_or(0) + 1);
                        shared.persist()?;
                    }
                    receipt["snapshot"] = shared.snapshot.clone();
                    return Ok(receipt);
                }
                if matches!(&request.action, Action::Start { .. }) { request.admitted_binding = shared.binding.clone(); }
                shared.requests.insert(request.request_id.clone(), (request.clone(), request.receipt(false, false, false, None)));
                if stop && shared.snapshot["session"]["phase"] != "stopped" {
                    shared.snapshot["session"]["phase"] = json!("stopping");
                    shared.snapshot["session"]["live_view"] = json!("stopping");
                }
                if matches!(&request.action, Action::StopLiveView) && shared.snapshot["session"].is_object() {
                    shared.snapshot["session"]["live_view"] = json!("stopping");
                }
                shared.pending();
                shared.snapshot["revision"] = json!(shared.snapshot["revision"].as_u64().unwrap_or(0) + 1);
                // The stop signal is issued ONLY after its identity is durable.
                shared.persist()?;
                if stop { shared.stop_intent = Some(request.clone()); shared.cancel.cancel(); }
            }
            if stop { let _ = self.tx.try_send(Command::Refresh); }
            else if self.tx.try_send(Command::User(request.clone())).is_err() {
                self.settle(&request, false, false, Some("命令队列已满或宿主线程已停止；该请求未进入驱动"))?;
            }
            let snapshot = self.snapshot()?;
            let _ = self.app.emit(EVENT, json!({"type":"snapshot","snapshot":snapshot}));
            self.receipt(&request.request_id)
        }
    }
    fn slot() -> &'static Mutex<Option<Arc<Host>>> {
        static HOST: OnceLock<Mutex<Option<Arc<Host>>>> = OnceLock::new();
        HOST.get_or_init(|| Mutex::new(None))
    }
    pub(super) fn get(app: tauri::AppHandle, state: Arc<AppState>) -> Result<Arc<Host>, String> {
        let mut slot = slot().lock().map_err(|_| "联机宿主锁不可用")?;
        if let Some(host) = slot.as_ref() { return Ok(host.clone()); }
        let ledger = Ledger::open(&app.path().app_local_data_dir().map_err(|e| e.to_string())?)?;
        let blocked = ledger.recovery_needed();
        if !blocked { ledger.archive_completed()?; }
        let host_id = storage::uuid()?;
        let reason = if blocked { "上次联机会话或请求没有已核验的终态；保留私有暂存和原工程回执，禁止自动重放。请先核对原工程与导入结果。" }
            else { "正在读取真实设备和已保存工程；尚未触发快门" };
        let (tx, rx) = mpsc::sync_channel(8);
        let host = Arc::new(Host { shared: Mutex::new(Shared {
            snapshot: json!({"protocol_version":1,"host_id":host_id,"revision":0,
                "availability":{"available":false,"reason":reason},"ingestion_target":null,
                "devices":[],"session":null,"transfers":[],"pending_requests":[]}),
            requests:BTreeMap::new(),destinations:HashMap::new(),binding:None,engine_pending:Value::Null,engine_records:BTreeMap::new(),
            ledger,recovery_blocked:blocked,cancel:CancellationToken::default(),stop_intent:None,
        }), tx, closing:AtomicBool::new(false), app });
        if !blocked {
            let owner = host.clone();
            std::thread::Builder::new().name("tether-device-owner".into()).spawn(move || {
                if let Err(error) = super::worker::run(owner.clone(), state, rx) {
                    let _ = owner.edit(false, |shared| {
                        shared.cancel.cancel();
                        shared.snapshot["availability"] = json!({"available":false,"reason":error});
                        Ok(())
                    });
                }
            }).map_err(|e| e.to_string())?;
        }
        *slot = Some(host.clone());
        Ok(host)
    }
    pub(super) fn shutdown() {
        if let Ok(slot) = slot().lock() {
            if let Some(host) = slot.as_ref() {
                host.closing.store(true, Ordering::Release);
                if let Ok(shared) = host.shared.lock() { shared.cancel.cancel(); }
                let _ = host.tx.try_send(Command::Shutdown);
            }
        }
    }
}

#[tauri::command]
pub(crate) fn tether_capture_state(app: tauri::AppHandle, state: State<'_, Arc<AppState>>) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { let host = runtime::get(app, state.inner().clone())?; let _ = host.tx.try_send(runtime::Command::Refresh); host.snapshot() }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state); Ok(json!({"protocol_version":1,"host_id":"unsupported-platform","revision":0,
        "availability":{"available":false,"reason":"原生有线拍摄适配器仅支持 Linux；未连接相机"},
        "ingestion_target":null,"devices":[],"session":null,"transfers":[],"pending_requests":[]})) }
}
#[tauri::command]
pub(crate) fn tether_capture_request(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { runtime::get(app, state.inner().clone())?.enqueue(wire::Request::parse(request)?) }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, request); Err("当前平台没有原生相机适配器".into()) }
}
#[tauri::command]
pub(crate) fn tether_capture_receipt(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { runtime::get(app, state.inner().clone())?.receipt(&request_id) }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, request_id); Ok(Value::Null) }
}
/// Called by the application adapter only after the actual system folder picker.
/// The returned token, never a later renderer-supplied path, authorizes imports.
#[tauri::command]
pub(crate) fn tether_capture_destination(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, path: String) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    {
        let host = runtime::get(app, state.inner().clone())?;
        let directory = Arc::new(storage::Directory::open(std::path::Path::new(&path))?);
        directory.writable()?;
        if path == "/" { return Err("不能选择文件系统根目录".into()); }
        let token = storage::uuid()?;
        let mut shared = host.shared.lock().map_err(|_| "联机会话状态锁不可用")?;
        if shared.destinations.len() >= 16 { return Err("目录授权容量已满；不会忘记旧会话的授权".into()); }
        shared.destinations.insert(token.clone(), directory);
        Ok(json!({"destination_id":token,"display_path":path}))
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, path); Err("当前平台没有原生相机适配器".into()) }
}
/// Cooperative cancellation only; never joins or reports a blocked C driver stopped.
pub(crate) fn shutdown() {
    #[cfg(target_os = "linux")] runtime::shutdown();
}
