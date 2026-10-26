//! Bounded retained-chain plans and metadata-only receipts. No snapshot replay.
use serde_json::Value;
pub(crate) const MAX_HISTORY:u64=64;
pub(crate) const REQUEST_PREFIX:&str="history-nav-v1:";
fn reserved(s:&str)->bool {s.starts_with(REQUEST_PREFIX)}
fn navigation_id(v:&Value)->bool {text(v)&&v.as_str().is_some_and(|s|reserved(s)&&s.len()>REQUEST_PREFIX.len())}
/// A syntactic namespace, not an ID ledger. Every native transport lane checks
/// this before queueing/writing, so no genuine other-family terminal can own a
/// navigation ID. Include nested/target/capture/operation ID aliases used by
/// cancellation controls and compatibility routes.
fn borrowed_namespace(v:&Value)->bool {
    match v {
        Value::Object(fields)=>fields.iter().any(|(k,value)|
            ((k=="id"||k.ends_with("_id"))&&value.as_str().is_some_and(reserved))||borrowed_namespace(value)),
        Value::Array(items)=>items.iter().any(borrowed_namespace),
        _=>false,
    }
}
pub(crate) fn admission(command:&Value)->Result<(),String> {
    if command["cmd"]=="history_navigation" {checked(command).map(|_|())}
    else if borrowed_namespace(command) {Err("历史导航请求身份为保留命名空间；其他操作未发送".into())}
    else {Ok(())}
}
/// These are navigation-exclusive top-level markers, not generic phase/protocol
/// fields. A renamed receipt with request_id removed is still not an App event.
pub(crate) fn navigation_shaped(value:&Value)->bool {
    value["event"]=="history_navigation_result" || value["original_request"]["cmd"]=="history_navigation"
        || ["completed_steps","reached","last_confirmed"].iter().any(|key|value.get(*key).is_some())
}
fn fields(v:&Value, keys:&[&str])->bool {v.as_object().is_some_and(|o|o.len()==keys.len()&&keys.iter().all(|k|o.contains_key(*k)))}
fn text(v:&Value)->bool {v.as_str().is_some_and(|s|!s.is_empty()&&s.len()<=128&&!s.contains('\0'))}
fn revision(v:&Value)->Option<u64> {let s=v.as_str()?;(!s.is_empty()&&s.len()<=20&&(s=="0"||!s.starts_with('0'))&&s.bytes().all(|b|b.is_ascii_digit())).then(||s.parse().ok()).flatten()}
pub(crate) fn view(v:&Value)->bool {
    fields(v,&["workspace","document_id","load_id","revision","digest","cursor","undo_steps","redo_steps","history_max"])
        && ["workspace","document_id","load_id"].iter().all(|k|text(&v[*k]))&&revision(&v["revision"]).is_some()
        && v["digest"].as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)))
        && v["history_max"].as_u64().is_some_and(|limit| (1..=MAX_HISTORY).contains(&limit)
            && v["undo_steps"].as_u64().is_some_and(|n|n<=limit)&&v["redo_steps"].as_u64().is_some_and(|n|n<=limit))
        && v["cursor"]==v["undo_steps"]
}
pub(crate) struct Plan {pub(crate) direction:&'static str,pub(crate) steps:u64}
pub(crate) fn checked(r:&Value)->Result<Option<Plan>,String> {
    if r["cmd"]!="history_navigation"||!navigation_id(&r["request_id"]) {return Err("历史请求身份无效".into());}
    if r["action"]=="state"&&fields(r,&["cmd","action","request_id"]) {return Ok(None);}
    if r["action"]!="navigate"||!fields(r,&["cmd","action","request_id","view","target"])||!view(&r["view"]) {return Err("历史选择绑定无效；请刷新历史".into());}
    let v=&r["view"];let total=v["undo_steps"].as_u64().unwrap()+v["redo_steps"].as_u64().unwrap();
    let target=r["target"].as_u64().filter(|t|*t<=total).ok_or("历史目标不在实际保留范围")?;
    if total>v["history_max"].as_u64().unwrap() {return Err("两侧历史总长度超过保留上限；跳转会淘汰端点，未提交".into());}
    let cursor=v["cursor"].as_u64().unwrap();
    if revision(&v["revision"]).and_then(|n|n.checked_add(target.abs_diff(cursor))).is_none() {return Err("文档版本不足以完成此跳转；未提交".into());}
    Ok(Some(Plan{direction:if target>cursor{"redo"}else{"undo"},steps:target.abs_diff(cursor)}))
}
pub(crate) fn mutation(r:&Value)->bool {r["cmd"]=="history_navigation"&&r["action"]=="navigate"}
pub(crate) fn read_only(r:&Value)->bool {checked(r).is_ok_and(|p|p.is_none())}
fn reached(r:&Value,v:&Value,completed:u64,plan:&Plan)->bool {
    if !view(v) {return false;}
    let before=&r["view"];
    let cursor=before["cursor"].as_u64().unwrap();
    let expected=if plan.direction=="redo" {cursor.checked_add(completed)}else{cursor.checked_sub(completed)};
    ["workspace","document_id","load_id","history_max"].iter().all(|k|v[*k]==before[*k])
        && v["cursor"].as_u64()==expected
        && v["undo_steps"].as_u64().unwrap()+v["redo_steps"].as_u64().unwrap()==before["undo_steps"].as_u64().unwrap()+before["redo_steps"].as_u64().unwrap()
        && revision(&before["revision"]).zip(revision(&v["revision"])).is_some_and(|(a,b)|b>=a&&a.checked_add(plan.steps).is_some_and(|end|b<=end))
}
pub(crate) fn receipt(r:&Value,v:&Value)->bool {
    let Some(o)=v.as_object() else{return false;};
    let required=["event","protocol","request_id","original_request","success","outcome_unknown","requires_reload","phase","completed_steps","reached","last_confirmed"];
    if !required.iter().all(|k|o.contains_key(*k))||o.keys().any(|k|!required.contains(&k.as_str())&&k!="error"&&k!="view") {return false;}
    if v["event"]!="history_navigation_result"||v["protocol"]!=1||v["request_id"]!=r["request_id"]||v["original_request"]!=*r
        ||!v["success"].is_boolean()||!v["outcome_unknown"].is_boolean()||!v["requires_reload"].is_boolean() {return false;}
    let Ok(plan)=checked(r) else{return false;};
    let Some(done)=v["completed_steps"].as_u64() else{return false;};
    let phase=v["phase"].as_str().unwrap_or("");
    let Some(plan)=plan else {
        return done==0&&v["reached"].is_null()&&v["last_confirmed"].is_null()&&v["outcome_unknown"]==false&&v["requires_reload"]==false
            && ((phase=="state"&&v["success"]==true&&view(&v["view"]))||(phase=="rejected"&&v["success"]==false&&v["error"].is_string()));
    };
    if done>plan.steps||v.get("view").is_some() {return false;}
    if phase=="unknown" {
        return v["success"]==false&&v["outcome_unknown"]==true&&v["requires_reload"]==true&&v["error"].is_string()&&v["reached"].is_null()
            && (v["last_confirmed"].is_null()||reached(r,&v["last_confirmed"],done,&plan));
    }
    if v["outcome_unknown"]!=false||v["requires_reload"]!=false {return false;}
    match phase {
        "applied"|"no_change" => v["success"]==true&&done==plan.steps&&(phase=="no_change")== (plan.steps==0)
            && reached(r,&v["reached"],done,&plan)&&v["last_confirmed"]==v["reached"]
            && (phase!="no_change"||v["reached"]==r["view"]),
        "partial" => v["success"]==false&&done>0&&done<plan.steps&&v["error"].is_string()
            && reached(r,&v["reached"],done,&plan)&&v["last_confirmed"]==v["reached"],
        "rejected" => v["success"]==false&&done==0&&v["error"].is_string()
            && ((v["reached"].is_null()&&v["last_confirmed"].is_null())
                ||(reached(r,&v["reached"],0,&plan)&&v["last_confirmed"]==v["reached"])),
        _ => false,
    }
}

// AUTHORED / UNRUN. No Rust build or test execution was performed.
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn request()->Value {json!({"cmd":"history_navigation","action":"navigate","request_id":"history-nav-v1:jump","target":0,
        "view":{"workspace":"workspace","document_id":"doc","load_id":"load","revision":"7","digest":"a".repeat(64),"cursor":3,"undo_steps":3,"redo_steps":1,"history_max":64}})}
    fn partial()->Value {
        let mut reached=request()["view"].clone(); reached["revision"]=json!("9");reached["digest"]=json!("b".repeat(64));
        reached["cursor"]=json!(2);reached["undo_steps"]=json!(2);reached["redo_steps"]=json!(2);
        json!({"event":"history_navigation_result","protocol":1,"request_id":"history-nav-v1:jump","original_request":request(),
            "success":false,"outcome_unknown":false,"requires_reload":false,"phase":"partial","completed_steps":1,
            "reached":reached,"last_confirmed":reached,"error":"protected edge refused"})
    }
    #[test] fn bounded_plan_requires_exact_digest_and_retained_domain() {
        let r=request();let p=checked(&r).unwrap().unwrap();assert_eq!(p.direction,"undo");assert_eq!(p.steps,3);
        let mut bad=r.clone();bad["target"]=json!(5);assert!(checked(&bad).is_err());
        bad=r.clone();bad["view"]["digest"]=json!("");assert!(checked(&bad).is_err());
        bad=r.clone();bad["target"]=json!(true);assert!(checked(&bad).is_err());
        bad=r.clone();bad["view"]["revision"]=json!("18446744073709551615");assert!(checked(&bad).is_err());
        bad=r;bad["view"]["history_max"]=json!(3);assert!(checked(&bad).is_err());
    }
    #[test] fn partial_and_unknown_never_become_target_success() {
        let r=request();let mut v=partial();assert!(receipt(&r,&v));
        v["success"]=json!(true);assert!(!receipt(&r,&v));
        v=partial();v["phase"]=json!("applied");assert!(!receipt(&r,&v));
        v=partial();v["phase"]=json!("unknown");v["outcome_unknown"]=json!(true);v["requires_reload"]=json!(true);v["reached"]=Value::Null;
        assert!(receipt(&r,&v));v["reached"]=v["last_confirmed"].clone();assert!(!receipt(&r,&v));
    }
    #[test] fn metadata_and_receipt_reject_other_owner_and_raw_snapshot() {
        let r=request();for key in ["workspace","document_id","load_id","revision","digest"] {
            let mut v=partial();v["original_request"]["view"][key]=json!("different");assert!(!receipt(&r,&v));
        }
        let mut v=partial();v["snapshot"]=json!({});assert!(!receipt(&r,&v));
        assert!(!receipt(&r,&json!({"request_id":"history-nav-v1:jump","requested":true})));
    }
    #[test] fn no_change_is_exact_original_view_not_merely_same_cursor() {
        let mut r=request();r["target"]=r["view"]["cursor"].clone();
        let mut v=partial();v["original_request"]=r.clone();v["phase"]=json!("no_change");v["success"]=json!(true);v["completed_steps"]=json!(0);
        v["reached"]=r["view"].clone();v["last_confirmed"]=r["view"].clone();assert!(receipt(&r,&v));
        v["reached"]["digest"]=json!("c".repeat(64));v["last_confirmed"]=v["reached"].clone();assert!(!receipt(&r,&v));
    }

    #[test] fn namespace_prevents_every_foreign_family_before_send_or_control_write() {
        let id="history-nav-v1:fixture";
        for command in ["hand_shape","background_material_library","creative_selection","ingest_session","workflow_owner",
            "torso_length","waist_length","head_size","body_slim","photo_grain_state","colour_editor_preview",
            "virtual_copy","project_recovery","managed_import","canvas_guides","project_package","source_relocation","preset_organisation",
            "light_glow_cancel_read","upscale_restore_cancel_read","lens_blur_cancel_read","portrait_crop_cancel",
            "expression_replacement_cancel","eye_bag_cancel","sample_library_cancel","semantic_colour_cancel"] {
            assert!(admission(&json!({"cmd":command,"action":"state","request_id":id})).is_err(),"{command}");
            assert!(admission(&json!({"cmd":command,"action":"state","request_id":"ordinary-id"})).is_ok(),"{command}");
        }
        for alias in ["target_request_id","capture_id","operation_id","original_request_id","id"] {
            let mut borrowed=json!({"cmd":"creative_selection","action":"cancel","request_id":"ordinary-id","payload":{}});
            borrowed["payload"][alias]=json!(id);assert!(admission(&borrowed).is_err(),"{alias}");
        }
        assert!(admission(&request()).is_ok());
        for id in ["ordinary-id","history-nav-v1:"] {
            let mut bad=request();bad["request_id"]=json!(id);assert!(admission(&bad).is_err());
        }
    }

    #[test] fn stripped_identity_or_renamed_receipt_is_still_navigation_not_app_state() {
        let mut value=partial();value.as_object_mut().unwrap().remove("request_id");
        for event in ["project_opened","history_state","frame","ready"] {
            value["event"]=json!(event);assert!(navigation_shaped(&value));
        }
        for marker in ["completed_steps","reached","last_confirmed"] {
            let mut stripped=json!({"event":"project_opened","open":true,"path":"/fixture/project","docs":1});
            stripped[marker]=Value::Null;assert!(navigation_shaped(&stripped));
        }
        assert!(navigation_shaped(&json!({"event":"frame","original_request":{"cmd":"history_navigation"}})));
        assert!(!navigation_shaped(&json!({"event":"project_opened","open":true,"path":"/fixture/project","project_id":"project","docs":1,"dirty":false})));
        assert!(!navigation_shaped(&json!({"event":"other_result","protocol":1,"phase":"done","success":true,"original_request":{"cmd":"other"}})));
    }

}
