//! Versioned levels validation and dispatch. Scalar contract is shared with headless replay.
use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,levels_core};

fn validate(spec:&Value)->Result<(),String>{
    let object=spec.as_object().ok_or("levels spec must be an object")?;
    let keys=["version","space","enabled","master","red","green","blue"];
    if object.len()!=keys.len() || object.keys().any(|k|!keys.contains(&k.as_str())) {
        return Err("levels fields missing or unknown".into());
    }
    if spec["version"].as_u64()!=Some(1) || spec["space"]!="srgb-display" || !spec["enabled"].is_boolean(){
        return Err("unsupported levels schema or domain".into());
    }
    let fields=["input_black","input_white","gamma","output_black","output_white"];
    for name in ["master","red","green","blue"] {
        let channel=spec[name].as_object().ok_or("levels channel must be an object")?;
        if channel.len()!=fields.len() || channel.keys().any(|k|!fields.contains(&k.as_str())) {
            return Err("levels channel fields missing or unknown".into());
        }
        let mut values=[0.;5];
        for (i,key) in fields.iter().enumerate(){values[i]=channel[*key].as_f64().ok_or("levels parameters must be numbers")?;}
        levels_core::Channel::new(values).map_err(str::to_owned)?;
    }
    Ok(())
}
#[tauri::command]
pub(crate) fn levels(state:State<'_,Arc<AppState>>,action:String,spec:Option<Value>,document_id:String,
    gesture_id:Option<String>,request_id:Option<String>,interactive:Option<bool>)->Result<Value,String>{
    if !["set","clear"].contains(&action.as_str()){return Err("unknown levels action".into());}
    if document_id.is_empty()||document_id.chars().count()>64{return Err("invalid levels document identity".into());}
    let mut command=json!({"cmd":"levels","action":action,"document_id":document_id});
    if action=="set" {let value=spec.ok_or("levels set requires spec")?;validate(&value)?;command["spec"]=value;}
    let gesture=gesture_id.unwrap_or_default();let request=request_id.unwrap_or_default();
    if gesture.chars().count()>128 || request.chars().count()>128{return Err("levels identity too long".into());}
    command["gesture_id"]=json!(gesture.clone());command["request_id"]=json!(request);
    if interactive==Some(true)&&action=="set"{state.send_interactive(format!("levels:{gesture}"),command)?;}
    else {state.send_to_engine(command)?;}
    Ok(json!({"requested":true}))
}
#[cfg(test)]
mod tests{
    use super::*;
    fn spec()->Value{let channel=json!({"input_black":0.,"input_white":1.,"gamma":1.,"output_black":0.,"output_white":1.});
        json!({"version":1,"space":"srgb-display","enabled":true,"master":channel,"red":channel,"green":channel,"blue":channel})}
    #[test] fn complete_neutral_and_inversion_are_accepted(){let mut v=spec();assert!(validate(&v).is_ok());v["red"]["output_black"]=json!(1.);v["red"]["output_white"]=json!(0.);assert!(validate(&v).is_ok());}
    #[test] fn invalid_gap_gamma_domain_and_extra_fields_are_rejected(){
        for (key,value) in [("input_white",json!(0.)),("gamma",json!(0.)),("extra",json!(1.))]{let mut v=spec();v["master"][key]=value;assert!(validate(&v).is_err());}
        let mut v=spec();v["space"]=json!("lab");assert!(validate(&v).is_err());
    }
}
