use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    if command["action"]=="pick" {
        let epoch=command.as_object_mut().ok_or("invalid WB command")?.remove("host_epoch").ok_or("missing native WB epoch")?;
        if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("WB engine generation changed before dispatch".into());}
    }
    let id=command["request_id"].as_str().ok_or("missing WB request")?.to_owned();
    let action=command["action"].as_str().ok_or("missing WB action")?.to_owned();
    let mut host=state.white_balance_results.lock().map_err(|_|"WB receipt lock poisoned")?;
    let pick_binding=if action=="pick" {Some(crate::source_patch_host::binding(
        command["document_id"].as_str().ok_or("missing WB document")?,
        command["capture_id"].as_str().ok_or("missing WB capture")?,
        command["ticket"].as_str().ok_or("missing WB ticket")?)?)} else {None};
    host.begin_bound(handle.epoch(),&id,&action,pick_binding.as_deref().or(command["document_id"].as_str()))?;
    let result=handle.send(command);if let Err(error)=&result{host.failed(&id,error);}result
}
#[tauri::command]
pub(crate) fn white_balance(state:State<'_,Arc<AppState>>,action:String,algorithm:Option<String>,request_id:String,document_id:String)->Result<Value,String>{
    if !["set_algorithm","reset","clear_pick"].contains(&action.as_str()){return Err("invalid WB action".into());}
    if action=="set_algorithm" {
        if !algorithm.as_deref().is_some_and(|a|["legacy-xyz-ratio-v1","linear-srgb-d-white-ratio-v1"].contains(&a)){return Err("invalid WB algorithm".into());}
    } else if algorithm.is_some(){return Err("reset does not select an algorithm".into());}
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["white_balance_result_protocol"]!=1{return Err("engine does not support reviewed WB actions".into());}
    let mut command=json!({"cmd":"white_balance","action":action,"request_id":request_id,"document_id":document_id});
    if let Some(value)=algorithm{command["algorithm"]=json!(value);}
    state.send_to_engine(command)?;Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn white_balance_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid WB request ID".into());}
    Ok(state.white_balance_results.lock().map_err(|_|"WB receipt lock poisoned")?.status(&request_id))
}
