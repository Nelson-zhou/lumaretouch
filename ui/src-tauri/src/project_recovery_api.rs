//! Retained, epoch-correlated project recovery receipts. Never retry an uncertain send.
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
    if value["event"]!="project_recovery_result" || value.to_string().len()>4*1024*1024 {return;}
    let Some(id)=value["request_id"].as_str() else {return;};
    if let Ok(mut store)=receipts().lock() {
        if let Some(row)=store.get_mut(id) {
            if row.epoch==epoch {row.result=Some(value.clone());}
        }
    }
}
#[tauri::command]
pub(crate) fn project_recovery_request(state:State<'_,Arc<AppState>>,mut request:Value)->Result<Value,String> {
    if request.to_string().len()>4*1024*1024 {return Err("项目恢复请求超过大小上限".into());}
    if request["cmd"]!="project_recovery" {return Err("无效项目恢复命令".into());}
    let action=request["action"].as_str().ok_or("缺少动作")?.to_owned();
    if !matches!(action.as_str(),"list"|"inspect"|"restore"|"discard"|"status"|"cancel"|"snapshot"|"checkpoint"|"relink"|"trash_list"|"restore_trash") {return Err("未知项目恢复动作".into());}
    let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("缺少请求身份")?.to_owned();
    if matches!(action.as_str(),"restore"|"discard"|"restore_trash"|"relink") && request["confirmed"]!=true {return Err("请先确认恢复为副本或移入恢复回收站".into());}
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let handle=engine.as_ref().ok_or("引擎未启动")?;
    let epoch=handle.epoch();
    if matches!(action.as_str(),"checkpoint"|"snapshot") {
        let queue=handle.queue_stats();
        if queue["pending"].as_u64()!=Some(0)||queue["in_flight"]!=false||queue["closed"]!=false {
            return Err("编辑队列尚未静止，自动保存暂缓".into());
        }
        let proof=crate::project_recovery_fence::proof(epoch)?;
        request["native_settled"]=proof["native_settled"].clone();
        request["native_receipts"]=proof["native_receipts"].clone();
    }
    {
        let mut store=receipts().lock().map_err(|_|"项目恢复回执锁不可用")?;
        if let Some(prior)=store.get(&id) {
            if prior.epoch==epoch&&prior.request==request {return Ok(json!({"request_id":id,"requested":true,"replayed":true}));}
            return Err("请求身份冲突，未发送".into());
        }
        // Completed readbacks can be discarded; original writes remain queryable.
        // Unread receipts are retained; read-only results are retired after readback.
        if store.len()>=256 {return Err("项目恢复回执空间已满，请保存并重启".into());}
        store.insert(id.clone(),Receipt{epoch,request:request.clone(),result:None});
    }
    drop(engine);
    // Flush the existing edit queue before scan admission; cancels/readbacks use
    // the same transport but never enter the recipe-edit fence or history stack.
    state.send_to_engine(request).map_err(|error|format!("发送结果待确认：{error}；请查询原请求，勿重发"))?;
    Ok(json!({"request_id":id,"requested":true}))
}
#[tauri::command]
pub(crate) fn project_recovery_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String> {
    if request_id.is_empty()||request_id.len()>128 {return Err("无效请求身份".into());}
    let engine=state.engine.lock().map_err(|_|"引擎锁不可用")?;
    let epoch=engine.as_ref().map(|h|h.epoch());
    let mut store=receipts().lock().map_err(|_|"项目恢复回执锁不可用")?;
    let Some(row)=store.get(&request_id) else {return Ok(json!({"phase":"not_sent","result":null}));};
    if epoch!=Some(row.epoch) {return Ok(json!({"phase":"unknown","result":null,"reason":"engine restarted; inspect local candidates and destination before retrying"}));}
    let result=json!({"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result});
    let retire=row.result.is_some()&&!matches!(row.request["action"].as_str(),Some("restore"|"restore_trash"|"discard"|"relink"|"snapshot"));
    if retire {store.remove(&request_id);}
    Ok(result)
}
