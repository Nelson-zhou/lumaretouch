//! AUTHORED / UNRUN. Transport fixtures, not solver, decoder or product acceptance.
use super::*;
use crate::receipt_host::{ReceiptHost, ReceiptKind};
fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "action":action, "request_id":"style-fixture", "document_id":"doc", "document_epoch":"epoch",
        "document_revision":4, "state_revision":3, "association_revision":2,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":1}}, "payload":payload})
}
fn confirmation() -> Value {
    request("face_style_confirm", json!({"token":"b".repeat(32),"ack":{"review_sha256":"c".repeat(64),
        "before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64)}}))
}
#[test] fn exact_single_face_and_bounded_recipe_are_required() {
    let good = request("face_style_preview", json!({"version":1,"style":"classic","amount":0.5}));
    assert!(command(&good).is_ok()); assert!(read_only(&good));
    for (path, bad) in [("/target/scope",json!("person")), ("/payload/version",json!(2)),
        ("/payload/style",json!("unknown")), ("/payload/amount",json!(-0.01)),
        ("/payload/amount",json!(1.01)), ("/payload/amount",json!(true)), ("/target/face_ref/analysis_revision",json!(-1))] {
        let mut v=good.clone(); *v.pointer_mut(path).unwrap()=bad;
        assert!(command(&v).is_err(), "{path}"); assert!(!read_only(&v));
    }
    let mut extra=good.clone(); extra["payload"]["commit"]=json!(true); assert!(command(&extra).is_err());
    assert!(!read_only(&confirmation()));
}
struct Kind;
impl ReceiptKind for Kind {
    const NAME: &'static str="people";
    const ACTIONS: &'static [&'static str]=&["face_style_confirm", "face_style_catalog"];
    fn valid(v:&Value,_:Option<&str>)->bool { v["success"].is_boolean() && v["outcome_unknown"].is_boolean() }
}
fn host()->ReceiptHost<Kind>{let mut h=ReceiptHost::default();h.reset([217;16]);h.ready([217;16],true);h}
fn result(c:&Value)->Value {
    json!({"request_id":c["request_id"],"action":c["action"],"success":true,"outcome_unknown":false,
        "face_style_request":binding(c).unwrap().unwrap()["face_style_request"]})
}
#[test] fn altered_review_or_context_is_unknown_and_preserves_original_identity() {
    let c=confirmation();
    for path in ["/face_style_request/payload/token", "/face_style_request/payload/ack/review_sha256",
        "/face_style_request/payload/ack/before_sha256", "/face_style_request/document_epoch", "/face_style_request/target/target_id"] {
        let mut h=host();h.begin_command([217;16],&c).unwrap();
        let mut v=result(&c); *v.pointer_mut(path).unwrap()=json!("substituted"); h.receive([217;16],&v);
        let retained=h.status("style-fixture")["result"].clone(); assert_eq!(retained["outcome_unknown"],true);
        assert_eq!(retained["face_style_request"],result(&c)["face_style_request"]);
        assert!(h.guards_review([217;16],"style-fixture"));
        h.receive([217;16],&result(&c)); assert_eq!(h.status("style-fixture")["result"],retained);
    }
}
#[test] fn readonly_never_erases_an_existing_mutation_fence() {
    let epoch=[216;16]; let c=confirmation(); crate::project_recovery_fence::issued(epoch,&c).unwrap();
    let read=request("face_style_catalog",json!({}));
    assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"people_result","action":"face_style_catalog",
        "request_id":"style-fixture","success":true,"outcome_unknown":false}));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch,&read).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn single_image_requires_canonical_png_and_exact_digest() {
    let v=json!({"mime":"image/png","width":1,"height":1,"sha256":"a".repeat(64),"base64":"AAAA"});
    assert!(!image(&v));
    let mut oversized=v.clone();oversized["width"]=json!(1025);assert!(!image(&oversized));
    let mut paired=v;paired["after"]=json!({});assert!(!image(&paired));
}
#[test] fn error_receipt_still_requires_exact_echo_and_context() {
    let c=confirmation();let mut v=result(&c);v["document_id"]=json!("doc"); v["success"]=json!(false);v["error"]=json!("Rejected");
    assert!(receipt(&v));v.as_object_mut().unwrap().remove("face_style_request");assert!(!receipt(&v));
}
fn frozen_review() -> (Value, Value) {
    let c=request("face_style_preview",json!({"version":1,"style":"classic","amount":0.5}));
    let source=json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let owner=json!({"document":{"document_id":"doc","epoch":"epoch","revision":4},"people_scope":"project",
        "state_revision":3,"association_revision":2,"graph_sha256":"1".repeat(64),"source_proof":source});
    let png=json!({"mime":"image/png","width":1024,"height":512,"sha256":"2".repeat(64)});
    let visual=json!({"version":1,"document_id":"doc","revision":"4","source_proof":source,
        "before_state_sha256":"3".repeat(64),"candidate_state_sha256":"4".repeat(64),
        "before_people_sha256":"5".repeat(64),"candidate_people_sha256":"6".repeat(64),
        "source_size":[2048,1024],"before_output_size":[2048,1024],"after_output_size":[2048,1024],"before":png,"after":png});
    let review=json!({"version":1,"token":"7".repeat(32),"recipe":c["payload"],"owner":owner,
        "face_ref":c["target"]["face_ref"],"patches_sha256":"8".repeat(64),"visual":visual,"review_sha256":"9".repeat(64)});
    (c,review)
}
#[test] fn frozen_visual_is_face_and_source_bound_without_borrowed_body_support() {
    let (c,v)=frozen_review(); assert!(review(&v,&c));
    for (path,bad) in [("/owner/document/epoch",json!("other")),("/owner/state_revision",json!(4)),
        ("/face_ref/face_instance_id",json!("other")),("/owner/source_proof/asset_sha256",json!("b".repeat(64))),
        ("/visual/revision",json!(4)),("/visual/before/width",json!(1023)),("/visual/after/height",json!(513))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!review(&changed,&c),"{path}");
    }
    let mut borrowed=v.clone();borrowed["visual"]["coverage_sha256"]=json!("a".repeat(64));assert!(!review(&borrowed,&c));
    let mut inline=v.clone();inline["visual"]["before"]["base64"]=json!("AAAA");assert!(!review(&inline,&c));
    // Owner graph and render people-context fingerprints intentionally differ.
    assert_ne!(v["owner"]["graph_sha256"],v["visual"]["before_people_sha256"]);
}
