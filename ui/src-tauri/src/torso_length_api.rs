// SPDX-License-Identifier: GPL-3.0-or-later
//! Epoch-bound torso length receipts with process-lifetime replay protection.
use std::{collections::{HashMap,VecDeque},sync::{Arc,Mutex,OnceLock}};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
const MAX_BYTES:usize=32*1024*1024;
const MAX_RECORDS:usize=32;
const MAX_SIGNATURE_BYTES:usize=16*1024*1024;
fn fields(v:&Value,keys:&[&str])->bool{v.as_object().is_some_and(|o|o.len()==keys.len()&&keys.iter().all(|key|o.contains_key(*key)))}
fn text(v:&Value)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b"_.:-".contains(&b)))}
fn revision(v:&Value)->bool{v.as_u64().is_some_and(|n|n<=9_007_199_254_740_991)}
fn digest(v:&Value)->bool{v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))}
fn binding(v:&Value)->bool{fields(v,&["document_id","document_epoch","document_revision","asset_sha256"])&&text(&v["document_id"])&&text(&v["document_epoch"])&&revision(&v["document_revision"])&&digest(&v["asset_sha256"])}
fn body_ref(v:&Value)->bool{fields(v,&["asset_sha256","body_instance_id","analysis_revision"])&&digest(&v["asset_sha256"])&&text(&v["body_instance_id"])&&revision(&v["analysis_revision"])}
fn face_ref(v:&Value)->bool{fields(v,&["asset_sha256","face_instance_id","analysis_revision"])&&digest(&v["asset_sha256"])&&text(&v["face_instance_id"])&&revision(&v["analysis_revision"])}
fn valid_request(action:&str,v:&Value)->bool{
 if v.to_string().len()>256*1024{return false;}
 match action {
  "view"=>fields(v,&[]),
  "status"=>fields(v,&["request_id"])&&text(&v["request_id"]),
  "select"=>fields(v,&["binding","body_ref"])&&binding(&v["binding"])&&body_ref(&v["body_ref"])&&v["body_ref"]["asset_sha256"]==v["binding"]["asset_sha256"],
  "edit"=>fields(v,&["request_id","gesture_id","document_id","document_epoch","document_revision","state_revision","association_revision","people_association_revision","body_ref","body_graph_sha256","people_graph_sha256","operation_id","action","payload"])
    &&["request_id","gesture_id","document_id","document_epoch"].iter().all(|k|text(&v[*k]))
    &&["document_revision","state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&v[*k]))&&body_ref(&v["body_ref"])
    &&digest(&v["body_graph_sha256"])&&digest(&v["people_graph_sha256"])&&v["operation_id"]=="lnx.torso_length.v1"
    &&valid_payload(v["action"].as_str().unwrap_or(""),&v["payload"])
    &&(v["action"]!="support_review"||v["payload"]["data"].get("associated_face_ref").map_or(true,|face|face["asset_sha256"]==v["body_ref"]["asset_sha256"])),
  _=>false,
 }
}
struct Record{id:String,action:String,epoch:[u8;16],binding:Option<Value>,receipt:Option<String>,result:Option<Value>,settled:bool,bytes:usize}
fn expected_binding(action:&str,request:&Value)->Option<Value>{match action{
 "select"=>Some(request["binding"].clone()),
 "edit"=>Some(json!({"document_id":request["document_id"],"document_epoch":request["document_epoch"],"document_revision":request["document_revision"],"asset_sha256":request["body_ref"]["asset_sha256"]})),
 _=>None,
}}
fn matches_binding(view:&Value,record:&Record)->bool{record.binding.as_ref().map_or(true,|expected|{
 ["document_id","document_epoch","asset_sha256"].iter().all(|key|view["binding"][*key]==expected[*key])&&view["binding"]["document_revision"].as_u64()>=expected["document_revision"].as_u64()
})}
#[derive(Default)]struct Mailbox{epoch:[u8;16],supported:bool,seen:HashMap<String,String>,signature_bytes:usize,records:VecDeque<Record>}
fn mailbox()->&'static Mutex<Mailbox>{static HOST:OnceLock<Mutex<Mailbox>>=OnceLock::new();HOST.get_or_init(||Mutex::new(Mailbox::default()))}
fn failure(id:&str,action:&str,error:&str,unknown:bool)->Value{json!({"event":"torso_length_result","protocol":1,"request_id":id,"action":action,"success":false,"outcome_unknown":unknown,"error":error})}
fn terminal(id:&str,result:Value)->Value{json!({"phase":"done","request_id":id,"result":result})}
impl Mailbox{
 fn status(&self,id:&str)->Value{match self.records.iter().find(|r|r.id==id){Some(r)=>match &r.result{Some(value)=>terminal(id,value.clone()),None=>json!({"phase":"pending","request_id":id})},None=>json!({"phase":"unavailable","request_id":id,"outcome_unknown":true,"error":"躯干长度回执不可用，不能认定操作没有执行"})}}
 fn end(&mut self,epoch:[u8;16]){for r in &mut self.records{if r.epoch==epoch&&r.result.is_none(){let v=failure(&r.id,&r.action,"引擎退出前未确认躯干长度结果，请核对，不会自动重发",true);r.bytes=v.to_string().len();r.result=Some(v);}}if self.epoch==epoch{self.supported=false;}}
 fn finish(&mut self,id:&str,value:Value){if let Some(r)=self.records.iter_mut().find(|r|r.id==id&&r.result.is_none()){r.bytes=value.to_string().len();r.settled|=value["outcome_unknown"]==false&&(value.get("result").is_none()||value["result"]["receipt"]["phase"]=="done");r.result=Some(value);}}
 // Tombstones retain exact canonical content through release and epoch changes.
 // 16 MiB serialized payload/key retention budget, not a total allocator bound.
 fn replay(&self,id:&str,signature:&str)->Result<bool,String>{match self.seen.get(id){None=>Ok(false),Some(old) if old==signature=>Ok(true),Some(_)=>Err("躯干长度请求身份对应的内容已改变，未提交，也不会返回其他请求的成功结果".into())}}
 fn begin(&mut self,epoch:[u8;16],id:&str,action:&str,request:&Value,signature:&str)->Result<(),String>{
  if epoch==[0;16]||epoch!=self.epoch||!self.supported{return Err("引擎变化或未声明躯干长度协议，未提交".into());}
  if self.replay(id,signature)?{return Err("躯干长度请求身份已用过，不会重发".into());}
  if self.signature_bytes.saturating_add(signature.len()+id.len())>MAX_SIGNATURE_BYTES||self.seen.len()>=65_536{return Err("躯干长度进程级防重放记录预算已满；先核对未完成请求，释放回执不会删除身份记录".into());}
  if self.records.len()>=MAX_RECORDS||self.records.iter().map(|r|if r.result.is_some(){r.bytes}else{8*1024*1024}).sum::<usize>()+8*1024*1024>MAX_BYTES{return Err("躯干长度回执预算已满，请先查询并释放已有结果".into());}
  self.signature_bytes+=signature.len()+id.len();self.seen.insert(id.into(),signature.into());self.records.push_back(Record{id:id.into(),action:action.into(),epoch,binding:expected_binding(action,request),receipt:request["request_id"].as_str().map(str::to_owned),result:None,settled:false,bytes:0});Ok(())
 }
}
pub(crate) fn reset(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){let old=host.epoch;host.end(old);host.epoch=epoch;host.supported=false;}}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut host)=mailbox().lock(){if host.epoch==epoch{host.supported=supported;}}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){host.end(epoch);}}
fn unit(v:&Value)->bool{v.as_f64().is_some_and(|n|n.is_finite()&&(-1.0..=1.0).contains(&n))}
fn normalized(v:&Value)->bool{v.as_f64().is_some_and(|n|n.is_finite()&&n>0.0&&n<1.0)}
fn recipe(v:&Value)->bool{fields(v,&["version","amount"])&&v["version"]==1&&unit(&v["amount"])}
fn box_valid(v:&Value)->bool{v.as_array().is_some_and(|a|a.len()==4&&a.iter().all(normalized)&&a[0].as_f64()<a[2].as_f64()&&a[1].as_f64()<a[3].as_f64())}
fn support(v:&Value)->bool{support_input(v,false)}
fn support_input(v:&Value,allow_draft:bool)->bool{
 let flags=["joints_visible","upright_not_foreshortened","ownership_confirmed","complete_head_hair_reviewed","complete_arms_hands_reviewed","background_transition_reviewed","no_occlusion_or_contacts"];
 let base=["version","method","outer_left","inner_left","inner_right","outer_right","upper_zero","upper_plateau","head_box","left_arm_box","right_arm_box","confirmations"];
 let full=["version","method","outer_left","inner_left","inner_right","outer_right","upper_zero","upper_plateau","head_box","left_arm_box","right_arm_box","confirmations","associated_face_ref","associated_face_box","associated_face_evidence_sha256"];
 let complete=fields(v,&full);
 if !(complete||(allow_draft&&fields(v,&base)))||v["version"]!=1||v["method"]!="user-reviewed-visible-torso-length-support"||!fields(&v["confirmations"],&flags)||!flags.iter().all(|k|v["confirmations"][*k]==true){return false;}
 if !["outer_left","inner_left","inner_right","outer_right","upper_zero","upper_plateau"].iter().all(|k|normalized(&v[*k]))
  ||!(v["outer_left"].as_f64()<v["inner_left"].as_f64()&&v["inner_left"].as_f64()<v["inner_right"].as_f64()&&v["inner_right"].as_f64()<v["outer_right"].as_f64()&&v["upper_zero"].as_f64()<v["upper_plateau"].as_f64()){return false;}
 for key in ["head_box","left_arm_box","right_arm_box"]{let b=&v[key];if !box_valid(b)||!(v["inner_left"].as_f64()<b[0].as_f64()&&b[2].as_f64()<v["inner_right"].as_f64()&&v["upper_plateau"].as_f64()<b[1].as_f64()){return false;}}
 if complete{let head=&v["head_box"];let face=&v["associated_face_box"];if !face_ref(&v["associated_face_ref"])||!digest(&v["associated_face_evidence_sha256"])||!box_valid(face)||!(head[0].as_f64()<face[0].as_f64()&&head[1].as_f64()<face[1].as_f64()&&face[2].as_f64()<head[2].as_f64()&&face[3].as_f64()<head[3].as_f64()){return false;}}
 true
}
fn valid_payload(action:&str,v:&Value)->bool{match action{
 "recipe"=>fields(v,&["recipe","base"])&&recipe(&v["recipe"])&&recipe(&v["base"]),
 "support_review"=>fields(v,&["data","points_sha256","visible_anchors","ownership_confirmed"])&&support_input(&v["data"],true)&&digest(&v["points_sha256"])&&v["visible_anchors"].as_array().is_some_and(|a|a.len()==25&&a.iter().enumerate().all(|(i,n)|n.as_u64()==Some(i as u64)))&&v["ownership_confirmed"]==true,
 "operation_status"=>fields(v,&["enabled"])&&v["enabled"].is_boolean(),_=>false,
}}
fn dimensions(v:&Value)->bool{["width","height"].iter().all(|key|v[*key].as_u64().is_some_and(|n|(2..=1_000_000).contains(&n)))}
fn valid_view(view:&Value)->bool{
 if !binding(&view["binding"])||!["state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&view[*k]))||!digest(&view["body_graph_sha256"])||!digest(&view["people_graph_sha256"])||!view["refusals"].is_array()||!recipe(&view["recipe"]){return false;}
 if !view["selected_body_ref"].is_null()&&(!body_ref(&view["selected_body_ref"])||view["selected_body_ref"]["asset_sha256"]!=view["binding"]["asset_sha256"]){return false;}
 view["bodies"].as_array().is_some_and(|bodies|bodies.len()<=128&&(view["selected_body_ref"].is_null()||bodies.iter().any(|body|body["body_ref"]==view["selected_body_ref"]))&&bodies.iter().all(|body|{
  body_ref(&body["body_ref"])&&body["body_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]
   &&body["enabled"].is_boolean()&&body["operation_enabled"].is_boolean()&&body["reviewed"].is_boolean()&&digest(&body["points_sha256"])
   &&fields(&body["source"],&["sha256","width","height","orientation"])&&body["source"]["sha256"]==view["binding"]["asset_sha256"]&&body["source"]["orientation"]=="exif_normalized_once"&&dimensions(&body["source"])
   &&(body["support"].is_null()||(support(&body["support"])&&body["support"]["associated_face_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]))
   &&body["points"].as_array().is_some_and(|points|points.len()==33&&points.iter().enumerate().all(|(index,p)|{
    fields(p,&["index","x","y","z","visibility","presence"])&&p["index"].as_u64()==Some(index as u64)&&["x","y","z","visibility","presence"].iter().all(|key|p[*key].as_f64().is_some_and(f64::is_finite))&&["visibility","presence"].iter().all(|key|p[*key].as_f64().is_some_and(|n|(0.0..=1.0).contains(&n)))
   }))
 }))
}
fn valid_source(source:&Value,view:&Value)->bool{
 if !fields(source,&["mime","base64","source_sha256","source_width","source_height","decoded_width","decoded_height","width","height","mapping","orientation"]){return false;}
 let (Some(sw),Some(sh),Some(dw),Some(dh))=(source["source_width"].as_u64(),source["source_height"].as_u64(),source["decoded_width"].as_u64(),source["decoded_height"].as_u64())else{return false};
 if [sw,sh,dw,dh].iter().any(|n|!(2..=1_000_000).contains(n)){return false;}
 if (dw!=sw||dh!=sh)&&(dw%8!=0||dh%8!=0||dw*sh>=(dh+8)*sw||dh*sw>=(dw+8)*sh){return false;}
 let (Some(pw),Some(ph))=(source["width"].as_u64(),source["height"].as_u64())else{return false};
 if pw>1280||ph>1280||pw<2||ph<2{return false;}
 if dw.max(dh)<=1280 {if pw!=dw||ph!=dh{return false;}}else if pw.max(ph)!=1280||(pw*dh).abs_diff(ph*dw)>dw.max(dh){return false;}
 source["mime"]=="image/png"&&source["base64"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=7_000_000)
 &&source["source_sha256"]==view["binding"]["asset_sha256"]&&source["mapping"]=="normalized_full_frame"&&source["orientation"]=="exif_normalized_once"
 &&["width","height"].iter().all(|key|source[*key].as_u64().is_some_and(|n|(2..=1280).contains(&n)))
 &&[("source_width","decoded_width","width"),("source_height","decoded_height","height")].iter().all(|(original,decoded,display)|{
  let (Some(o),Some(d),Some(p))=(source[*original].as_u64(),source[*decoded].as_u64(),source[*display].as_u64())else{return false};o>=2&&o<=1_000_000&&d>=2&&d<=o&&p<=d
 })
 &&view["bodies"].as_array().is_some_and(|bodies|bodies.iter().all(|body|body["source"]["width"]==source["source_width"]&&body["source"]["height"]==source["source_height"]))
}
fn valid_result(v:&Value,record:&Record)->bool{
 if v["event"]!="torso_length_result"||v["protocol"]!=1||v["request_id"]!=record.id||v["action"]!=record.action||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||v.to_string().len()>8*1024*1024{return false;}
 if v["success"]!=true{
  if !v["error"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192){return false;}
  if v.get("result").is_none(){return true;}
 }
 let data=&v["result"];let view=&data["view"];
 if !data.is_object(){return false;}
 // An authoritative status receipt remains readable after source deletion/switch.
 if record.action=="status" {
  if data.get("view").is_some_and(|value|!valid_view(value))||data.get("model").is_some_and(|value|!value.is_object())||data.get("view_error").is_some_and(|value|!value.as_str().is_some_and(|message|message.len()<=4096)){return false;}
 } else if !valid_view(view)||!matches_binding(view,record)||!data["model"].is_object(){return false;}
 if matches!(record.action.as_str(),"view"|"select")&&data.get("source_preview").is_none(){return false;}
 if let Some(source)=data.get("source_preview"){if !valid_view(view)||!valid_source(source,view){return false;}}
 if record.action=="edit"||record.action=="status"{let r=&data["receipt"];if !text(&r["request_id"])||r["request_id"].as_str()!=record.receipt.as_deref()||!matches!(r["phase"].as_str(),Some("done"|"pending"|"unavailable"))||(r["phase"]=="done"&&(!r["success"].is_boolean()||!r["outcome_unknown"].is_boolean())){return false;}
  if r["success"]==true&&(r["phase"]!="done"||r["outcome_unknown"]!=false||!valid_view(&r["view"])){return false;}
  if record.action=="edit"&&(v["success"]!=r["success"]||v["outcome_unknown"]!=r["outcome_unknown"]){return false;}
 }
 if let Some(receipt_view)=data["receipt"].get("view"){if !valid_view(receipt_view)||!matches_binding(receipt_view,record){return false;}}
 true
}
pub(crate) fn receive(epoch:[u8;16],v:&Value)->bool{
 let Some(id)=v["request_id"].as_str()else{return false};let Ok(mut host)=mailbox().lock()else{return false};
 let Some(record)=host.records.iter().find(|r|r.id==id&&r.epoch==epoch&&r.result.is_none())else{return false};
 let valid=valid_result(v,record);let result=if valid{v.clone()}else{failure(id,&record.action,"躯干长度回执无效，实际结果未知，请核对当前配方",true)};
 if valid{
  if record.action!="edit"||v.get("result").is_none()||v["result"]["receipt"]["phase"]=="done"{crate::project_recovery_fence::observed(epoch,v);}
  // A read-only authoritative inner receipt can settle its original outer fence.
  // It never dispatches the edit again, even after a lost reply or source switch.
  let receipt=&v["result"]["receipt"];
  if record.action=="status"&&receipt["phase"]=="done"&&receipt["outcome_unknown"]==false&&receipt["success"].is_boolean(){
   let resolved:Vec<String>=host.records.iter().filter(|r|r.epoch==epoch&&r.action=="edit"&&r.receipt.as_deref()==receipt["request_id"].as_str()&&(receipt["success"]==false||matches_binding(&receipt["view"],r))).map(|r|r.id.clone()).collect();
   for original in resolved{
    crate::project_recovery_fence::observed(epoch,&json!({"event":"torso_length_result","request_id":original,"success":receipt["success"],"outcome_unknown":false}));
    if let Some(retained)=host.records.iter_mut().find(|r|r.id==original){retained.settled=true;}
   }
  }
 }
 host.finish(id,result);valid
}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="torso_length"&&matches!(v["action"].as_str(),Some("view"|"status"))}
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String>{let epoch=command.as_object_mut().ok_or("躯干长度命令无效")?.remove("host_epoch").ok_or("躯干长度命令缺少引擎身份")?;if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("引擎已变化，未向新引擎重发躯干长度操作".into());}handle.send(command)}
#[tauri::command]
pub(crate) fn torso_length(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 let id=request["request_id"].as_str().filter(|_|text(&request["request_id"])).ok_or("躯干长度请求身份无效")?;
 let action=request["action"].as_str().ok_or("躯干长度动作无效")?;
 if matches!(action,"mailbox_status"|"release"){
  if !fields(&request,&["action","request_id"]){return Err("躯干长度查询字段无效".into());}
  let mut host=mailbox().lock().map_err(|_|"躯干长度回执锁失败")?;
  if action=="mailbox_status"{return Ok(host.status(id));}
  if let Some(index)=host.records.iter().position(|r|r.id==id){let retained=&host.records[index];if !retained.settled&&retained.result.is_none(){return Ok(host.status(id));}host.records.remove(index);}
  return Ok(json!({"released":true,"request_id":id}));
 }
 let refused=|why:&str|terminal(id,failure(id,action,why,false));
 if !fields(&request,&["action","request_id","request"])||!valid_request(action,&request["request"])||(action=="edit"&&request["request"]["request_id"]==id){return Ok(refused("躯干长度命令字段、版本或动作无效，未提交"));}
 let signature=request.to_string();
 let mut host=mailbox().lock().map_err(|_|"躯干长度回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}drop(host);
 let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;let Some(handle)=guard.as_ref().filter(|h|h.is_alive())else{return Ok(refused("引擎不可用，未提交"));};handle.epoch()};
 host=mailbox().lock().map_err(|_|"躯干长度回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}if let Err(error)=host.begin(epoch,id,action,&request["request"],&signature){return Ok(refused(&error));}drop(host);
 let mut command=request.clone();command["cmd"]=json!("torso_length");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
 let sent=if matches!(action,"view"|"status") {match state.engine.lock(){Ok(guard)=>match guard.as_ref(){Some(handle)=>enqueue(handle,command),None=>Err("引擎已停止，未提交".into())},Err(_)=>Err("引擎锁失败，未提交".into())}}else{state.send_to_engine(command)};
 if let Err(error)=sent{let result=failure(id,action,&error,false);crate::project_recovery_fence::observed(epoch,&result);let mut host=mailbox().lock().map_err(|_|"躯干长度回执锁失败")?;host.finish(id,result);return Ok(host.status(id));}
 Ok(json!({"phase":"pending","request_id":id,"requested":true}))
}

#[cfg(test)]
mod tests {
 use super::*;
 // Authored UNRUN: altered action/payload cannot reuse an old success, even after release.
 #[test] fn immutable_signature_survives_release_and_epoch(){
  let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
  let original=json!({"action":"view","request_id":"same","request":{}}).to_string();
  host.begin([1;16],"same","view",&json!({}),&original).unwrap();assert_eq!(host.replay("same",&original).unwrap(),true);
  for changed in [json!({"action":"select","request_id":"same","request":{}}),json!({"action":"view","request_id":"same","request":{"changed":true}})]{assert!(host.replay("same",&changed.to_string()).is_err());}
  host.records.clear();host.end([1;16]);assert!(host.replay("same","altered").is_err());assert!(host.replay("same",&original).unwrap());assert_eq!(host.status("same")["phase"],"unavailable");
 }
 #[test] fn signature_retention_has_byte_budget(){let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.signature_bytes=MAX_SIGNATURE_BYTES;assert!(host.begin([1;16],"new","view",&json!({}),"{}").is_err());assert!(!host.seen.contains_key("new"));}
 #[test] fn queries_never_accept_edit_payloads(){assert!(valid_request("view",&json!({})));assert!(!valid_request("view",&json!({"body_ref":{}})));assert!(!valid_request("install",&json!({})));}
 #[test] fn faces_are_never_body_references(){assert!(!body_ref(&json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":0})));}
 #[test] fn epoch_end_is_unknown_not_rollback(){let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.begin([1;16],"id","edit",&json!({"request_id":"inner"}),"original").unwrap();host.end([1;16]);assert_eq!(host.status("id")["result"]["outcome_unknown"],true);host.records.clear();assert!(host.seen.contains_key("id"));}
 fn status_record()->Record{Record{id:"outer".into(),action:"status".into(),epoch:[1;16],binding:None,receipt:Some("inner".into()),result:None,settled:false,bytes:0}}
 fn status_result()->Value{json!({"event":"torso_length_result","protocol":1,"request_id":"outer","action":"status","success":true,"outcome_unknown":false,"result":{"receipt":{"phase":"done","request_id":"inner","success":false,"outcome_unknown":false,"error":"rejected"},"view_error":"source missing"}})}
 #[test] fn status_keeps_authoritative_receipt_without_current_source(){
  let record=status_record();let value=status_result();assert!(valid_result(&value,&record));
  let mut missing=value.clone();missing["result"]=json!({"view_error":"source missing"});assert!(!valid_result(&missing,&record));
  let mut malformed=value.clone();malformed["result"]["view"]=json!({});assert!(!valid_result(&malformed,&record));
  malformed=value.clone();malformed["result"]["model"]=json!(true);assert!(!valid_result(&malformed,&record));
  let non_status=Record{action:"view".into(),..record};let mut no_view=value.clone();no_view["action"]=json!("view");assert!(!valid_result(&no_view,&non_status));
 }
 #[test] fn receipt_identifiers_cannot_be_swapped_even_on_failure(){
  let record=status_record();let value=status_result();
  for key in ["request_id","action","event"]{let mut wrong=value.clone();wrong[key]=json!("other");assert!(!valid_result(&wrong,&record));}
  let mut wrong=value.clone();wrong["result"]["receipt"]["request_id"]=json!("other-inner");assert!(!valid_result(&wrong,&record));
  wrong["success"]=json!(false);wrong["error"]=json!("failed");assert!(!valid_result(&wrong,&record));
  let mut unsupported_success=value.clone();unsupported_success["result"]["receipt"]["success"]=json!(true);assert!(!valid_result(&unsupported_success,&record));
 }
 #[test] fn recipe_is_only_signed_amount(){
  for amount in [-1.0,0.0,1.0]{assert!(recipe(&json!({"version":1,"amount":amount})));}
  for value in [json!({"version":1,"amount":1.01}),json!({"version":1,"amount":true}),json!({"version":1,"thigh":0,"calf":0}),json!({"version":1,"amount":0,"linked":true})]{assert!(!recipe(&value));}
 }
 #[test] fn source_correspondence_requires_decoded_whole_canvas(){
  let view=json!({"binding":{"asset_sha256":"a".repeat(64)},"bodies":[]});
  let source=json!({"mime":"image/png","base64":"fixture","source_sha256":"a".repeat(64),"source_width":4000,"source_height":3000,"decoded_width":2048,"decoded_height":1536,"width":1280,"height":960,"mapping":"normalized_full_frame","orientation":"exif_normalized_once"});
  assert!(valid_source(&source,&view));let mut wrong=source.clone();wrong["decoded_width"]=json!(1600);assert!(!valid_source(&wrong,&view));wrong=source.clone();wrong["height"]=json!(800);assert!(!valid_source(&wrong,&view));
 }
 fn reviewed_support()->Value{json!({"version":1,"method":"user-reviewed-visible-torso-length-support","outer_left":0.1,"inner_left":0.2,"inner_right":0.8,"outer_right":0.9,"upper_zero":0.02,"upper_plateau":0.06,"head_box":[0.4,0.1,0.6,0.3],"left_arm_box":[0.25,0.31,0.38,0.7],"right_arm_box":[0.62,0.31,0.75,0.7],"confirmations":{"joints_visible":true,"upright_not_foreshortened":true,"ownership_confirmed":true,"complete_head_hair_reviewed":true,"complete_arms_hands_reviewed":true,"background_transition_reviewed":true,"no_occlusion_or_contacts":true}})}
 #[test] fn explicit_support_draft_is_not_a_persisted_bound_support(){
  let draft=reviewed_support();assert!(support_input(&draft,true));assert!(!support(&draft));
  let mut full=draft.clone();full["associated_face_ref"]=json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face:actual","analysis_revision":3});assert!(!support_input(&full,true));
  full["associated_face_box"]=json!([0.43,0.14,0.57,0.26]);full["associated_face_evidence_sha256"]=json!("b".repeat(64));assert!(support(&full));
  let mut partial=full.clone();partial.as_object_mut().unwrap().remove("associated_face_evidence_sha256");assert!(!support_input(&partial,true));
  let mut crossed=full.clone();crossed["inner_left"]=json!(0.81);assert!(!support(&crossed));
  let mut incomplete=full.clone();incomplete["confirmations"]["complete_arms_hands_reviewed"]=json!(false);assert!(!support(&incomplete));
  let mut escaped=full.clone();escaped["head_box"]=json!([0.45,0.1,0.6,0.3]);assert!(!support(&escaped));
  let mut foreign=full.clone();foreign["associated_face_ref"]["body_instance_id"]=json!("body:wrong");assert!(!support(&foreign));
 }
 #[test] fn support_requires_every_real_upper_body_anchor(){
  let mut payload=json!({"data":reviewed_support(),"points_sha256":"c".repeat(64),"visible_anchors":(0..25).collect::<Vec<_>>(),"ownership_confirmed":true});assert!(valid_payload("support_review",&payload));
  payload["visible_anchors"]=json!([0,7,8,11,12,23,24]);assert!(!valid_payload("support_review",&payload));
 }
 #[test] fn non_torso_and_mutating_actions_are_not_read_only(){
  for action in ["view","status"]{assert!(read_only(&json!({"cmd":"torso_length","action":action})));}
  for action in ["select","edit","analyse","reanalyse","install"]{assert!(!read_only(&json!({"cmd":"torso_length","action":action})));}
  for operation in ["leg_length","neck_shape","shoulder_shape","people"]{assert!(!read_only(&json!({"cmd":operation,"action":"view"})));}
 }
 #[test] fn expected_source_epoch_and_revision_are_not_interchangeable(){
  let request=json!({"document_id":"doc","document_epoch":"doc-epoch","document_revision":7,"body_ref":{"asset_sha256":"a".repeat(64)}});
  let record=Record{action:"edit".into(),binding:expected_binding("edit",&request),..status_record()};
  let view=json!({"binding":record.binding.clone()});assert!(matches_binding(&view,&record));
  for (key,value) in [("asset_sha256",json!("b".repeat(64))),("document_epoch",json!("other")),("document_id",json!("other")),("document_revision",json!(6))]{let mut stale=view.clone();stale["binding"][key]=value;assert!(!matches_binding(&stale,&record));}
 }
 #[test] fn startup_requires_ready_for_the_exact_epoch(){
  let mut host=Mailbox::default();host.epoch=[7;16];assert!(host.begin([7;16],"one","view",&json!({}),"one").is_err());
  host.supported=true;assert!(host.begin([8;16],"two","view",&json!({}),"two").is_err());assert!(host.begin([7;16],"three","view",&json!({}),"three").is_ok());
 }
 #[test] fn only_correlated_authoritative_status_settles_the_original_fence(){
  let epoch=[217;16];reset(epoch);ready(epoch,true);
  let original=json!({"cmd":"torso_length","action":"edit","request_id":"torso-fixture-original"});
  crate::project_recovery_fence::issued(epoch,&original).unwrap();
  {let mut host=mailbox().lock().unwrap();host.begin(epoch,"torso-fixture-original","edit",&json!({"request_id":"torso-inner"}),"original").unwrap();host.begin(epoch,"torso-fixture-status","status",&json!({"request_id":"torso-inner"}),"status").unwrap();}
  let mut reply=status_result();reply["request_id"]=json!("torso-fixture-status");reply["result"]["receipt"]["request_id"]=json!("wrong-inner");
  assert!(!receive([216;16],&reply));assert!(crate::project_recovery_fence::proof(epoch).is_err());
  assert!(!receive(epoch,&reply));assert!(crate::project_recovery_fence::proof(epoch).is_err());
  {let mut host=mailbox().lock().unwrap();host.begin(epoch,"torso-fixture-status-2","status",&json!({"request_id":"torso-inner"}),"status-2").unwrap();}
  reply["request_id"]=json!("torso-fixture-status-2");reply["result"]["receipt"]["request_id"]=json!("torso-inner");assert!(receive(epoch,&reply));assert!(crate::project_recovery_fence::proof(epoch).is_ok());
  assert_eq!(mailbox().lock().unwrap().status("torso-fixture-original")["phase"],"pending"); // Querying did not replay or invent an outer response.
  assert!(mailbox().lock().unwrap().records.iter().find(|r|r.id=="torso-fixture-original").unwrap().settled); // Safe release is allowed after authoritative inner readback.
 }

}
