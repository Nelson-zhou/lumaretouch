//! Source LRCP authorizes geometry; displayed full-effect review authorizes apply.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn request_id(value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > 128 { return Err("invalid recovery request ID".into()); }
    Ok(())
}
fn target(value: &Value) -> bool {
    crate::effect_recovery_host::supported_target(value)
}
fn mutation(value: &Value) -> Result<(), String> {
    if !value.is_object() || value.to_string().len() > 128*1024 || !target(&value["target"]) {
        return Err("invalid or oversized recovery mutation".into());
    }
    let count = value.as_object().map_or(0, |v| v.len());
    let valid = match value["action"].as_str() {
        Some("stroke") => count == 3 && value["stroke"]["kind"] == "brush"
            && value["stroke"]["points"].as_array().is_some_and(|v| !v.is_empty() && v.len() <= 1024),
        Some("clear"|"view") => count == 2,
        Some("enable") => count == 3 && value["enabled"].is_boolean(),
        Some("delete") => count == 3 && value["id"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 64),
        _ => false,
    };
    if valid { Ok(()) } else { Err("invalid recovery action".into()) }
}

#[tauri::command]
pub(crate) fn effect_recovery_preview(state: State<'_, Arc<AppState>>, action: String, preview_id: String,
    capture_id: String, ticket: String, mutation: Option<Value>) -> Result<Value, String> {
    id16(&preview_id)?; id16(&capture_id)?; token(&ticket)?;
    if !matches!(action.as_str(), "preview"|"presented"|"cancel") || (action == "preview") != mutation.is_some() {
        return Err("invalid recovery preview arguments".into());
    }
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["effect_recovery_protocol"] != 1 {
        return Err("current engine does not support reviewed effect recovery".into());
    }
    if let Some(value) = mutation.as_ref() { self::mutation(value)?; }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let capture = state.source_patch_capture.lock().map_err(|_| "capture lock poisoned")?;
    let proof = capture.eligible_proof(handle.epoch(), &capture_id, &ticket)?;
    if proof.descriptor["domain"] != "source-input" { return Err("recovery drawing requires immutable source input".into()); }
    let document = proof.identity.document.to_string();
    let mut host = state.recovery_preview.lock().map_err(|_| "recovery preview lock poisoned")?;
    if action == "preview" {
        let selected = mutation.as_ref().ok_or("missing recovery mutation")?;
        host.begin(handle.epoch(), &preview_id, &capture_id, &ticket, &document, &selected["target"])?;
    }
    else if !host.matches(handle.epoch(), &preview_id, &capture_id, &ticket, &document) {
        return Err("recovery preview expired".into());
    }
    if action == "presented" { host.allow_presented()?; }
    let mut command = json!({"cmd":"effect_recovery_preview","action":action,"preview_id":preview_id,
        "document_id":document,"capture_id":capture_id,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":proof.recipe_document_id,
        "recipe_revision":proof.recipe_revision});
    if let Some(mutation) = mutation { command["mutation"] = mutation; }
    if let Err(error) = handle.send(command) { host.invalidate(); return Err(error); }
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn effect_recovery_preview_status(state: State<'_, Arc<AppState>>, preview_id: String) -> Result<Value, String> {
    id16(&preview_id)?;
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let capture = state.source_patch_capture.lock().map_err(|_| "capture lock poisoned")?;
    let mut host = state.recovery_preview.lock().map_err(|_| "recovery preview lock poisoned")?;
    if host.bound.as_ref().is_some_and(|b| capture.eligible_proof(handle.epoch(), &b.1, &b.2).is_err()) {
        host.invalidate();
    }
    Ok(host.status(handle.epoch(), &preview_id))
}

pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let epoch = command.as_object_mut().ok_or("invalid recovery command")?.remove("host_epoch")
        .ok_or("recovery native epoch missing")?;
    if epoch.as_str() != Some(hex(handle.epoch()).as_str()) { return Err("recovery engine changed before dispatch".into()); }
    let request = command["request_id"].as_str().ok_or("recovery request missing")?.to_owned();
    let bound = crate::effect_recovery_host::binding(
        command["document_id"].as_str().ok_or("recovery document missing")?,
        command["capture_id"].as_str().ok_or("recovery capture missing")?,
        command["ticket"].as_str().ok_or("recovery ticket missing")?,
        command["preview_id"].as_str().ok_or("recovery preview missing")?)?;
    let mut host = state.effect_recovery.lock().map_err(|_| "recovery receipt lock poisoned")?;
    host.begin_bound(handle.epoch(), &request, "apply", Some(&bound))?;
    let sent = handle.send(command);
    if let Err(error) = &sent { host.failed(&request, error); }
    sent
}

#[tauri::command]
pub(crate) fn effect_recovery(state: State<'_, Arc<AppState>>, request_id: String, preview_id: String,
    capture_id: String, ticket: String) -> Result<Value, String> {
    self::request_id(&request_id)?; id16(&preview_id)?; id16(&capture_id)?; token(&ticket)?;
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["effect_recovery_protocol"] != 1 {
        return Err("current engine does not support reviewed effect recovery".into());
    }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let proof = {
        let mut capture = state.source_patch_capture.lock().map_err(|_| "capture lock poisoned")?;
        let proof = capture.eligible_proof(handle.epoch(), &capture_id, &ticket)?;
        if proof.descriptor["domain"] != "source-input" { return Err("recovery requires source input".into()); }
        let mut preview = state.recovery_preview.lock().map_err(|_| "recovery preview lock poisoned")?;
        if !preview.matches(handle.epoch(), &preview_id, &capture_id, &ticket, &proof.identity.document.to_string()) {
            return Err("rendered recovery preview identity changed".into());
        }
        preview.redeem()?;
        capture.redeem(handle.epoch(), &capture_id, &ticket)?
    };
    state.send_to_engine(json!({"cmd":"effect_recovery","action":"apply","request_id":request_id,
        "preview_id":preview_id,"host_epoch":hex(proof.identity.epoch),"capture_id":capture_id,"ticket":ticket,
        "document_id":proof.identity.document.to_string(),"generation":proof.identity.generation.to_string(),
        "recipe_document_id":proof.recipe_document_id,"recipe_revision":proof.recipe_revision}))?;
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn effect_recovery_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    self::request_id(&request_id)?;
    Ok(state.effect_recovery.lock().map_err(|_| "recovery receipt lock poisoned")?.status(&request_id))
}

// Source fixtures only; no native tests have been run in this authoring slice.
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reviewed_face_mutations_use_the_same_exact_target_contract() {
        for name in ["facial_wrinkles", "lip_makeup", "eye_light", "blush_makeup",
            "lipstick", "eyeliner", "eyelash", "brow_makeup", "iris_makeup",
            "skin_smoothing", "fabric_fine", "background_replace", "id_background"] {
            assert!(mutation(&json!({"action":"view","target":name})).is_ok());
            assert!(mutation(&json!({"action":"clear","target":name})).is_ok());
            assert!(mutation(&json!({"action":"enable","target":name,"enabled":false})).is_ok());
            assert!(mutation(&json!({"action":"view","target":name,"source":"other"})).is_err());
            assert!(mutation(&json!({"action":"stroke","target":name,
                "stroke":{"kind":"brush","points":[]}})).is_err());
        }
        for name in ["sky", "hair", "fabric_coarse", "all", "Eye_light"] {
            assert!(mutation(&json!({"action":"view","target":name})).is_err());
        }
        assert!(!target(&Value::Null));
        assert!(!target(&json!(["eye_light"])));
    }
}
