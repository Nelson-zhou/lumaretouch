//! Native action binding; UI sends coordinates/delta, never sampled RGB or recipe.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle,frame_identity::hex,color_capture_host::{id16,token},color_picker_capture_api::Region};
fn id(value:&str)->Result<(),String>{if value.is_empty()||value.len()>128{Err("invalid targeted color request".into())}else{Ok(())}}
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    let epoch=command.as_object_mut().ok_or("invalid color command")?.remove("host_epoch").ok_or("missing native color epoch")?;
    if epoch.as_str()!=Some(hex(handle.epoch()).as_str()){return Err("color picker engine changed before dispatch".into());}
    let request=command["request_id"].as_str().ok_or("missing color request")?.to_owned();let action=command["action"].as_str().ok_or("missing color action")?.to_owned();
    let bound=crate::color_picker_host::binding(&command)?;
    let mut host=state.color_picker_results.lock().map_err(|_|"color receipt lock poisoned")?;
    host.begin_bound(handle.epoch(),&request,&action,Some(&bound))?;
    let result=handle.send(command);if let Err(error)=&result{host.failed(&request,error);}result
}
#[tauri::command]
pub(crate) fn color_picker(state:State<'_,Arc<AppState>>,request_id:String,capture_id:String,ticket:String,
    action:String,channel:String,region:Region,delta:f64,preview:bool)->Result<Value,String>{
    if matches!(action.as_str(),"colour_editor"|"id_background"|"id_background_reference"|"id_background_subject") {return Err("Use colour editor verified sample, not HSL/curve mutation".into());}
    id(&request_id)?;id16(&capture_id)?;token(&ticket)?;region.validate()?;crate::color_picker_host::selection(&action,&channel)?;
    let limit=if action=="hsl"{60.}else if action=="curve"{1.}else{0.};
    if !delta.is_finite()||delta.abs()>limit{return Err("color picker drag out of range".into());}
    let handle=state.engine.lock().map_err(|_|"engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut capture=state.color_picker_capture.lock().map_err(|_|"color capture lock poisoned")?;
    let proof=capture.eligible_proof(handle.epoch(),&capture_id,&ticket)?;
    if proof.descriptor["picker_action"]!=action||proof.descriptor["picker_channel"]!=channel{return Err("color picker target differs from displayed input".into());}
    if u64::from(region.x)+u64::from(region.width)>u64::from(proof.identity.width)||u64::from(region.y)+u64::from(region.height)>u64::from(proof.identity.height){return Err("color sample exceeds presented image".into());}
    let mut command=json!({"cmd":if preview{"color_picker_probe"}else{"color_picker"},"action":action,"channel":channel,
        "request_id":request_id,"document_id":proof.identity.document.to_string(),"capture_id":capture_id,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":proof.recipe_document_id,"recipe_revision":proof.recipe_revision,"region":region,"delta":delta});
    if preview {
        // Probe goes directly through the same serial engine queue, without a
        // mutation fence. Native admission is one in flight; the UI coalesces
        // one latest candidate rather than accumulating unbounded work.
        let bound=crate::color_picker_host::binding(&command)?;
        let mut host=state.color_picker_probes.lock().map_err(|_|"color probe lock poisoned")?;
        host.begin_bound(handle.epoch(),&request_id,&action,Some(&bound))?;drop(capture);
        let sent=handle.send(command);if let Err(error)=&sent{host.failed(&request_id,error);}sent?;
    }else{
        capture.redeem(handle.epoch(),&capture_id,&ticket)?;drop(capture);
        command["host_epoch"]=json!(hex(handle.epoch()));state.send_to_engine(command)?;
    }
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn color_picker_result(state:State<'_,Arc<AppState>>,request_id:String,preview:bool)->Result<Value,String>{
    id(&request_id)?;
    if preview{Ok(state.color_picker_probes.lock().map_err(|_|"color probe lock poisoned")?.status(&request_id))}
    else{Ok(state.color_picker_results.lock().map_err(|_|"color receipt lock poisoned")?.status(&request_id))}
}
