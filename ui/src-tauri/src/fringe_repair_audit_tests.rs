//! Source-only fixtures: no tests were executed during implementation.
use super::*;
const EPOCH: [u8; 16] = [61; 16];
const SESSION: &str = "11111111111111111111111111111111";
const PREVIEW: &str = "22222222222222222222222222222222";
fn identity() -> Identity { Identity::new("one", "42", SESSION, PREVIEW).unwrap() }
fn receipt() -> Value {
    json!({"event": "fringe_repair_result", "protocol": 1, "action": "apply", "request_id": "one",
        "document_id": "42", "session_id": SESSION, "preview_id": PREVIEW,
        "success": true, "outcome_unknown": false, "requires_reload": false, "no_change": false,
        "history": {"undo_steps": 1, "redo_steps": 0}})
}
fn ledger_with_pending() -> Ledger {
    let mut ledger = Ledger::default(); ledger.bootstrap(Some((EPOCH, true))).unwrap();
    ledger.admit(EPOCH, identity(), 1, || Ok(())).unwrap(); ledger
}

#[test]
fn bootstrap_includes_pending_and_atomically_fences_the_old_client() {
    let mut ledger = ledger_with_pending();
    let remount = ledger.bootstrap(Some((EPOCH, true))).unwrap();
    assert_eq!(remount["client_generation"], "2"); assert_eq!(remount["count"], 1);
    assert_eq!(remount["items"][0]["original_request"]["request_id"], "one");
    assert_eq!(remount["items"][0]["unresolved"], true);
    assert!(remount["items"][0]["original_receipt"].is_null());
    let fresh = Identity::new("two", "42", SESSION, PREVIEW).unwrap();
    let mut called = false;
    assert!(ledger.admit(EPOCH, fresh.clone(), 1, || { called = true; Ok(()) }).is_err());
    assert!(!called); assert!(ledger.status("two").is_none());
    ledger.admit(EPOCH, fresh, 2, || Ok(())).unwrap();
    assert_eq!(ledger.status("one").unwrap()["phase"], "pending");
}

#[test]
fn no_bootstrap_or_failed_receipt_admission_can_reserve_an_apply() {
    let mut ledger = Ledger::default();
    assert!(ledger.admit(EPOCH, identity(), 0, || Ok(())).is_err());
    ledger.bootstrap(Some((EPOCH, true))).unwrap();
    assert!(ledger.admit(EPOCH, identity(), 1, || Err("generic receipt admission failed".into())).is_err());
    assert!(ledger.status("one").is_none());
}

#[test]
fn immutable_original_survives_bootstrap_new_epoch_and_late_contradictions() {
    let mut ledger = ledger_with_pending();
    assert_eq!(ledger.original(EPOCH, &receipt(), true), Some(receipt()));
    let mut contradiction = receipt(); contradiction["history"]["undo_steps"] = json!(88);
    assert!(ledger.original(EPOCH, &contradiction, true).is_none());
    ledger.ended(EPOCH);
    let inventory = ledger.bootstrap(Some(([62; 16], true))).unwrap();
    assert_eq!(inventory["items"][0]["original_receipt"], receipt());
    assert_eq!(inventory["items"][0]["unresolved"], false);
    assert_eq!(inventory["items"][0]["engine_state"], "epoch_changed");
    assert!(ledger.admit([62; 16], identity(), 2, || Ok(())).is_err());
    assert_eq!(ledger.status("one").unwrap()["result"], receipt());
}

#[test]
fn native_unknown_wins_over_a_late_engine_success_and_never_settles() {
    let mut ledger = ledger_with_pending(); let unknown = identity().unknown("send outcome uncertain");
    assert!(ledger.original(EPOCH, &unknown, false).is_none());
    assert!(ledger.original(EPOCH, &receipt(), true).is_none());
    assert_eq!(ledger.status("one").unwrap()["result"], unknown);
    assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], true);
    ledger.not_sent(EPOCH, identity(), "late synchronous rejection").unwrap();
    assert_eq!(ledger.status("one").unwrap()["result"], unknown);
}

#[test]
fn wrong_epoch_is_ignored_and_wrong_binding_becomes_bound_unknown() {
    let mut ledger = ledger_with_pending();
    assert!(ledger.original([62; 16], &receipt(), true).is_none());
    assert_eq!(ledger.status("one").unwrap()["phase"], "pending");
    for (key, value) in [("document_id", json!("43")), ("session_id", json!(PREVIEW)),
        ("preview_id", json!(SESSION)), ("event", json!("other_result")),
        ("action", json!("query")), ("protocol", json!(2)), ("history", Value::Null)] {
        let mut ledger = ledger_with_pending(); let mut bad = receipt(); bad[key] = value;
        assert!(ledger.original(EPOCH, &bad, true).is_none());
        let unknown = ledger.status("one").unwrap()["result"].clone();
        assert_eq!(unknown["document_id"], "42"); assert_eq!(unknown["session_id"], SESSION);
        assert_eq!(unknown["preview_id"], PREVIEW); assert_eq!(unknown["outcome_unknown"], true);
        assert_eq!(unknown["requires_reload"], true); assert_eq!(unknown["success"], false);
    }
}

#[test]
fn synchronous_rejection_is_definite_only_if_admission_did_not_happen() {
    let mut ledger = Ledger::default();
    ledger.not_sent([0; 16], identity(), "engine not running").unwrap();
    let rejection = ledger.status("one").unwrap()["result"].clone();
    assert_eq!(rejection["submission"], "not_sent"); assert_eq!(rejection["outcome_unknown"], false);
    assert_eq!(rejection["requires_reload"], false);
    assert_eq!(ledger.inventory(None)["items"][0]["unresolved"], false);
    let mut ledger = ledger_with_pending();
    ledger.not_sent(EPOCH, identity(), "caller saw an error after admission").unwrap();
    assert_eq!(ledger.status("one").unwrap()["phase"], "pending");
}

#[test]
fn engine_end_preserves_pending_as_query_only_unknown() {
    let mut ledger = ledger_with_pending(); ledger.ended(EPOCH);
    let result = ledger.status("one").unwrap()["result"].clone();
    assert_eq!(result["outcome_unknown"], true); assert_eq!(result["requires_reload"], true);
    let inventory = ledger.bootstrap(None).unwrap();
    assert_eq!(inventory["items"][0]["original_receipt"], result);
    assert_eq!(inventory["items"][0]["engine_state"], "engine_unavailable");
    assert_eq!(inventory["items"][0]["unresolved"], true);
}

#[test]
fn generation_overflow_and_audit_capacity_fail_closed_without_eviction() {
    let mut ledger = Ledger::default(); ledger.client_generation = u64::MAX;
    assert!(ledger.bootstrap(None).is_err());
    let mut ledger = ledger_with_pending();
    for index in 1..(MAX_BYTES / MAX_RECEIPT_BYTES) {
        let id = Identity::new(&format!("pending-{index}"), "42", SESSION, PREVIEW).unwrap();
        ledger.admit(EPOCH, id, 1, || Ok(())).unwrap();
    }
    let next = Identity::new("overflow", "42", SESSION, PREVIEW).unwrap();
    assert!(ledger.admit(EPOCH, next, 1, || Ok(())).is_err());
    assert_eq!(ledger.status("one").unwrap()["phase"], "pending");
    assert!(ledger.status("overflow").is_none());
}
