// AUTHORED / UNRUN: transport contracts, not rendered-photo acceptance.
use super::*;
fn ack() -> Value { json!([{"document_id":"target", "revision":"3", "before_sha256":"a".repeat(64),
    "after_sha256":"b".repeat(64), "coverage_sha256":"c".repeat(64)}]) }
fn request() -> Value { json!({"cmd":"batch", "action":"commit", "request_id":"clavicle",
    "preflight_token":"f".repeat(32), "collarbone_review_ack":ack()}) }
#[test] fn exact_ack_and_command_shape() {
    assert!(command(&request()).is_ok());
    for key in ["people_transfer", "head_review_ack", "module_scope", "docs"] {
        let mut value=request(); value[key]=json!([]); assert!(command(&value).is_err());
    }
    for action in ["preflight", "undo", "redo", "state"] {
        let mut value=request(); value["action"]=json!(action); assert!(command(&value).is_err());
    }
}
#[test] fn coverage_and_ordered_unique_targets_are_required() {
    for key in ["before_sha256", "after_sha256", "coverage_sha256", "revision"] {
        let mut value=ack(); value[0].as_object_mut().unwrap().remove(key); assert!(!acknowledgments(&value));
    }
    let mut value=ack(); value[0]["revision"]=json!("03"); assert!(!acknowledgments(&value));
    let mut value=ack(); value.as_array_mut().unwrap().push(ack()[0].clone()); assert!(!acknowledgments(&value));
}
#[test] fn exact_binding_cannot_be_replaced_by_another_operation() {
    let original=request(); let bound=binding(&original).unwrap().unwrap();
    assert_eq!(bound[ACK], original[ACK]); assert_eq!(bound["preflight_token"],original["preflight_token"]);
    assert!(bound.get("module_scope").is_none());
    let mut value=json!({"action":"commit", "module_scope":[OP], "preflight_token":"f".repeat(32),
        "collarbone_review_ack":ack()});
    assert!(receipt(&value)); value["module_scope"]=json!(["lnx.head_size.v1"]); assert!(!receipt(&value));
}
#[test] fn unknown_receipt_keeps_original_ack_without_inventing_photographic_acceptance() {
    use crate::receipt_host::{ReceiptHost,ReceiptKind};
    struct Fixture;
    impl ReceiptKind for Fixture {
        const NAME: &'static str="batch";
        const ACTIONS: &'static [&'static str]=&["commit"];
        fn valid(v:&Value,_:Option<&str>)->bool { receipt(v) && v["success"].is_boolean() }
    }
    let mut host=ReceiptHost::<Fixture>::default();host.reset([1;16]);host.ready([1;16],true);
    let original=request();host.begin_command([1;16],&original).unwrap();
    let mut reply=json!({"action":"commit","request_id":"clavicle","success":true,"outcome_unknown":false,
        "module_scope":[OP],"preflight_token":"f".repeat(32),"collarbone_review_ack":ack()});
    reply[ACK][0]["coverage_sha256"]=json!("d".repeat(64));host.receive([1;16],&reply);
    let result=host.status("clavicle")["result"].clone();
    assert_eq!(result["outcome_unknown"],true);assert_eq!(result[ACK],original[ACK]);
}
#[test] fn generic_and_persistent_association_batch_routes_are_not_visual_people_review() {
    let mut value=json!({"cmd":"batch","action":"preflight","request_id":"review",
        "module_scope":[OP],"docs":["target"]});
    assert!(command(&value).is_err());
    value["people_transfer"]=json!({"target_policy":"persistent_association"});assert!(command(&value).is_err());
    value["people_transfer"]=json!({"target_policy":"explicit_face_map"});assert!(command(&value).is_ok());
    value["action"]=json!("commit");assert!(command(&value).is_err());
}
#[test] fn source_and_image_evidence_are_required_for_each_eligible_target() {
    let value=json!({"action":"preflight","success":true,"module_scope":[OP],"people_transfer":true,
        "applies":{"target_policy":"explicit_face_map"},"targets":[{"document_id":"target","revision":"3",
        "blocked":null,"people_transfer":{"collarbone_visual":{}}}],"ok":1,"blocked":0});
    assert!(!preflight(&value));
}
#[test] fn successful_or_unknown_selected_commit_must_retain_ack() {
    for (success,unknown) in [(true,false),(false,true)] {
        assert!(!receipt(&json!({"action":"commit","module_scope":[OP],"success":success,"outcome_unknown":unknown})));
    }
}
fn image_request_fixture()->Value {
    json!({"cmd":"batch","action":"collarbone_visual","request_id":"page", "preflight_token":"a".repeat(32),
        "document_id":"target","revision":"3","side":"before","sha256":"b".repeat(64)})
}
#[test] fn paged_retrieval_identity_and_read_only_bounds_are_exact() {
    let original=image_request_fixture();assert!(command(&original).is_ok());assert!(read_only(&original));
    let bound=binding(&original).unwrap().unwrap();
    for key in ["preflight_token","document_id","revision","side","sha256"] {assert_eq!(bound[key],original[key]);}
    for key in ["people_transfer","module_scope","collarbone_review_ack","path"] {
        let mut changed=original.clone();changed[key]=json!({});assert!(!read_only(&changed));assert!(command(&changed).is_err());
    }
    for side in ["mask","source","../before"] {
        let mut changed=original.clone();changed["side"]=json!(side);assert!(!read_only(&changed));
    }
    let mut changed=original;changed["action"]=json!("commit");assert!(!read_only(&changed));assert!(command(&changed).is_err());
}
#[test] fn only_bounded_people_collarbone_preflight_is_read_only() {
    let original=json!({"cmd":"batch","action":"preflight","request_id":"review","module_scope":[OP],
        "docs":["target"],"people_transfer":{"target_policy":"explicit_face_map"}});
    assert!(read_only(&original));
    for key in ["preflight_token","collarbone_review_ack","path"] {
        let mut changed=original.clone();changed[key]=json!({});assert!(!read_only(&changed));
    }
    let mut changed=original.clone();changed["people_transfer"]["target_policy"]=json!("persistent_association");assert!(!read_only(&changed));
    changed=original.clone();changed["docs"]=json!(["target","target"]);assert!(!read_only(&changed));
    changed=original;changed["action"]=json!("commit");assert!(!read_only(&changed));
}
#[test] fn compact_image_cannot_substitute_a_tiny_thumbnail() {
    let mut value=json!({"mime":"image/png","width":1024,"height":768,"sha256":"a".repeat(64)});
    assert!(compact_image(&value,(4000,3000)));value["width"]=json!(256);value["height"]=json!(192);
    assert!(!compact_image(&value,(4000,3000)));
    value["width"]=json!(1024);value["height"]=json!(768);value["base64"]=json!("AA==");
    assert!(!compact_image(&value,(4000,3000)));
}
