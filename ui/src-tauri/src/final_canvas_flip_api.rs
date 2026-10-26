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
    Ok(*workspaces().lock().map_err(|_|"翻转工作区证明锁错误")?.get(&epoch).unwrap_or(&0))
}
/// Called only after the fence validates a real state-replacing project open.
/// Creating a new project preserves live documents and is not recovery evidence.
pub(crate) fn verified_workspace_opened(epoch: [u8;16]) {
    if let Ok(mut clock)=workspaces().lock() {
        if !clock.contains_key(&epoch) && clock.len()>=4096 { return; }
        let old=*clock.get(&epoch).unwrap_or(&0);
        if let Some(next)=old.checked_add(1) { clock.insert(epoch,next); }
    }
}
fn queue_idle(queue:&Value)->bool {
    queue["pending"].as_u64()==Some(0) && queue["in_flight"]==false && queue["closed"]==false
}
fn observe_unresolved_idle(row:&mut Row, epoch:[u8;16], opened:u64, queue:&Value) {
    // A restored UI request with no native mailbox reserves its identity before
    // this point. A late invocation can only replay that row, never send again.
    if row.observed_only && row.epoch==[0;16] { row.epoch=epoch; }
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
    queue_idle(queue) && (
        // Recorded nonzero epoch is authoritative: epoch-bound admission cannot
        // dispatch this old request into a replacement process.
        (row.epoch!=[0;16] && row.epoch!=epoch)
        || (!row.admission_pending && row.recovery_observed && row.epoch==epoch && opened>row.generation))
}

fn not_sent(request:&Value, error:&str)->Value {
    json!({"event":"final_canvas_flip_result","protocol":1,"request_id":request["request_id"],
        "original_request":request,"success":false,"outcome_unknown":false,"requires_reload":false,
        "phase":"not_sent","authority":"native-admission","error":format!("翻转未入队，未修改：{error}")})
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

fn decimal(value: &str) -> bool {
    !value.is_empty() && value.len() <= 20 && value.bytes().all(|c| c.is_ascii_digit())
        && (value == "0" || !value.starts_with('0')) && value.parse::<u64>().is_ok()
}
fn checked(request: &Value) -> Result<&str, String> {
    let object = request.as_object().ok_or("翻转请求必须是对象")?;
    let fields = ["cmd", "request_id", "document_id", "revision", "horizontal", "vertical"];
    if object.len() != fields.len() || !fields.iter().all(|k| object.contains_key(*k))
        || request["cmd"] != "final_canvas_flip" || !request["horizontal"].is_boolean()
        || !request["vertical"].is_boolean() { return Err("翻转请求字段无效".into()); }
    let id = request["request_id"].as_str().filter(|s| !s.is_empty() && s.len() <= 128)
        .ok_or("翻转请求缺少有界身份")?;
    let document = request["document_id"].as_str().ok_or("缺少文档绑定")?;
    let revision = request["revision"].as_str().ok_or("缺少版本绑定")?;
    if document.is_empty() || document.len() > 128 || document == "0"
        || !document.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
        || !decimal(revision) { return Err("翻转请求缺少有效文档/版本绑定，请刷新当前照片".into()); }
    Ok(id)
}
fn receive(epoch: [u8; 16], value: &Value) -> bool {
    let Some(id) = value["request_id"].as_str() else { return false };
    let Ok(mut m) = mailbox().lock() else { return false };
    let Some(row) = m.get_mut(id) else { return false };
    if row.epoch != epoch || row.result.is_some() || value.to_string().len() > 32768
        || value["event"] != "final_canvas_flip_result" || value["protocol"] != 1
        || value["original_request"] != row.request || !value["success"].is_boolean()
        || !value["outcome_unknown"].is_boolean() || !value["requires_reload"].is_boolean() { return false; }
    let phase = value["phase"].as_str().unwrap_or("");
    if value["success"] == true {
        let Some(before) = row.request["revision"].as_str().and_then(|s|s.parse::<u64>().ok()) else { return false };
        let after = value["result_revision"].as_str().filter(|s|decimal(s)).and_then(|s|s.parse::<u64>().ok());
        let expected = if phase == "applied" { before.checked_add(1) } else if phase == "no_change" { Some(before) } else { None };
        if expected.is_none() || after != expected || value["outcome_unknown"] != false || value["requires_reload"] != false
            || value["spec"] != json!({"horizontal":row.request["horizontal"],"vertical":row.request["vertical"]}) { return false; }
    } else if !matches!(phase, "rejected" | "rolled_back" | "unknown") || !value["error"].is_string()
        || (phase == "unknown") != (value["outcome_unknown"] == true)
        || (phase == "unknown") != (value["requires_reload"] == true) { return false; }
    row.result = Some(value.clone());
    true
}
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox().lock().map(|m|m.get(id).is_some_and(|r|r.epoch==epoch
        && crate::project_recovery_fence::final_canvas_flip_pending(epoch,&r.request))).unwrap_or(true)
}
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    if !line.contains("final_canvas_flip_result") { return None; }
    // Reuse the existing bounded duplicate-key-rejecting JSON reader only;
    // crop operation/state semantics are not involved.
    let value = crate::portrait_crop_protocol::unique_json(line, 32768).ok()?;
    receive(epoch, &value).then_some(value)
}

#[tauri::command]
pub(crate) fn final_canvas_flip(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = checked(&request)?.to_owned();
    {
        let mut m=mailbox().lock().map_err(|_|"翻转回执锁错误，原身份不能证明未发送")?;
        if let Some(old)=m.get(&id) {
            if old.request==request { return Ok(json!({"requested":true,"request_id":id,"replayed":true})); }
            return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"请求身份冲突")}));
        }
        if m.len()>=4096 { return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"翻转回执容量已满；请保存并重启应用")})); }
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
pub(crate) fn final_canvas_flip_status(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    let guard = state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive());
    let epoch=handle.map(|h|h.epoch());
    // Order matters: first observe idle (after FIFO command_done), then read
    // reset generation. Reading generation first could miss an earlier buffered
    // project_opened that RX processes just before that idle observation.
    let observed_queue=handle.map(|h|h.queue_stats());
    let opened=generation(epoch.unwrap_or([0;16]))?;
    let mut m = mailbox().lock().map_err(|_|"翻转回执锁错误")?;
    if !m.contains_key(&id) {
        if m.len()>=4096 { return Err("翻转回执容量已满；请重启应用后重新打开工程".into()); }
        // Lost native mailbox is NOT proof of non-delivery. Start a recovery
        // observation now; require a *later* verified open or epoch replacement.
        m.insert(id.clone(),Row{epoch:epoch.unwrap_or([0;16]),generation:u64::MAX,request:request.clone(),result:None,abandoned:false,observed_only:true,admission_pending:false,recovery_observed:false});
    }
    let row=m.get_mut(&id).ok_or("翻转回执不可用")?;
    if row.request!=request { return Err("翻转查询原请求不匹配".into()); }
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
pub(crate) fn final_canvas_flip_abandon(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive()).ok_or("请启动新引擎并打开已确认的照片/工程")?;
    let opened=generation(handle.epoch())?;
    let mut m=mailbox().lock().map_err(|_|"翻转回执锁错误")?;
    let row=m.get_mut(&id).ok_or("先查询原操作，再重新打开已确认的工程")?;
    if row.request!=request { return Err("翻转恢复原请求不匹配".into()); }
    if !row.abandoned {
        if row.result.as_ref().is_some_and(|r|r["outcome_unknown"]==false) { return Err("原操作已有准确终态；请查询结果".into()); }
        if !recovery_allowed(row,handle.epoch(),opened,&handle.queue_stats()) { return Err("尚无新引擎或后续工程重新打开证明，或队列未静止；旧操作不能放弃".into()); }
        row.abandoned=true;
    }
    // No engine command, recipe edit, resend, or invented success is published.
    Ok(json!({"request_id":id,"phase":"abandoned","original_request":row.request,"previous_outcome":"unknown","recovery_available":false}))
}

// AUTHORED / UNRUN: retained exact outcomes, not runtime acceptance evidence.
#[cfg(test)]
mod tests {
    use super::*;
    fn request(id: &str) -> Value { json!({"cmd":"final_canvas_flip","request_id":id,"document_id":"doc","revision":"9","horizontal":true,"vertical":false}) }
    fn registered(id: &str, epoch: [u8;16]) -> Value {
        let r=request(id); mailbox().lock().unwrap().insert(id.into(),Row{epoch,generation:0,request:r.clone(),result:None,abandoned:false,observed_only:false,admission_pending:false,recovery_observed:false});r
    }
    fn applied(r:&Value)->Value {json!({"event":"final_canvas_flip_result","protocol":1,"request_id":r["request_id"],"original_request":r,
        "success":true,"outcome_unknown":false,"requires_reload":false,"phase":"applied","result_revision":"10","spec":{"horizontal":true,"vertical":false}})}
    #[test] fn exact_binding_epoch_state_and_first_terminal() {
        let epoch=[193;16];let r=registered("flip-exact",epoch);let result=applied(&r);
        assert!(!receive([194;16],&result));
        for key in ["document_id","revision","horizontal","vertical"] {
            let mut wrong=result.clone();wrong["original_request"][key]=Value::Null;assert!(!receive(epoch,&wrong));
        }
        let mut wrong=result.clone();wrong["result_revision"]=json!("9");assert!(!receive(epoch,&wrong));
        wrong=result.clone();wrong["spec"]["horizontal"]=json!(false);assert!(!receive(epoch,&wrong));
        assert!(receive(epoch,&result));assert!(!receive(epoch,&result));
    }
    #[test] fn raw_duplicates_and_acks_do_not_settle_recovery() {
        let epoch=[195;16];let r=registered("flip-recovery",epoch);
        crate::project_recovery_fence::issued(epoch,&r).unwrap();
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        assert!(!receive(epoch,&json!({"request_id":"flip-recovery","requested":true})));
        assert!(observe_line(epoch,r#"{"event":"final_canvas_flip_result","success":true,"success":false}"#).is_none());
        let mut wrong=applied(&r);wrong["original_request"]["revision"]=json!("8");
        crate::project_recovery_fence::observed(epoch,&wrong);
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        let result=applied(&r);let marker=observe_line(epoch,&result.to_string()).unwrap();
        crate::project_recovery_fence::observed(epoch,&marker);
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
    #[test] fn strict_bool_and_unknown_cannot_look_successful() {
        let epoch=[196;16];let r=registered("flip-unknown",epoch);
        let mut bad=r.clone();bad["horizontal"]=json!(1);assert!(checked(&bad).is_err());
        let mut result=applied(&r);result["outcome_unknown"]=json!(true);assert!(!receive(epoch,&result));
        result=json!({"event":"final_canvas_flip_result","protocol":1,"request_id":r["request_id"],"original_request":r,
            "success":false,"outcome_unknown":true,"requires_reload":true,"phase":"unknown","error":"rollback proof failed"});
        assert!(receive(epoch,&result));
    }
    #[test] fn native_admission_refusal_is_known_not_sent_and_settles_only_own_fence() {
        let epoch=[197;16];let r=registered("flip-not-sent",epoch);
        crate::project_recovery_fence::issued(epoch,&r).unwrap();
        let answer=rejected_admission(epoch,&r,"another owner rejected before enqueue");
        assert_eq!(answer["requested"],false);assert_eq!(answer["result"]["phase"],"not_sent");
        assert_eq!(answer["result"]["original_request"],r);
        assert_eq!(answer["result"]["outcome_unknown"],false);
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
        assert_eq!(mailbox().lock().unwrap().get("flip-not-sent").unwrap().result.as_ref().unwrap()["phase"],"not_sent");
        let other=registered("flip-forged-not-sent",[198;16]);
        assert!(!receive([198;16],&not_sent(&other,"engine cannot fabricate native admission")));
    }
    #[test] fn unknown_wait_is_abandonable_only_after_idle_verified_reset() {
        let epoch=[199;16];let r=registered("flip-reset",epoch);
        let idle=json!({"pending":0,"in_flight":false,"closed":false});
        {let mut m=mailbox().lock().unwrap();let row=m.get_mut("flip-reset").unwrap();
            assert!(!recovery_allowed(row,epoch,0,&idle));
            observe_unresolved_idle(row,epoch,0,&idle);
            assert!(!recovery_allowed(row,epoch,0,&idle)); // explicit query alone is not authority.
        }
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
        assert_eq!(generation(epoch).unwrap(),0);
        // AUTHORED / UNRUN repair: create keeps live _docs, so it is never the
        // later state-replacing reset required by this flip's idle baseline.
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_created","open":true,"path":"/fixture/new.lrt","project_id":"new","docs":1,"dirty":true}));
        assert_eq!(generation(epoch).unwrap(),0);
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened","open":true,"path":"/fixture/confirmed.lrt","project_id":"confirmed","docs":1,"dirty":false}));
        let opened=generation(epoch).unwrap();assert_eq!(opened,1);
        let m=mailbox().lock().unwrap();let row=m.get("flip-reset").unwrap();
        assert!(recovery_allowed(row,epoch,opened,&idle));
        assert!(!recovery_allowed(row,epoch,opened,&json!({"pending":1,"in_flight":false,"closed":false})));
        assert!(!recovery_allowed(row,epoch,opened,&json!({"pending":0,"in_flight":true,"closed":false})));
        assert!(recovery_allowed(row,[200;16],0,&idle));
        assert_eq!(row.request,r);assert!(row.result.is_none()); // Unknown was never called success.
    }
    #[test] fn buffered_earlier_open_and_missing_mailbox_need_later_reset() {
        let epoch=[201;16];let idle=json!({"pending":0,"in_flight":false,"closed":false});
        let running=json!({"pending":0,"in_flight":true,"closed":false});
        let mut row=Row{epoch,generation:u64::MAX,request:request("flip-buffered"),result:None,
            abandoned:false,observed_only:false,admission_pending:false,recovery_observed:false};
        // Earlier open was queued before flip, but its RX event arrives after
        // flip enqueue. It cannot arm recovery while flip is in flight.
        observe_unresolved_idle(&mut row,epoch,1,&running);
        assert!(!row.recovery_observed);
        // Flip command_done is consumed after that buffered event. First idle
        // status anchors at 1, never at the old enqueue-time generation 0.
        observe_unresolved_idle(&mut row,epoch,1,&idle);
        assert!(!recovery_allowed(&row,epoch,1,&idle));
        assert!(recovery_allowed(&row,epoch,2,&idle));
        row.observed_only=true;row.recovery_observed=false;row.generation=u64::MAX;
        observe_unresolved_idle(&mut row,epoch,4,&idle);
        assert!(!recovery_allowed(&row,epoch,4,&idle));
        assert!(recovery_allowed(&row,epoch,5,&idle));
        assert!(recovery_allowed(&row,[202;16],0,&idle)); // Replacement cannot run old epoch-bound request.
        row.epoch=[0;16];row.recovery_observed=false;
        assert!(!recovery_allowed(&row,epoch,5,&idle)); // Offline orphan is not a known old engine.
        observe_unresolved_idle(&mut row,epoch,5,&idle);
        assert!(!recovery_allowed(&row,epoch,5,&idle));
        assert!(recovery_allowed(&row,epoch,6,&idle));
    }
    #[test] fn not_sent_id_collision_cannot_settle_another_command_family() {
        let epoch=[203;16];
        let exposure=json!({"cmd":"exposure","request_id":"flip-collision","ev":1});
        crate::project_recovery_fence::issued(epoch,&exposure).unwrap();
        let flip=registered("flip-collision",epoch);
        assert!(crate::project_recovery_fence::issued(epoch,&flip).is_err());
        let response=rejected_admission(epoch,&flip,"request ID belongs to exposure");
        assert!(!guards_result(epoch,"flip-collision")); // Do not suppress exposure's real receipt in RX.
        assert_eq!(response["result"]["phase"],"not_sent");
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"exposure_result","request_id":"flip-collision","success":true,"outcome_unknown":false}));
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
}
