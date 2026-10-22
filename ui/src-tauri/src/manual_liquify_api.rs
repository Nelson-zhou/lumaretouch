//! No locator-capture proof: only this exact processed-output preview can apply.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle,color_capture_host::{id16,token},frame_identity::hex};
fn mutation(v:&Value)->Result<(),String>{
    let count=v.as_object().map_or(0,|v|v.len());
    let valid=match v["action"].as_str(){
        Some("view"|"clear")=>count==1,
        Some("delete")=>count==2&&v["id"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=64),
        Some("stroke")=>count==2&&v["stroke"]["points"].as_array().is_some_and(|p|!p.is_empty()&&p.len()<=2048)
            &&matches!(v["stroke"]["mode"].as_str(),Some("push"|"reconstruct"|"smooth"|"rotate"|"pucker"|"bloat"|"left"|"freeze"|"thaw")),
        _=>false,
    };
    if valid&&v.to_string().len()<=256*1024{Ok(())}else{Err("invalid manual liquify mutation".into())}
}
fn supported(state:&AppState)->Result<(),String>{
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["manual_liquify_protocol"]!=1{
        return Err("engine does not support manual liquify".into());
    }Ok(())
}
#[tauri::command]
pub(crate) fn manual_liquify_preview(state:State<'_,Arc<AppState>>,action:String,preview_id:String,session_id:String,document_id:String,mutation:Option<Value>)->Result<Value,String>{
    supported(&state)?;id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    if !matches!(action.as_str(),"preview"|"presented"|"cancel")||(action=="preview")!=mutation.is_some(){return Err("invalid manual preview action".into());}
    if let Some(v)=mutation.as_ref(){self::mutation(v)?;}
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut host=state.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?;
    if action=="preview"{host.begin(handle.epoch(),&document_id,&session_id,&preview_id)?;}
    else if !host.matches(handle.epoch(),&document_id,&session_id,&preview_id){
        if action=="cancel"{return Ok(json!({"discarded":true}));}return Err("manual preview was replaced".into());
    }
    if action=="presented"{host.presentation_requested()?;}
    let mut command=json!({"cmd":"manual_liquify_preview","action":action,"preview_id":preview_id,"session_id":session_id,"document_id":document_id});
    if let Some(v)=mutation{command["mutation"]=v;}
    if let Err(error)=handle.send(command){host.invalidate();return Err(error);}
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn manual_liquify_preview_status(state:State<'_,Arc<AppState>>,preview_id:String)->Result<Value,String>{
    id16(&preview_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    Ok(state.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?.status(handle.epoch(),&preview_id))
}
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    let epoch=command.as_object_mut().ok_or("invalid liquify command")?.remove("host_epoch").ok_or("liquify epoch missing")?;
    if epoch.as_str()!=Some(hex(handle.epoch()).as_str()){return Err("liquify engine changed before dispatch".into());}
    let request=command["request_id"].as_str().ok_or("liquify request missing")?.to_owned();
    let bound=crate::manual_liquify_host::binding(command["document_id"].as_str().ok_or("document missing")?,command["session_id"].as_str().ok_or("session missing")?,command["preview_id"].as_str().ok_or("preview missing")?)?;
    let mut host=state.manual_liquify.lock().map_err(|_|"liquify receipt lock poisoned")?;
    host.begin_bound(handle.epoch(),&request,"apply",Some(&bound))?;
    let sent=handle.send(command);if let Err(e)=&sent{host.failed(&request,e);}sent
}
#[tauri::command]
pub(crate) fn manual_liquify(state:State<'_,Arc<AppState>>,request_id:String,preview_id:String,session_id:String,document_id:String)->Result<Value,String>{
    supported(&state)?;
    if request_id.is_empty()||request_id.len()>128{return Err("invalid liquify request ID".into());}
    id16(&preview_id)?;id16(&session_id)?;token(&document_id)?;
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    {let mut preview=state.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?;
        if !preview.matches(handle.epoch(),&document_id,&session_id,&preview_id){return Err("manual output changed before apply".into());}
        preview.redeem()?;
    }
    state.send_to_engine(json!({"cmd":"manual_liquify","action":"apply","request_id":request_id,"preview_id":preview_id,"session_id":session_id,"document_id":document_id,"host_epoch":hex(handle.epoch())}))?;
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn manual_liquify_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid liquify request ID".into());}
    Ok(state.manual_liquify.lock().map_err(|_|"liquify receipt lock poisoned")?.status(&request_id))
}
