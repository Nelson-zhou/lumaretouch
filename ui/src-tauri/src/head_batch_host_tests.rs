//! AUTHORED / UNRUN. Synthetic batch protocol, not actual target-head acceptance.
use super::*;
use serde_json::json;
use crate::torso_transfer_protocol::HEAD_OP;
fn review() -> Value {
    let source = json!({"asset_sha256":"2".repeat(64),"original_sha256":"2".repeat(64),"creative_source":null});
    let params = json!({"version":1,"amount":0.0});
    let pair = torso::tests::sample_transfer(&json!("c".repeat(32)), &json!("2"), &params, &source);
    json!({"request_id":"head-review","action":"preflight","success":true,"outcome_unknown":false,
        "preflight_token":"a".repeat(32),"module_scope":[HEAD_OP],"applies":{(HEAD_OP):params},"policy":"skip_and_report",
        "source_snapshot":{"document_id":"b".repeat(32),"revision":"4","path":"/source.raw",
            "source_proof":{"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}},
        "targets":[{"index":1,"path":"/target.raw","document_id":"c".repeat(32),"revision":"2","blocked":null,
            "before":{(HEAD_OP):{"target_recipe_key":"d".repeat(64)}},"source_proof":source,"head_transfer":pair}],
        "ok":1,"blocked":0,"rejected_docs":[]})
}
fn commit() -> Value {
    let review = review(); let target = &review["targets"][0]; let pair = &target["head_transfer"];
    json!({"action":"commit","request_id":"head-commit","success":true,"outcome_unknown":false,
        "module_scope":[HEAD_OP],"preflight_token":review["preflight_token"],"batch_id":"batch-001-1234",
        "source_snapshot":review["source_snapshot"],"targets":[7],
        "target_outcomes":[{"document_id":target["document_id"],"path":target["path"],"reviewed_index":target["index"],
            "index":7,"expected_revision":target["revision"],"current_revision":target["revision"],"result_revision":"3","blocked":null,"outcome":"applied"}],
        "head_review_ack":[{"document_id":target["document_id"],"revision":target["revision"],
            "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}]})
}
#[test]
fn every_head_target_owns_current_proof_even_for_zero_amount() {
    let value = review(); assert!(BatchKind::valid(&value, None));
    for key in value["targets"][0]["head_transfer"].as_object().unwrap().keys() {
        let mut bad = value.clone(); bad["targets"][0]["head_transfer"].as_object_mut().unwrap().remove(key);
        assert!(!BatchKind::valid(&bad, None), "{key}");
    }
    for path in ["/source_snapshot/source_proof", "/targets/0/source_proof", "/targets/0/before",
        "/targets/0/head_transfer/body_ref", "/targets/0/head_transfer/associated_face",
        "/targets/0/head_transfer/before/base64", "/targets/0/head_transfer/after/base64"] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null; assert!(!BatchKind::valid(&bad, None), "{path}");
    }
    for (key, replacement) in [("source_proof", value["source_snapshot"]["source_proof"].clone()),
        ("revision", json!("3")), ("parameters", json!({"version":1,"amount":0.1})),
        ("body_refs", json!([])), ("body_support_sha256", json!("bad"))] {
        let mut bad = value.clone(); bad["targets"][0]["head_transfer"][key] = replacement; assert!(!BatchKind::valid(&bad, None), "{key}");
    }
    let mut bad = value.clone(); bad["applies"][HEAD_OP]["amount"] = json!(-0.1);
    bad["targets"][0]["head_transfer"]["parameters"] = bad["applies"][HEAD_OP].clone(); assert!(!BatchKind::valid(&bad, None));
    bad = value.clone(); bad["source_snapshot"]["document_id"] = value["targets"][0]["document_id"].clone();
    bad["source_snapshot"]["source_proof"] = value["targets"][0]["source_proof"].clone(); assert!(!BatchKind::valid(&bad, None));
    bad["source_snapshot"]["revision"] = value["targets"][0]["revision"].clone(); assert!(BatchKind::valid(&bad, None));
}
#[test]
fn source_level_foreign_family_or_mixed_scope_head_proofs_cannot_be_relocated() {
    let value = review();
    for op in [TORSO_OP, WAIST_OP, HEAD_OP, SPILL_OP, SHADOW_OP, "lnx.exposure.v1"] {
        let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op)); bad["applies"][op] = json!({});
        assert!(!BatchKind::valid(&bad, None), "{op}");
    }
    for key in ["torso_transfer", "waist_transfer", "spill_transfer", "shadow_transfer", "people_transfer", "persistent_association", "xmp_transfer"] {
        let mut bad = value.clone(); bad[key] = json!({}); assert!(!BatchKind::valid(&bad, None), "top {key}");
        bad = value.clone(); bad["targets"][0][key] = json!({}); assert!(!BatchKind::valid(&bad, None), "target {key}");
    }
    for key in ["torso_review_ack", "waist_review_ack", "head_review_ack", "spill_review_ack", "shadow_review_ack"] {
        let mut bad = value.clone(); bad[key] = Value::Null; assert!(!BatchKind::valid(&bad, None), "top {key}");
        bad = value.clone(); bad["targets"][0][key] = Value::Null; assert!(!BatchKind::valid(&bad, None), "target {key}");
    }
    let mut bad = value.clone(); bad["head_transfer"] = value["targets"][0]["head_transfer"].clone(); assert!(!BatchKind::valid(&bad, None));
    for op in [TORSO_OP, WAIST_OP] {
        let mut bad = value.clone(); bad["module_scope"] = json!([op]); bad["applies"] = json!({(op):{"version":1,"amount":0}});
        assert!(!BatchKind::valid(&bad, None));
    }
}
#[test]
fn head_target_budget_and_unique_ids_indices_include_blocked_rows_without_requiring_contiguous_rows() {
    let value = review(); let mut two = value.clone(); let mut other = value["targets"][0].clone();
    other["document_id"] = json!("e".repeat(32)); other["index"] = json!(7);
    other["head_transfer"]["document_id"] = other["document_id"].clone();
    two["targets"].as_array_mut().unwrap().push(other); two["ok"] = json!(2); assert!(BatchKind::valid(&two, None));
    let mut bad = two.clone(); bad["targets"][1] = bad["targets"][0].clone(); assert!(!BatchKind::valid(&bad, None));
    bad = two.clone(); bad["targets"][1]["index"] = json!(1); assert!(!BatchKind::valid(&bad, None));
    two["targets"][1]["blocked"] = json!("Current complete-head and face review unavailable");
    two["ok"] = json!(1); two["blocked"] = json!(1); assert!(!BatchKind::valid(&two, None));
    two["targets"][1]["head_transfer"] = Value::Null; assert!(BatchKind::valid(&two, None));
    bad = two.clone(); bad["targets"][1]["index"] = json!(1); assert!(!BatchKind::valid(&bad, None));
    bad = value.clone(); bad["targets"] = json!([]); bad["ok"] = json!(0); assert!(!BatchKind::valid(&bad, None));
    let mut many = value.clone(); many["targets"] = json!((0..9).map(|index| {
        let mut target = value["targets"][0].clone(); target["document_id"] = json!(format!("{index:032x}"));
        target["index"] = json!(index); target["head_transfer"]["document_id"] = target["document_id"].clone(); target
    }).collect::<Vec<_>>());
    many["ok"] = json!(9); assert!(!BatchKind::valid(&many, None));
    many["targets"][8]["blocked"] = json!("Target unavailable"); many["targets"][8]["head_transfer"] = Value::Null;
    many["ok"] = json!(8); many["blocked"] = json!(1); assert!(!BatchKind::valid(&many, None));
    many["targets"].as_array_mut().unwrap().pop(); many["blocked"] = json!(0); assert!(BatchKind::valid(&many, None));
}
#[test]
fn head_terminal_identity_and_explicit_unknown_state_are_mandatory() {
    let original = commit();
    for (success, unknown) in [(true,false), (false,true), (false,false)] {
        let mut value = original.clone(); value["success"] = json!(success); value["outcome_unknown"] = json!(unknown);
        assert!(BatchKind::valid(&value, None));
        for key in ["head_review_ack", "module_scope", "preflight_token", "outcome_unknown"] {
            let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!BatchKind::valid(&bad, None), "{key}");
        }
        let mut bad = value.clone(); bad["waist_review_ack"] = value["head_review_ack"].clone(); assert!(!BatchKind::valid(&bad, None));
        bad = value; bad["head_review_ack"][0]["revision"] = json!("02"); assert!(!BatchKind::valid(&bad, None));
    }
    let command = json!({"cmd":"batch","action":"commit","request_id":original["request_id"],
        "preflight_token":original["preflight_token"],"head_review_ack":original["head_review_ack"]});
    let mut host = BatchHost::default(); host.reset([1;16]); host.ready([1;16], true); host.begin_command([1;16], &command).unwrap();
    let mut substituted = original.clone(); substituted["head_review_ack"][0]["after_sha256"] = json!("e".repeat(64));
    assert!(BatchKind::valid(&substituted, None)); // Shape is not frozen-record equality.
    host.receive([1;16], &substituted); let result = host.status("head-commit")["result"].clone();
    assert_eq!(result["outcome_unknown"], true); assert_eq!(result["head_review_ack"], original["head_review_ack"]);
}

#[test]
fn incomplete_head_success_cannot_settle_recovery_and_relocation_keeps_distinct_indices() {
    let value = commit(); assert!(BatchKind::valid(&value, None));
    assert_ne!(value["target_outcomes"][0]["reviewed_index"], value["target_outcomes"][0]["index"]);
    for path in ["/batch_id", "/source_snapshot", "/source_snapshot/source_proof", "/target_outcomes", "/targets",
        "/target_outcomes/0/document_id", "/target_outcomes/0/reviewed_index", "/target_outcomes/0/current_revision",
        "/target_outcomes/0/result_revision", "/target_outcomes/0/path"] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null; assert!(!BatchKind::valid(&bad, None), "{path}");
    }
    for (key, replacement) in [("expected_revision", json!("1")), ("current_revision", json!("4")),
        ("result_revision", json!("2")), ("result_revision", json!("03")), ("outcome", json!("unknown")),
        ("document_id", json!("e".repeat(32))), ("index", json!(-1)), ("waist_transfer", json!({}))] {
        let mut bad = value.clone(); bad["target_outcomes"][0][key] = replacement; assert!(!BatchKind::valid(&bad, None), "{key}");
    }
    let mut bad = value.clone(); bad["target_outcomes"].as_array_mut().unwrap().push(value["target_outcomes"][0].clone());
    assert!(!BatchKind::valid(&bad, None));
    bad = value.clone(); bad["targets"] = json!([1]); assert!(!BatchKind::valid(&bad, None));
    bad = value.clone(); bad["head_review_ack"] = json!([]); assert!(!BatchKind::valid(&bad, None));
    let mut skipped = value.clone(); skipped["target_outcomes"].as_array_mut().unwrap().push(json!({
        "document_id":"e".repeat(32),"path":"/blocked.raw","reviewed_index":2,"index":null,
        "expected_revision":"4","current_revision":null,"result_revision":null,"blocked":"Target removed","outcome":"skipped"}));
    assert!(BatchKind::valid(&skipped, None));
    skipped["target_outcomes"][1]["reviewed_index"] = json!(1); assert!(!BatchKind::valid(&skipped, None));
}

#[test]
fn unacknowledged_applied_documents_or_duplicate_current_rows_are_rejected() {
    let value = commit(); let mut two = value.clone(); let mut other = value["target_outcomes"][0].clone();
    other["document_id"] = json!("e".repeat(32)); other["reviewed_index"] = json!(2); other["index"] = json!(8);
    two["target_outcomes"].as_array_mut().unwrap().push(other); two["targets"] = json!([7,8]);
    assert!(!BatchKind::valid(&two, None));
    let mut ack = value["head_review_ack"][0].clone(); ack["document_id"] = json!("e".repeat(32));
    two["head_review_ack"].as_array_mut().unwrap().push(ack); assert!(BatchKind::valid(&two, None));
    two["target_outcomes"][1]["index"] = json!(7); two["targets"] = json!([7,7]); assert!(!BatchKind::valid(&two, None));
}
#[test]
fn incomplete_success_pins_actual_head_batch_host_and_validated_success_settles() {
    let value = commit(); let command = json!({"cmd":"batch","action":"commit","request_id":value["request_id"],
        "preflight_token":value["preflight_token"],"head_review_ack":value["head_review_ack"]});
    let epoch = [196;16]; let mut host = BatchHost::default(); host.reset(epoch); host.ready(epoch, true);
    host.begin_command(epoch, &command).unwrap(); crate::project_recovery_fence::issued(epoch, &command).unwrap();
    let mut bad = value.clone(); bad.as_object_mut().unwrap().remove("target_outcomes"); host.receive(epoch, &bad);
    assert_eq!(host.status("head-commit")["result"]["outcome_unknown"], true);
    assert!(crate::project_recovery_fence::proof(epoch).is_err()); host.receive(epoch, &value);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
    let epoch = [197;16]; let mut host = BatchHost::default(); host.reset(epoch); host.ready(epoch, true);
    host.begin_command(epoch, &command).unwrap(); crate::project_recovery_fence::issued(epoch, &command).unwrap();
    host.receive(epoch, &value); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
