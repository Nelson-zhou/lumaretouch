//! Reviewed common background transport, independent from studio cleanup.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn mutation(value: &Value) -> Result<(), String> {
    let Some(object) = value.as_object() else { return Err("background mutation must be an object".into()) };
    let in_range = |key: &str, minimum: f64| value[key].as_f64()
        .is_some_and(|number| number.is_finite() && (minimum..=1.0).contains(&number));
    let valid = match value["action"].as_str() {
        Some("set") => object.len() == 4 && in_range("tol", 0.0) && in_range("softness", 0.001)
            && value["bg"].as_array().is_some_and(|rgb| rgb.len() == 3
                && rgb.iter().all(|channel| channel.as_u64().is_some_and(|n| n <= 255))),
        Some("clear") => object.len() == 1,
        _ => false,
    };
    if valid { Ok(()) } else { Err("invalid common background mutation".into()) }
}

fn supported(state: &AppState) -> Result<(), String> {
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["common_background_protocol"] != 1 {
        return Err("engine does not support reviewed common background".into());
    }
    Ok(())
}

#[tauri::command]
pub(crate) fn common_background_preview(state: State<'_, Arc<AppState>>, action: String,
    preview_id: String, session_id: String, document_id: String, mutation: Option<Value>) -> Result<Value, String> {
    supported(&state)?;
    id16(&preview_id)?; id16(&session_id)?; token(&document_id)?;
    if !matches!(action.as_str(), "preview" | "presented" | "cancel") || (action == "preview") != mutation.is_some() {
        return Err("invalid common background preview action".into());
    }
    if let Some(value) = mutation.as_ref() { self::mutation(value)?; }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut host = state.common_background_preview.lock().map_err(|_| "common background preview lock poisoned")?;
    if action == "preview" { host.begin(handle.epoch(), &document_id, &session_id, &preview_id)?; }
    else if !host.matches(handle.epoch(), &document_id, &session_id, &preview_id) {
        if action == "cancel" { return Ok(json!({"discarded": true})); }
        return Err("common background preview was replaced".into());
    }
    if action == "presented" { host.presentation_requested()?; }
    // Revoke submission before cancellation enters the queue, not after an ACK.
    if action == "cancel" { host.cancel_requested(); }
    let mut command = json!({"cmd": "common_background_preview", "action": action,
        "preview_id": preview_id, "session_id": session_id, "document_id": document_id});
    if let Some(value) = mutation { command["mutation"] = value; }
    if let Err(error) = handle.send(command) { host.invalidate(); return Err(error); }
    Ok(json!({"requested": true}))
}

#[tauri::command]
pub(crate) fn common_background_preview_status(state: State<'_, Arc<AppState>>, preview_id: String) -> Result<Value, String> {
    id16(&preview_id)?;
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let value = state.common_background_preview.lock().map_err(|_| "common background preview lock poisoned")?
        .status(handle.epoch(), &preview_id);
    Ok(value)
}

pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let epoch = command.as_object_mut().ok_or("invalid common background command")?
        .remove("host_epoch").ok_or("common background epoch missing")?;
    if epoch.as_str() != Some(hex(handle.epoch()).as_str()) {
        return Err("common background engine changed before dispatch".into());
    }
    let generation = command.as_object_mut().ok_or("invalid common background command")?
        .remove("host_client_generation").ok_or("common background client generation missing")?;
    let generation = token(generation.as_str().ok_or("invalid common background client generation")?)?;
    if command["action"] != "apply" { return Err("invalid common background apply action".into()); }
    let request = command["request_id"].as_str().ok_or("common background request missing")?.to_owned();
    let document = command["document_id"].as_str().ok_or("document missing")?;
    let session = command["session_id"].as_str().ok_or("session missing")?;
    let preview_id = command["preview_id"].as_str().ok_or("preview missing")?;
    let bound = crate::common_background_host::binding(document, session, preview_id)?;
    // AppState holds the current engine lock here. Keep the proof lock through
    // receipt admission and the unkeyed send so another mutation cannot slip
    // between proof redemption and queue admission.
    let mut preview = state.common_background_preview.lock().map_err(|_| "common background preview lock poisoned")?;
    if !preview.matches(handle.epoch(), document, session, preview_id) {
        return Err("common background output changed before apply".into());
    }
    preview.can_redeem()?;
    let mut receipts = state.common_background.lock().map_err(|_| "common background receipt lock poisoned")?;
    crate::common_background_readback::admit_apply(handle.epoch(), &command, generation, ||
        receipts.begin_bound(handle.epoch(), &request, "apply", Some(&bound)))?;
    preview.redeem()?;
    let sent = handle.send(command);
    if let Err(error) = &sent {
        receipts.failed(&request, error);
        crate::common_background_readback::retain_native_unknown(handle.epoch(), &receipts.status(&request)["result"]);
    }
    sent
}

#[tauri::command]
pub(crate) fn common_background(state: State<'_, Arc<AppState>>, request_id: String,
    preview_id: String, session_id: String, document_id: String, client_generation: Option<String>) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid common background request ID".into()); }
    id16(&preview_id)?; id16(&session_id)?; token(&document_id)?;
    let mut epoch = [0; 16];
    let sent = (|| -> Result<Value, String> {
        let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
        epoch = handle.epoch();
        supported(&state)?;
        let generation = client_generation.as_deref().ok_or("common background client bootstrap missing")?;
        token(generation)?;
        state.send_to_engine(json!({"cmd": "common_background", "action": "apply", "request_id": request_id,
            "preview_id": preview_id, "session_id": session_id, "document_id": document_id,
            "host_epoch": hex(epoch), "host_client_generation": generation}))?;
        Ok(json!({"requested": true}))
    })();
    if let Err(error) = &sent {
        // A ledger row is inserted before a send can occur. Only its verified
        // absence on this synchronous error path permits a not-sent receipt.
        crate::common_background_readback::record_not_sent(epoch, &request_id, &document_id, &session_id, &preview_id, error)?;
    }
    sent
}

#[tauri::command]
pub(crate) fn common_background_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid common background request ID".into()); }
    // The audit validates both arrival orders against authoritative readback.
    // Its first original, including native unknown, must win over generic state.
    if let Some(retained) = crate::common_background_readback::original_status(&request_id)? { return Ok(retained); }
    Ok(state.common_background.lock().map_err(|_| "common background receipt lock poisoned")?.status(&request_id))
}

// Source-authored validation fixtures, intentionally UNRUN.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_exact_set_and_clear_mutations_are_admitted() {
        assert!(mutation(&json!({"action": "clear"})).is_ok());
        for (tol, softness) in [(0.0, 0.001), (1.0, 1.0)] {
            assert!(mutation(&json!({"action": "set", "bg": [0, 127, 255], "tol": tol, "softness": softness})).is_ok());
        }
        for invalid in [
            json!({"action": "clear", "bg": [0, 0, 0]}),
            json!({"action": "view"}),
            json!({"action": "set", "bg": [0, 0], "tol": 0.2, "softness": 0.1}),
            json!({"action": "set", "bg": [0, -1, 0], "tol": 0.2, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 256, 0], "tol": 0.2, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 0.5, 0], "tol": 0.2, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": -0.1, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": 1.1, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": null, "softness": 0.1}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": 0.2, "softness": 0.0}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": 0.2, "softness": 1.1}),
            json!({"action": "set", "bg": [0, 0, 0], "tol": 0.2, "softness": 0.1, "backend": "birefnet"}),
        ] { assert!(mutation(&invalid).is_err(), "unexpected admitted mutation: {invalid}"); }
    }
}
