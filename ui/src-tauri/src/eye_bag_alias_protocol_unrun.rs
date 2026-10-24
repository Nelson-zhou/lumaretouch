// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Protocol fixtures only, not render or photographic evidence.
use super::*;

fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people","action":action,"payload":payload,"request_id":"eye-alias",
        "document_id":"current","document_epoch":"epoch","document_revision":7,
        "state_revision":11,"association_revision":3,"target":{"scope":"face","target_id":"face",
            "face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":2}}})
}
fn painted() -> Value {
    json!({"left":{"visible":true,"unoccluded":true,"ownership_confirmed":true,
        "recipe":{"version":1,"domain":"source-normalized","objects":[{"id":"left-1","name":"Left ridge",
            "enabled":true,"operation":"add","kind":"brush","opacity":1,"feather":0,
            "points":[[0.5,0.55]],"axes":[[0.0015,0],[0,0.002]]}]}}})
}
fn preview() -> Value { request("eye_bag_preview", json!({"recipe":{"version":2,"amount":0.5,"preserve":1},
    "eyes":painted(),"replace_legacy":false})) }
fn visual(document: &str, revision: &str, width: u64, height: u64) -> Value {
    let image = json!({"mime":"image/png","width":width,"height":height,"sha256":"c".repeat(64)});
    json!({"version":1,"document_id":document,"revision":revision,
        "source_proof":{"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null},
        "before_state_sha256":"1".repeat(64),"candidate_state_sha256":"2".repeat(64),
        "before_people_sha256":"3".repeat(64),"candidate_people_sha256":"4".repeat(64),
        "source_size":[64,32],"before_output_size":[width,height],"after_output_size":[width,height],
        "before":image,"after":image})
}
fn review_fixture() -> Value {
    let c = preview(); let current = visual("current", "7", 64, 32); let other = visual("alias", "9", 32, 16);
    json!({"version":2,"token":"b".repeat(32),"recipe":c["payload"]["recipe"],
        "owner":{"document":{"document_id":"current","epoch":"epoch","revision":7},"people_scope":"project",
            "state_revision":11,"association_revision":3,"graph_sha256":"5".repeat(64),"source_proof":current["source_proof"]},
        "face_ref":c["target"]["face_ref"],"support_sha256":"6".repeat(64),"candidate_state_revision":14,"replace_legacy":false,
        "visual":current,"support_overlay":{"mime":"image/png","width":64,"height":32,"sha256":"7".repeat(64)},
        "support_source":{"source_width":64,"source_height":32,"decoded_width":64,"decoded_height":32},
        "review_sha256":"8".repeat(64),"members":[{"path":"/current.raw","visual":current},{"path":"/alias.raw","visual":other}]})
}
fn acknowledgment() -> Value {
    json!({"review_sha256":"8".repeat(64),"support_overlay_sha256":"7".repeat(64),"members":[
        {"document_id":"current","revision":"7","before_sha256":"c".repeat(64),"after_sha256":"d".repeat(64)},
        {"document_id":"alias","revision":"9","before_sha256":"e".repeat(64),"after_sha256":"f".repeat(64)}]})
}
fn confirmation() -> Value { request("eye_bag_confirm", json!({"token":"b".repeat(32),"ack":acknowledgment()})) }
fn result(c: &Value, payload: Value) -> Value {
    json!({"action":c["action"],"document_id":c["document_id"],"success":true,"outcome_unknown":false,
        "eye_bag_request":binding(c).unwrap().unwrap()["eye_bag_request"],"payload":payload})
}
fn confirmed(c: &Value) -> Value {
    let mut v = result(c, json!({"kind":"eye_bag_confirm","token":c["payload"]["token"],"review_sha256":"8".repeat(64),
        "ack":c["payload"]["ack"],"recipe":{"version":2,"amount":0.5,"preserve":1},"support_sha256":"6".repeat(64),
        "replace_legacy":false,"candidate_state_revision":14,"alias_members":[
            {"document_id":"current","expected_revision":"7","result_revision":"8"},
            {"document_id":"alias","expected_revision":"9","result_revision":"10"}]}));
    v["batch_id"] = json!("batch-eye-alias"); v
}
#[test] fn shared_source_alias_keeps_independent_crops_and_original_provenance() {
    let mut v = review_fixture(); assert!(review(&v, &binding(&preview()).unwrap().unwrap()["eye_bag_request"]));
    v["members"][1]["visual"]["source_proof"]["original_sha256"] = json!("9".repeat(64));
    v["members"][1]["visual"]["source_proof"]["creative_source"] = json!({"sha256":"a".repeat(64),"width":64,"height":32});
    assert!(review(&v, &binding(&preview()).unwrap().unwrap()["eye_bag_request"]));
    assert_ne!(v["members"][0]["visual"]["before_output_size"], v["members"][1]["visual"]["before_output_size"]);
    let mut legacy = review_fixture(); legacy["version"] = json!(1); legacy.as_object_mut().unwrap().remove("members");
    assert!(review(&legacy, &binding(&preview()).unwrap().unwrap()["eye_bag_request"]));
}
#[test] fn alias_review_refuses_partial_duplicate_substituted_and_donor_support_evidence() {
    let original = review_fixture(); let r = binding(&preview()).unwrap().unwrap()["eye_bag_request"].clone();
    for (path, replacement) in [("/version",json!(3)),("/owner/people_scope",json!("current")),
        ("/members/1/visual/document_id",json!("current")),("/members/1/visual/revision",json!("09")),
        ("/members/1/visual/source_proof/asset_sha256",json!("f".repeat(64))),
        ("/members/1/visual/source_size",json!([32,16])),("/members/1/visual/before/width",json!(64)),
        ("/members/1/visual/before_state_sha256",json!("bad")),("/support_source/source_width",json!(32)),
        ("/members/0/path",json!("")),("/face_ref/face_instance_id",json!("other"))] {
        let mut v = original.clone(); *v.pointer_mut(path).unwrap() = replacement; assert!(!review(&v, &r), "{path}");
    }
    for count in [0,1,17] { let mut v = original.clone(); v["members"] = json!(vec![v["members"][0].clone(); count]); assert!(!review(&v, &r)); }
    let mut v = original.clone(); v["members"].as_array_mut().unwrap().reverse(); assert!(!review(&v, &r));
    let mut v = original; v["members"][1]["support_overlay"] = v["support_overlay"].clone(); assert!(!review(&v, &r));
}
#[test] fn all_member_ack_is_ordered_bounded_and_has_one_authoritative_support_digest() {
    let c = confirmation(); assert!(command(&c).is_ok()); assert!(!read_only(&c));
    for (path, replacement) in [("/payload/ack/members/0/document_id",json!("alias")),
        ("/payload/ack/members/0/revision",json!("8")),("/payload/ack/members/1/document_id",json!("current")),
        ("/payload/ack/members/1/revision",json!("09")),("/payload/ack/members/1/revision",json!("9007199254740992")),
        ("/payload/ack/members/1/before_sha256",json!("bad")),("/payload/ack/support_overlay_sha256",json!("bad"))] {
        let mut bad = c.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(command(&bad).is_err(), "{path}");
    }
    let mut bad = c.clone(); bad["payload"]["ack"]["members"].as_array_mut().unwrap().reverse(); assert!(command(&bad).is_err());
    bad = c.clone(); bad["payload"]["ack"]["members"][1]["support_sha256"] = json!("f".repeat(64)); assert!(command(&bad).is_err());
    for count in [0,1,17] { let mut bad = c.clone(); bad["payload"]["ack"]["members"] = json!(vec![c["payload"]["ack"]["members"][0].clone(); count]); assert!(command(&bad).is_err()); }
}
#[test] fn sixteen_distinct_alias_members_are_bounded_without_dropping_any_member() {
    let mut v = review_fixture(); let mut c = confirmation();
    for n in 2..16 {
        v["members"].as_array_mut().unwrap().push(json!({"path":format!("/alias-{n}.raw"),"visual":visual(&format!("alias-{n}"), "9", 32, 16)}));
        c["payload"]["ack"]["members"].as_array_mut().unwrap().push(json!({"document_id":format!("alias-{n}"),
            "revision":"9","before_sha256":"e".repeat(64),"after_sha256":"f".repeat(64)}));
    }
    let r = binding(&preview()).unwrap().unwrap()["eye_bag_request"].clone();
    assert!(review(&v, &r)); assert!(command(&c).is_ok());
    v["members"].as_array_mut().unwrap().push(json!({"path":"/seventeenth.raw","visual":visual("seventeenth", "9", 32, 16)}));
    c["payload"]["ack"]["members"].as_array_mut().unwrap().push(json!({"document_id":"seventeenth",
        "revision":"9","before_sha256":"e".repeat(64),"after_sha256":"f".repeat(64)}));
    assert!(!review(&v, &r)); assert!(command(&c).is_err());
}
#[test] fn alias_images_are_exact_member_reads_and_support_is_current_source_only() {
    let image = super::tests::crop_png();
    for side in ["before","after","support"] {
        let c = request("eye_bag_image",json!({"token":"b".repeat(32),"document_id":"current","side":side,"sha256":image["sha256"]}));
        assert!(read_only(&c));
        let v = result(&c,json!({"kind":"eye_bag_image","token":"b".repeat(32),"document_id":"current","side":side,
            "sha256":image["sha256"],"review_sha256":"8".repeat(64),"image":image}));
        assert!(receipt(&v)); let mut bad = v.clone(); bad["payload"]["document_id"] = json!("alias"); assert!(!receipt(&bad));
        let mut other = c; other["payload"]["document_id"] = json!("alias"); assert_eq!(command(&other).is_ok(), side != "support");
    }
}
#[test] fn publication_requires_exact_ordered_member_advances_and_actual_batch_identity() {
    let c = confirmation(); let original = confirmed(&c); assert!(receipt(&original));
    for (path, replacement) in [("/batch_id",Value::Null),("/payload/alias_members/1/document_id",json!("other")),
        ("/payload/alias_members/1/expected_revision",json!("8")),("/payload/alias_members/1/result_revision",json!("11")),
        ("/payload/alias_members/1/result_revision",json!("010")),("/payload/ack/support_overlay_sha256",json!("9".repeat(64)))] {
        let mut bad = original.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
    }
    let mut bad = original.clone(); bad["payload"]["alias_members"].as_array_mut().unwrap().reverse(); assert!(!receipt(&bad));
    bad = original.clone(); bad["payload"]["alias_members"].as_array_mut().unwrap().pop(); assert!(!receipt(&bad));
    bad = original; bad["success"] = json!(false); bad["error"] = json!("Refused before publication"); assert!(!receipt(&bad));
    bad["batch_id"] = Value::Null; assert!(receipt(&bad)); bad["outcome_unknown"] = json!(true); bad["batch_id"] = json!("batch-eye-alias"); assert!(receipt(&bad));
}
