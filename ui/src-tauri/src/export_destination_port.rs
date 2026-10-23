//! Read-only preview receipts, fenced by the actual engine generation.
use serde_json::{json, Value};
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use tauri::State;
use crate::AppState;
struct Receipt { epoch: [u8;16], result: Value }
fn store() -> &'static Mutex<HashMap<String,Receipt>> {
    static STORE: OnceLock<Mutex<HashMap<String,Receipt>>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(HashMap::new()))
}
pub(crate) fn receive(epoch:[u8;16], event:&Value) {
    let Some(id)=event["request_id"].as_str() else {return};
    if let Ok(mut entries)=store().lock() {
        if let Some(entry)=entries.get_mut(id) {
            if entry.epoch==epoch && entry.result["status"]=="pending" {
                entry.result=if event.to_string().len()>8*1024*1024 {
                    json!({"status":"failed","error":"目录预览过大，请分批导出"})
                } else {event.clone()};
            }
        }
    }
}
#[tauri::command]
pub(crate) fn export_destination(state:State<'_,Arc<AppState>>,action:String,request_id:String,
    policy:Option<Value>,document_ids:Option<Vec<String>>,intent_revision:Option<u64>,export_options:Option<Value>) -> Result<Value,String> {
    if !["preview","cancel"].contains(&action.as_str()) || request_id.is_empty() || request_id.len()>128 {
        return Err("无效目录预览请求".into());
    }
    if state.ready_caps.lock().map_err(|_|"能力锁不可用")?["export_destination_protocol"]!=1 {
        return Err("当前引擎不支持目录规划，请重启更新后的引擎".into());
    }
    let epoch=state.engine.lock().map_err(|_|"引擎锁不可用")?.as_ref().ok_or("引擎未启动")?.epoch();
    let mut cmd=json!({"cmd":"export_destination","action":action,"request_id":request_id});
    if action=="preview" {
        cmd["policy"]=policy.ok_or("缺少目录策略")?;
        cmd["document_ids"]=json!(document_ids.ok_or("缺少文档身份")?);
        cmd["intent_revision"]=json!(intent_revision.ok_or("缺少预览修订")?);
        cmd["export_options"]=export_options.ok_or("缺少导出选项")?;
    }
    if cmd.to_string().len()>1024*1024 {return Err("目录请求过大".into());}
    {
        let mut entries=store().lock().map_err(|_|"目录回执锁不可用")?;
        entries.retain(|_,r|r.epoch==epoch);
        if entries.len()>=64 || entries.contains_key(&request_id) {return Err("目录请求已存在或容量已满".into());}
        entries.insert(request_id.clone(),Receipt{epoch,result:json!({"status":"pending"})});
    }
    if let Err(error)=state.send_to_engine(cmd) {
        receive(epoch,&json!({"request_id":request_id,"status":"failed","error":error}));
        return Err("目录预览发送失败，请重新预览".into());
    }
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn export_destination_result(state:State<'_,Arc<AppState>>,request_id:String) -> Result<Value,String> {
    let epoch=state.engine.lock().map_err(|_|"引擎锁不可用")?.as_ref().map(|h|h.epoch());
    let entries=store().lock().map_err(|_|"目录回执锁不可用")?;
    Ok(match entries.get(&request_id) {
        Some(row) if Some(row.epoch)==epoch => row.result.clone(),
        _ => json!({"status":"failed","error":"引擎或预览已失效，请重新预览"}),
    })
}
#[tauri::command]
pub(crate) fn export_destination_release(request_id:String) -> Result<Value,String> {
    store().lock().map_err(|_|"目录回执锁不可用")?.remove(&request_id);
    Ok(json!({"released":true}))
}

#[tauri::command]
pub(crate) async fn choose_import_folder(app:tauri::AppHandle) -> Result<Option<String>,String> {
    use tauri_plugin_dialog::DialogExt;
    tauri::async_runtime::spawn_blocking(move || -> Result<Option<String>,String> {
        let selected=app.dialog().file().set_title("添加照片文件夹（保留内部层级，不移动原图）").blocking_pick_folder();
        let Some(selected)=selected else {return Ok(None)};
        let path=selected.into_path().map_err(|_|"只接受本机文件夹")?;
        let text=path.to_str().filter(|v|v.starts_with('/') && !v.contains('\0')).ok_or("无效本地路径")?;
        Ok(Some(text.to_owned()))
    }).await.map_err(|error|error.to_string())?
}
