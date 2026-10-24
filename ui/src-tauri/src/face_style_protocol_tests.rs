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

// AUTHORED / UNRUN. Same-owner alias transport only, not real rendered evidence.
fn alias_review() -> (Value, Value) {
    let (c, mut v) = frozen_review();
    let current = v["visual"].clone(); let mut other = current.clone();
    other["document_id"] = json!("alias"); other["revision"] = json!("9");
    // Identical source bytes can have independent crop/state/render fingerprints.
    other["before_output_size"] = json!([1024,1024]); other["after_output_size"] = json!([1024,1024]);
    other["before"]["height"] = json!(1024); other["after"]["height"] = json!(1024);
    other["before_state_sha256"] = json!("a".repeat(64)); other["candidate_state_sha256"] = json!("b".repeat(64));
    v["version"] = json!(2);
    v["members"] = json!([{"path":"/current.raw","visual":current},{"path":"/alias.raw","visual":other}]);
    (c, v)
}
fn alias_ack(v: &Value) -> Value {
    let members: Vec<Value> = v["members"].as_array().unwrap().iter().map(|member| {
        let visual = &member["visual"];
        json!({"document_id":visual["document_id"],"revision":visual["revision"],
            "before_sha256":visual["before"]["sha256"],"after_sha256":visual["after"]["sha256"]})
    }).collect();
    json!({"review_sha256":v["review_sha256"],"members":members})
}
fn alias_confirm() -> Value {
    let (_, review) = alias_review();
    request("face_style_confirm", json!({"token":review["token"],"ack":alias_ack(&review)}))
}
fn alias_result(c: &Value) -> Value {
    let mut result = result(c); result["document_id"] = c["document_id"].clone();
    result["batch_id"] = json!("batch-001-1234");
    result["payload"] = json!({"kind":"face_style_confirm","token":c["payload"]["token"],
        "review_sha256":c["payload"]["ack"]["review_sha256"],"ack":c["payload"]["ack"],
        "recipe":{"version":1,"style":"classic","amount":0.5},"patches_sha256":"8".repeat(64),
        "alias_members":[{"document_id":"doc","expected_revision":"4","result_revision":"5"},
            {"document_id":"alias","expected_revision":"9","result_revision":"10"}]});
    result
}
#[test] fn alias_review_preserves_v1_and_requires_every_source_bound_visual() {
    let (c, v) = alias_review(); assert!(review(&v, &c));
    let (old_command, old_review) = frozen_review(); assert!(review(&old_review, &old_command));
    for (path, bad) in [("/version",json!(1)),("/owner/people_scope",json!("doc")),("/members/0/visual/revision",json!("5")),
        ("/members/1/visual/document_id",json!("doc")),("/members/1/visual/revision",json!("09")),
        ("/members/1/visual/revision",json!("9007199254740992")),("/members/1/path",json!("bad\0path")),
        ("/members/1/visual/source_proof/asset_sha256",json!("b".repeat(64))),
        ("/members/1/visual/before/height",json!(1)),("/members/1/visual/before_people_sha256",Value::Null)] {
        let mut changed = v.clone(); *changed.pointer_mut(path).unwrap() = bad;
        assert!(!review(&changed, &c), "{path}");
    }
    let mut changed = v.clone(); changed["members"].as_array_mut().unwrap().reverse(); assert!(!review(&changed, &c));
    changed = v.clone(); changed["members"].as_array_mut().unwrap().pop(); assert!(!review(&changed, &c));
    changed = v.clone(); changed["members"][1]["visual"]["coverage_sha256"] = json!("a".repeat(64)); assert!(!review(&changed, &c));
    changed = v; changed["members"][1]["visual"]["before"]["base64"] = json!("AAAA"); assert!(!review(&changed, &c));
}
#[test] fn alias_ack_is_exact_ordered_bounded_and_starts_with_the_current_document() {
    let c = alias_confirm(); assert!(command(&c).is_ok()); assert!(!read_only(&c));
    for (path, bad) in [("/payload/ack/members/0/document_id",json!("other")),
        ("/payload/ack/members/0/revision",json!("5")),("/payload/ack/members/1/document_id",json!("doc")),
        ("/payload/ack/members/1/revision",json!(9)),("/payload/ack/members/1/revision",json!("09")),
        ("/payload/ack/members/1/before_sha256",Value::Null)] {
        let mut changed = c.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(command(&changed).is_err(), "{path}");
    }
    let mut changed = c.clone(); changed["payload"]["ack"]["before_sha256"] = json!("a".repeat(64)); assert!(command(&changed).is_err());
    changed = c.clone(); changed["payload"]["ack"]["members"].as_array_mut().unwrap().pop(); assert!(command(&changed).is_err());
    changed = c; let members = changed["payload"]["ack"]["members"].as_array_mut().unwrap();
    while members.len() < MAX_ALIAS_MEMBERS {
        let mut member = members[1].clone(); member["document_id"] = json!(format!("alias-{}", members.len())); members.push(member);
    }
    assert!(command(&changed).is_ok()); assert!(binding(&changed).unwrap().unwrap().to_string().len() < 16 * 1024);
    let mut extra = changed["payload"]["ack"]["members"][1].clone(); extra["document_id"] = json!("one-too-many");
    changed["payload"]["ack"]["members"].as_array_mut().unwrap().push(extra); assert!(command(&changed).is_err());
}
#[test] fn alias_confirmation_requires_the_real_batch_and_every_exact_revision_advance() {
    let c = alias_confirm(); let v = alias_result(&c); assert!(receipt(&v));
    for (path, bad) in [("/batch_id",Value::Null),("/batch_id",json!("")),("/batch_id",json!(" ")),
        ("/payload/alias_members/0/expected_revision",json!("3")),("/payload/alias_members/0/result_revision",json!("4")),
        ("/payload/alias_members/1/document_id",json!("doc")),("/payload/alias_members/1/result_revision",json!("11")),
        ("/payload/alias_members/1/result_revision",json!(10)),("/payload/alias_members/1/result_revision",json!("010"))] {
        let mut changed = v.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed), "{path}");
    }
    let mut changed = v.clone(); changed["payload"]["alias_members"].as_array_mut().unwrap().reverse(); assert!(!receipt(&changed));
    changed = v.clone(); changed["payload"]["alias_members"].as_array_mut().unwrap().pop(); assert!(!receipt(&changed));
    changed = v.clone(); changed["payload"]["alias_members"][1]["hidden"] = json!(true); assert!(!receipt(&changed));
    changed = v; changed["payload"].as_object_mut().unwrap().remove("alias_members"); assert!(!receipt(&changed));
}
#[test] fn alias_image_document_coordinate_is_bound_without_relaxing_the_old_envelope() {
    let old = request("face_style_image",json!({"token":"b".repeat(32),"side":"before","sha256":"a".repeat(64)}));
    assert!(command(&old).is_ok()); assert!(read_only(&old));
    let mut c = old; c["payload"]["document_id"] = json!("alias"); assert!(command(&c).is_ok()); assert!(read_only(&c));
    assert_eq!(binding(&c).unwrap().unwrap()["face_style_request"]["payload"]["document_id"],"alias");
    for bad in [Value::Null,json!(""),json!("x".repeat(129))] {
        let mut changed = c.clone(); changed["payload"]["document_id"] = bad; assert!(command(&changed).is_err());
    }
    c["payload"]["revision"] = json!("9"); assert!(command(&c).is_err());
}
#[test] fn alias_image_receipt_requires_its_document_echo_and_canonical_png_bytes() {
    let source = json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let pair = crate::original_shadow_transfer_protocol::tests::sample_transfer(&json!("alias"), &json!("9"), &json!({}), &source);
    let png = &pair["before"];
    let c = request("face_style_image", json!({"token":"b".repeat(32),"document_id":"alias","side":"before","sha256":png["sha256"]}));
    let v = json!({"document_id":"doc","action":"face_style_image","success":true,
        "face_style_request":binding(&c).unwrap().unwrap()["face_style_request"],
        "payload":{"kind":"face_style_image","token":"b".repeat(32),"document_id":"alias","side":"before",
            "sha256":png["sha256"],"review_sha256":"c".repeat(64),"image":png}});
    assert!(receipt(&v));
    for (path, bad) in [("/payload/document_id",json!("doc")),("/payload/image/base64",json!("AAAA")),
        ("/payload/image/sha256",json!("e".repeat(64))),("/payload/image/width",json!(1025))] {
        let mut changed = v.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
    }
    let mut changed = v.clone(); changed["payload"].as_object_mut().unwrap().remove("document_id"); assert!(!receipt(&changed));
    let mut legacy = v; legacy["face_style_request"]["payload"].as_object_mut().unwrap().remove("document_id");
    assert!(!receipt(&legacy)); legacy["payload"].as_object_mut().unwrap().remove("document_id"); assert!(receipt(&legacy));
}
#[test] fn ordered_alias_ack_and_unknown_outcomes_keep_the_original_mailbox_binding() {
    let c = alias_confirm(); let v = alias_result(&c);
    let mut h = host(); h.begin_command([217;16], &c).unwrap();
    let mut substituted = v.clone(); substituted["face_style_request"]["payload"]["ack"]["members"].as_array_mut().unwrap().reverse();
    h.receive([217;16], &substituted); let retained = h.status("style-fixture")["result"].clone();
    assert_eq!(retained["outcome_unknown"],true);
    assert_eq!(retained["face_style_request"],v["face_style_request"]);
    h.receive([217;16], &v); assert_eq!(h.status("style-fixture")["result"],retained);
    assert!(h.guards_review([217;16],"style-fixture"));
    let mut h = host(); h.begin_command([217;16], &c).unwrap();
    let mut unknown = v; unknown["success"] = json!(false); unknown["outcome_unknown"] = json!(true);
    unknown["error"] = json!("Publication state is uncertain"); h.receive([217;16], &unknown);
    let retained = h.status("style-fixture")["result"].clone(); assert_eq!(retained["outcome_unknown"],true);
    assert_eq!(retained["face_style_request"]["payload"]["ack"],c["payload"]["ack"]);
    assert!(retained.get("batch_id").is_none()); assert!(h.guards_review([217;16],"style-fixture"));
}
