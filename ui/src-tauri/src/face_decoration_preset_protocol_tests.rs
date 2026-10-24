// AUTHORED / UNRUN. Synthetic native transport fixtures, not rendered-photo acceptance.
use super::*;
fn ack()->Value {json!({"document_id":"logical-document","revision":"3","before_sha256":"a".repeat(64),
    "after_sha256":"b".repeat(64),"coverage_sha256":"c".repeat(64),"preset_sha256":"d".repeat(64),"applies_sha256":"e".repeat(64)})}
fn apply()->Value {json!({"cmd":"preset","action":"apply","request_id":"apply-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),(ACK):ack()})}
fn read()->Value {json!({"cmd":"preset","action":"face_decoration_visual","request_id":"read-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),"revision":"3","side":"before","sha256":"a".repeat(64)})}
fn preflight()->Value {json!({"cmd":"preset","action":"preflight","request_id":"review-one","id":"preset-one",
    "document_id":"load-one","module_scope":[OP,"lnx.exposure.v1"]})}
fn review_fixture()->Value {
    let source=json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let face=json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face-one","analysis_revision":2});
    let coverage=json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face,"scope":"target-reviewed-visible-skin",
        "visibility_sha256":"b".repeat(64),"recipe_sha256":"7".repeat(64)}]});
    let image=json!({"mime":"image/png","width":1024,"height":512,"sha256":"c".repeat(64)});
    let visual=json!({"version":1,"document_id":"logical-document","revision":"3","source_proof":source,
        "before_state_sha256":"d".repeat(64),"candidate_state_sha256":"e".repeat(64),"before_people_sha256":"f".repeat(64),
        "candidate_people_sha256":"1".repeat(64),"source_size":[2048,1024],"before_output_size":[2048,1024],"after_output_size":[2048,1024],
        "coverage_sha256":crate::batch_api::collarbone::request_digest(&coverage),"before":image,"after":image});
    json!({"protocol":1,"action":"preflight","request_id":"review-one","id":"preset-one","document_id":"load-one",
        "revision":"3","success":true,"outcome_unknown":false,"preflight_token":"f".repeat(32),"module_scope":[OP,"lnx.exposure.v1"],
        "applies":{(OP):{"recipe":{"version":1,"pattern":"freckle_dust","strength":0.5}},"lnx.exposure.v1":{"exposure":0.25}},
        "face_decoration_visual_required":true,"source_proof":source,"face_decoration_preset":{"version":1,"preset_sha256":"2".repeat(64),"applies_sha256":"3".repeat(64),
        "load_id":"load-one","owner":{"document":{"document_id":"logical-document","epoch":"workspace","revision":3},
        "people_scope":"logical-document","state_revision":4,"association_revision":2,"graph_sha256":"4".repeat(64),"source_proof":source},
        "face_ref":face,"coverage":coverage,"visual":visual}})
}
// AUTHORED / UNRUN. Protocol fixtures only, no render or build acceptance.
#[test] fn exact_review_and_retained_active_review() {
    let mut value=review_fixture();assert!(review(&value));assert!(receipt(&value));
    value["module_scope"]=json!(["lnx.exposure.v1"]);assert!(receipt(&value));
    value["face_decoration_preset"]["coverage"]["targets"][0]["visibility_sha256"]=json!("wrong");assert!(!receipt(&value));
}
#[test] fn exact_ack_cannot_be_batch_or_alias() {
    assert!(command(&apply()).is_ok());let mut value=apply();value[ACK]=json!([ack()]);assert!(command(&value).is_err());
    value=apply();value[ACK]["members"]=json!([]);assert!(command(&value).is_err());
    value=apply();value["face_decoration_review_ack"]=json!([]);assert!(command(&value).is_err());
}
#[test] fn retained_read_is_exact_and_mutation_is_not_readonly() {
    let mut value=preflight();value["module_scope"]=json!(["lnx.exposure.v1"]);assert!(read_only(&value));
    value["force"]=json!(true);assert!(!read_only(&value));assert!(!read_only(&apply()));assert!(read_only(&read()));
    let mut value=read();value["member_document_id"]=json!("sibling");assert!(command(&value).is_err());
}
#[test] fn extra_active_faces_remain_sorted_and_source_owned() {
    let mut value=review_fixture();let p=&mut value["face_decoration_preset"];
    let mut other=p["coverage"]["targets"][0].clone();other["face_ref"]["face_instance_id"]=json!("face-two");
    p["coverage"]["targets"].as_array_mut().unwrap().push(other);
    p["visual"]["coverage_sha256"]=json!(crate::batch_api::collarbone::request_digest(&p["coverage"]));assert!(review(&value));
    value["face_decoration_preset"]["coverage"]["targets"][1]["face_ref"]["asset_sha256"]=json!("0".repeat(64));assert!(!review(&value));
}
#[test] fn unknown_or_expired_apply_keeps_ack_without_invented_scope() {
    let mut v=json!({"action":"apply","face_decoration_visual_required":true,"success":false,"outcome_unknown":false,"preflight_token":"f".repeat(32),(ACK):ack()});assert!(receipt(&v));
    v["module_scope"]=json!([OP]);v["outcome_unknown"]=json!(true);v.as_object_mut().unwrap().remove(ACK);assert!(!receipt(&v));
}
#[test] fn retained_required_marker_cannot_lose_wrapper() {
    let mut v=review_fixture();v["module_scope"]=json!(["lnx.exposure.v1"]);v["face_decoration_visual_required"]=json!(true);
    assert!(receipt(&v));v.as_object_mut().unwrap().remove("face_decoration_preset");assert!(!receipt(&v));
    v["face_decoration_visual_required"]=json!(false);assert!(!receipt(&v));
}
