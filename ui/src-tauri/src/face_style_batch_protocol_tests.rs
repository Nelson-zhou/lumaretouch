//! AUTHORED / UNRUN. Native source fixtures, not runtime/render/browser acceptance.
use super::*;
use crate::receipt_host::ReceiptKind;

fn owner(id: char, asset: char) -> Value {
    json!({"document":{"document_id":id.to_string().repeat(32),"epoch":"workspace","revision":3},
        "people_scope":"project","state_revision":2,"association_revision":1,"graph_sha256":"e".repeat(64),
        "source_proof":{"asset_sha256":asset.to_string().repeat(64),"original_sha256":asset.to_string().repeat(64),"creative_source":null}})
}
fn face_ref(asset: char, id: &str) -> Value {
    json!({"asset_sha256":asset.to_string().repeat(64),"face_instance_id":id,"analysis_revision":1})
}
fn recipe_fixture() -> Value { json!({"version":1,"style":"classic","amount":0.5}) }
fn request_fixture() -> Value {
    let mut selection = json!({}); for (op, paths) in LEAVES { selection[*op] = json!(paths); }
    json!({"cmd":"batch","action":"preflight","request_id":"face-style-review","docs":["b".repeat(32)],
        "module_scope":OPS,"conflict_policy":"recheck","people_transfer":{"target_policy":"explicit_face_map",
        "source_ref":face_ref('c',"source-face"),"source":owner('a','c'),"selection":selection,
        "targets":[{"target":owner('b','d'),"target_refs":[face_ref('d',"target-face")]}],"face_style":recipe_fixture()}})
}
fn review_fixture() -> Value {
    let c = request_fixture(); let a = &c["people_transfer"]; let target = &a["targets"][0]["target"];
    let parameters: Vec<Value> = LEAVES.iter().flat_map(|(op, paths)| paths.iter().map(move |path|
        json!({"operation_id":op,"parameter_path":path,"value":if path.ends_with("/linked") {json!(true)}
            else {json!(coefficient("classic",op,path)*0.5)}}))).collect();
    let image = json!({"mime":"image/png","width":1024,"height":768,"sha256":"f".repeat(64)});
    let visual = json!({"version":1,"document_id":"b".repeat(32),"revision":"3","source_proof":target["source_proof"],
        "before_state_sha256":"1".repeat(64),"candidate_state_sha256":"2".repeat(64),
        "before_people_sha256":"3".repeat(64),"candidate_people_sha256":"4".repeat(64),
        "source_size":[4000,3000],"before_output_size":[4000,3000],"after_output_size":[4000,3000],
        "before":image,"after":image,"recipe_sha256":recipe_digest(&recipe_fixture()).unwrap()});
    let transfer = json!({"version":1,"source_document":a["source"]["document"],"target_document":target["document"],
        "source_ref":a["source_ref"],"target_refs":a["targets"][0]["target_refs"],"parameters":parameters,
        "source_state_revision":2,"target_state_revision":2,"source_association_revision":1,"target_association_revision":1,
        "transfer_policy":"selected_parameter_keys_replace","excluded":["local_assets","landmarks","masks","identity_links"],
        "source_owner":a["source"],"target_owner":target,"target_policy":"explicit_face_map",
        "face_style":recipe_fixture(),"face_style_visual":visual});
    json!({"event":"batch_result","action":"preflight","request_id":c["request_id"],"success":true,
        "preflight_token":"9".repeat(32),"module_scope":OPS,"people_transfer":true,"applies":a,"policy":"recheck",
        "source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "targets":[{"document_id":"b".repeat(32),"revision":"3","index":1,"path":"/target.raw","blocked":null,
            "people_transfer":transfer}],"ok":1,"blocked":0,"rejected_docs":[]})
}
fn commit_fixture() -> Value {
    json!({"cmd":"batch","action":"commit","request_id":"face-style-commit","preflight_token":"9".repeat(32),
        "face_style_review_ack":[{"document_id":"b".repeat(32),"revision":"3","before_sha256":"f".repeat(64),
            "after_sha256":"f".repeat(64),"recipe_sha256":recipe_digest(&recipe_fixture()).unwrap()}]})
}
fn terminal(c: &Value) -> Value {
    json!({"event":"batch_result","action":"commit","request_id":c["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":c["preflight_token"],"module_scope":OPS,"face_style_review_ack":c[ACK],
        "people_transfer":true,"batch_id":"batch","source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "applied":[1],"target_outcomes":[{"document_id":"b".repeat(32),"expected_revision":"3","current_revision":"3",
            "result_revision":"4","index":1,"blocked":null,"outcome":"applied"}]})
}
fn image_request_fixture() -> Value {
    json!({"cmd":"batch","action":"face_style_visual","request_id":"face-style-image","preflight_token":"9".repeat(32),
        "document_id":"b".repeat(32),"revision":"3","side":"before","sha256":"f".repeat(64)})
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch,true); h
}
#[test] fn exact_thirty_owned_leaves_and_explicit_local_faces_are_required() {
    let c = request_fixture(); assert!(command(&c).is_ok()); assert!(read_only(&c)); assert!(crate::batch_api::read_only(&c));
    assert_eq!(LEAVES.iter().map(|(_,paths)| paths.len()).sum::<usize>(),30);
    for path in ["/people_transfer/source_ref", "/people_transfer/source", "/people_transfer/face_style",
        "/people_transfer/selection/lnx.eye_shape.v1", "/people_transfer/targets/0/target_refs"] {
        let mut changed = c.clone(); *changed.pointer_mut(path).unwrap() = Value::Null;
        assert!(command(&changed).is_err(),"{path}"); assert!(!read_only(&changed));
    }
    for (path, bad) in [("/people_transfer/target_policy",json!("confirmed_person_only")),
        ("/people_transfer/targets/0/target/document/epoch",json!("other")),
        ("/people_transfer/targets/0/target_refs/0/asset_sha256",json!("c".repeat(64))),
        ("/people_transfer/face_style/amount",json!(true)),("/people_transfer/face_style/amount",json!(1.01)),
        ("/people_transfer/face_style/style",json!("legacy")),("/people_transfer/face_style/version",json!(2))] {
        let mut changed=c.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(command(&changed).is_err(),"{path}");
    }
    let mut changed=c.clone();changed["people_transfer"]["selection"]["lnx.eye_shape.v1"][0]=json!("/size/left");assert!(!read_only(&changed));
    changed=c.clone();changed["module_scope"].as_array_mut().unwrap().reverse();assert!(!read_only(&changed));
    changed=c.clone();changed["people_transfer"]["targets"].as_array_mut().unwrap().push(c["people_transfer"]["targets"][0].clone());assert!(!read_only(&changed));
    for key in ["reference_color","local_mask_transfer","collarbone_review_ack","preflight_token"] {
        let mut changed=c.clone();changed[key]=json!({});assert!(command(&changed).is_err());
    }
}
#[test] fn leaf_order_is_not_identity_but_scope_and_request_content_are_bound() {
    let c=request_fixture();let mut changed=c.clone();
    changed["people_transfer"]["selection"]["lnx.eye_shape.v1"].as_array_mut().unwrap().reverse();
    assert!(command(&changed).is_ok());
    let binding=binding(&c).unwrap().unwrap();assert_eq!(binding["module_scope"],json!(OPS));assert_eq!(binding["policy"],"recheck");
    let mut one=c["people_transfer"].clone();one["face_style"]["amount"]=json!(1);
    let mut float=one.clone();float["face_style"]["amount"]=json!(1.0);
    assert_eq!(request_digest(&one),request_digest(&float));
    float["targets"][0]["target"]["graph_sha256"]=json!("f".repeat(64));assert_ne!(request_digest(&one),request_digest(&float));
}
#[test] fn recipe_identity_is_typed_and_neutral_amount_cannot_retain_old_values() {
    let mut zero=recipe_fixture();zero["amount"]=json!(0);let mut negative_zero=zero.clone();negative_zero["amount"]=json!(-0.0);
    assert_eq!(recipe_digest(&zero),recipe_digest(&negative_zero));
    let mut other=zero.clone();other["style"]=json!("square");assert_ne!(recipe_digest(&zero),recipe_digest(&other));
    assert_eq!(coefficient("classic","lnx.face_contour.v1","/jaw/left"),-0.20);
    assert_eq!(coefficient("square","lnx.face_contour.v1","/jaw/right"),-0.30);
    assert_eq!(coefficient("youthful","lnx.nose_shape.v1","/height"),-0.03);
    let v=review_fixture();assert!(!parameters(&v["targets"][0]["people_transfer"]["parameters"],&zero));
}
#[test] fn full_render_metadata_recipe_and_each_target_owner_are_required() {
    let v=review_fixture();assert!(receipt(&v));assert!(crate::batch_host::BatchKind::valid(&v,None));
    for path in ["/targets/0/people_transfer/face_style_visual", "/targets/0/people_transfer/face_style",
        "/targets/0/people_transfer/target_owner", "/targets/0/people_transfer/parameters"] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=Value::Null;assert!(!receipt(&changed),"{path}");
    }
    for (path,bad) in [("/targets/0/people_transfer/face_style_visual/recipe_sha256",json!("e".repeat(64))),
        ("/targets/0/people_transfer/face_style_visual/before/width",json!(256)),
        ("/targets/0/people_transfer/face_style_visual/source_proof/asset_sha256",json!("c".repeat(64))),
        ("/targets/0/people_transfer/parameters/0/value",json!(false)),
        ("/targets/0/people_transfer/parameters/1/value",json!(0.25)),
        ("/targets/0/people_transfer/face_style/style",json!("round")),
        ("/targets/0/revision",json!("4")),("/blocked",json!(1))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!receipt(&changed),"{path}");
    }
    let mut changed=v.clone();changed["targets"][0]["people_transfer"]["face_style_visual"]["coverage_sha256"]=json!("1".repeat(64));assert!(!receipt(&changed));
    changed=v.clone();changed["targets"][0]["people_transfer"]["face_style_visual"]["before"]["base64"]=json!("AAAA");assert!(!receipt(&changed));
    changed=v.clone();changed["targets"][0]["blocked"]=json!("Target changed");changed["targets"][0]["people_transfer"]=Value::Null;
    changed["ok"]=json!(0);changed["blocked"]=json!(1);assert!(receipt(&changed));
}
#[test] fn paged_image_coordinates_are_exact_and_share_the_read_only_dispatch() {
    let c=image_request_fixture();assert!(command(&c).is_ok());assert!(collarbone::command(&c).is_ok());assert!(crate::batch_api::read_only(&c));
    let binding=binding(&c).unwrap().unwrap();for key in ["preflight_token","document_id","revision","side","sha256"] {assert_eq!(binding[key],c[key]);}
    for key in ["people_transfer","module_scope","face_style_review_ack","path","compact"] {
        let mut changed=c.clone();changed[key]=json!({});assert!(command(&changed).is_err());assert!(collarbone::command(&changed).is_err());assert!(!read_only(&changed));
    }
    for (key,bad) in [("side",json!("../before")),("revision",json!("03")),("sha256",json!("F".repeat(64)))] {
        let mut changed=c.clone();changed[key]=bad;assert!(!read_only(&changed));
    }
    let mut changed=c;changed["action"]=json!("commit");assert!(collarbone::command(&changed).is_err());assert!(!read_only(&changed));
}
#[test] fn image_receipt_checks_png_bytes_hash_and_compact_metadata() {
    let source=owner('b','d')["source_proof"].clone();
    let sample=crate::spill_transfer_protocol::tests::sample_transfer(&json!("b".repeat(32)),&json!("3"),&json!({}),&source);
    let image=sample["before"].clone();let mut compact=image.clone();compact.as_object_mut().unwrap().remove("base64");
    let mut v=image_request_fixture();v.as_object_mut().unwrap().remove("cmd");v["success"]=json!(true);
    v["sha256"]=image["sha256"].clone();v["image"]=image;v["compact"]=compact;assert!(receipt(&v));
    for (path,bad) in [("/compact/width",json!(2)),("/image/base64",json!("AAAA")),("/sha256",json!("e".repeat(64))),
        ("/image/width",json!(2)),("/compact/sha256",json!("e".repeat(64)))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!receipt(&changed),"{path}");
    }
    let mut changed=v;changed["doc_state"]=json!({});assert!(!receipt(&changed));
}
#[test] fn image_failures_still_retain_the_original_exact_coordinates() {
    let c=image_request_fixture();
    for key in ["preflight_token","document_id","revision","side","sha256"] {
        let mut h=host([230;16]);h.begin_command([230;16],&c).unwrap();
        let mut v=binding(&c).unwrap().unwrap();v["request_id"]=c["request_id"].clone();v["action"]=c["action"].clone();
        v["success"]=json!(false);v["outcome_unknown"]=json!(false);v["error"]=json!("Image unavailable");v[key]=json!("other");
        h.receive([230;16],&v);let retained=h.status("face-style-image")["result"].clone();
        assert_eq!(retained["outcome_unknown"],true);assert_eq!(retained[key],c[key]);
    }
}
#[test] fn commit_accepts_only_its_own_exact_frozen_ack_family() {
    let c=commit_fixture();assert!(command(&c).is_ok());assert!(!read_only(&c));assert!(receipt(&terminal(&c)));
    for key in ["module_scope","people_transfer","collarbone_review_ack","head_review_ack","docs"] {
        let mut changed=c.clone();changed[key]=json!([]);assert!(command(&changed).is_err());
    }
    let mut duplicated=c.clone();duplicated[ACK].as_array_mut().unwrap().push(c[ACK][0].clone());assert!(command(&duplicated).is_err());
    for key in ["before_sha256","after_sha256","recipe_sha256","revision"] {
        let mut changed=c.clone();changed[ACK][0].as_object_mut().unwrap().remove(key);assert!(command(&changed).is_err());
    }
    let mut no_op=terminal(&c);no_op["batch_id"]=Value::Null;no_op["target_outcomes"][0]["result_revision"]=json!("3");assert!(receipt(&no_op));
}
#[test] fn wrong_scope_ack_recipe_or_target_outcome_stays_unknown_without_replay() {
    let c=commit_fixture();let v=terminal(&c);
    for (path,bad) in [("/preflight_token",json!("8".repeat(32))),("/module_scope",json!(["lnx.head_size.v1"])),
        ("/face_style_review_ack/0/recipe_sha256",json!("8".repeat(64))),("/face_style_review_ack/0/revision",json!("4")),
        ("/target_outcomes/0/document_id",json!("c".repeat(32))),("/target_outcomes/0/expected_revision",json!("2")),
        ("/target_outcomes",json!([])),("/applied",json!([]))] {
        let mut h=host([231;16]);h.begin_command([231;16],&c).unwrap();
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;h.receive([231;16],&changed);
        let retained=h.status("face-style-commit")["result"].clone();assert_eq!(retained["outcome_unknown"],true,"{path}");
        assert_eq!(retained[ACK],c[ACK]);assert_eq!(retained["module_scope"],json!(OPS));assert_eq!(retained["preflight_token"],c["preflight_token"]);
        h.receive([231;16],&v);assert_eq!(h.status("face-style-commit")["result"],retained);
    }
}
#[test] fn request_recipe_and_policy_substitution_cannot_settle_preflight() {
    let c=request_fixture();let v=review_fixture();
    for (key,bad) in [("policy",json!("skip_and_report")),("applies",json!({}))] {
        let mut h=host([232;16]);h.begin_command([232;16],&c).unwrap();let mut changed=v.clone();changed[key]=bad;
        h.receive([232;16],&changed);assert_eq!(h.status("face-style-review")["result"]["outcome_unknown"],true);
    }
}
#[test] fn uncertain_commit_never_settles_recovery_and_read_cannot_reuse_it() {
    let epoch=[233;16];let c=commit_fixture();let mut h=host(epoch);h.begin_command(epoch,&c).unwrap();
    crate::project_recovery_fence::issued(epoch,&c).unwrap();
    let mut read=image_request_fixture();read["request_id"]=c["request_id"].clone();
    assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"batch_result","action":"face_style_visual",
        "request_id":c["request_id"],"success":true}));assert!(crate::project_recovery_fence::proof(epoch).is_err());
    let mut wrong=terminal(&c);wrong[ACK][0]["after_sha256"]=json!("8".repeat(64));h.receive(epoch,&wrong);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());h.receive(epoch,&terminal(&c));assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
    crate::project_recovery_fence::issued(epoch,&read).unwrap();assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn missing_or_unsettled_outcome_cannot_be_a_known_failed_write() {
    let c=commit_fixture();
    for (key,bad) in [("outcome_unknown",Value::Null),("outcome_unknown",json!("false")),("status",json!("running")),
        ("requires_readback",json!(true)),("requires_reload",json!(true))] {
        let mut h=host([234;16]);h.begin_command([234;16],&c).unwrap();let mut v=terminal(&c);
        v["success"]=json!(false);v["error"]=json!("Unsettled");v[key]=bad;h.receive([234;16],&v);
        assert_eq!(h.status("face-style-commit")["result"]["outcome_unknown"],true,"{key}");
    }
}
#[test] fn lost_image_receipts_are_bounded_without_pinning_an_edit_fence() {
    let epoch=[235;16];let mut h=host(epoch);
    for n in 0..(crate::receipt_host::MAX_RECORDS+3) {
        let mut c=image_request_fixture();let id=format!("page-{n}");c["request_id"]=json!(id);
        h.begin_command(epoch,&c).unwrap();crate::project_recovery_fence::issued(epoch,&c).unwrap();h.failed(&id,"Read unavailable");
    }
    assert_eq!(h.status("page-0")["phase"],"unavailable");assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn only_explicit_unclaimed_no_write_refusal_can_omit_commit_identity() {
    let c=commit_fixture();let refusal=json!({"event":"batch_result","action":"commit","request_id":c["request_id"],
        "success":false,"outcome_unknown":false,"error":"Token expired before claim"});
    let mut h=host([236;16]);h.begin_command([236;16],&c).unwrap();h.receive([236;16],&refusal);
    assert_eq!(h.status("face-style-commit")["result"],refusal);
    for (key,bad) in [("outcome_unknown",Value::Null),("preflight_token",json!("7".repeat(32))),
        (ACK,c[ACK].clone()),("module_scope",json!(OPS)),("operation_committed",json!(true)),
        ("target_outcomes",json!([{"outcome":"applied"}]))] {
        let mut h=host([237;16]);h.begin_command([237;16],&c).unwrap();let mut changed=refusal.clone();changed[key]=bad;
        h.receive([237;16],&changed);assert_eq!(h.status("face-style-commit")["result"]["outcome_unknown"],true,"{key}");
    }
}
#[test] fn ordered_ack_cannot_be_replaced_even_when_each_row_is_individually_valid() {
    let mut c=commit_fixture();let mut second=c[ACK][0].clone();second["document_id"]=json!("c".repeat(32));
    c[ACK].as_array_mut().unwrap().push(second);
    let mut v=terminal(&c);let mut outcome=v["target_outcomes"][0].clone();outcome["document_id"]=json!("c".repeat(32));outcome["index"]=json!(2);
    v["target_outcomes"].as_array_mut().unwrap().push(outcome);v["applied"]=json!([1,2]);assert!(receipt(&v));
    let mut h=host([238;16]);h.begin_command([238;16],&c).unwrap();v[ACK].as_array_mut().unwrap().reverse();
    assert!(receipt(&v));h.receive([238;16],&v);assert_eq!(h.status("face-style-commit")["result"]["outcome_unknown"],true);
}
#[test] fn new_receipts_do_not_bypass_epoch_action_or_request_registration() {
    let c=commit_fixture();let v=terminal(&c);let mut h=host([239;16]);h.begin_command([239;16],&c).unwrap();
    h.receive([240;16],&v);assert_eq!(h.status("face-style-commit")["phase"],"pending");
    let mut wrong=v.clone();wrong["action"]=json!("preflight");h.receive([239;16],&wrong);
    wrong=v.clone();wrong["request_id"]=json!("other");h.receive([239;16],&wrong);
    assert_eq!(h.status("face-style-commit")["phase"],"pending");h.receive([239;16],&v);
    assert_eq!(h.status("face-style-commit")["result"],v);assert!(h.begin_command([239;16],&c).is_err());
}
#[test] fn exact_commit_settles_recovery_but_send_failure_preserves_frozen_identity() {
    let epoch=[241;16];let c=commit_fixture();let mut h=host(epoch);h.begin_command(epoch,&c).unwrap();
    crate::project_recovery_fence::issued(epoch,&c).unwrap();h.receive(epoch,&terminal(&c));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    let mut h=host([242;16]);let mut changed=c.clone();h.begin_command([242;16],&changed).unwrap();
    changed[ACK][0]["recipe_sha256"]=json!("0".repeat(64));h.failed("face-style-commit","Pipe outcome unknown");
    assert_eq!(h.status("face-style-commit")["result"][ACK],c[ACK]);assert!(h.guards_review([242;16],"face-style-commit"));
    h.ended([242;16]);assert_eq!(h.status("face-style-commit")["result"][ACK],c[ACK]);
}
#[test] fn legacy_batch_and_collarbone_paths_are_not_reclassified_as_named_styles() {
    let ordinary=json!({"cmd":"batch","action":"preflight","request_id":"ordinary","docs":["target"],"module_scope":["lnx.exposure.v1"]});
    assert!(command(&ordinary).is_ok());assert!(binding(&ordinary).unwrap().is_none());assert!(!read_only(&ordinary));
    let mut collarbone=image_request_fixture();collarbone["action"]=json!("collarbone_visual");
    assert!(command(&collarbone).is_ok());assert!(binding(&collarbone).unwrap().is_none());
    assert!(collarbone::command(&collarbone).is_ok());assert!(crate::batch_api::read_only(&collarbone));
}
#[test] fn named_commit_success_requires_explicit_known_outcome() {
    let c=commit_fixture();let mut v=terminal(&c);v.as_object_mut().unwrap().remove("outcome_unknown");
    assert!(!receipt(&v));let mut h=host([243;16]);h.begin_command([243;16],&c).unwrap();h.receive([243;16],&v);
    assert_eq!(h.status("face-style-commit")["result"]["outcome_unknown"],true);
    for unknown in [Value::Null,json!(true),json!(0),json!("false")] {
        let mut v=terminal(&c);v["outcome_unknown"]=unknown;assert!(!receipt(&v));
    }
}
#[test] fn null_batch_id_requires_every_applied_target_to_be_a_real_no_op() {
    let c=commit_fixture();let mut v=terminal(&c);v["batch_id"]=Value::Null;
    assert!(!receipt(&v));let mut h=host([244;16]);h.begin_command([244;16],&c).unwrap();h.receive([244;16],&v);
    assert_eq!(h.status("face-style-commit")["result"]["outcome_unknown"],true);
    v["target_outcomes"][0]["result_revision"]=json!("3");assert!(receipt(&v));
    let mut second_ack=c[ACK][0].clone();second_ack["document_id"]=json!("c".repeat(32));v[ACK].as_array_mut().unwrap().push(second_ack);
    let mut second=v["target_outcomes"][0].clone();second["document_id"]=json!("c".repeat(32));second["index"]=json!(2);
    second["result_revision"]=json!("4");v["target_outcomes"].as_array_mut().unwrap().push(second);v["applied"]=json!([1,2]);
    assert!(!receipt(&v));v["batch_id"]=json!("mixed-batch");assert!(receipt(&v));
}
