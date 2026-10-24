// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic protocol fixtures, not render/build acceptance.
use super::*;
use serde_json::json;
use crate::{preset_api::face_decoration as preset, receipt_host::ReceiptKind};

fn rehash(value: &mut Value) {
    let wrapper = &mut value["face_decoration_preset"];
    wrapper.as_object_mut().unwrap().remove("review_sha256");
    wrapper["review_sha256"] = json!(crate::batch_api::collarbone::request_digest(wrapper));
}
fn review_fixture() -> Value {
    let source = json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
    let face = json!({"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":2});
    let coverage = json!({"version":1,"support_transfer":"none","targets":[{"face_ref":face,
        "scope":"target-reviewed-visible-skin","visibility_sha256":"b".repeat(64),"recipe_sha256":"7".repeat(64)}]});
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
        "preflight_token":"f".repeat(32),"module_scope":[preset::OP,"lnx.exposure.v1"],"face_decoration_visual_required":true,
        "applies":{(preset::OP):{"recipe":{"version":1,"pattern":"freckle_dust","strength":0.5}},"lnx.exposure.v1":{"exposure":0.25}},
        "source_proof":source,"face_decoration_preset":{"version":2,"preset_sha256":"2".repeat(64),"applies_sha256":"3".repeat(64),
            "load_id":"load-active","owner":{"document":{"document_id":"logical-active","epoch":"workspace","revision":3},
            "people_scope":"project","state_revision":4,"association_revision":2,"graph_sha256":"4".repeat(64),"source_proof":source},
            "face_ref":face,"coverage":coverage,"visual":active,"before_bank_sha256":"5".repeat(64),
            "members":[{"path":"/same.raw","role":"active","visual":active},{"path":"/same.raw","role":"sibling","visual":sibling}]}});
    rehash(&mut value); value
}
fn ack(value: &Value) -> Value {
    let wrapper = &value["face_decoration_preset"];
    json!({"review_sha256":wrapper["review_sha256"],"preset_sha256":wrapper["preset_sha256"],"applies_sha256":wrapper["applies_sha256"],
        "members":wrapper["members"].as_array().unwrap().iter().map(|member| {
            let v = &member["visual"];
            json!({"document_id":v["document_id"],"revision":v["revision"],"before_sha256":v["before"]["sha256"],
                "after_sha256":v["after"]["sha256"],"coverage_sha256":v["coverage_sha256"]})
        }).collect::<Vec<_>>()})
}
fn command() -> Value {
    json!({"cmd":"preset","action":"apply","request_id":"decoration-alias-apply","id":"mixed-preset",
        "document_id":"load-active","preflight_token":"f".repeat(32),(ACK):ack(&review_fixture())})
}
fn result(command: &Value) -> Value {
    let mut value = command.clone(); value.as_object_mut().unwrap().remove("cmd");
    value["event"] = json!("preset_result"); value["protocol"] = json!(1);
    value["success"] = json!(true); value["outcome_unknown"] = json!(false); value["face_decoration_visual_required"] = json!(true);
    value["module_scope"] = json!([preset::OP,"lnx.exposure.v1"]);
    value["before"] = json!({(preset::OP):{},"lnx.exposure.v1":{}}); value["after"] = value["before"].clone();
    value["batch_id"] = json!("decoration-composite");
    value["alias_members"] = json!([{"document_id":"logical-active","expected_revision":"3","result_revision":"4"},
        {"document_id":"logical-sibling","expected_revision":"9","result_revision":"10"}]);
    value[ALIAS_MARKER] = json!({"version":1,"review_sha256":command[ACK]["review_sha256"],
        "preset_sha256":command[ACK]["preset_sha256"],"applies_sha256":command[ACK]["applies_sha256"],
        "current_document_id":"logical-active","member_count":2,"selected_modules":value["module_scope"]});
    value["doc_state"] = json!({"document_id":"load-active","people":{"binding":{"document_id":"logical-active","document_revision":4}}}); value
}
fn host(epoch: [u8;16]) -> crate::preset_host::PresetHost {
    let mut h = crate::preset_host::PresetHost::default(); h.reset(epoch); h.ready(epoch, true); h
}
fn epoch(tag: u8) -> [u8;16] { let mut value = [71;16]; value[15] = tag; value }
fn opened() -> Value { json!({"event":"project_opened","open":true,"path":"/project.lrt","project_id":"verified","docs":2,"dirty":false}) }

#[test] fn all_members_keep_original_provenance_and_own_nonportrait_recipe() {
    let value = review_fixture(); assert!(review(&value)); assert!(preset::receipt(&value));
    assert!(crate::preset_host::PresetKind::valid(&value, Some("load-active")));
    assert_ne!(value["face_decoration_preset"]["members"][1]["visual"]["source_proof"], value["source_proof"]);
    assert_ne!(value["face_decoration_preset"]["members"][1]["visual"]["before_output_size"], value["face_decoration_preset"]["visual"]["before_output_size"]);
    assert!(acknowledgment(&ack(&value))); assert!(preset::command(&command()).is_ok());
    let mut retained = value; retained["module_scope"] = json!(["lnx.exposure.v1"]);
    retained["applies"].as_object_mut().unwrap().remove(preset::OP);
    assert!(crate::preset_host::PresetKind::valid(&retained, Some("load-active")));
}
#[test] fn rehash_cannot_authorize_cloned_recipe_or_wrong_member_support_source() {
    for (path, replacement) in [
        ("/face_decoration_preset/members/1/role",json!("active")),
        ("/face_decoration_preset/members/1/visual/document_id",json!("logical-active")),
        ("/face_decoration_preset/members/1/visual/candidate_state_sha256",json!("e".repeat(64))),
        ("/face_decoration_preset/members/1/visual/candidate_people_sha256",json!("e".repeat(64))),
        ("/face_decoration_preset/members/1/visual/after_output_size",json!([512,128])),
        ("/face_decoration_preset/members/1/visual/source_proof/creative_source/sha256",json!("9".repeat(64))),
        ("/face_decoration_preset/members/1/visual/source_proof/creative_source/width",json!(1024)),
        ("/face_decoration_preset/members/1/visual/coverage_sha256",json!("9".repeat(64))),
        ("/face_decoration_preset/members/1/visual/revision",json!("09")),
        ("/face_decoration_preset/members/1/visual/revision",json!("9007199254740991")),
        ("/face_decoration_preset/before_bank_sha256",Value::Null),
        ("/face_decoration_preset/owner/people_scope",json!("logical-active"))] {
        let mut bad = review_fixture(); *bad.pointer_mut(path).unwrap() = replacement; rehash(&mut bad); assert!(!review(&bad), "{path}");
    }
    let mut bad = review_fixture(); bad["face_decoration_preset"]["members"].as_array_mut().unwrap().reverse(); rehash(&mut bad); assert!(!review(&bad));
    let mut bad = review_fixture(); bad["face_decoration_preset"]["before_bank_sha256"] = json!("0".repeat(64)); assert!(!review(&bad));
    for key in ["face_style_alias_review", "face_decoration_support_alias_review", "eye_bag_preset_alias_review"] {
        let mut bad = review_fixture(); bad[key] = json!({}); assert!(!review(&bad));
    }
}
#[test] fn complete_member_set_is_bounded_without_subset_fallback() {
    let mut value = review_fixture();
    for n in 2..16 { let mut member = value["face_decoration_preset"]["members"][1].clone();
        member["visual"]["document_id"] = json!(format!("sibling-{n}")); value["face_decoration_preset"]["members"].as_array_mut().unwrap().push(member); }
    rehash(&mut value); assert!(review(&value)); assert!(acknowledgment(&ack(&value)));
    let extra = value["face_decoration_preset"]["members"][1].clone(); value["face_decoration_preset"]["members"].as_array_mut().unwrap().push(extra);
    rehash(&mut value); assert!(!review(&value)); assert!(!acknowledgment(&ack(&value)));
    let mut changed = ack(&review_fixture()); changed["members"].as_array_mut().unwrap().pop(); assert!(!acknowledgment(&changed));
    changed = ack(&review_fixture()); changed["members"][1]["extra"] = json!(true); assert!(!acknowledgment(&changed));
}
#[test] fn member_reads_bind_exact_load_token_revision_and_coordinates() {
    let c = json!({"cmd":"preset","action":"face_decoration_visual","request_id":"member-read","id":"mixed-preset",
        "document_id":"load-active","preflight_token":"f".repeat(32),"revision":"3","member_document_id":"logical-sibling",
        "member_revision":"9","side":"after","sha256":"c".repeat(64)});
    assert!(preset::command(&c).is_ok()); assert!(crate::preset_api::eye_bag::command(&c).is_ok());
    assert!(crate::preset_api::collarbone::command(&c).is_ok()); assert!(preset::read_only(&c));
    let bound = preset::binding(&c).unwrap().unwrap(); assert_eq!(bound["member_document_id"], "logical-sibling");
    for key in ["member_document_id", "member_revision"] { let mut bad = c.clone(); bad.as_object_mut().unwrap().remove(key); assert!(preset::command(&bad).is_err()); }
    let mut bad = c.clone(); bad["member_revision"] = json!("09"); assert!(preset::command(&bad).is_err());
    bad = c; bad["action"] = json!("apply"); assert!(preset::command(&bad).is_err());
}
#[test] fn exact_publication_requires_ordered_member_revisions_and_distinct_marker() {
    let c = command(); let value = result(&c); assert!(receipt(&value)); assert!(crate::preset_host::PresetKind::valid(&value, Some("load-active")));
    for (path, replacement) in [("/batch_id",Value::Null),("/alias_members/1/result_revision",json!("11")),
        ("/alias_members/1/expected_revision",json!("8")),("/alias_members/1/result_revision",json!("010")),
        ("/face_decoration_preset_alias_review/current_document_id",json!("load-active")),
        ("/face_decoration_preset_alias_review/member_count",json!(1)),("/face_decoration_preset_alias_review/review_sha256",json!("9".repeat(64))),
        ("/face_decoration_preset_alias_review/selected_modules",json!([preset::OP]))] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
    }
    let mut bad = value.clone(); bad["alias_members"].as_array_mut().unwrap().reverse(); assert!(!receipt(&bad));
    for key in ["face_style_alias_review", "eye_bag_preset_alias_review", "eye_bag_alias_review", "face_decoration_alias_review",
        "face_decoration_support_alias_review", "face_decoration_batch_review", "face_decoration_cohort_review"] {
        let mut bad = value.clone(); bad[key] = json!({}); assert!(!receipt(&bad), "{key}");
    }
    for key in ["no_write", "rolled_back", "requires_reload", "requires_readback"] { let mut bad = value.clone(); bad[key] = json!(true); assert!(!receipt(&bad)); }
    let mut retained = value; retained["module_scope"] = json!(["lnx.exposure.v1"]);
    retained[ALIAS_MARKER]["selected_modules"] = retained["module_scope"].clone(); assert!(receipt(&retained));
    retained[ALIAS_MARKER]["selected_modules"] = json!((0..33).map(|n| format!("op-{n}")).collect::<Vec<_>>()); assert!(!summary(&retained[ALIAS_MARKER]));
}
#[test] fn rejected_receipts_and_unknown_diagnostics_never_create_replay_authority() {
    let c = command(); let mut denied = c.clone(); denied.as_object_mut().unwrap().remove("cmd");
    denied["protocol"] = json!(1); denied["success"] = json!(false); denied["outcome_unknown"] = json!(false);
    denied["face_decoration_visual_required"] = json!(true); denied["error"] = json!("Frozen target changed");
    assert!(preset::receipt(&denied)); assert!(crate::preset_host::PresetKind::valid(&denied, Some("load-active")));
    let mut compensated = denied.clone(); compensated["rolled_back"] = json!(true); compensated["requires_reload"] = json!(false);
    assert!(preset::receipt(&compensated));
    for key in ["batch_id", "alias_members", ALIAS_MARKER, "before", "after", "doc_state"] {
        let mut bad = denied.clone(); bad[key] = Value::Null; assert!(!preset::receipt(&bad), "{key}");
    }
    let mut unknown = denied; unknown["outcome_unknown"] = json!(true); unknown["batch_id"] = json!("actual-batch");
    assert!(preset::receipt(&unknown)); assert_eq!(retained_publication(&unknown).unwrap()["batch_id"], "actual-batch");
    unknown["alias_members"] = result(&c)["alias_members"].clone(); assert!(!preset::receipt(&unknown));
    let mut complete = result(&c); complete["success"] = json!(false); complete["outcome_unknown"] = json!(true); complete["error"] = json!("Publication outcome unknown");
    assert!(preset::receipt(&complete)); assert_eq!(retained_publication(&complete).unwrap()[ALIAS_MARKER], complete[ALIAS_MARKER]);
    for key in ["no_write", "rolled_back"] { let mut bad = complete.clone(); bad[key] = json!(true); assert!(!preset::receipt(&bad)); }
}
#[test] fn invalid_publication_retains_original_ack_and_fences_until_verified_reopen() {
    let epoch = epoch(1); let c = command(); let mut h = host(epoch); h.begin_command(epoch, &c).unwrap();
    crate::project_recovery_fence::issued(epoch, &c).unwrap();
    let mut bad = result(&c); bad["alias_members"][1]["result_revision"] = json!("11"); h.receive(epoch, &bad);
    let retained = h.status("decoration-alias-apply"); assert_eq!(retained["result"]["outcome_unknown"], true);
    assert_eq!(retained["result"][ACK], c[ACK]); assert_eq!(retained["result"]["face_decoration_visual_required"], true);
    assert!(retained["result"].get(ALIAS_MARKER).is_none()); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    for write in [json!({"cmd":"project","action":"save"}),json!({"cmd":"export","path":"/out.png"}),json!({"cmd":"exposure","exposure":0.5})] {
        assert!(crate::project_recovery_fence::issued(epoch, &write).is_err());
    }
    assert!(crate::project_recovery_fence::issued(epoch, &json!({"cmd":"batch","action":"state"})).is_ok());
    h.receive(epoch, &result(&c)); assert_eq!(h.status("decoration-alias-apply"), retained);
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"})); assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &opened()); assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}
#[test] fn compact_unknown_preserves_only_valid_bound_publication() {
    let c = command(); let mut value = result(&c); value["success"] = json!(false); value["outcome_unknown"] = json!(true); value["error"] = json!("Readback needed");
    let mut h = host(epoch(2)); h.begin_command(epoch(2), &c).unwrap(); h.receive(epoch(2), &value);
    let retained = &h.status("decoration-alias-apply")["result"];
    assert_eq!(retained[ALIAS_MARKER], value[ALIAS_MARKER]); assert_eq!(retained["alias_members"], value["alias_members"]);
    assert_eq!(retained["module_scope"], value["module_scope"]); assert!(retained.get("doc_state").is_none());
}

fn workspace(epoch: [u8;16], name: &str) {
    crate::project_recovery_fence::observed(epoch, &json!({"event":"session_state","sync":{"workspace_generation":name,"batches":[]}}));
}
#[test] fn transport_first_unknown_settles_only_exact_original_terminal_in_same_workspace() {
    for tag in 10..12 {
        let e = epoch(tag); workspace(e, "original"); let c = command(); let mut h = host(e);
        h.begin_command(e, &c).unwrap(); crate::project_recovery_fence::issued(e, &c).unwrap();
        h.failed("decoration-alias-apply", "Transport outcome uncertain"); assert!(crate::project_recovery_fence::proof(e).is_err());
        let original = h.status("decoration-alias-apply"); let mut wrong = result(&c); wrong[ACK]["members"][1]["revision"] = json!("8");
        h.receive(e, &wrong); assert_eq!(h.status("decoration-alias-apply"), original);
        let mut value = result(&c);
        if tag == 11 {
            for key in ["batch_id", "alias_members", ALIAS_MARKER, "before", "after", "doc_state", "module_scope"] { value.as_object_mut().unwrap().remove(key); }
            value["success"] = json!(false); value["error"] = json!("Frozen member changed before write"); value["no_write"] = json!(true);
        }
        h.receive(e, &value); assert_eq!(h.status("decoration-alias-apply")["result"], value);
        assert!(crate::project_recovery_fence::proof(e).is_ok()); assert!(h.begin_command(e, &c).is_err());
        crate::project_recovery_fence::observed(e, &opened());
    }
}
#[test] fn engine_unknown_or_changed_workspace_cannot_gain_late_terminal_authority() {
    for tag in 12..15 {
        let e = epoch(tag); workspace(e, "original"); let c = command(); let mut h = host(e);
        h.begin_command(e, &c).unwrap(); crate::project_recovery_fence::issued(e, &c).unwrap(); h.failed("decoration-alias-apply", "Transport uncertain");
        if tag == 12 {
            let mut unknown = result(&c); unknown["success"] = json!(false); unknown["outcome_unknown"] = json!(true); unknown["error"] = json!("Engine cannot prove publication");
            h.receive(e, &unknown); assert_eq!(h.status("decoration-alias-apply")["result"][ALIAS_MARKER], unknown[ALIAS_MARKER]);
        } else if tag == 13 { workspace(e, "another-workspace"); }
        else { crate::project_recovery_fence::observed(e, &opened()); }
        let retained = h.status("decoration-alias-apply"); h.receive(e, &result(&c)); assert_eq!(h.status("decoration-alias-apply"), retained);
        if tag != 14 { assert!(crate::project_recovery_fence::proof(e).is_err()); }
        crate::project_recovery_fence::observed(e, &opened());
    }
}
