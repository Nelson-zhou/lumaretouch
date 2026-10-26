//! Epoch-bound retained exact receipts. Queue acknowledgement is not edit success.
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

struct Row { epoch: [u8; 16], generation: u64, request: Value, result: Option<Value>, abandoned: bool, observed_only: bool, admission_pending: bool, recovery_observed: bool }
fn mailbox() -> &'static Mutex<HashMap<String, Row>> {
    static BOX: OnceLock<Mutex<HashMap<String, Row>>> = OnceLock::new();
    BOX.get_or_init(|| Mutex::new(HashMap::new()))
}
fn workspaces() -> &'static Mutex<HashMap<[u8;16],u64>> {
    static CLOCK: OnceLock<Mutex<HashMap<[u8;16],u64>>> = OnceLock::new();
    CLOCK.get_or_init(|| Mutex::new(HashMap::new()))
}
fn generation(epoch: [u8;16]) -> Result<u64,String> {
    Ok(*workspaces().lock().map_err(|_|"历史导航工作区证明锁错误")?.get(&epoch).unwrap_or(&0))
}
/// Called only after the fence validates a real state-replacing project open.
/// Creating a new project preserves live documents and is not recovery evidence.
fn verified_workspace_opened(epoch: [u8;16]) {
    if let Ok(mut clock)=workspaces().lock() {
        if !clock.contains_key(&epoch) && clock.len()>=4096 { return; }
        let old=*clock.get(&epoch).unwrap_or(&0);
        if let Some(next)=old.checked_add(1) { clock.insert(epoch,next); }
    }
}
/// A loose serde reparse, renamed owned result, or duplicate-key event is not
/// recovery evidence. Only a current epoch's strict state-replacing open counts.
pub(crate) fn observe_project_line(epoch:[u8;16], line:&str) {
    if !line.contains("project_opened") {return;}
    let Ok(value)=crate::portrait_crop_protocol::unique_json(line,4*1024*1024) else{return;};
    // Exact allowed envelope from the canonical project-open publisher. In
    // particular stripping request_id from a renamed receipt is insufficient:
    // original_request/protocol/action/view/reached and all other receipt fields
    // are forbidden, even if plausible project fields were also injected.
    let fields=["event","docs","auto_opened","task_restore","proxy_budget","missing","missing_count",
        "changed","changed_count","restore_ms","saved_ns","assets","notes","notes_count","open","path",
        "name","project_id","dirty","tasks","writer","writer_match","dropped_count","project_recovery",
        "managed_import","source_relocation"];
    if !value.as_object().is_some_and(|o|o.keys().all(|k|fields.contains(&k.as_str()))) {return;}
    if crate::project_recovery_fence::verified_history_workspace_open(&value) {verified_workspace_opened(epoch);}
}
fn queue_idle(queue:&Value)->bool {
    queue["pending"].as_u64()==Some(0) && queue["in_flight"]==false && queue["closed"]==false
}
fn observe_unresolved_idle(row:&mut Row, epoch:[u8;16], opened:u64, queue:&Value) {
    // A restored UI request with no native mailbox reserves its identity before
    // this point. A late invocation can only replay that row, never send again.
    if row.observed_only && row.epoch==[0;16] { row.epoch=epoch; }
    if !mutation(&row.request) { return; }
    let unresolved=row.result.as_ref().map_or(true,|r|r["outcome_unknown"]==true);
    if unresolved && !row.admission_pending && !row.recovery_observed && row.epoch==epoch && queue_idle(queue) {
        // RX processes project_opened before the command_done that releases its
        // dispatcher slot. At idle, all earlier queued reset events have passed;
        // only a later verified reset can exceed this explicit query baseline.
        row.generation=opened;
        row.recovery_observed=true;
    }
}
fn recovery_allowed(row:&Row, epoch:[u8;16], opened:u64, queue:&Value)->bool {
    mutation(&row.request) && queue_idle(queue) && (
        // Recorded nonzero epoch is authoritative: epoch-bound admission cannot
        // dispatch this old request into a replacement process.
        (row.epoch!=[0;16] && row.epoch!=epoch)
        || (!row.admission_pending && row.recovery_observed && row.epoch==epoch && opened>row.generation))
}

fn not_sent(request:&Value, error:&str)->Value {
    json!({"event":"history_navigation_result","protocol":1,"request_id":request["request_id"],
        "original_request":request,"success":false,"outcome_unknown":false,"requires_reload":false,
        "phase":"not_sent","completed_steps":0,"reached":null,"last_confirmed":null,"authority":"native-admission","error":format!("历史导航未入队，未修改：{error}")})
}
fn rejected_admission(epoch:[u8;16], request:&Value, error:&str)->Value {
    let packet=not_sent(request,error);
    if let Ok(mut m)=mailbox().lock() {
        if let Some(row)=request["request_id"].as_str().and_then(|id|m.get_mut(id)) {
            if row.request==*request && row.result.is_none() { row.result=Some(packet.clone());row.admission_pending=false; }
        }
    }
    // A guard may already have inserted this exact fence before queue admission.
    // No other command/ID is settled by this native-only not_sent authority.
    crate::project_recovery_fence::observed(epoch,&packet);
    json!({"requested":false,"request_id":request["request_id"],"phase":"done","result":packet})
}

fn checked(request:&Value)->Result<&str,String> {
    crate::history_navigation_protocol::checked(request)?;
    request["request_id"].as_str().ok_or_else(||"历史请求身份无效".into())
}
pub(crate) use crate::history_navigation_protocol::{mutation,read_only};
fn receive(epoch: [u8; 16], value: &Value) -> bool {
    let Some(id) = value["request_id"].as_str() else { return false };
    let Ok(mut m) = mailbox().lock() else { return false };
    let Some(row) = m.get_mut(id) else { return false };
    if row.epoch != epoch || row.result.is_some() || value.to_string().len() > 32768
        || !crate::history_navigation_protocol::receipt(&row.request,value) { return false; }
    row.result = Some(value.clone());
    true
}
pub(crate) fn matches_request(command:&Value,value:&Value)->bool {
    crate::history_navigation_protocol::receipt(command,value)
        || (value["event"]=="history_navigation_result" && value["protocol"]==1
            && value["request_id"]==command["request_id"] && value["original_request"]==*command
            && value["phase"]=="not_sent" && value["authority"]=="native-admission"
            && value["success"]==false && value["outcome_unknown"]==false && value["requires_reload"]==false)
}
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox().lock().map(|m|m.get(id).is_some_and(|r|r.epoch==epoch
        && crate::project_recovery_fence::history_navigation_identity_uncontested(epoch,&r.request))).unwrap_or(true)
}
/// Validated raw receipt recording happens first. No navigation packet, including
/// late/duplicate completed/read-only or stripped-ID renamed packets, reaches
/// generic recovery/readiness/canvas publication after that point.
pub(crate) fn guards_packet(epoch:[u8;16],value:&Value)->bool {
    crate::history_navigation_protocol::navigation_shaped(value)
        || value["request_id"].as_str().is_some_and(|id|guards_result(epoch,id))
}
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    if !line.contains("history_navigation_result") { return None; }
    // Reuse the existing bounded duplicate-key-rejecting JSON reader only;
    // crop operation/state semantics are not involved.
    let value = crate::portrait_crop_protocol::unique_json(line, 32768).ok()?;
    receive(epoch, &value).then_some(value)
}

#[tauri::command]
pub(crate) fn history_navigation(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = checked(&request)?.to_owned();
    {
        let mut m=mailbox().lock().map_err(|_|"历史导航回执锁错误，原身份不能证明未发送")?;
        if let Some(old)=m.get(&id) {
            if old.request==request { return Ok(json!({"requested":true,"request_id":id,"replayed":true})); }
            return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"请求身份冲突")}));
        }
        if m.len()>=4096 { return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"历史导航回执容量已满；请保存并重启应用")})); }
        // Reserve identity before admission: concurrent same-ID invocations can
        // only replay, never relabel the original unknown request as not_sent.
        m.insert(id.clone(),Row{epoch:[0;16],generation:u64::MAX,request:request.clone(),result:None,
            abandoned:false,observed_only:false,admission_pending:true,recovery_observed:false});
    }
    let guard = match state.engine.lock() {
        Ok(guard)=>guard,
        Err(_)=>return Ok(rejected_admission([0;16],&request,"引擎锁错误")),
    };
    let epoch=guard.as_ref().map(|h|h.epoch()).unwrap_or([0;16]);
    let offline=guard.as_ref().map_or(true,|h|!h.is_alive());
    if let Ok(mut m)=mailbox().lock() { if let Some(row)=m.get_mut(&id) { row.epoch=epoch; } }
    drop(guard);
    if offline { return Ok(rejected_admission(epoch,&request,"引擎未启动")); }
    // For this exact unkeyed command the synchronous dispatch path returns Err
    // only before Dispatcher.enqueue pushes it. OS transport runs asynchronously
    // after Ok; a later transport loss never enters this not_sent branch.
    if let Err(error)=state.send_to_engine_at_epoch(request.clone(), epoch) {
        return Ok(rejected_admission(epoch,&request,&error));
    }
    // Successful queue admission is not a reset-order proof. Same-epoch recovery
    // is anchored only by a later explicit unresolved+idle status observation.
    if let Ok(mut m)=mailbox().lock() { if let Some(row)=m.get_mut(&id) { row.admission_pending=false; } }
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn history_navigation_status(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    let guard = state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive());
    let epoch=handle.map(|h|h.epoch());
    // Order matters: first observe idle (after FIFO command_done), then read
    // reset generation. Reading generation first could miss an earlier buffered
    // project_opened that RX processes just before that idle observation.
    let observed_queue=handle.map(|h|h.queue_stats());
    let opened=generation(epoch.unwrap_or([0;16]))?;
    let mut m = mailbox().lock().map_err(|_|"历史导航回执锁错误")?;
    if !m.contains_key(&id) {
        if m.len()>=4096 { return Err("历史导航回执容量已满；请重启应用后重新打开工程".into()); }
        // Lost native mailbox is NOT proof of non-delivery. Start a recovery
        // observation now; require a *later* verified open or epoch replacement.
        m.insert(id.clone(),Row{epoch:epoch.unwrap_or([0;16]),generation:u64::MAX,request:request.clone(),result:None,abandoned:false,observed_only:true,admission_pending:false,recovery_observed:false});
    }
    let row=m.get_mut(&id).ok_or("历史导航回执不可用")?;
    if row.request!=request { return Err("历史导航查询原请求不匹配".into()); }
    if let (Some(h),Some(queue))=(handle,observed_queue.as_ref()) { observe_unresolved_idle(row,h.epoch(),opened,queue); }
    let recover=handle.is_some_and(|h|recovery_allowed(row,h.epoch(),opened,&h.queue_stats()));
    let hint=if recover {"已验证新工作区；可明确放弃旧等待，旧结果仍未知，不会重发。"}
        else if row.recovery_observed {"已记录未知操作的静止队列；请重新打开已确认的工程，然后再查询以放弃旧等待。"}
        else {"请等队列结束后查询原操作，再重新打开已确认的工程；仅等待或旧的打开事件不能解锁。"};
    if row.abandoned { return Ok(json!({"request_id":id,"phase":"abandoned","original_request":row.request,"previous_outcome":"unknown","recovery_available":false})); }
    // A previously verified terminal remains valid evidence about its original
    // document even when the UI is now displaying a replacement engine.
    if let Some(result)=&row.result {
        return Ok(json!({"request_id":id,"phase":"done","result":result,"recovery_available":recover,"recovery_hint":hint}));
    }
    Ok(json!({"request_id":id,"phase":if epoch==Some(row.epoch)&&!row.observed_only{"pending"}else{"unknown"},"result":null,
        "recovery_available":recover,"reason":hint,"recovery_hint":hint}))
}
#[tauri::command]
pub(crate) fn history_navigation_abandon(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    if !mutation(&request) { return Err("只读历史请求无需放弃修改".into()); }
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive()).ok_or("请启动新引擎并打开已确认的照片/工程")?;
    let opened=generation(handle.epoch())?;
    let mut m=mailbox().lock().map_err(|_|"历史导航回执锁错误")?;
    let row=m.get_mut(&id).ok_or("先查询原操作，再重新打开已确认的工程")?;
    if row.request!=request { return Err("历史导航恢复原请求不匹配".into()); }
    if !row.abandoned {
        if row.result.as_ref().is_some_and(|r|r["outcome_unknown"]==false) { return Err("原操作已有准确终态；请查询结果".into()); }
        if !recovery_allowed(row,handle.epoch(),opened,&handle.queue_stats()) { return Err("尚无新引擎或后续工程重新打开证明，或队列未静止；旧操作不能放弃".into()); }
        row.abandoned=true;
        crate::project_recovery_fence::abandon_history_navigation(row.epoch,&row.request);
    }
    // No engine command, recipe edit, resend, or invented success is published.
    Ok(json!({"request_id":id,"phase":"abandoned","original_request":row.request,"previous_outcome":"unknown","recovery_available":false}))
}

// AUTHORED / UNRUN. Exact receipt/family and causal recovery fixtures only.
#[cfg(test)]
mod tests {
    use super::*;
    fn request(id:&str)->Value {json!({"cmd":"history_navigation","action":"navigate","request_id":format!("history-nav-v1:{id}"),"target":0,
        "view":{"workspace":"workspace","document_id":"doc","load_id":"load","revision":"7","digest":"a".repeat(64),"cursor":2,"undo_steps":2,"redo_steps":0,"history_max":64}})}
    fn row(epoch:[u8;16],request:Value)->Row {Row{epoch,generation:0,request,result:None,abandoned:false,observed_only:false,admission_pending:false,recovery_observed:false}}
    fn rejected(r:&Value)->Value {json!({"event":"history_navigation_result","protocol":1,"request_id":r["request_id"],"original_request":r,
        "success":false,"outcome_unknown":false,"requires_reload":false,"phase":"rejected","completed_steps":0,"reached":null,"last_confirmed":null,"error":"stale"})}
    fn idle()->Value {json!({"pending":0,"in_flight":false,"closed":false})}
    #[test] fn only_exact_epoch_owner_and_first_terminal_settle() {
        let epoch=[181;16];let r=request("nav-exact");let v=rejected(&r);
        mailbox().lock().unwrap().insert("history-nav-v1:nav-exact".into(),row(epoch,r.clone()));
        crate::project_recovery_fence::issued(epoch,&r).unwrap();
        assert!(!receive([182;16],&v));
        let mut wrong=v.clone();wrong["original_request"]["view"]["load_id"]=json!("other");assert!(!receive(epoch,&wrong));
        wrong=v.clone();wrong["event"]=json!("people_result");assert!(!receive(epoch,&wrong));
        crate::project_recovery_fence::observed(epoch,&wrong);assert!(crate::project_recovery_fence::proof(epoch).is_err());
        assert!(observe_line(epoch,r#"{"event":"history_navigation_result","success":true,"success":false}"#).is_none());
        let exact=observe_line(epoch,&v.to_string()).unwrap();crate::project_recovery_fence::observed(epoch,&exact);
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());assert!(!receive(epoch,&v));
    }
    #[test] fn reverse_family_injected_fixture_does_not_settle_or_suppress_other_owner() {
        let epoch=[183;16];let r=request("nav-collision");
        mailbox().lock().unwrap().insert("history-nav-v1:nav-collision".into(),row(epoch,r.clone()));
        let other=json!({"cmd":"exposure","action":"set","request_id":"history-nav-v1:nav-collision","ev":1});
        assert!(crate::history_navigation_protocol::admission(&other).is_err());
        // Deliberately bypass admission to retain reverse-family defense in depth.
        crate::project_recovery_fence::issued(epoch,&other).unwrap();
        assert!(!guards_result(epoch,"history-nav-v1:nav-collision"));
        crate::project_recovery_fence::observed(epoch,&rejected(&r));assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&not_sent(&r,"collision"));assert!(crate::project_recovery_fence::proof(epoch).is_err());
    }
    #[test] fn only_later_strict_open_after_unresolved_idle_or_new_engine_unlocks() {
        let epoch=[184;16];let mut r=row(epoch,request("nav-recovery"));
        let opened=json!({"event":"project_opened","open":true,"path":"/fixture/project","project_id":"project","docs":1,"dirty":false});
        observe_project_line(epoch,&opened.to_string());let old=generation(epoch).unwrap();
        assert!(!recovery_allowed(&r,epoch,old,&idle()));
        let mut busy=idle();busy["in_flight"]=json!(true);observe_unresolved_idle(&mut r,epoch,old,&busy);assert!(!r.recovery_observed);
        observe_unresolved_idle(&mut r,epoch,old,&idle());assert!(!recovery_allowed(&r,epoch,old,&idle()));
        observe_project_line(epoch,r#"{"event":"project_opened","open":true,"open":false,"path":"/fixture/project","project_id":"project","docs":1,"dirty":false}"#);
        let mut created=opened.clone();created["event"]=json!("project_created");observe_project_line(epoch,&created.to_string());
        let mut renamed=opened.clone();renamed["request_id"]=json!("nav-recovery");observe_project_line(epoch,&renamed.to_string());
        let mut stripped=opened.clone();stripped["original_request"]=request("nav-recovery");
        stripped["protocol"]=json!(1);stripped["phase"]=json!("unknown");
        observe_project_line(epoch,&stripped.to_string());
        for key in ["original_request","protocol","action","view","target","completed_steps","reached","last_confirmed"] {
            let mut disguised=opened.clone();disguised[key]=Value::Null;observe_project_line(epoch,&disguised.to_string());
        }
        assert_eq!(generation(epoch).unwrap(),old);
        observe_project_line(epoch,&opened.to_string());assert!(recovery_allowed(&r,epoch,generation(epoch).unwrap(),&idle()));
        assert!(!recovery_allowed(&r,epoch,generation(epoch).unwrap(),&busy));
        assert!(recovery_allowed(&r,[185;16],0,&idle()));
    }
    #[test] fn project_create_and_generic_open_never_remove_navigation_fence() {
        let epoch=[186;16];let r=request("nav-create");crate::project_recovery_fence::issued(epoch,&r).unwrap();
        assert!(crate::project_recovery_fence::issued(epoch,&json!({"cmd":"project","action":"create","name":"new","directory":"/fixture"})).is_err());
        for event in ["project_created","project_opened"] {
            crate::project_recovery_fence::observed(epoch,&json!({"event":event,"open":true,"path":"/fixture/project","project_id":"project","docs":1,"dirty":false}));
            assert!(crate::project_recovery_fence::proof(epoch).is_err());
        }
        crate::project_recovery_fence::abandon_history_navigation(epoch,&r);assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
    #[test] fn lost_mailbox_reservation_cannot_be_replayed_into_a_new_submission() {
        let epoch=[187;16];let mut r=row([0;16],request("nav-observed-only"));r.observed_only=true;
        observe_unresolved_idle(&mut r,epoch,4,&idle());assert_eq!(r.epoch,epoch);assert!(!recovery_allowed(&r,epoch,4,&idle()));
        assert!(recovery_allowed(&r,epoch,5,&idle()));
        r.admission_pending=true;assert!(!recovery_allowed(&r,epoch,5,&idle()));
    }
    #[test] fn completed_success_and_read_rows_guard_late_renamed_packets() {
        let epoch=[189;16];let mut r=request("nav-late-success");r["target"]=r["view"]["cursor"].clone();
        let id=r["request_id"].as_str().unwrap().to_owned();
        mailbox().lock().unwrap().insert(id.clone(),row(epoch,r.clone()));
        crate::project_recovery_fence::issued(epoch,&r).unwrap();
        let mut done=rejected(&r);done["success"]=json!(true);done["phase"]=json!("no_change");
        done["reached"]=r["view"].clone();done["last_confirmed"]=r["view"].clone();
        assert!(receive(epoch,&done));crate::project_recovery_fence::observed(epoch,&done);
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());assert!(guards_result(epoch,&id));
        for event in ["project_opened","history_state","frame","ready"] {
            let mut renamed=done.clone();renamed["event"]=json!(event);assert!(guards_packet(epoch,&renamed));
            renamed.as_object_mut().unwrap().remove("request_id");assert!(guards_packet(epoch,&renamed));
        }
        let read=json!({"cmd":"history_navigation","action":"state","request_id":"history-nav-v1:late-read"});
        mailbox().lock().unwrap().insert("history-nav-v1:late-read".into(),row(epoch,read.clone()));
        let mut result=rejected(&read);result["success"]=json!(true);result["phase"]=json!("state");result["view"]=r["view"].clone();
        assert!(receive(epoch,&result));assert!(guards_result(epoch,"history-nav-v1:late-read"));
        assert!(!guards_result([190;16],"history-nav-v1:late-read"));
    }

}
