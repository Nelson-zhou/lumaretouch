// SPDX-License-Identifier: GPL-3.0-or-later
//! Source-owned selection transport. Engine alone owns rasterization/history.
//! AUTHORED / UNRUN; query never resubmits an operation.
use std::{collections::{HashMap, HashSet}, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

const REQUEST_BYTES: usize = 2 * 1024 * 1024;
const RESULT_BYTES: usize = 128 * 1024 * 1024;
const STORE_BYTES: usize = 192 * 1024 * 1024;
struct Row { epoch: [u8;16], request: Value, result: Option<Value>, sequence: u64, retired: bool, mask: Option<(String,String)> }
#[derive(Default)]
struct Mailbox { rows: HashMap<String, Row>, sequence: u64, seen: HashSet<String> }
fn store() -> &'static Mutex<Mailbox> {
    static STORE: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(Mailbox::default()))
}
fn token(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control))
}
fn binding(value: &Value) -> bool {
    ["document_id", "source_uid", "ownership_token", "layer_id"].iter().all(|k| token(&value[*k]))
        && value["expected_revision"].as_u64().is_some_and(|v| v <= 9_007_199_254_740_991)
}
fn validate(request: &Value) -> Result<(), String> {
    if !request.is_object() || request["cmd"] != "creative_selection" || !token(&request["request_id"])
        || !token(&request["source_uid"]) || request.to_string().len() > REQUEST_BYTES {
        return Err("选区请求缺少有效身份或超过传输上限".into());
    }
    match request["action"].as_str() {
        Some("context") if binding(request) => Ok(()),
        Some("preview") if binding(&request["proof"]) && request["proof"]["source_uid"] == request["source_uid"]
            && request["recipe"].is_object()
            && matches!(request["mask_policy"].as_str(), Some("create"|"replace"|"union"|"subtract"|"intersect")) => Ok(()),
        Some("apply") if binding(&request["proof"]) && request["proof"]["source_uid"] == request["source_uid"]
            && token(&request["preview_token"]) && token(&request["ack"]) && request["reviewed"] == true => Ok(()),
        Some("cancel") if token(&request["target_request_id"]) => Ok(()),
        _ => Err("选区动作或完整所有权证明无效".into()),
    }
}
fn terminal(value: &Value) -> bool {
    matches!(value["status"].as_str(), Some("ready"|"applied"|"no_change"|"rejected"|"cancelled"))
        && value["outcome_unknown"] != true
}
pub(crate) fn read_only(command: &Value) -> bool {
    command["cmd"] == "creative_selection" && matches!(command["action"].as_str(), Some("context"|"preview"|"cancel"|"status"))
}
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    store().lock().map(|s| s.rows.get(id).is_some_and(|r| r.epoch == epoch)).unwrap_or(true)
}
pub(crate) fn blocks_mutation(epoch: [u8;16], command: &Value) -> Result<(),String> {
    let s = store().lock().map_err(|_| "选区回执锁不可用")?;
    let safe = read_only(command) || matches!(command["cmd"].as_str(), Some("hello"|"shutdown"))
        || command["cmd"] == "project_recovery"
        || (command["cmd"] == "project" && matches!(command["action"].as_str(), Some("open"|"create"|"state")));
    if s.rows.values().any(|r| r.epoch == epoch && !r.retired && r.request["action"] == "apply"
        && !r.result.as_ref().is_some_and(terminal)
        && !(command == &r.request)) && !safe {
        return Err("选区应用仍在处理或结果未知；请核对原操作或明确重新打开工程".into());
    }
    Ok(())
}
/// Validated markers alone may settle the generic native recovery fence.
pub(crate) fn receive(epoch: [u8;16], value: &Value) -> Option<Value> {
    if value["event"] != "creative_selection_result" { return None; }
    let id = value["request_id"].as_str()?;
    let mut s = store().lock().ok()?;
    let row = s.rows.get_mut(id)?;
    if row.epoch != epoch || row.retired || row.result.as_ref().is_some_and(terminal)
        || value["source_uid"] != row.request["source_uid"] || value["action"] != row.request["action"] { return None; }
    let status = value["status"].as_str()?;
    if !matches!(status, "ready"|"applied"|"no_change"|"rejected"|"cancelled"|"unknown"|"pending") { return None; }
    if row.request["action"] == "apply" && !matches!(status,"applied"|"no_change"|"rejected"|"pending"|"unknown") { return None; }
    if row.request["action"] != "apply" && matches!(status,"applied"|"no_change") { return None; }
    if matches!(status, "applied"|"no_change") && (row.request["action"] != "apply"
        || value["proof"] != row.request["proof"] || value["success"] != true
        || value["outcome_unknown"] != false || value["preview_token"] != row.request["preview_token"]
        || !token(&value["mask_id"]) || !value["mask_sha256"].as_str().is_some_and(|h|h.len()==64 && h.bytes().all(|c|c.is_ascii_digit() || (b'a'..=b'f').contains(&c)))
        || value["revision"].as_u64() != row.request["proof"]["expected_revision"].as_u64().and_then(|r|r.checked_add(u64::from(status=="applied")))) { return None; }
    if matches!(status,"applied"|"no_change") && !row.mask.as_ref().is_some_and(|(id,hash)|value["mask_id"]==id.as_str() && value["mask_sha256"]==hash.as_str()) { return None; }
    if row.request["action"]=="apply" && status=="rejected" && (value["proof"]!=row.request["proof"] || value["preview_token"]!=row.request["preview_token"]) { return None; }
    if status == "rejected" && (value["success"] != false || value["outcome_unknown"] != false) { return None; }
    if value.to_string().len() > RESULT_BYTES { return None; }
    row.result = Some(value.clone());
    if row.request["action"] == "apply" && terminal(value) { Some(value.clone()) } else { None }
}
pub(crate) fn project_reopened(_epoch: [u8;16], value: &Value) {
    if value["event"] != "project_opened" || !value["docs"].is_u64() { return; }
    if let Ok(mut s) = store().lock() {
        for row in s.rows.values_mut() {
            if !row.result.as_ref().is_some_and(terminal) {
                row.retired = true;
                row.result = Some(json!({"event":"creative_selection_result","request_id":row.request["request_id"],
                    "source_uid":row.request["source_uid"],"status":"unknown","success":false,"outcome_unknown":true,
                    "workspace_reopened":true,"message":"已明确重开工程；旧操作结果仍未知，当前工程以重新读取的状态为准。请核对，不会重发旧请求。"}));
            }
        }
    }
}
fn prune(s: &mut Mailbox) -> Result<(),String> {
    while s.rows.len() >= 64 || s.rows.values().map(|r| r.request.to_string().len() + r.result.as_ref().map(|v|v.to_string().len()).unwrap_or(0)).sum::<usize>() > STORE_BYTES {
        let oldest = s.rows.iter().filter(|(_,r)| r.request["action"] != "apply" && r.result.as_ref().is_some_and(terminal))
            .min_by_key(|(_,r)|r.sequence).map(|(id,_)|id.clone());
        if let Some(id) = oldest { s.rows.remove(&id); }
        else { return Err("选区回执容量已满，请先核对或释放已完成请求".into()); }
    }
    Ok(())
}
#[tauri::command]
pub(crate) fn creative_selection_request(state: State<'_,Arc<AppState>>, request: Value) -> Result<Value,String> {
    let id = request["request_id"].clone();
    match submit(state, request) {
        Ok(value) => Ok(value),
        Err(message) => {
            let retained = store().lock().map(|s|id.as_str().is_some_and(|key|s.rows.contains_key(key))).unwrap_or(true);
            if retained { Err(message) }
            else { Ok(json!({"requested":false,"request_id":id,"status":"rejected","message":message})) }
        }
    }
}
fn submit(state: State<'_,Arc<AppState>>, request: Value) -> Result<Value,String> {
    if let Err(message) = validate(&request) {
        return Ok(json!({"requested":false,"request_id":request["request_id"],"status":"rejected","message":message}));
    }
    let handle = state.engine.lock().map_err(|_| "引擎锁不可用")?.clone().filter(|h|h.is_alive()).ok_or("引擎未运行")?;
    let epoch = handle.epoch();
    let id = request["request_id"].as_str().ok_or("选区身份缺失")?.to_owned();
    {
        let mut s = store().lock().map_err(|_| "选区回执锁不可用")?;
        if s.seen.contains(&id) { return Err("选区请求已存在，请查询原请求，不会再次发送".into()); }
        if request["action"] == "cancel" {
            let original = request["target_request_id"].as_str().and_then(|key|s.rows.get(key)).ok_or("原选区读取请求不存在")?;
            if original.epoch != epoch || original.request["source_uid"] != request["source_uid"]
                || !matches!(original.request["action"].as_str(),Some("context"|"preview")) {
                return Err("仅可请求取消同一来源的原选区读取，应用不可伪装为取消".into());
            }
        }
        let mask = if request["action"] == "apply" {
            let review = s.rows.values().filter(|r|r.epoch==epoch && r.request["action"]=="preview")
                .filter_map(|r|r.result.as_ref()).map(|v|&v["review"])
                .find(|v|v["proof"]==request["proof"] && v["preview_token"]==request["preview_token"] && v["ack"]==request["ack"])
                .ok_or("原审核候选已丢失，未应用蒙版；请重新生成完整审核")?;
            Some((review["output_mask_id"].as_str().ok_or("审核蒙版身份无效")?.to_owned(),
                review["output_mask_sha256"].as_str().ok_or("审核蒙版摘要无效")?.to_owned()))
        } else { None };
        prune(&mut s)?;
        if s.seen.len() >= 8192 { return Err("选区请求身份预算已满，请保存并核对工程后重新启动应用".into()); }
        s.seen.insert(id.clone());
        s.sequence = s.sequence.checked_add(1).ok_or("选区序号耗尽")?;
        let sequence = s.sequence;
        s.rows.insert(id.clone(), Row{epoch,request:request.clone(),result:None,sequence,retired:false,mask});
    }
    let sent = if request["action"] == "cancel" { handle.cancel_creative_selection(&request) }
        else if request["action"] == "apply" { state.send_to_engine_at_epoch(request, epoch) }
        else { handle.send(request) };
    if let Err(error) = sent { return Err(format!("选区发送结果待核对，不会重发：{error}")); }
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn creative_selection_status(state: State<'_,Arc<AppState>>, request_id: String) -> Result<Value,String> {
    if !token(&json!(&request_id)) { return Err("选区请求身份无效".into()); }
    let epoch = state.engine.lock().map_err(|_| "引擎锁不可用")?.as_ref().filter(|h|h.is_alive()).map(|h|h.epoch());
    let s = store().lock().map_err(|_| "选区回执锁不可用")?;
    let Some(row) = s.rows.get(&request_id) else {return Ok(json!({"phase":"unknown","result":null}));};
    if !row.retired && !row.result.as_ref().is_some_and(terminal) && Some(row.epoch)!=epoch {
        return Ok(json!({"phase":"done","result":{"event":"creative_selection_result","request_id":request_id,
            "source_uid":row.request["source_uid"],"status":"unknown","message":"原引擎已结束，旧操作结果未知；请明确重新打开工程核对，不会向新引擎重发。"}}));
    }
    Ok(json!({"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result}))
}
#[tauri::command]
pub(crate) fn creative_selection_release(request_id: String) -> Result<(),String> {
    let mut s = store().lock().map_err(|_| "选区回执锁不可用")?;
    if s.rows.get(&request_id).is_some_and(|r|!r.retired && !r.result.as_ref().is_some_and(terminal)) {
        return Err("不能释放仍在处理或结果未知的选区操作".into());
    }
    s.rows.remove(&request_id); Ok(())
}
