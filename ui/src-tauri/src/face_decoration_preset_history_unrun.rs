// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Reopened composite history and immutable unknown fixtures.
use super::*;
fn epoch(tag: u8) -> [u8;16] { let mut epoch = [72;16]; epoch[15] = tag; epoch }
fn marker() -> Value {
    json!({"version":1,"review_sha256":"a".repeat(64),"preset_sha256":"b".repeat(64),"applies_sha256":"c".repeat(64),
        "current_document_id":"active","member_count":2,"selected_modules":["lnx.exposure.v1"]})
}
fn request() -> Value { json!({"cmd":"batch","action":"undo","request_id":"decoration-history","batch_id":"decoration-composite"}) }
fn result(c: &Value) -> Value {
    json!({"event":"batch_result","action":c["action"],"request_id":c["request_id"],"batch_id":c["batch_id"],
        "success":true,"outcome_unknown":false,"module_scope":["lnx.people_graph.v1"],"restored":[0,3],"conflicts":[],(DECORATION_PRESET):marker()})
}
fn status() -> Value {
    json!({"event":"session_state","sync":{"workspace_generation":"decoration-workspace","batches":[{
        "batch_id":"decoration-composite","module_scope":["lnx.people_graph.v1"],"targets":2,"undone":false,(DECORATION_PRESET):marker()}]}})
}
fn opened() -> Value { json!({"event":"project_opened","open":true,"path":"/verified.lrt","project_id":"new","docs":2,"dirty":false}) }
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut host = crate::batch_host::BatchHost::default(); host.reset(epoch); host.ready(epoch, true); host
}
#[test] fn exact_history_accepts_retained_decoration_without_new_recipe_authority() {
    for action in ["undo", "redo"] {
        let mut c = request(); c["action"] = json!(action); let value = result(&c); assert!(receipt(&value));
        for field in [DECORATION_PRESET, "face_decoration_preset_ack", "alias_members", "selected_modules"] {
            let mut unauthorized = c.clone(); unauthorized[field] = json!({}); assert!(command(&unauthorized).is_err());
        }
    }
    let value = result(&request());
    for (path, replacement) in [("/restored",json!([0])),("/restored",json!([0,0])),("/module_scope",json!(["lnx.exposure.v1"])),
        ("/conflicts",json!([{"index":3,"path":"/same.raw","reason":"Sibling changed"}])),
        ("/face_decoration_preset_alias_review/member_count",json!(17)),
        ("/face_decoration_preset_alias_review/selected_modules",json!(["lnx.exposure.v1","lnx.exposure.v1"]))] {
        let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = replacement; assert!(!receipt(&bad), "{path}");
    }
    for field in ["face_style_alias_review", "face_decoration_alias_review", "face_decoration_support_alias_review",
        "face_decoration_cohort_review", "face_decoration_batch_review", "eye_bag_preset_alias_review", "eye_bag_alias_review",
        "eye_bag_cohort_review", "eye_bag_batch_review", "eye_bag_recovery_alias_review"] {
        let mut bad = value.clone(); bad[field] = json!({"version":1,"review_sha256":"a".repeat(64),"member_count":2}); assert!(!receipt(&bad), "{field}");
    }
}
#[test] fn no_write_and_compensated_failures_need_exact_empty_restore_proof() {
    let mut value = result(&request()); value["success"] = json!(false); value["error"] = json!("Protected member changed");
    value["restored"] = json!([]); value["no_write"] = json!(true); assert!(receipt(&value));
    value["no_write"] = json!(false); value["rolled_back"] = json!(true); assert!(receipt(&value));
    for (field, replacement) in [("restored",json!([0])),("module_scope",json!(["lnx.exposure.v1"])),("no_write",json!(true)),("rolled_back",json!(false))] {
        let mut bad = value.clone(); bad[field] = replacement; assert!(!receipt(&bad), "{field}");
    }
    value["outcome_unknown"] = json!(true); assert!(!receipt(&value)); value["rolled_back"] = json!(false);
    assert!(!receipt(&value)); value.as_object_mut().unwrap().remove("restored"); assert!(receipt(&value));
}
#[test] fn restored_summary_requires_exact_marker_through_native_mailbox() {
    let e = epoch(1); let c = request(); crate::project_recovery_fence::observed(e, &status());
    let markers = crate::project_recovery_fence::shared_history_markers(e, &c).unwrap().unwrap(); assert_eq!(markers[DECORATION_PRESET], marker());
    let mut h = host(e); h.begin_command(e, &c).unwrap(); crate::project_recovery_fence::issued(e, &c).unwrap();
    let mut missing = result(&c); missing.as_object_mut().unwrap().remove(DECORATION_PRESET); h.receive(e, &missing);
    let retained = h.status("decoration-history"); assert_eq!(retained["result"]["outcome_unknown"], true);
    assert_eq!(retained["result"][DECORATION_PRESET], marker()); assert_eq!(retained["result"]["module_scope"], json!(["lnx.people_graph.v1"]));
    h.receive(e, &result(&c)); assert_eq!(h.status("decoration-history"), retained);
    assert!(crate::project_recovery_fence::issued(e, &json!({"cmd":"project","action":"save"})).is_err());
    crate::project_recovery_fence::observed(e, &json!({"event":"project_opened"})); assert!(crate::project_recovery_fence::proof(e).is_err());
    crate::project_recovery_fence::observed(e, &opened()); assert!(crate::project_recovery_fence::proof(e).is_ok());
}
#[test] fn malformed_missing_or_changed_summary_cannot_launder_known_history() {
    for tag in 2..5 {
        let e = epoch(tag); let c = request(); let mut changed = status(); crate::project_recovery_fence::observed(e, &changed);
        match tag {
            2 => { changed["sync"]["batches"][0].as_object_mut().unwrap().remove(DECORATION_PRESET); },
            3 => { changed["sync"]["batches"][0][DECORATION_PRESET]["review_sha256"] = json!("invalid"); },
            _ => { changed["sync"]["batches"][0][DECORATION_PRESET]["review_sha256"] = json!("d".repeat(64)); },
        }
        crate::project_recovery_fence::observed(e, &changed); assert!(crate::project_recovery_fence::shared_history_markers(e, &c).is_err());
        changed["sync"]["batches"][0].as_object_mut().unwrap().remove(DECORATION_PRESET);
        crate::project_recovery_fence::observed(e, &changed); assert!(crate::project_recovery_fence::issued(e, &c).is_err());
        crate::project_recovery_fence::observed(e, &opened());
    }
}
#[test] fn complete_history_and_no_write_terminal_settle_only_original_request() {
    for tag in 5..7 {
        let e = epoch(tag); let c = request(); crate::project_recovery_fence::observed(e, &status());
        let mut h = host(e); h.begin_command(e, &c).unwrap(); crate::project_recovery_fence::issued(e, &c).unwrap();
        let mut value = result(&c);
        if tag == 6 { value["success"] = json!(false); value["error"] = json!("Sibling changed"); value["no_write"] = json!(true); value["restored"] = json!([]); }
        h.receive(e, &value); assert_eq!(h.status("decoration-history")["result"], value); assert!(crate::project_recovery_fence::proof(e).is_ok());
        assert!(h.begin_command(e, &c).is_err()); crate::project_recovery_fence::observed(e, &opened());
    }
}
#[test] fn transport_first_history_unknown_reconciles_exact_marker_and_workspace_only() {
    for tag in 10..15 {
        let e = epoch(tag); let c = request(); crate::project_recovery_fence::observed(e, &status());
        let mut h = host(e); h.begin_command(e, &c).unwrap(); crate::project_recovery_fence::issued(e, &c).unwrap();
        h.failed("decoration-history", "History transport outcome uncertain");
        let frozen = h.status("decoration-history"); assert_eq!(frozen["result"]["no_write"], false);
        let mut wrong = result(&c); wrong[DECORATION_PRESET]["review_sha256"] = json!("f".repeat(64)); h.receive(e, &wrong);
        assert_eq!(h.status("decoration-history"), frozen);
        if tag == 11 {
            let mut changed = status(); changed["sync"]["workspace_generation"] = json!("other-workspace"); crate::project_recovery_fence::observed(e, &changed);
        } else if tag == 12 {
            let mut unknown = result(&c); unknown["success"] = json!(false); unknown["outcome_unknown"] = json!(true);
            unknown["error"] = json!("Engine outcome uncertain"); unknown["no_write"] = json!(false); unknown.as_object_mut().unwrap().remove("restored");
            h.receive(e, &unknown);
        } else if tag == 13 {
            let mut changed = status(); changed["sync"]["batches"][0].as_object_mut().unwrap().remove(DECORATION_PRESET);
            crate::project_recovery_fence::observed(e, &changed);
        } else if tag == 14 { crate::project_recovery_fence::observed(e, &opened()); }
        let retained = h.status("decoration-history"); let value = result(&c); h.receive(e, &value);
        if tag == 10 { assert_eq!(h.status("decoration-history")["result"], value); assert!(crate::project_recovery_fence::proof(e).is_ok()); }
        else { assert_eq!(h.status("decoration-history"), retained); }
        crate::project_recovery_fence::observed(e, &opened());
    }
}
