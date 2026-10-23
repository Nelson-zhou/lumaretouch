//! Retained virtual-copy receipts. Submission acceptance is never a commit receipt.
use std::{collections::{HashMap, HashSet}, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

const MAX_BYTES: usize = 4 * 1024 * 1024;
const MAX_RECEIPTS: usize = 512;
const MAX_WRITE_RECEIPTS: usize = 256;
struct Receipt { epoch: [u8; 16], request: Value, result: Option<Value> }
fn receipts() -> &'static Mutex<HashMap<String, Receipt>> {
    static STORE: OnceLock<Mutex<HashMap<String, Receipt>>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(HashMap::new()))
}
fn write_ids() -> &'static Mutex<HashSet<String>> {
    static IDS: OnceLock<Mutex<HashSet<String>>> = OnceLock::new();
    IDS.get_or_init(|| Mutex::new(HashSet::new()))
}
fn identity(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 256)
}
fn mutation(action: &str) -> bool { matches!(action, "create" | "trash" | "restore") }

pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    if value["event"] != "virtual_copy_result" || value.to_string().len() > MAX_BYTES
        || !value["success"].is_boolean() { return; }
    let Some(id) = value["request_id"].as_str() else { return; };
    if let Ok(mut store) = receipts().lock() {
        if let Some(row) = store.get_mut(id) {
            // First terminal reply wins; late prior-engine events never satisfy a new request.
            if row.epoch == epoch && row.result.is_none() { row.result = Some(value.clone()); }
        }
    }
}

#[tauri::command]
pub(crate) fn virtual_copy_request(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    if request.to_string().len() > MAX_BYTES { return Err("虚拟副本请求超过大小上限".into()); }
    if request["cmd"] != "virtual_copy" { return Err("无效虚拟副本命令".into()); }
    let action = request["action"].as_str().ok_or("缺少动作")?;
    if !matches!(action, "state" | "create" | "trash" | "restore" | "query") { return Err("未知虚拟副本动作".into()); }
    if !identity(&request["request_id"]) { return Err("缺少请求身份".into()); }
    let id = request["request_id"].as_str().ok_or("缺少请求身份")?.to_owned();
    if action != "state" && !identity(&request["workspace"]) { return Err("缺少工程会话身份".into()); }
    if action == "query" && !identity(&request["operation_id"]) { return Err("缺少原操作身份".into()); }
    if mutation(action) {
        if request["operation_id"] != request["request_id"] { return Err("操作身份必须等于请求身份".into()); }
        let ids = request["document_ids"].as_array().filter(|ids| !ids.is_empty()).ok_or("请选择文档")?;
        let mut unique = HashSet::new();
        if ids.iter().any(|id| !identity(id) || !unique.insert(id.as_str().unwrap_or_default())) {
            return Err("文档身份无效或重复".into());
        }
        let revisions = request["expected_revisions"].as_object().ok_or("缺少文档修订栅栏")?;
        if revisions.iter().any(|(id, revision)| id.is_empty() || id.len() > 256 || revision.as_u64().is_none())
            || unique.iter().any(|id| !revisions.contains_key(*id)) {
            return Err("文档修订栅栏无效或不完整".into());
        }
    }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let handle = engine.as_ref().ok_or("引擎未启动")?;
    let epoch = handle.epoch();
    {
        let mut store = receipts().lock().map_err(|_| "虚拟副本回执锁不可用")?;
        if let Some(prior) = store.get(&id) {
            if prior.epoch == epoch && prior.request == request {
                return Ok(json!({"request_id": id, "requested": true, "replayed": true}));
            }
            return Err("请求身份冲突，未发送".into());
        }
        // Evict only finished readbacks. Writes, including uncertain or failed writes,
        // are never silently forgotten and never sent again under the same identity.
        store.retain(|_, row| row.epoch == epoch && (mutation(row.request["action"].as_str().unwrap_or("")) || row.result.is_none()));
        if mutation(action) && store.values().filter(|row| mutation(row.request["action"].as_str().unwrap_or(""))).count() >= MAX_WRITE_RECEIPTS {
            return Err("虚拟副本写入回执已满；仍可查询核对，请保存工程后重启".into());
        }
        if store.len() >= MAX_RECEIPTS { return Err("虚拟副本回执已满；请先核对并保存工程后重启".into()); }
        if mutation(action) {
            let mut ids = write_ids().lock().map_err(|_| "操作身份锁不可用")?;
            if ids.contains(&id) { return Err("此操作身份已使用，请查询原操作，不会重发".into()); }
            if ids.len() >= 4096 { return Err("本次应用操作身份容量已满，请保存并重启应用".into()); }
            ids.insert(id.clone());
        }
        store.insert(id.clone(), Receipt { epoch, request: request.clone(), result: None });
    }
    drop(engine);
    // The native edit dispatcher preserves ordering with pending edits. A transport
    // error does not establish whether an operation ran, so retain the original ID.
    state.send_to_engine(request).map_err(|error| format!("发送结果待确认：{error}；请查询原请求，勿重发"))?;
    Ok(json!({"request_id": id, "requested": true}))
}

#[tauri::command]
pub(crate) fn virtual_copy_status(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 256 { return Err("无效请求身份".into()); }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = engine.as_ref().map(|handle| handle.epoch());
    let store = receipts().lock().map_err(|_| "虚拟副本回执锁不可用")?;
    let Some(row) = store.get(&request_id) else { return Ok(json!({"phase": "unknown", "result": null})); };
    if epoch != Some(row.epoch) {
        return Ok(json!({"phase": "unknown", "result": null, "reason": "engine generation changed; query original operation"}));
    }
    Ok(json!({"phase": if row.result.is_some() { "done" } else { "pending" }, "result": row.result}))
}
