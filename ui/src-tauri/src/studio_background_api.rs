//! No locator-capture proof: only this exact processed-output preview can apply.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle,color_capture_host::{id16,token},frame_identity::hex};
fn mutation(v:&Value)->Result<(),String>{
    let Some(object)=v.as_object() else{return Err("background mutation must be an object".into())};
    let target=matches!(v["target"].as_str(),Some("background"|"floor"|"protect"|"intrusion"|"blemish"|"recover_intrusions"|"recover_blemishes"|"recover_uniformity"|"recover_banding"));
    let valid=match v["action"].as_str(){
        Some("view")=>object.len()==2,
        Some("replace")=>object.len()==3&&v["proposal"].as_object().is_some_and(|p|p.len()==3)
            &&v["proposal"]["strokes"].as_array().is_some_and(|s|s.len()<=128)
            &&matches!(v["proposal"]["region_mode"].as_str(),Some("manual"|"semantic_background"))
            &&v["proposal"]["parameters"].as_object().is_some_and(|p|p.len()==7),
        _=>false,
    };
    if valid&&target&&v.to_string().len()<=512*1024{Ok(())}else{Err("invalid studio background mutation".into())}
}
fn supported(state:&AppState)->Result<(),String>{
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["studio_background_protocol"]!=1{
        return Err("engine does not support manual studio background".into());
    }Ok(())
}
#[tauri::command]
pub(crate) fn studio_background_preview(state:State<'_,Arc<AppState>>,action:String,preview_id:String,session_id:String,document_id:String,mutation:Option<Value>)->Result<Value,String>{
    supported(&state)?;id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    if !matches!(action.as_str(),"preview"|"presented"|"cancel")||(action=="preview")!=mutation.is_some(){return Err("invalid manual preview action".into());}
    if let Some(v)=mutation.as_ref(){self::mutation(v)?;}
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut host=state.studio_background_preview.lock().map_err(|_|"studio background preview lock poisoned")?;
    if action=="preview"{host.begin(handle.epoch(),&document_id,&session_id,&preview_id)?;}
    else if !host.matches(handle.epoch(),&document_id,&session_id,&preview_id){
        if action=="cancel"{return Ok(json!({"discarded":true}));}return Err("manual preview was replaced".into());
    }
    if action=="presented"{host.presentation_requested()?;}
    let mut command=json!({"cmd":"studio_background_preview","action":action,"preview_id":preview_id,"session_id":session_id,"document_id":document_id});
    if let Some(v)=mutation{command["mutation"]=v;}
    if let Err(error)=handle.send(command){host.invalidate();return Err(error);}
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn studio_background_preview_status(state:State<'_,Arc<AppState>>,preview_id:String)->Result<Value,String>{
    id16(&preview_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    Ok(state.studio_background_preview.lock().map_err(|_|"studio background preview lock poisoned")?.status(handle.epoch(),&preview_id))
}
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    let epoch=command.as_object_mut().ok_or("invalid studio background command")?.remove("host_epoch").ok_or("studio background epoch missing")?;
    if epoch.as_str()!=Some(hex(handle.epoch()).as_str()){return Err("studio background engine changed before dispatch".into());}
    let request=command["request_id"].as_str().ok_or("studio background request missing")?.to_owned();
    let bound=crate::studio_background_host::binding(command["document_id"].as_str().ok_or("document missing")?,command["session_id"].as_str().ok_or("session missing")?,command["preview_id"].as_str().ok_or("preview missing")?)?;
    let mut host=state.studio_background.lock().map_err(|_|"studio background receipt lock poisoned")?;
    host.begin_bound(handle.epoch(),&request,"apply",Some(&bound))?;
    let sent=handle.send(command);if let Err(e)=&sent{host.failed(&request,e);}sent
}
#[tauri::command]
pub(crate) fn studio_background(state:State<'_,Arc<AppState>>,request_id:String,preview_id:String,session_id:String,document_id:String)->Result<Value,String>{
    supported(&state)?;
    if request_id.is_empty()||request_id.len()>128{return Err("invalid studio background request ID".into());}
    id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    {let mut preview=state.studio_background_preview.lock().map_err(|_|"studio background preview lock poisoned")?;
        if !preview.matches(handle.epoch(),&document_id,&session_id,&preview_id){return Err("manual output changed before apply".into());}
        preview.redeem()?;
    }
    state.send_to_engine(json!({"cmd":"studio_background","action":"apply","request_id":request_id,"preview_id":preview_id,"session_id":session_id,"document_id":document_id,"host_epoch":hex(handle.epoch())}))?;
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn studio_background_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid studio background request ID".into());}
    Ok(state.studio_background.lock().map_err(|_|"studio background receipt lock poisoned")?.status(&request_id))
}
