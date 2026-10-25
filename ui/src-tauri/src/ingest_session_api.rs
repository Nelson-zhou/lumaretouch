//! Versioned, epoch-bound transport for the engine's project ingestion lease.
//! No camera, filesystem watcher or project mutation is implemented by this store.
use std::{collections::HashMap, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::AppState;

struct Receipt { epoch: [u8; 16], request: Value, result: Option<Value>, delivered_read: bool }
fn receipts() -> &'static Mutex<HashMap<String, Receipt>> {
    static STORE: OnceLock<Mutex<HashMap<String, Receipt>>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(HashMap::new()))
}
fn request_id(request: &Value) -> Result<String, String> {
    if !crate::ingest_receipt_validation::valid_request(request) {
        return Err("Invalid or oversized protocol-1 ingestion request".into());
    }
    Ok(request["request_id"].as_str().expect("validated request identity").to_owned())
}

pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    if value["event"] != "ingest_session_result" || value["protocol"] != 1
        || value.to_string().len() > 4 * 1024 * 1024 { return; }
    let Some(id) = value["request_id"].as_str() else { return; };
    let accepted = if let Ok(mut store) = receipts().lock() {
        let Some(row) = store.get(id).filter(|row| row.epoch == epoch) else { return; };
        let session_id = row.request["session_id"].as_str();
        let arm = session_id.and_then(|session_id| store.values().find(|candidate|
            candidate.epoch == epoch && candidate.request["action"] == "arm"
            && candidate.result.as_ref().is_some_and(|result|
                result["status"] == "succeeded" && result["session"]["session_id"] == session_id)));
        let original = if matches!(row.request["action"].as_str(), Some("query" | "cancel")) {
            store.values().find(|candidate| candidate.epoch == epoch
                && candidate.request["action"] == "import"
                && candidate.request["session_id"] == row.request["session_id"]
                && crate::ingest_receipt_validation::operation_id(
                    candidate.request["session_id"].as_str().unwrap_or(""),
                    candidate.request["request_id"].as_str().unwrap_or(""))
                    .ok().as_deref() == row.request["operation_id"].as_str())
        } else { None };
        let context = crate::ingest_receipt_validation::ValidationContext {
            arm_request: arm.map(|row| &row.request),
            arm_receipt: arm.and_then(|row| row.result.as_ref()),
            original_import_request: original.map(|row| &row.request),
            original_import_prior: original.and_then(|row| row.result.as_ref()),
        };
        let valid = crate::ingest_receipt_validation::accept_with_context(
            &row.request, row.result.as_ref(), value, &context);
        if valid { store.get_mut(id).expect("retained receipt").result = Some(value.clone()); }
        valid
    } else { false };
    // Never settle the project fence from an unvalidated raw engine event.
    if accepted { crate::project_recovery_fence::observed(epoch, value); }
}

pub(crate) fn submit(state: &AppState, request: Value) -> Result<Value, String> {
    let id = request_id(&request)?;
    let engine = state.engine.lock().map_err(|_| "Engine lock unavailable")?;
    let epoch = engine.as_ref().ok_or("Engine is not running")?.epoch();
    {
        let mut store = receipts().lock().map_err(|_| "Ingestion receipt lock unavailable")?;
        if let Some(old) = store.get(&id) {
            if old.epoch == epoch && old.request == request {
                return Ok(json!({"request_id":id,"requested":true,"replayed":true}));
            }
            return Err("Ingestion request identity conflict; nothing sent".into());
        }
        // Only completed reads expire. Mutating and uncertain receipts never do.
        store.retain(|_, row| !(matches!(row.request["action"].as_str(), Some("state" | "query"))
            && row.delivered_read
            && row.result.as_ref().is_some_and(|result| result["status"] == "readback")));
        let limit = if matches!(request["action"].as_str(), Some("arm" | "import")) { 240 } else { 256 };
        if store.len() >= limit {
            return Err("Ingestion receipt capacity reached; reconcile and restart before another session".into());
        }
        store.insert(id.clone(), Receipt { epoch, request:request.clone(), result:None, delivered_read:false });
    }
    drop(engine);
    state.send_to_engine_at_epoch(request, epoch).map_err(|error|
        format!("Ingestion send outcome is uncertain: {error}; query request {id}, do not replay it"))?;
    Ok(json!({"request_id":id,"requested":true}))
}

pub(crate) fn read_receipt(state: &AppState, id: &str) -> Result<Value, String> {
    if id.is_empty() || id.len() > 128 { return Err("Invalid ingestion request identity".into()); }
    let engine = state.engine.lock().map_err(|_| "Engine lock unavailable")?;
    let epoch = engine.as_ref().map(|handle| handle.epoch());
    let mut store = receipts().lock().map_err(|_| "Ingestion receipt lock unavailable")?;
    let Some(row) = store.get_mut(id) else {
        return Ok(json!({"phase":"unknown","result":null}));
    };
    if epoch != Some(row.epoch) {
        return Ok(json!({"phase":"unknown","result":null,
            "reason":"Engine epoch changed; reconcile original persisted operation, never resend"}));
    }
    // A competing owner must not evict a completed read before its consumer
    // has observed it. Only readbacks actually returned through this API expire.
    if matches!(row.request["action"].as_str(), Some("state" | "query"))
        && row.result.as_ref().is_some_and(|value| value["status"] == "readback") {
        row.delivered_read = true;
    }
    let done = row.result.as_ref().map(|value| value["status"] != "pending").unwrap_or(false);
    Ok(json!({"phase":if done {"done"} else {"pending"},"result":row.result}))
}

#[tauri::command]
pub(crate) fn ingest_session_request(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    submit(state.inner().as_ref(), request)
}
#[tauri::command]
pub(crate) fn ingest_session_status(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    read_receipt(state.inner().as_ref(), &request_id)
}

pub(crate) fn read_only(request: &Value) -> bool {
    request["cmd"] == "ingest_session"
        && matches!(request["action"].as_str(), Some("state" | "query" | "cancel"))
}
