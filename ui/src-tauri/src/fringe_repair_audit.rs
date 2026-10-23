//! Process-lifetime original receipts. Bootstrap fences a remounted web client.
//! This is native audit observation only: no engine cache query or apply retry.
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, color_capture_host::token,
    fringe_repair_host::{binding, FringeRepairKind}, receipt_host::ReceiptKind};

const MAX_IDS: usize = 4096;
const MAX_RECEIPT_BYTES: usize = 64 * 1024;
const MAX_BYTES: usize = 16 * 1024 * 1024;
type Current = Option<([u8; 16], bool)>;

#[derive(Clone, PartialEq, Eq)]
struct Identity { request: String, document: String, session: String, preview: String }
impl Identity {
    fn new(request: &str, document: &str, session: &str, preview: &str) -> Result<Self, String> {
        if request.is_empty() || request.len() > 128 { return Err("invalid fringe repair request ID".into()); }
        binding(document, session, preview)?;
        Ok(Self { request: request.into(), document: document.into(), session: session.into(), preview: preview.into() })
    }

    fn receipt_valid(&self, value: &Value) -> bool {
        let bound = format!("{}|{}|{}", self.document, self.session, self.preview);
        value["request_id"] == self.request && value.to_string().len() <= MAX_RECEIPT_BYTES
            && FringeRepairKind::valid(value, Some(&bound))
    }

    fn unknown(&self, error: &str) -> Value {
        json!({"event": "fringe_repair_result", "protocol": 1, "action": "apply",
            "request_id": self.request, "document_id": self.document, "session_id": self.session,
            "preview_id": self.preview, "success": false, "outcome_unknown": true,
            "requires_reload": true, "no_change": false, "history": null,
            "error": error.chars().take(2000).collect::<String>()})
    }
}

struct Audit { epoch: [u8; 16], identity: Identity, original: Option<Value>, sequence: usize }
#[derive(Default)]
struct Ledger { applies: HashMap<String, Audit>, client_generation: u64 }
fn ledger() -> &'static Mutex<Ledger> {
    static LEDGER: OnceLock<Mutex<Ledger>> = OnceLock::new();
    LEDGER.get_or_init(|| Mutex::new(Ledger::default()))
}
fn settled(value: &Value) -> bool { value["outcome_unknown"] == false && value["requires_reload"] == false }
fn engine_state(current: Current, epoch: [u8; 16]) -> &'static str {
    match current {
        Some((now, _)) if now != epoch => "epoch_changed",
        Some((_, true)) => "same_live_engine",
        _ => "engine_unavailable",
    }
}

impl Ledger {
    fn bootstrap(&mut self, current: Current) -> Result<Value, String> {
        self.client_generation = self.client_generation.checked_add(1).ok_or("fringe repair client generation exhausted")?;
        let mut inventory = self.inventory(current);
        inventory["client_generation"] = json!(self.client_generation.to_string());
        Ok(inventory)
    }

    fn check_client(&self, generation: u64) -> Result<(), String> {
        if generation == 0 || generation != self.client_generation {
            return Err("fringe repair client changed before apply admission; modification was not sent".into());
        }
        Ok(())
    }

    fn reserved(&self) -> usize {
        self.applies.values().map(|row| row.original.as_ref().map_or(MAX_RECEIPT_BYTES, |v| v.to_string().len())).sum()
    }

    fn admit(&mut self, epoch: [u8; 16], identity: Identity, generation: u64,
        admit: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
        // This check and row insertion share bootstrap's mutex. A submit from
        // the old webview can never pass between the new inventory and fence.
        self.check_client(generation)?;
        if epoch == [0; 16] { return Err("fringe repair engine is unavailable".into()); }
        if self.applies.contains_key(&identity.request) {
            return Err("fringe repair request was already recorded; query the original, do not reapply".into());
        }
        if self.applies.len() >= MAX_IDS || self.reserved() + MAX_RECEIPT_BYTES > MAX_BYTES {
            return Err("fringe repair audit is full; original outcomes retained, apply was not submitted".into());
        }
        // Receipt admission and native audit reservation both precede sending.
        // No terminal or pending identity is ever evicted during this process.
        admit()?;
        let sequence = self.applies.len();
        self.applies.insert(identity.request.clone(), Audit { epoch, identity, original: None, sequence });
        Ok(())
    }

    fn original(&mut self, epoch: [u8; 16], value: &Value, authoritative: bool) -> Option<Value> {
        let row = self.applies.get_mut(value["request_id"].as_str()?)?;
        if row.epoch != epoch || row.original.is_some() { return None; }
        let valid = row.identity.receipt_valid(value);
        let original = if valid { value.clone() } else {
            row.identity.unknown("invalid, mismatched or oversized fringe repair receipt; inspect actual state")
        };
        let settlement = (authoritative && valid && settled(&original)).then(|| original.clone());
        row.original = Some(original);
        settlement
    }

    fn not_sent(&mut self, epoch: [u8; 16], identity: Identity, error: &str) -> Result<(), String> {
        // Called only from a synchronous submit rejection. If admission may
        // already have happened, its row wins: absence alone is not a receipt.
        if self.applies.contains_key(&identity.request) { return Ok(()); }
        let mut receipt = identity.unknown(error);
        receipt["outcome_unknown"] = json!(false);
        receipt["requires_reload"] = json!(false);
        receipt["submission"] = json!("not_sent");
        if self.applies.len() >= MAX_IDS || self.reserved() + receipt.to_string().len() > MAX_BYTES {
            return Err("native rejection audit is full; no noncommit receipt was recorded".into());
        }
        let sequence = self.applies.len();
        self.applies.insert(identity.request.clone(), Audit { epoch, identity, original: Some(receipt), sequence });
        Ok(())
    }

    fn status(&self, request: &str) -> Option<Value> {
        let row = self.applies.get(request)?;
        Some(match &row.original {
            Some(receipt) => json!({"phase": "done", "request_id": request, "result": receipt, "audit_scope": "application-process"}),
            None => json!({"phase": "pending", "request_id": request, "audit_scope": "application-process"}),
        })
    }

    fn inventory(&self, current: Current) -> Value {
        let mut items: Vec<_> = self.applies.values().map(|row| {
            let unresolved = !row.original.as_ref().is_some_and(settled);
            let identity = &row.identity;
            let item = json!({"original_request": {"request_id": identity.request, "document_id": identity.document,
                "session_id": identity.session, "preview_id": identity.preview}, "original_receipt": row.original,
                "engine_state": engine_state(current, row.epoch), "unresolved": unresolved});
            (unresolved, row.sequence, item)
        }).collect();
        items.sort_by_key(|(unresolved, sequence, _)| (!*unresolved, *sequence));
        let items: Vec<_> = items.into_iter().map(|(_, _, item)| item).collect();
        json!({"protocol": 1, "audit_scope": "application-process", "count": items.len(), "items": items})
    }

    fn ended(&mut self, epoch: [u8; 16]) {
        for row in self.applies.values_mut().filter(|row| row.epoch == epoch && row.original.is_none()) {
            row.original = Some(row.identity.unknown("engine ended before fringe repair completion was confirmed"));
        }
    }
}

pub(crate) fn precheck_client(command: &Value) -> Result<(), String> {
    let generation = token(command["host_client_generation"].as_str().ok_or("fringe repair client generation missing")?)?;
    // Advisory early rejection before unrelated captures are invalidated.
    // Admission rechecks under the same lock as the bootstrap snapshot.
    ledger().lock().map_err(|_| "fringe repair audit lock poisoned")?.check_client(generation)
}

pub(crate) fn admit_apply(epoch: [u8; 16], command: &Value, generation: u64,
    admit: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
    let get = |key: &str| command[key].as_str().ok_or_else(|| format!("fringe repair {key} missing"));
    let identity = Identity::new(get("request_id")?, get("document_id")?, get("session_id")?, get("preview_id")?)?;
    ledger().lock().map_err(|_| "fringe repair audit lock poisoned")?.admit(epoch, identity, generation, admit)
}

pub(crate) fn record_not_sent(epoch: [u8; 16], request: &str, document: &str, session: &str, preview: &str, error: &str) -> Result<(), String> {
    let identity = Identity::new(request, document, session, preview)?;
    ledger().lock().map_err(|_| "fringe repair audit lock poisoned")?.not_sent(epoch, identity, error)
}

pub(crate) fn original_status(request: &str) -> Result<Option<Value>, String> {
    Ok(ledger().lock().map_err(|_| "fringe repair audit lock poisoned")?.status(request))
}

pub(crate) fn receive_apply(epoch: [u8; 16], value: &Value) {
    if let Ok(mut ledger) = ledger().lock() {
        if let Some(receipt) = ledger.original(epoch, value, true) {
            crate::project_recovery_fence::observed(epoch, &receipt);
        }
    }
}

pub(crate) fn retain_native_unknown(epoch: [u8; 16], value: &Value) {
    if let Ok(mut ledger) = ledger().lock() { ledger.original(epoch, value, false); }
}

pub(crate) fn ended(epoch: [u8; 16]) {
    if let Ok(mut ledger) = ledger().lock() { ledger.ended(epoch); }
}

#[tauri::command]
pub(crate) fn fringe_repair_audit(state: State<'_, Arc<AppState>>) -> Result<Value, String> {
    let engine = state.engine.lock().map_err(|_| "engine lock poisoned")?;
    let current = engine.as_ref().map(|handle| (handle.epoch(), handle.is_alive()));
    ledger().lock().map_err(|_| "fringe repair audit lock poisoned")?.bootstrap(current)
}

// Source-authored generation and original-evidence fixtures, intentionally UNRUN.
#[cfg(test)]
#[path = "fringe_repair_audit_tests.rs"]
mod tests;
