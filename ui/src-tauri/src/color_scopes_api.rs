//! Read-only queue path: refreshing a histogram must not cancel full-resolution inspection.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::AppState;
#[tauri::command]
pub(crate) fn color_scopes(state:State<'_,Arc<AppState>>,document_id:String,request_id:String,stage:String)->Result<Value,String>{
    if document_id.is_empty()||document_id.len()>64||request_id.is_empty()||request_id.len()>128 {
        return Err("invalid colour-scope identity".into());
    }
    if !["original","levels-input","curves-input","output"].contains(&stage.as_str()) {
        return Err("unknown colour-scope stage".into());
    }
    let revision={
        let report=state.doc_report.lock().map_err(|_|"document lock poisoned")?;
        if report.as_ref().and_then(|r|r["doc_state"]["document_id"].as_str())!=Some(document_id.as_str()) {
            return Err("document changed; refresh colour scopes".into());
        }
        *state.doc_rev.lock().map_err(|_|"revision lock poisoned")?
    };
    let engine=state.engine.lock().map_err(|_|"engine lock poisoned")?
        .clone().ok_or("engine is not running")?;
    let mut scopes=state.color_scopes.lock().map_err(|_|"colour-scope lock poisoned")?;
    let ticket=scopes.begin(request_id.clone(),document_id.clone(),stage.clone(),revision)?;
    let command=json!({"cmd":"color_scopes","document_id":document_id,"request_id":request_id,"stage":stage,"ticket":ticket});
    let sent=engine.send_interactive("color-scopes".into(),command);
    if let Err(error)=sent {scopes.invalidate();return Err(error);}
    Ok(json!({"requested":true}))
}
