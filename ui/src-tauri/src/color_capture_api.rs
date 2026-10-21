//! Exact complete capture reads, separate from preview counters/dirty-window modes.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle,capture_wire::HEADER_BYTES,color_capture_host::{id16,token}};
fn engine(state:&AppState)->Result<Arc<EngineHandle>,String>{
    state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running".into())
}
#[tauri::command]
pub(crate) fn capture_arm(state:State<'_,Arc<AppState>>,capture_id:String,document_id:String)->Result<Value,String>{
    id16(&capture_id)?;token(&document_id)?;
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["color_capture_protocol"]!=1 {
        return Err("current engine does not support identified colour capture".into());
    }
    let revision={
        let report=state.doc_report.lock().map_err(|_|"document lock poisoned")?;
        if report.as_ref().and_then(|r|r["doc_state"]["document_id"].as_str())!=Some(document_id.as_str()) {
            return Err("document changed before capture".into());
        }
        *state.doc_rev.lock().map_err(|_|"revision lock poisoned")?
    };
    let handle=engine(&state)?;
    let mut capture=state.color_capture.lock().map_err(|_|"capture lock poisoned")?;
    let ticket=capture.begin(capture_id.clone(),document_id.clone(),revision)?;
    let command=json!({"cmd":"color_capture","action":"arm","capture_id":capture_id,"ticket":ticket,"document_id":document_id});
    if let Err(error)=handle.send(command){capture.cancel(&capture_id,&ticket);return Err(error);}
    Ok(json!({"ticket":ticket,"revision":revision}))
}
#[tauri::command]
pub(crate) fn capture_status(state:State<'_,Arc<AppState>>,capture_id:String,ticket:String)->Result<Value,String>{
    id16(&capture_id)?;token(&ticket)?;
    Ok(state.color_capture.lock().map_err(|_|"capture lock poisoned")?.status_for(&capture_id,&ticket))
}
#[tauri::command]
pub(crate) fn capture_frame(state:State<'_,Arc<AppState>>,capture_id:String,ticket:String)->Result<tauri::ipc::Response,String>{
    let identity=state.color_capture.lock().map_err(|_|"capture lock poisoned")?.frame(&capture_id,&ticket)?;
    let header=identity.header().map_err(str::to_owned)?;
    let payload=identity.payload_len().map_err(str::to_owned)?;
    let mut bytes=vec![0u8;HEADER_BYTES+payload];bytes[..HEADER_BYTES].copy_from_slice(&header);
    {
        let frames=state.frames.lock().map_err(|_|"frame lock poisoned")?;
        let shm=frames.shm.as_ref().ok_or("capture mapping is unavailable")?;
        let read=shm.read()?;
        if shm.instance_id()!=Some(identity.instance){return Err("capture mapping was replaced".into());}
        let (meta,slot)=read.freshest()?.ok_or("capture frame is unavailable")?;
        if meta.seq!=identity.seq||meta.w!=identity.width||meta.h!=identity.height||shm.pixel_size!=payload {
            return Err("capture frame was overwritten; rearm sampling".into());
        }
        read.copy_span(slot,0,&mut bytes[HEADER_BYTES..])?;
    }
    // Do not hold frame/flock guards while checking the independently owned ticket.
    state.color_capture.lock().map_err(|_|"capture lock poisoned")?.copied(&identity)?;
    Ok(tauri::ipc::Response::new(bytes))
}
#[tauri::command]
pub(crate) fn capture_presented(state:State<'_,Arc<AppState>>,capture_id:String,ticket:String)->Result<Value,String>{
    state.color_capture.lock().map_err(|_|"capture lock poisoned")?.eligible(&capture_id,&ticket)?;
    Ok(json!({"eligible":true}))
}
#[tauri::command]
pub(crate) fn capture_sample(state:State<'_,Arc<AppState>>,capture_id:String,ticket:String,request_id:String,
    x:u32,y:u32,size:u32)->Result<Value,String>{
    if ![1,3,5,11].contains(&size){return Err("invalid sampling neighbourhood".into());}
    let handle=engine(&state)?;
    let mut capture=state.color_capture.lock().map_err(|_|"capture lock poisoned")?;
    let (identity,request_ticket)=capture.begin_sample(&capture_id,&ticket,request_id.clone(),x,y,size)?;
    if x>=identity.width||y>=identity.height {capture.abandon_sample(&request_ticket);return Err("sample outside image".into());}
    let command=json!({"cmd":"color_capture","action":"sample","capture_id":capture_id,"ticket":ticket,
        "document_id":identity.document.to_string(),"generation":identity.generation.to_string(),
        "request_id":request_id,"request_ticket":request_ticket,"x":x,"y":y,"size":size});
    if let Err(error)=handle.send_interactive("color-capture-sample".into(),command){
        capture.abandon_sample(&request_ticket);return Err(error);
    }
    Ok(json!({"request_ticket":request_ticket}))
}
#[tauri::command]
pub(crate) fn capture_cancel(state:State<'_,Arc<AppState>>,capture_id:String,ticket:String)->Result<Value,String>{
    id16(&capture_id)?;token(&ticket)?;
    let document=state.color_capture.lock().map_err(|_|"capture lock poisoned")?.cancel(&capture_id,&ticket);
    if let Some(document_id)=document {
        if let Ok(handle)=engine(&state) {
            handle.send(json!({"cmd":"color_capture","action":"cancel","capture_id":capture_id,"ticket":ticket,"document_id":document_id}))?;
        }
    }
    Ok(json!({"cancelled":true}))
}
