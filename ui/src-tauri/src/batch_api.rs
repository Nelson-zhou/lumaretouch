//! Batch command surface and correlated receipt registration, separate from main.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};

pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,command:Value)->Result<(),String>{
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
    preflight_token:Option<String>,request_id:Option<String>,local_mask_transfer:Option<Value>,reference_color:Option<Value>)->Result<Value,String>{
    if !["preflight","commit","undo","redo","state"].contains(&action.as_str()){return Err("unknown batch action".into());}
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
    if let Some(v)=reference_color{cmd["reference_color"]=v;}
    if let Some(v)=local_mask_transfer{cmd["local_mask_transfer"]=v;}
    state.send_to_engine(cmd)?;Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn batch_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty() || request_id.len()>128{return Err("invalid batch request ID".into());}
    Ok(state.batch_results.lock().map_err(|_|"batch receipt lock poisoned")?.status(&request_id))
}
