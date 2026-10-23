//! Process-lifetime audit and same-engine cache observation. Never retries apply.
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, color_capture_host::id16, common_background_host::{binding, CommonBackgroundKind}, receipt_host::ReceiptKind};

const MAX_IDS: usize = 4096;
const MAX_RECEIPT_BYTES: usize = 8 * 1024 * 1024;
const MAX_QUERY_BYTES: usize = MAX_RECEIPT_BYTES + 16384;
const MAX_BYTES: usize = 64 * 1024 * 1024;
type Current = Option<([u8; 16], bool)>;

#[derive(Clone, PartialEq, Eq)]
struct Identity { request: String, document: String, session: String, preview: String }
impl Identity {
    fn new(request: &str, document: &str, session: &str, preview: &str) -> Result<Self, String> {
        if request.is_empty() || request.len() > 128 { return Err("invalid common background request ID".into()); }
        binding(document, session, preview)?;
        Ok(Self { request: request.into(), document: document.into(), session: session.into(), preview: preview.into() })
    }
    fn matches(&self, value: &Value) -> bool {
        value["request_id"] == self.request && value["document_id"] == self.document
            && value["session_id"] == self.session && value["preview_id"] == self.preview
    }
    fn receipt_valid(&self, value: &Value) -> bool {
        let bound = format!("{}|{}|{}", self.document, self.session, self.preview);
        self.matches(value) && value["event"] == "common_background_result"
            && value.to_string().len() <= MAX_RECEIPT_BYTES
            && CommonBackgroundKind::valid(value, Some(&bound))
    }
    fn envelope(&self, readback: &str, phase: &str) -> Value {
        json!({"event": "common_background_readback", "protocol": 1, "action": "query",
            "request_id": self.request, "document_id": self.document, "session_id": self.session,
            "preview_id": self.preview, "readback_id": readback, "phase": phase, "result": null})
    }
    fn unknown(&self, error: &str) -> Value {
        json!({"event": "common_background_result", "protocol": 1, "action": "apply",
            "request_id": self.request, "document_id": self.document, "session_id": self.session,
            "preview_id": self.preview, "success": false, "outcome_unknown": true,
            "requires_reload": true, "no_change": false, "history": null, "error": error})
    }
}

struct Audit { epoch: [u8; 16], identity: Identity, original: Option<Value>, original_authoritative: bool, sequence: usize, authoritative_readback: Option<String> }
struct Query { request: String, outcome: Option<Value> }
#[derive(Default)]
struct Ledger { applies: HashMap<String, Audit>, queries: HashMap<String, Query>, client_generation: u64 }
fn ledger() -> &'static Mutex<Ledger> {
    static LEDGER: OnceLock<Mutex<Ledger>> = OnceLock::new();
    LEDGER.get_or_init(|| Mutex::new(Ledger::default()))
}
fn settled(value: &Value) -> bool { value["outcome_unknown"] == false && value["requires_reload"] == false }
fn reason(current: Current, epoch: [u8; 16]) -> Option<&'static str> {
    match current {
        Some((now, _)) if now != epoch => Some("epoch_changed"),
        Some((_, true)) => None,
        _ => Some("engine_unavailable"),
    }
}
impl Ledger {
    fn bootstrap(&mut self, current: Current) -> Result<Value, String> {
        self.client_generation = self.client_generation.checked_add(1).ok_or("common background client generation exhausted")?;
        let mut inventory = self.inventory(current);
        inventory["client_generation"] = json!(self.client_generation.to_string());
        Ok(inventory)
    }
    fn check_client(&self, generation: u64) -> Result<(), String> {
        if generation == 0 || generation != self.client_generation {
            return Err("common background client changed before apply admission; modification was not sent".into());
        }
        Ok(())
    }
    fn admit_client(&mut self, epoch: [u8; 16], identity: Identity, generation: u64,
        admit: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
        // Called while the same ledger mutex used by bootstrap remains held.
        self.check_client(generation)?;
        self.admit(epoch, identity, admit)
    }
    fn reserved(&self) -> usize {
        self.applies.values().map(|row| row.original.as_ref().map_or(MAX_RECEIPT_BYTES, |v| v.to_string().len())).sum::<usize>()
            + self.queries.values().map(|row| row.outcome.as_ref().map_or(MAX_QUERY_BYTES, |v| v.to_string().len())).sum::<usize>()
    }
    fn admit(&mut self, epoch: [u8; 16], identity: Identity, admit: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
        if epoch == [0; 16] { return Err("common background engine is unavailable".into()); }
        if self.applies.contains_key(&identity.request) { return Err("common background apply identity was already admitted; query the original".into()); }
        if self.applies.len() >= MAX_IDS || self.reserved() + MAX_RECEIPT_BYTES > MAX_BYTES {
            return Err("common background audit is full; original outcomes were retained, apply was not submitted".into());
        }
        // The caller holds its proof and generic receipt locks. Reserve this
        // audit only if admission there succeeds, before any bytes can be sent.
        admit()?;
        let sequence = self.applies.len();
        self.applies.insert(identity.request.clone(), Audit { epoch, identity, original: None, original_authoritative: false, sequence, authoritative_readback: None });
        Ok(())
    }
    fn original(&mut self, epoch: [u8; 16], value: &Value, authoritative: bool) -> Option<Value> {
        let row = self.applies.get_mut(value["request_id"].as_str()?)?;
        if row.epoch != epoch || row.original.is_some() || value["action"] != "apply" { return None; }
        // The cache observation may arrive first. An actual engine terminal
        // must agree with that immutable evidence in either arrival order.
        let prior = row.authoritative_readback.as_ref().and_then(|id| self.queries.get(id))
            .and_then(|query| query.outcome.as_ref()).map(|outcome| &outcome["result"]);
        let valid = row.identity.receipt_valid(value)
            && (!authoritative || prior.map_or(true, |prior| prior == value));
        let original = if valid { value.clone() } else {
            row.identity.unknown("invalid, contradictory or oversized common_background receipt; inspect actual state")
        };
        let settlement = (authoritative && valid && settled(&original)).then(|| original.clone());
        row.original_authoritative = authoritative && valid;
        row.original = Some(original);
        settlement
    }
    fn not_sent(&mut self, epoch: [u8; 16], identity: Identity, error: &str) -> Result<(), String> {
        // Presence, including any uncertain admission, always wins. Absence is
        // insufficient alone: only the synchronous submit error path calls us.
        if self.applies.contains_key(&identity.request) { return Ok(()); }
        let mut receipt = identity.unknown(error);
        receipt["outcome_unknown"] = json!(false);
        receipt["requires_reload"] = json!(false);
        receipt["submission"] = json!("not_sent");
        receipt["error"] = json!(error.chars().take(2000).collect::<String>());
        if self.applies.len() >= MAX_IDS || self.reserved() + receipt.to_string().len() > MAX_BYTES {
            return Err("native rejection audit is full; no noncommit receipt was recorded".into());
        }
        let sequence = self.applies.len();
        self.applies.insert(identity.request.clone(), Audit { epoch, identity, original: Some(receipt), original_authoritative: false, sequence, authoritative_readback: None });
        Ok(())
    }
    fn start(&mut self, identity: &Identity, readback: &str, current: Current, supported: bool) -> Result<bool, String> {
        id16(readback)?;
        let row = self.applies.get(&identity.request).ok_or("original common background audit is unavailable; no query sent")?;
        if &row.identity != identity { return Err("common background readback binding differs from the original apply".into()); }
        if let Some(query) = self.queries.get(readback) {
            if query.request != identity.request { return Err("common background readback ID was already used".into()); }
            return Ok(false); // Observe this query, never silently send it again.
        }
        if self.queries.len() >= MAX_IDS || self.reserved() + MAX_QUERY_BYTES > MAX_BYTES {
            return Err("common background readback audit is full; original outcomes were retained".into());
        }
        let outcome = if row.original.as_ref().is_some_and(|receipt| receipt["submission"] == "not_sent") {
            let mut value = identity.envelope(readback, "failed");
            value["error"] = json!("original request was not submitted; inspect its retained native receipt, not the engine cache");
            Some(value)
        } else if let Some(phase) = reason(current, row.epoch) {
            Some(identity.envelope(readback, phase))
        } else if !supported {
            let mut value = identity.envelope(readback, "failed");
            value["error"] = json!("engine has not advertised common background readback support");
            Some(value)
        } else { None };
        let send = outcome.is_none();
        self.queries.insert(readback.into(), Query { request: identity.request.clone(), outcome });
        Ok(send)
    }
    fn status(&self, readback: &str, current: Current) -> Value {
        let Some(query) = self.queries.get(readback) else {
            return json!({"phase": "unavailable", "readback_id": readback, "result": null,
                "error": "readback audit is unavailable in this application process"});
        };
        let row = &self.applies[&query.request];
        let mut value = if let Some(phase) = reason(current, row.epoch) {
            row.identity.envelope(readback, phase)
        } else { query.outcome.clone().unwrap_or_else(|| row.identity.envelope(readback, "pending")) };
        value["original_receipt"] = row.original.clone().unwrap_or(Value::Null);
        value["audit_scope"] = json!("application-process");
        value
    }
    fn inventory(&self, current: Current) -> Value {
        let mut items: Vec<_> = self.applies.values().map(|row| {
            let readback = row.authoritative_readback.as_ref().and_then(|id| self.queries.get(id))
                .and_then(|query| query.outcome.as_ref()).map(|value| &value["result"]);
            let unresolved = !row.original.as_ref().is_some_and(settled) && !readback.is_some_and(settled);
            let identity = &row.identity;
            let value = json!({"original_request": {"request_id": identity.request, "document_id": identity.document,
                    "session_id": identity.session, "preview_id": identity.preview},
                "original_receipt": row.original, "readback_result": readback, "readback_id": row.authoritative_readback,
                "engine_state": reason(current, row.epoch).unwrap_or("same_live_engine"), "unresolved": unresolved});
            (unresolved, row.sequence, value)
        }).collect();
        items.sort_by_key(|(unresolved, sequence, _)| (!*unresolved, *sequence));
        let items: Vec<_> = items.into_iter().map(|(_, _, value)| value).collect();
        json!({"protocol": 1, "audit_scope": "application-process", "count": items.len(), "items": items})
    }
    fn send_failed(&mut self, readback: &str, error: &str) {
        let Some(query) = self.queries.get_mut(readback) else { return };
        if query.outcome.is_some() { return; }
        let row = &self.applies[&query.request];
        let mut value = row.identity.envelope(readback, "failed");
        value["error"] = json!(error.chars().take(2000).collect::<String>());
        query.outcome = Some(value);
    }
    fn receive(&mut self, epoch: [u8; 16], value: &Value) -> Option<Value> {
        let readback = value["readback_id"].as_str()?;
        // An immutable engine cache cannot legitimately change its original
        // receipt between queries. Contradictory evidence never releases intent.
        let prior = self.queries.get(readback).and_then(|query| self.applies.get(&query.request))
            .and_then(|row| row.authoritative_readback.as_ref()).and_then(|id| self.queries.get(id))
            .and_then(|query| query.outcome.as_ref()).map(|outcome| outcome["result"].clone());
        let query = self.queries.get_mut(readback)?;
        let row = &self.applies[&query.request];
        if row.epoch != epoch || query.outcome.is_some() { return None; }
        let phase = value["phase"].as_str();
        let keys = ["event", "protocol", "action", "request_id", "document_id", "session_id", "preview_id", "readback_id", "phase", "result"];
        let fields = value.as_object().is_some_and(|object|
            keys.iter().all(|key| object.contains_key(*key)) && (object.len() == keys.len() ||
                (phase != Some("found") && object.len() == keys.len() + 1
                    && object.get("error").is_some_and(|error| error.as_str().is_some_and(|text| text.len() <= 4096)))));
        let valid = fields
            && value["event"] == "common_background_readback" && value["protocol"] == 1 && value["action"] == "query"
            && row.identity.matches(value) && value.to_string().len() <= MAX_QUERY_BYTES
            && match phase {
                Some("found") => row.identity.receipt_valid(&value["result"])
                    && !row.original.as_ref().is_some_and(|original| original["submission"] == "not_sent")
                    && prior.as_ref().map_or(true, |prior| prior == &value["result"])
                    && (!row.original_authoritative || row.original.as_ref().is_some_and(|original| original == &value["result"]))
                    && row.original.as_ref().filter(|original| settled(original)).map_or(true, |original| original == &value["result"]),
                Some("missing") => value.get("result").is_some_and(Value::is_null),
                Some("failed") => value.get("result").is_some_and(Value::is_null),
                _ => false,
            };
        if !valid {
            let mut failure = row.identity.envelope(readback, "failed");
            failure["error"] = json!("invalid or mismatched common background readback; original outcome remains unresolved");
            query.outcome = Some(failure);
            return None;
        }
        query.outcome = Some(value.clone());
        let request = query.request.clone();
        if phase == Some("found") {
            let row = self.applies.get_mut(&request)?;
            if row.authoritative_readback.is_none() { row.authoritative_readback = Some(readback.into()); }
        }
        // Only this exact original request can settle, never the whole fence.
        (phase == Some("found") && settled(&value["result"])).then(|| value["result"].clone())
    }
}

pub(crate) fn precheck_client(command: &Value) -> Result<(), String> {
    let generation = command["host_client_generation"].as_str().ok_or("common background client generation missing")?;
    let generation = crate::color_capture_host::token(generation)?;
    // Advisory only: admission rechecks under the ledger lock. Reject already
    // stale clients before native dispatch invalidates unrelated tool captures.
    ledger().lock().map_err(|_| "common background audit lock poisoned")?.check_client(generation)
}

pub(crate) fn admit_apply(epoch: [u8; 16], command: &Value, client_generation: u64, admit: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
    let get = |key: &str| command[key].as_str().ok_or_else(|| format!("common background {key} missing"));
    let identity = Identity::new(get("request_id")?, get("document_id")?, get("session_id")?, get("preview_id")?)?;
    ledger().lock().map_err(|_| "common background audit lock poisoned")?.admit_client(epoch, identity, client_generation, admit)
}

pub(crate) fn record_not_sent(epoch: [u8; 16], request: &str, document: &str, session: &str, preview: &str, error: &str) -> Result<(), String> {
    let identity = Identity::new(request, document, session, preview)?;
    ledger().lock().map_err(|_| "common background audit lock poisoned")?.not_sent(epoch, identity, error)
}

pub(crate) fn original_status(request: &str) -> Result<Option<Value>, String> {
    let ledger = ledger().lock().map_err(|_| "common background audit lock poisoned")?;
    let Some(row) = ledger.applies.get(request) else { return Ok(None) };
    Ok(Some(match &row.original {
        Some(receipt) => json!({"phase": "done", "request_id": request, "result": receipt, "audit_scope": "application-process"}),
        None => json!({"phase": "pending", "request_id": request, "audit_scope": "application-process"}),
    }))
}

pub(crate) fn receive_apply(epoch: [u8; 16], value: &Value) {
    if let Ok(mut ledger) = ledger().lock() {
        if let Some(receipt) = ledger.original(epoch, value, true) { crate::project_recovery_fence::observed(epoch, &receipt); }
    }
}

pub(crate) fn retain_native_unknown(epoch: [u8; 16], value: &Value) {
    if let Ok(mut ledger) = ledger().lock() { ledger.original(epoch, value, false); }
}

pub(crate) fn ended(epoch: [u8; 16]) {
    if let Ok(mut ledger) = ledger().lock() {
        for row in ledger.applies.values_mut().filter(|row| row.epoch == epoch && row.original.is_none()) {
            row.original = Some(row.identity.unknown("engine ended before common_background completion was confirmed"));
        }
        // No reset or eviction: old-epoch originals remain queryable as audit,
        // but can never authorize a readback command to a replacement engine.
    }
}

pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    if let Ok(mut ledger) = ledger().lock() {
        if let Some(receipt) = ledger.receive(epoch, value) { crate::project_recovery_fence::observed(epoch, &receipt); }
    }
}

pub(crate) fn read_only(command: &Value) -> bool {
    command["cmd"] == "common_background_readback" && command["action"] == "query"
        && command.as_object().is_some_and(|object| object.len() == 7)
        && command["readback_id"].as_str().is_some_and(|id| id16(id).is_ok())
        && ["request_id", "document_id", "session_id", "preview_id"].iter().all(|key| command[*key].is_string())
        && Identity::new(command["request_id"].as_str().unwrap_or(""), command["document_id"].as_str().unwrap_or(""),
            command["session_id"].as_str().unwrap_or(""), command["preview_id"].as_str().unwrap_or("")).is_ok()
}

#[tauri::command]
pub(crate) fn common_background_readback(state: State<'_, Arc<AppState>>, request_id: String,
    preview_id: String, session_id: String, document_id: String, readback_id: String) -> Result<Value, String> {
    let identity = Identity::new(&request_id, &document_id, &session_id, &preview_id)?;
    id16(&readback_id)?;
    // Keep the current-engine lock through admission and unkeyed queue insertion.
    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?;
    let handle = engine.as_ref();
    let current = handle.map(|handle| (handle.epoch(), handle.is_alive()));
    let supported = state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["common_background_readback_protocol"] == 1;
    let mut ledger = ledger().lock().map_err(|_| "common background audit lock poisoned")?;
    if ledger.start(&identity, &readback_id, current, supported)? {
        let command = json!({"cmd": "common_background_readback", "action": "query", "request_id": request_id,
            "preview_id": preview_id, "session_id": session_id, "document_id": document_id, "readback_id": readback_id});
        if let Some(handle) = handle {
            if let Err(error) = handle.send(command) { ledger.send_failed(&readback_id, &error); }
        }
    }
    Ok(ledger.status(&readback_id, current))
}

#[tauri::command]
pub(crate) fn common_background_readback_status(state: State<'_, Arc<AppState>>, readback_id: String) -> Result<Value, String> {
    id16(&readback_id)?;
    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?;
    let current = engine.as_ref().map(|handle| (handle.epoch(), handle.is_alive()));
    Ok(ledger().lock().map_err(|_| "common background audit lock poisoned")?.status(&readback_id, current))
}

#[tauri::command]
pub(crate) fn common_background_audit(state: State<'_, Arc<AppState>>) -> Result<Value, String> {
    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?;
    let current = engine.as_ref().map(|handle| (handle.epoch(), handle.is_alive()));
    ledger().lock().map_err(|_| "common background audit lock poisoned")?.bootstrap(current)
}

// Source-authored fixtures only; not run by this implementation.
#[cfg(test)]
mod tests {
    use super::*;
    const EPOCH: [u8; 16] = [9; 16];
    const SESSION: &str = "11111111111111111111111111111111";
    const PREVIEW: &str = "22222222222222222222222222222222";
    const QUERY: &str = "33333333333333333333333333333333";
    fn identity() -> Identity { Identity::new("apply-one", "42", SESSION, PREVIEW).unwrap() }
    fn receipt() -> Value {
        json!({"event": "common_background_result", "protocol": 1, "action": "apply", "request_id": "apply-one",
            "document_id": "42", "session_id": SESSION, "preview_id": PREVIEW, "success": true,
            "outcome_unknown": false, "requires_reload": false, "no_change": false, "history": {"undo_steps": 1, "redo_steps": 0}})
    }
    fn ledger_with_query() -> Ledger {
        let mut ledger = Ledger::default(); ledger.admit(EPOCH, identity(), || Ok(())).unwrap();
        assert!(ledger.start(&identity(), QUERY, Some((EPOCH, true)), true).unwrap()); ledger
    }
    #[test]
    fn found_is_separate_from_original_unknown_and_duplicate_does_not_resend() {
        let mut ledger = ledger_with_query();
        let unknown = identity().unknown("delivery uncertain"); ledger.original(EPOCH, &unknown, false);
        let mut found = identity().envelope(QUERY, "found"); found["result"] = receipt();
        assert_eq!(ledger.receive(EPOCH, &found), Some(receipt()));
        assert!(!ledger.start(&identity(), QUERY, Some((EPOCH, true)), true).unwrap());
        let status = ledger.status(QUERY, Some((EPOCH, true)));
        assert_eq!(status["phase"], "found"); assert_eq!(status["result"], receipt());
        assert_eq!(status["original_receipt"], unknown);
        let mut late = found; late["result"]["no_change"] = json!(true);
        assert!(ledger.receive(EPOCH, &late).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["result"], receipt());
    }
    #[test]
    fn restart_never_rebinds_original_apply_or_sends_old_query() {
        let mut ledger = ledger_with_query(); ledger.original(EPOCH, &receipt(), true);
        let next = [10; 16];
        assert_eq!(ledger.status(QUERY, Some((next, true)))["phase"], "epoch_changed");
        assert_eq!(ledger.status(QUERY, None)["phase"], "engine_unavailable");
        assert_eq!(ledger.status(QUERY, Some((next, true)))["original_receipt"], receipt());
        let fresh = "44444444444444444444444444444444";
        assert!(!ledger.start(&identity(), fresh, Some((next, true)), true).unwrap());
        assert_eq!(ledger.status(fresh, Some((next, true)))["phase"], "epoch_changed");
        assert!(ledger.admit(next, identity(), || Ok(())).is_err());
    }
    #[test]
    fn missing_or_malformed_or_wrong_epoch_never_settles() {
        let mut ledger = ledger_with_query(); let missing = identity().envelope(QUERY, "missing");
        assert!(ledger.receive([10; 16], &missing).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "pending");
        assert!(ledger.receive(EPOCH, &missing).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "missing");
        for key in ["request_id", "document_id", "session_id", "preview_id"] {
            let mut ledger = ledger_with_query(); let mut found = identity().envelope(QUERY, "found");
            found["result"] = receipt(); found["result"][key] = json!("wrong");
            assert!(ledger.receive(EPOCH, &found).is_none());
            assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "failed");
        }
    }
    #[test]
    fn admission_failure_and_capacity_never_drop_existing_audit() {
        let mut ledger = Ledger::default();
        assert!(ledger.admit(EPOCH, identity(), || Err("generic host full".into())).is_err());
        assert!(ledger.applies.is_empty());
        for n in 0..8 {
            let mut id = identity(); id.request = format!("apply-{n}"); ledger.admit(EPOCH, id, || Ok(())).unwrap();
        }
        assert!(ledger.admit(EPOCH, identity(), || Ok(())).is_err());
        assert_eq!(ledger.applies.len(), 8);
    }
    #[test]
    fn only_exact_readback_is_read_only_and_clean_correlated_terminal_settles() {
        let mut command = json!({"cmd": "common_background_readback", "action": "query", "request_id": "apply-one",
            "document_id": "42", "session_id": SESSION, "preview_id": PREVIEW, "readback_id": QUERY});
        assert!(read_only(&command)); command["mutation"] = json!({"action": "clear"}); assert!(!read_only(&command));
        let mut ledger = ledger_with_query(); let mut wrong = receipt(); wrong["document_id"] = json!("43");
        assert!(ledger.original(EPOCH, &wrong, true).is_none());
        assert_eq!(ledger.applies["apply-one"].original.as_ref().unwrap()["outcome_unknown"], true);
        assert!(ledger.original(EPOCH, &receipt(), true).is_none());
    }
    #[test]
    fn inventory_survives_ui_remount_and_orders_all_unresolved_first() {
        let mut ledger = ledger_with_query(); ledger.original(EPOCH, &receipt(), true);
        let mut pending = identity(); pending.request = "apply-two".into();
        ledger.admit(EPOCH, pending.clone(), || Ok(())).unwrap();
        let inventory = ledger.inventory(Some(([10; 16], true)));
        assert_eq!(inventory["audit_scope"], "application-process"); assert_eq!(inventory["count"], 2);
        assert_eq!(inventory["items"][0]["original_request"]["request_id"], "apply-two");
        assert_eq!(inventory["items"][0]["unresolved"], true);
        assert_eq!(inventory["items"][0]["engine_state"], "epoch_changed");
        assert_eq!(inventory["items"][1]["original_receipt"], receipt());
        assert_eq!(inventory["items"][1]["unresolved"], false);
    }
    #[test]
    fn real_unknown_and_failed_lookup_remain_unresolved_without_overwrite() {
        let mut ledger = ledger_with_query(); let unknown = identity().unknown("rollback failed");
        ledger.original(EPOCH, &unknown, true);
        let mut failed = identity().envelope(QUERY, "failed"); failed["error"] = json!("digest mismatch");
        assert!(ledger.receive(EPOCH, &failed).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "failed");
        assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], true);
        let second = "44444444444444444444444444444444";
        ledger.start(&identity(), second, Some((EPOCH, true)), true).unwrap();
        let mut found = identity().envelope(second, "found"); found["result"] = unknown.clone();
        assert!(ledger.receive(EPOCH, &found).is_none());
        let item = ledger.inventory(Some((EPOCH, true)))["items"][0].clone();
        assert_eq!(item["unresolved"], true); assert_eq!(item["readback_result"], unknown);
    }
    #[test]
    fn explicit_pre_admission_failure_is_clean_but_never_overwrites_admission() {
        let mut ledger = Ledger::default();
        ledger.not_sent(EPOCH, identity(), "preview expired before queue admission").unwrap();
        let item = ledger.inventory(Some((EPOCH, true)))["items"][0].clone();
        assert_eq!(item["unresolved"], false); assert_eq!(item["original_receipt"]["submission"], "not_sent");
        assert_eq!(item["original_receipt"]["success"], false);
        assert!(ledger.admit(EPOCH, identity(), || Ok(())).is_err());
        let mut admitted = ledger_with_query();
        admitted.not_sent(EPOCH, identity(), "uncertain send error").unwrap();
        assert!(admitted.applies["apply-one"].original.is_none());
        let unknown = identity().unknown("uncertain send"); admitted.original(EPOCH, &unknown, false);
        admitted.not_sent(EPOCH, identity(), "later error").unwrap();
        assert_eq!(admitted.applies["apply-one"].original, Some(unknown));
    }
    #[test]
    fn found_cache_cannot_contradict_a_clean_original_success_or_rejection() {
        for success in [true, false] {
            let mut ledger = ledger_with_query(); let mut original = receipt();
            if !success {
                original["success"] = json!(false); original["history"] = Value::Null;
                original["error"] = json!("clean original rejection");
            }
            ledger.original(EPOCH, &original, true);
            let mut found = identity().envelope(QUERY, "found"); found["result"] = receipt();
            found["result"]["no_change"] = json!(true);
            assert!(ledger.receive(EPOCH, &found).is_none());
            let status = ledger.status(QUERY, Some((EPOCH, true)));
            assert_eq!(status["phase"], "failed"); assert_eq!(status["original_receipt"], original);
            assert!(ledger.applies["apply-one"].authoritative_readback.is_none());
        }
    }
    #[test]
    fn native_not_sent_receipt_never_starts_an_engine_cache_query() {
        let mut ledger = Ledger::default(); ledger.not_sent(EPOCH, identity(), "expired proof").unwrap();
        assert!(!ledger.start(&identity(), QUERY, Some((EPOCH, true)), true).unwrap());
        let mut fabricated = identity().envelope(QUERY, "found");
        fabricated["result"] = ledger.applies["apply-one"].original.clone().unwrap();
        assert!(ledger.receive(EPOCH, &fabricated).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "failed");
        assert!(ledger.applies["apply-one"].authoritative_readback.is_none());
    }
    #[test]
    fn authoritative_engine_rollback_unknown_cannot_turn_into_clean_found() {
        let mut ledger = ledger_with_query(); let unknown = identity().unknown("engine rollback failed");
        ledger.original(EPOCH, &unknown, true);
        assert!(ledger.applies["apply-one"].original_authoritative);
        let mut contradicted = identity().envelope(QUERY, "found"); contradicted["result"] = receipt();
        assert!(ledger.receive(EPOCH, &contradicted).is_none());
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["phase"], "failed");
        assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], true);
        let second = "44444444444444444444444444444444";
        ledger.start(&identity(), second, Some((EPOCH, true)), true).unwrap();
        let mut matching = identity().envelope(second, "found"); matching["result"] = unknown.clone();
        assert!(ledger.receive(EPOCH, &matching).is_none());
        assert_eq!(ledger.status(second, Some((EPOCH, true)))["result"], unknown);
        assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], true);
    }
    #[test]
    fn found_engine_unknown_rejects_a_late_clean_original_without_settlement() {
        let mut ledger = ledger_with_query(); let unknown = identity().unknown("engine rollback failed");
        let mut found = identity().envelope(QUERY, "found"); found["result"] = unknown.clone();
        assert!(ledger.receive(EPOCH, &found).is_none());
        assert!(ledger.applies["apply-one"].original.is_none());
        assert!(ledger.original(EPOCH, &receipt(), true).is_none());
        let original = ledger.applies["apply-one"].original.clone().unwrap();
        assert_eq!(original["outcome_unknown"], true); assert_eq!(original["requires_reload"], true);
        assert!(!ledger.applies["apply-one"].original_authoritative);
        assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], true);
        assert_eq!(ledger.status(QUERY, Some((EPOCH, true)))["result"], unknown);
        assert!(ledger.original(EPOCH, &unknown, true).is_none());
        assert_eq!(ledger.applies["apply-one"].original, Some(original));
        let mut matching = ledger_with_query(); matching.receive(EPOCH, &found);
        assert!(matching.original(EPOCH, &unknown, true).is_none());
        assert!(matching.applies["apply-one"].original_authoritative);
        assert_eq!(matching.applies["apply-one"].original, Some(unknown));
    }
    #[test]
    fn bootstrap_before_delayed_admission_rejects_the_old_client_without_sending() {
        let mut ledger = Ledger::default();
        assert_eq!(ledger.bootstrap(Some((EPOCH, true))).unwrap()["client_generation"], "1");
        let new_ui = ledger.bootstrap(Some((EPOCH, true))).unwrap();
        assert_eq!(new_ui["client_generation"], "2"); assert_eq!(new_ui["count"], 0);
        assert!(ledger.check_client(1).is_err()); assert!(ledger.check_client(2).is_ok());
        let called = std::cell::Cell::new(false);
        assert!(ledger.admit_client(EPOCH, identity(), 1, || { called.set(true); Ok(()) }).is_err());
        assert!(!called.get()); assert!(ledger.applies.is_empty());
        ledger.not_sent(EPOCH, identity(), "stale client generation").unwrap();
        assert_eq!(ledger.inventory(Some((EPOCH, true)))["items"][0]["unresolved"], false);
        assert!(ledger.admit_client(EPOCH, identity(), 0, || Ok(())).is_err());
    }
    #[test]
    fn admission_before_bootstrap_is_visible_to_the_new_client() {
        let mut ledger = Ledger::default(); ledger.bootstrap(Some((EPOCH, true))).unwrap();
        ledger.admit_client(EPOCH, identity(), 1, || Ok(())).unwrap();
        let new_ui = ledger.bootstrap(Some((EPOCH, true))).unwrap();
        assert_eq!(new_ui["client_generation"], "2"); assert_eq!(new_ui["count"], 1);
        assert_eq!(new_ui["items"][0]["original_request"]["request_id"], "apply-one");
        assert_eq!(new_ui["items"][0]["unresolved"], true);
        assert_eq!(ledger.applies["apply-one"].epoch, EPOCH);
    }
}
