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

fn cohort_request() -> Value {
    json!({"cmd":"batch","action":"preflight","request_id":"cohort","docs":["target"],"module_scope":[],"conflict_policy":"recheck",
        "people_transfer":{"target_policy":"persistent_association","operation":"unlink","association_id":"association",
            "source_ref":{},"source":{},"selection":{},"targets":[{"target":{"document":{"document_id":"target"}},"target_refs":[{}]}]}})
}
#[test] fn cohort_unlink_preflight_is_read_only_without_selected_module() {
    let value=cohort_request();assert!(command(&value).is_ok());assert!(read_only(&value));
    let proof=binding(&value).unwrap().unwrap();assert_eq!(proof["collarbone_applies_sha256"],request_digest(&value["people_transfer"]));
    assert_eq!(proof["module_scope"],json!([]));
    let mut changed=value.clone();changed["action"]=json!("commit");assert!(!read_only(&changed));
    changed=value.clone();changed["conflict_policy"]=json!("skip_and_report");assert!(!read_only(&changed));
    changed=value;changed["docs"]=json!(["other"]);assert!(!read_only(&changed));
}
#[test] fn cohort_commit_requires_ack_even_when_module_scope_is_empty() {
    let mut value=json!({"action":"commit","module_scope":[],"collarbone_cohort":true,"success":true,
        "preflight_token":"f".repeat(32)});
    assert!(!receipt(&value));value[ACK]=ack();assert!(receipt(&value));
    value["collarbone_cohort"]=json!(false);assert!(!receipt(&value));
}
#[test] fn persistent_marker_cannot_replace_whole_cohort_images() {
    let value=json!({"action":"preflight","success":true,"module_scope":[],"collarbone_cohort":true,
        "people_transfer":true,"applies":{"target_policy":"persistent_association"},"policy":"recheck",
        "persistent_association":{"members":[{},{}]},"targets":[{}],"association_source":{},"blocked":0,"ok":1,"rejected_docs":[]});
    assert!(!preflight(&value));
}
#[test] fn inherited_collarbone_intent_requires_cohort_marker_even_without_scope() {
    let value=json!({"action":"preflight","success":true,"module_scope":[],"people_transfer":true,
        "applies":{"target_policy":"persistent_association"},"persistent_association":{"intent":[{"op":OP}]}});
    assert!(!preflight(&value));
}

fn cohort_target(id:&str, digest:&str)->Value {
    let reference=json!({"asset_sha256":digest,"face_instance_id":format!("face-{id}"),"analysis_revision":0});
    let proof=json!({"asset_sha256":digest,"original_sha256":digest,"creative_source":null});
    let image=json!({"mime":"image/png","width":1024,"height":768,"sha256":"1".repeat(64)});
    json!({"document_id":id,"revision":"3","blocked":null,"association":{
        "owner":{"document":{"document_id":id,"revision":3},"source_proof":proof},"ref":reference,
        "collarbone_coverage":{"version":1,"support_transfer":"none","targets":[{"face_ref":reference}]},
        "collarbone_visual":{"version":1,"document_id":id,"revision":"3","source_proof":proof,
            "before_state_sha256":"2".repeat(64),"candidate_state_sha256":"3".repeat(64),
            "before_people_sha256":"4".repeat(64),"candidate_people_sha256":"5".repeat(64),
            "coverage_sha256":"6".repeat(64),"source_size":[4000,3000],"before_output_size":[4000,3000],
            "after_output_size":[4000,3000],"before":image,"after":image}}})
}
#[test] fn exact_source_and_all_targets_form_one_reviewed_cohort() {
    let source=cohort_target("source",&"a".repeat(64));let target=cohort_target("target",&"b".repeat(64));
    let original=json!({"action":"preflight","success":true,"module_scope":[],"collarbone_cohort":true,
        "people_transfer":true,"applies":{"target_policy":"persistent_association"},"policy":"recheck",
        "persistent_association":{"members":[{"document_id":"source","ref":source["association"]["ref"]},
            {"document_id":"target","ref":target["association"]["ref"]}],"intent":[]},
        "source_snapshot":{"document_id":"source"},"association_source":source,"targets":[target],
        "blocked":0,"ok":1,"rejected_docs":[]});
    assert!(preflight(&original));
    for pointer in ["/association_source/association/collarbone_visual", "/targets/0/association/collarbone_visual",
        "/association_source/association/collarbone_coverage", "/targets/0/association/collarbone_coverage"] {
        let mut changed=original.clone();*changed.pointer_mut(pointer).unwrap()=Value::Null;assert!(!preflight(&changed));
    }
    let mut changed=original;changed["targets"][0]["association"]["owner"]["source_proof"]["asset_sha256"]=json!("c".repeat(64));
    assert!(!preflight(&changed));
}

#[test] fn cohort_request_digest_preserves_content_and_array_order() {
    let left=json!({"z":1,"a":{"b":2,"a":3},"targets":["source","target"]});
    let right=json!({"targets":["source","target"],"a":{"a":3,"b":2},"z":1});
    assert_eq!(request_digest(&left),request_digest(&right));
    let mut changed=right;changed["targets"]=json!(["target","source"]);
    assert_ne!(request_digest(&left),request_digest(&changed));
}
