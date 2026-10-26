// SPDX-License-Identifier: GPL-3.0-or-later
//! Reuses the bounded canonical receipt ledger; this module owns no image/history state.
use std::sync::{Arc,Mutex,OnceLock};
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,receipt_host::{ReceiptHost,ReceiptKind}};
const MARKER:&str="hand_shape_request";
struct Kind;
impl ReceiptKind for Kind {
    const NAME:&'static str="hand_shape";
    const ACTIONS:&'static [&'static str]=&["reference","propose","preview","confirm","clear"];
    fn valid(v:&Value,document:Option<&str>)->bool {
        v["event"]=="hand_shape_result"&&v["protocol"]==1&&v["document_id"].as_str()==document
          &&v["success"].is_boolean()&&v["outcome_unknown"].is_boolean()
          &&check(&v[MARKER]).is_ok()&&matches_request(&v[MARKER],v)
          &&(!(v["success"]==false&&v["outcome_unknown"]==false&&mutation(&v[MARKER]))||v["no_write"]==true)
          &&(!(v["success"]==true)||(v["outcome_unknown"]==false&&v["payload"]["protocol"]==1&&v["payload"]["family"]=="hand_shape"))
          &&(!(v["success"]==true&&mutation(&v[MARKER]))||
              (v["doc_state"]["document_id"]==v["document_id"]&&v["doc_state"]["hand_shape"]["protocol"]==1
               &&v["doc_state"]["hand_shape"]["active"]==v["payload"]["active"]
               &&v["payload"]["active"].is_boolean()&&digest(&v["payload"]["candidate_sha256"])
               &&(v["action"]!="clear"||v["payload"]["active"]==false)
               &&(v["action"]!="confirm"||v["payload"]["candidate_sha256"]==v[MARKER]["payload"]["candidate_sha256"])
               &&v["doc_state"]["hand_shape"]["recipe_sha256"]==v["payload"]["candidate_sha256"]
               &&revision(&v["doc_state"]["hand_shape"]["revision"]).zip(revision(&v["revision"])).is_some_and(|(new,old)|new>=old)))
    }
    fn decorate_failure(v:&mut Value,document:Option<&str>){v["event"]=json!("hand_shape_result");v["protocol"]=json!(1);v["document_id"]=json!(document);}
}
struct Mailbox{epoch:[u8;16],host:ReceiptHost<Kind>}
fn store()->&'static Mutex<Mailbox>{static STORE:OnceLock<Mutex<Mailbox>>=OnceLock::new();STORE.get_or_init(||Mutex::new(Mailbox{epoch:[0;16],host:ReceiptHost::default()}))}
fn revision(v:&Value)->Option<u64>{let s=v.as_str()?;if s.is_empty()||s.len()>16||s.len()>1&&s.starts_with('0')||!s.bytes().all(|c|c.is_ascii_digit()){return None;}s.parse::<u64>().ok().filter(|n|*n<=9_007_199_254_740_991)}
fn digest(v:&Value)->bool{v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c)))}
fn text(v:&Value)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&!s.chars().any(char::is_control))}
pub(crate) fn check(v:&Value)->Result<(),String>{
    let o=v.as_object().ok_or("Invalid hand shape request")?;
    if o.len()!=7||!["cmd","protocol","request_id","action","document_id","revision","payload"].iter().all(|k|o.contains_key(*k)){return Err("Unknown hand shape envelope fields".into());}
    if v["cmd"]!="hand_shape"||v["protocol"]!=1||!text(&v["request_id"])||!text(&v["document_id"])
      ||revision(&v["revision"]).is_none()
      ||!Kind::ACTIONS.contains(&v["action"].as_str().unwrap_or(""))||!v["payload"].is_object()
      ||v.to_string().len()>256*1024{return Err("Invalid or oversized hand shape request".into());}
    Ok(())
}
pub(crate) fn read_only(v:&Value)->bool{v["cmd"]=="hand_shape"&&matches!(v["action"].as_str(),Some("reference"|"propose"|"preview"))&&check(v).is_ok()}
pub(crate) fn mutation(v:&Value)->bool{v["cmd"]=="hand_shape"&&matches!(v["action"].as_str(),Some("confirm"|"clear"))}
pub(crate) fn binding(v:&Value)->Result<Option<Value>,String>{if v["cmd"]!="hand_shape"{return Ok(None);}check(v)?;Ok(Some(json!({"hand_shape_request":v,"event":"hand_shape_result","protocol":1,"document_id":v["document_id"],"revision":v["revision"]})))}
pub(crate) fn matches_request(request:&Value,result:&Value)->bool{result["event"]=="hand_shape_result"&&result["protocol"]==1&&result[MARKER]==*request&&result["request_id"]==request["request_id"]&&result["action"]==request["action"]&&result["revision"]==request["revision"]&&result["document_id"]==request["document_id"]}

/// Only the retained exact event in the current engine epoch may settle a
/// locally synthesized transport unknown. An actual engine unknown closes this
/// path in ReceiptHost; this function never sends or replays a command.
pub(crate) fn late_bound_event(epoch:[u8;16],request:&Value,result:&Value)->bool {
    check(request).is_ok()&&matches_request(request,result)
      &&Kind::valid(result,request["document_id"].as_str())
      &&(read_only(request)||(mutation(request)&&crate::project_recovery_fence::hand_shape_pending(epoch,request)))
}
pub(crate) fn ready(epoch:[u8;16],supported:bool){if let Ok(mut m)=store().lock(){if m.epoch!=epoch{m.epoch=epoch;m.host.reset(epoch);}m.host.ready(epoch,supported);}}
pub(crate) fn ended(epoch:[u8;16]){if let Ok(mut m)=store().lock(){m.host.ended(epoch);}}
pub(crate) fn guards_review(epoch:[u8;16],id:&str)->bool{store().lock().map(|m|m.host.guards_review(epoch,id)).unwrap_or(true)}
pub(crate) fn receive(epoch:[u8;16],v:&Value)->Option<Value>{
    let id=v["request_id"].as_str()?;
    let mut m=store().lock().ok()?;
    if m.epoch!=epoch{return None;}
    m.host.receive(epoch,v);
    let status=m.host.status(id);let result=status.get("result")?;
    if result["success"]==true&&result["outcome_unknown"]==false&&result["event"]=="hand_shape_result"{Some(result.clone())}else{None}
}
pub(crate) fn enqueue(handle:&crate::engine::EngineHandle,command:Value)->Result<(),String>{
    check(&command)?;let id=command["request_id"].as_str().unwrap().to_owned();let epoch=handle.epoch();
    store().lock().map_err(|_|"Hand shape receipt lock failed")?.host.begin_command(epoch,&command)?;
    let sent=handle.send(command);
    if let Err(error)=&sent{store().lock().map_err(|_|"Hand shape receipt lock failed")?.host.failed(&id,error);}
    sent
}
#[tauri::command]
pub(crate) fn hand_shape_request(state:State<'_,Arc<AppState>>,request:Value)->Result<Value,String>{
    check(&request)?;let id=request["request_id"].clone();
    let epoch=state.engine.lock().map_err(|_|"Engine lock failed")?.as_ref().ok_or("Engine offline")?.epoch();
    state.send_to_engine_at_epoch(request,epoch)?;Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn hand_shape_status(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("Invalid hand shape receipt identity".into());}
    let epoch=state.engine.lock().map_err(|_|"Engine lock failed")?.as_ref().map(|h|h.epoch());
    let m=store().lock().map_err(|_|"Hand shape receipt lock failed")?;
    if epoch!=Some(m.epoch){return Ok(json!({"phase":"unavailable","request_id":request_id,"error":"Original engine changed; no request was resent"}));}
    Ok(m.host.status(&request_id))
}

// Authored regression fixtures; UNRUN (no build or execution authorized).
#[cfg(test)]
mod tests_unrun {
    use super::*;
    fn request(action:&str)->Value { json!({"cmd":"hand_shape","protocol":1,
        "request_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","action":action,
        "document_id":"source-document","revision":"7","payload":{}}) }
    #[test]
    fn separates_review_from_publication() {
        for action in ["reference","propose","preview"] {
            let q=request(action);assert!(read_only(&q));assert!(!mutation(&q));
        }
        for action in ["confirm","clear"] {
            let q=request(action);assert!(!read_only(&q));assert!(mutation(&q));
        }
    }
    #[test]
    fn refuses_vein_and_unknown_envelopes() {
        let mut q=request("preview");q["cmd"]=json!("limb_vein");
        assert!(check(&q).is_err());assert!(binding(&q).unwrap().is_none());
        let mut q=request("preview");q["unexpected"]=json!(true);assert!(check(&q).is_err());
    }
    #[test]
    fn receipt_binds_family_source_revision_and_exact_request() {
        let q=request("confirm");let r=json!({"event":"hand_shape_result","protocol":1,
            "request_id":q["request_id"],"action":"confirm","document_id":"source-document",
            "revision":"7","hand_shape_request":q});
        assert!(matches_request(&q,&r));
        for field in ["event","document_id","revision","request_id"] {
            let mut wrong=r.clone();wrong[field]=json!("different");assert!(!matches_request(&q,&wrong));
        }
    }
    #[test]
    fn publication_requires_canonical_candidate_and_nonstale_revision() {
        let mut q=request("confirm");q["payload"]=json!({"candidate_sha256":"a".repeat(64)});
        let result=json!({"event":"hand_shape_result","protocol":1,"request_id":q["request_id"],
            "action":"confirm","document_id":"source-document","revision":"7",
            "success":true,"outcome_unknown":false,"hand_shape_request":q,
            "payload":{"protocol":1,"family":"hand_shape","active":true,"candidate_sha256":"a".repeat(64)},
            "doc_state":{"document_id":"source-document","hand_shape":{"protocol":1,
                "revision":"8","active":true,"recipe_sha256":"a".repeat(64)}}});
        assert!(Kind::valid(&result,Some("source-document")));
        let mut stale=result.clone();stale["doc_state"]["hand_shape"]["revision"]=json!("6");
        assert!(!Kind::valid(&stale,Some("source-document")));
        let mut changed=result.clone();changed["payload"]["candidate_sha256"]=json!("b".repeat(64));
        assert!(!Kind::valid(&changed,Some("source-document")));
        let mut mismatch=result.clone();mismatch["doc_state"]["hand_shape"]["active"]=json!(false);
        assert!(!Kind::valid(&mismatch,Some("source-document")));
    }
    #[test]
    fn revision_and_family_are_not_coerced() {
        for raw in [json!("01"),json!("-1"),json!(7),json!("9007199254740992")] {
            let mut q=request("preview");q["revision"]=raw;assert!(check(&q).is_err());
        }
        let mut q=request("preview");q["cmd"]=json!("hand_tone");assert!(check(&q).is_err());
    }

    fn terminal(q:&Value)->Value {
        json!({"event":"hand_shape_result","protocol":1,"request_id":q["request_id"],
            "action":q["action"],"document_id":q["document_id"],"revision":q["revision"],
            "hand_shape_request":q,"success":true,"outcome_unknown":false,
            "payload":{"protocol":1,"family":"hand_shape","active":true,"candidate_sha256":"a".repeat(64)},
            "doc_state":{"document_id":q["document_id"],"hand_shape":{"protocol":1,"revision":"8",
                "active":true,"recipe_sha256":"a".repeat(64)}}})
    }
    #[test]
    fn only_native_unknown_current_fenced_exact_terminal_reconciles() {
        let epoch=[193;16];let mut q=request("confirm");q["request_id"]=json!("hand-shape-late-exact");
        q["payload"]=json!({"candidate_sha256":"a".repeat(64)});
        crate::project_recovery_fence::issued(epoch,&q).unwrap();
        let mut h:ReceiptHost<Kind>=ReceiptHost::default();h.reset(epoch);h.ready(epoch,true);
        h.begin_command(epoch,&q).unwrap();h.failed("hand-shape-late-exact","transport unavailable");
        let unknown=h.status("hand-shape-late-exact")["result"].clone();
        assert!(matches_request(&q,&unknown));assert_eq!(unknown["outcome_unknown"],true);
        let result=terminal(&q);let mut changed=result.clone();
        changed["hand_shape_request"]["revision"]=json!("6");
        h.receive(epoch,&changed);assert_eq!(h.status("hand-shape-late-exact")["result"]["outcome_unknown"],true);
        h.receive([194;16],&result);assert_eq!(h.status("hand-shape-late-exact")["result"]["outcome_unknown"],true);
        assert!(crate::project_recovery_fence::hand_shape_pending(epoch,&q));
        h.receive(epoch,&result);assert_eq!(h.status("hand-shape-late-exact")["result"]["success"],true);
        assert!(!crate::project_recovery_fence::hand_shape_pending(epoch,&q));
        assert!(!late_bound_event(epoch,&q,&result));
    }
    #[test]
    fn engine_unknown_does_not_gain_late_success_authority() {
        let epoch=[195;16];let mut q=request("reference");q["request_id"]=json!("hand-shape-engine-unknown");
        let mut h:ReceiptHost<Kind>=ReceiptHost::default();h.reset(epoch);h.ready(epoch,true);
        h.begin_command(epoch,&q).unwrap();h.failed("hand-shape-engine-unknown","transport unavailable");
        let mut unknown=terminal(&q);unknown["success"]=json!(false);unknown["outcome_unknown"]=json!(true);
        unknown["error"]=json!("engine outcome unknown");h.receive(epoch,&unknown);
        h.receive(epoch,&terminal(&q));assert_eq!(h.status("hand-shape-engine-unknown")["result"]["outcome_unknown"],true);
    }
    #[test]
    fn transported_status_is_not_the_local_status_reader() {
        let q=request("status");assert!(check(&q).is_err());assert!(!read_only(&q));
    }

    #[test]
    fn known_mutation_failure_requires_explicit_no_write() {
        let q=request("clear");let mut result=terminal(&q);
        result["success"]=json!(false);result["error"]=json!("rejected");
        assert!(!Kind::valid(&result,Some("source-document")));
        result["no_write"]=json!(true);assert!(Kind::valid(&result,Some("source-document")));
    }

}
