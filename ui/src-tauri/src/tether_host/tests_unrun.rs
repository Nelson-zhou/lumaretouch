//! Authored source fixtures only: UNRUN. No driver load, camera, project import,
//! filesystem mutation, thread startup or application execution occurs here.
use super::wire::{self, Action, Naming, Request};
use serde_json::json;

fn naming(mode: &str) -> Naming {
    Naming { mode:mode.into(),custom_name:"春日 人像".into(),counter_start:12 }
}
fn stop_request() -> serde_json::Value {
    json!({"protocol_version":1,"host_id":"host","request_id":"request-1","action":"stop",
        "expected_revision":8,"expected_session_id":"session-1","expected_generation":2})
}
#[test]
fn exact_safe_unicode_names_preserve_extension_and_pattern() {
    assert_eq!(wire::local_name(&naming("custom_counter"),"原片 甲.CR3","20261025",0).unwrap(),"春日 人像-000012.CR3");
    assert_eq!(wire::local_name(&naming("custom_filename"),"原片 甲.CR3","20261025",0).unwrap(),"春日 人像-原片 甲.CR3");
    assert_eq!(wire::local_name(&naming("date_counter"),"原片 甲.CR3","20261025",1).unwrap(),"20261025-000013.CR3");
    assert_eq!(wire::local_name(&naming("date_filename"),"原片 甲.CR3","20261025",0).unwrap(),"20261025-原片 甲.CR3");
    assert_eq!(wire::local_name(&naming("original"),"原片 甲.CR3","20261025",0).unwrap(),"原片 甲.CR3");
}
#[test]
fn unsafe_or_oversized_names_are_rejected_not_sanitized() {
    for value in ["../原片.jpg","a/b.jpg","a\\b.jpg","CON.jpg","LPT9.raw","尾部.","尾部 ","\0.jpg","..",""] {
        assert!(wire::component(value).is_err(),"{value:?}");
    }
    assert!(wire::component(&"甲".repeat(86)).is_err());
    let mut long = naming("custom_filename"); long.custom_name = "甲".repeat(80);
    assert!(wire::local_name(&long,"较长的原片.CR3","20261025",0).is_err());
}
#[test]
fn counter_allocation_never_wraps_or_silently_changes_format() {
    let mut last = naming("custom_counter"); last.counter_start = 999_999_999;
    assert!(wire::local_name(&last,"a.JPG","20261025",1).is_err());
    assert_eq!(wire::format("real.CR3"),"raw");
    assert_eq!(wire::format("real.JPEG"),"jpeg");
    assert_eq!(wire::format("movie.MOV"),"other");
    assert_eq!(wire::format("not-a-name"),"other");
}
#[test]
fn envelopes_reject_extra_fields_and_missing_null_identity() {
    assert!(Request::parse(stop_request()).is_ok());
    let mut extra = stop_request(); extra["camera_path"] = json!("/DCIM/a.jpg");
    assert!(Request::parse(extra).is_err());
    let mut missing = stop_request(); missing.as_object_mut().unwrap().remove("expected_generation");
    assert!(Request::parse(missing).is_err());
}
#[test]
fn request_private_binding_never_enters_public_abi() {
    let mut request = Request::parse(stop_request()).unwrap();
    request.admitted_binding = Some(json!({"workspace":"private","disk_sha256":"private"}));
    assert_eq!(serde_json::to_value(&request).unwrap(),stop_request());
    assert!(matches!(request.action, Action::Stop));
}
#[test]
fn unknown_receipt_is_pending_and_never_invents_success() {
    let request = Request::parse(stop_request()).unwrap();
    let receipt = request.receipt(false,true,false,Some("unknown"));
    assert_eq!(receipt["phase"],"pending");
    assert_eq!(receipt["outcome_unknown"],true);
    assert!(receipt.get("success").is_none());
    assert_eq!(receipt["expected_session_id"],"session-1");
    assert_eq!(receipt["expected_generation"],2);
}
#[test]
fn jpeg_preview_dimensions_come_from_bounded_actual_bytes() {
    let bytes = [0xff,0xd8,0xff,0xc0,0,11,8,0,32,0,48,1,1,0x11,0,0xff,0xd9];
    assert_eq!(wire::jpeg_dimensions(&bytes),Some((48,32)));
    assert_eq!(wire::jpeg_dimensions(&bytes[..8]),None);
    assert_eq!(wire::jpeg_dimensions(b"pretend jpeg"),None);
    let mut oversized = bytes; oversized[9] = 0xff;
    assert_eq!(wire::jpeg_dimensions(&oversized),None);
}
#[test]
fn deterministic_import_and_managed_names_are_distinct_roles() {
    let session = "6ba7b810-9dad-11d1-80b4-00c04fd430c8";
    let request = "e902893a-9d22-41f0-9901-3826a1b4dd25";
    let operation = crate::ingest_receipt_validation::operation_id(session,request).unwrap();
    let target = crate::ingest_receipt_validation::uuid_v5(&operation,"/private/occurrence-1/原片.CR3").unwrap();
    assert_ne!(operation,target);
    assert_ne!(operation,request);
    assert!(crate::ingest_receipt_validation::operation_id(session,"non-uuid").is_err());
}
