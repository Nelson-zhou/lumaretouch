//! Reviewed fringe-repair transport. Only the exact presented proof may apply.
use std::{collections::HashSet, sync::Arc};
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn unit(value: &Value) -> bool { value.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n)) }

fn mutation(value: &Value) -> Result<(), String> {
    let Some(object) = value.as_object() else { return Err("fringe repair mutation must be an object".into()) };
    if value["action"] == "enter" && object.len() == 1 { return Ok(()); }
    if value["action"] != "set" || object.len() != 5 || !value["enabled"].is_boolean()
        || !value["reset_coverage"].is_boolean()
        || !value["strength"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n)) {
        return Err("invalid fringe repair set mutation".into());
    }
    let strokes = value["strokes"].as_array().ok_or("fringe repair strokes must be an array")?;
    if strokes.len() > 128 { return Err("too many fringe repair strokes".into()); }
    let mut ids = HashSet::new();
    let mut points_total = 0usize;
    for stroke in strokes {
        let object = stroke.as_object().ok_or("invalid fringe repair stroke")?;
        let id = stroke["id"].as_str().ok_or("fringe repair stroke ID missing")?;
        id16(id)?;
        if !ids.insert(id) || object.len() != 6 || !matches!(stroke["mode"].as_str(), Some("add" | "subtract"))
            || !stroke["radius"].as_f64().is_some_and(|n| n.is_finite() && n > 0.0 && n <= 0.5)
            || !unit(&stroke["opacity"]) || !unit(&stroke["feather"]) {
            return Err("invalid fringe repair stroke controls".into());
        }
        let points = stroke["points"].as_array().ok_or("fringe repair stroke points missing")?;
        points_total = points_total.checked_add(points.len()).ok_or("fringe repair point count overflow")?;
        if points.is_empty() || points.len() > 1024 || points_total > 8192 || !points.iter().all(|point|
            point.as_array().is_some_and(|xy| xy.len() == 2 && xy.iter().all(unit))) {
            return Err("invalid or excessive fringe repair stroke points".into());
        }
    }
    Ok(())
}

fn supported(state: &AppState) -> Result<(), String> {
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["fringe_repair_protocol"] != 1 {
        return Err("engine does not support reviewed fringe repair".into());
    }
    Ok(())
}

#[tauri::command]
pub(crate) fn fringe_repair_preview(state: State<'_, Arc<AppState>>, action: String,
    preview_id: String, session_id: String, document_id: String, mutation: Option<Value>) -> Result<Value, String> {
    supported(&state)?;
    id16(&preview_id)?; id16(&session_id)?; token(&document_id)?;
    if !matches!(action.as_str(), "preview" | "presented" | "cancel") || (action == "preview") != mutation.is_some() {
        return Err("invalid fringe repair preview action".into());
    }
    if let Some(value) = mutation.as_ref() { self::mutation(value)?; }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let mut host = state.fringe_repair_preview.lock().map_err(|_| "fringe repair preview lock poisoned")?;
    if action == "preview" { host.begin(handle.epoch(), &document_id, &session_id, &preview_id)?; }
    else if !host.matches(handle.epoch(), &document_id, &session_id, &preview_id) {
        if action == "cancel" { return Ok(json!({"discarded": true})); }
        return Err("fringe repair preview was replaced".into());
    }
    if action == "presented" { host.presentation_requested()?; }
    // Cancel revokes apply synchronously, before any engine ACK can arrive.
    if action == "cancel" { host.cancel_requested(); }
    let mut command = json!({"cmd": "fringe_repair_preview", "action": action,
        "preview_id": preview_id, "session_id": session_id, "document_id": document_id});
    if let Some(value) = mutation { command["mutation"] = value; }
    if let Err(error) = handle.send(command) { host.invalidate(); return Err(error); }
    Ok(json!({"requested": true}))
}

#[tauri::command]
pub(crate) fn fringe_repair_preview_status(state: State<'_, Arc<AppState>>, preview_id: String) -> Result<Value, String> {
    id16(&preview_id)?;
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let value = state.fringe_repair_preview.lock().map_err(|_| "fringe repair preview lock poisoned")?
        .status(handle.epoch(), &preview_id);
    Ok(value)
}

pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let epoch = command.as_object_mut().ok_or("invalid fringe repair command")?
        .remove("host_epoch").ok_or("fringe repair epoch missing")?;
    if epoch.as_str() != Some(hex(handle.epoch()).as_str()) { return Err("fringe repair engine changed before dispatch".into()); }
    let generation = command.as_object_mut().ok_or("invalid fringe repair command")?
        .remove("host_client_generation").ok_or("fringe repair client generation missing")?;
    let generation = token(generation.as_str().ok_or("invalid fringe repair client generation")?)?;
    if command["action"] != "apply" { return Err("invalid fringe repair apply action".into()); }
    let request = command["request_id"].as_str().ok_or("fringe repair request missing")?.to_owned();
    let document = command["document_id"].as_str().ok_or("document missing")?;
    let session = command["session_id"].as_str().ok_or("session missing")?;
    let preview_id = command["preview_id"].as_str().ok_or("preview missing")?;
    let bound = crate::fringe_repair_host::binding(document, session, preview_id)?;
    // Native dispatch holds the current engine lock. Keep proof and receipt
    // admission atomic with the unkeyed send; no mutation can redeem this twice.
    let mut preview = state.fringe_repair_preview.lock().map_err(|_| "fringe repair preview lock poisoned")?;
    if !preview.matches(handle.epoch(), document, session, preview_id) {
        return Err("fringe repair output changed before apply".into());
    }
    preview.can_redeem()?;
    let mut receipts = state.fringe_repair.lock().map_err(|_| "fringe repair receipt lock poisoned")?;
    crate::fringe_repair_audit::admit_apply(handle.epoch(), &command, generation, ||
        receipts.begin_bound(handle.epoch(), &request, "apply", Some(&bound)))?;
    preview.redeem()?;
    let sent = handle.send(command);
    if let Err(error) = &sent {
        receipts.failed(&request, error);
        crate::fringe_repair_audit::retain_native_unknown(handle.epoch(), &receipts.status(&request)["result"]);
    }
    sent
}

#[tauri::command]
pub(crate) fn fringe_repair(state: State<'_, Arc<AppState>>, request_id: String,
    preview_id: String, session_id: String, document_id: String, client_generation: Option<String>) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid fringe repair request ID".into()); }
    id16(&preview_id)?; id16(&session_id)?; token(&document_id)?;
    let mut epoch = [0; 16];
    let sent = (|| -> Result<Value, String> {
        let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
        epoch = handle.epoch();
        supported(&state)?;
        let generation = client_generation.as_deref().ok_or("fringe repair client bootstrap missing")?;
        token(generation)?;
        state.send_to_engine(json!({"cmd": "fringe_repair", "action": "apply", "request_id": request_id,
            "preview_id": preview_id, "session_id": session_id, "document_id": document_id,
            "host_epoch": hex(epoch), "host_client_generation": generation}))?;
        Ok(json!({"requested": true}))
    })();
    if let Err(error) = &sent {
        crate::fringe_repair_audit::record_not_sent(epoch, &request_id, &document_id, &session_id, &preview_id, error)?;
    }
    sent
}

#[tauri::command]
pub(crate) fn fringe_repair_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid fringe repair request ID".into()); }
    // Process originals, including unknown outcomes, beat evictable host state.
    if let Some(original) = crate::fringe_repair_audit::original_status(&request_id)? { return Ok(original); }
    Ok(state.fringe_repair.lock().map_err(|_| "fringe repair receipt lock poisoned")?.status(&request_id))
}

// Source-authored ingress validation fixtures only; intentionally UNRUN.
#[cfg(test)]
#[path = "fringe_repair_api_tests.rs"]
mod tests;
