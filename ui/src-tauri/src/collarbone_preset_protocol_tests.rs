// AUTHORED / UNRUN. Synthetic native transport fixtures, not rendered-photo acceptance.
use super::*;
fn ack()->Value {json!({"document_id":"logical-document","revision":"3","before_sha256":"a".repeat(64),
    "after_sha256":"b".repeat(64),"coverage_sha256":"c".repeat(64),"preset_sha256":"d".repeat(64),"applies_sha256":"e".repeat(64)})}
fn apply()->Value {json!({"cmd":"preset","action":"apply","request_id":"apply-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),(ACK):ack()})}
fn read()->Value {json!({"cmd":"preset","action":"collarbone_visual","request_id":"read-one","id":"preset-one",
    "document_id":"load-one","preflight_token":"f".repeat(32),"revision":"3","side":"before","sha256":"a".repeat(64)})}
fn preflight()->Value {json!({"cmd":"preset","action":"preflight","request_id":"review-one","id":"preset-one",
    "document_id":"load-one","module_scope":[OP,"lnx.exposure.v1"]})}
fn review_fixture()->Value {
    let source=json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let face=json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face-one","analysis_revision":2});
    let coverage=json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face,"scope":"reviewed-clavicle-only",
        "body_review_sha256":"b".repeat(64),"clavicle_category":"female","clavicle_sides":["left"]}]});
    let image=json!({"mime":"image/png","width":1024,"height":512,"sha256":"c".repeat(64)});
    let visual=json!({"version":1,"document_id":"logical-document","revision":"3","source_proof":source,
        "before_state_sha256":"d".repeat(64),"candidate_state_sha256":"e".repeat(64),"before_people_sha256":"f".repeat(64),
        "candidate_people_sha256":"1".repeat(64),"source_size":[2048,1024],"before_output_size":[2048,1024],"after_output_size":[2048,1024],
        "coverage_sha256":crate::batch_api::collarbone::request_digest(&coverage),"before":image,"after":image});
    json!({"protocol":1,"action":"preflight","request_id":"review-one","id":"preset-one","document_id":"load-one",
        "revision":"3","success":true,"outcome_unknown":false,"preflight_token":"f".repeat(32),"module_scope":[OP,"lnx.exposure.v1"],
        "applies":{(OP):{"version":1,"amount":30},"lnx.exposure.v1":{"exposure":0.25}},
        "source_proof":source,"collarbone_preset":{"version":1,"preset_sha256":"2".repeat(64),"applies_sha256":"3".repeat(64),
        "load_id":"load-one","owner":{"document":{"document_id":"logical-document","epoch":"workspace","revision":3},
        "people_scope":"logical-document","state_revision":4,"association_revision":2,"graph_sha256":"4".repeat(64),"source_proof":source},
        "face_ref":face,"coverage":coverage,"visual":visual}})
}
#[test] fn preset_ack_is_one_exact_object_not_batch_array(){
    assert!(command(&apply()).is_ok());let mut value=apply();value[ACK]=json!([ack()]);assert!(command(&value).is_err());
    value=apply();value.as_object_mut().unwrap().remove(ACK);value["collarbone_review_ack"]=json!([ack()]);assert!(command(&value).is_err());
}
#[test] fn logical_document_is_distinct_from_load_identity(){
    let value=review_fixture();assert!(review(&value));assert_ne!(value["document_id"],value["collarbone_preset"]["visual"]["document_id"]);
    let mut changed=value;changed["collarbone_preset"]["visual"]["document_id"]=json!("load-one");assert!(!review(&changed));
}
#[test] fn each_ack_hash_and_revision_required(){
    for key in ["document_id","revision","before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"] {
        let mut value=ack();value.as_object_mut().unwrap().remove(key);assert!(!acknowledgment(&value));
    }
    let mut value=ack();value["revision"]=json!("03");assert!(!acknowledgment(&value));
}
#[test] fn image_request_namespace_and_exact_coordinates(){
    assert!(read_only(&read()));assert!(command(&read()).is_ok());
    for key in ["path","modules","collarbone_preset_ack"]{let mut value=read();value[key]=json!("injected");assert!(!read_only(&value));assert!(command(&value).is_err());}
    let mut value=read();value["cmd"]=json!("batch");assert!(!read_only(&value));assert!(binding(&value).unwrap().is_none());
}
#[test] fn preflight_read_only_is_narrow_and_apply_is_never_exempt(){
    assert!(read_only(&preflight()));assert!(!read_only(&apply()));
    for key in ["force","preflight_token","collarbone_preset_ack"]{let mut value=preflight();value[key]=json!(true);assert!(!read_only(&value));}
    let mut value=preflight();value["module_scope"]=json!(["lnx.exposure.v1"]);assert!(!read_only(&value));
}
#[test] fn bindings_retain_preset_load_token_and_other_valid_acknowledgments(){
    let mut value=apply();value["spill_review_ack"]=json!([{"document_id":"load-one","revision":"3","before_sha256":"a".repeat(64),"after_sha256":"b".repeat(64)}]);
    assert!(command(&value).is_ok());let bound=binding(&value).unwrap().unwrap();
    for key in ["id","document_id","preflight_token",ACK,"spill_review_ack"]{assert_eq!(bound[key],value[key]);}
    let bound=binding(&read()).unwrap().unwrap();for key in ["id","document_id","preflight_token","revision","side","sha256"]{assert_eq!(bound[key],read()[key]);}
}
#[test] fn full_preset_review_requires_exact_owner_coverage_and_image_metadata(){
    let value=review_fixture();assert!(receipt(&value));
    for path in ["preset_sha256","applies_sha256","load_id","owner","face_ref","coverage","visual"] {
        let mut changed=value.clone();changed["collarbone_preset"].as_object_mut().unwrap().remove(path);assert!(!review(&changed));
    }
    let mut changed=value.clone();changed["collarbone_preset"]["coverage"]["targets"][0]["clavicle_category"]=json!("elder_female");assert!(!review(&changed));
    let mut changed=value;changed["collarbone_preset"]["visual"]["after"]["width"]=json!(256);assert!(!review(&changed));
}
#[test] fn unknown_apply_retains_required_scope_and_ack(){
    let mut value=json!({"action":"apply","success":false,"outcome_unknown":true,"module_scope":[OP],"preflight_token":"f".repeat(32),(ACK):ack()});
    assert!(receipt(&value));value.as_object_mut().unwrap().remove(ACK);assert!(!receipt(&value));
    value[ACK]=ack();value.as_object_mut().unwrap().remove("module_scope");assert!(!receipt(&value));
}
#[test] fn unrelated_preset_cannot_smuggle_visual_or_ack(){
    let mut value=review_fixture();value["module_scope"]=json!(["lnx.exposure.v1"]);assert!(!receipt(&value));
    let mut value=apply();value["action"]=json!("save");assert!(command(&value).is_err());
}
#[test] fn zero_coverage_keeps_null_category_and_no_borrowed_side(){
    let mut value=review_fixture();let face=value["collarbone_preset"]["face_ref"].clone();
    value["collarbone_preset"]["coverage"]["targets"][0]=json!({"face_ref":face,"scope":"neutral-no-effect","body_review_sha256":null,"clavicle_category":null,"clavicle_sides":[]});
    value["collarbone_preset"]["visual"]["coverage_sha256"]=json!(crate::batch_api::collarbone::request_digest(&value["collarbone_preset"]["coverage"]));
    assert!(review(&value));value["collarbone_preset"]["coverage"]["targets"][0]["clavicle_sides"]=json!(["left"]);assert!(!review(&value));
}
#[test] fn mismatched_preset_preflight_receipt_preserves_original_binding(){
    let epoch=[173;16];let mut host=crate::preset_host::PresetHost::default();host.reset(epoch);host.ready(epoch,true);
    host.begin_command(epoch,&preflight()).unwrap();let mut reply=review_fixture();reply["id"]=json!("other-preset");
    host.receive(epoch,&reply);let terminal=host.status("review-one");let result=&terminal["result"];
    assert_eq!(result["outcome_unknown"],true);assert_eq!(result["id"],"preset-one");
    assert_eq!(result["document_id"],"load-one");assert_eq!(result["module_scope"],preflight()["module_scope"]);
}
#[test] fn image_reads_do_not_create_edit_fences_or_replace_an_existing_write(){
    let epoch=[174;16];crate::project_recovery_fence::issued(epoch,&read()).unwrap();
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    let write=apply();crate::project_recovery_fence::issued(epoch,&write).unwrap();
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    let mut collision=read();collision["request_id"]=write["request_id"].clone();
    assert!(crate::project_recovery_fence::issued(epoch,&collision).is_err());
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
}
