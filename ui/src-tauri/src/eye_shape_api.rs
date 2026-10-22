// SPDX-License-Identifier: GPL-3.0-or-later
use serde_json::{json,Value};
use std::sync::{Mutex,OnceLock};
use crate::receipt_host::{ReceiptHost,ReceiptKind};
const KEYS:[&str;10]=["size","iris_size","height","width","spacing","inner_corner","outer_corner","lower_lid","tilt","position"];
fn text(v:&Value)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128)}
fn recipe(v:&Value)->bool{
    v.as_object().is_some_and(|m|m.len()==11)&&v["version"].as_u64()==Some(1)&&KEYS.iter().all(|k|{
        v[*k].as_object().is_some_and(|m|m.len()==3)&&v[*k]["linked"].is_boolean()
            &&["left","right"].iter().all(|s|v[*k][*s].as_f64().is_some_and(|n|n.is_finite()&&n.abs()<=1.))
    })
}

struct EyeKind;
impl ReceiptKind for EyeKind{
    const NAME:&'static str="eye_shape";const ACTIONS:&'static [&'static str]=&["edit"];
    fn valid(v:&Value,d:Option<&str>)->bool{
        v["protocol"]==1&&v["document_id"].as_str()==d&&v["success"].is_boolean()&&v["outcome_unknown"].is_boolean()
            &&text(&v["face_id"])&&text(&v["gesture_id"])&&text(&v["control"])
            &&(v["success"]!=true||(v["outcome_unknown"]==false&&v["frame_emitted"]==true&&recipe(&v["recipe"])&&v["revision"].as_u64().is_some()))
    }
}
#[derive(Default)]
struct Mailbox{epoch:[u8;16],host:ReceiptHost<EyeKind>}
fn mailbox()->&'static Mutex<Mailbox>{static BOX:OnceLock<Mutex<Mailbox>>=OnceLock::new();BOX.get_or_init(||Mutex::new(Mailbox::default()))}
pub(crate) fn enqueue(handle:&crate::engine::EngineHandle,mut command:Value)->Result<(),String>{
    let epoch=command.as_object_mut().ok_or("眼形命令无效")?.remove("host_epoch").ok_or("眼形缺少引擎身份")?;
    if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("眼形引擎已变化；未向新引擎重发".into());}
    handle.send(command)
}
pub(crate) fn receive(epoch:[u8;16],v:&Value){if let Ok(mut m)=mailbox().lock(){m.host.receive(epoch,v);}}
#[tauri::command]
pub(crate) fn eye_shape(state:tauri::State<'_,std::sync::Arc<crate::AppState>>,request:Value)->Result<Value,String>{
    let object=request.as_object().ok_or("眼形请求必须是对象")?;
    let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("眼形请求身份无效")?;
    let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;{let handle=guard.as_ref().ok_or("引擎不可用；结果未确认")?;if !handle.is_alive(){return Err("引擎已退出；结果未确认".into());}handle.epoch()}};
    if request["action"]=="status"{
        if object.len()!=2{return Err("眼形查询字段无效".into());}
        let m=mailbox().lock().map_err(|_|"眼形结果锁失败")?;
        if m.epoch!=epoch{return Ok(json!({"phase":"unavailable","request_id":id,"error":"引擎已重启，原请求结果未确认"}));}
        return Ok(m.host.status(id));
    }
    if request["action"]!="edit"||(object.len()!=8 && object.len()!=9)||!["document_id","face_id","gesture_id","control"].iter().all(|k|text(&request[*k]))
        ||!recipe(&request["recipe"])||!recipe(&request["base"])||!(request["control"]=="all"||KEYS.iter().any(|k|request["control"]==*k)){
        return Err("眼形编辑字段无效".into());
    }
    if let Some(context) = request.get("people_context") {
        if !crate::people_api::valid_context(context) { return Err("人物范围或版本信息无效".into()); }
    } else if object.len() != 8 { return Err("未识别的人像命令字段".into()); }
    if state.ready_caps.lock().map_err(|_|"能力锁失败")?["eye_shape_protocol"]!=2{return Err("引擎缺少确认式眼形协议".into());}
    {let mut m=mailbox().lock().map_err(|_|"眼形结果锁失败")?;
        if m.epoch!=epoch{m.epoch=epoch;m.host.reset(epoch);m.host.ready(epoch,true);}
        m.host.begin_bound(epoch,id,"edit",request["document_id"].as_str())?;}
    let mut command=request.clone();command.as_object_mut().unwrap().remove("action");command["cmd"]=json!("eye_shape");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
    // No interactive-key dropping: UI owns one pending operation and the latest intent.
    // A send error does not assert non-execution; original ID stays queryable.
    state.send_to_engine(command)?;Ok(json!({"requested":true}))
}
