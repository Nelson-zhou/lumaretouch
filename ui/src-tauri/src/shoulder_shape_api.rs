// SPDX-License-Identifier: GPL-3.0-or-later
//! Epoch-bound shoulder receipts with process-lifetime replay protection.
use std::{collections::{HashSet,VecDeque},sync::{Arc,Mutex,OnceLock}};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
const MAX_BYTES:usize=32*1024*1024;
const MAX_RECORDS:usize=32;
fn fields(v:&Value,keys:&[&str])->bool{v.as_object().is_some_and(|o|o.len()==keys.len()&&keys.iter().all(|key|o.contains_key(*key)))}
fn text(v:&Value)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&!s.contains('\0'))}
fn revision(v:&Value)->bool{v.as_u64().is_some_and(|n|n<=9_007_199_254_740_991)}
fn digest(v:&Value)->bool{v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))}
fn binding(v:&Value)->bool{fields(v,&["document_id","document_epoch","document_revision","asset_sha256"])&&text(&v["document_id"])&&text(&v["document_epoch"])&&revision(&v["document_revision"])&&digest(&v["asset_sha256"])}
fn body_ref(v:&Value)->bool{fields(v,&["asset_sha256","body_instance_id","analysis_revision"])&&digest(&v["asset_sha256"])&&text(&v["body_instance_id"])&&revision(&v["analysis_revision"])}
fn valid_request(action:&str,v:&Value)->bool{
 if v.to_string().len()>256*1024{return false;}
 match action {
  "view"=>fields(v,&[]),
  "status"=>fields(v,&["request_id"])&&text(&v["request_id"]),
  "analyse"=>fields(v,&["binding"])&&binding(&v["binding"]),
  "select"=>fields(v,&["binding","body_ref"])&&binding(&v["binding"])&&body_ref(&v["body_ref"]),
  "reanalyse"=>fields(v,&["binding","body_ref","candidate_ref","run_id","user_confirmed"])&&binding(&v["binding"])&&body_ref(&v["body_ref"])&&body_ref(&v["candidate_ref"])&&text(&v["run_id"])&&v["user_confirmed"]==true,
  "edit"=>fields(v,&["request_id","gesture_id","document_id","document_epoch","document_revision","state_revision","association_revision","people_association_revision","body_ref","action","payload"])
    &&["request_id","gesture_id","document_id","document_epoch"].iter().all(|k|text(&v[*k]))
    &&["document_revision","state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&v[*k]))&&body_ref(&v["body_ref"])
    &&matches!(v["action"].as_str(),Some("recipe"|"review"|"associate"|"unlink"|"body_status"|"operation_status"))&&v["payload"].is_object(),
  _=>false,
 }
}
struct Record{id:String,action:String,epoch:[u8;16],document:Option<String>,result:Option<Value>,bytes:usize}
#[derive(Default)]struct Mailbox{epoch:[u8;16],supported:bool,seen:HashSet<String>,records:VecDeque<Record>}
fn mailbox()->&'static Mutex<Mailbox>{static HOST:OnceLock<Mutex<Mailbox>>=OnceLock::new();HOST.get_or_init(||Mutex::new(Mailbox::default()))}
fn failure(id:&str,action:&str,error:&str,unknown:bool)->Value{json!({"event":"shoulder_shape_result","protocol":1,"request_id":id,"action":action,"success":false,"outcome_unknown":unknown,"error":error})}
fn terminal(id:&str,result:Value)->Value{json!({"phase":"done","request_id":id,"result":result})}
impl Mailbox{
 fn status(&self,id:&str)->Value{match self.records.iter().find(|r|r.id==id){Some(r)=>match &r.result{Some(value)=>terminal(id,value.clone()),None=>json!({"phase":"pending","request_id":id})},None=>json!({"phase":"unavailable","request_id":id,"outcome_unknown":true,"error":"肩部回执不可用，不能认定操作没有执行"})}}
 fn end(&mut self,epoch:[u8;16]){for r in &mut self.records{if r.epoch==epoch&&r.result.is_none(){let v=failure(&r.id,&r.action,"引擎退出前未确认肩部结果，请核对，不会自动重发",true);r.bytes=v.to_string().len();r.result=Some(v);}}if self.epoch==epoch{self.supported=false;}}
 fn finish(&mut self,id:&str,value:Value){if let Some(r)=self.records.iter_mut().find(|r|r.id==id&&r.result.is_none()){r.bytes=value.to_string().len();r.result=Some(value);}}
 fn begin(&mut self,epoch:[u8;16],id:&str,action:&str,document:Option<&str>)->Result<(),String>{
  if epoch==[0;16]||epoch!=self.epoch||!self.supported{return Err("引擎变化或未声明肩部协议，未提交".into());}
  if self.seen.contains(id){return Err("肩部请求身份已用过，不会重发".into());}
  if self.seen.len()>=65_536||self.records.len()>=MAX_RECORDS||self.records.iter().map(|r|if r.result.is_some(){r.bytes}else{8*1024*1024}).sum::<usize>()+8*1024*1024>MAX_BYTES{return Err("肩部回执预算已满，请先查询并释放已有结果".into());}
  self.seen.insert(id.into());self.records.push_back(Record{id:id.into(),action:action.into(),epoch,document:document.map(str::to_owned),result:None,bytes:0});Ok(())
 }
}
pub(crate) fn reset(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){let old=host.epoch;host.end(old);host.epoch=epoch;host.supported=false;}}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut host)=mailbox().lock(){if host.epoch==epoch{host.supported=supported;}}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){host.end(epoch);}}
fn valid_view(view:&Value)->bool{
 if !binding(&view["binding"])||!["state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&view[*k]))||!view["persons"].is_object()||!view["refusals"].is_array(){return false;}
 let recipe=&view["recipe"];
 if recipe["version"]!=1||!["square","width"].iter().all(|key|{let pair=&recipe[*key];pair["linked"].is_boolean()&&["left","right"].iter().all(|side|pair[*side].as_f64().is_some_and(|n|n.is_finite()&&n>=(if *key=="square"{0.0}else{-1.0})&&n<=1.0))}){return false;}
 if !view["selected_body_ref"].is_null()&&!body_ref(&view["selected_body_ref"]){return false;}
 view["bodies"].as_array().is_some_and(|bodies|bodies.len()<=128&&bodies.iter().all(|body|{
  body_ref(&body["body_ref"])&&body["body_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]
   &&body["enabled"].is_boolean()&&body["reviewed"].is_boolean()&&digest(&body["points_sha256"])
   &&body["source"]["sha256"]==view["binding"]["asset_sha256"]&&body["source"]["orientation"]=="exif_normalized_once"
   &&body["points"].as_array().is_some_and(|points|points.len()==33&&points.iter().enumerate().all(|(index,p)|{
    p["index"].as_u64()==Some(index as u64)&&["x","y","z","visibility","presence"].iter().all(|key|p[*key].as_f64().is_some_and(f64::is_finite))
   }))
 }))
}
fn valid_result(v:&Value,record:&Record)->bool{
 if v["event"]!="shoulder_shape_result"||v["protocol"]!=1||v["action"]!=record.action||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||v.to_string().len()>8*1024*1024{return false;}
 if v["success"]!=true{return v["error"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192);}
 let data=&v["result"];let view=&data["view"];
 if !data.is_object(){return false;}
 // An authoritative status receipt remains readable after source deletion/switch.
 if record.action=="status" {
  if data.get("view").is_some_and(|value|!valid_view(value))||data.get("model").is_some_and(|value|!value.is_object())||data.get("view_error").is_some_and(|value|!value.as_str().is_some_and(|message|message.len()<=4096)){return false;}
 } else if !valid_view(view)||record.document.as_deref().is_some_and(|id|view["binding"]["document_id"].as_str()!=Some(id))||!data["model"].is_object(){return false;}
 if let Some(source)=data.get("source_preview"){if !valid_view(view)||source["mime"]!="image/png"||!source["base64"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=7_000_000)||source["source_sha256"]!=view["binding"]["asset_sha256"]||!["width","height"].iter().all(|k|source[*k].as_u64().is_some_and(|n|(1..=1280).contains(&n))){return false;}}
 if let Some(candidates)=data.get("analysis_candidates") {
  if !text(&candidates["run_id"])||!candidates["bodies"].as_array().is_some_and(|b|b.len()<=4){return false;}
  let mut candidate_view=view.clone();candidate_view["bodies"]=candidates["bodies"].clone();candidate_view["selected_body_ref"]=Value::Null;
  if !valid_view(&candidate_view){return false;}
 }
 if record.action=="edit"||record.action=="status"{let r=&data["receipt"];if !text(&r["request_id"])||!matches!(r["phase"].as_str(),Some("done"|"pending"|"unavailable"))||(r["phase"]=="done"&&(!r["success"].is_boolean()||!r["outcome_unknown"].is_boolean())){return false;}}
 true
}
pub(crate) fn receive(epoch:[u8;16],v:&Value){let Some(id)=v["request_id"].as_str()else{return};let Ok(mut host)=mailbox().lock()else{return};let Some(record)=host.records.iter().find(|r|r.id==id&&r.epoch==epoch&&r.result.is_none())else{return};let result=if valid_result(v,record){v.clone()}else{failure(id,&record.action,"肩部回执无效，实际结果未知，请核对当前配方",true)};host.finish(id,result);}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="shoulder_shape"&&matches!(v["action"].as_str(),Some("view"|"status"))}
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String>{let epoch=command.as_object_mut().ok_or("肩部命令无效")?.remove("host_epoch").ok_or("肩部命令缺少引擎身份")?;if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("引擎已变化，未向新引擎重发肩部操作".into());}handle.send(command)}
#[tauri::command]
pub(crate) fn shoulder_shape(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 let id=request["request_id"].as_str().filter(|_|text(&request["request_id"])).ok_or("肩部请求身份无效")?;
 let action=request["action"].as_str().ok_or("肩部动作无效")?;
 if matches!(action,"mailbox_status"|"release"){
  if !fields(&request,&["action","request_id"]){return Err("肩部查询字段无效".into());}
  let mut host=mailbox().lock().map_err(|_|"肩部回执锁失败")?;
  if action=="mailbox_status"{return Ok(host.status(id));}
  if let Some(index)=host.records.iter().position(|r|r.id==id){if host.records[index].result.is_none(){return Ok(host.status(id));}host.records.remove(index);}
  return Ok(json!({"released":true,"request_id":id}));
 }
 let refused=|why:&str|terminal(id,failure(id,action,why,false));
 if !fields(&request,&["action","request_id","request"])||!valid_request(action,&request["request"]){return Ok(refused("肩部命令字段、版本或动作无效，未提交"));}
 let mut host=mailbox().lock().map_err(|_|"肩部回执锁失败")?;if host.seen.contains(id){return Ok(host.status(id));}drop(host);
 let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;let Some(handle)=guard.as_ref().filter(|h|h.is_alive())else{return Ok(refused("引擎不可用，未提交"));};handle.epoch()};
 let document=request["request"]["document_id"].as_str().or_else(||request["request"]["binding"]["document_id"].as_str());
 host=mailbox().lock().map_err(|_|"肩部回执锁失败")?;if host.seen.contains(id){return Ok(host.status(id));}if let Err(error)=host.begin(epoch,id,action,document){return Ok(refused(&error));}drop(host);
 let mut command=request.clone();command["cmd"]=json!("shoulder_shape");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
 let sent=if matches!(action,"view"|"status") {let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;match guard.as_ref(){Some(handle)=>enqueue(handle,command),None=>Err("引擎已停止，未提交".into())}}else{state.send_to_engine(command)};
 if let Err(error)=sent{let mut host=mailbox().lock().map_err(|_|"肩部回执锁失败")?;host.finish(id,failure(id,action,&error,false));return Ok(host.status(id));}
 Ok(json!({"phase":"pending","request_id":id,"requested":true}))
}

#[cfg(test)]
mod tests {
 use super::*;
 #[test] fn queries_never_accept_edit_payloads(){assert!(valid_request("view",&json!({})));assert!(!valid_request("view",&json!({"body_ref":{}})));assert!(!valid_request("install",&json!({})));}
 #[test] fn faces_are_never_body_references(){assert!(!body_ref(&json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":0})));}
 #[test] fn epoch_end_is_unknown_not_rollback(){let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.begin([1;16],"id","edit",Some("doc")).unwrap();host.end([1;16]);assert_eq!(host.status("id")["result"]["outcome_unknown"],true);host.records.clear();assert!(host.seen.contains("id"));}
 #[test] fn status_keeps_authoritative_receipt_without_current_source(){let record=Record{id:"outer".into(),action:"status".into(),epoch:[1;16],document:None,result:None,bytes:0};let value=json!({"event":"shoulder_shape_result","protocol":1,"request_id":"outer","action":"status","success":true,"outcome_unknown":false,"result":{"receipt":{"phase":"done","request_id":"inner","success":false,"outcome_unknown":false,"error":"rejected"},"view_error":"source missing"}});assert!(valid_result(&value,&record));let mut missing=value.clone();missing["result"]=json!({"view_error":"source missing"});assert!(!valid_result(&missing,&record));let mut malformed=value.clone();malformed["result"]["view"]=json!({});assert!(!valid_result(&malformed,&record));malformed=value.clone();malformed["result"]["model"]=json!(true);assert!(!valid_result(&malformed,&record));let non_status=Record{action:"view".into(),..record};let mut no_view=value.clone();no_view["action"]=json!("view");assert!(!valid_result(&no_view,&non_status));}

}
