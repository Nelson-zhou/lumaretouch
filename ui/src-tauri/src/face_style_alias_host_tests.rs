//! AUTHORED / UNRUN. Native alias receipt fencing, not engine/render acceptance.
use super::*;

fn command() -> Value {
    json!({"cmd":"people","request_id":"alias-confirm","action":"face_style_confirm",
        "document_id":"current","document_epoch":"epoch","document_revision":4,
        "state_revision":3,"association_revision":2,"target":{"scope":"face","target_id":"face",
            "face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":1}},
        "payload":{"token":"b".repeat(32),"ack":{"review_sha256":"c".repeat(64),"members":[
            {"document_id":"current","revision":"4","before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64)},
            {"document_id":"alias","revision":"9","before_sha256":"f".repeat(64),"after_sha256":"1".repeat(64)}]}}})
}
fn result(c: &Value) -> Value {
    json!({"protocol":1,"request_id":c["request_id"],"action":c["action"],"document_id":c["document_id"],
        "success":true,"outcome_unknown":false,"batch_id":"batch-001-1234",
        "face_style_request":face_style::binding(c).unwrap().unwrap()["face_style_request"],
        "payload":{"kind":"face_style_confirm","token":c["payload"]["token"],"review_sha256":"c".repeat(64),
            "ack":c["payload"]["ack"],"recipe":{"version":1,"style":"classic","amount":0.5},
            "patches_sha256":"2".repeat(64),"alias_members":[
                {"document_id":"current","expected_revision":"4","result_revision":"5"},
                {"document_id":"alias","expected_revision":"9","result_revision":"10"}]},
        "doc_state":{"people":{"binding":{"document_id":"current","document_epoch":"epoch",
            "document_revision":5,"asset_sha256":"a".repeat(64)},"revision":33,"association_revision":2}}})
}
fn host() -> ReceiptHost<PeopleKind> {
    let mut host = ReceiptHost::default(); host.reset([218;16]); host.ready([218;16],true); host
}
#[test] fn alias_success_needs_exact_current_graph_and_document_advances() {
    let c = command(); let v = result(&c); assert!(PeopleKind::valid(&v,Some("current")));
    for (path, bad) in [("/doc_state/people/binding/document_revision",json!(4)),
        ("/doc_state/people/binding/document_revision",json!(6)),("/doc_state/people/revision",json!(3)),
        ("/doc_state/people/revision",json!(4)),("/doc_state/people/revision",json!(34)),("/doc_state/people/association_revision",json!(3)),
        ("/doc_state/people/binding/document_epoch",json!("other")),("/batch_id",Value::Null)] {
        let mut changed = v.clone(); *changed.pointer_mut(path).unwrap() = bad;
        assert!(!PeopleKind::valid(&changed,Some("current")),"{path}");
        let mut host = host(); host.begin_command([218;16],&c).unwrap(); host.receive([218;16],&changed);
        let retained = host.status("alias-confirm")["result"].clone(); assert_eq!(retained["outcome_unknown"],true);
        assert_eq!(retained["face_style_request"],v["face_style_request"]);
        host.receive([218;16],&v); assert_eq!(host.status("alias-confirm")["result"],retained);
    }
}
#[test] fn alias_known_refusal_and_unknown_both_keep_the_full_acknowledgment() {
    let c = command(); let original = result(&c);
    for unknown in [false,true] {
        let mut v = original.clone(); v["success"] = json!(false); v["outcome_unknown"] = json!(unknown);
        v["error"] = json!(if unknown {"Publication failed after it started"} else {"Canonical candidate is unchanged"});
        v.as_object_mut().unwrap().remove("payload"); v.as_object_mut().unwrap().remove("batch_id");
        assert!(PeopleKind::valid(&v,Some("current")));
        let mut host = host(); host.begin_command([218;16],&c).unwrap(); host.receive([218;16],&v);
        let retained = host.status("alias-confirm")["result"].clone();
        assert_eq!(retained["success"],false); assert_eq!(retained["outcome_unknown"],unknown);
        assert_eq!(retained["face_style_request"],original["face_style_request"]);
    }
}
#[test] fn legacy_v1_local_confirmation_keeps_its_previous_revision_contract() {
    let mut c = command(); c["payload"]["ack"] = json!({"review_sha256":"c".repeat(64),
        "before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64)});
    let mut v = result(&c); v["payload"].as_object_mut().unwrap().remove("alias_members");
    v["batch_id"] = Value::Null;
    for (document_revision, state_revision) in [(4,3),(5,4),(7,9)] {
        v["doc_state"]["people"]["binding"]["document_revision"] = json!(document_revision);
        v["doc_state"]["people"]["revision"] = json!(state_revision);
        assert!(PeopleKind::valid(&v,Some("current")));
    }
}
#[test] fn alias_known_refusal_cannot_claim_a_batch_but_can_retain_prepared_proof() {
    let c = command(); let mut v = result(&c);
    v["success"] = json!(false); v["error"] = json!("Preparation failed before publication");
    v["batch_id"] = Value::Null;
    // The prepared payload, including alias_members, does not prove a write.
    assert!(PeopleKind::valid(&v,Some("current")));
    v["batch_id"] = json!("batch-001-1234"); assert!(!PeopleKind::valid(&v,Some("current")));
    let mut h = host(); h.begin_command([218;16],&c).unwrap(); h.receive([218;16],&v);
    let retained = h.status("alias-confirm")["result"].clone(); assert_eq!(retained["outcome_unknown"],true);
    assert_eq!(retained["face_style_request"],v["face_style_request"]); assert!(retained.get("batch_id").is_none());
    // A post-publication failure can carry a batch identity, but stays unknown.
    v["outcome_unknown"] = json!(true); assert!(PeopleKind::valid(&v,Some("current")));
    let mut h = host(); h.begin_command([218;16],&c).unwrap(); h.receive([218;16],&v);
    assert_eq!(h.status("alias-confirm")["result"]["outcome_unknown"],true);
}
