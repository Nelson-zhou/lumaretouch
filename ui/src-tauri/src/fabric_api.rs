//! Fine clothing-crease recipe boundary; no image synthesis.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::AppState;
#[tauri::command]
pub(crate) fn fabric(state:State<'_,Arc<AppState>>,action:String,amount:Option<f64>,document_id:String)->Result<Value,String>{
    if !["set","clear"].contains(&action.as_str()){return Err("Unknown fabric action".into());}
    if document_id.is_empty()||document_id.chars().count()>64{return Err("Invalid fabric document".into());}
    let value=if action=="clear"{0.0}else{amount.ok_or("Fabric amount required")?};
    if !value.is_finite()||!(0.0..=1.0).contains(&value){return Err("Fabric amount must be between 0 and 1".into());}
    state.send_to_engine(json!({"cmd":"fabric","action":action,"amount":value,"document_id":document_id}))?;
    Ok(json!({"requested":true}))
}
