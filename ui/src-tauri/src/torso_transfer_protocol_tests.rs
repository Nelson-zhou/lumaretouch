//! AUTHORED / UNRUN. Source-only fixtures, not real portrait or browser acceptance.
use super::*;
use serde_json::json;

pub(crate) fn sample_transfer(document: &Value, rev: &Value, params: &Value, source: &Value) -> Value {
    let mut value = crate::original_shadow_transfer_protocol::tests::sample_transfer(document, rev, params, source);
    value["body_ref"] = json!({"asset_sha256":source["asset_sha256"],"body_instance_id":"body:actual","analysis_revision":3});
    value["associated_face"] = json!({
        "associated_face_ref":{"asset_sha256":source["asset_sha256"],"face_instance_id":"face:actual","analysis_revision":4},
        "associated_face_box":[0.3,0.1,0.7,0.3],"associated_face_evidence_sha256":"e".repeat(64)});
    value["body_support_sha256"] = json!("5".repeat(64));
    value["body_review_sha256"] = json!("6".repeat(64));
    value["before_bank_sha256"] = json!("7".repeat(64));
    value["candidate_bank_sha256"] = json!("8".repeat(64));
    value
}
fn sample() -> Value {
    sample_transfer(&json!("loaded-photo"), &json!("4"), &json!({"version":1,"amount":0.35}),
        &json!({"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}))
}
fn valid(value: &Value) -> bool {
    let expected = sample();
    transfer(value, &expected["document_id"], &expected["revision"], &expected["parameters"], &expected["source_proof"])
}
fn acknowledgment() -> Value {
    let value = sample();
    json!({"document_id":value["document_id"],"revision":value["revision"],"before_sha256":value["before"]["sha256"],"after_sha256":value["after"]["sha256"]})
}
fn request() -> Value {
    json!({"cmd":"batch","action":"commit","request_id":"torso-commit","preflight_token":"f".repeat(32),"torso_review_ack":[acknowledgment()]})
}
#[test]
fn exact_target_owned_complete_proof_is_required() {
    let original = sample(); assert!(valid(&original));
    for key in original.as_object().unwrap().keys() {
        let mut value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(!valid(&value),"missing {key}");
    }
    for (key,replacement) in [("support",json!({})),("version",json!(2)),("document_id",json!("foreign")),
        ("revision",json!("04")),("parameters",json!({"version":1,"amount":0.36})),("before_bank_sha256",json!("bad")),
        ("body_review_sha256",Value::Null),("candidate_people_sha256",json!(false)),("source_size",json!([0,1]))] {
        let mut value=original.clone();value[key]=replacement;assert!(!valid(&value),"{key}");
    }
    for field in ["body_ref","associated_face"] {
        let mut value=original.clone();value[field]["unrequested"]=json!(true);assert!(!valid(&value));
    }
}
#[test]
fn body_and_actual_face_have_distinct_exact_target_source_references() {
    let original=sample();
    let mut value=original.clone();value["body_ref"]["asset_sha256"]=json!("9".repeat(64));assert!(!valid(&value));
    value=original.clone();value["associated_face"]["associated_face_ref"]["asset_sha256"]=json!("9".repeat(64));assert!(!valid(&value));
    value=original.clone();value["body_ref"]=value["associated_face"]["associated_face_ref"].clone();assert!(!valid(&value));
    for revision in [json!(-1),json!(1.5),json!(9_007_199_254_740_992_u64),json!("3")] {
        value=original.clone();value["body_ref"]["analysis_revision"]=revision;assert!(!valid(&value));
    }
    for face_box in [json!([0,0.1,0.7,0.3]),json!([0.3,0.1,1,0.3]),json!([0.7,0.1,0.3,0.3]),json!([0.1,0.2,0.3])] {
        value=original.clone();value["associated_face"]["associated_face_box"]=face_box;assert!(!valid(&value));
    }
}
#[test]
fn parameters_never_accept_source_support_ownership_or_arbitrary_fields() {
    for amount in [-1.0,0.0,1.0] {assert!(parameters(&json!({"version":1,"amount":amount})));}
    for params in [json!({"version":1,"amount":1.01}),json!({"version":2,"amount":0}),json!({"version":1,"amount":true}),json!({"amount":0})] {assert!(!parameters(&params));}
    for key in ["body_ref","associated_face","support","points","review","enabled"] {
        let mut value=json!({"version":1,"amount":0.2});value[key]=Value::Null;assert!(!parameters(&value));
    }
}
#[test]
fn png_content_is_verified_beyond_metadata() {
    let original=sample();
    for side in ["before","after"] {
        for (key,replacement) in [("sha256",json!("e".repeat(64))),("width",json!(2)),("height",json!(257)),("base64",json!("iVBORw==")),("base64",json!("A".repeat(MAX_BASE64+4))),("extra",json!(true))] {
            let mut value=original.clone();value[side][key]=replacement;assert!(!valid(&value));
        }
        let mut bytes=STANDARD.decode(original[side]["base64"].as_str().unwrap()).unwrap();bytes[29]^=1;
        let mut value=original.clone();value[side]["base64"]=json!(STANDARD.encode(&bytes));value[side]["sha256"]=json!(format!("{:x}",Sha256::digest(&bytes)));assert!(!valid(&value));
    }
}
#[test]
fn ack_only_belongs_to_correlated_frozen_torso_application() {
    let original=request();assert!(command(&original).is_ok());
    let mut value=original.clone();value["torso_review_ack"]=json!([]);assert!(command(&value).is_ok());
    for action in ["preflight","undo","redo","save","import","people_targets"] {
        value=original.clone();value["action"]=json!(action);assert!(command(&value).is_err());
    }
    for key in ["request_id","preflight_token"] {value=original.clone();value.as_object_mut().unwrap().remove(key);assert!(command(&value).is_err());}
    for key in ["people_transfer","shadow_review_ack","spill_review_ack","xmp_review_ack","local_mask_transfer"] {
        value=original.clone();value[key]=json!([]);assert!(command(&value).is_err());
    }
    value=original.clone();value["module_scope"]=json!([TORSO_OP,"lnx.exposure.v1"]);assert!(command(&value).is_err());
    value=original.clone();value["module_scope"]=json!(["lnx.exposure.v1"]);assert!(command(&value).is_err());
    value=original.clone();value["cmd"]=json!("preset");value["action"]=json!("apply");value["document_id"]=json!("loaded-photo");assert!(command(&value).is_ok());
    value["document_id"]=json!("foreign");assert!(command(&value).is_err());
    value["document_id"]=json!("loaded-photo");value["torso_review_ack"]=json!([]);assert!(command(&value).is_err());
}
#[test]
fn acknowledgment_bounds_and_exact_fields_are_enforced() {
    assert!(acknowledgments(&json!([acknowledgment()])));
    assert!(!acknowledgments(&json!([acknowledgment(),acknowledgment()])));
    for rev in ["04","","-1","18446744073709551616"] {
        let mut ack=acknowledgment();ack["revision"]=json!(rev);assert!(!acknowledgments(&json!([ack])));
    }
    let mut ack=acknowledgment();ack["reviewed"]=json!(true);assert!(!acknowledgments(&json!([ack])));
    let items=(0..9).map(|i| {let mut ack=acknowledgment();ack["document_id"]=json!(format!("target-{i}"));ack}).collect::<Vec<_>>();
    assert!(!acknowledgments(&json!(items)));assert!(acknowledgments(&json!(&items[..8])));
}
