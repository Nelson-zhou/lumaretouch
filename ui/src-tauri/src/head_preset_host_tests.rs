//! AUTHORED / UNRUN. Synthetic native receipts, not real head support/render acceptance.
use super::*;
fn review() -> Value {
    let source = json!({"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null});
    let params = json!({"version":1,"amount":0.0});
    let pair = torso::tests::sample_transfer(&json!("head-target"), &json!("3"), &params, &source);
    json!({"protocol":1,"action":"preflight","success":true,"outcome_unknown":false,"request_id":"head-review",
        "id":"head-preset","document_id":"head-target","revision":"3","module_scope":[torso::HEAD_OP],
        "applies":{(torso::HEAD_OP):params},"preflight_token":"f".repeat(32),"source_proof":source,"head_transfer":pair})
}
fn apply() -> Value {
    let review = review(); let pair = &review["head_transfer"];
    json!({"protocol":1,"action":"apply","request_id":"head-apply","success":true,"outcome_unknown":false,
        "id":"head-preset","document_id":"head-target","module_scope":[torso::HEAD_OP],
        "preflight_token":review["preflight_token"],
        "head_review_ack":[{"document_id":review["document_id"],"revision":review["revision"],
            "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}],
        "before":{(torso::HEAD_OP):{"target_recipe_key":"a".repeat(64)}},
        "after":{(torso::HEAD_OP):{"target_recipe_key":"b".repeat(64)}},"doc_state":{"document_id":"head-target"}})
}
#[test]
fn head_preflight_requires_all_target_bindings_and_zero_amount_pixels() {
    let value = review(); assert!(PresetKind::valid(&value, Some("head-target")));
    for key in value["head_transfer"].as_object().unwrap().keys() {
        let mut bad = value.clone(); bad["head_transfer"].as_object_mut().unwrap().remove(key);
        assert!(!PresetKind::valid(&bad, Some("head-target")), "{key}");
    }
    for (path, replacement) in [("/source_proof", Value::Null), ("/head_transfer/revision", json!("4")),
        ("/head_transfer/parameters/amount", json!(0.4)), ("/head_transfer/before/base64", json!("iVBORw==")),
        ("/head_transfer/after/sha256", json!("e".repeat(64))),
        ("/head_transfer/body_ref/asset_sha256", json!("2".repeat(64))),
        ("/head_transfer/associated_face/associated_face_ref/asset_sha256", json!("2".repeat(64)))] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = replacement;
        assert!(!PresetKind::valid(&bad, Some("head-target")), "{path}");
    }
    let mut bad = value.clone(); bad["applies"][torso::HEAD_OP]["amount"] = json!(-0.1);
    bad["head_transfer"]["parameters"] = bad["applies"][torso::HEAD_OP].clone();
    assert!(!PresetKind::valid(&bad, Some("head-target")));
}
#[test]
fn head_presets_are_scalar_only_with_no_cross_family_proof_ack_or_scope() {
    let value = review();
    for op in [torso::TORSO_OP, waist::WAIST_OP, torso::HEAD_OP, spill::SPILL_OP, shadow::SHADOW_OP, "lnx.exposure.v1"] {
        let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op)); bad["applies"][op] = json!({});
        assert!(!PresetKind::valid(&bad, Some("head-target")), "{op}");
    }
    for key in ["torso_transfer", "waist_transfer", "spill_transfer", "shadow_transfer", "people_transfer", "persistent_association", "xmp_transfer"] {
        let mut bad = value.clone(); bad[key] = json!({}); assert!(!PresetKind::valid(&bad, Some("head-target")), "{key}");
    }
    for key in ["torso_review_ack", "waist_review_ack", "head_review_ack", "spill_review_ack", "shadow_review_ack", "xmp_review_ack"] {
        let mut bad = value.clone(); bad[key] = Value::Null; assert!(!PresetKind::valid(&bad, Some("head-target")), "{key}");
    }
    for op in [torso::TORSO_OP, waist::WAIST_OP] {
        let mut bad = value.clone(); bad["module_scope"] = json!([op]); bad["applies"] = json!({(op):{"version":1,"amount":0}});
        assert!(!PresetKind::valid(&bad, Some("head-target")));
    }
    let catalog = json!({"schema":"lrt.preset.v1","id":"head","name":"Head","kind":"custom","builtin":false,
        "modules":{(torso::HEAD_OP):{"version":1,"amount":0.3}}});
    assert!(preset(&catalog));
    for key in ["head_box", "pivot", "transition", "body_ref", "associated_face", "support", "review"] {
        let mut bad = catalog.clone(); bad["modules"][torso::HEAD_OP][key] = Value::Null; assert!(!preset(&bad));
    }
    let mut bad = catalog.clone(); bad["modules"][torso::HEAD_OP]["amount"] = json!(-0.1); assert!(!preset(&bad));
    bad = catalog; bad["modules"][waist::WAIST_OP] = json!({"version":1,"amount":0.3}); assert!(!preset(&bad));
}
#[test]
fn terminal_head_receipts_preserve_original_identity_even_on_rejection_or_unknown() {
    let original = apply();
    for (success, unknown) in [(true,false), (false,true), (false,false)] {
        let mut value = original.clone(); value["success"] = json!(success); value["outcome_unknown"] = json!(unknown);
        assert!(PresetKind::valid(&value, Some("head-target")));
        for key in ["module_scope", "head_review_ack", "preflight_token"] {
            let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!PresetKind::valid(&bad, Some("head-target")), "{key}");
        }
        for key in ["torso_review_ack", "waist_review_ack"] {
            let mut bad = value.clone(); bad[key] = value["head_review_ack"].clone(); assert!(!PresetKind::valid(&bad, Some("head-target")));
        }
    }
    let mut bad = original.clone(); bad["after"][torso::HEAD_OP] = json!({"version":1,"amount":0.3});
    assert!(!PresetKind::valid(&bad, Some("head-target")));
    bad = original.clone(); bad["head_transfer"] = review()["head_transfer"].clone(); assert!(!PresetKind::valid(&bad, Some("head-target")));
    let command = json!({"cmd":"preset","action":"apply","request_id":original["request_id"],"document_id":original["document_id"],
        "preflight_token":original["preflight_token"],"head_review_ack":original["head_review_ack"]});
    for (key, replacement) in [("document_id", json!("foreign")), ("preflight_token", json!("e".repeat(32))),
        ("head_review_ack", json!([]))] {
        let mut host = PresetHost::default(); host.reset([1;16]); host.ready([1;16], true); host.begin_command([1;16], &command).unwrap();
        let mut bad = original.clone(); bad[key] = replacement; host.receive([1;16], &bad);
        let retained = host.status("head-apply")["result"].clone(); assert_eq!(retained["outcome_unknown"], true);
        assert_eq!(retained["document_id"], original["document_id"]); assert_eq!(retained["head_review_ack"], original["head_review_ack"]);
        assert_eq!(retained["preflight_token"], original["preflight_token"]);
    }
}
