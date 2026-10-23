// SPDX-License-Identifier: GPL-3.0-or-later
//! Source-owned hair review receipts; never claim enqueue equals applied pixels.
use serde_json::{json, Value};
use std::sync::{Mutex, OnceLock};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
const ACTIONS: &[&str] = &["context", "preview_support", "preview_recovery", "commit_support", "commit_recovery", "clear_recovery", "clear_support"];
struct HairKind;
impl ReceiptKind for HairKind {
    const NAME: &'static str = "hair_colour";
    const ACTIONS: &'static [&'static str] = ACTIONS;
    fn valid(value: &Value, document: Option<&str>) -> bool {
        value["protocol"] == 1 && value["document_id"].as_str() == document
            && value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
            && (if value["success"] == true { value["payload"].is_object() && value["outcome_unknown"] == false }
                else { value["error"].is_string() })
    }
    fn valid_request(_: &str, document: Option<&str>) -> bool { document.is_some_and(|s| !s.is_empty() && s.len() <= 128) }
    fn decorate_failure(value: &mut Value, document: Option<&str>) { value["protocol"] = json!(1); value["document_id"] = json!(document); }
}
#[derive(Default)]
struct Mailbox {epoch: [u8;16], host: ReceiptHost<HairKind>}
fn mailbox() -> &'static Mutex<Mailbox> {static BOX: OnceLock<Mutex<Mailbox>> = OnceLock::new(); BOX.get_or_init(|| Mutex::new(Mailbox::default()))}
pub(crate) fn receive(epoch: [u8;16], value: &Value) {if let Ok(mut b)=mailbox().lock(){b.host.receive(epoch,value);}}
pub(crate) fn ended(epoch: [u8;16]) {if let Ok(mut b)=mailbox().lock(){b.host.ended(epoch);}}
pub(crate) fn enqueue(handle: &crate::engine::EngineHandle, mut command: Value) -> Result<(),String> {
    let epoch=command.as_object_mut().ok_or("头发命令无效")?.remove("host_epoch").ok_or("头发命令缺少引擎身份")?;
    if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("引擎已变化，未重发头发操作".into());}
    handle.send(command)
}
#[tauri::command]
pub(crate) fn hair_colour(state:tauri::State<'_,std::sync::Arc<crate::AppState>>,request:Value)->Result<Value,String>{
    let fields=request.as_object().ok_or("头发请求必须是对象")?;
    let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("头发请求身份无效")?;
    if request["action"]=="status"{if fields.len()!=2{return Err("头发查询字段无效".into());}return Ok(mailbox().lock().map_err(|_|"头发回执锁失败")?.host.status(id));}
    if fields.len()!=4||!request["action"].as_str().is_some_and(|a|ACTIONS.contains(&a))||!request["payload"].is_object()
        ||request.to_string().len()>512*1024||!crate::people_api::valid_context(&request["people_context"])
        ||request["people_context"]["target"]["scope"]!="face"{return Err("头发请求缺少源照片、人物、版本或有效范围".into());}
    let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;let handle=guard.as_ref().ok_or("引擎不可用，头发修改未提交")?;
        if !handle.is_alive(){return Err("引擎已退出，头发修改未提交".into());}handle.epoch()};
    if state.ready_caps.lock().map_err(|_|"能力锁失败")?["hair_colour_protocol"]!=1{return Err("引擎未提供头发审核协议".into());}
    {let mut b=mailbox().lock().map_err(|_|"头发回执锁失败")?;if b.epoch!=epoch{b.epoch=epoch;b.host.reset(epoch);b.host.ready(epoch,true);}
        b.host.begin_bound(epoch,id,request["action"].as_str().unwrap(),request["people_context"]["document_id"].as_str())?;}
    let mut command=request.clone();command["cmd"]=json!("hair_colour");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
    if let Err(error)=state.send_to_engine(command){mailbox().lock().map_err(|_|"头发回执锁失败")?.host.failed(id,&error);return Err(error);}
    Ok(json!({"requested":true}))
}
