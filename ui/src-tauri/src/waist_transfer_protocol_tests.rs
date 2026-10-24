//! AUTHORED / UNRUN. Synthetic transport fixtures, not body/marker or render acceptance.
use super::*;
use serde_json::json;
fn review() -> Value {
    crate::torso_transfer_protocol::tests::sample_transfer(&json!("target"), &json!("5"),
        &json!({"version":1,"amount":0.3}), &json!({"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}))
}
fn request() -> Value {
    let value=review();
    json!({"cmd":"batch","action":"commit","request_id":"waist-commit","preflight_token":"a".repeat(32),
        "waist_review_ack":[{"document_id":"target","revision":"5","before_sha256":value["before"]["sha256"],"after_sha256":value["after"]["sha256"]}]})
}
#[test]
fn exact_waist_command_has_an_independent_acknowledgment_family() {
    let original=request();assert!(command(&original).is_ok());
    for key in ["torso_review_ack","spill_review_ack","shadow_review_ack","local_mask_transfer","people_transfer","reference_color","xmp_ack","xmp_review_ack"] {
        let mut value=original.clone();value[key]=json!([]);assert!(command(&value).is_err(),"{key}");
    }
    for action in ["preflight","undo","redo","save","import","state"] {
        let mut value=original.clone();value["action"]=json!(action);assert!(command(&value).is_err());
    }
    for scope in [json!([crate::torso_transfer_protocol::TORSO_OP]),json!([WAIST_OP,"lnx.exposure.v1"]),json!([])] {
        let mut value=original.clone();value["module_scope"]=scope;assert!(command(&value).is_err());
    }
    let mut value=original.clone();value["module_scope"]=json!([WAIST_OP]);assert!(command(&value).is_ok());
    value["cmd"]=json!("preset");value["action"]=json!("apply");value["document_id"]=json!("target");assert!(command(&value).is_ok());
    value["document_id"]=json!("foreign");assert!(command(&value).is_err());
}
#[test]
fn common_proof_requires_target_body_own_face_support_review_and_verified_pngs() {
    let original=review();
    let valid=|value:&Value|transfer(value,&original["document_id"],&original["revision"],&original["parameters"],&original["source_proof"]);
    assert!(valid(&original));
    for key in original.as_object().unwrap().keys() {let mut value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(!valid(&value),"{key}");}
    let mut value=original.clone();value["body_ref"]["asset_sha256"]=json!("2".repeat(64));assert!(!valid(&value));
    value=original.clone();value["associated_face"]["associated_face_ref"]["asset_sha256"]=json!("2".repeat(64));assert!(!valid(&value));
    value=original.clone();value["body_review_sha256"]=Value::Null;assert!(!valid(&value));
    value=original.clone();value["after"]["base64"]=json!("iVBORw==");assert!(!valid(&value));
    for key in ["waist_points","support","review","body_ref","associated_face","source_proof"] {
        let mut params=json!({"version":1,"amount":0.3});params[key]=json!({});assert!(!parameters(&params));
    }
}
