// SPDX-License-Identifier: GPL-3.0-or-later
//! Reuses the bounded canonical receipt ledger; this module owns no image/history state.
use std::sync::{Arc,Mutex,OnceLock};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,receipt_host::{ReceiptHost,ReceiptKind}};
const MARKER:&str="limb_vein_request";
struct Kind;
impl ReceiptKind for Kind {
    const NAME:&'static str="limb_vein";
    const ACTIONS:&'static [&'static str]=&["reference","preview","confirm","clear","status"];
    fn valid(v:&Value,document:Option<&str>)->bool {
        v["event"]=="limb_vein_result"&&v["protocol"]==1&&v["document_id"].as_str()==document
          &&v["success"].is_boolean()&&v["outcome_unknown"].is_boolean()
          &&check(&v[MARKER]).is_ok()&&matches_request(&v[MARKER],v)
          &&(!(v["success"]==true)||(v["outcome_unknown"]==false&&v["payload"]["protocol"]==1&&v["payload"]["family"]=="limb_vein"))
          &&(!(v["success"]==true&&mutation(&v[MARKER]))||
              (v["doc_state"]["document_id"]==v["document_id"]
               &&v["doc_state"]["limb_vein"]["amount"]==v["payload"]["amount"]
               &&v["doc_state"]["limb_vein"]["recipe_sha256"]==v["payload"]["candidate_sha256"]
               &&v["doc_state"]["limb_vein"]["revision"].as_str().is_some_and(|r|!r.is_empty()&&r.bytes().all(|b|b.is_ascii_digit()))))
    }
    fn decorate_failure(v:&mut Value,document:Option<&str>){v["document_id"]=json!(document);}
}
struct Mailbox{epoch:[u8;16],host:ReceiptHost<Kind>}
fn store()->&'static Mutex<Mailbox>{static STORE:OnceLock<Mutex<Mailbox>>=OnceLock::new();STORE.get_or_init(||Mutex::new(Mailbox{epoch:[0;16],host:ReceiptHost::default()}))}
fn text(v:&Value)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&!s.chars().any(char::is_control))}
pub(crate) fn check(v:&Value)->Result<(),String>{
    let o=v.as_object().ok_or("Invalid limb vein request")?;
    if o.len()!=7||!["cmd","protocol","request_id","action","document_id","revision","payload"].iter().all(|k|o.contains_key(*k)){return Err("Unknown limb vein envelope fields".into());}
    if v["cmd"]!="limb_vein"||v["protocol"]!=1||!text(&v["request_id"])||!text(&v["document_id"])
      ||!v["revision"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=20&&s.bytes().all(|c|c.is_ascii_digit()))
      ||!Kind::ACTIONS.contains(&v["action"].as_str().unwrap_or(""))||!v["payload"].is_object()
      ||v.to_string().len()>512*1024{return Err("Invalid or oversized limb vein request".into());}
    Ok(())
}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="limb_vein"&&matches!(v["action"].as_str(),Some("reference"|"preview"|"status"))&&check(v).is_ok()}
pub(crate) fn mutation(v:&Value)->bool{v["cmd"]=="limb_vein"&&matches!(v["action"].as_str(),Some("confirm"|"clear"))}
pub(crate) fn binding(v:&Value)->Result<Option<Value>,String>{if v["cmd"]!="limb_vein"{return Ok(None);}check(v)?;Ok(Some(json!({"limb_vein_request":v})))}
pub(crate) fn matches_request(request:&Value,result:&Value)->bool{result["event"]=="limb_vein_result"&&result["protocol"]==1&&result[MARKER]==*request&&result["request_id"]==request["request_id"]&&result["action"]==request["action"]&&result["revision"]==request["revision"]&&result["document_id"]==request["document_id"]}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut m)=store().lock(){if m.epoch!=epoch{m.epoch=epoch;m.host.reset(epoch);}m.host.ready(epoch,supported);}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut m)=store().lock(){m.host.ended(epoch);}}
pub(crate) fn guards_review(epoch:[u8;16],id:&str)->bool{store().lock().map(|m|m.host.guards_review(epoch,id)).unwrap_or(true)}
pub(crate) fn receive(epoch:[u8;16],v:&Value)->Option<Value>{
    let id=v["request_id"].as_str()?;
    let mut m=store().lock().ok()?;
    if m.epoch!=epoch{return None;}
    m.host.receive(epoch,v);
    let status=m.host.status(id);let result=status.get("result")?;
    if result["success"]==true&&result["outcome_unknown"]==false&&result["event"]=="limb_vein_result"{Some(result.clone())}else{None}
}
pub(crate) fn enqueue(handle:&crate::engine::EngineHandle,command:Value)->Result<(),String>{
    check(&command)?;let id=command["request_id"].as_str().unwrap().to_owned();let epoch=handle.epoch();
    store().lock().map_err(|_|"Vein receipt lock failed")?.host.begin_command(epoch,&command)?;
    let sent=handle.send(command);
    if let Err(error)=&sent{store().lock().map_err(|_|"Vein receipt lock failed")?.host.failed(&id,error);}
    sent
}
#[tauri::command]
pub(crate) fn limb_vein_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    check(&request)?;let id=request["request_id"].clone();
    let epoch=state.engine.lock().map_err(|_|"Engine lock failed")?.as_ref().ok_or("Engine offline")?.epoch();
    state.send_to_engine_at_epoch(request,epoch)?;Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn limb_vein_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("Invalid vein receipt identity".into());}
    let epoch=state.engine.lock().map_err(|_|"Engine lock failed")?.as_ref().map(|h|h.epoch());
    let m=store().lock().map_err(|_|"Vein receipt lock failed")?;
    if epoch!=Some(m.epoch){return Ok(json!({"phase":"unavailable","request_id":request_id,"error":"Original engine changed; no request was resent"}));}
    Ok(m.host.status(&request_id))
}
