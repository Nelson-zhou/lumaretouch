//! Document view metadata has its own receipts, never pixel-edit invalidation.
use std::{collections::{HashMap, HashSet}, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

const MAX_BYTES: usize = 64 * 1024;
const MAX_RECEIPTS: usize = 256;
const MAX_REVISION: u64 = 9_007_199_254_740_991;
struct Receipt { epoch: [u8; 16], request: Value, result: Option<Value>, sequence: u64 }
#[derive(Default)]
struct Store { rows: HashMap<String, Receipt>, sequence: u64 }
fn receipts() -> &'static Mutex<Store> {
    static STORE: OnceLock<Mutex<Store>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(Store::default()))
}
fn identity(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|c| c.is_ascii_alphanumeric() || b"-_.:".contains(&c)))
}
fn document_identity(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 256)
}
fn validate_state(value: &Value) -> bool {
    let Some(object) = value.as_object() else { return false; };
    if object.len() != 2 || !value["visible"].is_boolean() { return false; }
    let Some(lines) = value["lines"].as_array() else { return false; };
    if lines.len() > 128 { return false; }
    let mut ids = HashSet::new();
    lines.iter().all(|line| line.as_object().is_some_and(|row| row.len() == 3)
        && identity(&line["id"]) && ids.insert(line["id"].as_str().unwrap_or_default())
        && matches!(line["axis"].as_str(), Some("horizontal" | "vertical"))
        && line["position"].as_f64().is_some_and(|p| p.is_finite() && (0.0..=1.0).contains(&p)))
}
fn validate(request: &Value) -> Result<(), String> {
    if request.to_string().len() > MAX_BYTES { return Err("参考线请求超过大小上限".into()); }
    let object = request.as_object().ok_or("参考线请求必须是对象")?;
    if request["cmd"] != "canvas_guides" || !identity(&request["request_id"]) {
        return Err("无效参考线命令或请求身份".into());
    }
    let action = request["action"].as_str().ok_or("缺少参考线动作")?;
    if !matches!(action, "state" | "set" | "undo" | "redo") { return Err("未知参考线动作".into()); }
    if object.keys().any(|key| !matches!(key.as_str(), "cmd" | "action" | "request_id" | "document_id" | "workspace" | "revision" | "geometry" | "load_id")
        && !(action == "set" && key == "state")) { return Err("参考线命令包含未知字段".into()); }
    if action != "state" && (!document_identity(&request["document_id"]) || !identity(&request["workspace"]) || !identity(&request["load_id"])
        || !request["revision"].as_u64().is_some_and(|r| r <= MAX_REVISION)) {
        return Err("参考线修改缺少文档、工程或视图修订栅栏".into());
    }
    if action == "set" && !validate_state(&request["state"]) { return Err("无效参考线状态".into()); }
    if (action != "state" || object.contains_key("geometry")) && !request["geometry"].as_str().is_some_and(|v|
        !v.is_empty() && v.len() <= 20 && v.bytes().all(|c| c.is_ascii_digit()) && v.parse::<u64>().is_ok_and(|n| n > 0)) {
        return Err("无效画布几何身份".into());
    }
    Ok(())
}

pub(crate) fn receive(state: &AppState, epoch: [u8; 16], value: &Value) {
    if value["event"] != "canvas_guides_result" || value.to_string().len() > MAX_BYTES
        || !value["success"].is_boolean() { return; }
    let Some(id) = value["request_id"].as_str() else { return; };
    let accepted = if let Ok(mut store) = receipts().lock() {
        if let Some(row) = store.rows.get_mut(id) {
            if row.epoch == epoch && row.result.is_none() && row.request["action"] == value["action"] {
                row.result = Some(value.clone()); true
            } else { false }
        } else { false }
    } else { false };
    if !accepted { return; }
    // Update only guide metadata, without note_doc's pixel-history clean flag.
    // Old receipts can never paint another document or rewind a newer view.
    let guides = &value["canvas_guides"];
    if guides["protocol"] != 1 || guides["view_only"] != true { return; }
    if let Ok(mut report) = state.doc_report.lock() {
        if let Some(doc) = report.as_mut().and_then(|v| v.get_mut("doc_state")) {
            let old = &doc["canvas_guides"];
            if doc["document_id"] == guides["load_id"] && old["document_id"] == guides["document_id"]
                && old["workspace"] == guides["workspace"]
                && guides["revision"].as_u64().zip(old["revision"].as_u64()).is_some_and(|(next, prior)| next >= prior) {
                doc["canvas_guides"] = guides.clone();
                if let Ok(mut revision) = state.doc_rev.lock() { *revision += 1; }
            }
        }
    }
}

#[tauri::command]
pub(crate) fn canvas_guides_request(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    validate(&request)?;
    let id = request["request_id"].as_str().ok_or("缺少请求身份")?.to_owned();
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = engine.as_ref().ok_or("引擎未启动")?.epoch();
    {
        let mut store = receipts().lock().map_err(|_| "参考线回执锁不可用")?;
        store.rows.retain(|_, row| row.epoch == epoch);
        if let Some(prior) = store.rows.get(&id) {
            if prior.request == request { return Ok(json!({"request_id":id,"requested":true,"replayed":true})); }
            return Err("参考线请求身份冲突，未发送".into());
        }
        if store.rows.len() >= MAX_RECEIPTS {
            let oldest = store.rows.iter().filter(|(_, row)| row.result.is_some())
                .min_by_key(|(_, row)| row.sequence).map(|(id, _)| id.clone());
            if let Some(oldest) = oldest { store.rows.remove(&oldest); }
            else { return Err("参考线待确认请求已满，请先查询原请求".into()); }
        }
        store.sequence = store.sequence.checked_add(1).ok_or("参考线请求序号耗尽")?;
        let sequence = store.sequence;
        store.rows.insert(id.clone(), Receipt { epoch, request: request.clone(), result: None, sequence });
    }
    drop(engine);
    // Keep uncertain requests. Every mutation is additionally revision-fenced;
    // even an evicted old request cannot apply its undo/set twice.
    state.send_to_engine(request).map_err(|error| format!("参考线发送结果待确认：{error}；请查询原请求"))?;
    Ok(json!({"request_id":id,"requested":true}))
}

#[tauri::command]
pub(crate) fn canvas_guides_status(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if !identity(&Value::String(request_id.clone())) { return Err("无效请求身份".into()); }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = engine.as_ref().filter(|handle| handle.is_alive()).map(|handle| handle.epoch());
    let store = receipts().lock().map_err(|_| "参考线回执锁不可用")?;
    let Some(row) = store.rows.get(&request_id).filter(|row| Some(row.epoch) == epoch) else {
        return Ok(json!({"phase":"unknown","result":null}));
    };
    Ok(json!({"phase":if row.result.is_some() {"done"} else {"pending"},"result":row.result}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_normalized_state_and_mutation_fences() {
        let mut request = json!({"cmd":"canvas_guides","action":"set","request_id":"r-1",
            "document_id":"doc","workspace":"epoch","load_id":"101","geometry":"123","revision":0,
            "state":{"visible":true,"lines":[{"id":"g-1","axis":"vertical","position":0.25}]}});
        assert!(validate(&request).is_ok());
        request["state"]["lines"][0]["position"] = json!(1.01);
        assert!(validate(&request).is_err());
        request["state"]["lines"][0]["position"] = json!(true);
        assert!(validate(&request).is_err());
        request["state"]["lines"][0]["position"] = json!(0.0);
        request["revision"] = json!(true);
        assert!(validate(&request).is_err());
    }
    #[test]
    fn duplicate_ids_and_unknown_fields_are_rejected() {
        assert!(!validate_state(&json!({"visible":true,"lines":[
            {"id":"same","axis":"horizontal","position":0.0},
            {"id":"same","axis":"vertical","position":1.0}]})));
        assert!(!validate_state(&json!({"visible":true,"lines":[],"recipe":{}})));
        assert!(validate(&json!({"cmd":"canvas_guides","action":"state","request_id":"r"})).is_ok());
    }
}
