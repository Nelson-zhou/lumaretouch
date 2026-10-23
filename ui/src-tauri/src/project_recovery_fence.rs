//! Conservative cross-domain native receipt fence, including direct engine sends.
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use serde_json::{json, Value};
fn pending()->&'static Mutex<HashMap<([u8;16],String),Value>> {
    static STORE:OnceLock<Mutex<HashMap<([u8;16],String),Value>>=OnceLock::new();
    STORE.get_or_init(||Mutex::new(HashMap::new()))
}
pub(crate) fn issued(epoch:[u8;16], command:&Value)->Result<(),String>{
    if command["cmd"]=="project_recovery" || crate::batch_api::read_only(command) {return Ok(());}
    let name=command["cmd"].as_str().unwrap_or("");
    if name.ends_with("_state")||name.ends_with("_receipt")||name.ends_with("_capture")||name.ends_with("_preview")||name.ends_with("_sample")
        || matches!(command["action"].as_str(),Some("state"|"status"|"query"|"receipt"|"list"|"context"|"preview"|"preview_support"|"preview_recovery")) {return Ok(());}
    let Some(id)=command["request_id"].as_str() else {return Ok(());};
    let mut store=pending().lock().map_err(|_|"恢复回执屏障锁不可用")?;
    let key=(epoch,id.to_owned());
    if let Some(prior)=store.get(&key) {if prior!=command{return Err("原请求尚未确认且身份冲突".into());}return Ok(());}
    if store.len()>=4096{return Err("未确认请求超过恢复屏障容量，请查询原请求或重新打开工程".into());}
    store.insert(key,command.clone()); Ok(())
}
pub(crate) fn observed(epoch:[u8;16], value:&Value){
    let Ok(mut store)=pending().lock() else{return;};
    if matches!(value["event"].as_str(),Some("project_opened"|"project_created")) {
        store.retain(|(e,_),_|*e!=epoch);return;
    }
    let Some(id)=value["request_id"].as_str() else{return;};
    let event=value["event"].as_str().unwrap_or("");
    if !(event.ends_with("_result")||event.ends_with("_done")||event.ends_with("_receipt")){return;}
    if value["outcome_unknown"]==true||value["requires_readback"]==true||value["requires_reload"]==true{return;}
    let status=value["status"].as_str().or(value["phase"].as_str());
    if matches!(status,Some("pending"|"running"|"unknown"|"queued"|"writing"|"accepted")){return;}
    if value["success"].is_boolean()||matches!(status,Some("succeeded"|"failed"|"committed"|"rejected"|"cancelled"|"done"|"readback"|"preview")) {
        store.remove(&(epoch,id.to_owned()));
    }
}
pub(crate) fn proof(epoch:[u8;16])->Result<Value,String>{
    let store=pending().lock().map_err(|_|"恢复回执屏障锁不可用")?;
    if store.keys().any(|(e,_)|*e==epoch){return Err("仍有原生请求正在处理或结果未知，自动保存暂缓".into());}
    Ok(json!({"native_settled":true,"native_receipts":[]}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn unknown_result_keeps_fence_until_explicit_new_workspace() {
        let epoch=[201;16];
        issued(epoch,&json!({"cmd":"people","action":"commit","request_id":"recovery-fixture"})).unwrap();
        observed(epoch,&json!({"event":"people_result","request_id":"recovery-fixture","success":false,"outcome_unknown":true}));
        assert!(proof(epoch).is_err());
        observed(epoch,&json!({"event":"project_opened"}));
        assert!(proof(epoch).is_ok());
    }
    #[test] fn terminal_receipt_settles_but_running_does_not() {
        let epoch=[202;16];
        issued(epoch,&json!({"cmd":"managed_import","action":"start","request_id":"import-fixture"})).unwrap();
        observed(epoch,&json!({"event":"managed_import_result","request_id":"import-fixture","status":"running"}));
        assert!(proof(epoch).is_err());
        observed(epoch,&json!({"event":"managed_import_result","request_id":"import-fixture","status":"succeeded"}));
        assert!(proof(epoch).is_ok());
    }
}
