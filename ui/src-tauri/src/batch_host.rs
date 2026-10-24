//! Reviewed batch receipts use the shared epoch-bound mailbox.
use serde_json::Value;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use crate::spill_transfer_protocol::{self as spill, hex, revision, source_proof as spill_source, SPILL_OP};
use crate::original_shadow_transfer_protocol::{self as shadow, SHADOW_OP};
use crate::torso_transfer_protocol::{self as torso, TORSO_OP};
pub(crate) struct BatchKind;
fn spill_preflight(value: &Value) -> bool {
    let (Some(ops), Some(applies), Some(targets)) = (value["module_scope"].as_array(),
        value["applies"].as_object(), value["targets"].as_array()) else { return false; };
    if targets.len() > spill::MAX_TARGETS { return false; }
    let mut selected = std::collections::BTreeSet::new();
    if ops.iter().any(|op| op.as_str().map_or(true, |op| !selected.insert(op)))
        || selected.contains("lnx.id_background.v1") || applies.len() != ops.len()
        || !selected.iter().all(|op| applies.get(*op).is_some_and(Value::is_object)) { return false; }
    let params = &value["applies"][SPILL_OP];
    if !spill::parameters(params) { return false; }
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
            || !spill::transfer(&target["spill_transfer"], &target["document_id"], &target["revision"], params, &target["source_proof"])
            || (target["document_id"] == source["document_id"] && target["source_proof"] != source["source_proof"]) { return false; }
    }
    value["blocked"].as_u64() == Some(blocked)
        && value["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
fn shadow_preflight(value: &Value) -> bool {
    let (Some(ops), Some(applies), Some(targets)) = (value["module_scope"].as_array(),
        value["applies"].as_object(), value["targets"].as_array()) else { return false; };
    if targets.len() > shadow::MAX_TARGETS { return false; }
    let mut selected = std::collections::BTreeSet::new();
    if ops.iter().any(|op| op.as_str().map_or(true, |op| !selected.insert(op)))
        || selected.contains("lnx.id_background.v1") || selected.contains("lnx.spill_removal.v1") || applies.len() != ops.len()
        || !selected.iter().all(|op| applies.get(*op).is_some_and(Value::is_object)) { return false; }
    let params = &value["applies"][SHADOW_OP];
    if !shadow::parameters(params) { return false; }
    let source = &value["source_snapshot"];
    if !hex(&value["preflight_token"], 32) || !hex(&source["document_id"], 32)
        || !revision(&source["revision"]) || !source["path"].is_string()
        || !shadow::source_proof(&source["source_proof"]) || !value["rejected_docs"].is_array()
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
        let before = &target["before"][SHADOW_OP];
        if !shadow::source_proof(&target["source_proof"])
            || before.as_object().map_or(true, |m| m.len() != 1)
            || !hex(&before["target_recipe_key"], 64)
            || !shadow::transfer(&target["shadow_transfer"], &target["document_id"], &target["revision"], params, &target["source_proof"])
            || (target["document_id"] == source["document_id"] && target["source_proof"] != source["source_proof"]) { return false; }
    }
    value["blocked"].as_u64() == Some(blocked)
        && value["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
fn torso_preflight(value: &Value) -> bool {
    let (Some(ops), Some(applies), Some(targets)) = (value["module_scope"].as_array(),
        value["applies"].as_object(), value["targets"].as_array()) else { return false; };
    if targets.is_empty() || targets.len() > torso::MAX_TARGETS { return false; }
    let mut selected = std::collections::BTreeSet::new();
    if ops.len() != 1 || ops[0] != TORSO_OP
        || ops.iter().any(|op| op.as_str().map_or(true, |op| !selected.insert(op)))
        || applies.len() != ops.len()
        || !selected.iter().all(|op| applies.get(*op).is_some_and(Value::is_object)) { return false; }
    if !value["people_transfer"].is_null() || !value["persistent_association"].is_null()
        || value.get("torso_review_ack").is_some()
        || ["local_mask_transfer", "reference_color", "spill_transfer", "shadow_transfer", "crop_transfer"]
            .iter().any(|key| !value[*key].is_null()) { return false; }
    let params = &value["applies"][TORSO_OP];
    if !torso::parameters(params) { return false; }
    let source = &value["source_snapshot"];
    if !hex(&value["preflight_token"], 32) || !hex(&source["document_id"], 32)
        || !revision(&source["revision"]) || !source["path"].is_string()
        || !torso::source_proof(&source["source_proof"]) || !value["rejected_docs"].is_array()
        || !matches!(value["policy"].as_str(), Some("skip_and_report" | "recheck")) { return false; }
    let mut ids = std::collections::BTreeSet::new();
    let mut blocked = 0_u64;
    for target in targets {
        if ["spill_transfer", "shadow_transfer", "crop_transfer", "people_transfer", "local_mask_transfer", "optical_transfer", "reference_color"]
            .iter().any(|key| !target[*key].is_null()) { return false; }
        if !hex(&target["document_id"], 32) || !revision(&target["revision"])
            || !target["path"].is_string() || target["index"].as_u64().is_none()
            || !ids.insert(target["document_id"].as_str().unwrap()) { return false; }
        if !target["blocked"].is_null() {
            if !target["blocked"].as_str().is_some_and(|s| !s.is_empty())
                || !target["torso_transfer"].is_null() { return false; }
            blocked += 1;
            continue;
        }
        let before = &target["before"][TORSO_OP];
        if !torso::source_proof(&target["source_proof"])
            || target["before"].as_object().map_or(true, |m| m.len() != 1)
            || before.as_object().map_or(true, |m| m.len() != 1)
            || !hex(&before["target_recipe_key"], 64)
            || !torso::transfer(&target["torso_transfer"], &target["document_id"], &target["revision"], params, &target["source_proof"])
            || (target["document_id"] == source["document_id"] && target["source_proof"] != source["source_proof"]) { return false; }
    }
    value["blocked"].as_u64() == Some(blocked)
        && value["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
impl ReceiptKind for BatchKind {
    const NAME: &'static str = "batch";
    const ACTIONS: &'static [&'static str] = &["preflight", "commit", "undo", "redo", "people_targets"];
    fn valid(value: &Value, _: Option<&str>) -> bool {
        let has_torso = value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == TORSO_OP));
        let torso_evidence = value["targets"].as_array().is_some_and(|targets| targets.iter().any(|target| !target["torso_transfer"].is_null()));
        // The batch proof is per target, never a source-level stand-in.
        if !value["torso_transfer"].is_null() { return false; }
        if torso_evidence && (value["success"] != true || value["action"] != "preflight" || !has_torso) { return false; }
        if has_torso && value["module_scope"].as_array().map_or(true, |ops| ops.len() != 1) { return false; }
        if has_torso && ["spill_review_ack", "shadow_review_ack", "xmp_review_ack", "xmp_ack"]
            .iter().any(|key| value.get(*key).is_some()) { return false; }
        if has_torso && (value["outcome_unknown"] == true && value["success"] == true
            || value.get("outcome_unknown").is_some_and(|unknown| !unknown.is_boolean())) { return false; }
        if let Some(ack) = value.get("torso_review_ack") {
            if !has_torso || value["action"] != "commit"
                || ["spill_review_ack", "shadow_review_ack", "xmp_review_ack", "xmp_ack"]
                    .iter().any(|key| value.get(*key).is_some()) { return false; }
            let command = serde_json::json!({"cmd":"batch", "action":"commit", "request_id":value["request_id"],
                "preflight_token":value["preflight_token"], "torso_review_ack":ack});
            if torso::command(&command).is_err() { return false; }
        } else if has_torso && value["success"] == true && value["action"] == "commit" { return false; }
        value["success"].as_bool().is_some()
            && (value["success"] != true || value["action"] != "preflight"
                || !value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SPILL_OP))
                || spill_preflight(value))
            && (value["success"] != true || value["action"] != "preflight"
                || !value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SHADOW_OP))
                || shadow_preflight(value))
            && (value["success"] != true || value["action"] != "preflight" || !has_torso
                || torso_preflight(value))
    }
}
pub(crate) type BatchHost = ReceiptHost<BatchKind>;
#[cfg(test)] use crate::receipt_host::MAX_RECORDS;
#[cfg(test)] use serde_json::json;
#[cfg(test)]
mod tests {
    use super::*;
    // AUTHORED / UNRUN: small valid PNG fixtures, not actual target renders.
    fn spill_review() -> Value {
        let mut value = json!({"request_id":"spill","action":"preflight","success":true,
            "preflight_token":"a".repeat(32),"module_scope":[SPILL_OP],
            "applies":{(SPILL_OP):{"enabled":true,"strength":61}},"policy":"skip_and_report",
            "source_snapshot":{"document_id":"b".repeat(32),"revision":"4","path":"/source.raw",
                "source_proof":{"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}},
            "targets":[{"index":1,"path":"/target.raw","document_id":"c".repeat(32),"revision":"2","blocked":null,
                "before":{(SPILL_OP):{"target_recipe_key":"d".repeat(64)}},
                "source_proof":{"asset_sha256":"2".repeat(64),"original_sha256":"2".repeat(64),"creative_source":null}}],
            "ok":1,"blocked":0,"rejected_docs":[]});
        let target = &value["targets"][0];
        let transfer = spill::tests::sample_transfer(&target["document_id"], &target["revision"], &value["applies"][SPILL_OP], &target["source_proof"]);
        value["targets"][0]["spill_transfer"] = transfer;
        value
    }
    #[test] fn spill_review_requires_each_admitted_targets_owned_evidence() {
        let value = spill_review();
        assert!(BatchKind::valid(&value, None));
        for path in ["/source_snapshot/source_proof", "/targets/0/source_proof", "/targets/0/before", "/targets/0/spill_transfer"] {
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
        value["targets"][0]["spill_transfer"]["source_proof"] = value["targets"][0]["source_proof"].clone();
        value["targets"][0]["spill_transfer"]["source_size"] = json!([32,24]);
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
    #[test] fn spill_review_binds_each_target_and_bounds_total_selected_targets() {
        let value = spill_review();
        for (key, replacement) in [("document_id", json!("e".repeat(32))), ("revision", json!("3")),
            ("parameters", json!({"enabled":true,"strength":60})), ("source_proof", Value::Null)] {
            let mut changed = value.clone(); changed["targets"][0]["spill_transfer"][key] = replacement;
            assert!(!BatchKind::valid(&changed, None), "{key}");
        }
        let mut changed = value.clone();
        changed["targets"][0]["spill_transfer"]["before"]["sha256"] = json!("e".repeat(64));
        assert!(!BatchKind::valid(&changed, None));
        changed = value.clone(); changed["targets"][0]["revision"] = json!("02");
        changed["targets"][0]["spill_transfer"]["revision"] = json!("02");
        assert!(!BatchKind::valid(&changed, None));
        let mut many = value.clone();
        many["targets"] = json!((0..9).map(|index| {
            let mut target = value["targets"][0].clone();
            target["document_id"] = json!(format!("{index:032x}")); target["index"] = json!(index);
            target["spill_transfer"]["document_id"] = target["document_id"].clone(); target
        }).collect::<Vec<_>>());
        many["ok"] = json!(9); assert!(!BatchKind::valid(&many, None));
        many["targets"][8]["blocked"] = json!("independently reviewed target is unavailable");
        many["targets"][8].as_object_mut().unwrap().remove("spill_transfer");
        many["ok"] = json!(8); many["blocked"] = json!(1); assert!(!BatchKind::valid(&many, None));
        many["targets"].as_array_mut().unwrap().remove(0);
        many["ok"] = json!(7); assert!(BatchKind::valid(&many, None));
    }
    #[test] fn malformed_spill_pair_becomes_unknown_not_a_reviewable_success() {
        let mut host=BatchHost::default();host.reset([1;16]);host.ready([1;16],true);
        host.begin([1;16],"spill","preflight").unwrap();
        let mut value=spill_review();value["targets"][0]["spill_transfer"]["after"]["sha256"]=json!("e".repeat(64));
        host.receive([1;16],&value);
        assert_eq!(host.status("spill")["result"]["success"],false);
        assert_eq!(host.status("spill")["result"]["outcome_unknown"],true);
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

    #[test] fn shadow_each_target_requires_owned_pixels_even_when_disabled() {
        let mut value=spill_review();
        let params=json!({"enabled":false,"strength":0,"blend":"normal"});
        value["module_scope"]=json!([SHADOW_OP]);value["applies"]=json!({(SHADOW_OP):params});
        value["targets"][0]["before"]=json!({(SHADOW_OP):{"target_recipe_key":"d".repeat(64)}});
        let target=&value["targets"][0];
        let pair=shadow::tests::sample_transfer(&target["document_id"],&target["revision"],&params,&target["source_proof"]);
        value["targets"][0].as_object_mut().unwrap().remove("spill_transfer");value["targets"][0]["shadow_transfer"]=pair;
        assert!(BatchKind::valid(&value,None));
        for key in ["shadow_transfer","source_proof","before"] {
            let mut bad=value.clone();bad["targets"][0].as_object_mut().unwrap().remove(key);assert!(!BatchKind::valid(&bad,None));
        }
        let mut bad=value.clone();bad["targets"][0]["shadow_transfer"]["source_proof"]=bad["source_snapshot"]["source_proof"].clone();
        assert!(!BatchKind::valid(&bad,None));
        for op in [SPILL_OP,"lnx.id_background.v1"] {
            let mut bad=value.clone();bad["module_scope"].as_array_mut().unwrap().push(json!(op));bad["applies"][op]=json!({});
            assert!(!BatchKind::valid(&bad,None));
        }
        let mut host=BatchHost::default();host.reset([1;16]);host.ready([1;16],true);host.begin([1;16],"spill","preflight").unwrap();
        value["targets"][0]["shadow_transfer"]["after"]["sha256"]=json!("e".repeat(64));host.receive([1;16],&value);
        assert_eq!(host.status("spill")["result"]["success"],false);
    }

    // AUTHORED / UNRUN. Protocol fixtures do not prove native or rendered acceptance.
    fn torso_review() -> Value {
        let mut value = spill_review();
        let params = json!({"version":1,"amount":0.0});
        value["request_id"] = json!("torso");
        value["module_scope"] = json!([TORSO_OP]); value["applies"] = json!({(TORSO_OP):params});
        value["targets"][0]["before"] = json!({(TORSO_OP):{"target_recipe_key":"d".repeat(64)}});
        let target = &value["targets"][0];
        let pair = torso::tests::sample_transfer(&target["document_id"], &target["revision"], &params, &target["source_proof"]);
        value["targets"][0].as_object_mut().unwrap().remove("spill_transfer");
        value["targets"][0]["torso_transfer"] = pair;
        value
    }
    #[test] fn torso_review_requires_exact_target_body_and_pixels_even_at_zero() {
        let value = torso_review(); assert!(BatchKind::valid(&value, None));
        for path in ["/source_snapshot/source_proof", "/targets/0/source_proof", "/targets/0/before",
            "/targets/0/torso_transfer", "/targets/0/torso_transfer/body_ref",
            "/targets/0/torso_transfer/associated_face", "/targets/0/torso_transfer/body_support_sha256"] {
            let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null;
            assert!(!BatchKind::valid(&bad, None), "{path}");
        }
        for op in [SPILL_OP, SHADOW_OP, "lnx.crop.v1", "lnx.exposure.v1"] {
            let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op));
            bad["applies"][op] = json!({}); assert!(!BatchKind::valid(&bad, None));
        }
        let mut bad = value.clone(); bad["targets"][0]["torso_transfer"]["source_proof"] = value["source_snapshot"]["source_proof"].clone();
        assert!(!BatchKind::valid(&bad, None));
        bad = value.clone(); bad["targets"][0]["torso_transfer"]["parameters"]["amount"] = json!(0.25);
        assert!(!BatchKind::valid(&bad, None));
        bad = value.clone(); bad["targets"][0]["blocked"] = json!("Target body review changed");
        bad["ok"] = json!(0); bad["blocked"] = json!(1);
        assert!(!BatchKind::valid(&bad, None));
        bad["targets"][0]["torso_transfer"] = Value::Null; assert!(BatchKind::valid(&bad, None));
        bad = value.clone(); bad["module_scope"] = json!(["lnx.exposure.v1"]); assert!(!BatchKind::valid(&bad, None));
        let mut host = BatchHost::default(); host.reset([1;16]); host.ready([1;16],true);
        host.begin([1;16],"torso","preflight").unwrap();
        bad = value; bad["targets"][0]["torso_transfer"]["after"]["sha256"] = json!("e".repeat(64));
        host.receive([1;16],&bad);
        assert_eq!(host.status("torso")["result"]["outcome_unknown"],true);
    }
    #[test] fn torso_terminal_receipts_require_the_original_bounded_ack_shape() {
        let review = torso_review(); let target = &review["targets"][0];
        let ack = json!([{"document_id":target["document_id"], "revision":target["revision"],
            "before_sha256":target["torso_transfer"]["before"]["sha256"], "after_sha256":target["torso_transfer"]["after"]["sha256"]}]);
        let value = json!({"action":"commit","request_id":"torso-commit","success":true,"outcome_unknown":false,
            "module_scope":[TORSO_OP],"preflight_token":review["preflight_token"],"torso_review_ack":ack});
        assert!(BatchKind::valid(&value, None));
        for key in ["torso_review_ack", "preflight_token", "module_scope"] {
            let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!BatchKind::valid(&bad, None));
        }
        let mut bad = value.clone(); bad["torso_review_ack"][0]["revision"] = json!("02"); assert!(!BatchKind::valid(&bad, None));
        bad = value.clone(); bad["shadow_review_ack"] = json!([]); assert!(!BatchKind::valid(&bad, None));
        let mut pending = value.clone(); pending["success"] = json!(false); pending["outcome_unknown"] = json!(true);
        assert!(BatchKind::valid(&pending, None));
        assert!(BatchKind::valid(&json!({"action":"commit","request_id":"rejected","success":false,
            "outcome_unknown":false,"error":"Review acknowledgment missing; no write"}), None));
    }
    #[test] fn torso_target_budget_and_unique_document_fences_include_blocked_rows() {
        let value = torso_review();
        let mut many = value.clone();
        many["targets"] = json!((0..9).map(|index| {
            let mut target = value["targets"][0].clone();
            target["document_id"] = json!(format!("{index:032x}")); target["index"] = json!(index);
            target["torso_transfer"]["document_id"] = target["document_id"].clone(); target
        }).collect::<Vec<_>>());
        many["ok"] = json!(9); assert!(!BatchKind::valid(&many, None));
        many["targets"][8]["blocked"] = json!("Target review unavailable"); many["targets"][8]["torso_transfer"] = Value::Null;
        many["ok"] = json!(8); many["blocked"] = json!(1); assert!(!BatchKind::valid(&many, None));
        many["targets"].as_array_mut().unwrap().pop(); many["blocked"] = json!(0);
        assert!(BatchKind::valid(&many, None));
        many["targets"][1] = many["targets"][0].clone(); assert!(!BatchKind::valid(&many, None));
    }

}
