// SPDX-License-Identifier: GPL-3.0-or-later
//! Epoch-bound leg length receipts with process-lifetime replay protection.
use std::{collections::{HashMap,VecDeque},sync::{Arc,Mutex,OnceLock}};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
const MAX_BYTES:usize=32*1024*1024;
const MAX_RECORDS:usize=32;
const MAX_SIGNATURE_BYTES:usize=16*1024*1024;
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
  "select"=>fields(v,&["binding","body_ref"])&&binding(&v["binding"])&&body_ref(&v["body_ref"]),
  "edit"=>fields(v,&["request_id","gesture_id","document_id","document_epoch","document_revision","state_revision","association_revision","people_association_revision","body_ref","body_graph_sha256","people_graph_sha256","operation_id","action","payload"])
    &&["request_id","gesture_id","document_id","document_epoch"].iter().all(|k|text(&v[*k]))
    &&["document_revision","state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&v[*k]))&&body_ref(&v["body_ref"])
    &&digest(&v["body_graph_sha256"])&&digest(&v["people_graph_sha256"])&&v["operation_id"]=="lnx.leg_length.v1"
    &&valid_payload(v["action"].as_str().unwrap_or(""),&v["payload"]),
  _=>false,
 }
}
struct Record{id:String,action:String,epoch:[u8;16],document:Option<String>,result:Option<Value>,bytes:usize}
#[derive(Default)]struct Mailbox{epoch:[u8;16],supported:bool,seen:HashMap<String,String>,signature_bytes:usize,records:VecDeque<Record>}
fn mailbox()->&'static Mutex<Mailbox>{static HOST:OnceLock<Mutex<Mailbox>>=OnceLock::new();HOST.get_or_init(||Mutex::new(Mailbox::default()))}
fn failure(id:&str,action:&str,error:&str,unknown:bool)->Value{json!({"event":"leg_length_result","protocol":1,"request_id":id,"action":action,"success":false,"outcome_unknown":unknown,"error":error})}
fn terminal(id:&str,result:Value)->Value{json!({"phase":"done","request_id":id,"result":result})}
impl Mailbox{
 fn status(&self,id:&str)->Value{match self.records.iter().find(|r|r.id==id){Some(r)=>match &r.result{Some(value)=>terminal(id,value.clone()),None=>json!({"phase":"pending","request_id":id})},None=>json!({"phase":"unavailable","request_id":id,"outcome_unknown":true,"error":"腿长回执不可用，不能认定操作没有执行"})}}
 fn end(&mut self,epoch:[u8;16]){for r in &mut self.records{if r.epoch==epoch&&r.result.is_none(){let v=failure(&r.id,&r.action,"引擎退出前未确认腿长结果，请核对，不会自动重发",true);r.bytes=v.to_string().len();r.result=Some(v);}}if self.epoch==epoch{self.supported=false;}}
 fn finish(&mut self,id:&str,value:Value){if let Some(r)=self.records.iter_mut().find(|r|r.id==id&&r.result.is_none()){r.bytes=value.to_string().len();r.result=Some(value);}}
 // Tombstones retain exact canonical content through release and epoch changes.
 // 16 MiB serialized payload/key retention budget, not a total allocator bound.
 fn replay(&self,id:&str,signature:&str)->Result<bool,String>{match self.seen.get(id){None=>Ok(false),Some(old) if old==signature=>Ok(true),Some(_)=>Err("腿长请求身份对应的内容已改变，未提交，也不会返回其他请求的成功结果".into())}}
 fn begin(&mut self,epoch:[u8;16],id:&str,action:&str,document:Option<&str>,signature:&str)->Result<(),String>{
  if epoch==[0;16]||epoch!=self.epoch||!self.supported{return Err("引擎变化或未声明腿长协议，未提交".into());}
  if self.replay(id,signature)?{return Err("腿长请求身份已用过，不会重发".into());}
  if self.signature_bytes.saturating_add(signature.len()+id.len())>MAX_SIGNATURE_BYTES||self.seen.len()>=65_536{return Err("腿长进程级防重放记录预算已满；先核对未完成请求，释放回执不会删除身份记录".into());}
  if self.records.len()>=MAX_RECORDS||self.records.iter().map(|r|if r.result.is_some(){r.bytes}else{8*1024*1024}).sum::<usize>()+8*1024*1024>MAX_BYTES{return Err("腿长回执预算已满，请先查询并释放已有结果".into());}
  self.signature_bytes+=signature.len()+id.len();self.seen.insert(id.into(),signature.into());self.records.push_back(Record{id:id.into(),action:action.into(),epoch,document:document.map(str::to_owned),result:None,bytes:0});Ok(())
 }
}
pub(crate) fn reset(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){let old=host.epoch;host.end(old);host.epoch=epoch;host.supported=false;}}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut host)=mailbox().lock(){if host.epoch==epoch{host.supported=supported;}}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut host)=mailbox().lock(){host.end(epoch);}}
fn unit(v:&Value)->bool{v.as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n))}
fn recipe(v:&Value)->bool{fields(v,&["version","thigh","calf"])&&v["version"]==1&&unit(&v["thigh"])&&unit(&v["calf"])}
fn support(v:&Value)->bool{
 let flags=["joints_visible","separate_legs","not_foreshortened","ownership_confirmed","background_support_reviewed","foot_contours_visible","torso_transition_reviewed"];
 let keys=["version","method","legs","joints_visible","separate_legs","not_foreshortened","ownership_confirmed","background_support_reviewed","foot_contours_visible","torso_transition_reviewed"];
 if !fields(v,&keys)||v["version"]!=1||v["method"]!="user-reviewed-visible-length-support"||!flags.iter().all(|k|v[*k]==true)||!fields(&v["legs"],&["left","right"]){return false;}
 let columns=["outer_left","inner_left","inner_right","outer_right","foot_end","support_end"];
 for side in ["left","right"]{let s=&v["legs"][side];if !fields(s,&columns)||!columns.iter().all(|k|s[*k].as_f64().is_some_and(|x|x.is_finite()&&x>0.0&&x<1.0)){return false;}
  if !(s["outer_left"].as_f64()<s["inner_left"].as_f64()&&s["inner_left"].as_f64()<s["inner_right"].as_f64()&&s["inner_right"].as_f64()<s["outer_right"].as_f64()&&s["foot_end"].as_f64()<s["support_end"].as_f64()){return false;}}
 let a=&v["legs"]["left"];let b=&v["legs"]["right"];a["outer_right"].as_f64()<b["outer_left"].as_f64()||b["outer_right"].as_f64()<a["outer_left"].as_f64()
}
fn valid_payload(action:&str,v:&Value)->bool{match action{
 "recipe"=>fields(v,&["recipe","base"])&&recipe(&v["recipe"])&&recipe(&v["base"]),
 "support_review"=>fields(v,&["data","points_sha256","visible_anchors","ownership_confirmed"])&&support(&v["data"])&&digest(&v["points_sha256"])&&v["visible_anchors"]==json!([23,24,25,26,27,28,29,30,31,32])&&v["ownership_confirmed"]==true,
 "operation_status"=>fields(v,&["enabled"])&&v["enabled"].is_boolean(),_=>false,
}}
fn dimensions(v:&Value)->bool{["width","height"].iter().all(|key|v[*key].as_u64().is_some_and(|n|(2..=1_000_000).contains(&n)))}
fn valid_view(view:&Value)->bool{
 if !binding(&view["binding"])||!["state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&view[*k]))||!digest(&view["body_graph_sha256"])||!digest(&view["people_graph_sha256"])||!view["refusals"].is_array()||!recipe(&view["recipe"]){return false;}
 if !view["selected_body_ref"].is_null()&&!body_ref(&view["selected_body_ref"]){return false;}
 view["bodies"].as_array().is_some_and(|bodies|bodies.len()<=128&&bodies.iter().all(|body|{
  body_ref(&body["body_ref"])&&body["body_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]
   &&body["enabled"].is_boolean()&&body["operation_enabled"].is_boolean()&&body["reviewed"].is_boolean()&&digest(&body["points_sha256"])
   &&body["source"]["sha256"]==view["binding"]["asset_sha256"]&&body["source"]["orientation"]=="exif_normalized_once"&&dimensions(&body["source"])
   &&(body["support"].is_null()||support(&body["support"]))
   &&body["points"].as_array().is_some_and(|points|points.len()==33&&points.iter().enumerate().all(|(index,p)|{
    p["index"].as_u64()==Some(index as u64)&&["x","y","z","visibility","presence"].iter().all(|key|p[*key].as_f64().is_some_and(f64::is_finite))
   }))
 }))
}
fn valid_source(source:&Value,view:&Value)->bool{
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
 if v["event"]!="leg_length_result"||v["protocol"]!=1||v["action"]!=record.action||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||v.to_string().len()>8*1024*1024{return false;}
 if v["success"]!=true{return v["error"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192);}
 let data=&v["result"];let view=&data["view"];
 if !data.is_object(){return false;}
 // An authoritative status receipt remains readable after source deletion/switch.
 if record.action=="status" {
  if data.get("view").is_some_and(|value|!valid_view(value))||data.get("model").is_some_and(|value|!value.is_object())||data.get("view_error").is_some_and(|value|!value.as_str().is_some_and(|message|message.len()<=4096)){return false;}
 } else if !valid_view(view)||record.document.as_deref().is_some_and(|id|view["binding"]["document_id"].as_str()!=Some(id))||!data["model"].is_object(){return false;}
 if let Some(source)=data.get("source_preview"){if !valid_view(view)||!valid_source(source,view){return false;}}
 if record.action=="edit"||record.action=="status"{let r=&data["receipt"];if !text(&r["request_id"])||!matches!(r["phase"].as_str(),Some("done"|"pending"|"unavailable"))||(r["phase"]=="done"&&(!r["success"].is_boolean()||!r["outcome_unknown"].is_boolean())){return false;}}
 if let Some(receipt_view)=data["receipt"].get("view"){if !valid_view(receipt_view){return false;}}
 true
}
pub(crate) fn receive(epoch:[u8;16],v:&Value){let Some(id)=v["request_id"].as_str()else{return};let Ok(mut host)=mailbox().lock()else{return};let Some(record)=host.records.iter().find(|r|r.id==id&&r.epoch==epoch&&r.result.is_none())else{return};let result=if valid_result(v,record){v.clone()}else{failure(id,&record.action,"腿长回执无效，实际结果未知，请核对当前配方",true)};host.finish(id,result);}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="leg_length"&&matches!(v["action"].as_str(),Some("view"|"status"))}
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String>{let epoch=command.as_object_mut().ok_or("腿长命令无效")?.remove("host_epoch").ok_or("腿长命令缺少引擎身份")?;if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("引擎已变化，未向新引擎重发腿长操作".into());}handle.send(command)}
#[tauri::command]
pub(crate) fn leg_length(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 let id=request["request_id"].as_str().filter(|_|text(&request["request_id"])).ok_or("腿长请求身份无效")?;
 let action=request["action"].as_str().ok_or("腿长动作无效")?;
 if matches!(action,"mailbox_status"|"release"){
  if !fields(&request,&["action","request_id"]){return Err("腿长查询字段无效".into());}
  let mut host=mailbox().lock().map_err(|_|"腿长回执锁失败")?;
  if action=="mailbox_status"{return Ok(host.status(id));}
  if let Some(index)=host.records.iter().position(|r|r.id==id){if host.records[index].result.is_none(){return Ok(host.status(id));}host.records.remove(index);}
  return Ok(json!({"released":true,"request_id":id}));
 }
 let refused=|why:&str|terminal(id,failure(id,action,why,false));
 if !fields(&request,&["action","request_id","request"])||!valid_request(action,&request["request"]){return Ok(refused("腿长命令字段、版本或动作无效，未提交"));}
 let signature=request.to_string();
 let mut host=mailbox().lock().map_err(|_|"腿长回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}drop(host);
 let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;let Some(handle)=guard.as_ref().filter(|h|h.is_alive())else{return Ok(refused("引擎不可用，未提交"));};handle.epoch()};
 let document=request["request"]["document_id"].as_str().or_else(||request["request"]["binding"]["document_id"].as_str());
 host=mailbox().lock().map_err(|_|"腿长回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}if let Err(error)=host.begin(epoch,id,action,document,&signature){return Ok(refused(&error));}drop(host);
 let mut command=request.clone();command["cmd"]=json!("leg_length");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
 let sent=if matches!(action,"view"|"status") {let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;match guard.as_ref(){Some(handle)=>enqueue(handle,command),None=>Err("引擎已停止，未提交".into())}}else{state.send_to_engine(command)};
 if let Err(error)=sent{let mut host=mailbox().lock().map_err(|_|"腿长回执锁失败")?;host.finish(id,failure(id,action,&error,false));return Ok(host.status(id));}
 Ok(json!({"phase":"pending","request_id":id,"requested":true}))
}

#[cfg(test)]
mod tests {
 use super::*;
 // Authored UNRUN: altered action/payload cannot reuse an old success, even after release.
 #[test] fn immutable_signature_survives_release_and_epoch(){
  let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
  let original=json!({"action":"view","request_id":"same","request":{}}).to_string();
  host.begin([1;16],"same","view",None,&original).unwrap();assert_eq!(host.replay("same",&original).unwrap(),true);
  for changed in [json!({"action":"select","request_id":"same","request":{}}),json!({"action":"view","request_id":"same","request":{"changed":true}})]{assert!(host.replay("same",&changed.to_string()).is_err());}
  host.records.clear();host.end([1;16]);assert!(host.replay("same","altered").is_err());assert!(host.replay("same",&original).unwrap());assert_eq!(host.status("same")["phase"],"unavailable");
 }
 #[test] fn signature_retention_has_byte_budget(){let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.signature_bytes=MAX_SIGNATURE_BYTES;assert!(host.begin([1;16],"new","view",None,"{}").is_err());assert!(!host.seen.contains_key("new"));}
 #[test] fn queries_never_accept_edit_payloads(){assert!(valid_request("view",&json!({})));assert!(!valid_request("view",&json!({"body_ref":{}})));assert!(!valid_request("install",&json!({})));}
 #[test] fn faces_are_never_body_references(){assert!(!body_ref(&json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":0})));}
 #[test] fn epoch_end_is_unknown_not_rollback(){let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.begin([1;16],"id","edit",Some("doc"),"original").unwrap();host.end([1;16]);assert_eq!(host.status("id")["result"]["outcome_unknown"],true);host.records.clear();assert!(host.seen.contains_key("id"));}
 #[test] fn status_keeps_authoritative_receipt_without_current_source(){let record=Record{id:"outer".into(),action:"status".into(),epoch:[1;16],document:None,result:None,bytes:0};let value=json!({"event":"leg_length_result","protocol":1,"request_id":"outer","action":"status","success":true,"outcome_unknown":false,"result":{"receipt":{"phase":"done","request_id":"inner","success":false,"outcome_unknown":false,"error":"rejected"},"view_error":"source missing"}});assert!(valid_result(&value,&record));let mut missing=value.clone();missing["result"]=json!({"view_error":"source missing"});assert!(!valid_result(&missing,&record));let mut malformed=value.clone();malformed["result"]["view"]=json!({});assert!(!valid_result(&malformed,&record));malformed=value.clone();malformed["result"]["model"]=json!(true);assert!(!valid_result(&malformed,&record));let non_status=Record{action:"view".into(),..record};let mut no_view=value.clone();no_view["action"]=json!("view");assert!(!valid_result(&no_view,&non_status));}

 #[test] fn recipe_rejects_other_intensity_and_bilateral_unlock(){assert!(recipe(&json!({"version":1,"thigh":1.0,"calf":0.2})));assert!(!recipe(&json!({"version":1,"thigh":0,"calf":0,"overall":0})));assert!(!recipe(&json!({"version":1,"thigh":0,"calf":0,"linked":true})));}
 #[test] fn source_correspondence_requires_decoded_whole_canvas(){
  let view=json!({"binding":{"asset_sha256":"a".repeat(64)},"bodies":[]});
  let source=json!({"mime":"image/png","base64":"fixture","source_sha256":"a".repeat(64),"source_width":4000,"source_height":3000,"decoded_width":2048,"decoded_height":1536,"width":1280,"height":960,"mapping":"normalized_full_frame","orientation":"exif_normalized_once"});
  assert!(valid_source(&source,&view));let mut wrong=source.clone();wrong["decoded_width"]=json!(1600);assert!(!valid_source(&wrong,&view));wrong=source.clone();wrong["height"]=json!(800);assert!(!valid_source(&wrong,&view));
 }

}
