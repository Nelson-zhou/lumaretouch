//! Narrow group preset transport; source-only, runtime UNRUN.
use serde_json::Value;
fn exact(v:&Value,keys:&[&str])->bool {v.as_object().is_some_and(|m|m.len()==keys.len()&&keys.iter().all(|k|m.contains_key(*k)))}
fn token(v:&Value)->bool {v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&s.bytes().all(|c|c.is_ascii_alphanumeric()||b"_.:-".contains(&c)))}
fn plan_token(v:&Value)->bool {v.as_str().is_some_and(|s|s.len()==32&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c)))}
fn hash(v:&Value)->bool {v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c)))}
fn revision(v:&Value)->bool {v.as_str().is_some_and(|s|s.len()<=20&&s.bytes().all(|c|c.is_ascii_digit())&&s.parse::<u64>().is_ok()&&(s=="0"||!s.starts_with('0')))}
pub(crate) fn routed(v:&Value)->bool {v["action"].as_str().is_some_and(|s|s.starts_with("portrait_preset_"))||v.get("portrait_preset_ack").is_some()}
pub(crate) fn command(v:&Value)->Result<(),String>{
 if !routed(v){return Ok(());} if v["cmd"]!="batch"||!token(&v["request_id"]){return Err("invalid portrait group request".into());}
 let valid=match v["action"].as_str(){
  Some("portrait_preset_catalogue")=>exact(v,&["cmd","action","request_id"]),
  Some("portrait_preset_preflight"|"portrait_preset_prepare")=>exact(v,&["cmd","action","request_id","docs","preset_id","preset_sha256"])
   &&token(&v["preset_id"])&&hash(&v["preset_sha256"])&&v["docs"].as_array().is_some_and(|a|!a.is_empty()&&a.len()<=8&&a.iter().all(token)&&a.iter().enumerate().all(|(i,d)|!a[..i].contains(d))),
  Some("portrait_preset_image")=>exact(v,&["cmd","action","request_id","preflight_token","document_id","side","page"])
   &&plan_token(&v["preflight_token"])&&token(&v["document_id"])&&matches!(v["side"].as_str(),Some("before"|"after"))&&v["page"].as_u64().is_some_and(|p|p<64),
  Some("portrait_preset_save")=>exact(v,&["cmd","action","request_id","preflight_token","batch_id"])
   &&plan_token(&v["preflight_token"])&&token(&v["batch_id"]),
  Some("portrait_preset_export_preview")=>exact(v,&["cmd","action","request_id","preflight_token","batch_id","export_options","policy","intent_revision"])
   &&plan_token(&v["preflight_token"])&&token(&v["batch_id"])&&v["export_options"].is_object()&&v["policy"].is_object()
   &&v["intent_revision"].as_u64().is_some_and(|n|n<=9007199254740991)
   &&v["export_options"].to_string().len()<=65536&&v["policy"].to_string().len()<=16384,
  Some("portrait_preset_export_start")=>exact(v,&["cmd","action","request_id","preflight_token","batch_id","plan_id","intent_revision"])
   &&plan_token(&v["preflight_token"])&&token(&v["batch_id"])&&token(&v["plan_id"])
   &&v["intent_revision"].as_u64().is_some_and(|n|n<=9007199254740991),
  Some("portrait_preset_export_status"|"portrait_preset_export_cancel")=>exact(v,&["cmd","action","request_id","preflight_token","batch_id","task_id"])
   &&plan_token(&v["preflight_token"])&&token(&v["batch_id"])&&token(&v["task_id"]),
  Some("portrait_preset_commit")=>exact(v,&["cmd","action","request_id","preflight_token","portrait_preset_ack","accepted"])
   &&plan_token(&v["preflight_token"])&&v["accepted"]==true&&v["portrait_preset_ack"].as_array().is_some_and(|a|!a.is_empty()&&a.len()<=8&&a.iter().enumerate().all(|(i,t)|exact(t,&["document_id","revision","before_sha256","after_sha256","review_sha256"])
   &&token(&t["document_id"])&&revision(&t["revision"])&&hash(&t["before_sha256"])&&hash(&t["after_sha256"])&&hash(&t["review_sha256"])&&!a[..i].iter().any(|p|p["document_id"]==t["document_id"]))),
  _=>false};
 if valid{Ok(())}else{Err("invalid frozen portrait preset group command".into())}
}
pub(crate) fn read_only(v:&Value)->bool {command(v).is_ok()&&routed(v)&&matches!(v["action"].as_str(),Some("portrait_preset_catalogue"|"portrait_preset_preflight"|"portrait_preset_image"|"portrait_preset_export_preview"|"portrait_preset_export_status"))}

// AUTHORED / UNRUN. These specifications have not been compiled or executed.
#[cfg(test)]
mod tests {
 use super::*;use serde_json::json;
 #[test]fn delivery_reads_and_mutations_are_distinct_unrun(){
  let base=json!({"cmd":"batch","action":"portrait_preset_save","request_id":"save","preflight_token":"a".repeat(32),"batch_id":"batch"});
  assert!(command(&base).is_ok());assert!(!read_only(&base));
  let mut status=base.clone();status["action"]=json!("portrait_preset_export_status");status["task_id"]=json!("task-a");
  assert!(read_only(&status));status["action"]=json!("portrait_preset_export_cancel");assert!(command(&status).is_ok());assert!(!read_only(&status));
  status["export_options"]=json!({});assert!(command(&status).is_err());
 }
 #[test]fn group_reads_are_exact_and_commit_is_never_read_only(){
  let read=json!({"cmd":"batch","action":"portrait_preset_catalogue","request_id":"read"});
  assert!(read_only(&read));let mut bad=read.clone();bad["accepted"]=json!(true);assert!(command(&bad).is_err());
  let preflight=json!({"cmd":"batch","action":"portrait_preset_preflight","request_id":"prepare","docs":["a"],"preset_id":"saved","preset_sha256":"a".repeat(64)});
  assert!(read_only(&preflight));let mut prepare=preflight.clone();prepare["action"]=json!("portrait_preset_prepare");assert!(command(&prepare).is_ok());assert!(!read_only(&prepare));bad=preflight.clone();bad["docs"]=json!(["a","a"]);assert!(command(&bad).is_err());
  let commit=json!({"cmd":"batch","action":"portrait_preset_commit","request_id":"write","preflight_token":"f".repeat(32),"accepted":true,"portrait_preset_ack":[{"document_id":"a","revision":"1","before_sha256":"a".repeat(64),"after_sha256":"b".repeat(64),"review_sha256":"c".repeat(64)}]});
  assert!(command(&commit).is_ok());assert!(!read_only(&commit));bad=commit.clone();bad["accepted"]=json!(false);assert!(command(&bad).is_err());
 }
}
