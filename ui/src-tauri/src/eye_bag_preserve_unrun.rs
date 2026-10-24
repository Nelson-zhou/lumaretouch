//! AUTHORED / UNRUN source fixtures, not cargo/test evidence.
use super::*;
fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "action":action, "payload":payload, "request_id":"request",
        "document_id":"d".repeat(32), "document_epoch":"epoch", "document_revision":7,
        "state_revision":11, "association_revision":3,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":2}}})
}
fn painted() -> Value {json!({"left":{"visible":true, "unoccluded":true, "ownership_confirmed":true,
    "recipe":{"version":1, "domain":"source-normalized", "objects":[{"id":"left-1", "name":"人物左眼卧蚕保护", "enabled":true,
        "operation":"add", "kind":"brush", "opacity":1.0, "feather":0, "points":[[0.5,0.55]], "axes":[[0.0015,0],[0,0.002]]}]}}})}
#[test] fn reference_and_images_are_reads_but_confirm_is_never_a_read() {
    assert!(read_only(&request("eye_bag_reference", json!({}))));
    assert!(read_only(&request("eye_bag_image", json!({"token":"b".repeat(32),"side":"support","sha256":"c".repeat(64)}))));
    assert!(!read_only(&request("eye_bag_confirm", json!({"token":"b".repeat(32),"ack":{
        "review_sha256":"c".repeat(64),"before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"support_overlay_sha256":"f".repeat(64)}}))));
}
#[test] fn bounded_manual_vectors_keep_hard_core_and_independent_identity() {
    assert!(eyes(&painted(), false));
    let mut value = painted(); value["left"]["recipe"]["objects"][0]["opacity"] = json!(0.5); assert!(!eyes(&value, false));
    let mut value = painted(); value["left"]["recipe"]["objects"][0]["operation"] = json!("intersect"); assert!(!eyes(&value, false));
    let mut value = painted(); value["left"]["visible"] = json!(false); assert!(!eyes(&value, false));
    let mut value = painted(); value["eye_light_visibility"] = value["left"].clone(); assert!(!eyes(&value, false));
}
#[test] fn positive_preview_and_hash_ack_are_required_neutral_uses_safe_patch() {
    let mut command_value = request("eye_bag_preview", json!({"recipe":{"version":2,"amount":0.5,"preserve":1}, "eyes":painted(),"replace_legacy":false}));
    assert!(command(&command_value).is_ok()); assert!(binding(&command_value).unwrap().is_some());
    command_value["payload"]["recipe"]["amount"] = json!(0); assert!(command(&command_value).is_err());
    assert!(command(&request("eye_bag_confirm", json!({"token":"b".repeat(32),"ack":{"reviewed":true}}))).is_err());
}
#[test] fn malformed_read_cannot_bypass_recovery_fence() {
    let mut command_value = request("eye_bag_reference", json!({})); command_value["extra"] = json!(true);
    assert!(!read_only(&command_value));
    let mut command_value = request("eye_bag_reference", json!({})); command_value["target"]["scope"] = json!("all_people");
    assert!(!read_only(&command_value));
}
#[test] fn support_metadata_keeps_canonical_and_decoded_source_distinct() {
    let source = json!({"source_width":4001,"source_height":3001,"decoded_width":4000,"decoded_height":3000});
    let image = json!({"mime":"image/png","width":1024,"height":768,"sha256":"c".repeat(64)});
    assert!(support_mapping(&source,&image,(4001,3001)));
    assert!(!support_mapping(&source,&image,(4000,3000)));
    let bad = json!({"source_width":4001,"source_height":3001,"decoded_width":1000,"decoded_height":1000});
    assert!(!support_mapping(&bad,&image,(4001,3001)));
}

#[test] fn integer_and_float_spellings_keep_the_same_scalar_recipe() {
    assert!(same_recipe(&json!({"version":2,"amount":1,"preserve":1}), &json!({"version":2,"amount":1.0,"preserve":1.0})));
    assert!(!same_recipe(&json!({"version":2,"amount":1,"preserve":1}), &json!({"version":2,"amount":1.0,"preserve":0.0})));
}
