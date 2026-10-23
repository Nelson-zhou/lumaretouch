//! Correlated ID-background receipts. Unknown delivery never automatically resends a mutation.
use std::{collections::HashMap,sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
#[path = "spill_removal_protocol.rs"]
mod spill;
#[path = "original_shadow_protocol.rs"]
mod shadow;
struct Row {epoch:[u8;16],request:Value,result:Option<Value>}
fn mailbox()->&'static Mutex<HashMap<String,Row>> {static BOX:OnceLock<Mutex<HashMap<String,Row>>>=OnceLock::new();BOX.get_or_init(||Mutex::new(HashMap::new()))}
fn reviewed_action(value:&Value)->bool{spill::is_spill(value)||shadow::is_shadow(value)}
fn expire_previews(rows:&mut HashMap<String,Row>,keep:&str){
 for (id,row) in rows.iter_mut(){if id!=keep&&row.request["action"]=="id_spill_preview"&&row.result.as_ref().is_some_and(|result|result["review"].is_object()){
  row.result=Some(json!({"event":"id_background_result","protocol":1,"action":"id_spill_preview","request_id":id,"document_id":row.request["document_id"],"success":false,"outcome_unknown":false,"requires_reload":false,"error":"此祛染预览已被更新的审核替代；未修改照片，请重新生成预览"}));
 }}
}
fn expire_paint_sources(rows:&mut HashMap<String,Row>,keep:&str){
 for (id,row) in rows.iter_mut(){if id!=keep&&row.request["action"]=="id_spill_paint_source"&&row.result.as_ref().is_some_and(|result|result["paint_source"].is_object()){
  row.result=Some(json!({"event":"id_background_result","protocol":1,"action":"id_spill_paint_source","request_id":id,"document_id":row.request["document_id"],"success":false,"outcome_unknown":false,"requires_reload":false,"error":"此源图画笔读取已被更新的来源替代；未修改照片，请重新读取源图"}));
 }}
}
fn expire_shadow_previews(rows:&mut HashMap<String,Row>,keep:&str){
 for (id,row) in rows.iter_mut(){if id!=keep&&row.request["action"]=="id_original_shadow_preview"&&row.result.as_ref().is_some_and(|result|result["shadow_review"].is_object()){
  row.result=Some(json!({"event":"id_background_result","protocol":1,"action":"id_original_shadow_preview","request_id":id,"document_id":row.request["document_id"],"success":false,"outcome_unknown":false,"requires_reload":false,"error":"此原阴影预览已被更新的审核替代；未修改照片，请重新生成预览"}));
 }}
}
fn review_reserve(request:&Value)->usize{if shadow::is_shadow(request){shadow::MAX_REVIEW_BYTES}else{spill::MAX_REVIEW_BYTES}}
fn review_budget(rows:&HashMap<String,Row>)->usize{
 rows.values().filter(|row|reviewed_action(&row.request)).map(|row|
  row.request.to_string().len()+row.result.as_ref().map_or(review_reserve(&row.request),|value|value.to_string().len())).sum()
}
fn shadow_token_used(rows:&HashMap<String,Row>,epoch:[u8;16],request:&Value)->bool{
 rows.values().any(|row|row.epoch==epoch&&row.request["action"]=="id_original_shadow_apply"&&row.request["token"]==request["token"])
}
fn shadow_review_matches(rows:&HashMap<String,Row>,epoch:[u8;16],request:&Value)->bool{
 rows.values().any(|row|row.epoch==epoch&&row.result.as_ref().is_some_and(|result|shadow::apply_matches(request,&row.request,result)))
}
fn direct_reviewed_field(request:&Value)->bool{
 request["action"]=="id_set"&&["spill","original_shadow"].iter().any(|field|request["recipe"].get(*field).is_some()||request.get(*field).is_some())
}
fn retain_not_sent(rows:&mut HashMap<String,Row>,request:&Value,admitted:bool,error:&str)->bool{
 let Some(id)=request["request_id"].as_str() else{return true;};
 if let Some(row)=rows.get_mut(id){
  // A retry that failed admission must never overwrite an older uncertain
  // request. Only the row inserted by this exact unsent invocation is ours.
  if !admitted||row.request!=*request||row.result.is_some(){return false;}
  row.result=Some(json!({"event":"id_background_result","protocol":1,"action":request["action"],"request_id":id,"document_id":request["document_id"],"success":false,"outcome_unknown":false,"requires_reload":false,"not_sent":true,"error":error}));
 }
 true
}
pub(crate) fn receive(epoch:[u8;16],value:&Value){
 if value["event"]!="id_background_result" {return;}
 let Some(id)=value["request_id"].as_str() else{return};
 if let Ok(mut m)=mailbox().lock(){
 if m.get(id).is_some_and(|row|row.epoch==epoch&&row.result.is_none()&&row.request["action"]=="id_spill_preview"&&value["document_id"]==row.request["document_id"]){expire_previews(&mut m,id);}
 if m.get(id).is_some_and(|row|row.epoch==epoch&&row.result.is_none()&&row.request["action"]=="id_spill_paint_source"&&value["document_id"]==row.request["document_id"]){expire_paint_sources(&mut m,id);}
 if m.get(id).is_some_and(|row|row.epoch==epoch&&row.result.is_none()&&row.request["action"]=="id_original_shadow_preview"&&value["document_id"]==row.request["document_id"]&&shadow::receipt(value,&row.request)) {expire_shadow_previews(&mut m,id);}
 let paint_fence=m.get(id).map_or(true,|row|row.request.get("paint").is_none()||value["success"]!=true||m.values().any(|source|source.epoch==epoch&&source.result.as_ref().is_some_and(|result|spill::painted_review_matches(&row.request,value,&source.request,result))));
 if let Some(row)=m.get_mut(id){if row.epoch==epoch&&row.result.is_none()&&value["document_id"]==row.request["document_id"]{
  let mut v=value.clone();if let Some(o)=v.as_object_mut(){o.remove("doc_state");}
  if spill::is_spill(&row.request){
   if spill::receipt(&v,&row.request)&&paint_fence{row.result=Some(v);}else{
    let mutation=row.request["action"]=="id_spill_apply";
    row.result=Some(json!({"event":"id_background_result","protocol":1,"action":row.request["action"],"request_id":id,"document_id":row.request["document_id"],"success":false,"outcome_unknown":mutation,"requires_reload":mutation,"error":"祛染回执未通过照片、配方或有界 PNG 验证；不得重复应用"}));
   }
  }else if shadow::is_shadow(&row.request){
   if shadow::receipt(&v,&row.request){row.result=Some(v);}else{
    let mutation=row.request["action"]=="id_original_shadow_apply";
    row.result=Some(json!({"event":"id_background_result","protocol":1,"action":row.request["action"],"request_id":id,"document_id":row.request["document_id"],"success":false,"outcome_unknown":mutation,"requires_reload":mutation,"error":"原阴影回执未通过照片、配方或有界 PNG 摘要验证；请查询原操作，不得重复应用"}));
   }
  }else if v.to_string().len()<=2*1024*1024{row.result=Some(v);}
  // The raw event reader must not settle ID-background recovery receipts.
  // Observe only this admitted, epoch/document-correlated terminal result.
  // Invalid mutation receipts become unknown/reload above and keep the fence.
  if let Some(result)=row.result.as_ref(){crate::project_recovery_fence::observed(epoch,result);}
 }}}
}
#[tauri::command]
pub(crate) fn id_background_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 let original=request.clone();let mut attempted=false;let mut admitted=false;
 match request_inner(&state,request,&mut attempted,&mut admitted){
  Err(error) if reviewed_action(&original)&&!attempted=>{
   // A native admission/lock refusal before any send is not an unknown edit.
   // If a row was already reserved, finish it without reopening its token.
   let mut rows=mailbox().lock().map_err(|_|error.clone())?;
   if !retain_not_sent(&mut rows,&original,admitted,&error){return Err(error);}
   Ok(json!({"requested":false,"not_sent":true,"protocol":1,"action":original["action"],"request_id":original["request_id"],"document_id":original["document_id"],"error":error}))
  },
  result=>result,
 }
}
fn request_inner(state:&AppState,request:Value,attempted:&mut bool,admitted:&mut bool)->Result<Value,String>{
 if request.to_string().len()>65536{return Err("证件照背景请求超过 64 KiB".into());}
 let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("缺少背景请求身份")?.to_owned();
 let document=request["document_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=256).ok_or("缺少照片身份")?;
 if request["cmd"]!="background"||!matches!(request["action"].as_str(),Some("id_state"|"id_set"|"id_review"|"id_import"|"id_clear"|"id_sample"|"id_spill_preview"|"id_spill_apply"|"id_spill_paint_source"|"id_original_shadow_preview"|"id_original_shadow_apply")){return Err("未知证件照背景命令".into());}
 if direct_reviewed_field(&request){return Err("祛染与原阴影状态只能通过独立前后审核应用，不能从背景配方直接修改".into());}
 spill::command(&request)?;
 shadow::command(&request)?;
 let read=matches!(request["action"].as_str(),Some("id_state"|"id_sample"|"id_spill_preview"|"id_spill_paint_source"|"id_original_shadow_preview"));
 let handle=state.engine.lock().map_err(|_|"引擎锁错误")?.clone().ok_or("引擎未启动")?;let epoch=handle.epoch();
 {let report=state.doc_report.lock().map_err(|_|"照片状态锁错误")?;if report.as_ref().and_then(|v|v["doc_state"]["document_id"].as_str())!=Some(document){return Err("照片已切换，请重新读取背景状态".into());}}
 if request["action"]=="id_sample" {
  let capture=state.color_picker_capture.lock().map_err(|_|"source capture lock")?;
  let proof=capture.eligible_proof(epoch,request["capture_id"].as_str().ok_or("missing capture")?,request["ticket"].as_str().ok_or("missing ticket")?)?;
  if !matches!(proof.descriptor["picker_action"].as_str(),Some("id_background"|"id_background_reference"|"id_background_subject"))||proof.descriptor["source_stage"]!=crate::color_picker_host::stage(proof.descriptor["picker_action"].as_str().ok_or("missing picker action")?,"master")||request["picker_mode"]!=proof.descriptor["picker_mode"]||request["source_binding"]!=proof.descriptor["source_binding"]||proof.identity.document.to_string()!=document||request["generation"]!=proof.identity.generation.to_string()||request["recipe_document_id"]!=proof.recipe_document_id||request["recipe_revision"]!=proof.recipe_revision{return Err("source sample proof expired".into());}
  let region:crate::color_picker_capture_api::Region=serde_json::from_value(request["region"].clone()).map_err(|_|"invalid sample region")?;region.validate()?;
  if u64::from(region.x)+u64::from(region.width)>u64::from(proof.identity.width)||u64::from(region.y)+u64::from(region.height)>u64::from(proof.identity.height){return Err("source sample outside displayed frame".into());}
 }
 {let mut m=mailbox().lock().map_err(|_|"背景回执锁错误")?;
  if let Some(old)=m.get(&id){if old.epoch==epoch&&old.request==request{return Ok(json!({"requested":true,"request_id":id,"replayed":true}));}return Err("背景请求身份已使用，未发送".into());}
  if request["action"]=="id_spill_apply" {
   if m.values().any(|row|row.epoch==epoch&&row.request["action"]=="id_spill_apply"&&row.request["token"]==request["token"]){return Err("本次祛染审核已提交；请查询原操作，不得再次应用".into());}
   if !m.values().any(|row|row.epoch==epoch&&row.result.as_ref().is_some_and(|result|spill::apply_matches(&request,&row.request,result))){return Err("未找到与照片、配方及 PNG 摘要匹配的祛染审核".into());}
  }
  if request["action"]=="id_original_shadow_apply" {
   if shadow_token_used(&m,epoch,&request){return Err("本次原阴影审核已提交；请查询原操作，不得再次应用".into());}
   if !shadow_review_matches(&m,epoch,&request){return Err("未找到同一引擎、照片、配方及真实 PNG 摘要匹配的原阴影审核".into());}
  }
  if request["action"]=="id_spill_preview" {
   if request.get("paint").is_some()&&!m.values().any(|row|row.epoch==epoch&&row.result.as_ref().is_some_and(|result|spill::paint_matches(&request,&row.request,result))){return Err("未找到同一照片、配方与不可变来源的已确认画笔读取；未发送".into());}
   // Only the newest completed preview is useful; do not retain many MiB of
   // superseded PNGs. Mutation receipts themselves remain available to query.
   expire_previews(&mut m,&id);
   if m.values().filter(|row|row.request["action"]=="id_spill_preview"&&row.result.is_none()).count()>=8{return Err("祛染预览仍有未确认请求，请先查询原操作".into());}
  }
  if request["action"]=="id_spill_paint_source" {
   expire_previews(&mut m,&id);expire_paint_sources(&mut m,&id);
   if m.values().filter(|row|row.request["action"]=="id_spill_paint_source"&&row.result.is_none()).count()>=8{return Err("源图读取仍有未确认请求，请先查询原操作".into());}
  }
  if request["action"]=="id_original_shadow_preview" {
   expire_shadow_previews(&mut m,&id);
   if m.values().filter(|row|row.request["action"]=="id_original_shadow_preview"&&row.result.is_none()).count()>=8{return Err("原阴影预览仍有未确认请求，请先查询原操作".into());}
  }
  // Reserve the bounded future receipt before dispatch, including for apply.
  // Pending requests and confirmed mutation receipts are never evicted.
  if reviewed_action(&request)&&review_budget(&m)+request.to_string().len()+review_reserve(&request)>16*1024*1024{return Err("祛染与原阴影合计回执预算已满，未发送；请核对原操作并保存后重启应用".into());}
  m.retain(|_,r|r.result.is_none()||!matches!(r.request["action"].as_str(),Some("id_state"|"id_sample")));
  if m.len()>=512{return Err("背景回执容量已满；请保存并重启应用".into());}
  m.insert(id.clone(),Row{epoch,request:request.clone(),result:None});*admitted=true;}

 let sent=if read {let g=state.engine.lock().map_err(|_|"引擎锁错误")?;let active=g.as_ref().ok_or("引擎未启动")?;
  if shadow::is_shadow(&request)&&active.epoch()!=epoch{return Err("原阴影预览发送前引擎已重启；未发送".into());}
  *attempted=true;active.send(request)
 }else{*attempted=true;state.send_to_engine(request)};
 if let Err(e)=sent{return Err(format!("背景发送结果未确认：{}；请查询原操作，不要重复提交",e));}
 Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn id_background_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
 if request_id.is_empty()||request_id.len()>128{return Err("背景请求身份无效".into());}
 let engine=state.engine.lock().map_err(|_|"引擎锁错误")?;let epoch=engine.as_ref().map(|h|h.epoch());
 let m=mailbox().lock().map_err(|_|"背景回执锁错误")?;
 let Some(row)=m.get(&request_id) else{return Ok(json!({"phase":"unknown","result":null}));};
 if epoch!=Some(row.epoch){return Ok(json!({"phase":"unknown","result":null,"reason":"engine-restarted"}));}
 Ok(json!({"phase":if row.result.is_some(){"done"}else{"pending"},"result":row.result}))
}

// Source fixtures only, UNRUN. No native build or test process was started.
#[cfg(test)]
mod tests {
 use super::*;
 #[test]
 fn expiring_previews_preserves_pending_and_mutation_receipts(){
  let mut rows=HashMap::new();
  let preview=json!({"action":"id_spill_preview","document_id":"photo"});
  rows.insert("old".to_string(),Row{epoch:[1;16],request:preview.clone(),result:Some(json!({"success":true,"review":{"base64":"pixels"}}))});
  rows.insert("pending".to_string(),Row{epoch:[1;16],request:preview,result:None});
  let outcome=json!({"success":true,"history":{"undo_steps":1}});
  rows.insert("apply".to_string(),Row{epoch:[1;16],request:json!({"action":"id_spill_apply"}),result:Some(outcome.clone())});
  expire_previews(&mut rows,"new");
  assert_eq!(rows.len(),3);assert!(rows["pending"].result.is_none());assert_eq!(rows["apply"].result,Some(outcome));
  let old=rows["old"].result.as_ref().unwrap();assert_eq!(old["success"],false);assert_eq!(old["request_id"],"old");assert!(old.get("review").is_none());
 }
 #[test]
 fn pending_spill_reserves_bounded_future_receipt_before_dispatch(){
  let request=json!({"action":"id_spill_apply"});let bytes=request.to_string().len();let mut rows=HashMap::new();
  rows.insert("apply".to_string(),Row{epoch:[1;16],request,result:None});
  assert_eq!(review_budget(&rows),bytes+spill::MAX_REVIEW_BYTES);
  rows.get_mut("apply").unwrap().result=Some(json!({"success":false,"outcome_unknown":true}));
  assert_eq!(review_budget(&rows),bytes+rows["apply"].result.as_ref().unwrap().to_string().len());
 }
 #[test]
 fn pre_send_refusal_cannot_overwrite_an_earlier_uncertain_apply(){
  let request=json!({"action":"id_spill_apply","request_id":"apply","document_id":"photo"});let mut rows=HashMap::new();
  rows.insert("apply".to_string(),Row{epoch:[1;16],request:request.clone(),result:None});
  assert!(!retain_not_sent(&mut rows,&request,false,"engine unavailable"));assert!(rows["apply"].result.is_none());
  assert!(retain_not_sent(&mut rows,&request,true,"known unsent lock refusal"));
  assert_eq!(rows["apply"].result.as_ref().unwrap()["not_sent"],true);
 }
 #[test]
 fn superseded_source_pixels_expire_without_erasing_pending_reads_or_mutations(){
  let mut rows=HashMap::new();let request=json!({"action":"id_spill_paint_source","document_id":"photo"});
  rows.insert("source-old".into(),Row{epoch:[1;16],request:request.clone(),result:Some(json!({"success":true,"paint_source":{"token":"e".repeat(32)}}))});
  rows.insert("source-pending".into(),Row{epoch:[1;16],request,result:None});
  let mutation=json!({"success":true,"history":{"undo_steps":1}});
  rows.insert("apply".into(),Row{epoch:[1;16],request:json!({"action":"id_spill_apply"}),result:Some(mutation.clone())});
  expire_paint_sources(&mut rows,"source-new");
  assert_eq!(rows.len(),3);assert!(rows["source-pending"].result.is_none());assert_eq!(rows["apply"].result,Some(mutation));
  let old=rows["source-old"].result.as_ref().unwrap();assert_eq!(old["success"],false);assert_eq!(old["request_id"],"source-old");assert!(old.get("paint_source").is_none());
 }
 #[test]
 fn original_shadow_and_spill_share_one_bounded_future_receipt_reserve(){
  let mut rows=HashMap::new();
  for (id,action) in [("spill","id_spill_apply"),("shadow","id_original_shadow_apply")]{
   rows.insert(id.into(),Row{epoch:[1;16],request:json!({"action":action}),result:None});
  }
  let requests=rows.values().map(|row|row.request.to_string().len()).sum::<usize>();
  assert_eq!(review_budget(&rows),requests+spill::MAX_REVIEW_BYTES+shadow::MAX_REVIEW_BYTES);
  rows.insert("ordinary".into(),Row{epoch:[1;16],request:json!({"action":"id_state"}),result:None});
  assert_eq!(review_budget(&rows),requests+spill::MAX_REVIEW_BYTES+shadow::MAX_REVIEW_BYTES);
 }
 #[test]
 fn superseded_original_shadow_does_not_erase_spill_pending_or_mutation_receipts(){
  let mut rows=HashMap::new();let request=json!({"action":"id_original_shadow_preview","document_id":"photo"});
  rows.insert("old".into(),Row{epoch:[1;16],request:request.clone(),result:Some(json!({"success":true,"shadow_review":{"base64":"pixels"}}))});
  rows.insert("pending".into(),Row{epoch:[1;16],request,result:None});
  let spill_result=json!({"success":true,"review":{"base64":"spill-pixels"}});
  rows.insert("spill".into(),Row{epoch:[1;16],request:json!({"action":"id_spill_preview"}),result:Some(spill_result.clone())});
  let mutation=json!({"success":false,"outcome_unknown":true,"requires_reload":true});
  rows.insert("apply".into(),Row{epoch:[1;16],request:json!({"action":"id_original_shadow_apply"}),result:Some(mutation.clone())});
  expire_shadow_previews(&mut rows,"new");
  assert_eq!(rows.len(),4);assert!(rows["pending"].result.is_none());assert_eq!(rows["spill"].result,Some(spill_result));
  assert_eq!(rows["apply"].result,Some(mutation));assert_eq!(rows["old"].result.as_ref().unwrap()["success"],false);
  assert!(rows["old"].result.as_ref().unwrap().get("shadow_review").is_none());
 }
 #[test]
 fn original_shadow_token_remains_spent_after_pending_uncertain_or_known_unsent_admission(){
  let request=json!({"action":"id_original_shadow_apply","request_id":"apply","document_id":"photo","token":"b".repeat(32)});
  let mut rows=HashMap::new();rows.insert("apply".into(),Row{epoch:[1;16],request:request.clone(),result:None});
  assert!(shadow_token_used(&rows,[1;16],&request));assert!(!shadow_token_used(&rows,[2;16],&request));
  assert!(!retain_not_sent(&mut rows,&request,false,"duplicate admission must not hide an uncertain send"));assert!(rows["apply"].result.is_none());
  assert!(retain_not_sent(&mut rows,&request,true,"known unsent invocation"));assert!(shadow_token_used(&rows,[1;16],&request));
  assert_eq!(rows["apply"].result.as_ref().unwrap()["not_sent"],true);
  rows.get_mut("apply").unwrap().result=Some(json!({"success":false,"outcome_unknown":true,"requires_reload":true}));
  assert!(shadow_token_used(&rows,[1;16],&request));assert!(!shadow_review_matches(&rows,[1;16],&request));
 }
 #[test]
 fn original_shadow_apply_needs_a_real_successful_review_in_this_engine_epoch(){
  let request=shadow::tests::apply_request();let original=shadow::tests::preview_request();let result=shadow::tests::preview_receipt();
  let mut rows=HashMap::new();rows.insert("review".into(),Row{epoch:[1;16],request:original,result:Some(result.clone())});
  assert!(shadow_review_matches(&rows,[1;16],&request));assert!(!shadow_review_matches(&rows,[2;16],&request));
  rows.get_mut("review").unwrap().result=None;assert!(!shadow_review_matches(&rows,[1;16],&request));
  rows.get_mut("review").unwrap().result=Some(json!({"success":false,"error":"preview failed"}));assert!(!shadow_review_matches(&rows,[1;16],&request));
  rows.get_mut("review").unwrap().result=Some(result);expire_shadow_previews(&mut rows,"new");
  assert!(!shadow_review_matches(&rows,[1;16],&request));
 }
 #[test]
 fn direct_set_cannot_smuggle_original_shadow_or_spill_state(){
  for field in ["original_shadow","spill"]{
   let mut nested=json!({"action":"id_set","recipe":{}});nested["recipe"][field]=json!(null);assert!(direct_reviewed_field(&nested));
   let mut direct=json!({"action":"id_set","recipe":{}});direct[field]=json!({"enabled":false});assert!(direct_reviewed_field(&direct));
  }
  assert!(!direct_reviewed_field(&json!({"action":"id_set","recipe":{"shadow":{"kind":"none"}}})));
 }
 #[test]
 fn unvalidated_shadow_mutation_receipt_cannot_settle_native_recovery(){
  let epoch=[221;16];let mut request=shadow::tests::apply_request();request["request_id"]=json!("shadow-recovery-invalid-fixture");
  let id=request["request_id"].as_str().unwrap().to_owned();
  mailbox().lock().unwrap().insert(id.clone(),Row{epoch,request:request.clone(),result:None});
  crate::project_recovery_fence::issued(epoch,&request).unwrap();
  let mut result=json!({"event":"id_background_result","protocol":1,"action":request["action"],"request_id":id,
   "document_id":request["document_id"],"success":true,"outcome_unknown":false,"requires_reload":false,
   "report":{"recipe_document_id":request["recipe_document_id"],"recipe_revision":"8"}});
  result["document_id"]=json!("different-photo");receive(epoch,&result);
  assert!(crate::project_recovery_fence::proof(epoch).is_err());assert!(mailbox().lock().unwrap()[&id].result.is_none());
  result["document_id"]=request["document_id"].clone();receive([222;16],&result);
  assert!(crate::project_recovery_fence::proof(epoch).is_err());assert!(mailbox().lock().unwrap()[&id].result.is_none());
  result["protocol"]=json!(2);receive(epoch,&result);
  assert!(crate::project_recovery_fence::proof(epoch).is_err());
  assert_eq!(mailbox().lock().unwrap()[&id].result.as_ref().unwrap()["outcome_unknown"],true);
  // Later contradictory success must not overwrite the retained uncertainty.
  result["protocol"]=json!(1);receive(epoch,&result);assert!(crate::project_recovery_fence::proof(epoch).is_err());
  mailbox().lock().unwrap().remove(&id);crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
 }
 #[test]
 fn validated_correlated_shadow_terminal_receipt_settles_recovery_once(){
  let epoch=[223;16];let mut request=shadow::tests::apply_request();request["request_id"]=json!("shadow-recovery-valid-fixture");
  let id=request["request_id"].as_str().unwrap().to_owned();
  mailbox().lock().unwrap().insert(id.clone(),Row{epoch,request:request.clone(),result:None});
  crate::project_recovery_fence::issued(epoch,&request).unwrap();assert!(crate::project_recovery_fence::proof(epoch).is_err());
  let result=json!({"event":"id_background_result","protocol":1,"action":request["action"],"request_id":id,
   "document_id":request["document_id"],"success":true,"outcome_unknown":false,"requires_reload":false,
   "report":{"recipe_document_id":request["recipe_document_id"],"recipe_revision":"8"}});
  receive(epoch,&result);assert!(crate::project_recovery_fence::proof(epoch).is_ok());
  assert_eq!(mailbox().lock().unwrap()[&id].result.as_ref(),Some(&result));
  mailbox().lock().unwrap().remove(&id);
 }
}
