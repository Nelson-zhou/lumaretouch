// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Native pending admission, not engine/runtime acceptance.
use super::*;
use super::super::{issued, observed, proof};
use serde_json::json;

fn epoch(tag: u8) -> [u8;16] { let mut value = [247;16]; value[15] = tag; value }
fn request() -> Value {
    json!({"cmd":"preset","action":"apply","request_id":"composite-original","id":"mixed-preset",
        "document_id":"load-active","preflight_token":"f".repeat(32),"eye_bag_preset_ack":{
            "review_sha256":"a".repeat(64),"preset_sha256":"b".repeat(64),"applies_sha256":"c".repeat(64),
            "replace_legacy":false,"members":[
                {"document_id":"active","revision":"3","before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"coverage_sha256":"f".repeat(64)},
                {"document_id":"sibling","revision":"9","before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"coverage_sha256":"f".repeat(64)}]}})
}
fn refusal(command: &Value) -> Value {
    let mut result = command.clone(); result.as_object_mut().unwrap().remove("cmd");
    result["event"] = json!("preset_result"); result["protocol"] = json!(1);
    result["success"] = json!(false); result["outcome_unknown"] = json!(false);
    result["error"] = json!("Frozen preset review expired before any write"); result
}
fn opened() -> Value {
    json!({"event":"project_opened","open":true,"path":"/verified/project.lrt","project_id":"new-workspace",
        "docs":2,"dirty":false})
}
#[test] fn one_send_admits_original_once_then_blocks_even_uncorrelated_edits() {
    let epoch = epoch(1); let command = request(); assert!(applies(&command)); issued(epoch, &command).unwrap();
    for mutation in [command.clone(), json!({"cmd":"exposure","exposure":0.5}), json!({"cmd":"crop","rect":[0,0,1,1]}),
        json!({"cmd":"history","action":"undo"}), json!({"cmd":"batch","action":"undo","request_id":"other","batch_id":"unknown-batch"}),
        json!({"cmd":"project","action":"save"}), json!({"cmd":"export","path":"/output.png"}),
        json!({"cmd":"exposure","action":"status","exposure":0.5}), json!({"cmd":"arbitrary_state","write":true}),
        json!({"cmd":"preset","action":"apply","id":"ordinary-preset"}),
        json!({"cmd":"project_recovery","action":"snapshot","request_id":"snapshot","project_id":"p"})] {
        assert!(issued(epoch, &mutation).is_err(), "{mutation}");
    }
    assert!(proof(epoch).is_err()); observed(epoch, &opened()); assert!(proof(epoch).is_ok());
}
#[test] fn bounded_reads_and_explicit_recovery_do_not_release_or_add_mutation_authority() {
    let epoch = epoch(2); issued(epoch, &request()).unwrap();
    for read in [json!({"cmd":"batch","action":"state"}), json!({"cmd":"preset","action":"list","request_id":"catalog"}),
        json!({"cmd":"session","action":"query","request_id":"source-query","query":{}}),
        json!({"cmd":"project","action":"state"}), json!({"cmd":"hello"}), json!({"cmd":"shutdown"}),
        json!({"cmd":"project_recovery","action":"list","request_id":"recovery-list","project_id":"p"}),
        json!({"cmd":"project_recovery","action":"inspect","request_id":"recovery-inspect","project_id":"p","candidate_id":"candidate","area":"candidates"}),
        json!({"cmd":"project_recovery","action":"restore","request_id":"recovery-copy","project_id":"p",
            "candidate_id":"candidate","reviewed_sha256":"a".repeat(64),"destination":"/new-copy","confirmed":true}),
        json!({"cmd":"project","action":"open","path":"/verified/project.lrt","force":true}),
        json!({"cmd":"preset","action":"eye_bag_visual","request_id":"member-image","id":"mixed-preset",
            "document_id":"load-active","revision":"3","preflight_token":"f".repeat(32),"side":"before","sha256":"d".repeat(64),
            "member_document_id":"sibling","member_revision":"9"})] {
        assert!(safe_during_pending(&read), "{read}"); issued(epoch, &read).unwrap(); assert!(proof(epoch).is_err());
    }
    let mut injected = json!({"cmd":"preset","action":"list","mutation":{}}); assert!(issued(epoch, &injected).is_err());
    injected = json!({"cmd":"preset","action":"list","request_id":"composite-original"}); assert!(issued(epoch, &injected).is_err());
    injected = json!({"cmd":"project_recovery","action":"restore","request_id":"copy","project_id":"p","confirmed":true});
    assert!(issued(epoch, &injected).is_err());
    observed(epoch, &opened()); assert!(proof(epoch).is_ok());
}
#[test] fn only_actual_matching_terminal_or_verified_workspace_event_releases_composite() {
    let epoch = epoch(3); let command = request(); issued(epoch, &command).unwrap();
    let terminal = refusal(&command); assert!(settled(&command, &terminal));
    for (field, replacement) in [("request_id",json!("other")),("event",json!("batch_result")),
        ("action",json!("preflight")),("document_id",json!("other-load")),("preflight_token",json!("e".repeat(32))),
        ("eye_bag_preset_ack",Value::Null),("outcome_unknown",json!(true)),("success",json!(true))] {
        let mut bad = terminal.clone(); bad[field] = replacement; observed(epoch, &bad); assert!(proof(epoch).is_err(), "{field}");
    }
    let mut other_epoch = epoch; other_epoch[15] = 4;
    observed(other_epoch, &terminal); assert!(proof(epoch).is_err());
    for failed in [json!({"event":"project_opened"}), json!({"event":"project_opening"}),
        json!({"event":"project_opened","open":false}), json!({"event":"project_created","success":false}),
        json!({"event":"preset_result","action":"apply","request_id":"composite-original","success":false,"outcome_unknown":false,"error":"Cancelled"})] {
        observed(epoch, &failed); assert!(proof(epoch).is_err());
    }
    let mut failed = opened(); failed["success"] = json!(false); observed(epoch, &failed); assert!(proof(epoch).is_err());
    observed(epoch, &terminal); assert!(proof(epoch).is_ok());
    issued(epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap();
}
#[test] fn old_requests_and_new_epoch_keep_existing_admission_behavior() {
    let original_epoch = epoch(5); let new_epoch = epoch(6);
    issued(original_epoch, &json!({"cmd":"batch","action":"commit","request_id":"old-batch"})).unwrap();
    issued(original_epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap();
    observed(original_epoch, &json!({"event":"project_opened"})); assert!(proof(original_epoch).is_ok());
    issued(original_epoch, &request()).unwrap();
    issued(new_epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap(); assert!(proof(new_epoch).is_ok());
    assert!(proof(original_epoch).is_err()); observed(original_epoch, &opened());
}
