// SPDX-License-Identifier: GPL-3.0-or-later
//! Epoch-bound whole-person width receipts with process-lifetime replay protection.
//! LNX-REF-PC-32473-C-bc54b9eb3c. Measured complete silhouette and explicit collar.
//! Uses the canonical engine epoch, body publisher and recovery fence, never
//! an independent body source, undo owner or automatic uncertain-edit replay.
//! Rust fixtures are AUTHORED / UNRUN; source integration is not runtime acceptance.
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
    &&digest(&v["body_graph_sha256"])&&digest(&v["people_graph_sha256"])&&v["operation_id"]=="lnx.body_slim.v1"
    &&valid_payload(v["action"].as_str().unwrap_or(""),&v["payload"])
    &&(v["action"]!="support_review"||v["payload"]["data"].get("associated_face_ref").map_or(true,|face|face["asset_sha256"]==v["body_ref"]["asset_sha256"])),
  _=>false,
 }
}
struct Record{id:String,action:String,epoch:[u8;16],binding:Option<Value>,receipt:Option<String>,result:Option<Value>,settled:bool,bytes:usize}
fn releasable(record:&Record)->bool{record.settled||(record.action!="edit"&&record.result.is_some())}
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
fn failure(id:&str,action:&str,error:&str,unknown:bool)->Value{json!({"event":"body_slim_result","protocol":1,"request_id":id,"action":action,"success":false,"outcome_unknown":unknown,"error":error})}
fn terminal(id:&str,result:Value)->Value{json!({"phase":"done","request_id":id,"result":result})}
impl Mailbox{
 fn status(&self,id:&str)->Value{match self.records.iter().find(|r|r.id==id){Some(r)=>match &r.result{Some(value)=>terminal(id,value.clone()),None=>json!({"phase":"pending","request_id":id})},None=>json!({"phase":"unavailable","request_id":id,"outcome_unknown":true,"error":"全身瘦身回执不可用，不能认定操作没有执行"})}}
 fn end(&mut self,epoch:[u8;16]){for r in &mut self.records{if r.epoch==epoch&&r.result.is_none(){let v=failure(&r.id,&r.action,"引擎退出前未确认全身瘦身结果，请核对，不会自动重发",true);r.bytes=v.to_string().len();r.result=Some(v);}}if self.epoch==epoch{self.supported=false;}}
 fn finish(&mut self,id:&str,value:Value){if let Some(r)=self.records.iter_mut().find(|r|r.id==id&&r.result.is_none()){r.bytes=value.to_string().len();r.settled|=value["outcome_unknown"]==false&&(r.action!="edit"||value.get("result").is_none()||value["result"]["receipt"]["phase"]=="done");r.result=Some(value);}}
 // Tombstones retain exact canonical content through release and epoch changes.
 // 16 MiB serialized payload/key retention budget, not a total allocator bound.
 fn replay(&self,id:&str,signature:&str)->Result<bool,String>{match self.seen.get(id){None=>Ok(false),Some(old) if old==signature=>Ok(true),Some(_)=>Err("全身瘦身请求身份对应的内容已改变，未提交，也不会返回其他请求的成功结果".into())}}
 fn begin(&mut self,epoch:[u8;16],id:&str,action:&str,request:&Value,signature:&str)->Result<(),String>{
  if epoch==[0;16]||epoch!=self.epoch||!self.supported{return Err("引擎变化或未声明全身瘦身协议，未提交".into());}
  if self.replay(id,signature)?{return Err("全身瘦身请求身份已用过，不会重发".into());}
  if self.signature_bytes.saturating_add(signature.len()+id.len())>MAX_SIGNATURE_BYTES||self.seen.len()>=65_536{return Err("全身瘦身进程级防重放记录预算已满；先核对未完成请求，释放回执不会删除身份记录".into());}
  if self.records.len()>=MAX_RECORDS||self.records.iter().map(|r|if r.result.is_some(){r.bytes}else{8*1024*1024}).sum::<usize>()+8*1024*1024>MAX_BYTES{return Err("全身瘦身回执预算已满，请先查询并释放已有结果".into());}
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
const SUPPORT_FLAGS: &[&str] = &[
 "whole_person_visible", "upright_not_foreshortened", "actual_complete_silhouette_traced",
 "ownership_confirmed", "only_one_person_in_source", "no_occlusion_or_contacts",
 "background_collar_and_gaps_reviewed",
];
type Point = [f64; 2];
fn cross(a:Point,b:Point,p:Point)->f64{(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])}
fn on_segment(a:Point,b:Point,p:Point)->bool{
 cross(a,b,p).abs()<=1e-12&&p[0]>=a[0].min(b[0])-1e-12&&p[0]<=a[0].max(b[0])+1e-12
 &&p[1]>=a[1].min(b[1])-1e-12&&p[1]<=a[1].max(b[1])+1e-12
}
fn segments_touch(a:Point,b:Point,c:Point,d:Point)->bool{
 (cross(a,b,c)*cross(a,b,d)<0.0&&cross(c,d,a)*cross(c,d,b)<0.0)
 ||on_segment(a,b,c)||on_segment(a,b,d)||on_segment(c,d,a)||on_segment(c,d,b)
}
fn inside(outline:&[Point],p:Point)->bool{
 let mut result=false;
 for i in 0..outline.len(){let a=outline[i];let b=outline[(i+1)%outline.len()];
  if on_segment(a,b,p){return false;}
  if (a[1]>p[1])!=(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]{result=!result;}
 }
 result
}
/// Same geometric predicates and tolerances as body_slim_state.contour.
/// The engine remains the owner of actual pose/face/census admission and pixels.
fn contour(value:&Value)->Option<Vec<Point>>{
 let values=value.as_array()?;
 if !(8..=128).contains(&values.len()){return None;}
 let mut points=Vec::with_capacity(values.len());
 for value in values{
  let pair=value.as_array()?;
  if pair.len()!=2||!pair.iter().all(normalized){return None;}
  points.push([pair[0].as_f64()?,pair[1].as_f64()?]);
 }
 let n=points.len();let mut twice_area=0.0;
 for i in 0..n{let a=points[i];let b=points[(i+1)%n];
  if (b[0]-a[0]).hypot(b[1]-a[1])<=1e-6||cross(points[(i+n-1)%n],a,b).abs()<=1e-12{return None;}
  for j in (i+1)..n{
   if j==(i+1)%n||i==(j+1)%n{continue;}
   if segments_touch(a,b,points[j],points[(j+1)%n]){return None;}
  }
  twice_area+=a[0]*b[1]-b[0]*a[1];
 }
 if twice_area.abs()*0.5<=1e-5{return None;}
 Some(points)
}
fn support(v:&Value)->bool{support_input(v,false)}
fn support_input(v:&Value,allow_draft:bool)->bool{
 let base=["version","method","outline","collar_box","confirmations"];
 let full=["version","method","outline","collar_box","confirmations","associated_face_ref","associated_face_box","associated_face_evidence_sha256"];
 let complete=fields(v,&full);
 if !(complete||(allow_draft&&fields(v,&base)))||v["version"]!=1
  ||v["method"]!="user-traced-complete-person-silhouette-v1"
  ||!fields(&v["confirmations"],SUPPORT_FLAGS)||!SUPPORT_FLAGS.iter().all(|key|v["confirmations"][*key]==true){return false;}
 let Some(outline)=contour(&v["outline"])else{return false};
 let collar=&v["collar_box"];
 if !box_valid(collar){return false;}
 let (Some(left),Some(top),Some(right),Some(bottom))=(collar[0].as_f64(),collar[1].as_f64(),collar[2].as_f64(),collar[3].as_f64())else{return false};
 if !outline.iter().all(|p|left<p[0]&&p[0]<right&&top<p[1]&&p[1]<bottom){return false;}
 // Drafts contain geometry and explicit confirmations only. If any factual
 // face metadata is supplied, ALL three facts must be present; the canonical
 // engine graph, not this boundary or the UI, verifies their exact identity.
 if complete{
  let face=&v["associated_face_box"];
  if !face_ref(&v["associated_face_ref"])||!digest(&v["associated_face_evidence_sha256"])||!box_valid(face){return false;}
  let (Some(l),Some(t),Some(r),Some(b))=(face[0].as_f64(),face[1].as_f64(),face[2].as_f64(),face[3].as_f64())else{return false};
  let corners=[[l,t],[r,t],[r,b],[l,b]];
  if !corners.iter().all(|p|inside(&outline,*p)){return false;}
  // Corner inclusion alone is insufficient for a concave silhouette.
  for i in 0..outline.len(){for j in 0..4{
   if segments_touch(outline[i],outline[(i+1)%outline.len()],corners[j],corners[(j+1)%4]){return false;}
  }}
 }
 true
}
fn valid_payload(action:&str,v:&Value)->bool{match action{
 "recipe"=>fields(v,&["recipe","base"])&&recipe(&v["recipe"])&&recipe(&v["base"]),
 "support_review"=>fields(v,&["data","points_sha256","visible_anchors","ownership_confirmed"])&&support_input(&v["data"],true)&&digest(&v["points_sha256"])&&v["visible_anchors"].as_array().is_some_and(|a|a.len()==33&&a.iter().enumerate().all(|(i,n)|n.as_u64()==Some(i as u64)))&&v["ownership_confirmed"]==true,
 "operation_status"=>fields(v,&["enabled"])&&v["enabled"].is_boolean(),_=>false,
}}
fn dimensions(v:&Value)->bool{["width","height"].iter().all(|key|v[*key].as_u64().is_some_and(|n|(2..=1_000_000).contains(&n)))}
fn association(v:&Value,body:&Value,view:&Value)->bool{
 v.is_null()||(fields(v,&["person_id","body_ref","people_association_revision","confirmation_revision"])
  &&text(&v["person_id"])&&body_ref(&v["body_ref"])&&v["body_ref"]==body["body_ref"]
  &&revision(&v["people_association_revision"])&&revision(&v["confirmation_revision"])
  &&v["confirmation_revision"].as_u64()<=view["association_revision"].as_u64())
}
fn valid_view(view:&Value)->bool{
 if view.get("selected_body_ref").is_none()||!binding(&view["binding"])||!["state_revision","association_revision","people_association_revision"].iter().all(|k|revision(&view[*k]))||!digest(&view["body_graph_sha256"])||!digest(&view["people_graph_sha256"])||!view["refusals"].is_array()||!recipe(&view["recipe"]){return false;}
 if !view["selected_body_ref"].is_null()&&(!body_ref(&view["selected_body_ref"])||view["selected_body_ref"]["asset_sha256"]!=view["binding"]["asset_sha256"]){return false;}
 view["bodies"].as_array().is_some_and(|bodies|bodies.len()<=128&&bodies.iter().enumerate().all(|(i,body)|!bodies[..i].iter().any(|prior|prior["body_ref"]==body["body_ref"]))&&(view["selected_body_ref"].is_null()||bodies.iter().any(|body|body["body_ref"]==view["selected_body_ref"]))&&bodies.iter().all(|body|{
  body_ref(&body["body_ref"])&&body["body_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]
   &&body["enabled"].is_boolean()&&body["operation_enabled"].is_boolean()&&body["reviewed"].is_boolean()&&digest(&body["points_sha256"])
   &&fields(&body["source"],&["sha256","width","height","orientation"])&&body["source"]["sha256"]==view["binding"]["asset_sha256"]&&body["source"]["orientation"]=="exif_normalized_once"&&dimensions(&body["source"])
   &&body.get("association").is_some_and(|value|association(value,body,view))
   &&body.get("support").is_some_and(|value|value.is_null()||(support(value)&&value["associated_face_ref"]["asset_sha256"]==view["binding"]["asset_sha256"]))
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
fn dimension_pair(v:&Value)->Option<(u64,u64)>{
 let pair=v.as_array()?;
 if pair.len()!=2{return None;}
 let (w,h)=(pair[0].as_u64()?,pair[1].as_u64()?);
 if !(2..=1_000_000).contains(&w)||!(2..=1_000_000).contains(&h){return None;}
 Some((w,h))
}
fn whole_source(sw:u64,sh:u64,dw:u64,dh:u64)->bool{
 dw<=sw&&dh<=sh&&((dw==sw&&dh==sh)||(dw%8==0&&dh%8==0&&dw*sh<(dh+8)*sw&&dh*sw<(dw+8)*sh))
}
/// This validates the canonical publisher's proof, not the pixels or numerical
/// quality independently. The engine verifies actual map/pixel hashes before
/// publication. Native routing must never manufacture a separate render owner.
// The full common map may have an explicitly attested standalone hand prefix.
// A legacy body/face suffix string never authorizes an unreported prefix.
fn composition_proof(outcome:&Value,view:&Value,sw:u64,sh:u64)->bool{
 let order=&outcome["composition_order"];
 if order=="body-then-face-inverse-v1"{return outcome.get("document_geometry").is_none();}
 if order!="hand-then-body-then-face-inverse-v1"{return false;}
 let extension=&outcome["document_geometry"];
 if !fields(extension,&["version","composition_order","hand_ids","fields","single_source_sample","runtime_quality_accepted"])
  ||extension["version"]!=1||extension["composition_order"]!=*order
  ||extension["single_source_sample"]!=true||extension["runtime_quality_accepted"]!=false{return false;}
 let (Some(ids),Some(proofs))=(extension["hand_ids"].as_array(),extension["fields"].as_array())else{return false};
 // v1 is intentionally one explicitly reviewed standalone hand per document.
 if ids.len()!=1||proofs.len()!=1||!text(&ids[0]){return false;}
 let proof=&proofs[0];let source=&proof["source"];let amounts=&proof["amounts"];
 proof["hand_id"]==ids[0]&&proof["family"]=="hand_shape"&&proof["operation_id"]=="lnx.hand_shape.v1"
  &&proof["status"]=="rendered"&&proof["applied"]==true&&proof["runtime_quality_accepted"]==false
  &&proof["model_proposal_is_not_visibility"]==true&&digest(&proof["recipe_sha256"])
  &&proof["region_count"].as_u64().is_some_and(|n|(1..=32).contains(&n))
  &&matches!(proof["strategy"].as_str(),Some("manual-visible-support"|"model-proposal-visible-support-reviewed"))
  &&fields(source,&["sha256","width","height"])&&source["sha256"]==view["binding"]["asset_sha256"]
  &&source["width"].as_u64()==Some(sw)&&source["height"].as_u64()==Some(sh)
  &&fields(amounts,&["palm","finger","joint"])
  &&["palm","finger","joint"].iter().all(|k|amounts[*k].as_f64().is_some_and(|v|v.is_finite()&&(-1.0..=1.0).contains(&v)))
  &&["palm","finger","joint"].iter().any(|k|amounts[*k].as_f64().is_some_and(|v|v!=0.0))
}

fn publication_proof(receipt:&Value)->bool{
 let view=&receipt["view"];let outcome=&view["last_outcome"];
 if outcome["version"]!=1||outcome["request_id"]!=receipt["request_id"]
  ||!text(&outcome["published_frame_id"])||!digest(&outcome["output_pixel_sha256"])
  ||outcome["runtime_quality_accepted"]!=false{return false;}
 if receipt["rendered"]==false{
  return outcome["rendered"]==false&&outcome["applied"]==false&&outcome["retained_intent"]==true&&outcome["reason"]==receipt["unapplied_reason"];
 }
 let (Some((sw,sh)),Some((dw,dh)))=(dimension_pair(&outcome["original_dimensions"]),dimension_pair(&outcome["render_dimensions"]))else{return false};
 if !whole_source(sw,sh,dw,dh)||outcome["original_resolution"]!=json!(sw==dw&&sh==dh)
  ||!revision(&outcome["render_revision"])||outcome["render_revision"]!=view["binding"]["document_revision"]
  ||!digest(&outcome["geometry_delta_sha256"])||outcome["single_source_sample"]!=true
  ||!composition_proof(outcome,view,sw,sh)
  ||!matches!(outcome["output_dtype"].as_str(),Some("uint8"|"uint16"|"float32")){return false;}
 let order=&outcome["body_operation_order"];
 let Some(ids)=order["operation_ids"].as_array()else{return false};
 if !fields(order,&["version","operation_ids"])||!revision(&order["version"])||order["version"].as_u64()==Some(0)
  ||ids.is_empty()||ids.len()>32||!ids.iter().enumerate().all(|(i,id)|text(id)&&!ids[..i].contains(id)){return false;}
 let Some(bodies)=view["bodies"].as_array()else{return false};
 if bodies.is_empty()||!bodies.iter().all(|body|body["source"]["width"].as_u64()==Some(sw)&&body["source"]["height"].as_u64()==Some(sh)){return false;}
 let Some(proofs)=outcome["fields"].as_array()else{return false};
 if proofs.len()>128*32{return false;}
 for (index,proof) in proofs.iter().enumerate(){
  if !text(&proof["operation_id"])||!ids.contains(&proof["operation_id"])||!body_ref(&proof["body_ref"])
   ||proof["body_ref"]["asset_sha256"]!=view["binding"]["asset_sha256"]
   ||proof["status"]!="rendered"||proof["applied"]!=true||proof["runtime_quality_accepted"]!=false
   ||proofs[..index].iter().any(|prior|prior["operation_id"]==proof["operation_id"]&&prior["body_ref"]==proof["body_ref"]){return false;}
  let Some(body)=bodies.iter().find(|body|body["body_ref"]==proof["body_ref"])else{return false};
  if proof["operation_id"]!="lnx.body_slim.v1"{continue;}
  let support=&body["support"];
  if bodies.len()!=1||body["enabled"]!=true||body["operation_enabled"]!=true||body["reviewed"]!=true||body["association"].is_null()||body["association"]["people_association_revision"]!=view["people_association_revision"]||!support_input(support,false)
   ||proof["requirement_id"]!="LNX-REF-PC-32473-C-bc54b9eb3c"||proof["support_policy"]!="body-slim-complete-silhouette-review-v1"
   ||proof["source_dimensions"]!=outcome["original_dimensions"]||proof["render_dimensions"]!=outcome["render_dimensions"]
   ||proof["points_sha256"]!=body["points_sha256"]||!recipe(&proof["requested_recipe"])||proof["requested_recipe"]["amount"].as_f64()==Some(0.0)
   ||!["input_binding_sha256","support_sha256","measured_silhouette_sha256"].iter().all(|key|digest(&proof[*key]))
   ||proof["associated_face_ref"]!=support["associated_face_ref"]||proof["associated_face_evidence_sha256"]!=support["associated_face_evidence_sha256"]
   ||proof["whole_person_horizontal_width"]!=true||proof["complete_person_width_transport"]!=true
   ||proof["manual_complete_silhouette_required"]!=true||proof["single_person_only"]!=true
   ||proof["background_collar_and_internal_gaps_may_move"]!=true||proof["vertical_displacement"]!=false
   ||proof["hidden_anatomy_inferred"]!=false||proof["ai_segmentation"]!=false{return false;}
  if body["body_ref"]==view["selected_body_ref"]&&proof["requested_recipe"]!=view["recipe"]{return false;}
 }
 // A selected active intent cannot be presented as rendered with its field
 // silently absent. Neutral/disabled intent does not require a new order.
 if let Some(body)=bodies.iter().find(|body|body["body_ref"]==view["selected_body_ref"]){
  if body["enabled"]==true&&body["operation_enabled"]==true&&view["recipe"]["amount"].as_f64()!=Some(0.0)
   &&!proofs.iter().any(|proof|proof["operation_id"]=="lnx.body_slim.v1"&&proof["body_ref"]==body["body_ref"]){return false;}
 }
 true
}
fn valid_result(v:&Value,record:&Record)->bool{
 if v["event"]!="body_slim_result"||v["protocol"]!=1||v["request_id"]!=record.id||v["action"]!=record.action||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||v.to_string().len()>8*1024*1024{return false;}
 if v["success"]!=true{
  if !v["error"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192){return false;}
  if v.get("result").is_none(){return true;}
 }
 let data=&v["result"];let view=&data["view"];
 if !data.is_object(){return false;}
 // An authoritative status receipt remains readable after source deletion/switch.
 if record.action=="status" {
  if data.get("view").is_some_and(|value|!valid_view(value))||data.get("model").is_some_and(|value|!value.is_object())||["view_error","model_error"].iter().any(|key|data.get(*key).is_some_and(|value|!value.as_str().is_some_and(|message|message.len()<=4096))){return false;}
 } else if !valid_view(view)||!matches_binding(view,record)||!data["model"].is_object(){return false;}
 if matches!(record.action.as_str(),"view"|"select")&&data.get("source_preview").is_none(){return false;}
 if let Some(source)=data.get("source_preview"){if !valid_view(view)||!valid_source(source,view){return false;}}
 if record.action=="edit"||record.action=="status"{let r=&data["receipt"];if !text(&r["request_id"])||r["request_id"].as_str()!=record.receipt.as_deref()||!matches!(r["phase"].as_str(),Some("done"|"pending"|"unavailable"))||(r["phase"]=="done"&&(!r["success"].is_boolean()||!r["outcome_unknown"].is_boolean())){return false;}
  if r["success"]==true{
   let publication=&r["view"]["publication"];let reason=&r["unapplied_reason"];
   if r["phase"]!="done"||r["outcome_unknown"]!=false||!valid_view(&r["view"])||!r["rendered"].is_boolean()||r.get("unapplied_reason").is_none(){return false;}
   if (r["rendered"]==true&&!reason.is_null())||(r["rendered"]==false&&!reason.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=8192)){return false;}
   // A saved review/reset with no core is successful retained intent, not a
   // rendered effect. Preserve that distinction through the native boundary.
   if publication["request_id"]!=r["request_id"]||publication["rendered"]!=r["rendered"]||publication.get("unapplied_reason").is_none()||publication["unapplied_reason"]!=*reason||!publication_proof(r){return false;}
  }
  if record.action=="edit"&&(v["success"]!=r["success"]||v["outcome_unknown"]!=r["outcome_unknown"]){return false;}
  if record.action=="status"&&r["phase"]=="done"&&v["outcome_unknown"]!=r["outcome_unknown"]{return false;}
 }
 if let Some(receipt_view)=data["receipt"].get("view"){if !valid_view(receipt_view)||!matches_binding(receipt_view,record){return false;}}
 true
}
pub(crate) fn receive(epoch:[u8;16],v:&Value)->bool{
 let Some(id)=v["request_id"].as_str()else{return false};let Ok(mut host)=mailbox().lock()else{return false};
 let Some(record)=host.records.iter().find(|r|r.id==id&&r.epoch==epoch&&r.result.is_none())else{return false};
 let valid=valid_result(v,record);let result=if valid{v.clone()}else{failure(id,&record.action,"全身瘦身回执无效，实际结果未知，请核对当前配方",true)};
 if valid{
  if record.action!="edit"||v.get("result").is_none()||v["result"]["receipt"]["phase"]=="done"{crate::project_recovery_fence::observed(epoch,v);}
  // A read-only authoritative inner receipt can settle its original outer fence.
  // It never dispatches the edit again, even after a lost reply or source switch.
  let receipt=&v["result"]["receipt"];
  if record.action=="status"&&receipt["phase"]=="done"&&receipt["outcome_unknown"]==false&&receipt["success"].is_boolean(){
   let resolved:Vec<String>=host.records.iter().filter(|r|r.epoch==epoch&&r.action=="edit"&&r.receipt.as_deref()==receipt["request_id"].as_str()&&(receipt["success"]==false||matches_binding(&receipt["view"],r))).map(|r|r.id.clone()).collect();
   for original in resolved{
    crate::project_recovery_fence::observed(epoch,&json!({"event":"body_slim_result","request_id":original,"success":receipt["success"],"outcome_unknown":false}));
    if let Some(retained)=host.records.iter_mut().find(|r|r.id==original){retained.settled=true;}
   }
  }
 }
 host.finish(id,result);valid
}
/// Consult before the generic recovery observer, including wrong event names.
/// A malformed/unknown edit stays pinned until authoritative original-ID status.
pub(crate) fn guards_result(epoch:[u8;16],id:&str)->bool{
 mailbox().lock().map(|host|host.records.iter().any(|r|r.epoch==epoch&&r.id==id&&!r.settled&&matches!(r.action.as_str(),"edit"|"select"))).unwrap_or(true)
}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="body_slim"&&matches!(v["action"].as_str(),Some("view"|"status"))}
pub(crate) fn enqueue(handle:&EngineHandle,mut command:Value)->Result<(),String>{let epoch=command.as_object_mut().ok_or("全身瘦身命令无效")?.remove("host_epoch").ok_or("全身瘦身命令缺少引擎身份")?;if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("引擎已变化，未向新引擎重发全身瘦身操作".into());}handle.send(command)}
#[tauri::command]
pub(crate) fn body_slim(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 let id=request["request_id"].as_str().filter(|_|text(&request["request_id"])).ok_or("全身瘦身请求身份无效")?;
 let action=request["action"].as_str().ok_or("全身瘦身动作无效")?;
 if matches!(action,"mailbox_status"|"release"){
  if !fields(&request,&["action","request_id"]){return Err("全身瘦身查询字段无效".into());}
  let mut host=mailbox().lock().map_err(|_|"全身瘦身回执锁失败")?;
  if action=="mailbox_status"{return Ok(host.status(id));}
  if let Some(index)=host.records.iter().position(|r|r.id==id){if !releasable(&host.records[index]){return Ok(host.status(id));}host.records.remove(index);}
  return Ok(json!({"released":true,"request_id":id}));
 }
 let refused=|why:&str|terminal(id,failure(id,action,why,false));
 if request.to_string().len()>256*1024||!fields(&request,&["action","request_id","request"])||!valid_request(action,&request["request"])||(action=="edit"&&request["request"]["request_id"]==id){return Ok(refused("全身瘦身命令字段、版本或动作无效，未提交"));}
 let signature=request.to_string();
 let mut host=mailbox().lock().map_err(|_|"全身瘦身回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}drop(host);
 let epoch={let guard=state.engine.lock().map_err(|_|"引擎锁失败")?;let Some(handle)=guard.as_ref().filter(|h|h.is_alive())else{return Ok(refused("引擎不可用，未提交"));};handle.epoch()};
 host=mailbox().lock().map_err(|_|"全身瘦身回执锁失败")?;match host.replay(id,&signature){Ok(true)=>return Ok(host.status(id)),Err(error)=>return Ok(refused(&error)),Ok(false)=>{}}if let Err(error)=host.begin(epoch,id,action,&request["request"],&signature){return Ok(refused(&error));}drop(host);
 let mut command=request.clone();command["cmd"]=json!("body_slim");command["host_epoch"]=json!(crate::frame_identity::hex(epoch));
 let sent=if matches!(action,"view"|"status") {match state.engine.lock(){Ok(guard)=>match guard.as_ref(){Some(handle)=>enqueue(handle,command),None=>Err("引擎已停止，未提交".into())},Err(_)=>Err("引擎锁失败，未提交".into())}}else{state.send_to_engine(command)};
 if let Err(error)=sent{let result=failure(id,action,&error,false);crate::project_recovery_fence::observed(epoch,&result);let mut host=mailbox().lock().map_err(|_|"全身瘦身回执锁失败")?;host.finish(id,result);return Ok(host.status(id));}
 Ok(json!({"phase":"pending","request_id":id,"requested":true}))
}

// AUTHORED / UNRUN. No cargo test, compiler or product execution was performed.
#[cfg(test)]
#[path = "body_slim_api_unrun.rs"]
mod tests;

#[cfg(test)]
mod hand_prefix_unrun {
 use super::*;
 // Authored source fixtures only; not executed or compiled.
 fn fixture()->(Value,Value){
  let asset="a".repeat(64);let recipe="b".repeat(64);
  let view=json!({"binding":{"asset_sha256":asset}});
  let outcome=json!({"composition_order":"hand-then-body-then-face-inverse-v1",
   "document_geometry":{"version":1,"composition_order":"hand-then-body-then-face-inverse-v1",
    "hand_ids":["hand:reviewed"],"single_source_sample":true,"runtime_quality_accepted":false,
    "fields":[{"hand_id":"hand:reviewed","family":"hand_shape","operation_id":"lnx.hand_shape.v1",
     "status":"rendered","applied":true,"runtime_quality_accepted":false,"model_proposal_is_not_visibility":true,
     "recipe_sha256":recipe,"region_count":1,"strategy":"manual-visible-support",
     "source":{"sha256":view["binding"]["asset_sha256"],"width":1001,"height":1601},
     "amounts":{"palm":0.2,"finger":0.0,"joint":0.0}}]}});
  (outcome,view)
 }
 #[test]fn accepts_only_attested_hand_prefix(){
  let(outcome,view)=fixture();assert!(composition_proof(&outcome,&view,1001,1601));
  let mut missing=outcome.clone();missing.as_object_mut().unwrap().remove("document_geometry");
  assert!(!composition_proof(&missing,&view,1001,1601));
  let legacy=json!({"composition_order":"body-then-face-inverse-v1"});
  assert!(composition_proof(&legacy,&view,1001,1601));
  let mut hidden=outcome.clone();hidden["composition_order"]=json!("body-then-face-inverse-v1");
  assert!(!composition_proof(&hidden,&view,1001,1601));
 }
 #[test]fn refuses_wrong_source_identity_amount_and_hash(){
  let(outcome,view)=fixture();
  for(path,value) in [
   ("/document_geometry/fields/0/source/sha256",json!("c".repeat(64))),
   ("/document_geometry/fields/0/hand_id",json!("another")),
   ("/document_geometry/fields/0/recipe_sha256",json!("not-a-hash")),
   ("/document_geometry/fields/0/amounts/palm",json!(2.0)),
   ("/document_geometry/runtime_quality_accepted",json!(true))]{
    let mut wrong=outcome.clone();*wrong.pointer_mut(path).unwrap()=value;
    assert!(!composition_proof(&wrong,&view,1001,1601));
  }
 }
}
