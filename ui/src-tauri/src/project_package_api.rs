//! Retained, epoch-correlated source relocation receipts. Never retry an uncertain send.
use std::{collections::HashMap, sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
struct Receipt { epoch:[u8;16], request:Value, result:Option<Value> }
fn receipts()->&'static Mutex<HashMap<String,Receipt>> {
    static STORE:OnceLock<Mutex<HashMap<String,Receipt>>>=OnceLock::new();
    STORE.get_or_init(||Mutex::new(HashMap::new()))
}
pub(crate) fn receive(epoch:[u8;16], value:&Value) {
    if value["event"]!="project_package_result" || value.to_string().len()>4*1024*1024 {return;}
    let Some(id)=value["request_id"].as_str() else {return;};
    if let Ok(mut store)=receipts().lock() {
        if let Some(row)=store.get_mut(id) {
            if row.epoch==epoch {row.result=Some(value.clone());}
        }
    }
}
#[tauri::command]
pub(crate) fn project_package_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String> {
    if request.to_string().len()>4*1024*1024 {return Err("便携工程请求超过大小上限".into());}
    if request["cmd"]!="project_package" {return Err("无效便携工程命令".into());}
    let action=request["action"].as_str().ok_or("缺少动作")?;
    if !matches!(action,"preview_create"|"create"|"preview_restore"|"restore"|"status"|"cancel") {return Err("未知便携工程动作".into());}
    let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("缺少请求身份")?.to_owned();
    if matches!(action,"create"|"restore") && request["confirmed"]!=true {return Err("请先审核并确认便携工程清单".into());}
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let handle=engine.as_ref().ok_or("引擎未启动")?;
    let epoch=handle.epoch();
    {
        let mut store=receipts().lock().map_err(|_|"便携工程回执锁不可用")?;
        if let Some(prior)=store.get(&id) {
            if prior.epoch==epoch&&prior.request==request {return Ok(json!({"request_id":id,"requested":true,"replayed":true}));}
            return Err("请求身份冲突，未发送".into());
        }
        // Completed readbacks can be discarded; original writes remain queryable.
        store.retain(|_,row|row.result.is_none()||matches!(row.request["action"].as_str(),Some("create")|Some("restore")));
        if store.len()>=256 {return Err("便携工程回执空间已满，请保存并重启".into());}
        store.insert(id.clone(),Receipt{epoch,request:request.clone(),result:None});
    }
    drop(engine);
    // Flush the existing edit queue before scan admission; cancels/readbacks use
    // the same transport but never enter the recipe-edit fence or history stack.
    state.send_to_engine(request).map_err(|error|format!("发送结果待确认：{error}；请查询原请求，勿重发"))?;
    Ok(json!({"request_id":id,"requested":true}))
}
#[tauri::command]
pub(crate) fn project_package_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String> {
    if request_id.is_empty()||request_id.len()>128 {return Err("无效请求身份".into());}
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let epoch=engine.as_ref().map(|h|h.epoch());
    let store=receipts().lock().map_err(|_|"便携工程回执锁不可用")?;
    let Some(row)=store.get(&request_id) else {return Ok(json!({"phase":"unknown","result":null}));};
    if epoch!=Some(row.epoch) {return Ok(json!({"phase":"unknown","result":null,"reason":"engine restarted; read persisted operation receipt"}));}
    Ok(json!({"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result}))
}
