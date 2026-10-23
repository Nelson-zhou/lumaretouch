//! Native local-only picker. Register command only alongside correlated LUT routes.
use std::sync::atomic::{AtomicBool, Ordering};
use tauri_plugin_dialog::DialogExt;
static OPEN: AtomicBool = AtomicBool::new(false);
struct Guard;
impl Drop for Guard { fn drop(&mut self) { OPEN.store(false, Ordering::Release); } }
#[tauri::command]
pub(crate) async fn custom_lut_choose(app: tauri::AppHandle) -> Result<Option<String>, String> {
    if OPEN.swap(true, Ordering::AcqRel) {return Err("LUT 文件选择器已打开".into());}
    let guard=Guard;
    tauri::async_runtime::spawn_blocking(move || {
        let _guard=guard;
        let selected=app.dialog().file().set_title("导入本地 CUBE LUT（保留原文件）").add_filter("CUBE LUT", &["cube"]).blocking_pick_file();
        let Some(selected)=selected else{return Ok(None)};
        let path=selected.into_path().map_err(|_|"仅支持本机文件路径")?;
        if !path.is_absolute() || path.extension().and_then(|s|s.to_str()).map(|s|s.eq_ignore_ascii_case("cube"))!=Some(true) {return Err("请选择本地 .cube 文件".into());}
        let value=path.to_str().filter(|s|s.len()<=4096 && !s.contains('\0')).ok_or("文件路径无效")?;
        Ok(Some(value.to_owned()))
    }).await.map_err(|e|e.to_string())?
}

use std::{collections::{HashMap,HashSet},sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
struct Mailbox { rows:HashMap<String,([u8;16],Option<Value>)>, seen:HashSet<String> }
fn mailbox()->&'static Mutex<Mailbox> {static BOX:OnceLock<Mutex<Mailbox>>=OnceLock::new();BOX.get_or_init(||Mutex::new(Mailbox{rows:HashMap::new(),seen:HashSet::new()}))}
pub(crate) fn receive(epoch:[u8;16],value:&Value) {
    let Some(id)=value["request_id"].as_str() else{return};
    if let Ok(mut m)=mailbox().lock(){if let Some((owner,result))=m.rows.get_mut(id){if *owner==epoch && result.is_none(){let mut compact=value.clone();if let Some(obj)=compact.as_object_mut(){obj.remove("doc_state");}*result=Some(if compact.to_string().len()<=524288 {compact} else {json!({"success":false,"committed":value["committed"],"error":"LUT 回执超过预算，请核对当前状态"})});}}}
}
#[tauri::command]
pub(crate) fn custom_lut_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    if request.to_string().len()>65536{return Err("LUT 请求超过 64 KiB".into());}
    let id=request["request_id"].as_str().filter(|v|!v.is_empty()&&v.len()<=128).ok_or("LUT 请求标识无效")?.to_owned();
    let action=request["action"].as_str().ok_or("缺少 LUT 操作")?;
    if !matches!(action,"list"|"state"|"import"|"recover"|"select"|"rename"|"remove"|"restore"){return Err("未知 LUT 操作".into());}
    let guard=state.engine.lock().map_err(|_|"引擎锁中毒")?;
    let handle=guard.as_ref().ok_or("引擎未启动")?;let epoch=handle.epoch();
    {let mut m=mailbox().lock().map_err(|_|"LUT 回执锁中毒")?;
     if m.rows.len()>=64 || m.seen.len()>=65536 || m.seen.contains(&id){return Err("LUT 请求重复或容量已满；不重放写入".into());}
     m.seen.insert(id.clone());m.rows.insert(id.clone(),(epoch,None));}
    let is_edit=action=="select";
    let mut command=request;command["cmd"]=json!("custom_lut");
    drop(guard);
    let sent=if is_edit { state.send_to_engine(command) } else {
        let guard=state.engine.lock().map_err(|_|"引擎锁中毒")?;
        guard.as_ref().ok_or("引擎未启动")?.send(command)
    };
    if let Err(error)=sent{mailbox().lock().map_err(|_|"LUT 回执锁中毒")?.rows.remove(&id);return Err(error);}
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn custom_lut_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    let guard=state.engine.lock().map_err(|_|"引擎锁中毒")?;
    let epoch=guard.as_ref().map(|h|h.epoch());
    let mut m=mailbox().lock().map_err(|_|"LUT 回执锁中毒")?;
    let (owner,result)=m.rows.get(&request_id).ok_or("LUT 回执不存在或已消费")?;
    if epoch!=Some(*owner){m.rows.remove(&request_id);return Err("引擎已更换，写入结果未确认；请检查当前状态，不要自动重放".into());}
    if let Some(value)=result.clone(){m.rows.remove(&request_id);return Ok(value);}
    Ok(json!({"pending":true}))
}
#[tauri::command]
pub(crate) fn custom_lut_cancel(state:State<'_,Arc<AppState>>,request_id:String)->Result<(),String>{
    if request_id.len()>128{return Err("无效请求标识".into());}
    let guard=state.engine.lock().map_err(|_|"引擎锁中毒")?;
    guard.as_ref().ok_or("引擎未启动")?.send(json!({"cmd":"custom_lut_cancel","request_id":request_id}))
}
