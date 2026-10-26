//! Batch command surface and correlated receipt registration, separate from main.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
#[path="collarbone_transfer_protocol.rs"]
pub(crate) mod collarbone;
#[path="face_decoration_batch_protocol.rs"]
pub(crate) mod face_decoration;
#[path="face_decoration_cohort_protocol.rs"]
pub(crate) mod decoration_cohort;
#[path="face_style_batch_protocol.rs"]
pub(crate) mod face_style;
#[path="portrait_cohort_protocol.rs"]
pub(crate) mod portrait_cohort;
#[path="eye_bag_cohort_protocol.rs"]
pub(crate) mod eye_cohort;
#[path="eye_bag_batch_protocol.rs"]
pub(crate) mod eye_bag;
#[path="batch_history_protocol.rs"]
pub(crate) mod history;

#[path="portrait_preset_group_protocol.rs"]
pub(crate) mod portrait_preset_group;

pub(crate) fn read_only(command:&Value)->bool {
    if portrait_preset_group::routed(command) {return portrait_preset_group::read_only(command);}
    if decoration_cohort::read_only(command) {return true;}
    if eye_cohort::routed(command) { return eye_cohort::read_only(command); }
    if command["cmd"]=="batch" && (command["action"]=="eye_bag_visual"
        || command["people_transfer"].get("eye_bag").is_some() || command.get(eye_bag::ACK).is_some()) {
        return eye_bag::read_only(command);
    }
    if face_decoration::read_only(command) {return true;}
    if portrait_cohort::read_only(command) || face_style::read_only(command) || collarbone::read_only(command) {return true;}
    let Some(fields)=command.as_object() else{return false;};
    let Some(docs)=command["docs"].as_array() else{return false;};
    command["cmd"]=="batch" && command["action"]=="people_targets" && fields.len()==4
        && command["request_id"].as_str().is_some_and(|v|!v.is_empty()&&v.len()<=128)
        && !docs.is_empty() && docs.len()<=16
        && docs.iter().all(|v|v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128))
        && docs.iter().enumerate().all(|(i,v)|!docs[..i].contains(v))
}

pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,command:Value)->Result<(),String>{
    portrait_preset_group::command(&command)?;
    decoration_cohort::command(&command)?;
    face_decoration::command(&command)?;
    history::command(&command)?;
    eye_cohort::command(&command)?;
    eye_bag::command(&command)?;
    portrait_cohort::command(&command)?;
    face_style::command(&command)?;
    collarbone::command(&command)?;
    crate::spill_transfer_protocol::command(&command)?;
    crate::original_shadow_transfer_protocol::command(&command)?;
    crate::torso_transfer_protocol::command(&command)?;
    crate::waist_transfer_protocol::command(&command)?;
    crate::torso_transfer_protocol::head_command(&command)?;
    let Some(id)=command["request_id"].as_str().map(str::to_owned) else{return handle.send(command)};
    let mut host=state.batch_results.lock().map_err(|_|"batch receipt lock poisoned")?;
    host.begin_command(handle.epoch(),&command)?;
    let result=handle.send(command);
    if let Err(error)=&result{host.failed(&id,error);}
    result
}
#[tauri::command]
pub(crate) fn batch(state:State<'_,Arc<AppState>>,action:String,docs:Option<Vec<String>>,
    module_scope:Option<Vec<String>>,conflict_policy:Option<String>,batch_id:Option<String>,
    preflight_token:Option<String>,request_id:Option<String>,local_mask_transfer:Option<Value>,reference_color:Option<Value>,people_transfer:Option<Value>,spill_review_ack:Option<Value>,shadow_review_ack:Option<Value>,torso_review_ack:Option<Value>,waist_review_ack:Option<Value>,head_review_ack:Option<Value>,collarbone_review_ack:Option<Value>,face_style_review_ack:Option<Value>,portrait_cohort_ack:Option<Value>,face_decoration_cohort_ack:Option<Value>,face_decoration_review_ack:Option<Value>,eye_bag_review_ack:Option<Value>,eye_bag_cohort_ack:Option<Value>,document_id:Option<String>,revision:Option<String>,side:Option<String>,sha256:Option<String>,preset_id:Option<String>,preset_sha256:Option<String>,portrait_preset_ack:Option<Value>,accepted:Option<bool>,page:Option<u64>,export_options:Option<Value>,policy:Option<Value>,intent_revision:Option<u64>,plan_id:Option<String>,task_id:Option<String>)->Result<Value,String>{
    if !["portrait_preset_save","portrait_preset_export_preview","portrait_preset_export_start","portrait_preset_export_status","portrait_preset_export_cancel","portrait_preset_catalogue","portrait_preset_preflight", "portrait_preset_prepare","portrait_preset_image","portrait_preset_commit","preflight","commit","undo","redo","state","people_targets","collarbone_visual","face_style_visual","portrait_cohort_visual","eye_bag_visual","eye_bag_cohort_visual","face_decoration_visual","face_decoration_cohort_visual"].contains(&action.as_str()){return Err("unknown batch action".into());}
    if request_id.is_some() && state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["batch_preflight_protocol"]!=1 {
        return Err("current engine does not support reviewed batch receipts".into());
    }
    if ["portrait_preset_save","portrait_preset_export_preview","portrait_preset_export_start","portrait_preset_export_status","portrait_preset_export_cancel"].contains(&action.as_str())
        && state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["portrait_preset_delivery_protocol"]!=1 {return Err("current engine does not support exact portrait group delivery".into());}
    if action=="portrait_preset_prepare" && state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["portrait_preset_preparation_protocol"]!=1 {return Err("current engine does not support explicit portrait group preparation".into());}
    if action.starts_with("portrait_preset_") && state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["portrait_preset_group_protocol"]!=1 {return Err("current engine does not support portrait preset groups".into());}
    let mut cmd=json!({"cmd":"batch","action":action});
    if let Some(v)=preset_id{cmd["preset_id"]=json!(v);}
    if let Some(v)=preset_sha256{cmd["preset_sha256"]=json!(v);}
    if let Some(v)=portrait_preset_ack{cmd["portrait_preset_ack"]=v;}
    if let Some(v)=accepted{cmd["accepted"]=json!(v);}
    if let Some(v)=page{cmd["page"]=json!(v);}
    if let Some(v)=export_options{cmd["export_options"]=v;}
    if let Some(v)=policy{cmd["policy"]=v;}
    if let Some(v)=intent_revision{cmd["intent_revision"]=json!(v);}
    if let Some(v)=plan_id{cmd["plan_id"]=json!(v);}
    if let Some(v)=task_id{cmd["task_id"]=json!(v);}
    if let Some(v)=docs{cmd["docs"]=json!(v);}
    if let Some(v)=module_scope{cmd["module_scope"]=json!(v);}
    if let Some(v)=conflict_policy{cmd["conflict_policy"]=json!(v);}
    if let Some(v)=batch_id{cmd["batch_id"]=json!(v);}
    if let Some(v)=preflight_token{cmd["preflight_token"]=json!(v);}
    if let Some(v)=request_id{cmd["request_id"]=json!(v);}
    if let Some(v)=people_transfer{cmd["people_transfer"]=v;}
    if let Some(v)=reference_color{cmd["reference_color"]=v;}
    if let Some(v)=local_mask_transfer{cmd["local_mask_transfer"]=v;}
    if let Some(v)=spill_review_ack{cmd["spill_review_ack"]=v;}
    if let Some(v)=shadow_review_ack{cmd["shadow_review_ack"]=v;}
    if let Some(v)=torso_review_ack{cmd["torso_review_ack"]=v;}
    if let Some(v)=waist_review_ack{cmd["waist_review_ack"]=v;}
    if let Some(v)=head_review_ack{cmd["head_review_ack"]=v;}
    if let Some(v)=collarbone_review_ack{cmd["collarbone_review_ack"]=v;}
    if let Some(v)=face_style_review_ack{cmd["face_style_review_ack"]=v;}
    if let Some(v)=portrait_cohort_ack{cmd["portrait_cohort_ack"]=v;}
    if let Some(v)=face_decoration_cohort_ack{cmd["face_decoration_cohort_ack"]=v;}
    if let Some(v)=face_decoration_review_ack{cmd["face_decoration_review_ack"]=v;}
    if let Some(v)=eye_bag_review_ack{cmd["eye_bag_review_ack"]=v;}
    if let Some(v)=eye_bag_cohort_ack{cmd["eye_bag_cohort_ack"]=v;}
    for (key,value) in [("document_id",document_id),("revision",revision),("side",side),("sha256",sha256)] {
        if let Some(v)=value{cmd[key]=json!(v);}
    }
    portrait_preset_group::command(&cmd)?;
    decoration_cohort::command(&cmd)?;
    face_decoration::command(&cmd)?;
    history::command(&cmd)?;
    eye_cohort::command(&cmd)?;
    eye_bag::command(&cmd)?;
    portrait_cohort::command(&cmd)?;
    face_style::command(&cmd)?;
    collarbone::command(&cmd)?;
    crate::spill_transfer_protocol::command(&cmd)?;
    crate::original_shadow_transfer_protocol::command(&cmd)?;
    crate::torso_transfer_protocol::command(&cmd)?;
    crate::waist_transfer_protocol::command(&cmd)?;
    crate::torso_transfer_protocol::head_command(&cmd)?;
    if cmd["action"]=="people_targets" && !read_only(&cmd){return Err("invalid bounded face inventory request".into());}
    state.send_to_engine(cmd)?;Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn batch_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty() || request_id.len()>128{return Err("invalid batch request ID".into());}
    Ok(state.batch_results.lock().map_err(|_|"batch receipt lock poisoned")?.status(&request_id))
}

// AUTHORED / UNRUN: source-only transport regression specifications.
#[cfg(test)]
mod inventory_tests {
    use super::*;
    #[test]
    fn only_exact_bounded_inventory_is_read_only() {
        let valid=json!({"cmd":"batch","action":"people_targets","request_id":"inventory","docs":["target"]});
        assert!(read_only(&valid));
        for key in ["module_scope","people_transfer","preflight_token"] {
            let mut changed=valid.clone();changed[key]=json!({});assert!(!read_only(&changed));
        }
        let mut changed=valid.clone();changed["action"]=json!("commit");assert!(!read_only(&changed));
        changed=valid.clone();changed["docs"]=json!(["same","same"]);assert!(!read_only(&changed));
        changed=valid.clone();changed["docs"]=json!([]);assert!(!read_only(&changed));
        changed=valid.clone();changed["docs"]=json!((0..17).map(|i|format!("target-{i}")).collect::<Vec<_>>());assert!(!read_only(&changed));
        changed=valid.clone();changed["request_id"]=json!("");assert!(!read_only(&changed));
    }
}
