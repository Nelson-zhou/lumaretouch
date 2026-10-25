//! Local workflow native v1 host. Built-in module, not a runtime plug-in API.
//! Runtime/build/integration acceptance is deliberately UNRUN for this change.
mod wire;
mod validation;
mod review;
mod transport;
#[cfg(target_os = "linux")] mod storage;
#[cfg(target_os = "linux")] mod data;
#[cfg(target_os = "linux")] mod ingestion;
#[cfg(target_os = "linux")] mod view;
#[cfg(target_os = "linux")] mod runtime;
#[cfg(all(test, target_os = "linux"))] mod tests_unrun;

use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

pub(crate) fn receive(epoch: [u8; 16], event: &Value) -> bool { transport::receive(epoch, event) }
pub(crate) fn read_only(request: &Value) -> bool { transport::read_only(request) }

#[cfg(target_os = "linux")]
fn slot() -> &'static std::sync::Mutex<Option<Arc<runtime::Host>>> {
    static HOST: std::sync::OnceLock<std::sync::Mutex<Option<Arc<runtime::Host>>>> = std::sync::OnceLock::new();
    HOST.get_or_init(|| std::sync::Mutex::new(None))
}
#[cfg(target_os = "linux")]
fn host(app: tauri::AppHandle, state: Arc<AppState>) -> Result<Arc<runtime::Host>, String> {
    use tauri::Manager;
    let mut slot = slot().lock().map_err(|_| "工作流宿主锁不可用")?;
    if let Some(host) = slot.as_ref() { return Ok(host.clone()); }
    let (store, previous) = storage::Store::open(&app.path().app_local_data_dir().map_err(|e| e.to_string())?)?;
    let public = Arc::new(std::sync::Mutex::new(runtime::Public::default()));
    let closing = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let runtime = runtime::Runtime::create(store, previous, state, public.clone(), closing.clone())?;
    let (tx, rx) = std::sync::mpsc::sync_channel(16);
    let host = Arc::new(runtime::Host { tx, public, closing });
    std::thread::Builder::new().name("local-workflow-owner".into()).spawn(move || runtime.run(rx)).map_err(|e| e.to_string())?;
    *slot = Some(host.clone());
    Ok(host)
}

#[tauri::command]
pub(crate) fn local_workflow_workspace(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, refresh_catalogue: Option<bool>) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    {
        let host = host(app, state.inner().clone())?;
        let message = if refresh_catalogue == Some(true) { runtime::Message::RefreshCatalogue } else { runtime::Message::Refresh };
        let _ = host.tx.try_send(message);
        let shared = host.public.lock().map_err(|_| "工作流状态锁不可用")?;
        if shared.workspace.is_null() { return Err("工作流宿主正在读取持久化状态，请稍后刷新".into()); }
        Ok(shared.workspace.clone())
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, refresh_catalogue); Ok(json!({"port_version":1,"host_scope_id":"unsupported-local-workflow-platform","workspace_revision":0,
        "capabilities":{"available":false,"can_save":false,"can_run":false,"can_open_review":false,
            "reason":"本地工作流原生持久化适配器目前仅支持 Linux","error_policies":{}},
        "definitions":[],"runs":[],"active_run":null,"lease":null,"unresolved_requests":[]})) }
}
#[tauri::command]
pub(crate) fn local_workflow_definition(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, workflow_id: String) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { let host = host(app, state.inner().clone())?; let shared = host.public.lock().map_err(|_| "工作流状态锁不可用")?;
        shared.definitions.get(&workflow_id).cloned().ok_or_else(|| "找不到已保存定义".into()) }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, workflow_id); Err("当前平台不支持本地工作流持久化".into()) }
}
#[tauri::command]
pub(crate) async fn local_workflow_submit(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, input: Value) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    {
        let request = wire::Request::parse(input)?;
        let host = host(app, state.inner().clone())?;
        tauri::async_runtime::spawn_blocking(move || {
            let (tx, rx) = std::sync::mpsc::sync_channel(1);
            host.tx.try_send(runtime::Message::Submit(request, tx)).map_err(|_| "宿主队列已满或已关闭；没有入队")?;
            rx.recv_timeout(std::time::Duration::from_secs(20)).map_err(|_| "原请求结果尚未返回；只能查询原身份，不要重新提交".to_string())?
        }).await.map_err(|error| error.to_string())?
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, input); Err("当前平台不支持本地工作流执行".into()) }
}
#[tauri::command]
pub(crate) async fn local_workflow_preflight(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, input: Value) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    {
        if input.to_string().len() > 512 * 1024 { return Err("检测请求过大".into()); }
        let input: wire::PreflightInput = serde_json::from_value(input).map_err(|e| e.to_string())?;
        let host = host(app, state.inner().clone())?;
        tauri::async_runtime::spawn_blocking(move || {
            let (tx, rx) = std::sync::mpsc::sync_channel(1);
            host.tx.try_send(runtime::Message::Preflight(input, tx)).map_err(|_| "宿主队列已满或已关闭；没有启动检测")?;
            rx.recv_timeout(std::time::Duration::from_secs(20)).map_err(|_| "检测尚未完成；没有启动工作流".to_string())?
        }).await.map_err(|error| error.to_string())?
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, input); Err("当前平台不支持本地工作流检测".into()) }
}
#[tauri::command]
pub(crate) fn local_workflow_request(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { let host = host(app, state.inner().clone())?; let shared = host.public.lock().map_err(|_| "工作流状态锁不可用")?;
        shared.receipts.get(&request_id).cloned().ok_or_else(|| "找不到原请求记录；不能以新身份重发".into()) }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, request_id); Err("当前平台不支持本地工作流查询".into()) }
}
#[tauri::command]
pub(crate) fn local_workflow_run(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, run_id: String) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    { let host = host(app, state.inner().clone())?; let shared = host.public.lock().map_err(|_| "工作流状态锁不可用")?;
        shared.runs.get(&run_id).cloned().ok_or_else(|| "找不到原运行记录".into()) }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, run_id); Err("当前平台不支持本地工作流查询".into()) }
}
#[tauri::command]
pub(crate) async fn local_workflow_review_image(app: tauri::AppHandle, state: State<'_, Arc<AppState>>, input: Value) -> Result<Value, String> {
    #[cfg(target_os = "linux")]
    {
        if input.to_string().len() > 8192 { return Err("审核图片请求过大".into()); }
        let input: wire::ReviewImageInput = serde_json::from_value(input).map_err(|error| error.to_string())?;
        let host = host(app, state.inner().clone())?;
        tauri::async_runtime::spawn_blocking(move || {
            let (tx, rx) = std::sync::mpsc::sync_channel(1);
            host.tx.try_send(runtime::Message::ReviewImage(input, tx)).map_err(|_| "审核读取队列已满或关闭")?;
            rx.recv_timeout(std::time::Duration::from_secs(20)).map_err(|_| "审核图片读取尚未完成；没有提交批准".to_string())?
        }).await.map_err(|error| error.to_string())?
    }
    #[cfg(not(target_os = "linux"))]
    { let _ = (app, state, input); Err("当前平台不支持本地工作流审核".into()) }
}
pub(crate) fn shutdown() {
    #[cfg(target_os = "linux")]
    if let Ok(slot) = slot().lock() {
        if let Some(host) = slot.as_ref() {
            host.closing.store(true, std::sync::atomic::Ordering::Release);
            let _ = host.tx.try_send(runtime::Message::Shutdown);
        }
    }
}
