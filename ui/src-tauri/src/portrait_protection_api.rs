//! Epoch-bound retained exact receipts. Queue acknowledgement is not edit success.
use std::{collections::{HashMap, HashSet}, sync::{Arc, Mutex, OnceLock}};
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
    Ok(*workspaces().lock().map_err(|_|"人像保护工作区证明锁错误")?.get(&epoch).unwrap_or(&0))
}
/// Called only by this module after strict unique-key raw project-open validation.
/// Creating a new project preserves live documents and is not recovery evidence.
fn verified_workspace_opened(epoch: [u8;16]) {
    if let Ok(mut clock)=workspaces().lock() {
        if !clock.contains_key(&epoch) && clock.len()>=4096 { return; }
        let old=*clock.get(&epoch).unwrap_or(&0);
        if let Some(next)=old.checked_add(1) { clock.insert(epoch,next); }
    }
}
fn tainted_epochs() -> &'static Mutex<HashSet<[u8;16]>> {
    static TAINT: OnceLock<Mutex<HashSet<[u8;16]>>> = OnceLock::new();
    TAINT.get_or_init(||Mutex::new(HashSet::new()))
}
fn taint(epoch:[u8;16]) {
    if let Ok(mut epochs)=tainted_epochs().lock() {
        // Capacity failure is fail-closed for all same-epoch recovery, never eviction.
        if epochs.len()>=4096 {epochs.insert([0;16]);} else {epochs.insert(epoch);}
    }
}
fn trustworthy_idle(epoch:[u8;16])->bool {
    tainted_epochs().lock().map(|epochs|!epochs.contains(&epoch)&&!epochs.contains(&[0;16])).unwrap_or(false)
}
fn verified_open(value:&Value)->bool {
    let fields=["event","docs","auto_opened","task_restore","proxy_budget","missing","missing_count",
        "changed","changed_count","restore_ms","saved_ns","assets","notes","notes_count","open","path",
        "name","project_id","dirty","tasks","writer","writer_match","dropped_count","project_recovery",
        "managed_import","source_relocation","success","outcome_unknown","requires_reload","requires_readback"];
    value.as_object().is_some_and(|o|o.keys().all(|k|fields.contains(&k.as_str())))
        && value["event"]=="project_opened" && value["open"]==true
        && value["path"].as_str().is_some_and(|s|!s.trim().is_empty()&&s.len()<=4096&&!s.contains('\0'))
        && value["project_id"].as_str().is_some_and(|s|!s.trim().is_empty()&&s.len()<=128&&!s.chars().any(char::is_control))
        && value["docs"].is_u64() && value["dirty"].is_boolean()
        && value.get("success").map_or(true,|v|v.as_bool()==Some(true))
        && ["outcome_unknown","requires_reload","requires_readback"].iter().all(|k|value.get(*k).map_or(true,|v|v.as_bool()==Some(false)))
        && value.get("error").is_none()
}
/// Raw RX proof only. A generic serde reparse is used solely to *taint* invalid
/// completion packets, never to authorize a reset. Decode escaped event names too.
pub(crate) fn observe_recovery_line(epoch:[u8;16],line:&str) {
    let value=match crate::portrait_crop_protocol::unique_json(line,4*1024*1024) {
        Ok(value)=>value,
        Err(_)=>{
            if serde_json::from_str::<Value>(line).ok().is_some_and(|v|v["event"]=="command_done") {taint(epoch);}
            return;
        }
    };
    if value["event"]=="command_done" {
        if !value.as_object().is_some_and(|o|o.len()==2&&o.contains_key("event")&&o.contains_key("request_id"))
            || !value["request_id"].is_u64() {taint(epoch);}
    } else if verified_open(&value) {verified_workspace_opened(epoch);}
}
fn queue_idle(queue:&Value)->bool {
    queue["pending"].as_u64()==Some(0) && queue["in_flight"]==false && queue["closed"]==false
}
fn observe_unresolved_idle(row:&mut Row, epoch:[u8;16], opened:u64, queue:&Value) {
    // A restored UI request with no native mailbox reserves its identity before
    // this point. A late invocation can only replay that row, never send again.
    if row.observed_only && row.epoch==[0;16] { row.epoch=epoch; }
    let unresolved=row.result.as_ref().map_or(true,|r|r["outcome_unknown"]==true);
    if unresolved && trustworthy_idle(epoch) && !row.admission_pending && !row.recovery_observed && row.epoch==epoch && queue_idle(queue) {
        // RX processes project_opened before the command_done that releases its
        // dispatcher slot. At idle, all earlier queued reset events have passed;
        // only a later verified reset can exceed this explicit query baseline.
        row.generation=opened;
        row.recovery_observed=true;
    }
}
fn recovery_allowed(row:&Row, epoch:[u8;16], opened:u64, queue:&Value)->bool {
    trustworthy_idle(epoch) && queue_idle(queue) && (
        // Recorded nonzero epoch is authoritative: epoch-bound admission cannot
        // dispatch this old request into a replacement process.
        (row.epoch!=[0;16] && row.epoch!=epoch)
        || (!row.admission_pending && row.recovery_observed && row.epoch==epoch && opened>row.generation))
}

fn not_sent(request:&Value, error:&str)->Value {
    json!({"event":"portrait_protection_result","protocol":1,"request_id":request["request_id"],
        "original_request":request,"success":false,"outcome_unknown":false,"requires_reload":false,
        "phase":"not_sent","authority":"native-admission","error":format!("人像保护未入队，未修改：{error}")})
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
fn valid_controls(value: &Value) -> bool {
    let Some(o)=value.as_object() else { return false; };
    let fields=["enabled","strength","protect_identity_marks","analysis_enabled","overlay_visible","feather","protected_regions"];
    if o.len()!=fields.len() || !fields.iter().all(|key|o.contains_key(*key)) { return false; }
    if !["enabled","protect_identity_marks","analysis_enabled","overlay_visible"].iter().all(|key|value[*key].is_boolean())
        || !value["strength"].as_f64().is_some_and(|n|n.is_finite() && (0.0..=1.0).contains(&n))
        || !value["feather"].as_u64().is_some_and(|n|n<=256) { return false; }
    let Some(boxes)=value["protected_regions"].as_array() else { return false; };
    boxes.len()<=64 && boxes.iter().all(|b| {
        let Some(b)=b.as_array() else { return false; };
        b.len()==4 && b.iter().all(|n|n.as_f64().is_some_and(|n|n.is_finite() && (0.0..=1.0).contains(&n)))
            && b[0].as_f64()<b[2].as_f64() && b[1].as_f64()<b[3].as_f64()
    })
}
// Python's canonical strength is float even when JSON input was 0 or 1.
// Compare numeric values only after strict structural/range validation.
fn same_controls(a:&Value,b:&Value)->bool {
    valid_controls(a) && valid_controls(b)
        && ["enabled","protect_identity_marks","analysis_enabled","overlay_visible","feather"].iter().all(|k|a[*k]==b[*k])
        && a["strength"].as_f64()==b["strength"].as_f64()
        && a["protected_regions"].as_array().zip(b["protected_regions"].as_array()).is_some_and(|(left,right)|
            left.len()==right.len() && left.iter().zip(right).all(|(l,r)|
                (0..4).all(|i|l[i].as_f64()==r[i].as_f64())))
}
fn checked(request: &Value) -> Result<&str, String> {
    let object = request.as_object().ok_or("人像保护请求必须是对象")?;
    let fields = ["cmd", "request_id", "document_id", "revision", "controls"];
    if object.len() != fields.len() || !fields.iter().all(|k| object.contains_key(*k))
        || request["cmd"] != "portrait_protection" || !valid_controls(&request["controls"]) { return Err("人像保护请求字段无效".into()); }
    let id = request["request_id"].as_str().filter(|s| !s.is_empty() && s.len() <= 128)
        .ok_or("人像保护请求缺少有界身份")?;
    let document = request["document_id"].as_str().ok_or("缺少文档绑定")?;
    let revision = request["revision"].as_str().ok_or("缺少版本绑定")?;
    if document.is_empty() || document.len() > 128 || document == "0"
        || !document.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
        || !decimal(revision) { return Err("人像保护请求缺少有效文档/版本绑定，请刷新当前照片".into()); }
    Ok(id)
}
fn receive(epoch: [u8; 16], value: &Value) -> bool {
    let Some(id) = value["request_id"].as_str() else { return false };
    let Ok(mut m) = mailbox().lock() else { return false };
    let Some(row) = m.get_mut(id) else { return false };
    if row.epoch != epoch || row.result.is_some() || value.to_string().len() > 32768
        || value["event"] != "portrait_protection_result" || value["protocol"] != 1
        || value["original_request"] != row.request || !value["success"].is_boolean()
        || !value["outcome_unknown"].is_boolean() || !value["requires_reload"].is_boolean() { return false; }
    let phase = value["phase"].as_str().unwrap_or("");
    if value["success"] == true {
        let Some(before) = row.request["revision"].as_str().and_then(|s|s.parse::<u64>().ok()) else { return false };
        let after = value["result_revision"].as_str().filter(|s|decimal(s)).and_then(|s|s.parse::<u64>().ok());
        let expected = if phase == "applied" { before.checked_add(1) } else if phase == "no_change" { Some(before) } else { None };
        if expected.is_none() || after != expected || value["outcome_unknown"] != false || value["requires_reload"] != false
            || !same_controls(&value["spec"], &row.request["controls"]) { return false; }
    } else if !matches!(phase, "rejected" | "rolled_back" | "unknown") || !value["error"].is_string()
        || (phase == "unknown") != (value["outcome_unknown"] == true)
        || (phase == "unknown") != (value["requires_reload"] == true) { return false; }
    row.result = Some(value.clone());
    true
}
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox().lock().map(|m|m.get(id).is_some_and(|r|r.epoch==epoch
        && crate::project_recovery_fence::portrait_protection_pending(epoch,&r.request))).unwrap_or(true)
}
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    if !line.contains("portrait_protection_result") { return None; }
    // Reuse the existing bounded duplicate-key-rejecting JSON reader only;
    // crop operation/state semantics are not involved.
    let value = crate::portrait_crop_protocol::unique_json(line, 32768).ok()?;
    receive(epoch, &value).then_some(value)
}

#[tauri::command]
pub(crate) fn portrait_protection(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = checked(&request)?.to_owned();
    {
        let mut m=mailbox().lock().map_err(|_|"人像保护回执锁错误，原身份不能证明未发送")?;
        if let Some(old)=m.get(&id) {
            if old.request==request { return Ok(json!({"requested":true,"request_id":id,"replayed":true})); }
            return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"请求身份冲突")}));
        }
        if m.len()>=4096 { return Ok(json!({"requested":false,"request_id":id,"phase":"done","result":not_sent(&request,"人像保护回执容量已满；请保存并重启应用")})); }
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
pub(crate) fn portrait_protection_status(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    let guard = state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive());
    let epoch=handle.map(|h|h.epoch());
    // Order matters: first observe idle (after FIFO command_done), then read
    // reset generation. Reading generation first could miss an earlier buffered
    // project_opened that RX processes just before that idle observation.
    let observed_queue=handle.map(|h|h.queue_stats());
    let opened=generation(epoch.unwrap_or([0;16]))?;
    let mut m = mailbox().lock().map_err(|_|"人像保护回执锁错误")?;
    if !m.contains_key(&id) {
        if m.len()>=4096 { return Err("人像保护回执容量已满；请重启应用后重新打开工程".into()); }
        // Lost native mailbox is NOT proof of non-delivery. Start a recovery
        // observation now; require a *later* verified open or epoch replacement.
        m.insert(id.clone(),Row{epoch:epoch.unwrap_or([0;16]),generation:u64::MAX,request:request.clone(),result:None,abandoned:false,observed_only:true,admission_pending:false,recovery_observed:false});
    }
    let row=m.get_mut(&id).ok_or("人像保护回执不可用")?;
    if row.request!=request { return Err("人像保护查询原请求不匹配".into()); }
    if let (Some(h),Some(queue))=(handle,observed_queue.as_ref()) { observe_unresolved_idle(row,h.epoch(),opened,queue); }
    let recover=handle.is_some_and(|h|recovery_allowed(row,h.epoch(),opened,&h.queue_stats()));
    let hint=if recover {"已验证新工作区；可明确放弃旧等待，旧结果仍未知，不会重发。"}
        else if epoch.is_some_and(|e|!trustworthy_idle(e)) {"引擎完成回执格式异常，当前会话无法证明队列静止；请更换引擎会话并重新打开已确认工程，再查询原请求，不会重发。"}
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
pub(crate) fn portrait_protection_abandon(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id=checked(&request)?.to_owned();
    let guard=state.engine.lock().map_err(|_|"引擎锁错误")?;
    let handle=guard.as_ref().filter(|h|h.is_alive()).ok_or("请启动新引擎并打开已确认的照片/工程")?;
    let opened=generation(handle.epoch())?;
    let mut m=mailbox().lock().map_err(|_|"人像保护回执锁错误")?;
    let row=m.get_mut(&id).ok_or("先查询原操作，再重新打开已确认的工程")?;
    if row.request!=request { return Err("人像保护恢复原请求不匹配".into()); }
    if !row.abandoned {
        if row.result.as_ref().is_some_and(|r|r["outcome_unknown"]==false) { return Err("原操作已有准确终态；请查询结果".into()); }
        if !recovery_allowed(row,handle.epoch(),opened,&handle.queue_stats()) { return Err("尚无新引擎或后续工程重新打开证明，或队列未静止；旧操作不能放弃".into()); }
        row.abandoned=true;
        crate::project_recovery_fence::abandon_portrait_protection(row.epoch,&row.request);
    }
    // No engine command, recipe edit, resend, or invented success is published.
    Ok(json!({"request_id":id,"phase":"abandoned","original_request":row.request,"previous_outcome":"unknown","recovery_available":false}))
}
