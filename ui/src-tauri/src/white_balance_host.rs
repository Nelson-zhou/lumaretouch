//! Document-bound WB receipts; queue acceptance never proves an edit completed.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
pub(crate) struct WhiteBalanceKind;
const ALGORITHMS: [&str;2] = ["legacy-xyz-ratio-v1", "linear-srgb-d-white-ratio-v1"];
fn exposure(v: &Value) -> bool {
    let options = &v["options"];
    options.as_object().is_some_and(|o| o.len()==3) && options["version"].as_u64()==Some(1)
        && options["algorithm"].as_str().is_some_and(|s| ALGORITHMS.contains(&s))
        && options["picked_gains"].as_array().is_some_and(|a| a.len()==3 && a.iter().all(|n| n.as_f64().is_some_and(|x| x.is_finite()&&x>0.0)))
        && ["ev","temperature_shift","tint_shift","contrast","highlights","shadows","saturation"].iter().all(|k| v[*k].as_f64().is_some_and(f64::is_finite))
        && v.get("reference_k").is_some() && (v["reference_k"].is_null() || v["reference_k"].as_f64().is_some_and(|x| x.is_finite()&&(1000.0..=40000.0).contains(&x)))
}
fn pick_parts(bound: Option<&str>) -> Option<(&str, &str, &str)> {
    let mut values=bound?.split('|');
    let (document,capture,ticket)=(values.next()?,values.next()?,values.next()?);
    if values.next().is_some() || crate::source_patch_host::binding(document,capture,ticket).is_err(){return None;}
    Some((document,capture,ticket))
}
impl ReceiptKind for WhiteBalanceKind {
    const NAME: &'static str = "white_balance";
    const ACTIONS: &'static [&'static str] = &["set_algorithm", "reset", "pick", "clear_pick"];
    fn valid_request(action: &str, document: Option<&str>) -> bool {
        if action=="pick" {pick_parts(document).is_some()} else {document.is_some_and(|d| !d.is_empty() && d.len()<=64)}
    }
    fn valid(v: &Value, bound: Option<&str>) -> bool {
        let document=if v["action"]=="pick" {
            let Some((doc,capture,ticket))=pick_parts(bound) else{return false};
            if v["capture_id"].as_str()!=Some(capture) || v["ticket"].as_str()!=Some(ticket){return false;}
            Some(doc)
        } else {bound};
        let (Some(success),Some(unknown))=(v["success"].as_bool(),v["outcome_unknown"].as_bool()) else{return false};
        if v["protocol"]!=1 || v["document_id"].as_str()!=document || !v["requires_reload"].is_boolean() || (success&&unknown){return false;}
        if !success{return true;}
        if v["requires_reload"]!=false || !exposure(&v["before"]) || !exposure(&v["after"])
            || !["undo_steps","redo_steps"].iter().all(|k|v["history"][*k].as_u64().is_some()){return false;}
        let (before,after)=(&v["before"],&v["after"]);
        if !["ev","contrast","highlights","shadows","saturation","reference_k"].iter().all(|k|before[*k]==after[*k]){return false;}
        match v["action"].as_str(){
            Some("set_algorithm")=>before["temperature_shift"]==after["temperature_shift"] && before["tint_shift"]==after["tint_shift"]
                && before["options"]["picked_gains"]==after["options"]["picked_gains"],
            Some("pick") | Some("clear_pick")=>before["temperature_shift"]==after["temperature_shift"]
                && before["tint_shift"]==after["tint_shift"] && before["options"]["algorithm"]==after["options"]["algorithm"]
                && (v["action"]!="clear_pick" || after["options"]["picked_gains"].as_array().is_some_and(|a|a.iter().all(|n|n.as_f64()==Some(1.0)))),
            Some("reset")=>after["temperature_shift"].as_f64()==Some(0.0) && after["tint_shift"].as_f64()==Some(0.0)
                && before["options"]["algorithm"]==after["options"]["algorithm"]
                && after["options"]["picked_gains"].as_array().is_some_and(|a|a.iter().all(|n|n.as_f64()==Some(1.0))),
            _=>false,
        }
    }
    fn decorate_failure(value: &mut Value, document: Option<&str>){
        value["protocol"]=json!(1);value["requires_reload"]=json!(true);
        if let Some((doc,capture,ticket))=pick_parts(document){
            value["document_id"]=json!(doc);value["capture_id"]=json!(capture);value["ticket"]=json!(ticket);
        } else if let Some(doc)=document{value["document_id"]=json!(doc);}
    }
}
pub(crate) type WhiteBalanceHost = ReceiptHost<WhiteBalanceKind>;
#[cfg(test)]
mod tests {
    use super::*;
    fn state()->Value{json!({"ev":1.0,"temperature_shift":0.0,"tint_shift":0.0,"contrast":2.0,"highlights":0.0,"shadows":0.0,"saturation":0.0,"reference_k":null,
        "options":{"version":1,"algorithm":ALGORITHMS[0],"picked_gains":[1.0,1.0,1.0]}})}
    fn result()->Value{json!({"protocol":1,"request_id":"r","document_id":"d","action":"reset","success":true,"outcome_unknown":false,"requires_reload":false,
        "before":state(),"after":state(),"history":{"undo_steps":1,"redo_steps":0}})}
    #[test] fn valid_completion_requires_preserved_non_wb_state(){let mut v=result();assert!(WhiteBalanceKind::valid(&v,Some("d")));v["after"]["ev"]=json!(0.0);assert!(!WhiteBalanceKind::valid(&v,Some("d")));}
    #[test] fn wrong_document_and_unconfirmed_completion_reject(){let mut v=result();assert!(!WhiteBalanceKind::valid(&v,Some("other")));v["outcome_unknown"]=json!(true);assert!(!WhiteBalanceKind::valid(&v,Some("d")));}
    #[test] fn mailbox_binds_document_and_restart_is_not_success(){let mut h=WhiteBalanceHost::default();h.reset([1;16]);h.ready([1;16],true);assert!(h.begin([1;16],"x","reset").is_err());h.begin_bound([1;16],"r","reset",Some("d")).unwrap();h.ended([1;16]);assert_eq!(h.status("r")["result"]["success"],false);}
}
