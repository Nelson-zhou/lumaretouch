//! Batch command surface and correlated receipt registration, separate from main.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};

pub(crate) fn read_only(command:&Value)->bool {
    let Some(fields)=command.as_object() else{return false;};
    let Some(docs)=command["docs"].as_array() else{return false;};
    command["cmd"]=="batch" && command["action"]=="people_targets" && fields.len()==4
        && command["request_id"].as_str().is_some_and(|v|!v.is_empty()&&v.len()<=128)
        && !docs.is_empty() && docs.len()<=16
        && docs.iter().all(|v|v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128))
        && docs.iter().enumerate().all(|(i,v)|!docs[..i].contains(v))
}

pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,command:Value)->Result<(),String>{
    crate::spill_transfer_protocol::command(&command)?;
    crate::original_shadow_transfer_protocol::command(&command)?;
    crate::torso_transfer_protocol::command(&command)?;
    let Some(id)=command["request_id"].as_str().map(str::to_owned) else{return handle.send(command)};
    let action=command["action"].as_str().ok_or("missing batch action")?.to_owned();
    let mut host=state.batch_results.lock().map_err(|_|"batch receipt lock poisoned")?;
    host.begin(handle.epoch(),&id,&action)?;
    let result=handle.send(command);
    if let Err(error)=&result{host.failed(&id,error);}
    result
}
#[tauri::command]
pub(crate) fn batch(state:State<'_,Arc<AppState>>,action:String,docs:Option<Vec<String>>,
    module_scope:Option<Vec<String>>,conflict_policy:Option<String>,batch_id:Option<String>,
    preflight_token:Option<String>,request_id:Option<String>,local_mask_transfer:Option<Value>,reference_color:Option<Value>,people_transfer:Option<Value>,spill_review_ack:Option<Value>,shadow_review_ack:Option<Value>,torso_review_ack:Option<Value>)->Result<Value,String>{
    if !["preflight","commit","undo","redo","state","people_targets"].contains(&action.as_str()){return Err("unknown batch action".into());}
    if request_id.is_some() && state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["batch_preflight_protocol"]!=1 {
        return Err("current engine does not support reviewed batch receipts".into());
    }
    let mut cmd=json!({"cmd":"batch","action":action});
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
    crate::spill_transfer_protocol::command(&cmd)?;
    crate::original_shadow_transfer_protocol::command(&cmd)?;
    crate::torso_transfer_protocol::command(&cmd)?;
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
