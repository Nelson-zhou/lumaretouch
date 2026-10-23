//! Correlated ID-background receipts. Unknown delivery never automatically resends a mutation.
use std::{collections::HashMap,sync::{Arc,Mutex,OnceLock}};
use serde_json::{Value,json};
use tauri::State;
use crate::AppState;
struct Row {epoch:[u8;16],request:Value,result:Option<Value>}
fn mailbox()->&'static Mutex<HashMap<String,Row>> {static BOX:OnceLock<Mutex<HashMap<String,Row>>>=OnceLock::new();BOX.get_or_init(||Mutex::new(HashMap::new()))}
pub(crate) fn receive(epoch:[u8;16],value:&Value){
 if value["event"]!="id_background_result" {return;}
 let Some(id)=value["request_id"].as_str() else{return};
 if let Ok(mut m)=mailbox().lock(){if let Some(row)=m.get_mut(id){if row.epoch==epoch&&row.result.is_none()&&value["document_id"]==row.request["document_id"]{let mut v=value.clone();if let Some(o)=v.as_object_mut(){o.remove("doc_state");}if v.to_string().len()<=2*1024*1024{row.result=Some(v);}}}}
}
#[tauri::command]
pub(crate) fn id_background_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
 if request.to_string().len()>65536{return Err("证件照背景请求超过 64 KiB".into());}
 let id=request["request_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=128).ok_or("缺少背景请求身份")?.to_owned();
 let document=request["document_id"].as_str().filter(|s|!s.is_empty()&&s.len()<=256).ok_or("缺少照片身份")?;
 if request["cmd"]!="background"||!matches!(request["action"].as_str(),Some("id_state"|"id_set"|"id_review"|"id_import"|"id_clear"|"id_sample")){return Err("未知证件照背景命令".into());}
 let read=matches!(request["action"].as_str(),Some("id_state"|"id_sample"));
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
  m.retain(|_,r|r.result.is_none()||!matches!(r.request["action"].as_str(),Some("id_state"|"id_sample")));
  if m.len()>=512{return Err("背景回执容量已满；请保存并重启应用".into());}
  m.insert(id.clone(),Row{epoch,request:request.clone(),result:None});}

 let sent=if read {let g=state.engine.lock().map_err(|_|"引擎锁错误")?;g.as_ref().ok_or("引擎未启动")?.send(request)}else{state.send_to_engine(request)};
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
