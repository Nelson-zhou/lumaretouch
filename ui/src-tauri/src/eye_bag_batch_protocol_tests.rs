//! AUTHORED / UNRUN. Transport fixtures only, not render/browser acceptance.
use super::*;
use crate::receipt_host::ReceiptKind;

fn owner(id: char, asset: char) -> Value {
    json!({"document":{"document_id":id.to_string().repeat(32),"epoch":"workspace","revision":3},
        "people_scope":"project","state_revision":2,"association_revision":1,"graph_sha256":"e".repeat(64),
        "source_proof":{"asset_sha256":asset.to_string().repeat(64),"original_sha256":asset.to_string().repeat(64),"creative_source":null}})
}
fn face(asset: char, id: &str) -> Value {
    json!({"asset_sha256":asset.to_string().repeat(64),"face_instance_id":id,"analysis_revision":1})
}
fn request_fixture() -> Value {
    json!({"cmd":"batch","action":"preflight","request_id":"eye-review","docs":["b".repeat(32)],
        "module_scope":[OP],"conflict_policy":"recheck","people_transfer":{"target_policy":"explicit_face_map",
        "source_ref":face('c',"source-face"),"source":owner('a','c'),"selection":{(OP):["/amount","/preserve"]},
        "targets":[{"target":owner('b','d'),"target_refs":[face('d',"target-face")]}],
        "eye_bag":{"version":1,"targets":[{"document_id":"b".repeat(32),"replace_legacy":false}]}}})
}
fn review_fixture() -> Value {
    let c = request_fixture(); let a = &c["people_transfer"]; let owner = &a["targets"][0]["target"];
    let coverage = json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face('d',"target-face"),
        "scope":"target-reviewed-ridge","ridge_sha256":"8".repeat(64),"sides":["left","right"]}]});
    let image = json!({"mime":"image/png","width":1024,"height":768,"sha256":"f".repeat(64)});
    let visual = json!({"version":1,"document_id":"b".repeat(32),"revision":"3","source_proof":owner["source_proof"],
        "before_state_sha256":"1".repeat(64),"candidate_state_sha256":"2".repeat(64),
        "before_people_sha256":"3".repeat(64),"candidate_people_sha256":"4".repeat(64),
        "source_size":[4000,3000],"before_output_size":[4000,3000],"after_output_size":[4000,3000],
        "before":image,"after":image,"coverage_sha256":collarbone::request_digest(&coverage)});
    let transfer = json!({"version":1,"source_document":a["source"]["document"],"target_document":owner["document"],
        "source_ref":a["source_ref"],"target_refs":a["targets"][0]["target_refs"],"parameters":[
            {"operation_id":OP,"parameter_path":"/amount","value":0.5},
            {"operation_id":OP,"parameter_path":"/preserve","value":1.0}],
        "source_state_revision":2,"target_state_revision":2,"source_association_revision":1,"target_association_revision":1,
        "transfer_policy":"selected_parameter_keys_replace","excluded":["local_assets","landmarks","masks","identity_links"],
        "source_owner":a["source"],"target_owner":owner,"target_policy":"explicit_face_map",
        "eye_bag":{"version":1,"replace_legacy":false},"eye_bag_coverage":coverage,"eye_bag_visual":visual});
    json!({"event":"batch_result","action":"preflight","request_id":c["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":"9".repeat(32),"module_scope":[OP],"people_transfer":true,
        "applies":a,"policy":"recheck","source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "targets":[{"document_id":"b".repeat(32),"revision":"3","index":1,"path":"/target.raw","blocked":null,
            "people_transfer":transfer}],"ok":1,"blocked":0,"rejected_docs":[]})
}
fn commit_fixture() -> Value {
    json!({"cmd":"batch","action":"commit","request_id":"eye-commit","preflight_token":"9".repeat(32),
        (ACK):[{"document_id":"b".repeat(32),"revision":"3","before_sha256":"f".repeat(64),
            "after_sha256":"f".repeat(64),"coverage_sha256":"8".repeat(64),"replace_legacy":false}]})
}
fn terminal(c: &Value) -> Value {
    let mut v = json!({"event":"batch_result","action":"commit","request_id":c["request_id"],"success":true,
        "outcome_unknown":false,"preflight_token":c["preflight_token"],"module_scope":[OP],(ACK):c[ACK],
        "people_transfer":true,"batch_id":"batch","source_snapshot":{"document_id":"a".repeat(32),"revision":"3","path":"/source.raw"},
        "applied":[1],"target_outcomes":[{"document_id":"b".repeat(32),"expected_revision":"3","current_revision":"3",
            "result_revision":"4","index":1,"blocked":null,"outcome":"applied"}]});
    if let Some(other) = c.get(collarbone::ACK) {
        v[collarbone::ACK] = other.clone(); v["module_scope"] = json!([collarbone::OP, OP]);
    }
    v
}
fn image_request_fixture() -> Value {
    json!({"cmd":"batch","action":"eye_bag_visual","request_id":"eye-image","preflight_token":"9".repeat(32),
        "document_id":"b".repeat(32),"revision":"3","side":"before","sha256":"f".repeat(64)})
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut h = crate::batch_host::BatchHost::default(); h.reset(epoch); h.ready(epoch,true); h
}
fn refresh_coverage(v: &mut Value) {
    let digest = collarbone::request_digest(&v["targets"][0]["people_transfer"]["eye_bag_coverage"]);
    v["targets"][0]["people_transfer"]["eye_bag_visual"]["coverage_sha256"] = json!(digest);
}
#[test] fn request_requires_exact_target_qualified_choice_and_no_portable_support() {
    let c = request_fixture(); assert!(command(&c).is_ok()); assert!(read_only(&c)); assert!(crate::batch_api::read_only(&c));
    for (path, bad) in [("/people_transfer/target_policy",json!("confirmed_person_only")),
        ("/people_transfer/eye_bag/version",json!(2)),("/people_transfer/eye_bag/targets/0/replace_legacy",json!(1)),
        ("/people_transfer/eye_bag/targets/0/document_id",json!("c".repeat(32))),
        ("/people_transfer/targets/0/target/document/epoch",json!("other")),
        ("/people_transfer/targets/0/target_refs/0/asset_sha256",json!("c".repeat(64))),
        ("/people_transfer/selection/lnx.eye_bags.v2",json!(["/support"]))] {
        let mut bad_request = c.clone(); *bad_request.pointer_mut(path).unwrap() = bad;
        assert!(command(&bad_request).is_err(),"{path}"); assert!(!read_only(&bad_request));
    }
    for key in ["support", "eyes", "face_style", "operation", "association_id"] {
        let mut bad = c.clone(); bad["people_transfer"][key] = json!({}); assert!(command(&bad).is_err());
    }
    let mut bad=c.clone();bad["people_transfer"]["eye_bag"]["targets"].as_array_mut().unwrap().push(c["people_transfer"]["eye_bag"]["targets"][0].clone());
    assert!(command(&bad).is_err());
    for key in ["preflight_token", "eye_bag_replace_legacy", ACK, "reference_color", "local_mask_transfer"] {
        let mut bad=c.clone();bad[key]=json!({});assert!(command(&bad).is_err());
    }
}
#[test] fn each_full_target_render_is_owned_by_its_exact_face_map() {
    let v=review_fixture();assert!(receipt(&v));assert!(crate::batch_host::BatchKind::valid(&v,None));
    for path in ["/targets/0/people_transfer/eye_bag", "/targets/0/people_transfer/eye_bag_coverage",
        "/targets/0/people_transfer/eye_bag_visual", "/targets/0/people_transfer/target_owner",
        "/targets/0/people_transfer/parameters"] {
        let mut bad=v.clone();*bad.pointer_mut(path).unwrap()=Value::Null;assert!(!receipt(&bad),"{path}");
    }
    for (path,bad) in [("/targets/0/people_transfer/eye_bag/replace_legacy",json!(true)),
        ("/targets/0/people_transfer/eye_bag_visual/source_proof/asset_sha256",json!("c".repeat(64))),
        ("/targets/0/people_transfer/eye_bag_visual/before/width",json!(256)),
        ("/targets/0/people_transfer/eye_bag_visual/coverage_sha256",json!("1".repeat(64))),
        ("/targets/0/people_transfer/eye_bag_coverage/support_transfer",json!("source")),
        ("/targets/0/people_transfer/parameters/0/value",json!(true)),("/targets/0/revision",json!("4"))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!receipt(&changed),"{path}");
    }
}
#[test] fn ridge_scope_side_order_and_neutral_resets_are_explicit() {
    let v=review_fixture();
    for sides in [json!([]),json!(["right","left"]),json!(["left","left"]),json!(["upper"])] {
        let mut bad=v.clone();bad["targets"][0]["people_transfer"]["eye_bag_coverage"]["targets"][0]["sides"]=sides;
        refresh_coverage(&mut bad);assert!(!receipt(&bad));
    }
    let mut zero=v;zero["targets"][0]["people_transfer"]["parameters"][0]["value"]=json!(0);
    assert!(!receipt(&zero));let row=&mut zero["targets"][0]["people_transfer"]["eye_bag_coverage"]["targets"][0];
    row["scope"]=json!("neutral-no-effect");row["ridge_sha256"]=Value::Null;row["sides"]=json!([]);
    refresh_coverage(&mut zero);assert!(receipt(&zero));
    zero["targets"][0]["people_transfer"]["eye_bag_coverage"]["targets"][0]["ridge_sha256"]=json!("8".repeat(64));
    refresh_coverage(&mut zero);assert!(!receipt(&zero));
}
#[test] fn selected_active_legacy_leaf_is_not_silently_replaced() {
    let mut v=review_fixture();v["module_scope"]=json!(["lnx.enhance.v1",OP]);
    v["applies"]["selection"]["lnx.enhance.v1"]=json!(["/eye_bags"]);
    v["applies"]["eye_bag"]["targets"][0]["replace_legacy"]=json!(true);
    let p=&mut v["targets"][0]["people_transfer"];p["eye_bag"]["replace_legacy"]=json!(true);
    p["parameters"].as_array_mut().unwrap().push(json!({"operation_id":"lnx.enhance.v1","parameter_path":"/eye_bags","value":0.2}));
    assert!(!receipt(&v));v["targets"][0]["people_transfer"]["parameters"][2]["value"]=json!(0);assert!(receipt(&v));
}
#[test] fn blocked_targets_have_no_review_and_counts_cannot_omit_a_target() {
    let mut v=review_fixture();v["targets"][0]["blocked"]=json!("Target ridge is not independently reviewed");
    v["ok"]=json!(0);v["blocked"]=json!(1);assert!(!receipt(&v));
    v["targets"][0]["people_transfer"]=Value::Null;assert!(receipt(&v));
    v["targets"]=json!([]);assert!(!receipt(&v));
}
#[test] fn mixed_collarbone_retains_complete_render_and_both_coverage_families() {
    let mut v=review_fixture();v["module_scope"]=json!([collarbone::OP,OP]);v["applies"]["selection"][collarbone::OP]=json!(["/amount"]);
    let p=&mut v["targets"][0]["people_transfer"];
    p["parameters"].as_array_mut().unwrap().push(json!({"operation_id":collarbone::OP,"parameter_path":"/amount","value":0}));
    p["collarbone_coverage"]=json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face('d',"target-face"),
        "scope":"neutral-no-effect","body_review_sha256":null,"clavicle_category":null,"clavicle_sides":[]}]});
    p["collarbone_visual"]=p["eye_bag_visual"].clone();
    p["collarbone_visual"]["coverage_sha256"]=json!(collarbone::request_digest(&p["collarbone_coverage"]));
    assert!(receipt(&v));assert!(crate::batch_host::BatchKind::valid(&v,None));
    v["targets"][0]["people_transfer"]["collarbone_visual"]["candidate_people_sha256"]=json!("9".repeat(64));assert!(!receipt(&v));
}
#[test] fn image_reads_are_exact_and_never_accept_mutation_coordinates() {
    let c=image_request_fixture();assert!(command(&c).is_ok());assert!(collarbone::command(&c).is_ok());assert!(crate::batch_api::read_only(&c));
    for key in ["people_transfer", "module_scope", ACK, "path", "compact"] {
        let mut bad=c.clone();bad[key]=json!({});assert!(command(&bad).is_err());assert!(collarbone::command(&bad).is_err());assert!(!read_only(&bad));
    }
    let mut bad=c;bad["action"]=json!("commit");assert!(collarbone::command(&bad).is_err());assert!(!read_only(&bad));
}
#[test] fn image_receipts_verify_png_hash_and_compact_identity() {
    let source=owner('b','d')["source_proof"].clone();
    let sample=crate::spill_transfer_protocol::tests::sample_transfer(&json!("b".repeat(32)),&json!("3"),&json!({}),&source);
    let image=sample["before"].clone();let mut compact=image.clone();compact.as_object_mut().unwrap().remove("base64");
    let mut v=image_request_fixture();v.as_object_mut().unwrap().remove("cmd");v["success"]=json!(true);
    v["sha256"]=image["sha256"].clone();v["image"]=image;v["compact"]=compact;assert!(receipt(&v));
    for (path,bad) in [("/image/base64",json!("AAAA")),("/compact/width",json!(2)),("/sha256",json!("e".repeat(64)))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!receipt(&changed));
    }
    v["doc_state"]=json!({});assert!(!receipt(&v));
}
#[test] fn commit_choice_images_token_and_ack_order_are_immutable() {
    let c=commit_fixture();assert!(command(&c).is_ok());assert!(!read_only(&c));assert!(receipt(&terminal(&c)));
    for key in ["module_scope", "people_transfer", "face_style_review_ack", "portrait_cohort_ack", "eye_bag_preset_ack", "head_review_ack"] {
        let mut bad=c.clone();bad[key]=json!([]);assert!(command(&bad).is_err());
    }
    for path in ["/preflight_token", "/eye_bag_review_ack/0/replace_legacy", "/eye_bag_review_ack/0/coverage_sha256",
        "/eye_bag_review_ack/0/revision", "/target_outcomes/0/document_id"] {
        let mut h=host([145;16]);h.begin_command([145;16],&c).unwrap();let mut v=terminal(&c);
        *v.pointer_mut(path).unwrap()=if path.ends_with("replace_legacy") {json!(true)} else {json!("other")};
        h.receive([145;16],&v);let retained=h.status("eye-commit")["result"].clone();assert_eq!(retained["outcome_unknown"],true,"{path}");
        assert_eq!(retained[ACK],c[ACK]);assert_eq!(retained["preflight_token"],c["preflight_token"]);
        h.receive([145;16],&terminal(&c));assert_eq!(h.status("eye-commit")["result"],retained);
    }
}
#[test] fn mixed_ack_cannot_be_added_removed_or_substitute_a_family() {
    let mut c=commit_fixture();let mut other=c[ACK][0].clone();other.as_object_mut().unwrap().remove("replace_legacy");
    other["coverage_sha256"]=json!("7".repeat(64));c[collarbone::ACK]=json!([other]);
    assert!(command(&c).is_ok());assert!(collarbone::command(&c).is_ok());assert!(receipt(&terminal(&c)));
    for missing in [ACK,collarbone::ACK] {
        let mut h=host([146;16]);h.begin_command([146;16],&c).unwrap();let mut v=terminal(&c);v.as_object_mut().unwrap().remove(missing);
        h.receive([146;16],&v);assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
    }
    let plain=commit_fixture();let mut h=host([147;16]);h.begin_command([147;16],&plain).unwrap();
    h.receive([147;16],&terminal(&c));assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
    c[collarbone::ACK][0]["after_sha256"]=json!("6".repeat(64));assert!(command(&c).is_err());
}
#[test] fn noop_requires_full_ack_equal_revisions_and_no_applied_index() {
    let c=commit_fixture();let mut v=terminal(&c);v["batch_id"]=Value::Null;v["applied"]=json!([]);
    v["target_outcomes"][0]["outcome"]=json!("noop");v["target_outcomes"][0]["result_revision"]=json!("3");assert!(receipt(&v));
    for (path,bad) in [("/applied",json!([1])),("/batch_id",json!("invented")),("/target_outcomes/0/result_revision",json!("4"))] {
        let mut changed=v.clone();*changed.pointer_mut(path).unwrap()=bad;assert!(!receipt(&changed),"{path}");
    }
    v[ACK]=json!([]);assert!(!receipt(&v));
}
#[test] fn failed_and_unknown_commands_still_require_exact_native_identity() {
    let c=commit_fixture();let mut failure=binding(&c).unwrap().unwrap();failure["request_id"]=c["request_id"].clone();
    failure["action"]=json!("commit");failure["success"]=json!(false);failure["outcome_unknown"]=json!(false);failure["error"]=json!("Token expired before claim");
    let mut h=host([148;16]);h.begin_command([148;16],&c).unwrap();h.receive([148;16],&failure);assert_eq!(h.status("eye-commit")["result"],failure);
    for key in ["preflight_token",ACK,"outcome_unknown"] {
        let mut h=host([149;16]);h.begin_command([149;16],&c).unwrap();let mut bad=failure.clone();bad.as_object_mut().unwrap().remove(key);
        h.receive([149;16],&bad);assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
    }
    for key in ["requires_readback","requires_reload"] {
        let mut h=host([150;16]);h.begin_command([150;16],&c).unwrap();let mut bad=failure.clone();bad[key]=json!(true);
        h.receive([150;16],&bad);assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
    }
    for (key,bad) in [("applied",json!([1])),("batch_id",json!("already-written")),("operation_committed",json!(true)),
        ("doc_state",json!({})),("target_outcomes",json!([{"outcome":"applied","result_revision":"4"}]))] {
        let mut h=host([157;16]);h.begin_command([157;16],&c).unwrap();let mut changed=failure.clone();changed[key]=bad;
        h.receive([157;16],&changed);assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
    }
}
#[test] fn exact_preflight_identity_is_checked_on_failure_too() {
    let c=request_fixture();let mut v=json!({"event":"batch_result","action":"preflight","request_id":c["request_id"],
        "success":false,"outcome_unknown":false,"error":"Source changed","module_scope":c["module_scope"],
        "policy":"recheck","applies":c["people_transfer"]});
    let mut h=host([151;16]);h.begin_command([151;16],&c).unwrap();h.receive([151;16],&v);assert_eq!(h.status("eye-review")["result"],v);
    v["applies"]["eye_bag"]["targets"][0]["replace_legacy"]=json!(true);
    let mut h=host([152;16]);h.begin_command([152;16],&c).unwrap();h.receive([152;16],&v);assert_eq!(h.status("eye-review")["result"]["outcome_unknown"],true);
}
#[test] fn unknown_write_remains_fenced_and_query_does_not_resubmit() {
    let epoch=[153;16];let c=commit_fixture();let mut h=host(epoch);h.begin_command(epoch,&c).unwrap();
    crate::project_recovery_fence::issued(epoch,&c).unwrap();h.failed("eye-commit","Pipe outcome unknown");
    assert!(h.guards_review(epoch,"eye-commit"));assert!(crate::project_recovery_fence::proof(epoch).is_err());
    let retained=h.status("eye-commit");assert_eq!(retained,h.status("eye-commit"));
    h.receive(epoch,&terminal(&c));assert_eq!(h.status("eye-commit"),retained);
    let mut read=image_request_fixture();read["request_id"]=c["request_id"].clone();assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
    crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn image_read_failure_is_exact_but_does_not_pin_a_write_fence() {
    let epoch=[154;16];let c=image_request_fixture();let mut h=host(epoch);h.begin_command(epoch,&c).unwrap();
    crate::project_recovery_fence::issued(epoch,&c).unwrap();let mut v=binding(&c).unwrap().unwrap();
    v["action"]=c["action"].clone();v["request_id"]=c["request_id"].clone();v["success"]=json!(false);
    v["outcome_unknown"]=json!(false);v["error"]=json!("Image expired");v["side"]=json!("after");h.receive(epoch,&v);
    assert_eq!(h.status("eye-image")["result"]["outcome_unknown"],true);assert_eq!(h.status("eye-image")["result"]["side"],"before");
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn generic_neutral_route_and_other_families_are_not_reclassified() {
    let mut c=request_fixture();c["people_transfer"].as_object_mut().unwrap().remove("eye_bag");
    assert!(command(&c).is_ok());assert!(binding(&c).unwrap().is_none());assert!(!read_only(&c));
    for action in ["collarbone_visual","face_style_visual","portrait_cohort_visual"] {
        let mut c=image_request_fixture();c["action"]=json!(action);assert!(command(&c).is_ok());assert!(binding(&c).unwrap().is_none());
    }
    let mut c=request_fixture();c["people_transfer"]["target_policy"]=json!("persistent_association");assert!(command(&c).is_err());
}
#[test] fn epoch_action_and_request_registration_cannot_be_reused() {
    let c=commit_fixture();let v=terminal(&c);let mut h=host([155;16]);h.begin_command([155;16],&c).unwrap();
    h.receive([156;16],&v);assert_eq!(h.status("eye-commit")["phase"],"pending");
    let mut bad=v.clone();bad["action"]=json!("preflight");h.receive([155;16],&bad);
    bad=v.clone();bad["request_id"]=json!("other");h.receive([155;16],&bad);assert_eq!(h.status("eye-commit")["phase"],"pending");
    h.receive([155;16],&v);assert_eq!(h.status("eye-commit")["result"],v);assert!(h.begin_command([155;16],&c).is_err());
}
#[test] fn ordered_ack_is_not_a_set_and_noop_can_coexist_with_applied() {
    let mut c=commit_fixture();let mut second=c[ACK][0].clone();second["document_id"]=json!("c".repeat(32));second["replace_legacy"]=json!(true);
    c[ACK].as_array_mut().unwrap().push(second);let mut v=terminal(&c);
    let mut row=v["target_outcomes"][0].clone();row["document_id"]=json!("c".repeat(32));row["index"]=json!(2);
    row["result_revision"]=json!("3");row["outcome"]=json!("noop");v["target_outcomes"].as_array_mut().unwrap().push(row);
    assert!(receipt(&v));let mut h=host([158;16]);h.begin_command([158;16],&c).unwrap();v[ACK].as_array_mut().unwrap().reverse();
    assert!(receipt(&v));h.receive([158;16],&v);assert_eq!(h.status("eye-commit")["result"]["outcome_unknown"],true);
}
#[test] fn invalid_eye_envelope_cannot_fall_through_collarbone_read_only() {
    let mut c=request_fixture();c["module_scope"]=json!([collarbone::OP,OP]);
    c["people_transfer"]["selection"][collarbone::OP]=json!(["/amount"]);assert!(crate::batch_api::read_only(&c));
    c["people_transfer"]["eye_bag"]["targets"][0]["replace_legacy"]=json!("yes");
    assert!(!crate::batch_api::read_only(&c));assert!(!collarbone::read_only(&c));assert!(collarbone::command(&c).is_err());
}
#[test] fn no_target_is_silently_rejected_or_unbounded() {
    let mut v=review_fixture();v["policy"]=json!("skip_and_report");v["targets"]=json!([]);v["ok"]=json!(0);
    v["rejected_docs"]=json!([{"doc":"b".repeat(32),"error":"Missing"}]);assert!(!receipt(&v));
    let mut c=request_fixture();let template=c["people_transfer"]["targets"][0].clone();
    let targets:Vec<Value>=(0..17).map(|n|{let mut row=template.clone();row["target"]["document"]["document_id"]=json!(format!("{n:032x}"));row}).collect();
    c["docs"]=json!(targets.iter().map(|r|r["target"]["document"]["document_id"].clone()).collect::<Vec<_>>());
    c["people_transfer"]["eye_bag"]["targets"]=json!(targets.iter().map(|r|json!({"document_id":r["target"]["document"]["document_id"],"replace_legacy":false})).collect::<Vec<_>>());
    c["people_transfer"]["targets"]=json!(targets);assert!(command(&c).is_err());assert!(!read_only(&c));
}
#[test] fn shared_source_aliases_cannot_choose_conflicting_legacy_replacement() {
    let mut c=request_fixture();let mut alias=c["people_transfer"]["targets"][0].clone();alias["target"]["document"]["document_id"]=json!("c".repeat(32));
    c["people_transfer"]["targets"].as_array_mut().unwrap().push(alias);c["docs"].as_array_mut().unwrap().push(json!("c".repeat(32)));
    c["people_transfer"]["eye_bag"]["targets"].as_array_mut().unwrap().push(json!({"document_id":"c".repeat(32),"replace_legacy":true}));
    assert!(command(&c).is_err());c["people_transfer"]["eye_bag"]["targets"][1]["replace_legacy"]=json!(false);assert!(command(&c).is_ok());
    // An independent copy with identical bytes is a separate reviewed owner.
    c["people_transfer"]["targets"][1]["target"]["people_scope"]=json!("c".repeat(32));
    c["people_transfer"]["eye_bag"]["targets"][1]["replace_legacy"]=json!(true);assert!(command(&c).is_ok());
}
