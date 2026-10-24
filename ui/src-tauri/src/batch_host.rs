//! Reviewed batch receipts use the shared epoch-bound mailbox.
use serde_json::Value;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use crate::spill_transfer_protocol::{self as spill, hex, revision, source_proof as spill_source, SPILL_OP};
use crate::original_shadow_transfer_protocol::{self as shadow, SHADOW_OP};
use crate::torso_transfer_protocol as torso;
#[cfg(test)] use crate::torso_transfer_protocol::TORSO_OP;
#[cfg(test)] use crate::waist_transfer_protocol::WAIST_OP;
use crate::preset_host::{BodyReviewFamily, BODY_REVIEW_FAMILIES};
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
fn body_preflight(value: &Value, family: BodyReviewFamily) -> bool {
    let (Some(ops), Some(applies), Some(targets)) = (value["module_scope"].as_array(),
        value["applies"].as_object(), value["targets"].as_array()) else { return false; };
    if targets.is_empty() || targets.len() > family.max_targets() { return false; }
    let mut selected = std::collections::BTreeSet::new();
    if ops.len() != 1 || ops[0] != family.op()
        || ops.iter().any(|op| op.as_str().map_or(true, |op| !selected.insert(op)))
        || applies.len() != ops.len()
        || !selected.iter().all(|op| applies.get(*op).is_some_and(Value::is_object)) { return false; }
    if !family.no_foreign_evidence(value) || value.get(family.ack_key()).is_some() { return false; }
    let params = &value["applies"][family.op()];
    if !family.parameters(params) { return false; }
    let source = &value["source_snapshot"];
    if !hex(&value["preflight_token"], 32) || !hex(&source["document_id"], 32)
        || !revision(&source["revision"]) || !source["path"].is_string()
        || !torso::source_proof(&source["source_proof"]) || !value["rejected_docs"].is_array()
        || !matches!(value["policy"].as_str(), Some("skip_and_report" | "recheck")) { return false; }
    let mut ids = std::collections::BTreeSet::new();
    let mut indices = std::collections::BTreeSet::new();
    let mut blocked = 0_u64;
    for target in targets {
        if !family.no_foreign_evidence(target) || target.get(family.ack_key()).is_some() { return false; }
        if !hex(&target["document_id"], 32) || !revision(&target["revision"])
            || !target["path"].is_string() || target["index"].as_u64().is_none()
            || !ids.insert(target["document_id"].as_str().unwrap())
            || (family != BodyReviewFamily::Torso && !indices.insert(target["index"].as_u64().unwrap())) { return false; }
        if !target["blocked"].is_null() {
            if !target["blocked"].as_str().is_some_and(|s| !s.is_empty())
                || !target[family.transfer_key()].is_null() { return false; }
            blocked += 1;
            continue;
        }
        let before = &target["before"][family.op()];
        if !torso::source_proof(&target["source_proof"])
            || target["before"].as_object().map_or(true, |m| m.len() != 1)
            || before.as_object().map_or(true, |m| m.len() != 1)
            || !hex(&before["target_recipe_key"], 64)
            || !family.transfer(&target[family.transfer_key()], &target["document_id"], &target["revision"], params, &target["source_proof"])
            || (target["document_id"] == source["document_id"] && (target["source_proof"] != source["source_proof"]
                || (family != BodyReviewFamily::Torso && target["revision"] != source["revision"]))) { return false; }
    }
    value["blocked"].as_u64() == Some(blocked)
        && value["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
/// The native mailbox cannot reconstruct the frozen target plan or geometry.
/// It can reject incomplete head-success envelopes before they settle recovery.
/// The engine and UI still compare source/path/reviewed-row identity to the plan.
fn head_commit(value: &Value) -> bool {
    let family = BodyReviewFamily::Head;
    let (Some(outcomes), Some(acks), Some(applied)) = (value["target_outcomes"].as_array(),
        value[family.ack_key()].as_array(), value["targets"].as_array()) else { return false; };
    let bounded_text = |v: &Value, limit: usize| v.as_str().is_some_and(|s|
        !s.trim().is_empty() && s.len() <= limit && !s.chars().any(|c| c.is_control()));
    let index = |v: &Value| v.as_u64().filter(|n| *n <= 9_007_199_254_740_991);
    let source = &value["source_snapshot"];
    if outcomes.is_empty() || outcomes.len() > family.max_targets() || acks.is_empty()
        || !bounded_text(&value["batch_id"], 128) || !hex(&source["document_id"], 32)
        || !revision(&source["revision"]) || !bounded_text(&source["path"], 4096)
        || !torso::source_proof(&source["source_proof"]) { return false; }
    let mut acknowledged = std::collections::BTreeMap::new();
    for ack in acks {
        let Some(id) = ack["document_id"].as_str() else { return false; };
        if acknowledged.insert(id, &ack["revision"]).is_some() { return false; }
    }
    let mut documents = std::collections::BTreeSet::new();
    let mut reviewed_indices = std::collections::BTreeSet::new();
    let mut applied_indices = std::collections::BTreeSet::new();
    let mut actual_applied = Vec::new();
    for outcome in outcomes {
        if !hex(&outcome["document_id"], 32) || !revision(&outcome["expected_revision"])
            || !bounded_text(&outcome["path"], 4096) || !family.no_foreign_evidence(outcome)
            || !outcome[family.transfer_key()].is_null() || outcome.get(family.ack_key()).is_some() { return false; }
        let id = outcome["document_id"].as_str().unwrap();
        let Some(reviewed_index) = index(&outcome["reviewed_index"]) else { return false; };
        if !documents.insert(id) || !reviewed_indices.insert(reviewed_index) { return false; }
        let ack_revision = acknowledged.remove(id);
        if ack_revision.is_some_and(|expected| expected != &outcome["expected_revision"]) { return false; }
        match outcome["outcome"].as_str() {
            Some("applied") => {
                let Some(current_index) = index(&outcome["index"]) else { return false; };
                if ack_revision.is_none() || !applied_indices.insert(current_index) || !outcome["blocked"].is_null()
                    || outcome["current_revision"] != outcome["expected_revision"] || !revision(&outcome["result_revision"])
                    || outcome["result_revision"].as_str().unwrap().parse::<u64>().unwrap()
                        <= outcome["expected_revision"].as_str().unwrap().parse::<u64>().unwrap() { return false; }
                // The row may move without changing document identity. Do not
                // require this current index to equal the frozen reviewed index.
                actual_applied.push(outcome["index"].clone());
            }
            Some("skipped") => {
                // Engine diagnostics are capped at 2000 Unicode characters,
                // not UTF-8 bytes; non-Latin skip reasons must remain valid.
                if !outcome["blocked"].as_str().is_some_and(|reason| !reason.trim().is_empty() && reason.chars().count() <= 2000)
                    || (!outcome["index"].is_null() && index(&outcome["index"]).is_none())
                    || (!outcome["current_revision"].is_null() && !revision(&outcome["current_revision"]))
                    || (!outcome["result_revision"].is_null() && !revision(&outcome["result_revision"])) { return false; }
            }
            _ => return false,
        }
    }
    acknowledged.is_empty() && !actual_applied.is_empty() && &actual_applied == applied
}
impl ReceiptKind for BatchKind {
    const NAME: &'static str = "batch";
    const ACTIONS: &'static [&'static str] = &["preflight", "commit", "undo", "redo", "people_targets", "collarbone_visual"];
    fn valid(value: &Value, _: Option<&str>) -> bool {
        if !crate::batch_api::collarbone::receipt(value) || !crate::batch_api::collarbone::preflight(value) || !crate::batch_api::collarbone::image_receipt(value) { return false; }
        for family in BODY_REVIEW_FAMILIES {
            // The batch proof is per target, never a source-level stand-in.
            if !family.receipt(value, "batch", "commit") { return false; }
            let evidence = value["targets"].as_array().is_some_and(|targets| targets.iter().any(|target|
                !target[family.transfer_key()].is_null() || target.get(family.ack_key()).is_some()));
            if evidence && (value["success"] != true || value["action"] != "preflight" || !family.selected(value)) { return false; }
            if value["success"] == true && value["action"] == "preflight" && family.selected(value)
                && !body_preflight(value, family) { return false; }
            if family == BodyReviewFamily::Head && family.selected(value)
                && value["success"] == true && value["action"] == "commit" && !head_commit(value) { return false; }
        }
        value["success"].as_bool().is_some()
            && (value["success"] != true || value["action"] != "preflight"
                || !value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SPILL_OP))
                || spill_preflight(value))
            && (value["success"] != true || value["action"] != "preflight"
                || !value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SHADOW_OP))
                || shadow_preflight(value))
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

    // AUTHORED / UNRUN. Common synthetic transport shape, not real waist/body
    // geometry or current-face acceptance evidence from an actual photograph.
    fn waist_review() -> Value {
        let mut value = torso_review(); value["request_id"] = json!("waist");
        value["module_scope"] = json!([WAIST_OP]); value["applies"] = json!({(WAIST_OP):{"version":1,"amount":0.0}});
        value["targets"][0]["before"] = json!({(WAIST_OP):{"target_recipe_key":"d".repeat(64)}});
        let proof = value["targets"][0].as_object_mut().unwrap().remove("torso_transfer").unwrap();
        value["targets"][0]["waist_transfer"] = proof;
        value
    }
    fn waist_commit() -> Value {
        let review = waist_review(); let target = &review["targets"][0]; let pair = &target["waist_transfer"];
        json!({"action":"commit","request_id":"waist-commit","success":true,"outcome_unknown":false,
            "module_scope":[WAIST_OP],"preflight_token":review["preflight_token"],
            "waist_review_ack":[{"document_id":target["document_id"],"revision":target["revision"],
                "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}]})
    }
    #[test] fn waist_each_target_owns_every_proof_and_zero_amount_still_needs_pixels() {
        let value = waist_review(); assert!(BatchKind::valid(&value, None));
        for key in value["targets"][0]["waist_transfer"].as_object().unwrap().keys() {
            let mut bad = value.clone(); bad["targets"][0]["waist_transfer"].as_object_mut().unwrap().remove(key);
            assert!(!BatchKind::valid(&bad, None), "{key}");
        }
        for path in ["/source_snapshot/source_proof", "/targets/0/source_proof", "/targets/0/before",
            "/targets/0/waist_transfer/body_ref", "/targets/0/waist_transfer/associated_face",
            "/targets/0/waist_transfer/before/base64", "/targets/0/waist_transfer/after/base64"] {
            let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null;
            assert!(!BatchKind::valid(&bad, None), "{path}");
        }
        for (key, replacement) in [("document_id", json!("e".repeat(32))), ("revision", json!("3")),
            ("source_proof", value["source_snapshot"]["source_proof"].clone()), ("parameters", json!({"version":1,"amount":0.2})),
            ("body_ref", json!([value["targets"][0]["waist_transfer"]["body_ref"].clone()])), ("body_refs", json!([]))] {
            let mut bad = value.clone(); bad["targets"][0]["waist_transfer"][key] = replacement;
            assert!(!BatchKind::valid(&bad, None), "{key}");
        }
        let mut bad = value.clone(); bad["targets"][0]["before"][TORSO_OP] = json!({"target_recipe_key":"e".repeat(64)});
        assert!(!BatchKind::valid(&bad, None));
        bad = value.clone(); bad["source_snapshot"]["document_id"] = value["targets"][0]["document_id"].clone();
        bad["source_snapshot"]["source_proof"] = value["targets"][0]["source_proof"].clone();
        assert!(!BatchKind::valid(&bad, None)); // The same document cannot have two current revisions.
        bad["source_snapshot"]["revision"] = value["targets"][0]["revision"].clone(); assert!(BatchKind::valid(&bad, None));
        bad = value.clone(); bad["targets"][0]["waist_transfer"]["associated_face"]["associated_face_ref"]["asset_sha256"] = json!("e".repeat(64));
        assert!(!BatchKind::valid(&bad, None));
        bad = value; bad["targets"][0]["waist_transfer"]["after"]["sha256"] = json!("e".repeat(64));
        let mut host = BatchHost::default(); host.reset([1;16]); host.ready([1;16], true);
        host.begin_command([1;16], &json!({"cmd":"batch","action":"preflight","request_id":"waist","module_scope":[WAIST_OP]})).unwrap();
        host.receive([1;16], &bad); assert_eq!(host.status("waist")["result"]["outcome_unknown"], true);
    }
    #[test] fn waist_batch_rejects_mixed_source_level_or_wrong_family_evidence() {
        let value = waist_review();
        for op in [TORSO_OP, WAIST_OP, SPILL_OP, SHADOW_OP, "lnx.exposure.v1"] {
            let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op));
            bad["applies"][op] = json!({}); assert!(!BatchKind::valid(&bad, None), "{op}");
        }
        let mut legacy = value.clone(); legacy["targets"][0]["torso_transfer"] = Value::Null;
        assert!(BatchKind::valid(&legacy, None));
        for key in ["torso_transfer", "spill_transfer", "shadow_transfer", "people_transfer", "persistent_association", "xmp_transfer"] {
            let mut bad = value.clone(); bad[key] = json!({}); assert!(!BatchKind::valid(&bad, None), "top {key}");
            bad = value.clone(); bad["targets"][0][key] = json!({}); assert!(!BatchKind::valid(&bad, None), "target {key}");
        }
        for key in ["torso_review_ack", "waist_review_ack", "spill_review_ack", "shadow_review_ack"] {
            let mut bad = value.clone(); bad[key] = Value::Null; assert!(!BatchKind::valid(&bad, None), "top {key}");
            bad = value.clone(); bad["targets"][0][key] = Value::Null; assert!(!BatchKind::valid(&bad, None), "target {key}");
        }
        let mut bad = value.clone(); bad["waist_transfer"] = value["targets"][0]["waist_transfer"].clone();
        assert!(!BatchKind::valid(&bad, None));
        bad = value; bad["module_scope"] = json!([TORSO_OP]); assert!(!BatchKind::valid(&bad, None));
    }
    #[test] fn waist_target_count_identity_and_index_include_blocked_rows() {
        let value = waist_review();
        let mut two = value.clone(); let mut other = value["targets"][0].clone();
        other["document_id"] = json!("e".repeat(32)); other["index"] = json!(2);
        other["waist_transfer"]["document_id"] = other["document_id"].clone();
        two["targets"].as_array_mut().unwrap().push(other); two["ok"] = json!(2);
        assert!(BatchKind::valid(&two, None));
        let mut bad = two.clone(); bad["targets"][1] = bad["targets"][0].clone(); assert!(!BatchKind::valid(&bad, None));
        bad = two.clone(); bad["targets"][1]["index"] = json!(1); assert!(!BatchKind::valid(&bad, None));
        two["targets"][1]["blocked"] = json!("Actual waist body/face review is unavailable");
        two["ok"] = json!(1); two["blocked"] = json!(1); assert!(!BatchKind::valid(&two, None));
        two["targets"][1]["waist_transfer"] = Value::Null; assert!(BatchKind::valid(&two, None));
        bad = two.clone(); bad["targets"][1]["index"] = json!(1); assert!(!BatchKind::valid(&bad, None));
        bad = value.clone(); bad["targets"] = json!([]); bad["ok"] = json!(0); assert!(!BatchKind::valid(&bad, None));
        let mut many = value.clone();
        many["targets"] = json!((0..9).map(|index| {
            let mut target = value["targets"][0].clone(); target["document_id"] = json!(format!("{index:032x}"));
            target["index"] = json!(index); target["waist_transfer"]["document_id"] = target["document_id"].clone(); target
        }).collect::<Vec<_>>());
        many["ok"] = json!(9); assert!(!BatchKind::valid(&many, None));
        many["targets"][8]["blocked"] = json!("Target review unavailable"); many["targets"][8]["waist_transfer"] = Value::Null;
        many["ok"] = json!(8); many["blocked"] = json!(1); assert!(!BatchKind::valid(&many, None));
        many["targets"].as_array_mut().unwrap().pop(); many["blocked"] = json!(0); assert!(BatchKind::valid(&many, None));
    }
    #[test] fn waist_terminal_claim_and_unknown_need_the_original_family_ack_shape() {
        let original = waist_commit();
        for (success, unknown) in [(true,false), (false,true), (false,false)] {
            let mut value = original.clone(); value["success"] = json!(success); value["outcome_unknown"] = json!(unknown);
            assert!(BatchKind::valid(&value, None));
            for key in ["waist_review_ack", "module_scope", "preflight_token"] {
                let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!BatchKind::valid(&bad, None), "{key}");
            }
            let mut bad = value.clone(); bad["torso_review_ack"] = value["waist_review_ack"].clone(); assert!(!BatchKind::valid(&bad, None));
            bad = value; bad["waist_review_ack"][0]["revision"] = json!("02"); assert!(!BatchKind::valid(&bad, None));
        }
        let mut host = BatchHost::default(); host.reset([1;16]); host.ready([1;16], true);
        let command = json!({"cmd":"batch","action":"commit","request_id":original["request_id"],
            "preflight_token":original["preflight_token"],"waist_review_ack":original["waist_review_ack"]});
        host.begin_command([1;16], &command).unwrap();
        let mut substituted = original.clone(); substituted["waist_review_ack"][0]["after_sha256"] = json!("e".repeat(64));
        assert!(BatchKind::valid(&substituted, None)); // Shape alone is insufficient.
        host.receive([1;16], &substituted);
        let result = host.status("waist-commit")["result"].clone();
        assert_eq!(result["outcome_unknown"], true); assert_eq!(result["waist_review_ack"], original["waist_review_ack"]);
    }

}

// AUTHORED / UNRUN: independent head-family protocol specifications.
#[cfg(test)]
#[path = "head_batch_host_tests.rs"]
mod head_tests;
