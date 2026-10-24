// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Synthetic native transport fixtures, not rendered-photo acceptance.
use super::*;
fn ack()->Value {json!({"document_id":"logical-document","revision":"3","before_sha256":"a".repeat(64),
    "after_sha256":"b".repeat(64),"coverage_sha256":"c".repeat(64),"preset_sha256":"d".repeat(64),"applies_sha256":"e".repeat(64),"replace_legacy":false})}
fn apply()->Value {json!({"cmd":"preset","action":"apply","request_id":"apply-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),(ACK):ack()})}
fn read()->Value {json!({"cmd":"preset","action":"eye_bag_visual","request_id":"read-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),"revision":"3","side":"before","sha256":"a".repeat(64)})}
fn preflight()->Value {json!({"cmd":"preset","action":"preflight","request_id":"review-one","id":"preset-one",
    "document_id":"load-one","module_scope":[OP,"lnx.exposure.v1"],"eye_bag_replace_legacy":false})}
fn review_fixture()->Value {
    let source=json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let face=json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face-one","analysis_revision":2});
    let coverage=json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face,"scope":"target-reviewed-ridge",
        "ridge_sha256":"b".repeat(64),"sides":["left"]}]});
    let image=json!({"mime":"image/png","width":1024,"height":512,"sha256":"c".repeat(64)});
    let visual=json!({"version":1,"document_id":"logical-document","revision":"3","source_proof":source,
        "before_state_sha256":"d".repeat(64),"candidate_state_sha256":"e".repeat(64),"before_people_sha256":"f".repeat(64),
        "candidate_people_sha256":"1".repeat(64),"source_size":[2048,1024],"before_output_size":[2048,1024],"after_output_size":[2048,1024],
        "coverage_sha256":crate::batch_api::collarbone::request_digest(&coverage),"before":image,"after":image});
    json!({"protocol":1,"action":"preflight","request_id":"review-one","id":"preset-one","document_id":"load-one",
        "revision":"3","success":true,"outcome_unknown":false,"preflight_token":"f".repeat(32),"module_scope":[OP,"lnx.exposure.v1"],
        "eye_bag_replace_legacy":false,"applies":{(OP):{"recipe":{"version":2,"amount":0.3,"preserve":1.0}},"lnx.exposure.v1":{"exposure":0.25}},
        "source_proof":source,"eye_bag_preset":{"version":1,"preset_sha256":"2".repeat(64),"applies_sha256":"3".repeat(64),
        "load_id":"load-one","owner":{"document":{"document_id":"logical-document","epoch":"workspace","revision":3},
        "people_scope":"logical-document","state_revision":4,"association_revision":2,"graph_sha256":"4".repeat(64),"source_proof":source},
        "face_ref":face,"coverage":coverage,"visual":visual,"replace_legacy":false}})
}

#[test] fn explicit_preflight_policy_is_typed_and_read_only() {
    let value=preflight();assert!(command(&value).is_ok());assert!(read_only(&value));
    for bad_value in [Value::Null,json!(0),json!("false")] {
        let mut bad=value.clone();bad["eye_bag_replace_legacy"]=bad_value;
        assert!(command(&bad).is_err());assert!(!read_only(&bad));
    }
    let mut neutral=value.clone();neutral.as_object_mut().unwrap().remove("eye_bag_replace_legacy");assert!(command(&neutral).is_ok());assert!(!read_only(&neutral));
    let mut bad=value.clone();bad["module_scope"]=json!(["lnx.exposure.v1"]);assert!(command(&bad).is_err());
    bad=value;bad["force"]=json!(true);assert!(!read_only(&bad));
}
#[test] fn replacement_choice_is_inside_exact_apply_ack_only() {
    let value=apply();assert!(command(&value).is_ok());assert!(!read_only(&value));
    let mut bad=value.clone();bad["eye_bag_replace_legacy"]=json!(false);assert!(command(&bad).is_err());
    bad=value.clone();bad[ACK].as_object_mut().unwrap().remove("replace_legacy");assert!(command(&bad).is_err());
    bad=value.clone();bad[ACK]=json!([ack()]);assert!(command(&bad).is_err());
    bad=value;bad.as_object_mut().unwrap().remove(ACK);bad["eye_bag_review_ack"]=ack();assert!(command(&bad).is_err());
}
#[test] fn exact_image_identity_and_namespace() {
    assert!(read_only(&read()));assert!(command(&read()).is_ok());
    assert!(super::super::collarbone::command(&read()).is_ok());
    for key in ["path","modules","eye_bag_replace_legacy","eye_bag_preset_ack"] {
        let mut bad=read();bad[key]=json!(true);assert!(!read_only(&bad));assert!(command(&bad).is_err());
    }
    let mut foreign=read();foreign["cmd"]=json!("batch");assert!(binding(&foreign).unwrap().is_none());assert!(!read_only(&foreign));
}
#[test] fn coverage_is_own_face_ridge_not_another_family() {
    let value=review_fixture();assert!(review(&value));
    assert_ne!(value["document_id"],value["eye_bag_preset"]["visual"]["document_id"]);
    for side in [json!([]),json!(["left","left"]),json!(["right","left"]),json!(["upper"])] {
        let mut bad=value.clone();bad["eye_bag_preset"]["coverage"]["targets"][0]["sides"]=side;assert!(!review(&bad));
    }
    let mut bad=value.clone();bad["eye_bag_preset"]["coverage"]["targets"][0]["face_ref"]["face_instance_id"]=json!("donor");assert!(!review(&bad));
    bad=value;bad["eye_bag_preset"]["coverage"]["targets"][0]["clavicle_category"]=json!("female");assert!(!review(&bad));
}
#[test] fn neutral_coverage_needs_no_ridge_or_sides() {
    let mut value=review_fixture();let face=value["eye_bag_preset"]["face_ref"].clone();
    value["eye_bag_preset"]["coverage"]["targets"][0]=json!({"face_ref":face,"scope":"neutral-no-effect","ridge_sha256":null,"sides":[]});
    value["eye_bag_preset"]["visual"]["coverage_sha256"]=json!(crate::batch_api::collarbone::request_digest(&value["eye_bag_preset"]["coverage"]));
    assert!(review(&value));value["eye_bag_preset"]["coverage"]["targets"][0]["sides"]=json!(["left"]);assert!(!review(&value));
}
#[test] fn replacement_owner_and_image_metadata_cannot_drift() {
    let value=review_fixture();
    for pointer in ["/eye_bag_preset/replace_legacy","/eye_bag_replace_legacy"] {
        let mut bad=value.clone();*bad.pointer_mut(pointer).unwrap()=json!(true);assert!(!review(&bad));
    }
    let mut bad=value.clone();bad["eye_bag_preset"]["visual"]["after"]["width"]=json!(256);assert!(!review(&bad));
    bad=value.clone();bad["eye_bag_preset"]["face_ref"]["asset_sha256"]=json!("9".repeat(64));assert!(!review(&bad));
    bad=value;bad["eye_bag_preset"]["visual"]["document_id"]=json!("load-one");assert!(!review(&bad));
}
#[test] fn successful_or_unknown_apply_requires_exact_ack() {
    let mut value=apply();value["module_scope"]=json!([OP]);value["success"]=json!(true);value["outcome_unknown"]=json!(false);
    assert!(receipt(&value));value.as_object_mut().unwrap().remove(ACK);assert!(!receipt(&value));
    value["success"]=json!(false);value["outcome_unknown"]=json!(true);assert!(receipt(&value));
    // A known dormant reset retains the legacy generic path without review assets.
    value["success"]=json!(true);value["outcome_unknown"]=json!(false);
    value["after"]=json!({(OP):{"recipe":{"version":2,"amount":0.,"preserve":1.}}});assert!(receipt(&value));
    value["after"][OP]["recipe"]["amount"]=json!(0.1);assert!(!receipt(&value));
}
#[test] fn original_request_binding_retains_policy_and_ack_on_unknown() {
    let fields=binding(&preflight()).unwrap().unwrap();assert_eq!(fields["eye_bag_replace_legacy"],false);
    let fields=binding(&apply()).unwrap().unwrap();assert_eq!(fields[ACK],ack());
    let mut host=crate::preset_host::PresetHost::default();host.reset([1;16]);host.ready([1;16],true);host.begin_command([1;16],&apply()).unwrap();
    let mut wrong=apply();wrong["event"]=json!("preset_result");wrong["protocol"]=json!(1);wrong["success"]=json!(true);
    wrong["outcome_unknown"]=json!(false);wrong["document_id"]=json!("foreign");host.receive([1;16],&wrong);
    let result=host.status("apply-one")["result"].clone();assert_eq!(result["outcome_unknown"],true);
    assert_eq!(result[ACK],ack());assert_eq!(result["document_id"],"load-one");
}

#[test] fn source_proof_cannot_be_rebound_to_another_face() {
    let mut value=review_fixture();value["eye_bag_preset"]["face_ref"]["asset_sha256"]=json!("8".repeat(64));
    assert!(!review(&value));
}

#[test] fn derived_review_binds_effective_asset_not_original_provenance(){
    let mut value=review_fixture();let asset="9".repeat(64);
    let source=json!({"asset_sha256":asset,"original_sha256":"a".repeat(64),
        "creative_source":{"sha256":asset,"width":2048,"height":1024}});
    value["source_proof"]=source.clone();
    value["eye_bag_preset"]["owner"]["source_proof"]=source.clone();
    value["eye_bag_preset"]["visual"]["source_proof"]=source;
    value["eye_bag_preset"]["face_ref"]["asset_sha256"]=json!(asset);
    value["eye_bag_preset"]["coverage"]["targets"][0]["face_ref"]["asset_sha256"]=json!(asset);
    value["eye_bag_preset"]["visual"]["coverage_sha256"]=json!(crate::batch_api::collarbone::request_digest(&value["eye_bag_preset"]["coverage"]));
    assert!(review(&value));
    value["eye_bag_preset"]["face_ref"]["asset_sha256"]=json!("a".repeat(64));
    assert!(!review(&value));
}
