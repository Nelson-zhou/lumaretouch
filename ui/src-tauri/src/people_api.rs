// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded people commands and correlated receipts. Acceptance is not completion.
use serde_json::{json, Value};
use std::sync::{Mutex, OnceLock};
use crate::receipt_host::{ReceiptHost, ReceiptKind};

#[path = "face_style_protocol.rs"]
pub(crate) mod face_style;
#[path = "skin_reference_match_people.rs"]
pub(crate) mod skin_reference_match;
#[path = "eye_bag_preserve.rs"]
pub(crate) mod eye_bag;
#[path = "facial_sculpt_protocol.rs"]
pub(crate) mod facial_sculpt;
#[path = "eye_makeup_enhance_protocol.rs"]
pub(crate) mod eye_makeup_enhance;
#[path = "face_decoration_protocol.rs"]
pub(crate) mod face_decoration;
#[path="face_decoration_alias_protocol.rs"]
pub(crate) mod decoration_alias;
#[path = "face_decoration_support_alias_protocol.rs"]
pub(crate) mod decoration_support_alias;

const PEOPLE_ACTIONS: &[&str] = &["skin_reference_match_catalog", "skin_reference_match_preview", "skin_reference_match_image", "skin_reference_match_confirm", "skin_reference_match_clear", "eye_makeup_enhance_reference", "eye_makeup_enhance_review", "facial_sculpt_reference", "facial_sculpt_review", "face_decoration_support_alias_preview", "face_decoration_support_alias_image", "face_decoration_support_alias_confirm", "face_decoration_alias_preview", "face_decoration_alias_image", "face_decoration_alias_confirm", "face_decoration_reference", "face_decoration_review", "eye_bag_source_image", "eye_bag_reference", "eye_bag_preview", "eye_bag_image", "eye_bag_confirm", "face_style_catalog", "face_style_preview", "face_style_image", "face_style_confirm", "patch", "link", "group", "face_status", "manual_add", "create_person", "select", "target", "analyse_face", "resolve_legacy", "eye_light_reference", "eye_light_review", "blush_palette", "blush_reference", "blush_review", "lipstick_palette", "lipstick_reference", "lipstick_review", "eyeliner_palette", "eyeliner_reference", "eyeliner_review", "iris_reference", "iris_review", "eyelash_palette", "eyelash_reference", "eyelash_review", "brow_makeup_palette", "brow_makeup_reference", "brow_makeup_review", "skin_body_reference", "skin_body_preview", "skin_body_confirm", "skin_body_detach", "skin_finish_body_reference", "skin_finish_body_preview", "skin_finish_body_confirm", "skin_finish_body_detach", "body_skin_evenness_reference", "body_skin_evenness_preview", "body_skin_evenness_confirm", "body_skin_evenness_detach", "body_face_match_reference", "body_face_match_preview", "body_face_match_confirm", "body_face_match_detach", "collarbone_reference", "collarbone_preview", "collarbone_confirm", "collarbone_detach"];
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
        if !skin_reference_match::receipt(value) || !decoration_support_alias::receipt(value) || !decoration_alias::receipt(value) || !face_style::receipt(value) || !eye_bag::receipt(value) || !face_decoration::receipt(value) || !facial_sculpt::receipt(value) || !eye_makeup_enhance::receipt(value) { return false; }
        if value["success"] != true { return value["error"].is_string(); }
        // This family already checks complete source-wide report publication;
        // reads/tombstones intentionally carry no selected-face document view.
        if skin_reference_match::action(value) { return true; }
        if face_decoration::released_reference(value) || facial_sculpt::released_reference(value) || eye_makeup_enhance::released_reference(value) { return true; }
        if decoration_alias::action(value) || decoration_support_alias::action(value) {return true;}
        if (face_style::action(value) && value["action"] != "face_style_confirm") || (eye_bag::action(value) && value["action"] != "eye_bag_confirm") {
            return value["outcome_unknown"] == false && value.get("doc_state").is_none();
        }
        let people = &value["doc_state"]["people"];
        let binding = &people["binding"];
        if value["action"] == "face_style_confirm" {
            let request = &value["face_style_request"];
            if binding["document_epoch"] != request["document_epoch"]
                || binding["asset_sha256"] != request["target"]["face_ref"]["asset_sha256"]
                || people["association_revision"] != request["association_revision"]
                || binding["document_revision"].as_u64().zip(request["document_revision"].as_u64()).map_or(true, |(after, before)| after < before)
                || people["revision"].as_u64().zip(request["state_revision"].as_u64()).map_or(true, |(after, before)| after < before) { return false; }
            if request["payload"]["ack"].get("members").is_some() {
                // The alias route publishes one shared graph and advances every
                // reviewed document once through the existing batch ledger.
                // Its thirty set_override calls each advance the graph revision.
                // Do not accept the looser v1 current-document receipt here.
                if binding["document_revision"].as_u64().zip(request["document_revision"].as_u64())
                    .map_or(true, |(after, before)| before.checked_add(1) != Some(after))
                    || people["revision"].as_u64().zip(request["state_revision"].as_u64())
                        .map_or(true, |(after, before)| before.checked_add(30) != Some(after)) {
                    return false;
                }
            }
        }
        if value["action"] == "eye_bag_confirm" {
            let request = &value["eye_bag_request"];
            if binding["document_epoch"] != request["document_epoch"]
                || binding["asset_sha256"] != request["target"]["face_ref"]["asset_sha256"]
                || people["association_revision"] != request["association_revision"]
                || binding["document_revision"].as_u64().zip(request["document_revision"].as_u64()).map_or(true, |(after, before)| before.checked_add(1) != Some(after))
                || people["revision"] != value["payload"]["candidate_state_revision"]
                || !eye_bag::same_recipe(&people["eye_bag_preserve"]["recipe"], &value["payload"]["recipe"])
                || people["eye_bag_preserve"]["face_ref"] != request["target"]["face_ref"]
                || people["eye_bag_preserve"]["support_sha256"] != value["payload"]["support_sha256"]
                || people["resolved"]["face_ref"] != request["target"]["face_ref"]
                || people["resolved"]["state_revision"] != people["revision"]
                || people["resolved"]["association_revision"] != people["association_revision"]
                || people["resolved"]["operations"]["lnx.eye_bags.v2"]["/amount"]["value"].as_f64() != value["payload"]["recipe"]["amount"].as_f64()
                || people["resolved"]["operations"]["lnx.eye_bags.v2"]["/preserve"]["value"].as_f64() != value["payload"]["recipe"]["preserve"].as_f64()
                || (value["payload"]["replace_legacy"] == true && people["resolved"]["operations"]["lnx.enhance.v1"]["/eye_bags"]["value"].as_f64() != Some(0.0))
                || (value["payload"]["replace_legacy"] == true && people["eye_bag_preserve"]["legacy_amount"].as_f64() != Some(0.0)) { return false; }
        }
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
pub(crate) fn receive(epoch: [u8; 16], value: &Value) -> bool {
    if let Ok(mut mailbox) = mailbox().lock() {
        let guarded = value["request_id"].as_str().is_some_and(|id| mailbox.host.guards_review(mailbox.epoch, id));
        mailbox.host.receive(epoch, value);
        return (!skin_reference_match::action(value) && !face_style::action(value) && !eye_bag::action(value) && !face_decoration::action(value) && !facial_sculpt::action(value) && !eye_makeup_enhance::action(value) && !decoration_alias::action(value) && !decoration_support_alias::action(value) && !guarded) || (mailbox.epoch == epoch
            && value["request_id"].as_str().is_some_and(|id|
                mailbox.host.status(id)["result"] == *value && value["success"] == true));
    }
    false
}
pub(crate) fn guards_review(epoch: [u8; 16], id: &str) -> bool {
    mailbox().lock().map(|mailbox| mailbox.host.guards_review(epoch, id)).unwrap_or(true)
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
/// Only a retained original read proof can authorize control/recovery. Neither
/// a caller-supplied action label nor an unknown confirmation is sufficient.
fn eye_read_request(host: &ReceiptHost<PeopleKind>, id: &str) -> Result<Value, String> {
    let binding = host.read_review_binding(id).ok_or("原请求不是可验证的只读卧蚕审核；不能取消或释放写入结果" )?;
    let request = binding.get("eye_bag_request").ok_or("原请求不属于卧蚕审核")?;
    let mut command = request.clone(); command["cmd"] = json!("people"); command["request_id"] = json!(id);
    if !eye_bag::read_only(&command) {return Err("原卧蚕请求不是可取消的只读操作".into());}
    Ok(request.clone())
}
fn settled_read(status: &Value) -> bool {
    status["phase"] == "done" && status["result"]["outcome_unknown"] == false
}
fn eye_read_control(state: &crate::AppState, id: &str, recover: bool) -> Result<Value, String> {
    let engine = state.engine.lock().map_err(|_| "引擎锁失败")?;
    let mailbox = mailbox().lock().map_err(|_| "人物结果锁失败")?;
    let request = eye_read_request(&mailbox.host, id)?;
    let status = mailbox.host.status(id);
    let same_live = engine.as_ref().is_some_and(|h| h.epoch() == mailbox.epoch && h.is_alive());
    if recover {
        if !settled_read(&status) && same_live {
            return Err("只读审核仍可能运行，请请求取消后查询原请求；未释放正在运行的审核".into());
        }
        // A different current epoch proves loss of old authority, not that the
        // old process stopped. Only an observed dead matching handle proves it.
        let stopped = engine.as_ref().is_some_and(|h| h.epoch() == mailbox.epoch && !h.is_alive());
        return Ok(json!({"request_id":id,"read_only":true,"released":true,
            "reason":if settled_read(&status) {"terminal_read"} else {"engine_ended"},
            "stopped":stopped,"eye_bag_request":request}));
    }
    if settled_read(&status) {
        return Ok(json!({"request_id":id,"cancel_requested":false,"stopped":false,"eye_bag_request":request}));
    }
    let handle = engine.as_ref().filter(|h| h.epoch() == mailbox.epoch && h.is_alive())
        .ok_or("原审核引擎不可用，请查询或恢复原只读请求；未向新引擎重发取消")?;
    handle.cancel_eye_bag_read(id)?;
    Ok(json!({"request_id":id,"cancel_requested":true,"stopped":false,"eye_bag_request":request}))
}

#[tauri::command]
pub(crate) fn people(state: tauri::State<'_, std::sync::Arc<crate::AppState>>, request: Value) -> Result<Value, String> {
    let fields = request.as_object().ok_or("人物请求必须是对象")?;
    let id = request["request_id"].as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or("人物请求身份无效")?;
    if matches!(request["action"].as_str(), Some("cancel_eye_bag_read" | "recover_eye_bag_read")) {
        if fields.len() != 2 {return Err("只读审核控制字段无效".into());}
        return eye_read_control(&state, id, request["action"] == "recover_eye_bag_read");
    }
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
    face_style::command(&request)?;
    skin_reference_match::command(&request)?;
    eye_bag::command(&request)?;
    face_decoration::command(&request)?;
    facial_sculpt::command(&request)?;
    eye_makeup_enhance::command(&request)?;
    decoration_alias::command(&request)?;
    decoration_support_alias::command(&request)?;
    let mut command = request.clone();
    command["cmd"] = json!("people");
    let epoch = {
        let guard = state.engine.lock().map_err(|_| "引擎锁失败")?;
        let handle = guard.as_ref().ok_or("引擎不可用，人物修改未提交")?;
        if !handle.is_alive() { return Err("引擎已退出，人物修改未提交".into()); }
        handle.epoch()
    };
    if state.ready_caps.lock().map_err(|_| "能力锁失败")?["people_protocol"] != 1 {
        return Err("引擎未提供确认式人物协议".into());
    }
    if skin_reference_match::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["skin_reference_match_protocol"] != 1 {
        return Err("引擎未提供当前照片的肤色参照匹配审核协议".into());
    }
    if decoration_support_alias::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["face_decoration_support_alias_protocol"] != 1 {
        return Err("引擎未提供共用源图可见皮肤与支撑库原子审核协议".into());
    }
    if decoration_alias::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["face_decoration_alias_protocol"] != 1 {
        return Err("引擎未提供完整共用源图装饰审核协议".into());
    }
    if facial_sculpt::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["facial_sculpt_protocol"] != 1 {
        return Err("引擎未提供绑定当前来源的面部立体审核协议".into());
    }
    if eye_makeup_enhance::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["eye_makeup_enhance_protocol"] != 1 {
        return Err("引擎未提供绑定当前来源的原有眼妆审核协议".into());
    }
    if face_decoration::action(&command) && state.ready_caps.lock().map_err(|_| "能力锁失败")?["face_decoration_protocol"] != 1 {
        return Err("引擎未提供绑定原图与关键点的面饰审核协议".into());
    }
    {
        let mut mailbox = mailbox().lock().map_err(|_| "人物结果锁失败")?;
        if mailbox.epoch != epoch { mailbox.epoch = epoch; mailbox.host.reset(epoch); mailbox.host.ready(epoch, true); }
        if command["action"] == "facial_sculpt_review" {
            let reference_id = command["payload"]["reference_proof"]["reference_request_id"].as_str().unwrap();
            if !facial_sculpt::reference_matches(&command, &mailbox.host.status(reference_id)) {
                return Err("面部立体来源凭据已过期，请重新读取当前人物原图".into());
            }
        }
        if command["action"] == "eye_makeup_enhance_review" {
            let reference_id = command["payload"]["reference_proof"]["reference_request_id"].as_str().unwrap();
            if !eye_makeup_enhance::reference_matches(&command, &mailbox.host.status(reference_id)) {
                return Err("原有眼妆来源凭据已过期，请重新读取当前人物原图".into());
            }
        }
        if command["action"] == "face_decoration_review" {
            let reference_id = command["payload"]["reference_proof"]["reference_request_id"].as_str().unwrap();
            if !face_decoration::reference_matches(&command, &mailbox.host.status(reference_id)) {
                return Err("面饰原图审核凭据已过期或未完成，请重新读取当前人物原图".into());
            }
        }
        if command["action"] == "face_decoration_support_alias_preview" {
            let reference_id = command["payload"]["reference_proof"]["reference_request_id"].as_str().unwrap();
            if !decoration_support_alias::reference_matches(&command, &mailbox.host.status(reference_id)) {
                return Err("共用源图支撑审核凭据已过期或未完成，请重新读取当前人物原图".into());
            }
        }
        if skin_reference_match::action(&command) || face_style::action(&command) || eye_bag::action(&command) || face_decoration::action(&command) || facial_sculpt::action(&command) || eye_makeup_enhance::action(&command) || decoration_alias::action(&command) || decoration_support_alias::action(&command) { mailbox.host.begin_command(epoch, &command)?; }
        else { mailbox.host.begin_bound(epoch, id, request["action"].as_str().unwrap(), request["document_id"].as_str())?; }
    }
    command["host_epoch"] = json!(crate::frame_identity::hex(epoch));
    if let Err(error) = state.send_to_engine(command) {
        mailbox().lock().map_err(|_| "人物结果锁失败")?.host.failed(id, &error);
        return Err(error);
    }
    Ok(json!({"requested": true}))
}

#[cfg(test)]
#[path = "face_style_alias_host_tests.rs"]
mod face_style_alias_host_tests;

// AUTHORED / UNRUN: no native test execution was performed.
#[cfg(test)]
#[path = "eye_bag_cancel_native_unrun.rs"]
mod eye_bag_cancel_tests;

#[cfg(test)]
#[path = "eye_bag_alias_host_unrun.rs"]
mod eye_bag_alias_host_tests;
