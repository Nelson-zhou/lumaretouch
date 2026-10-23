//! Correlated retained receipts bound to an engine epoch. Unknown never resends edits.
use std::{collections::HashMap,sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
struct Row {epoch:[u8;16],request:Value,result:Option<Value>}
fn mailbox()->&'static Mutex<HashMap<String,Row>> {static BOX:OnceLock<Mutex<HashMap<String,Row>>>=OnceLock::new();BOX.get_or_init(||Mutex::new(HashMap::new()))}
pub(crate) fn receive(epoch:[u8;16],value:&Value){
    let Some(id)=value["request_id"].as_str() else{return};
    if let Ok(mut m)=mailbox().lock(){if let Some(row)=m.get_mut(id){if row.epoch==epoch&&row.result.is_none(){let mut v=value.clone();if let Some(o)=v.as_object_mut(){o.remove("doc_state");}if v.to_string().len()<=32768{row.result=Some(v);}}}}
}
#[tauri::command]
pub(crate) fn photo_detail_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    if request.to_string().len()>8192{return Err("照片细节请求超过 8 KiB".into());}
    let id=request["request_id"].as_str().filter(|x|!x.is_empty()&&x.len()<=128).ok_or("缺少照片细节请求身份")?.to_owned();
    let cmd=request["cmd"].as_str().ok_or("缺少照片细节命令")?;
    if !matches!(cmd,"photo_detail"|"photo_detail_state"){return Err("未知照片细节命令".into());}
    let edit=cmd=="photo_detail";
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;let handle=guard.as_ref().ok_or("引擎未启动")?;let epoch=handle.epoch();
    {let mut m=mailbox().lock().map_err(|_|"照片细节回执锁错误")?;
      if let Some(old)=m.get(&id){if old.epoch==epoch&&old.request==request{return Ok(json!({"requested":true,"request_id":id,"replayed":true}));}return Err("请求身份重复，未发送".into());}
      if m.len()>=4096{return Err("照片细节回执容量已满；请保存并重启应用".into());}
      m.insert(id.clone(),Row{epoch,request:request.clone(),result:None});}
    drop(guard);
    let sent=if edit {state.send_to_engine(request)}else{let g=state.engine.lock().map_err(|_|"引擎锁错误")?;g.as_ref().ok_or("引擎未启动")?.send(request)};
    if let Err(error)=sent{return Err(format!("发送状态未确认：{}；请查询原操作，勿自动重发",error));}
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn photo_detail_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.len()>128{return Err("无效照片细节身份".into());}
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;let epoch=guard.as_ref().map(|h|h.epoch());
    let mut m=mailbox().lock().map_err(|_|"照片细节回执锁错误")?;
    let Some(row)=m.get(&request_id) else{return Ok(json!({"request_id":request_id,"phase":"unknown","result":null}));};
    if epoch!=Some(row.epoch){return Ok(json!({"request_id":request_id,"phase":"unknown","result":null,"reason":"engine-restarted; explicit-readback-required"}));}
    let result=json!({"request_id":request_id,"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result});
    let consume=row.request["cmd"]=="photo_detail_state" && row.result.is_some();
    if consume {m.remove(&request_id);}
    Ok(result)
}
#[tauri::command]
pub(crate) fn photo_detail_cancel(state:State<'_,Arc<AppState>>,request_id:String)->Result<(),String>{
    if request_id.len()>128{return Err("无效照片细节身份".into());}
    let g=state.engine.lock().map_err(|_|"引擎锁错误")?;
    g.as_ref().ok_or("引擎未启动")?.send(json!({"cmd":"photo_detail_cancel","request_id":request_id}))
}
