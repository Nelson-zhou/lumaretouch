//! AUTHORED / UNRUN. Synthetic protocol evidence, not full-head/photo acceptance.
use super::*;
use serde_json::json;
fn review(amount: f64) -> Value {
    crate::torso_transfer_protocol::tests::sample_transfer(&json!("target"), &json!("5"),
        &json!({"version":1,"amount":amount}),
        &json!({"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}))
}
fn request() -> Value {
    let pair = review(0.0);
    json!({"cmd":"batch","action":"commit","request_id":"head-commit","preflight_token":"a".repeat(32),
        "head_review_ack":[{"document_id":"target","revision":"5",
            "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}]})
}
#[test]
fn head_policy_is_explicit_nonnegative_scalar_only_and_legacy_signed_values_remain() {
    for amount in [0.0, 0.3, 1.0] { assert!(head_parameters(&json!({"version":1,"amount":amount}))); }
    for amount in [-1.0, -0.01, 1.01] { assert!(!head_parameters(&json!({"version":1,"amount":amount}))); }
    for value in [json!({"version":2,"amount":0}), json!({"version":1,"amount":true}),
        json!({"version":1,"amount":"0.3"}), json!({"amount":0})] { assert!(!head_parameters(&value)); }
    for key in ["head_box", "pivot", "transition", "body_ref", "associated_face", "support", "review", "mask"] {
        let mut params = json!({"version":1,"amount":0.3}); params[key] = Value::Null;
        assert!(!head_parameters(&params), "{key}");
    }
    let signed = json!({"version":1,"amount":-0.3});
    assert!(parameters(&signed)); assert!(crate::waist_transfer_protocol::parameters(&signed));
    let value = review(-0.3);
    assert!(transfer(&value, &value["document_id"], &value["revision"], &signed, &value["source_proof"]));
    assert!(!head_transfer(&value, &value["document_id"], &value["revision"], &signed, &value["source_proof"]));
}
#[test]
fn head_commands_never_borrow_an_ack_proof_or_mixed_scope() {
    let original = request(); assert!(head_command(&original).is_ok());
    for key in ["torso_review_ack", "waist_review_ack", "spill_review_ack", "shadow_review_ack",
        "torso_transfer", "waist_transfer", "head_transfer", "local_mask_transfer", "people_transfer",
        "reference_color", "xmp_ack", "xmp_review_ack"] {
        let mut value = original.clone(); value[key] = Value::Null;
        assert!(head_command(&value).is_err(), "{key}");
    }
    for scope in [json!([TORSO_OP]), json!([crate::waist_transfer_protocol::WAIST_OP]),
        json!([HEAD_OP,"lnx.exposure.v1"]), json!([HEAD_OP,HEAD_OP]), json!([])] {
        let mut value = original.clone(); value["module_scope"] = scope;
        assert!(head_command(&value).is_err());
    }
    for action in ["preflight", "undo", "redo", "save", "import", "state", "people_targets"] {
        let mut value = original.clone(); value["action"] = json!(action); assert!(head_command(&value).is_err());
    }
    let mut value = original.clone(); value["module_scope"] = json!([HEAD_OP]); assert!(head_command(&value).is_ok());
    value["cmd"] = json!("preset"); value["action"] = json!("apply"); value["document_id"] = json!("target");
    assert!(head_command(&value).is_ok());
    value["document_id"] = json!("foreign"); assert!(head_command(&value).is_err());
    for (operation, ack) in [(TORSO_OP, "torso_review_ack"), (crate::waist_transfer_protocol::WAIST_OP, "waist_review_ack")] {
        let mut value = original.clone(); value["module_scope"] = json!([operation]);
        value[ack] = value["head_review_ack"].clone();
        assert!(scalar_command(&value, operation, ack).is_err());
    }
}
#[test]
fn zero_head_amount_requires_the_entire_target_proof_and_both_verified_pngs() {
    let original = review(0.0);
    let valid = |value: &Value| head_transfer(value, &original["document_id"], &original["revision"],
        &original["parameters"], &original["source_proof"]);
    assert!(valid(&original));
    for key in original.as_object().unwrap().keys() {
        let mut value = original.clone(); value.as_object_mut().unwrap().remove(key);
        assert!(!valid(&value), "{key}");
    }
    for (pointer, replacement) in [("/body_ref/asset_sha256", json!("2".repeat(64))),
        ("/associated_face/associated_face_ref/asset_sha256", json!("2".repeat(64))),
        ("/associated_face/associated_face_ref/analysis_revision", json!("4")),
        ("/associated_face/associated_face_box", json!([0.3,0.1,0.2,0.4])),
        ("/parameters/amount", json!(0.1)), ("/revision", json!("05")),
        ("/body_support_sha256", Value::Null), ("/body_review_sha256", json!("bad")),
        ("/before_bank_sha256", json!("a".repeat(63))), ("/candidate_bank_sha256", Value::Null)] {
        let mut value = original.clone(); *value.pointer_mut(pointer).unwrap() = replacement;
        assert!(!valid(&value), "{pointer}");
    }
    for side in ["before", "after"] {
        for (key, replacement) in [("base64", json!("iVBORw==")), ("base64", json!("A".repeat(MAX_BASE64 + 4))),
            ("sha256", json!("e".repeat(64))), ("width", json!(2)), ("height", json!(257))] {
            let mut value = original.clone(); value[side][key] = replacement; assert!(!valid(&value), "{side}/{key}");
        }
        let mut bytes = STANDARD.decode(original[side]["base64"].as_str().unwrap()).unwrap(); bytes[29] ^= 1;
        let mut value = original.clone(); value[side]["base64"] = json!(STANDARD.encode(&bytes));
        value[side]["sha256"] = json!(format!("{:x}", Sha256::digest(&bytes))); assert!(!valid(&value));
    }
    for key in ["head_box", "pivot", "support", "body_refs", "automatic_detector"] {
        let mut value = original.clone(); value[key] = json!({}); assert!(!valid(&value), "{key}");
    }
}
#[test]
fn exact_ordered_ack_items_remain_bounded_and_have_no_geometry() {
    let original = request(); let ack = &original["head_review_ack"][0];
    assert!(acknowledgments(&original["head_review_ack"]));
    assert!(!acknowledgments(&json!([ack,ack])));
    for (key, replacement) in [("revision", json!("05")), ("before_sha256", json!("bad")),
        ("after_sha256", Value::Null), ("head_box", json!([0.1,0.1,0.8,0.8]))] {
        let mut changed = ack.clone(); changed[key] = replacement; assert!(!acknowledgments(&json!([changed])));
    }
    let many: Vec<Value> = (0..9).map(|index| { let mut value = ack.clone(); value["document_id"] = json!(format!("head-{index}")); value }).collect();
    assert!(!acknowledgments(&json!(many))); assert!(acknowledgments(&json!(&many[..8])));
}
