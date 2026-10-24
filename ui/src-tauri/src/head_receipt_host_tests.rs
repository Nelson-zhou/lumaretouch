//! AUTHORED / UNRUN. Ledger and recovery predicates only; no actual engine execution.
use super::*;
use crate::torso_transfer_protocol::HEAD_OP;
struct FixtureKind;
impl ReceiptKind for FixtureKind {
    const NAME: &'static str = "batch";
    const ACTIONS: &'static [&'static str] = &["preflight", "commit"];
    fn valid(value: &Value, _: Option<&str>) -> bool {
        value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
    }
}
fn host(epoch: [u8;16]) -> ReceiptHost<FixtureKind> {
    let mut host = ReceiptHost::default(); host.reset(epoch); host.ready(epoch, true); host
}
fn command() -> Value {
    json!({"cmd":"batch","action":"commit","request_id":"head","preflight_token":"f".repeat(32),
        "head_review_ack":[
            {"document_id":"first","revision":"2","before_sha256":"a".repeat(64),"after_sha256":"b".repeat(64)},
            {"document_id":"second","revision":"3","before_sha256":"c".repeat(64),"after_sha256":"d".repeat(64)}]})
}
fn terminal(command: &Value) -> Value {
    json!({"action":"commit","request_id":command["request_id"],"success":true,"outcome_unknown":false,
        "module_scope":[HEAD_OP],"preflight_token":command["preflight_token"],"head_review_ack":command["head_review_ack"]})
}
#[test]
fn head_original_token_scope_and_ordered_ack_are_immutable() {
    let command = command(); let value = terminal(&command);
    for (path, replacement) in [("/preflight_token", json!("e".repeat(32))),
        ("/module_scope", json!([crate::waist_transfer_protocol::WAIST_OP])),
        ("/head_review_ack/0/before_sha256", json!("e".repeat(64))),
        ("/head_review_ack/0/after_sha256", json!("e".repeat(64))),
        ("/head_review_ack/0/revision", json!("3")), ("/head_review_ack/0/document_id", json!("other"))] {
        let mut host = host([1;16]); host.begin_command([1;16], &command).unwrap();
        let mut changed = value.clone(); *changed.pointer_mut(path).unwrap() = replacement; host.receive([1;16], &changed);
        let retained = host.status("head")["result"].clone(); assert_eq!(retained["outcome_unknown"], true, "{path}");
        assert_eq!(retained["head_review_ack"], command["head_review_ack"]);
        assert_eq!(retained["preflight_token"], command["preflight_token"]); assert_eq!(retained["module_scope"], json!([HEAD_OP]));
    }
    let mut host = host([1;16]); host.begin_command([1;16], &command).unwrap();
    let mut changed = value; changed["head_review_ack"].as_array_mut().unwrap().reverse();
    host.receive([1;16], &changed); assert_eq!(host.status("head")["result"]["outcome_unknown"], true);
}
#[test]
fn head_registration_copies_sender_identity_and_never_replays_an_uncertain_request() {
    let original = command(); let mut changed = original.clone(); let mut host = host([1;16]);
    host.begin_command([1;16], &changed).unwrap(); changed["head_review_ack"][0]["after_sha256"] = json!("e".repeat(64));
    host.failed("head", "send outcome uncertain");
    assert_eq!(host.status("head")["result"]["head_review_ack"], original["head_review_ack"]);
    host.receive([1;16], &terminal(&original)); assert_eq!(host.status("head")["result"]["outcome_unknown"], true);
    assert!(host.begin_command([1;16], &original).is_err());
    let mut shutdown = original.clone(); shutdown["request_id"] = json!("head-shutdown");
    host.begin_command([1;16], &shutdown).unwrap(); host.ended([1;16]);
    assert_eq!(host.status("head-shutdown")["result"]["head_review_ack"], original["head_review_ack"]);
    host.reset([2;16]); assert_eq!(host.status("head-shutdown")["phase"], "unavailable");
}
#[test]
fn only_explicit_preclaim_no_write_rejection_may_omit_head_identity() {
    let command = command();
    let rejected = json!({"request_id":"head","action":"commit","success":false,"outcome_unknown":false,"error":"Claim rejected before mutation"});
    let mut host = host([1;16]); host.begin_command([1;16], &command).unwrap(); host.receive([1;16], &rejected);
    assert_eq!(host.status("head")["result"], rejected);
    let mut with_rows = rejected.clone(); with_rows["preflight_token"] = command["preflight_token"].clone();
    with_rows["target_outcomes"] = json!([{"outcome":"conflict"},{"outcome":"not_applied"}]);
    let mut host = self::host([1;16]); host.begin_command([1;16], &command).unwrap(); host.receive([1;16], &with_rows);
    assert_eq!(host.status("head")["result"], with_rows);
    for (key, replacement) in [("success", json!(true)), ("outcome_unknown", json!(true)), ("outcome_unknown", Value::Null),
        ("module_scope", json!([HEAD_OP])), ("head_review_ack", Value::Null), ("waist_review_ack", Value::Null),
        ("head_transfer", Value::Null), ("torso_transfer", json!({})), ("preflight_token", json!("e".repeat(32))),
        ("target_outcomes", json!([{"outcome":"applied"}])), ("target_outcomes", json!([{"outcome":"not_applied","result_revision":"3"}])),
        ("after", json!({})), ("operation_committed", json!(true)), ("requires_reload", json!(true)), ("error", json!(""))] {
        let mut host = self::host([1;16]); host.begin_command([1;16], &command).unwrap();
        let mut changed = rejected.clone(); changed[key] = replacement; host.receive([1;16], &changed);
        let retained = host.status("head")["result"].clone(); assert_eq!(retained["outcome_unknown"], true, "{key}");
        assert_eq!(retained["head_review_ack"], command["head_review_ack"]);
    }
}
#[test]
fn head_identity_never_overrides_epoch_request_action_or_unsettled_state() {
    let command = command(); let value = terminal(&command); let mut host = host([1;16]);
    host.begin_command([1;16], &command).unwrap(); host.receive([2;16], &value);
    let mut changed = value.clone(); changed["request_id"] = json!("foreign"); host.receive([1;16], &changed);
    changed = value.clone(); changed["action"] = json!("preflight"); host.receive([1;16], &changed);
    assert_eq!(host.status("head")["phase"], "pending");
    for event in ["batch_result", "preset_result", "arbitrary_done"] {
        let mut changed = value.clone(); changed["event"] = json!(event);
        // The dispatcher asks this predicate before observing any event name.
        assert!(host.guards_review([1;16], changed["request_id"].as_str().unwrap()));
    }
    for (key, replacement) in [("requires_reload", json!(true)), ("requires_readback", json!(true)),
        ("requires_reload", json!("yes")), ("status", json!("running")), ("phase", json!("accepted"))] {
        let mut host = self::host([1;16]); host.begin_command([1;16], &command).unwrap();
        let mut changed = value.clone(); changed[key] = replacement; host.receive([1;16], &changed);
        assert_eq!(host.status("head")["result"]["outcome_unknown"], true, "{key}");
    }
}
#[test]
fn head_preflight_binds_scope_without_inventing_token_or_ack() {
    let mut host = host([1;16]);
    host.begin_command([1;16], &json!({"cmd":"batch","action":"preflight","request_id":"head-review","module_scope":[HEAD_OP]})).unwrap();
    host.receive([1;16], &json!({"request_id":"head-review","action":"preflight","success":true,"outcome_unknown":false,
        "module_scope":[crate::waist_transfer_protocol::WAIST_OP]}));
    let retained = host.status("head-review")["result"].clone(); assert_eq!(retained["outcome_unknown"], true);
    assert_eq!(retained["module_scope"], json!([HEAD_OP])); assert!(retained.get("head_review_ack").is_none());
    assert!(retained.get("preflight_token").is_none());
    let command = json!({"cmd":"preset","action":"preflight","request_id":"head-preset-review", "document_id":"target","module_scope":[HEAD_OP]});
    let binding = ReviewBinding::from_command(&command).unwrap().unwrap();
    assert!(!binding.matches(&json!({"success":true,"outcome_unknown":false,"module_scope":[crate::torso_transfer_protocol::TORSO_OP]})));
    assert_eq!(binding.fields, json!({"module_scope":[HEAD_OP]}));
}
#[test]
fn head_unknown_records_remain_compact_pinned_and_capacity_bounded() {
    let mut host = host([1;16]);
    for index in 0..MAX_RECORDS {
        let mut command = command(); command["request_id"] = json!(format!("head-{index}")); host.begin_command([1;16], &command).unwrap();
        let mut unknown = terminal(&command); unknown["success"] = json!(false); unknown["outcome_unknown"] = json!(true);
        unknown["untrusted_padding"] = json!("x".repeat(100_000)); unknown["error"] = json!("x".repeat(10_000));
        host.receive([1;16], &unknown); let id = command["request_id"].as_str().unwrap(); let retained = host.status(id)["result"].clone();
        assert!(host.guards_review([1;16], id)); assert!(!host.guards_review([2;16], id));
        assert_eq!(retained["head_review_ack"], command["head_review_ack"]); assert!(retained.get("untrusted_padding").is_none());
        assert!(retained.to_string().len() < 16 * 1024);
    }
    assert!(host.begin_command([1;16], &command()).is_err());
    host.reset([2;16]); host.ready([2;16], true); assert!(host.begin_command([2;16], &command()).is_ok());
}
#[test]
fn head_recovery_settles_only_the_retained_validated_terminal_not_raw_replay() {
    let command = command(); let epoch = [189;16]; let mut host = host(epoch);
    host.begin_command(epoch, &command).unwrap(); crate::project_recovery_fence::issued(epoch, &command).unwrap();
    let mut changed = terminal(&command); changed["preflight_token"] = json!("e".repeat(32)); host.receive(epoch, &changed);
    assert!(crate::project_recovery_fence::proof(epoch).is_err()); host.receive(epoch, &terminal(&command));
    assert!(crate::project_recovery_fence::proof(epoch).is_err());
    crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
    let epoch = [190;16]; let mut host = self::host(epoch); host.begin_command(epoch, &command).unwrap();
    crate::project_recovery_fence::issued(epoch, &command).unwrap(); host.receive(epoch, &terminal(&command));
    assert!(crate::project_recovery_fence::proof(epoch).is_ok());
}

#[test]
fn unknown_head_preflight_can_expire_but_original_commit_stays_pinned() {
    let mut host = host([1;16]);
    for index in 0..MAX_RECORDS {
        let id = format!("head-review-{index}");
        host.begin_command([1;16], &json!({"cmd":"batch","action":"preflight","request_id":id,"module_scope":[HEAD_OP],"docs":["head-target"]})).unwrap();
        host.failed(&id, "read-only review display unavailable");
        assert_eq!(host.status(&id)["result"]["outcome_unknown"], true);
    }
    assert!(host.begin_command([1;16], &command()).is_ok());
    assert_eq!(host.status("head-review-0")["phase"], "unavailable");
    host.failed("head", "mutation outcome unknown");
    for index in MAX_RECORDS..MAX_RECORDS * 2 {
        let id = format!("head-review-{index}");
        host.begin_command([1;16], &json!({"cmd":"batch","action":"preflight","request_id":id,"module_scope":[HEAD_OP],"docs":["head-target"]})).unwrap();
        host.failed(&id, "read-only review display unavailable");
    }
    assert_eq!(host.status("head")["result"]["outcome_unknown"], true);
    assert_eq!(host.status("head")["result"]["head_review_ack"], command()["head_review_ack"]);
    // A terminal payload cannot change the immutable registered action.
    assert_eq!(host.status("head")["result"]["action"], "commit");
}
