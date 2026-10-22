//! Read-only requests bypass edit invalidation, but use the same ordered engine queue.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, color_capture_host::{id16, token}};

#[tauri::command]
pub(crate) fn prompted_masks(state: State<'_, Arc<AppState>>, action: String, preview_id: String,
    capture_id: String, ticket: String, prompts: Option<Value>, device: Option<String>, candidate: Option<u64>) -> Result<Value, String> {
    id16(&preview_id)?; id16(&capture_id)?; token(&ticket)?;
    if !matches!(action.as_str(), "open"|"predict"|"poll"|"presented"|"cancel") { return Err("invalid prompted preview action".into()); }
    if action != "predict" && (prompts.is_some() || device.is_some()) || action != "presented" && candidate.is_some() {
        return Err("unexpected prompted preview arguments".into());
    }
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["prompted_masks_protocol"] != 1 {
        return Err("current engine does not support prompted previews".into());
    }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    if !handle.is_alive() { return Err("engine is not running".into()); }
    let capture = state.source_patch_capture.lock().map_err(|_| "capture lock poisoned")?;
    let proof = capture.eligible_proof(handle.epoch(), &capture_id, &ticket)?;
    if proof.descriptor["domain"] != "source-input" { return Err("prompted selection requires original-source capture".into()); }
    let document = proof.identity.document.to_string();
    let mut command = json!({"cmd":"prompted_masks","action":action,"preview_id":preview_id,
        "document_id":document,"capture_id":capture_id,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":proof.recipe_document_id,"recipe_revision":proof.recipe_revision});
    if action == "predict" {
        let prompts = prompts.ok_or("prediction requires prompts")?;
        if !prompts.is_object() || prompts.to_string().len() > 32768 { return Err("invalid or oversized prompts".into()); }
        let device = device.ok_or("choose an inference device explicitly")?;
        if !matches!(device.as_str(), "cpu"|"cuda") { return Err("invalid prompted inference device".into()); }
        command["prompts"] = prompts; command["device"] = json!(device);
    }
    if action == "presented" {
        let candidate = candidate.filter(|v| *v < 3).ok_or("invalid prompted candidate")?;
        command["candidate"] = json!(candidate);
    }
    let mut host = state.prompted_masks.lock().map_err(|_| "preview lock poisoned")?;
    if matches!(action.as_str(), "open"|"predict") {
        if host.binding.as_ref().is_some_and(|b| b.0 == preview_id) { return Err("use a fresh preview ID".into()); }
        host.begin(handle.epoch(), &preview_id, &capture_id, &ticket, &document)?;
    } else if !host.binding.as_ref().is_some_and(|b| b == &(preview_id.clone(), capture_id.clone(), ticket.clone(), document.clone())) {
        return Err("prompted preview expired".into());
    }
    if let Err(error) = handle.send(command) { host.ended(handle.epoch()); return Err(error); }
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn prompted_masks_status(state: State<'_, Arc<AppState>>, preview_id: String) -> Result<Value, String> {
    id16(&preview_id)?;
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone();
    let Some(handle) = handle.filter(|h| h.is_alive()) else { return Ok(json!({"state":"stale"})); };
    let capture = state.source_patch_capture.lock().map_err(|_| "capture lock poisoned")?;
    let mut host = state.prompted_masks.lock().map_err(|_| "preview lock poisoned")?;
    if host.binding.as_ref().is_some_and(|b| capture.eligible_proof(handle.epoch(), &b.1, &b.2).is_err()) {
        host.reset(handle.epoch());
    }
    Ok(host.status(handle.epoch(), &preview_id))
}
