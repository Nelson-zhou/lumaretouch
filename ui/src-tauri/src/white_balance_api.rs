use std::sync::Arc;
use serde_json::{json,Value};
use tauri::State;
use crate::{AppState,engine::EngineHandle};
pub(crate) fn mutation(command:&Value)->bool {command["cmd"]=="white_balance" && command["action"]=="auto"}
fn checked_auto(command:&Value)->Result<(),String>{
    let fields=["cmd","action","request_id","document_id","input_id","recipe_document_id","recipe_revision"];
    if !mutation(command) || !command.as_object().is_some_and(|o|o.len()==fields.len()&&fields.iter().all(|k|o.contains_key(*k))) {
        return Err("invalid auto WB fields".into());
    }
    for (key,limit) in [("request_id",128),("document_id",64),("recipe_document_id",128)] {
        if !command[key].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=limit){return Err("invalid auto WB identity".into());}
    }
    if !command["input_id"].as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))) {
        return Err("invalid auto WB input hash".into());
    }
    if !command["recipe_revision"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=20&&(s=="0"||!s.starts_with('0'))&&s.bytes().all(|b|b.is_ascii_digit())&&s.parse::<u64>().is_ok()) {
        return Err("invalid auto WB revision".into());
    }
    Ok(())
}
pub(crate) fn binding(command:&Value)->Result<Option<Value>,String>{
    if !mutation(command){return Ok(None);}
    checked_auto(command)?;
    Ok(Some(json!({"event":"white_balance_result","protocol":1,"original_request":command})))
}
pub(crate) fn matches_request(command:&Value,value:&Value)->bool {
    use crate::receipt_host::ReceiptKind;
    mutation(command) && checked_auto(command).is_ok() && value["event"]=="white_balance_result"
        && value["action"]=="auto" && value["request_id"]==command["request_id"]
        && value["original_request"]==*command
        && crate::white_balance_host::WhiteBalanceKind::valid(value,command["document_id"].as_str())
}
fn not_sent(command:&Value,error:&str)->Value {
    json!({"event":"white_balance_result","protocol":1,"request_id":command["request_id"],
        "document_id":command["document_id"],"action":"auto","original_request":command,
        "success":false,"outcome_unknown":false,"requires_reload":false,"phase":"rejected","no_write":true,
        "authority":"native-admission","error":format!("自动白平衡未入队、未修改：{error}")})
}
pub(crate) fn enqueue(state:&AppState,handle:&EngineHandle,mut command:Value)->Result<(),String>{
    if command["action"]=="pick" || mutation(&command) {
        let epoch=command.as_object_mut().ok_or("invalid WB command")?.remove("host_epoch").ok_or("missing native WB epoch")?;
        if epoch.as_str()!=Some(crate::frame_identity::hex(handle.epoch()).as_str()){return Err("WB engine generation changed before dispatch".into());}
    }
    let id=command["request_id"].as_str().ok_or("missing WB request")?.to_owned();
    let action=command["action"].as_str().ok_or("missing WB action")?.to_owned();
    let mut host=state.white_balance_results.lock().map_err(|_|"WB receipt lock poisoned")?;
    if mutation(&command) {
        // Reserve this unique identity before any no-write admission result.
        // Duplicate/colliding invocations cannot claim an old request was not sent.
        host.begin_command(handle.epoch(),&command)?;
        let admission=(||->Result<(),String>{
            if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["white_balance_auto_protocol"]!=1 {
                return Err("匹配的自动白平衡 Rust 核心不可用".into());
            }
            let report=state.doc_report.lock().map_err(|_|"document lock poisoned")?;
            let current=report.as_ref().ok_or("current photo state unavailable")?;
            if current["doc_state"]["document_id"]!=command["document_id"]
                || !["input_id","recipe_document_id","recipe_revision"].iter().all(|k|current["doc_state"]["white_balance_auto_input"][*k]==command[*k]) {
                return Err("照片、配方或输入已变化，请刷新后重新选择操作".into());
            }
            Ok(())
        })();
        if let Err(error)=admission {host.receive(handle.epoch(),&not_sent(&command,&error));return Ok(());}
        // send() returns Err only before unkeyed Dispatcher.enqueue succeeds;
        // asynchronous OS-write errors arrive later and stay outcome-unknown.
        if let Err(error)=handle.send(command.clone()) {host.receive(handle.epoch(),&not_sent(&command,&error));}
        return Ok(());
    }
    let pick_binding=if action=="pick" {Some(crate::source_patch_host::binding(
        command["document_id"].as_str().ok_or("missing WB document")?,
        command["capture_id"].as_str().ok_or("missing WB capture")?,
        command["ticket"].as_str().ok_or("missing WB ticket")?)?)} else {None};
    host.begin_bound(handle.epoch(),&id,&action,pick_binding.as_deref().or(command["document_id"].as_str()))?;
    let result=handle.send(command);if let Err(error)=&result{host.failed(&id,error);}result
}
#[tauri::command]
pub(crate) fn white_balance(state:State<'_,Arc<AppState>>,action:String,algorithm:Option<String>,request_id:String,document_id:String,
    input_id:Option<String>,recipe_document_id:Option<String>,recipe_revision:Option<String>)->Result<Value,String>{
    if !["set_algorithm","reset","clear_pick","auto"].contains(&action.as_str()){return Err("invalid WB action".into());}
    if action=="set_algorithm" {
        if !algorithm.as_deref().is_some_and(|a|["legacy-xyz-ratio-v1","linear-srgb-d-white-ratio-v1"].contains(&a)){return Err("invalid WB algorithm".into());}
    } else if algorithm.is_some(){return Err("reset does not select an algorithm".into());}
    if state.ready_caps.lock().map_err(|_|"capability lock poisoned")?["white_balance_result_protocol"]!=1{return Err("engine does not support reviewed WB actions".into());}
    let mut command=json!({"cmd":"white_balance","action":action,"request_id":request_id,"document_id":document_id});
    if mutation(&command) {
        command["input_id"]=json!(input_id.ok_or("missing auto WB input")?);
        command["recipe_document_id"]=json!(recipe_document_id.ok_or("missing auto WB recipe")?);
        command["recipe_revision"]=json!(recipe_revision.ok_or("missing auto WB revision")?);
        checked_auto(&command)?;
        let guard=state.engine.lock().map_err(|_|"engine lock poisoned")?;
        let handle=guard.as_ref().ok_or("engine is not running")?;
        command["host_epoch"]=json!(crate::frame_identity::hex(handle.epoch()));
    } else if input_id.is_some()||recipe_document_id.is_some()||recipe_revision.is_some(){return Err("manual WB action cannot accept an auto input".into());}
    if let Some(value)=algorithm{command["algorithm"]=json!(value);}
    state.send_to_engine(command)?;Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn white_balance_result(state:State<'_,Arc<AppState>>,request_id:String)->Result<Value,String>{
    if request_id.is_empty()||request_id.len()>128{return Err("invalid WB request ID".into());}
    Ok(state.white_balance_results.lock().map_err(|_|"WB receipt lock poisoned")?.status(&request_id))
}
