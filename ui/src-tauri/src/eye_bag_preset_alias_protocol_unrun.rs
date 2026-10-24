// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic v2 transport fixtures, not photographic evidence.
use super::*;
use serde_json::json;
use crate::preset_api::eye_bag as preset;
use crate::receipt_host::ReceiptKind;

fn rehash(value: &mut Value) {
    let wrapper = &mut value["eye_bag_preset"];
    wrapper.as_object_mut().unwrap().remove("review_sha256");
    wrapper["review_sha256"] = json!(crate::batch_api::collarbone::request_digest(wrapper));
}
fn review_fixture() -> Value {
    let source = json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let face = json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":2});
    let coverage = json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face,
        "scope":"target-reviewed-ridge","ridge_sha256":"b".repeat(64),"sides":["left"]}]});
    let image = json!({"mime":"image/png","width":1024,"height":512,"sha256":"c".repeat(64)});
    let active = json!({"version":1,"document_id":"logical-active","revision":"3","source_proof":source,
        "before_state_sha256":"d".repeat(64),"candidate_state_sha256":"e".repeat(64),
        "before_people_sha256":"f".repeat(64),"candidate_people_sha256":"1".repeat(64),"source_size":[2048,1024],
        "before_output_size":[2048,1024],"after_output_size":[2048,1024],
        "coverage_sha256":crate::batch_api::collarbone::request_digest(&coverage),"before":image,"after":image});
    let mut sibling = active.clone();
    sibling["document_id"] = json!("logical-sibling"); sibling["revision"] = json!("9");
    sibling["source_proof"] = json!({"asset_sha256":"a".repeat(64),"original_sha256":"9".repeat(64),
        "creative_source":{"sha256":"a".repeat(64),"width":2048,"height":1024}});
    sibling["before_state_sha256"] = json!("8".repeat(64)); sibling["candidate_state_sha256"] = json!("8".repeat(64));
    sibling["before_output_size"] = json!([512,256]); sibling["after_output_size"] = json!([512,256]);
    for side in ["before", "after"] { sibling[side]["width"] = json!(512); sibling[side]["height"] = json!(256); }
    let mut value = json!({"event":"preset_result","protocol":1,"action":"preflight","request_id":"alias-preflight",
        "id":"mixed-preset","document_id":"load-active","revision":"3","success":true,"outcome_unknown":false,
        "preflight_token":"f".repeat(32),"module_scope":[preset::OP,"lnx.exposure.v1"],"eye_bag_replace_legacy":false,
        "applies":{(preset::OP):{"recipe":{"version":2,"amount":0.3,"preserve":1.0}},"lnx.exposure.v1":{"exposure":0.25}},
        "source_proof":source,"eye_bag_preset":{"version":2,"preset_sha256":"2".repeat(64),"applies_sha256":"3".repeat(64),
            "load_id":"load-active","owner":{"document":{"document_id":"logical-active","epoch":"workspace","revision":3},
            "people_scope":"project","state_revision":4,"association_revision":2,"graph_sha256":"4".repeat(64),"source_proof":source},
            "face_ref":face,"coverage":coverage,"visual":active,"replace_legacy":false,
            "members":[{"path":"/same.raw","role":"active","visual":active},{"path":"/same.raw","role":"sibling","visual":sibling}]}});
    rehash(&mut value); value
}
fn ack(value: &Value) -> Value {
    let wrapper = &value["eye_bag_preset"];
    json!({"review_sha256":wrapper["review_sha256"],"preset_sha256":wrapper["preset_sha256"],
        "applies_sha256":wrapper["applies_sha256"],"replace_legacy":wrapper["replace_legacy"],
        "members":wrapper["members"].as_array().unwrap().iter().map(|member| {
            let v = &member["visual"];
            json!({"document_id":v["document_id"],"revision":v["revision"],"before_sha256":v["before"]["sha256"],
                "after_sha256":v["after"]["sha256"],"coverage_sha256":v["coverage_sha256"]})
        }).collect::<Vec<_>>()})
}
fn command() -> Value {
    json!({"cmd":"preset","action":"apply","request_id":"preset-alias-apply","id":"mixed-preset",
        "document_id":"load-active","preflight_token":"f".repeat(32),(ACK):ack(&review_fixture())})
}
fn result(command: &Value) -> Value {
    let mut value = command.clone(); value.as_object_mut().unwrap().remove("cmd");
    value["event"] = json!("preset_result"); value["protocol"] = json!(1);
    value["success"] = json!(true); value["outcome_unknown"] = json!(false);
    value["module_scope"] = json!([preset::OP,"lnx.exposure.v1"]);
    value["before"] = json!({(preset::OP):{},"lnx.exposure.v1":{}}); value["after"] = value["before"].clone();
    value["batch_id"] = json!("composite-batch");
    value["alias_members"] = json!([{"document_id":"logical-active","expected_revision":"3","result_revision":"4"},
        {"document_id":"logical-sibling","expected_revision":"9","result_revision":"10"}]);
    value[MARKER] = json!({"version":1,"review_sha256":command[ACK]["review_sha256"],
        "preset_sha256":command[ACK]["preset_sha256"],"applies_sha256":command[ACK]["applies_sha256"],
        "current_document_id":"logical-active","member_count":2,"selected_modules":value["module_scope"]});
    value["doc_state"] = json!({"document_id":"load-active","people":{"binding":{
        "document_id":"logical-active","document_revision":4}}}); value
}
fn host(epoch: [u8;16]) -> crate::preset_host::PresetHost {
    let mut host = crate::preset_host::PresetHost::default(); host.reset(epoch); host.ready(epoch, true); host
}

#[test] fn v2_retains_actual_member_provenance_and_distinct_full_crops() {
    let value = review_fixture(); assert!(review(&value)); assert!(preset::receipt(&value));
    assert!(crate::preset_host::PresetKind::valid(&value, Some("load-active")));
    assert_ne!(value["eye_bag_preset"]["members"][1]["visual"]["source_proof"], value["source_proof"]);
    assert_ne!(value["eye_bag_preset"]["members"][1]["visual"]["before_output_size"], value["eye_bag_preset"]["visual"]["before_output_size"]);
    assert!(acknowledgment(&ack(&value))); assert!(preset::command(&command()).is_ok());
}
#[test] fn rehashed_shape_changes_cannot_clone_active_recipe_or_replace_source_ownership() {
    for (path, replacement) in [
        ("/eye_bag_preset/members/1/role",json!("active")),
        ("/eye_bag_preset/members/1/visual/document_id",json!("logical-active")),
        ("/eye_bag_preset/members/1/visual/candidate_state_sha256",json!("e".repeat(64))),
        ("/eye_bag_preset/members/1/visual/candidate_people_sha256",json!("e".repeat(64))),
        ("/eye_bag_preset/members/1/visual/after_output_size",json!([512,128])),
        ("/eye_bag_preset/members/1/visual/source_proof/creative_source/sha256",json!("9".repeat(64))),
        ("/eye_bag_preset/members/1/visual/source_proof/creative_source/width",json!(1024)),
        ("/eye_bag_preset/members/1/visual/coverage_sha256",json!("9".repeat(64))),
        ("/eye_bag_preset/members/1/visual/revision",json!("09")),
        ("/eye_bag_preset/members/1/visual/revision",json!("9007199254740991")),
        ("/eye_bag_preset/owner/people_scope",json!("logical-active"))] {
        let mut bad = review_fixture(); *bad.pointer_mut(path).unwrap() = replacement; rehash(&mut bad);
        assert!(!review(&bad), "{path}");
    }
    let mut bad = review_fixture(); bad["eye_bag_preset"]["members"].as_array_mut().unwrap().reverse(); rehash(&mut bad); assert!(!review(&bad));
    let mut bad = review_fixture(); bad["eye_bag_preset"]["review_sha256"] = json!("0".repeat(64)); assert!(!review(&bad));
}
#[test] fn complete_alias_set_is_bounded_without_silently_dropping_siblings() {
    let mut value = review_fixture();
    for n in 2..16 {
        let mut member = value["eye_bag_preset"]["members"][1].clone();
        member["visual"]["document_id"] = json!(format!("sibling-{n}"));
        value["eye_bag_preset"]["members"].as_array_mut().unwrap().push(member);
    }
    rehash(&mut value); assert!(review(&value)); assert!(acknowledgment(&ack(&value)));
    let extra = value["eye_bag_preset"]["members"][1].clone();
    value["eye_bag_preset"]["members"].as_array_mut().unwrap().push(extra); rehash(&mut value);
    assert!(!review(&value)); assert!(!acknowledgment(&ack(&value)));
    let mut changed = ack(&review_fixture()); changed["members"][1]["extra"] = json!(true); assert!(!acknowledgment(&changed));
    changed = ack(&review_fixture()); changed["members"].as_array_mut().unwrap().pop(); assert!(!acknowledgment(&changed));
}
#[test] fn exact_publication_requires_real_batch_all_revisions_and_composite_marker() {
    let c = command(); let value = result(&c); assert!(receipt(&value));
    assert!(crate::preset_host::PresetKind::valid(&value, Some("load-active")));
    for (path, replacement) in [("/batch_id",Value::Null),("/alias_members/1/result_revision",json!("11")),
        ("/alias_members/1/expected_revision",json!("8")),("/alias_members/1/result_revision",json!("010")),
        ("/eye_bag_preset_alias_review/current_document_id",json!("load-active")),
        ("/eye_bag_preset_alias_review/member_count",json!(1)),("/eye_bag_preset_alias_review/review_sha256",json!("9".repeat(64))),
        ("/eye_bag_preset_alias_review/selected_modules",json!([preset::OP])),
        ("/doc_state/people/binding/document_id",json!("load-active")),("/doc_state/people/binding/document_revision",json!(3))] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
    }
    for key in ["batch_id", "alias_members", MARKER] { let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key); assert!(!receipt(&bad)); }
    let mut bad = value; bad["alias_members"].as_array_mut().unwrap().reverse(); assert!(!receipt(&bad));
}
#[test] fn unknown_write_keeps_exact_original_order_and_cannot_become_cancelled_success() {
    let c = command(); let value = result(&c); let epoch = [231;16]; let mut h = host(epoch);
    h.begin_command(epoch, &c).unwrap(); crate::project_recovery_fence::issued(epoch, &c).unwrap();
    let mut bad = value.clone(); bad[ACK]["members"].as_array_mut().unwrap().reverse();
    h.receive(epoch, &bad); let retained = h.status("preset-alias-apply");
    assert_eq!(retained["result"]["outcome_unknown"], true); assert_eq!(retained["result"][ACK], c[ACK]);
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    h.receive(epoch, &value); assert_eq!(h.status("preset-alias-apply"), retained);
    bad = value; bad["success"] = json!(false); bad["error"] = json!("Cancelled"); bad["eye_bag_cancelled"] = json!(true);
    h.receive(epoch, &bad); assert_eq!(h.status("preset-alias-apply"), retained);
    assert!(h.begin_command(epoch, &c).is_err()); crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened",
        "open":true,"path":"/verified/project.lrt","project_id":"new-workspace","docs":2,"dirty":false}));
}
#[test] fn refusal_requires_original_ack_identity_and_no_publication_claim() {
    let c = command(); let mut value = result(&c); value["success"] = json!(false); value["error"] = json!("Membership changed before claim");
    for key in ["batch_id", "alias_members", MARKER, "doc_state", "before", "after"] { value.as_object_mut().unwrap().remove(key); }
    assert!(receipt(&value)); let mut h = host([232;16]); h.begin_command([232;16], &c).unwrap(); h.receive([232;16], &value);
    assert_eq!(h.status("preset-alias-apply")["result"], value);
    let mut expired = value.clone(); expired.as_object_mut().unwrap().remove("module_scope");
    assert!(crate::preset_host::PresetKind::valid(&expired, Some("load-active")));
    let mut h = host([240;16]); h.begin_command([240;16], &c).unwrap(); h.receive([240;16], &expired);
    assert_eq!(h.status("preset-alias-apply")["result"], expired);
    let mut missing = value.clone(); missing.as_object_mut().unwrap().remove(ACK); missing.as_object_mut().unwrap().remove("module_scope");
    let mut h = host([233;16]); h.begin_command([233;16], &c).unwrap(); h.receive([233;16], &missing);
    assert_eq!(h.status("preset-alias-apply")["result"]["outcome_unknown"], true);
    value["batch_id"] = json!("claimed-batch"); assert!(!receipt(&value));
    value["outcome_unknown"] = json!(true); assert!(receipt(&value));
}

fn image_request() -> (Value, Value) {
    let source = json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let pair = crate::original_shadow_transfer_protocol::tests::sample_transfer(&json!("logical-sibling"), &json!("9"), &json!({}), &source);
    let image = pair["after"].clone();
    let request = json!({"cmd":"preset","action":"eye_bag_visual","request_id":"preset-alias-image","id":"mixed-preset",
        "document_id":"load-active","revision":"3","preflight_token":"f".repeat(32),"side":"after","sha256":image["sha256"],
        "member_document_id":"logical-sibling","member_revision":"9"});
    let mut receipt = request.clone(); receipt.as_object_mut().unwrap().remove("cmd");
    receipt["event"] = json!("preset_result"); receipt["protocol"] = json!(1); receipt["success"] = json!(true);
    receipt["outcome_unknown"] = json!(false); receipt["image"] = image; (request, receipt)
}
#[test] fn paged_image_reads_bind_both_active_load_and_exact_member_revision() {
    let (c, value) = image_request(); assert!(preset::command(&c).is_ok()); assert!(preset::read_only(&c));
    assert!(crate::preset_host::PresetKind::valid(&value, Some("load-active")));
    let identity = preset::binding(&c).unwrap().unwrap();
    assert_eq!(identity["member_document_id"], "logical-sibling"); assert_eq!(identity["revision"], "3");
    for key in ["member_document_id", "member_revision"] {
        let mut bad = c.clone(); bad.as_object_mut().unwrap().remove(key); assert!(preset::command(&bad).is_err());
    }
    for (key, changed) in [("member_revision",json!("09")),("member_revision",json!(9)),
        ("member_document_id",Value::Null),("path",json!("/arbitrary.raw")),("side",json!("support")),("revision",json!("9007199254740991"))] {
        let mut bad = c.clone(); bad[key] = changed; assert!(preset::command(&bad).is_err()); assert!(!preset::read_only(&bad));
    }
    let mut h = host([234;16]); h.begin_command([234;16], &c).unwrap();
    h.receive([235;16], &value); assert_eq!(h.status("preset-alias-image")["phase"], "pending");
    let mut bad = value.clone(); bad["member_document_id"] = json!("logical-active"); h.receive([234;16], &bad);
    let retained = h.status("preset-alias-image"); assert_eq!(retained["result"]["outcome_unknown"], true);
    assert_eq!(retained["result"]["member_document_id"], c["member_document_id"]);
    h.receive([234;16], &value); assert_eq!(h.status("preset-alias-image"), retained);
    let epoch = [236;16]; crate::project_recovery_fence::issued(epoch, &c).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn member_images_require_canonical_png_bytes_and_cannot_widen_v1_identity() {
    let (c, value) = image_request();
    let mut bad = value.clone(); bad["image"]["base64"] = json!("iVBORw=="); assert!(!preset::receipt(&bad));
    bad = value.clone(); bad["image"]["sha256"] = json!("0".repeat(64)); assert!(!preset::receipt(&bad));
    let mut v1 = c; for key in ["member_document_id", "member_revision"] { v1.as_object_mut().unwrap().remove(key); }
    assert!(preset::command(&v1).is_ok()); let mut h = host([237;16]); h.begin_command([237;16], &v1).unwrap();
    h.receive([237;16], &value); assert_eq!(h.status("preset-alias-image")["result"]["outcome_unknown"], true);
    let mut legacy = review_fixture(); let wrapper = &mut legacy["eye_bag_preset"];
    wrapper["version"] = json!(1); for key in ["members", "review_sha256"] { wrapper.as_object_mut().unwrap().remove(key); }
    assert!(preset::review(&legacy));
}
#[test] fn unknown_retains_only_validated_group_identity_without_becoming_complete() {
    let c = command(); let mut value = result(&c); value["success"] = json!(false);
    value["outcome_unknown"] = json!(true); value["error"] = json!("Postpublication status unavailable");
    value.as_object_mut().unwrap().remove("doc_state"); value["untrusted_padding"] = json!("x".repeat(100_000));
    let mut h = host([241;16]); h.begin_command([241;16], &c).unwrap(); h.receive([241;16], &value);
    let retained = h.status("preset-alias-apply")["result"].clone(); assert_eq!(retained["outcome_unknown"], true);
    for key in ["batch_id", "alias_members", MARKER, ACK, "module_scope"] { assert_eq!(retained[key], value[key]); }
    assert!(preset::receipt(&retained));
    assert!(retained.get("untrusted_padding").is_none()); assert!(retained.get("doc_state").is_none());
    let mut batch_only = value.clone(); for key in ["alias_members", MARKER] { batch_only.as_object_mut().unwrap().remove(key); }
    let mut h = host([242;16]); h.begin_command([242;16], &c).unwrap(); h.receive([242;16], &batch_only);
    assert_eq!(h.status("preset-alias-apply")["result"]["batch_id"], "composite-batch");
    assert!(h.status("preset-alias-apply")["result"].get("alias_members").is_none());
    for pointer in ["/eye_bag_preset_ack/review_sha256", "/eye_bag_preset_alias_review/review_sha256", "/alias_members/1/result_revision"] {
        let mut bad = value.clone(); *bad.pointer_mut(pointer).unwrap() = json!("invalid");
        let mut h = host([243;16]); h.begin_command([243;16], &c).unwrap(); h.receive([243;16], &bad);
        let result = h.status("preset-alias-apply")["result"].clone(); assert_eq!(result["outcome_unknown"], true);
        assert_eq!(result[ACK], c[ACK]); for key in ["batch_id", "alias_members", MARKER] { assert!(result.get(key).is_none()); }
    }
}
