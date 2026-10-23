//! Reviewed batch receipts use the shared epoch-bound mailbox.
use serde_json::Value;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
pub(crate) struct BatchKind;
const SPILL_OP: &str = "lnx.spill_removal.v1";
fn hex(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|s| s.len() == length
        && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn revision(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20
        && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok())
}
fn spill_source(value: &Value) -> bool {
    if value.as_object().map_or(true, |m| m.len() != 3 || !m.contains_key("creative_source"))
        || !hex(&value["asset_sha256"], 64) || !hex(&value["original_sha256"], 64) { return false; }
    let creative = &value["creative_source"];
    if creative.is_null() { return value["asset_sha256"] == value["original_sha256"]; }
    creative.as_object().is_some_and(|m| m.len() == 3)
        && creative["sha256"] == value["asset_sha256"]
        && ["width", "height"].iter().all(|k| creative[*k].as_u64().is_some_and(|n| n > 0 && n <= 9_007_199_254_740_991))
}
fn spill_preflight(value: &Value) -> bool {
    let (Some(ops), Some(applies), Some(targets)) = (value["module_scope"].as_array(),
        value["applies"].as_object(), value["targets"].as_array()) else { return false; };
    let mut selected = std::collections::BTreeSet::new();
    if ops.iter().any(|op| op.as_str().map_or(true, |op| !selected.insert(op)))
        || selected.contains("lnx.id_background.v1") || applies.len() != ops.len()
        || !selected.iter().all(|op| applies.get(*op).is_some_and(Value::is_object)) { return false; }
    let params = &value["applies"][SPILL_OP];
    if params.as_object().map_or(true, |m| m.len() != 2) || !params["enabled"].is_boolean()
        || !params["strength"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n)) { return false; }
    let source = &value["source_snapshot"];
    if !hex(&value["preflight_token"], 32) || !hex(&source["document_id"], 32)
        || !revision(&source["revision"]) || !source["path"].is_string()
        || !spill_source(&source["source_proof"]) || !value["rejected_docs"].is_array()
        || !matches!(value["policy"].as_str(), Some("skip_and_report" | "recheck")) { return false; }
    let mut ids = std::collections::BTreeSet::new();
    let mut blocked = 0_u64;
    for target in targets {
        if !hex(&target["document_id"], 32) || !revision(&target["revision"])
            || !target["path"].is_string() || target["index"].as_u64().is_none()
            || !ids.insert(target["document_id"].as_str().unwrap()) { return false; }
        if !target["blocked"].is_null() {
            if !target["blocked"].as_str().is_some_and(|s| !s.is_empty()) { return false; }
            blocked += 1;
            continue;
        }
        let before = &target["before"][SPILL_OP];
        if !spill_source(&target["source_proof"])
            || before.as_object().map_or(true, |m| m.len() != 1)
            || !hex(&before["target_recipe_key"], 64)
            || (target["document_id"] == source["document_id"] && target["source_proof"] != source["source_proof"]) { return false; }
    }
    value["blocked"].as_u64() == Some(blocked)
        && value["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
impl ReceiptKind for BatchKind {
    const NAME: &'static str = "batch";
    const ACTIONS: &'static [&'static str] = &["preflight", "commit", "undo", "redo", "people_targets"];
    fn valid(value: &Value, _: Option<&str>) -> bool {
        value["success"].as_bool().is_some()
            && (value["success"] != true || value["action"] != "preflight"
                || !value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SPILL_OP))
                || spill_preflight(value))
    }
}
pub(crate) type BatchHost = ReceiptHost<BatchKind>;
#[cfg(test)] use crate::receipt_host::MAX_RECORDS;
#[cfg(test)] use serde_json::json;
#[cfg(test)]
mod tests {
    use super::*;
    // AUTHORED / UNRUN: schema evidence only; no target image is rendered here.
    fn spill_review() -> Value {
        json!({"request_id":"spill","action":"preflight","success":true,
            "preflight_token":"a".repeat(32),"module_scope":[SPILL_OP],
            "applies":{(SPILL_OP):{"enabled":true,"strength":61}},"policy":"skip_and_report",
            "source_snapshot":{"document_id":"b".repeat(32),"revision":"4","path":"/source.raw",
                "source_proof":{"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}},
            "targets":[{"index":1,"path":"/target.raw","document_id":"c".repeat(32),"revision":"2","blocked":null,
                "before":{(SPILL_OP):{"target_recipe_key":"d".repeat(64)}},
                "source_proof":{"asset_sha256":"2".repeat(64),"original_sha256":"2".repeat(64),"creative_source":null}}],
            "ok":1,"blocked":0,"rejected_docs":[]})
    }
    #[test] fn spill_review_requires_each_admitted_targets_owned_evidence() {
        let value = spill_review();
        assert!(BatchKind::valid(&value, None));
        for path in ["/source_snapshot/source_proof", "/targets/0/source_proof", "/targets/0/before"] {
            let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = Value::Null;
            assert!(!BatchKind::valid(&changed, None), "{path}");
        }
        let mut changed = value.clone(); changed["targets"][0]["document_id"] = value["source_snapshot"]["document_id"].clone();
        assert!(!BatchKind::valid(&changed, None));
        changed = value.clone(); changed["source_snapshot"]["source_proof"]["original_sha256"] = json!("9".repeat(64));
        assert!(!BatchKind::valid(&changed, None));
        changed = value.clone(); changed["targets"][0]["before"][SPILL_OP]["target_recipe_key"] = json!("invalid");
        assert!(!BatchKind::valid(&changed, None));
    }
    #[test] fn spill_review_accepts_distinct_derived_target_and_explicitly_blocked_target() {
        let mut value = spill_review();
        value["targets"][0]["source_proof"] = json!({"asset_sha256":"3".repeat(64),"original_sha256":"2".repeat(64),
            "creative_source":{"sha256":"3".repeat(64),"width":32,"height":24}});
        assert!(BatchKind::valid(&value, None));
        value["targets"][0]["source_proof"]["creative_source"]["width"] = json!(0);
        assert!(!BatchKind::valid(&value, None));
        value["targets"][0]["blocked"] = json!("Target source missing");
        value["targets"][0]["source_proof"] = Value::Null; value["targets"][0]["before"] = Value::Null;
        value["ok"] = json!(0); value["blocked"] = json!(1);
        assert!(BatchKind::valid(&value, None));
    }
    #[test] fn spill_review_rejects_non_scalar_params_and_conflicting_scope() {
        let value = spill_review();
        for params in [json!({"enabled":true,"strength":61,"coverage":null}),
            json!({"enabled":1,"strength":61}), json!({"enabled":true,"strength":101})] {
            let mut changed = value.clone(); changed["applies"][SPILL_OP] = params;
            assert!(!BatchKind::valid(&changed, None));
        }
        let mut changed = value.clone(); changed["module_scope"] = json!([SPILL_OP,"lnx.id_background.v1"]);
        changed["applies"]["lnx.id_background.v1"] = json!({"recipe":{}});
        assert!(!BatchKind::valid(&changed, None));
        changed = value.clone(); changed["targets"][0]["blocked"] = json!(true);
        assert!(!BatchKind::valid(&changed, None));
        changed = value.clone(); changed["ok"] = json!(2);
        assert!(!BatchKind::valid(&changed, None));
        changed = value; changed["success"] = json!(false); changed["targets"] = Value::Null;
        assert!(BatchKind::valid(&changed, None));
    }
    #[test]fn receipt_requires_epoch_request_and_action_and_first_terminal_wins(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();
        for (epoch,id,action) in [([2;16],"a","commit"),([1;16],"other","commit"),([1;16],"a","preflight")] {
            h.receive(epoch,&json!({"request_id":id,"action":action,"success":true}));
            assert_eq!(h.status("a")["phase"],"pending");
        }
        h.receive([1;16],&json!({"request_id":"a","action":"commit","success":true}));h.failed("a","late failure");
        assert_eq!(h.status("a")["result"]["success"],true);
    }
    #[test]fn restart_and_exit_do_not_turn_accepted_commands_into_success(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();h.ended([1;16]);
        assert_eq!(h.status("a")["result"]["outcome_unknown"],true);
        h.reset([2;16]);assert_eq!(h.status("a")["phase"],"unavailable");
        assert!(h.begin([1;16],"b","commit").is_err());h.ended([1;16]);h.ready([2;16],true);assert!(h.begin([2;16],"b","commit").is_ok());
    }
    #[test]fn pending_requests_are_bounded_and_never_silently_evicted(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);
        for i in 0..MAX_RECORDS {h.begin([1;16],&i.to_string(),"preflight").unwrap();}
        assert!(h.begin([1;16],"overflow","preflight").is_err());
        h.failed("0","test");h.begin([1;16],"new","preflight").unwrap();
        assert_eq!(h.status("0")["phase"],"unavailable");assert_eq!(h.status("1")["phase"],"pending");
    }
    #[test]fn readiness_belongs_to_current_epoch_and_exit_preserves_drained_success(){
        let mut h=BatchHost::default();h.reset([2;16]);h.ready([1;16],true);
        assert!(h.begin([2;16],"a","commit").is_err());h.ready([2;16],true);h.begin([2;16],"a","commit").unwrap();
        h.receive([2;16],&json!({"request_id":"a","action":"commit","success":true}));h.ended([2;16]);
        assert_eq!(h.status("a")["result"]["success"],true);
    }

    #[test]fn malformed_completion_is_explicitly_unknown_not_success(){
        let mut h=BatchHost::default();h.reset([1;16]);h.ready([1;16],true);h.begin([1;16],"a","commit").unwrap();
        h.receive([1;16],&json!({"request_id":"a","action":"commit","success":"true"}));
        assert_eq!(h.status("a")["result"]["success"],false);
        assert_eq!(h.status("a")["result"]["outcome_unknown"],true);
    }

}
