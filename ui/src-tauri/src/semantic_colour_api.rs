// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated, bounded semantic-colour mailbox. Never retries an unknown write.
//! Private worker proofs/mask bytes never cross this interface.
use std::collections::{HashMap,VecDeque};
use std::sync::{Arc,Mutex,OnceLock};
use serde_json::{json,Value};
use tauri::State;
use crate::{engine::EngineHandle,AppState};
const MAX_REQUEST_BYTES:usize=2*1024*1024;
const MAX_RESULT_BYTES:usize=8*1024*1024;
const MAX_MAILBOX_BYTES:usize=16*1024*1024;
const MAX_PROGRESS_BYTES:usize=4*1024;
const MAX_TARGETS:usize=128;
const MAX_RECORDS:usize=64;
const MAX_REQUEST_IDS:usize=65_536;
fn fields(v:&Value,keys:&[&str])->bool{v.as_object().is_some_and(|o|o.len()==keys.len()&&keys.iter().all(|k|o.contains_key(*k)))}
fn text(v:&Value,max:usize)->bool{v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=max&&!s.contains('\0'))}
fn request_id(v:&Value)->Option<&str>{v.as_str().filter(|s|!s.is_empty()&&s.len()<=128&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b"_-".contains(&b)))}
fn png(v:&Value)->bool{text(v,1_500_000)&&v.as_str().unwrap().starts_with("data:image/png;base64,")}
fn session_id(v:&Value)->Option<&str>{v.as_str().filter(|s|s.len()==32&&s.bytes().all(|b|b.is_ascii_hexdigit()))}
fn prepares(method:&str)->bool{matches!(method,"batch_prepare"|"preset_prepare")}
fn workflow(method:&str)->bool{method.starts_with("batch_")||method.starts_with("preset_")||method.starts_with("workflow_")}
fn valid_request(v:&Value)->bool {
    if v.to_string().len()>MAX_REQUEST_BYTES{return false;}
    let keys:&[&str]=match v["action"].as_str(){
        Some("state")=>&["action"],
        Some("capture")=>&["action","reference","context","session_id"],
        Some("start")=>&["action","session_id","mode","strengths","reference_selection","target_selection"],
        Some("poll"|"cancel")=>&["action","session_id"],
        Some("commit")=>&["action","session_id","proof","reviewed"],
        Some("edit")=>&["action","operation","payload","context"],
        Some("mask_overlay")=>&["action","mask_id","objects"],
        Some("batch_prepare")=>&["action","context","session_id","targets","policy"],
        Some("batch_preview")=>&["action","preflight_token","document_id"],
        Some("batch_apply")=>&["action","context","preflight_token","reviewed"],
        Some("batch_restore")=>&["action","context","batch_id","redo"],
        Some("workflow_cancel")=>&["action","session_id"],
        Some("workflow_release")=>&["action"],
        Some("workflow_inspect")=>&["action"],
        Some("preset_export_prepare")=>&["action","context","include_reference"],
        Some("preset_export_write")=>&["action","export_id","path","overwrite"],
        Some("preset_export_status")=>&["action","export_id","path","expected"],
        Some("preset_export_release")=>&["action","export_id"],
        Some("preset_import")=>&["action","path"],
        Some("preset_forget")=>&["action","import_id"],
        Some("preset_prepare")=>&["action","context","session_id","import_id"],
        _=>return false,
    };
    if !fields(v,keys){return false;}
    match v["action"].as_str().unwrap() {
        "batch_prepare"=>session_id(&v["session_id"]).is_some() && v["context"].is_object()
            && matches!(v["policy"].as_str(),Some("recheck"|"skip_and_report"))
            && v["targets"].as_array().is_some_and(|a|!a.is_empty()&&a.len()<=MAX_TARGETS&&a.iter().all(|p|text(p,4096))),
        "preset_prepare"=>session_id(&v["session_id"]).is_some() && session_id(&v["import_id"]).is_some() && v["context"].is_object(),
        "workflow_cancel"=>session_id(&v["session_id"]).is_some(),
        "batch_preview"=>text(&v["preflight_token"],128)&&text(&v["document_id"],128),
        "batch_apply"=>v["context"].is_object()&&text(&v["preflight_token"],128)&&v["reviewed"]==true,
        "batch_restore"=>v["context"].is_object()&&text(&v["batch_id"],128)&&v["redo"].is_boolean(),
        "preset_export_prepare"=>v["context"].is_object()&&v["include_reference"]==true,
        "preset_export_write"=>session_id(&v["export_id"]).is_some()&&text(&v["path"],4096)&&v["overwrite"].is_boolean(),
        "preset_export_status"=>session_id(&v["export_id"]).is_some()&&text(&v["path"],4096)
            &&fields(&v["expected"],&["file_bytes","file_sha256"])
            &&v["expected"]["file_bytes"].as_u64().is_some_and(|n|n>0&&n<=256*1024*1024+128*1024)
            &&v["expected"]["file_sha256"].as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_hexdigit())),
        "preset_export_release"=>session_id(&v["export_id"]).is_some(),
        "preset_forget"=>session_id(&v["import_id"]).is_some(),
        "preset_import"=>text(&v["path"],4096),
        _=>true,
    }
}
fn result_budget(method:&str)->usize{match method{
    "batch_prepare"|"preset_prepare"=>MAX_RESULT_BYTES,
    "start"|"cancel"|"workflow_cancel"|"workflow_release"|"preset_export_prepare"|"preset_export_write"|"preset_export_status"|"preset_export_release"|"preset_forget"=>16*1024,
    "preset_import"=>64*1024,
    "mask_overlay"|"batch_apply"|"batch_restore"|"workflow_inspect"=>2*1024*1024,
    _=>4*1024*1024,
}}
fn failure(id: &str, error: &str, code: &str, unknown: bool) -> Value {
    json!({"event":"semantic_colour_result", "protocol":1, "request_id":id, "action":"request",
        "success":false, "outcome_unknown":unknown, "committed":if unknown { Value::Null } else { json!(false) },
        "error":error, "error_code":code})
}
fn terminal(id: &str, result: Value) -> Value { json!({"phase":"done", "request_id":id, "result":result}) }

struct Record {
    id: String,
    epoch: [u8; 16],
    method: String,
    budget: usize,
    result: Option<Value>,
    bytes: usize,
    cancel_requested: bool,
    session: Option<String>,
    progress: Option<Value>,
}
enum Seen { Admitted, CancelledBeforeAdmission }
#[derive(Default)]
struct Mailbox {
    epoch: [u8; 16],
    supported: bool,
    workflow_supported: bool,
    records: VecDeque<Record>,
    seen: HashMap<String, Seen>,
}
fn mailbox() -> &'static Mutex<Mailbox> {
    static HOST: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    HOST.get_or_init(|| Mutex::new(Mailbox::default()))
}
impl Mailbox {
    fn update_progress(&mut self,epoch:[u8;16],value:&Value){
        if self.epoch!=epoch{return;}
        let Some((session,p))=valid_progress(value) else{return;};
        if let Some(record)=self.records.iter_mut().find(|r|r.epoch==epoch&&prepares(&r.method)&&r.session.as_deref()==Some(session)&&r.result.is_none()){
            record.progress=Some(p.clone());
        }
    }
    fn status(&self, id: &str) -> Value {
        match self.records.iter().find(|record| record.id == id) {
            Some(record) => match &record.result {
                Some(result) => terminal(id, result.clone()),
                None => json!({"phase":"pending", "request_id":id, "cancel_requested":record.cancel_requested,
                    "session_id":record.session,"progress":record.progress}),
            },
            None if matches!(self.seen.get(id), Some(Seen::CancelledBeforeAdmission)) => terminal(id,
                failure(id, "请求在进入引擎队列前已取消，未提交", "cancelled", false)),
            None => json!({"phase":"unavailable", "request_id":id, "outcome_unknown":true,
                "error":"AI 追色回执不可用或已释放；不能据此认定操作没有执行"}),
        }
    }
    fn finish(&mut self, id: &str, result: Value) {
        if let Some(record) = self.records.iter_mut().find(|record| record.id == id && record.result.is_none()) {
            record.bytes = result.to_string().len();
            record.result = Some(result);
            record.progress = None;
        }
    }
    fn end_epoch(&mut self, epoch: [u8; 16]) {
        for record in &mut self.records {
            if record.epoch == epoch && record.result.is_none() {
                let result = failure(&record.id, "引擎结束前未确认操作结果，请核对当前配方，不要自动重试", "outcome_unknown", true);
                record.bytes = result.to_string().len();
                record.result = Some(result);
                record.progress = None;
            }
        }
    }
    fn begin(&mut self, epoch: [u8; 16], id: &str, method: &str) -> Result<(), &'static str> {
        if epoch == [0; 16] || self.epoch != epoch || !self.supported { return Err("AI 追色引擎已变化或未声明协议，未提交"); }
        if workflow(method)&&!self.workflow_supported{return Err("当前引擎未声明追色批量/便携预设协议，未提交");}
        if self.seen.contains_key(id) { return Err("AI 追色请求身份已使用，未重新提交"); }
        if self.seen.len() >= MAX_REQUEST_IDS { return Err("AI 追色请求身份预算已满，请重启应用，未提交"); }
        let budget = result_budget(method);
        let progress_budget=if prepares(method){MAX_PROGRESS_BYTES}else{0};
        let reserved: usize = self.records.iter().map(|record| if record.result.is_some() { record.bytes } else { record.budget+if prepares(&record.method){MAX_PROGRESS_BYTES}else{0} }).sum();
        if self.records.len() >= MAX_RECORDS || reserved + budget + progress_budget > MAX_MAILBOX_BYTES {
            return Err("AI 追色回执邮箱已满，请等待并释放已读回执，未提交");
        }
        self.seen.insert(id.into(), Seen::Admitted);
        self.records.push_back(Record { id:id.into(), epoch, method:method.into(), budget, result:None, bytes:0, cancel_requested:false,session:None,progress:None });
        Ok(())
    }
}

pub(crate) fn reset(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() {
        let previous = host.epoch;
        host.end_epoch(previous);
        host.epoch = epoch;
        host.supported = false;
        host.workflow_supported = false;
    }
}
pub(crate) fn ready(epoch: [u8; 16], supported: bool, workflow_supported:bool) {
    if let Ok(mut host) = mailbox().lock() { if host.epoch == epoch { host.supported = supported;host.workflow_supported=supported&&workflow_supported; } }
}
pub(crate) fn ended(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() {
        host.end_epoch(epoch);
        if host.epoch == epoch { host.supported = false;host.workflow_supported=false; }
    }
}
fn valid_result(method:&str,value:&Value)->bool {
    if !value.is_object(){return false;}
    match method {
        "state"=>value["report"].is_object() && (value["context"].is_object() || value["context"].is_null()),
        "capture"=>text(&value["session_id"],32) && value["context"].is_object()
            && value["target"]["binding"].is_object() && value["reference"]["binding"].is_object()
            && png(&value["target"]["image"]) && png(&value["reference"]["image"]),
        "mask_overlay"=>png(&value["image"]) && text(&value["mask_id"],128),
        "commit"|"edit"=>value["state"]=="applied" && value["report"].is_object() && value["context"].is_object(),
        "start"|"poll"|"cancel"=>text(&value["state"],32),
        "batch_prepare"|"preset_prepare"=>value["success"]==true&&text(&value["preflight_token"],128)
            && value["targets"].as_array().is_some_and(|a|a.len()<=MAX_TARGETS)
            && value["ok"].is_u64()&&value["blocked"].is_u64()&&value["applies"].is_object(),
        "batch_preview"=>text(&value["document_id"],128)&&text(&value["preflight_token"],128)
            &&png(&value["preview"]["before"])&&png(&value["preview"]["after"]),
        "batch_apply"=>value["success"].is_boolean()&&
            (if value["success"]==true {text(&value["batch_id"],128)&&value["target_outcomes"].is_array()}
             else {value["outcome_unknown"].is_boolean()&&text(&value["error"],4096)}),
        "batch_restore"=>matches!(value["event"].as_str(),Some("batch_undone"|"batch_redone"))
            &&text(&value["batch_id"],128)&&value["restored"].is_array()&&value["conflicts"].is_array(),
        "workflow_cancel"=>value["state"]=="cancelled"&&session_id(&value["session_id"]).is_some(),
        "workflow_release"|"preset_export_release"|"preset_forget"=>value["released"]==true,
        "workflow_inspect"=>value["state"]=="inspected"&&(value["inspection"].is_null()||value["inspection"].is_object())&&value["batches"].is_array(),
        "preset_export_prepare"=>session_id(&value["export_id"]).is_some()&&value["reference_included"]==true
            &&value["reference_bytes"].is_u64()&&value["file_bytes"].is_u64()&&text(&value["file_sha256"],64),
        "preset_export_write"=>value["state"]=="exported"&&text(&value["path"],4096)&&text(&value["file_sha256"],64)&&value["file_bytes"].is_u64(),
        "preset_export_status"=>text(&value["path"],4096)&&matches!(value["state"].as_str(),Some("matching"|"missing"|"different"))
            &&(value["state"]=="missing"||(value["file_bytes"].is_u64()&&text(&value["file_sha256"],64))),
        "preset_import"=>session_id(&value["import_id"]).is_some()&&value["intent"].is_object()
            &&value["reference_included"]==true&&value["reference_bytes"].is_u64()&&text(&value["notice"],4096),
        _=>false,
    }
}

/// One metadata-only latest progress snapshot, bound to the real prepare request
/// and current engine epoch. Unknown fields (including image bytes) are rejected.
fn valid_progress(value:&Value)->Option<(&str,&Value)>{
    if !fields(value,&["event","session_id","progress"])||value["event"]!="semantic_colour_progress"
        ||value.to_string().len()>MAX_PROGRESS_BYTES{return None;}
    let Some(session)=session_id(&value["session_id"]) else{return None;};
    let p=&value["progress"];
    let shape=match p["stage"].as_str(){
        Some("reference_analysis")=>fields(p,&["stage","targets"]),
        Some("target_fit")=>fields(p,&["stage","position","targets","document_id","path"])
            &&p["position"].as_u64().is_some_and(|n|n>0&&n<=p["targets"].as_u64().unwrap_or(0))
            &&text(&p["document_id"],128)&&text(&p["path"],4096),
        _=>false,
    };
    if !shape||!p["targets"].as_u64().is_some_and(|n|n<=MAX_TARGETS as u64){return None;}
    Some((session,p))
}
pub(crate) fn progress(epoch:[u8;16],value:&Value){
    if let Ok(mut host)=mailbox().lock(){host.update_progress(epoch,value);}
}
pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    let Some(id) = request_id(&value["request_id"]) else { return };
    let Ok(mut host) = mailbox().lock() else { return };
    let Some(record) = host.records.iter().find(|record| record.id == id && record.epoch == epoch && record.result.is_none()) else { return };
    let valid = value["event"] == "semantic_colour_result" && value["protocol"] == 1 && value["action"] == "request"
        && value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
        && value.get("committed").map_or(true, |v| v.is_null() || v.is_boolean())
        && value.to_string().len() <= record.budget.min(MAX_RESULT_BYTES)
        && if value["success"] == true {
            value["outcome_unknown"] == false && valid_result(&record.method, &value["result"])
        } else { text(&value["error"], 4096) && value.get("error_code").map_or(true, |code| text(code, 128)) };
    let result = if valid { value.clone() } else {
        failure(id, "AI 追色回执无效或超出大小限制；实际写入结果未知，请核对当前配方", "invalid_receipt", true)
    };
    host.finish(id, result);
}

/// Called under the engine lock before editor intent enters the normal queue.
/// Only pending captures are cancelled; importing local files is independent of edits.
pub(crate) fn invalidate_captures(handle: &EngineHandle) -> Result<(), String> {
    let mut host = mailbox().lock().map_err(|_| "AI 追色回执锁失败")?;
    for record in &mut host.records {
        if record.epoch == handle.epoch() && record.method == "capture" && record.result.is_none() && !record.cancel_requested {
            handle.cancel_semantic_colour(&record.id)?;
            record.cancel_requested = true;
        }
    }
    Ok(())
}
pub(crate) fn read_only(command:&Value)->bool {
    command["cmd"]=="semantic_colour_cancel" || (command["cmd"]=="semantic_colour" &&
        matches!(command["request"]["action"].as_str(),Some("state"|"capture"|"start"|"poll"|"mask_overlay"|"cancel"
            |"batch_prepare"|"batch_preview"|"workflow_cancel"|"workflow_release"|"workflow_inspect"|"preset_prepare"|"preset_import"|"preset_forget"
            |"preset_export_prepare"|"preset_export_write"|"preset_export_status"|"preset_export_release")))
}
pub(crate) fn invalidates_capture(command:&Value)->bool {
    if matches!(command["cmd"].as_str(),Some("semantic_colour"|"semantic_colour_cancel")){return false;}
    crate::sample_library_api::invalidates_capture(command)
}
fn cancel(state: &AppState, id: &str) -> Result<Value, String> {
    let guard = state.engine.lock().map_err(|_| "引擎锁失败")?;
    let mut host = mailbox().lock().map_err(|_| "AI 追色回执锁失败")?;
    if !host.records.iter().any(|record| record.id == id) {
        if !host.seen.contains_key(id) {
            // A timed-out IPC may arrive after its cancel control. Preserve this
            // negative admission proof so the late request cannot start a write.
            if host.seen.len() < MAX_REQUEST_IDS {
                host.seen.insert(id.into(), Seen::CancelledBeforeAdmission);
                return Ok(host.status(id));
            }
            // begin() permanently refuses new IDs once this fixed budget is full.
            return Ok(terminal(id, failure(id, "请求身份预算已满，未提交", "not_submitted", false)));
        }
        return Ok(host.status(id));
    }
    let record = host.records.iter_mut().find(|record| record.id == id).unwrap();
    if record.result.is_some() { return Ok(host.status(id)); }
    let handle = guard.as_ref().filter(|handle| handle.epoch() == record.epoch && handle.is_alive());
    if let Some(handle) = handle {
        if !record.cancel_requested {
            // Failure to send cancellation is not failure of the original request.
            // Keep its receipt pending; the caller can still observe real completion.
            if let Err(error) = handle.cancel_semantic_colour(id) {
                return Ok(json!({"phase":"pending", "request_id":id, "cancel_requested":false,
                    "cancel_error":error, "outcome_unknown":true}));
            }
            record.cancel_requested = true;
        }
    }
    // stdout may already be closed while accepted receipts are still draining.
    // Only ended(), after that drain, may synthesize an unknown terminal outcome.
    Ok(host.status(id))
}

#[tauri::command]
pub(crate) fn semantic_colour(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = request_id(&request["request_id"]).ok_or("AI 追色请求身份无效")?;
    let action = request["action"].as_str().ok_or("AI 追色请求动作无效")?;
    match action {
        "status" | "release" | "cancel" => {
            if !fields(&request, &["action", "request_id"]) { return Err("AI 追色控制请求字段无效".into()); }
            if action == "cancel" { return cancel(&state, id); }
            let mut host = mailbox().lock().map_err(|_| "AI 追色回执锁失败")?;
            if action == "status" { return Ok(host.status(id)); }
            if let Some(index) = host.records.iter().position(|record| record.id == id) {
                if host.records[index].result.is_none() { return Ok(json!({"released":false, "phase":"pending", "request_id":id})); }
                host.records.remove(index);
            }
            return Ok(json!({"released":true, "request_id":id}));
        }
        "request" => (),
        _ => return Err("未知AI 追色动作".into()),
    }
    let host = mailbox().lock().map_err(|_| "AI 追色回执锁失败")?;
    // A duplicate is an observation of the original operation, never a resend.
    if host.records.iter().any(|record| record.id == id) { return Ok(host.status(id)); }
    if host.seen.contains_key(id) { return Ok(host.status(id)); }
    drop(host);
    let refuse = |error: &str, code: &str| terminal(id, failure(id, error, code, false));
    if !fields(&request, &["action", "request_id", "request"]) || !valid_request(&request["request"]) {
        return Ok(refuse("AI 追色请求格式、大小、名称、路径或版本无效，未提交", "invalid_request"));
    }
    let guard = match state.engine.lock() {
        Ok(guard) => guard,
        Err(_) => return Ok(refuse("引擎锁不可用，未提交", "engine_unavailable")),
    };
    let Some(handle) = guard.as_ref().filter(|handle| handle.is_alive()) else {
        return Ok(refuse("引擎尚未启动或已退出，未提交", "engine_unavailable"));
    };
    let mut host = mailbox().lock().map_err(|_| "AI 追色回执锁失败")?;
    // Recheck after acquiring the engine lock: another caller may have admitted ID.
    if host.seen.contains_key(id) { return Ok(host.status(id)); }
    if let Err(error) = host.begin(handle.epoch(), id, request["request"]["action"].as_str().unwrap()) {
        return Ok(refuse(error, "not_submitted"));
    }
    let method=request["request"]["action"].as_str().unwrap();
    if prepares(method){
        let session=request["request"]["session_id"].as_str().unwrap();
        if host.records.iter().any(|r|r.id!=id&&r.epoch==handle.epoch()&&r.session.as_deref()==Some(session)&&r.result.is_none()){
            host.finish(id,failure(id,"追色准备会话身份正在使用，未提交","not_submitted",false));
            return Ok(host.status(id));
        }
        host.records.iter_mut().find(|r|r.id==id).unwrap().session=Some(session.into());
    }
    if method=="workflow_cancel"{
        let session=request["request"]["session_id"].as_str().unwrap();
        // The regular dispatcher may be blocked on this prepare. Signal its
        // actual native request ID now, before enqueueing resource cleanup.
        let pending=host.records.iter().find(|record|record.epoch==handle.epoch()&&prepares(&record.method)
            &&record.session.as_deref()==Some(session)&&record.result.is_none()&&!record.cancel_requested).map(|record|record.id.clone());
        if let Some(pending)=pending{
            if let Err(error)=handle.cancel_semantic_colour(&pending){
                host.finish(id,failure(id,&error,"cancel_unconfirmed",false));
                return Ok(host.status(id));
            }
            host.records.iter_mut().find(|record|record.id==pending).unwrap().cancel_requested=true;
        }
    }
    // Keep this dedicated mailbox transport. Read-only operations, including
    // file export writes, must not invalidate editor previews or history.
    // batch_apply/batch_restore remain mutations in read_only() and in the host.
    let command = json!({"cmd":"semantic_colour", "request_id":id, "action":"request", "request":request["request"]});
    if let Err(error) = handle.send(command) {
        // Dispatcher::enqueue errors mean the command was not inserted. A later
        // stdin write failure is instead handled by engine-ended unknown receipts.
        host.finish(id, failure(id, &error, "not_submitted", false));
        return Ok(host.status(id));
    }
    Ok(json!({"requested":true, "phase":"pending", "request_id":id}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn mailbox_never_replays_released_identity() {
        let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
        assert!(host.begin([1;16],"id","edit").is_ok());
        host.records.clear();assert!(host.begin([1;16],"id","edit").is_err());
        assert_eq!(host.status("id")["outcome_unknown"],true);
    }
    #[test]
    fn ended_epoch_is_unknown_not_success_or_rollback() {
        let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
        host.begin([1;16],"id","commit").unwrap();host.end_epoch([1;16]);
        assert_eq!(host.status("id")["result"]["outcome_unknown"],true);
    }
    #[test]
    fn read_only_semantic_work_does_not_cancel_library_capture() {
        assert!(read_only(&json!({"cmd":"semantic_colour","request":{"action":"poll"}})));
        assert!(!read_only(&json!({"cmd":"semantic_colour","request":{"action":"edit"}})));
        assert!(!read_only(&json!({"cmd":"semantic_colour","request":{"action":"batch_apply"}})));
        assert!(!read_only(&json!({"cmd":"semantic_colour","request":{"action":"batch_restore"}})));
        assert!(read_only(&json!({"cmd":"semantic_colour","request":{"action":"preset_export_write"}})));
        assert!(read_only(&json!({"cmd":"semantic_colour","request":{"action":"workflow_inspect"}})));
    }
    #[test]
    fn workflow_requires_its_own_capability_and_reserves_full_preflight() {
        let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;
        assert!(host.begin([1;16],"prepare","batch_prepare").is_err());
        host.workflow_supported=true;
        assert!(host.begin([1;16],"prepare","batch_prepare").is_ok());
        assert_eq!(host.records[0].budget,MAX_RESULT_BYTES);
        // Both full-size receipts plus bounded progress cannot exceed 16 MiB.
        assert!(host.begin([1;16],"second","batch_prepare").is_err());
        assert!(host.begin([1;16],"cleanup","workflow_cancel").is_ok());
    }
    #[test]
    fn workflow_targets_and_fields_are_explicit_and_bounded() {
        let mut body=json!({"action":"batch_prepare","context":{},"session_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "targets":["/one.raw"],"policy":"recheck"});
        assert!(valid_request(&body));
        body["targets"]=json!(vec!["/one.raw";MAX_TARGETS+1]);assert!(!valid_request(&body));
        body["targets"]=json!([]);assert!(!valid_request(&body));
        assert!(valid_request(&json!({"action":"workflow_inspect"})));
        assert!(!valid_request(&json!({"action":"workflow_inspect","retry":true})));
    }
    #[test]
    fn progress_is_small_metadata_bound_to_session_and_epoch() {
        let session="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        let event=json!({"event":"semantic_colour_progress","session_id":session,
            "progress":{"stage":"target_fit","position":1,"targets":2,"document_id":"doc-1","path":"/one.raw"}});
        let mut host=Mailbox::default();host.epoch=[1;16];host.supported=true;host.workflow_supported=true;
        host.begin([1;16],"prepare","batch_prepare").unwrap();host.records[0].session=Some(session.into());
        host.update_progress([2;16],&event);assert!(host.records[0].progress.is_none());
        let mut wrong=event.clone();wrong["session_id"]=json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        host.update_progress([1;16],&wrong);assert!(host.records[0].progress.is_none());
        host.update_progress([1;16],&event);assert_eq!(host.status("prepare")["progress"]["position"],1);
        let mut image=event.clone();image["progress"]["image"]=json!("data:image/png;base64,AAAA");
        assert!(valid_progress(&image).is_none());
        let mut huge=event.clone();huge["progress"]["path"]=json!("x".repeat(MAX_PROGRESS_BYTES));
        assert!(valid_progress(&huge).is_none());
        host.finish("prepare",failure("prepare","cancelled","cancelled",false));
        host.update_progress([1;16],&event);assert!(host.records[0].progress.is_none());
    }
}
