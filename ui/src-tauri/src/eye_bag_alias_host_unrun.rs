// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Correlated native alias receipts and cancellation boundaries.
use super::*;
fn command() -> Value {
    json!({"cmd":"people","request_id":"eye-alias-confirm","action":"eye_bag_confirm",
        "document_id":"current","document_epoch":"epoch","document_revision":7,
        "state_revision":11,"association_revision":3,"target":{"scope":"face","target_id":"face",
            "face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":2}},
        "payload":{"token":"b".repeat(32),"ack":{"review_sha256":"c".repeat(64),"support_overlay_sha256":"d".repeat(64),
            "members":[{"document_id":"current","revision":"7","before_sha256":"e".repeat(64),"after_sha256":"f".repeat(64)},
                {"document_id":"alias","revision":"9","before_sha256":"1".repeat(64),"after_sha256":"2".repeat(64)}]}}})
}
fn result(c: &Value) -> Value {
    let recipe = json!({"version":2,"amount":0.5,"preserve":1});
    json!({"event":"people_result","protocol":1,"request_id":c["request_id"],"action":c["action"],"document_id":c["document_id"],
        "success":true,"outcome_unknown":false,"batch_id":"batch-eye-alias",
        "eye_bag_request":eye_bag::binding(c).unwrap().unwrap()["eye_bag_request"],
        "payload":{"kind":"eye_bag_confirm","token":c["payload"]["token"],"review_sha256":"c".repeat(64),
            "ack":c["payload"]["ack"],"recipe":recipe,"support_sha256":"3".repeat(64),"replace_legacy":false,
            "candidate_state_revision":14,"alias_members":[
                {"document_id":"current","expected_revision":"7","result_revision":"8"},
                {"document_id":"alias","expected_revision":"9","result_revision":"10"}]},
        "doc_state":{"people":{"binding":{"document_id":"current","document_epoch":"epoch","document_revision":8,"asset_sha256":"a".repeat(64)},
            "revision":14,"association_revision":3,"eye_bag_preserve":{"recipe":recipe,"face_ref":c["target"]["face_ref"],
                "support_sha256":"3".repeat(64),"legacy_amount":0},
            "resolved":{"face_ref":c["target"]["face_ref"],"state_revision":14,"association_revision":3,"operations":{
                "lnx.eye_bags.v2":{"/amount":{"value":0.5},"/preserve":{"value":1}},"lnx.enhance.v1":{"/eye_bags":{"value":0}}}}}}})
}
fn host(epoch: [u8;16]) -> ReceiptHost<PeopleKind> {
    let mut h = ReceiptHost::default(); h.reset(epoch); h.ready(epoch, true); h
}
#[test] fn exact_alias_success_requires_full_publication_and_current_readback() {
    let c = command(); let v = result(&c); assert!(PeopleKind::valid(&v, Some("current")));
    let mut h = host([219;16]); h.begin_command([219;16], &c).unwrap(); h.receive([219;16], &v);
    assert_eq!(h.status("eye-alias-confirm")["result"], v); assert!(eye_read_request(&h, "eye-alias-confirm").is_err());
    for (path, replacement) in [("/doc_state/people/binding/document_revision",json!(7)),
        ("/doc_state/people/revision",json!(15)),("/doc_state/people/association_revision",json!(4)),
        ("/doc_state/people/eye_bag_preserve/support_sha256",json!("4".repeat(64))),
        ("/doc_state/people/resolved/operations/lnx.eye_bags.v2/~1amount/value",json!(0.2)),
        ("/payload/alias_members/1/result_revision",json!("11")),("/batch_id",Value::Null)] {
        let mut bad = v.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!PeopleKind::valid(&bad, Some("current")), "{path}");
        let mut h = host([220;16]); h.begin_command([220;16], &c).unwrap(); h.receive([220;16], &bad);
        let retained = h.status("eye-alias-confirm"); assert_eq!(retained["result"]["outcome_unknown"], true);
        assert_eq!(retained["result"]["eye_bag_request"], v["eye_bag_request"]);
        h.receive([220;16], &v); assert_eq!(h.status("eye-alias-confirm"), retained);
    }
}
#[test] fn callback_cannot_rebind_member_order_or_shared_support_after_dispatch() {
    let c = command(); let v = result(&c);
    let mut substituted = c.clone(); substituted["payload"]["ack"]["members"][1]["before_sha256"] = json!("9".repeat(64));
    let bad = result(&substituted); assert!(PeopleKind::valid(&bad, Some("current")));
    let mut h = host([221;16]); h.begin_command([221;16], &c).unwrap(); h.receive([221;16], &bad);
    assert_eq!(h.status("eye-alias-confirm")["result"]["outcome_unknown"], true);
    assert_eq!(h.status("eye-alias-confirm")["result"]["eye_bag_request"], v["eye_bag_request"]);
    let mut substituted = c.clone(); substituted["payload"]["ack"]["support_overlay_sha256"] = json!("9".repeat(64));
    let mut h = host([222;16]); h.begin_command([222;16], &c).unwrap(); h.receive([222;16], &result(&substituted));
    assert_eq!(h.status("eye-alias-confirm")["result"]["outcome_unknown"], true);
    let mut three = c; three["payload"]["ack"]["members"].as_array_mut().unwrap().push(json!({"document_id":"alias-two",
        "revision":"12","before_sha256":"4".repeat(64),"after_sha256":"5".repeat(64)}));
    let mut reordered = result(&three);
    reordered["payload"]["alias_members"].as_array_mut().unwrap().push(json!({"document_id":"alias-two","expected_revision":"12","result_revision":"13"}));
    reordered["eye_bag_request"]["payload"]["ack"]["members"].as_array_mut().unwrap().swap(1, 2);
    reordered["payload"]["ack"]["members"].as_array_mut().unwrap().swap(1, 2);
    reordered["payload"]["alias_members"].as_array_mut().unwrap().swap(1, 2);
    assert!(PeopleKind::valid(&reordered, Some("current")));
    let mut h = host([228;16]); h.begin_command([228;16], &three).unwrap(); h.receive([228;16], &reordered);
    assert_eq!(h.status("eye-alias-confirm")["result"]["outcome_unknown"], true);
    assert_eq!(h.status("eye-alias-confirm")["result"]["eye_bag_request"]["payload"]["ack"], three["payload"]["ack"]);
}
#[test] fn unknown_alias_write_is_query_only_and_keeps_original_recovery_fence() {
    let epoch = [223;16]; let c = command(); let v = result(&c); let mut h = host(epoch);
    h.begin_command(epoch, &c).unwrap(); crate::project_recovery_fence::issued(epoch, &c).unwrap();
    h.failed("eye-alias-confirm", "Publication outcome unknown"); let retained = h.status("eye-alias-confirm");
    assert_eq!(retained["result"]["eye_bag_request"], v["eye_bag_request"]);
    assert!(eye_read_request(&h, "eye-alias-confirm").is_err()); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    h.receive(epoch, &v); assert_eq!(h.status("eye-alias-confirm"), retained);
    let mut c2 = c.clone(); c2["request_id"] = json!("do-not-reissue"); assert!(crate::project_recovery_fence::issued(epoch, &c2).is_err());
    let mut canceled = v; canceled["success"] = json!(false); canceled["eye_bag_cancelled"] = json!(true);
    canceled["error"] = json!("Cannot cancel a confirmation"); h.receive(epoch, &canceled); assert_eq!(h.status("eye-alias-confirm"), retained);
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
}
#[test] fn known_alias_refusal_needs_exact_original_identity_without_publication() {
    let c = command(); let mut v = result(&c); v["success"] = json!(false); v["error"] = json!("Alias membership changed before claim");
    for key in ["payload", "doc_state", "batch_id"] { v.as_object_mut().unwrap().remove(key); }
    assert!(PeopleKind::valid(&v, Some("current"))); let mut h = host([224;16]); h.begin_command([224;16], &c).unwrap();
    h.receive([224;16], &v); assert_eq!(h.status("eye-alias-confirm")["result"], v);
    let mut no_identity = v.clone(); no_identity.as_object_mut().unwrap().remove("eye_bag_request");
    let mut h = host([225;16]); h.begin_command([225;16], &c).unwrap(); h.receive([225;16], &no_identity);
    assert_eq!(h.status("eye-alias-confirm")["result"]["outcome_unknown"], true);
    v["batch_id"] = json!("batch-eye-alias"); assert!(!PeopleKind::valid(&v, Some("current")));
    v["outcome_unknown"] = json!(true); assert!(PeopleKind::valid(&v, Some("current")));
}
#[test] fn alias_image_cancellation_retains_member_identity_and_ignores_late_callbacks() {
    let mut c = command(); c["action"] = json!("eye_bag_image"); c["request_id"] = json!("eye-alias-image");
    c["payload"] = json!({"token":"b".repeat(32),"document_id":"alias","side":"after","sha256":"f".repeat(64)});
    let proof = eye_bag::binding(&c).unwrap().unwrap()["eye_bag_request"].clone();
    let v = json!({"event":"people_result","protocol":1,"request_id":c["request_id"],"action":c["action"],"document_id":"current",
        "success":false,"outcome_unknown":false,"error":"Read canceled","eye_bag_cancelled":true,"eye_bag_request":proof});
    let mut h = host([226;16]); h.begin_command([226;16], &c).unwrap(); h.failed("eye-alias-image", "Read transport unknown");
    assert_eq!(eye_read_request(&h, "eye-alias-image").unwrap(), proof);
    let unknown = h.status("eye-alias-image"); let mut bad = v.clone(); bad["eye_bag_request"]["payload"]["document_id"] = json!("current");
    h.receive([226;16], &bad); assert_eq!(h.status("eye-alias-image"), unknown);
    h.receive([227;16], &v); assert_eq!(h.status("eye-alias-image"), unknown);
    h.receive([226;16], &v); let done = h.status("eye-alias-image"); assert!(settled_read(&done));
    h.receive([226;16], &bad); assert_eq!(h.status("eye-alias-image"), done);
}
