// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Rich engine-summary classification and recovery fencing.
use super::*;
use super::super::{issued, observed, proof};
fn epoch(tag: u8) -> [u8;16] { let mut value = [246;16]; value[15] = tag; value }
fn marked() -> Value {
    json!({"version":1,"review_sha256":"a".repeat(64),"preset_sha256":"b".repeat(64),"applies_sha256":"c".repeat(64),
        "current_document_id":"logical-active","member_count":2,"selected_modules":["lnx.eye_bags.v2","lnx.exposure.v1"]})
}
fn summary(workspace: &str) -> Value {
    json!({"event":"session_state","sync":{"workspace_generation":workspace,"batches":[{
        "batch_id":"composite-batch","module_scope":["lnx.people_graph.v1"],"targets":2,"undone":false,(MARKER):marked()}]}})
}
fn command() -> Value { json!({"cmd":"batch","action":"undo","request_id":"history-original","batch_id":"composite-batch"}) }
fn result(command: &Value) -> Value {
    json!({"event":"batch_result","action":command["action"],"request_id":command["request_id"],"batch_id":command["batch_id"],
        "success":true,"outcome_unknown":false,"module_scope":["lnx.people_graph.v1"],"restored":[0,1],"conflicts":[],(MARKER):marked()})
}
fn opened() -> Value {
    json!({"event":"project_opened","open":true,"path":"/verified/project.lrt","project_id":"new-project","docs":2,"dirty":false})
}
fn host(epoch: [u8;16]) -> crate::batch_host::BatchHost {
    let mut host = crate::batch_host::BatchHost::default(); host.reset(epoch); host.ready(epoch,true); host
}

#[test] fn rich_reopened_summary_classifies_only_exact_composite_history() {
    let epoch = epoch(1); let c = command(); observed(epoch, &summary("workspace-a"));
    assert_eq!(marker(epoch, &c).unwrap(), Some(marked()));
    let mut h = host(epoch); h.begin_command(epoch, &c).unwrap(); issued(epoch, &c).unwrap();
    assert!(issued(epoch, &json!({"cmd":"exposure","exposure":0.5})).is_err());
    assert!(issued(epoch, &json!({"cmd":"project","action":"save"})).is_err());
    assert!(issued(epoch, &json!({"cmd":"export","path":"/output.png"})).is_err());
    assert!(issued(epoch, &json!({"cmd":"batch","action":"state"})).is_ok());
    h.receive(epoch, &result(&c)); assert!(proof(epoch).is_ok());
    assert_eq!(h.status("history-original")["result"], result(&c));
    issued(epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap(); observed(epoch, &opened());
}
#[test] fn client_marker_and_incomplete_batch_state_cannot_create_authority() {
    let epoch = epoch(2); let c = command();
    observed(epoch, &json!({"event":"batch_state","batches":[{"batch_id":"composite-batch",(MARKER):marked()}]}));
    assert!(marker(epoch, &c).unwrap().is_none());
    let mut client = c.clone(); client[MARKER] = marked(); assert!(crate::batch_api::history::command(&client).is_err());
    assert!(marker(epoch, &c).unwrap().is_none());
    observed(epoch, &summary("workspace-a"));
    let mut legacy = c; legacy.as_object_mut().unwrap().remove("request_id"); assert!(issued(epoch, &legacy).is_err());
    observed(epoch, &opened());
}
#[test] fn history_unknown_retains_original_marker_and_blocks_late_success() {
    let epoch = epoch(3); let c = command(); observed(epoch, &summary("workspace-a"));
    let mut h = host(epoch); h.begin_command(epoch, &c).unwrap(); issued(epoch, &c).unwrap();
    let mut wrong = result(&c); wrong[MARKER]["review_sha256"] = json!("d".repeat(64));
    h.receive(epoch, &wrong); let retained = h.status("history-original");
    assert_eq!(retained["result"]["outcome_unknown"], true); assert_eq!(retained["result"][MARKER], marked());
    h.receive(epoch, &result(&c)); assert_eq!(h.status("history-original"), retained);
    assert!(issued(epoch, &json!({"cmd":"crop","rect":[0,0,1,1]})).is_err());
    observed(epoch, &json!({"event":"project_opened"})); assert!(proof(epoch).is_err());
    observed(epoch, &opened()); assert!(proof(epoch).is_ok()); assert!(marker(epoch, &c).unwrap().is_none());
}
#[test] fn bound_known_no_write_conflict_releases_without_granting_retry() {
    let epoch = epoch(4); let c = command(); observed(epoch, &summary("workspace-a"));
    let mut h = host(epoch); h.begin_command(epoch, &c).unwrap(); issued(epoch, &c).unwrap();
    let mut rejected = result(&c); rejected["success"] = json!(false); rejected["error"] = json!("Protected member changed");
    rejected["restored"] = json!([]); h.receive(epoch, &rejected);
    assert_eq!(h.status("history-original")["result"], rejected); assert!(proof(epoch).is_ok());
    assert!(h.begin_command(epoch, &c).is_err()); observed(epoch, &opened());
}
#[test] fn workspace_generation_and_confirmed_reopen_prevent_batch_id_aliasing() {
    let epoch = epoch(5); let c = command(); observed(epoch, &summary("workspace-a"));
    let mut next = summary("workspace-b"); next["sync"]["batches"][0].as_object_mut().unwrap().remove(MARKER);
    next["sync"]["batches"][0]["module_scope"] = json!(["lnx.exposure.v1"]);
    observed(epoch, &next); assert!(marker(epoch, &c).unwrap().is_none());
    issued(epoch, &c).unwrap(); issued(epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap();
    observed(epoch, &opened()); assert!(proof(epoch).is_ok());
    observed(epoch, &summary("workspace-c")); assert!(marker(epoch, &c).unwrap().is_some());
    observed(epoch, &opened()); assert!(marker(epoch, &c).unwrap().is_none());
}
#[test] fn malformed_or_conflicting_composite_marks_only_that_batch_unavailable() {
    let epoch = epoch(6); let c = command(); observed(epoch, &summary("workspace-a"));
    let mut changed = summary("workspace-a"); changed["sync"]["batches"][0][MARKER]["review_sha256"] = json!("d".repeat(64));
    observed(epoch, &changed); assert!(marker(epoch, &c).is_err());
    let mut ordinary = c.clone(); ordinary["batch_id"] = json!("ordinary"); assert!(marker(epoch, &ordinary).unwrap().is_none());
    observed(epoch, &opened());
    let mut malformed = summary("workspace-b"); malformed["sync"]["batches"][0]["targets"] = json!(1);
    observed(epoch, &malformed); assert!(marker(epoch, &c).is_err());
    assert!(marker(epoch, &ordinary).unwrap().is_none()); observed(epoch, &opened());
}
#[test] fn ten_thousand_ordinary_saved_batches_keep_existing_admission() {
    let epoch = epoch(7); let mut source = summary("legacy-workspace");
    source["sync"]["batches"] = json!((0..10_000).map(|n|json!({"batch_id":format!("ordinary-{n}"),
        "module_scope":["lnx.exposure.v1"],"targets":1,"undone":false})).collect::<Vec<_>>());
    observed(epoch, &source); let mut c = command(); c["batch_id"] = json!("ordinary-9999");
    assert!(marker(epoch, &c).unwrap().is_none()); issued(epoch, &c).unwrap();
    issued(epoch, &json!({"cmd":"exposure","exposure":0.5})).unwrap(); observed(epoch, &opened());
}
#[test] fn repeated_incomplete_status_cannot_launder_a_blocked_composite_id() {
    let epoch = epoch(8); let c = command(); observed(epoch, &summary("workspace-a"));
    let mut removed = summary("workspace-a"); removed["sync"]["batches"][0].as_object_mut().unwrap().remove(MARKER);
    for _ in 0..3 { observed(epoch, &removed); assert!(marker(epoch, &c).is_err()); assert!(issued(epoch, &c).is_err()); }
    observed(epoch, &opened());
    let mut malformed = summary("workspace-b"); malformed["sync"]["batches"][0][MARKER]["review_sha256"] = json!("invalid");
    observed(epoch, &malformed); assert!(marker(epoch, &c).is_err());
    malformed["sync"]["batches"][0].as_object_mut().unwrap().remove(MARKER);
    for _ in 0..3 { observed(epoch, &malformed); assert!(marker(epoch, &c).is_err()); }
    observed(epoch, &opened()); assert!(marker(epoch, &c).unwrap().is_none());
}
