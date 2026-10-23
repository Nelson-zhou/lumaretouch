// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded people commands and correlated receipts. Acceptance is not completion.
use serde_json::{json, Value};
use std::sync::{Mutex, OnceLock};
use crate::receipt_host::{ReceiptHost, ReceiptKind};

const PEOPLE_ACTIONS: &[&str] = &["patch", "link", "group", "face_status", "manual_add", "create_person", "select", "target", "analyse_face", "resolve_legacy", "eye_light_reference", "eye_light_review"];
fn text(value: &Value) -> bool { value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128) }
fn revision(value: &Value) -> bool { value.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
fn digest(value: &Value) -> bool {
    value.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn target(value: &Value) -> bool {
    if !value.as_object().is_some_and(|m| m.len() == 3) { return false; }
    match value["scope"].as_str() {
        Some("all_people") => digest(&value["target_id"]) && value["face_ref"].is_null(),
        Some("group" | "person") => text(&value["target_id"]) && value["face_ref"].is_null(),
        Some("face") => {
            let face = &value["face_ref"];
            face.as_object().is_some_and(|m| m.len() == 3) && digest(&face["asset_sha256"])
                && text(&face["face_instance_id"]) && face["face_instance_id"] == value["target_id"]
                && revision(&face["analysis_revision"])
        }
        _ => false,
    }
}
/// Legacy portrait routes carry the same captured fences, without a second request ID.
pub(crate) fn valid_context(value: &Value) -> bool {
    value.as_object().is_some_and(|m| m.len() == 6)
        && ["document_id", "document_epoch"].iter().all(|key| text(&value[*key]))
        && ["document_revision", "state_revision", "association_revision"].iter().all(|key| revision(&value[*key]))
        && target(&value["target"])
}
pub(crate) fn add_context(command: &mut Value, context: Option<Value>) -> Result<(), String> {
    if let Some(value) = context {
        if !valid_context(&value) { return Err("人物编辑范围或版本信息无效".into()); }
        command["people_context"] = value;
    }
    Ok(())
}
struct PeopleKind;
impl ReceiptKind for PeopleKind {
    const NAME: &'static str = "people";
    const ACTIONS: &'static [&'static str] = PEOPLE_ACTIONS;
    fn valid(value: &Value, document: Option<&str>) -> bool {
        if value["protocol"] != 1 || value["document_id"].as_str() != document
            || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean() { return false; }
        if value["success"] != true { return value["error"].is_string(); }
        let people = &value["doc_state"]["people"];
        let binding = &people["binding"];
        value["outcome_unknown"] == false && binding["document_id"].as_str() == document
            && text(&binding["document_epoch"]) && revision(&binding["document_revision"])
            && digest(&binding["asset_sha256"]) && revision(&people["revision"])
            && revision(&people["association_revision"])
    }
    fn valid_request(_: &str, document: Option<&str>) -> bool { document.is_some_and(|s| !s.is_empty() && s.len() <= 128) }
    fn decorate_failure(value: &mut Value, document: Option<&str>) {
        value["protocol"] = json!(1); value["document_id"] = json!(document);
    }
}
#[derive(Default)]
struct Mailbox { epoch: [u8; 16], host: ReceiptHost<PeopleKind> }
fn mailbox() -> &'static Mutex<Mailbox> {
    static BOX: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    BOX.get_or_init(|| Mutex::new(Mailbox::default()))
}
pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    if let Ok(mut mailbox) = mailbox().lock() { mailbox.host.receive(epoch, value); }
}
pub(crate) fn ended(epoch: [u8; 16]) {
    if let Ok(mut mailbox) = mailbox().lock() { mailbox.host.ended(epoch); }
}
pub(crate) fn enqueue(handle: &crate::engine::EngineHandle, mut command: Value) -> Result<(), String> {
    let epoch = command.as_object_mut().ok_or("人物命令无效")?.remove("host_epoch").ok_or("人物命令缺少引擎身份")?;
    if epoch.as_str() != Some(crate::frame_identity::hex(handle.epoch()).as_str()) {
        return Err("引擎已变化，未向新引擎重发人物修改".into());
    }
    handle.send(command)
}
#[tauri::command]
pub(crate) fn people(state: tauri::State<'_, std::sync::Arc<crate::AppState>>, request: Value) -> Result<Value, String> {
    let fields = request.as_object().ok_or("人物请求必须是对象")?;
    let id = request["request_id"].as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or("人物请求身份无效")?;
    if request["action"] == "status" {
        if fields.len() != 2 { return Err("人物查询字段无效".into()); }
        return Ok(mailbox().lock().map_err(|_| "人物结果锁失败")?.host.status(id));
    }
    if fields.len() != 9 || !request["action"].as_str().is_some_and(|a| PEOPLE_ACTIONS.contains(&a))
        || !request["payload"].is_object() || request.to_string().len() > 256 * 1024 {
        return Err("人物命令字段或长度无效".into());
    }
    let mut context = request.clone();
    for key in ["request_id", "action", "payload"] { context.as_object_mut().unwrap().remove(key); }
    if !valid_context(&context) { return Err("人物命令缺少精确文档、分析和范围版本".into()); }
    let epoch = {
        let guard = state.engine.lock().map_err(|_| "引擎锁失败")?;
        let handle = guard.as_ref().ok_or("引擎不可用，人物修改未提交")?;
        if !handle.is_alive() { return Err("引擎已退出，人物修改未提交".into()); }
        handle.epoch()
    };
    if state.ready_caps.lock().map_err(|_| "能力锁失败")?["people_protocol"] != 1 {
        return Err("引擎未提供确认式人物协议".into());
    }
    {
        let mut mailbox = mailbox().lock().map_err(|_| "人物结果锁失败")?;
        if mailbox.epoch != epoch { mailbox.epoch = epoch; mailbox.host.reset(epoch); mailbox.host.ready(epoch, true); }
        mailbox.host.begin_bound(epoch, id, request["action"].as_str().unwrap(), request["document_id"].as_str())?;
    }
    let mut command = request.clone();
    command["cmd"] = json!("people"); command["host_epoch"] = json!(crate::frame_identity::hex(epoch));
    if let Err(error) = state.send_to_engine(command) {
        mailbox().lock().map_err(|_| "人物结果锁失败")?.host.failed(id, &error);
        return Err(error);
    }
    Ok(json!({"requested": true}))
}
