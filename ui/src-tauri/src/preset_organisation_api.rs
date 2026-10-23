//! Catalogue metadata port. Reads receipts without resubmitting edits.
use std::sync::{Arc,Mutex,OnceLock};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,receipt_host::{ReceiptHost,ReceiptKind}};
struct OrganisationKind;
const ORGANISATION_ACTIONS:&[&str]=&["snapshot","receipt","category_create","category_rename","category_move","category_trash","category_restore","preset_rename","preset_move","preset_trash","preset_restore"];
fn hash(v:&Value)->bool { v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))) }
fn text(v:&Value)->bool { v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=256) }
fn receipt(v:&Value)->bool { text(&v["request_id"])&&text(&v["action"])&&hash(&v["request_hash"])&&hash(&v["revision"])&&v["generation"].as_u64().is_some_and(|n|n<9_007_199_254_740_992) }
impl ReceiptKind for OrganisationKind {
    const NAME:&'static str="preset organisation";
    const ACTIONS:&'static [&'static str]=ORGANISATION_ACTIONS;
    fn valid(v:&Value,_:Option<&str>)->bool {
        if v["protocol"]!=1||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||v["success"]==true&&v["outcome_unknown"]==true{return false;}
        if v["success"]!=true{return v["error"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192);}
        match v["action"].as_str(){
            Some("snapshot")=>{let c=&v["catalog"]; c["schema"]=="lrt.preset-organisation.v1"&&hash(&c["revision"])&&c["generation"].is_u64()&&c["categories"].is_array()&&c["presets"].is_array()&&c["errors"].is_array()},
            Some("receipt")=>text(&v["target_request_id"])&&v["found"].is_boolean()&&if v["found"]==true{receipt(&v["receipt"])&&v["receipt"]["request_id"]==v["target_request_id"]}else{v["receipt"].is_null()},
            _=>receipt(&v["receipt"])&&v["receipt"]["request_id"]==v["request_id"]&&v["receipt"]["action"]==v["action"],
        }
    }
    fn decorate_failure(v:&mut Value,_:Option<&str>){v["protocol"]=json!(1);}
}
fn mailbox()->&'static Mutex<ReceiptHost<OrganisationKind>>{static HOST:OnceLock<Mutex<ReceiptHost<OrganisationKind>>>=OnceLock::new();HOST.get_or_init(||Mutex::new(ReceiptHost::default()))}
pub(crate) fn reset(epoch:[u8;16]){if let Ok(mut h)=mailbox().lock(){h.reset(epoch)}}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut h)=mailbox().lock(){h.ready(epoch,supported)}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut h)=mailbox().lock(){h.ended(epoch)}}
pub(crate) fn receive(epoch:[u8;16],v:&Value){if let Ok(mut h)=mailbox().lock(){h.receive(epoch,v)}}
#[tauri::command]
pub(crate) fn preset_organisation(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    if !request.is_object()||request.to_string().len()>16384{return Err("目录请求过大或无效".into());}
    let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("缺少目录请求身份")?;
    let action=request["action"].as_str().ok_or("缺少目录操作")?;
    let engine=state.engine.lock().map_err(|_|"引擎锁失败")?;
    let handle=engine.as_ref().filter(|h|h.is_alive()).ok_or("引擎尚未启动")?;
    let mut host=mailbox().lock().map_err(|_|"目录回执锁失败")?;
    host.begin(handle.epoch(),id,action)?;
    let mut command=request.clone(); command["cmd"]=json!("preset_organisation");
    if let Err(error)=handle.send(command){host.failed(id,&error);}
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn preset_organisation_result(request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("目录查询身份无效".into());}
    Ok(mailbox().lock().map_err(|_|"目录回执锁失败")?.status(&request_id))
}
