//! Narrow epoch-bound export/preset owner mailbox. It never sends an ordinary
//! export/preset command around the ingestion lease guard.
use std::{collections::BTreeMap, sync::{Mutex, OnceLock}};
use serde_json::{json, Value};
use crate::AppState;

struct Entry { epoch: [u8; 16], request: Value, result: Option<Value>, delivered_read: bool }
fn entries() -> &'static Mutex<BTreeMap<String, Entry>> {
    static ENTRIES: OnceLock<Mutex<BTreeMap<String, Entry>>> = OnceLock::new();
    ENTRIES.get_or_init(|| Mutex::new(BTreeMap::new()))
}
pub fn epoch(state: &AppState) -> Result<[u8; 16], String> {
    state.engine.lock().map_err(|_| "引擎状态锁不可用")?.as_ref().map(|engine| engine.epoch()).ok_or_else(|| "引擎尚未运行".into())
}
pub fn supported(state: &AppState) -> bool {
    state.ready_caps.lock().map(|caps| caps["local_workflow_protocol"] == 1 || caps["workflow_owner_protocol"] == 1).unwrap_or(false)
}
/// Caller has already persisted this exact request and epoch. No retries here.
pub fn send(state: &AppState, request: Value, expected_epoch: [u8; 16]) -> Result<(), String> {
    if epoch(state)? != expected_epoch { return Err("引擎已变化；保留原请求，不重发".into()); }
    let id = request["request_id"].as_str().filter(|s| super::wire::identity(s)).ok_or("缺少工作流 owner 请求身份")?.to_owned();
    if request["cmd"] != "workflow_owner" || request["protocol"] != 1 || request.to_string().len() > 1024 * 1024
        || !matches!(request["action"].as_str(), Some("profile" | "preflight" | "execute" | "query" | "open_review")) {
        return Err("无效工作流 owner 请求".into());
    }
    {
        let mut rows = entries().lock().map_err(|_| "工作流 owner 回执锁不可用")?;
        if let Some(old) = rows.get(&id) {
            return if old.epoch == expected_epoch && old.request == request { Ok(()) }
                else { Err("工作流 owner 请求身份冲突；未发送".into()) };
        }
        // Only completed read-only envelopes may be dropped. Mutation receipts
        // and unknown results are retained for this process/epoch.
        rows.retain(|_, row| !(row.delivered_read && row.result.as_ref().is_some_and(|result|
            matches!(row.request["action"].as_str(), Some("profile" | "preflight" | "query")) && result["status"] == "readback")));
        let capacity = if request["action"] == "execute" { 1008 } else { 1024 };
        if rows.len() >= capacity { return Err("工作流 owner 回执容量已满；不会驱逐原操作".into()); }
        rows.insert(id.clone(), Entry { epoch: expected_epoch, request: request.clone(), result: None, delivered_read: false });
    }
    state.send_to_engine_at_epoch(request, expected_epoch).map_err(|error| format!("发送结果待核对：{error}；仅查询原请求 {id}"))
}
pub fn read(state: &AppState, id: &str) -> Result<Value, String> {
    let current = epoch(state).ok();
    let mut rows = entries().lock().map_err(|_| "工作流 owner 回执锁不可用")?;
    match rows.get_mut(id) {
        Some(row) if current == Some(row.epoch) => {
            if row.result.as_ref().is_some_and(|result| result["status"] == "readback") { row.delivered_read = true; }
            Ok(json!({"phase":if row.result.is_some() {"done"} else {"pending"},"result":row.result}))
        },
        _ => Ok(json!({"phase":"unknown","result":null,"reason":"原 owner 回执不在当前引擎代际；禁止重放"})),
    }
}
pub fn receive(epoch: [u8; 16], event: &Value) -> bool {
    if event["event"] != "workflow_owner_result" || event["protocol"] != 1 || event.to_string().len() > 2 * 1024 * 1024 { return false; }
    let Some(id) = event["request_id"].as_str() else { return false; };
    let Ok(mut rows) = entries().lock() else { return false; };
    let Some(row) = rows.get(id) else { return false; };
    if row.epoch != epoch || event["action"] != row.request["action"]
        || event["session_id"] != row.request["session_id"]
        || !matches!(event["status"].as_str(), Some("pending" | "readback" | "succeeded" | "failed" | "unknown")) { return false; }
    let mut settled = false;
    if event["receipt"].is_object() {
        let Ok(receipt) = serde_json::from_value::<lrt_local_workflow::ports::Receipt>(event["receipt"].clone()) else { return false; };
        let original = if row.request["action"] == "execute" { row }
            else if row.request["action"] == "query" {
                let Some(original) = row.request["original_request_id"].as_str().and_then(|id| rows.get(id)) else { return false; };
                if original.epoch != epoch || original.request["action"] != "execute"
                    || original.request["session_id"] != row.request["session_id"]
                    || original.request["command"]["identity"]["operation_id"] != row.request["operation_id"]
                    || event["status"] != "readback" { return false; }
                original
            } else { return false; };
        let Ok(command) = serde_json::from_value::<lrt_local_workflow::ports::Command>(original.request["command"].clone()) else { return false; };
        if !super::validation::valid(&command, &receipt) { return false; }
        if let Some(prior) = original.result.as_ref().filter(|value| value["receipt"].is_object()) {
            let Ok(prior) = serde_json::from_value::<lrt_local_workflow::ports::Receipt>(prior["receipt"].clone()) else { return false; };
            if super::validation::terminal(&prior) && prior != receipt { return false; }
        }
        if row.request["action"] == "execute" {
            let expected = match &receipt.result {
                lrt_local_workflow::ports::ReceiptResult::Pending { .. } => "pending",
                lrt_local_workflow::ports::ReceiptResult::Unknown { .. } => "unknown",
                lrt_local_workflow::ports::ReceiptResult::Failed { .. } => "failed", _ => "succeeded",
            };
            if event["status"] != expected { return false; }
            settled = super::validation::terminal(&receipt);
        }
    } else if row.request["action"] == "execute" {
        if event["status"] == "succeeded" { return false; }
        if event["dispatch_rejected"] == true {
            if event["status"] != "failed" || !event["error"].as_str().is_some_and(|error| !error.is_empty() && error.len() <= 8192)
                || row.result.as_ref().is_some_and(|prior| prior["receipt"].is_object()) { return false; }
            settled = true; // Actual owner explicitly proves no dispatch occurred.
        }
    }
    if let Some(prior) = &row.result {
        // A terminal receipt is immutable, while pending/unknown reads may
        // acquire real owner evidence. A conflicting completion stays fenced.
        if prior["receipt"].is_object() && matches!(prior["status"].as_str(), Some("succeeded" | "failed")) && prior != event { return false; }
    }
    rows.get_mut(id).expect("retained owner request").result = Some(event.clone());
    drop(rows);
    // Only verified original terminal receipts settle the original mutation.
    // A query's outer readback or a bare failed envelope is insufficient.
    if settled { crate::project_recovery_fence::observed(epoch, event); }
    true
}

pub fn read_only(request: &Value) -> bool {
    request["cmd"] == "workflow_owner" && matches!(request["action"].as_str(), Some("profile" | "preflight" | "query" | "open_review"))
}
