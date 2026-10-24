//! Conservative cross-domain native receipt fence, including direct engine sends.
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use serde_json::{json, Value};
#[path = "preset_alias_recovery_fence.rs"]
mod preset_alias;
#[path = "preset_alias_history_fence.rs"]
mod preset_alias_history;
struct Pending { command: Value, composite_history: Option<Value> }
impl Pending { fn composite(&self)->bool {preset_alias::applies(&self.command)||crate::people_api::decoration_alias::applies(&self.command)||crate::people_api::decoration_support_alias::applies(&self.command)||crate::effect_recovery_host::alias::applies(&self.command)||self.composite_history.is_some()} }
fn pending()->&'static Mutex<HashMap<([u8;16],String),Pending>> {
    static STORE:OnceLock<Mutex<HashMap<([u8;16],String),Pending>>=OnceLock::new();
    STORE.get_or_init(||Mutex::new(HashMap::new()))
}
pub(crate) fn issued(epoch:[u8;16], command:&Value)->Result<(),String>{
    let mut store=pending().lock().map_err(|_|"恢复回执屏障锁不可用")?;
    if store.iter().any(|((owner_epoch,_),request)|*owner_epoch==epoch&&request.composite()) {
        if command["request_id"].as_str().is_some_and(|id|store.contains_key(&(epoch,id.to_owned())))
            || !preset_alias::safe_during_pending(command) {
            return Err("共享图层影响的全部照片尚未确认；请查询原请求或重新打开工程，不能继续编辑、撤销、保存、导出或重发".into());
        }
        // These reads/recovery escapes cannot create a second uncertain-edit
        // fence or release the original composite request.
        return Ok(());
    }
    if command["cmd"]=="project_recovery" {return Ok(());}
    // These exact background actions read isolated/source snapshots. A lost
    // display receipt must not create a fictitious uncertain-edit save fence.
    if command["cmd"]=="background" && matches!(command["action"].as_str(),
        Some("id_state"|"id_sample"|"id_spill_preview"|"id_spill_paint_source"|"id_original_shadow_preview"|"id_original_shadow_paint_source")) {return Ok(());}
    let name=command["cmd"].as_str().unwrap_or("");
    if name.ends_with("_state")||name.ends_with("_receipt")||name.ends_with("_capture")||name.ends_with("_preview")||name.ends_with("_sample")
        || matches!(command["action"].as_str(),Some("state"|"status"|"query"|"receipt"|"list"|"context"|"preview"|"preview_support"|"preview_recovery")) {return Ok(());}
    let composite_history=preset_alias_history::markers(epoch,command)?;
    if composite_history.is_some()&&(command.get("request_id").is_none()||crate::batch_api::history::command(command).is_err()) {
        return Err("多照片效果批次历史必须保留原批次与关联请求身份".into());
    }
    let Some(id)=command["request_id"].as_str() else {return Ok(());};
    let key=(epoch,id.to_owned());
    if let Some(prior)=store.get(&key) {if &prior.command!=command{return Err("原请求尚未确认且身份冲突".into());}return Ok(());}
    // Do not turn an unavailable head/portrait-cohort review into an uncertain edit.
    // Check a pending ID collision first: read-only status cannot release or
    // replace an already-issued mutation belonging to another receipt host.
    if crate::batch_api::read_only(command) || crate::torso_transfer_protocol::read_only_head_preflight(command) || crate::preset_api::read_only(command)
        || crate::people_api::face_style::read_only(command) || crate::people_api::eye_bag::read_only(command)
        || crate::people_api::face_decoration::read_only(command) || crate::people_api::decoration_alias::read_only(command) || crate::people_api::decoration_support_alias::read_only(command) {return Ok(());}
    if store.len()>=4096{return Err("未确认请求超过恢复屏障容量，请查询原请求或重新打开工程".into());}
    store.insert(key,Pending{command:command.clone(),composite_history}); Ok(())
}
pub(crate) fn composite_history_marker(epoch:[u8;16],command:&Value)->Result<Option<Value>,String>{preset_alias_history::marker(epoch,command)}
pub(crate) fn shared_history_markers(epoch:[u8;16],command:&Value)->Result<Option<Value>,String>{preset_alias_history::markers(epoch,command)}
pub(crate) fn support_history_workspace(epoch: [u8;16], binding: &Value) -> Option<String> {
    preset_alias_history::support_workspace(epoch, binding)
}
pub(crate) fn observed(epoch:[u8;16], value:&Value){
    let Ok(mut store)=pending().lock() else{return;};
    preset_alias_history::observe_session(epoch,value);
    if matches!(value["event"].as_str(),Some("project_opened"|"project_created")) {
        let reopened=preset_alias::reopened(value);
        if reopened {preset_alias_history::clear(epoch);}
        store.retain(|(e,_),request|*e!=epoch||(request.composite()&&!reopened));return;
    }
    let Some(id)=value["request_id"].as_str() else{return;};
    let event=value["event"].as_str().unwrap_or("");
    if !(event.ends_with("_result")||event.ends_with("_done")||event.ends_with("_receipt")){return;}
    let key=(epoch,id.to_owned());
    let Some(request)=store.get(&key) else{return;};
    let command=&request.command;
    // Receipt hosts can share an epoch but not command/action identity. A late
    // read-only preflight (including one whose result omits scope on rejection)
    // must never settle another host's later mutation with a reused request ID.
    let preset_or_batch=matches!(command["cmd"].as_str(),Some("preset"|"batch"|"people"|"effect_recovery"));
    let preset_or_batch_receipt=matches!(event,"preset_result"|"batch_result"|"people_result"|"effect_recovery_result");
    if preset_or_batch||preset_or_batch_receipt {
        let expected=format!("{}_result",command["cmd"].as_str().unwrap_or(""));
        if event!=expected||value["action"]!=command["action"] {return;}
    }
    if preset_alias::applies(command) {
        if preset_alias::matches_request(command,value) {preset_alias_history::observe_publication(epoch,value);}
        if !preset_alias::settled(command,value) {return;}
    }
    if crate::people_api::decoration_alias::applies(command) {
        if !crate::people_api::decoration_alias::matches_request(command,value) {return;}
        if value["success"]==true {
            let mut publication=value.clone();
            publication["face_decoration_alias_review"]=json!({"version":1,"review_sha256":value["payload"]["history_review_sha256"],"member_count":value["payload"]["alias_members"].as_array().map(|r|r.len())});
            preset_alias_history::observe_publication(epoch,&publication);
        }
        if value["outcome_unknown"]!=false {return;}
    }
    if crate::people_api::decoration_support_alias::applies(command) {
        if !crate::people_api::decoration_support_alias::matches_request(command, value) { return; }
        if value["success"] == true || crate::people_api::decoration_support_alias::retained_publication(value).is_some() {
            preset_alias_history::observe_publication(epoch, value);
        }
        if value["outcome_unknown"] != false { return; }
    }
    if crate::effect_recovery_host::alias::applies(command) {
        if !crate::effect_recovery_host::alias::matches_request(command, value) { return; }
        preset_alias_history::observe_publication(epoch, value);
        if value["outcome_unknown"] != false { return; }
    }
    if request.composite_history.as_ref().is_some_and(|markers|!preset_alias_history::settled_markers(command,markers,value)) {return;}
    if value["outcome_unknown"]==true||value["requires_readback"]==true||value["requires_reload"]==true{return;}
    let status=value["status"].as_str().or(value["phase"].as_str());
    if matches!(status,Some("pending"|"running"|"unknown"|"queued"|"writing"|"accepted")){return;}
    if value["success"].is_boolean()||matches!(status,Some("succeeded"|"failed"|"committed"|"rejected"|"cancelled"|"done"|"readback"|"preview")) {
        store.remove(&key);
    }
}
pub(crate) fn proof(epoch:[u8;16])->Result<Value,String>{
    let store=pending().lock().map_err(|_|"恢复回执屏障锁不可用")?;
    if store.keys().any(|(e,_)|*e==epoch){return Err("仍有原生请求正在处理或结果未知，自动保存暂缓".into());}
    Ok(json!({"native_settled":true,"native_receipts":[]}))
}

#[cfg(test)]
mod tests {
    use super::*;
    // AUTHORED / UNRUN. Read-only exception must never admit shadow apply.
    #[test] fn isolated_shadow_preview_does_not_fence_recovery_but_apply_does() {
        let epoch=[219;16];
        issued(epoch,&json!({"cmd":"background","action":"id_original_shadow_preview","request_id":"shadow-read"})).unwrap();
        issued(epoch,&json!({"cmd":"background","action":"id_original_shadow_paint_source","request_id":"shadow-source-read"})).unwrap();
        assert!(proof(epoch).is_ok());
        issued(epoch,&json!({"cmd":"background","action":"id_original_shadow_apply","request_id":"shadow-write"})).unwrap();
        assert!(proof(epoch).is_err());
        observed(epoch,&json!({"event":"id_background_result","request_id":"shadow-write","success":true,"outcome_unknown":false}));
        assert!(proof(epoch).is_ok());
    }
    #[test] fn unknown_result_keeps_fence_until_explicit_new_workspace() {
        let epoch=[201;16];
        issued(epoch,&json!({"cmd":"people","action":"commit","request_id":"recovery-fixture"})).unwrap();
        observed(epoch,&json!({"event":"people_result","request_id":"recovery-fixture","success":false,"outcome_unknown":true}));
        assert!(proof(epoch).is_err());
        observed(epoch,&json!({"event":"project_opened"}));
        assert!(proof(epoch).is_ok());
    }
    #[test] fn terminal_receipt_settles_but_running_does_not() {
        let epoch=[202;16];
        issued(epoch,&json!({"cmd":"managed_import","action":"start","request_id":"import-fixture"})).unwrap();
        observed(epoch,&json!({"event":"managed_import_result","request_id":"import-fixture","status":"running"}));
        assert!(proof(epoch).is_err());
        observed(epoch,&json!({"event":"managed_import_result","request_id":"import-fixture","status":"succeeded"}));
        assert!(proof(epoch).is_ok());
    }
}

// AUTHORED / UNRUN: read-only head review exclusion and late-event collisions.
#[cfg(test)]
#[path = "head_recovery_fence_tests.rs"]
mod head_tests;
