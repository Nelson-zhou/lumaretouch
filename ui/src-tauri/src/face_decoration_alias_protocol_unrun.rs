// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Protocol fixtures, not rendering or quality acceptance.
use super::*;
fn request(action:&str,payload:Value)->Value {
    json!({"cmd":"people","request_id":"alias-fixture","action":action,"payload":payload,
        "document_id":"doc","document_epoch":"epoch","document_revision":7,"state_revision":11,"association_revision":3,
        "target":{"scope":"face","target_id":"face","face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":2}}})
}
fn acknowledgment()->Value {json!({"review_sha256":"b".repeat(64),"members":[
    {"document_id":"doc","revision":"7","before_sha256":"c".repeat(64),"after_sha256":"d".repeat(64)},
    {"document_id":"sibling","revision":"9","before_sha256":"e".repeat(64),"after_sha256":"f".repeat(64)}]})}
#[test] fn scalar_preview_is_read_only_but_confirmation_never_is() {
    let c=request("face_decoration_alias_preview",json!({"recipe":{"version":1,"pattern":"freckle_dust","strength":0.6}}));
    assert!(read_only(&c));assert!(binding(&c).unwrap().is_some());
    let commit=request("face_decoration_alias_confirm",json!({"token":"a".repeat(32),"ack":acknowledgment()}));
    assert!(command(&commit).is_ok());assert!(!read_only(&commit));assert!(applies(&commit));
}
#[test] fn missing_or_duplicate_sibling_and_wrong_source_revision_refused() {
    let mut a=acknowledgment();a["members"].as_array_mut().unwrap().pop();assert!(!ack(&a));
    let mut a=acknowledgment();a["members"][1]=a["members"][0].clone();assert!(!ack(&a));
    let mut a=acknowledgment();a["members"][0]["revision"]=json!("8");
    assert!(command(&request("face_decoration_alias_confirm",json!({"token":"a".repeat(32),"ack":a}))).is_err());
}
#[test] fn old_report_compatible_new_metadata_cannot_be_incomplete() {
    assert!(report_metadata(&json!({})));assert!(!report_metadata(&json!({"alias_required":true})));
    assert!(report_metadata(&json!({"alias_required":false,"alias_member_count":0,"alias_reason":null,"alias_review":null})));
}
#[test] fn no_donor_support_in_preview() {
    let mut c=request("face_decoration_alias_preview",json!({"recipe":{"version":1,"pattern":"mole_pair","strength":0.4}}));
    c["payload"]["mask"]=json!({});assert!(command(&c).is_err());
}
#[test] fn unknown_shared_write_blocks_unrelated_edits_until_verified_reopen() {
    let epoch=[174;16];let c=request("face_decoration_alias_confirm",json!({"token":"a".repeat(32),"ack":acknowledgment()}));
    crate::project_recovery_fence::issued(epoch,&c).unwrap();
    let mut failure=json!({"event":"people_result","protocol":1,"action":c["action"],"request_id":c["request_id"],"document_id":"doc","success":false,"outcome_unknown":true,"error":"outcome not established"});
    failure[REQUEST]=binding(&c).unwrap().unwrap()[REQUEST].clone();
    crate::project_recovery_fence::observed(epoch,&failure);
    assert!(crate::project_recovery_fence::issued(epoch,&json!({"cmd":"exposure","request_id":"other"})).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened","open":true,"path":"/fixture/project","project_id":"project","docs":2,"dirty":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
