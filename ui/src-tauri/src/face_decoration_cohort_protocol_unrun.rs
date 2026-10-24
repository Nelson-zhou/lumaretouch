// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Exact cohort identity fixtures, no render acceptance.
use super::*;
fn acknowledgment()->Value {json!([
    {"document_id":"a".repeat(32),"revision":"7","before_sha256":"b".repeat(64),"after_sha256":"c".repeat(64),"coverage_sha256":"d".repeat(64)},
    {"document_id":"e".repeat(32),"revision":"9","before_sha256":"f".repeat(64),"after_sha256":"1".repeat(64),"coverage_sha256":"2".repeat(64)}])}
#[test] fn exact_unlink_scope_and_all_member_ack_are_required() {
    let mut c=json!({"cmd":"batch","action":"commit","request_id":"cohort-fixture","preflight_token":"a".repeat(32),"module_scope":[],(ACK):acknowledgment()});
    assert!(command(&c).is_ok());assert!(!read_only(&c));
    c[ACK].as_array_mut().unwrap().pop();assert!(command(&c).is_err());
}
#[test] fn automatic_marker_cannot_be_requested_or_wrong_family_mixed() {
    let c=json!({"cmd":"batch","action":"preflight",(KEY):true});assert!(command(&c).is_err());
    let c=json!({"cmd":"batch","action":"commit","request_id":"cohort-fixture","preflight_token":"a".repeat(32),"module_scope":[],(ACK):acknowledgment(),"face_decoration_review_ack":acknowledgment()});
    assert!(command(&c).is_err());
}
#[test] fn image_identity_is_read_only_and_rejects_extra_write_field() {
    let mut c=json!({"cmd":"batch","action":IMAGE,"request_id":"image-fixture","preflight_token":"a".repeat(32),"document_id":"b".repeat(32),"revision":"7","side":"after","sha256":"c".repeat(64)});
    assert!(read_only(&c));c["module_scope"]=json!([]);assert!(!read_only(&c));assert!(command(&c).is_err());
}
