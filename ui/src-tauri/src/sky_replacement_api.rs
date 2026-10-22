//! No locator-capture proof: only this exact processed-output preview can apply.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle,color_capture_host::{id16,token},frame_identity::hex};
fn mutation(v:&Value)->Result<(),String>{
    let count=v.as_object().map_or(0,|v|v.len());
    let target=matches!(v["target"].as_str(),Some("sky"|"person"|"water"|"recovery"));
    let valid=match v["action"].as_str(){
        Some("view")=>count==2&&target,
        Some("replace")=>count==3&&target&&v["draft"].is_object(),
        _=>false,
    };
    if valid&&v.to_string().len()<=256*1024{Ok(())}else{Err("invalid sky replacement draft".into())}
}
fn supported(state:&AppState)->Result<(),String>{
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["sky_replacement_protocol"]!=1{
        return Err("engine does not support sky replacement".into());
    }Ok(())
}
#[tauri::command]
pub(crate) fn sky_replacement_preview(state:State<'_,Arc<AppState>>,action:String,preview_id:String,session_id:String,document_id:String,mutation:Option<Value>)->Result<Value,String>{
    supported(&state)?;id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    if !matches!(action.as_str(),"preview"|"presented"|"cancel")||(action=="preview")!=mutation.is_some(){return Err("invalid sky preview action".into());}
    if let Some(v)=mutation.as_ref(){self::mutation(v)?;}
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut host=state.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?;
    if action=="preview"{host.begin(handle.epoch(),&document_id,&session_id,&preview_id)?;}
    else if !host.matches(handle.epoch(),&document_id,&session_id,&preview_id){
        if action=="cancel"{return Ok(json!({"discarded":true}));}return Err("sky preview was replaced".into());
    }
    if action=="presented"{host.presentation_requested()?;}
    let mut command=json!({"cmd":"sky_replacement_preview","action":action,"preview_id":preview_id,"session_id":session_id,"document_id":document_id});
    if let Some(v)=mutation{command["mutation"]=v;}
    if let Err(error)=handle.send(command){host.invalidate();return Err(error);}
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn sky_replacement_preview_status(state:State<'_,Arc<AppState>>,preview_id:String)->Result<Value,String>{
    id16(&preview_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    Ok(state.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?.status(handle.epoch(),&preview_id))
}
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    let epoch=command.as_object_mut().ok_or("invalid sky command")?.remove("host_epoch").ok_or("sky epoch missing")?;
    if epoch.as_str()!=Some(hex(handle.epoch()).as_str()){return Err("sky engine changed before dispatch".into());}
    let request=command["request_id"].as_str().ok_or("sky request missing")?.to_owned();
    let bound=crate::sky_replacement_host::binding(command["document_id"].as_str().ok_or("document missing")?,command["session_id"].as_str().ok_or("session missing")?,command["preview_id"].as_str().ok_or("preview missing")?)?;
    let mut host=state.sky_replacement.lock().map_err(|_|"sky receipt lock poisoned")?;
    host.begin_bound(handle.epoch(),&request,"apply",Some(&bound))?;
    let sent=handle.send(command);if let Err(e)=&sent{host.failed(&request,e);}sent
}
#[tauri::command]
pub(crate) fn sky_replacement(state:State<'_,Arc<AppState>>,request_id:String,preview_id:String,session_id:String,document_id:String)->Result<Value,String>{
    supported(&state)?;
    if request_id.is_empty()||request_id.len()>128{return Err("invalid sky request ID".into());}
    id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    {let mut preview=state.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?;
        if !preview.matches(handle.epoch(),&document_id,&session_id,&preview_id){return Err("sky output changed before apply".into());}
        preview.redeem()?;
    }
    state.send_to_engine(json!({"cmd":"sky_replacement","action":"apply","request_id":request_id,"preview_id":preview_id,"session_id":session_id,"document_id":document_id,"host_epoch":hex(handle.epoch())}))?;
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn sky_replacement_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid sky request ID".into());}
    Ok(state.sky_replacement.lock().map_err(|_|"sky receipt lock poisoned")?.status(&request_id))
}
