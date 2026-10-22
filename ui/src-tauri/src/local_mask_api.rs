//! Canonical mask edits redeem the same displayed pre-retouch input capture.
//! Rust owns generation fencing, bounded input, queue entry, and terminal receipts.
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn request_id(id: &str) -> Result<(), String> {
    if id.is_empty() || id.len() > 128 { return Err("invalid local mask request ID".into()); }
    Ok(())
}
fn mutation(value: &Value) -> Result<(), String> {
    if !value.is_object() || value.to_string().len() > 128 * 1024 { return Err("local mask mutation is invalid or too large".into()); }
    match value["action"].as_str() {
        Some("upsert") if value["object"].is_object()
            && matches!(value["coordinate_space"].as_str(), Some("capture" | "source")) => Ok(()),
        Some("delete") if value["id"].as_str().is_some_and(|id| !id.is_empty() && id.len() <= 128) => Ok(()),
        Some("move") if value["id"].as_str().is_some_and(|id| !id.is_empty() && id.len() <= 128)
            && value["index"].as_u64().is_some_and(|index| index < 64) => Ok(()),
        Some("bind") if value["enabled"].is_boolean() => Ok(()),
        Some("accept_prompted") if value.as_object().is_some_and(|v| v.len() == 8)
            && value["preview_id"].as_str().is_some_and(|v| id16(v).is_ok())
            && value["candidate"].as_u64().is_some_and(|v| v < 3)
            && ["id", "name", "operation"].iter().all(|k| value[*k].is_string())
            && value["opacity"].is_number() && value["feather"].is_number() => Ok(()),
        Some("clear") => Ok(()),
        Some("layer_update") if value["id"].is_string() && value["name"].is_string()
            && value["enabled"].is_boolean() && value["grade"].as_array().is_some_and(|v| v.len() == 4 && v.iter().all(Value::is_number)) => Ok(()),
        Some("layer_delete") if value["id"].is_string() => Ok(()),
        Some("layer_move") if value["id"].is_string() && value["index"].as_u64().is_some_and(|v| v < 8) => Ok(()),
        Some("layer_mask") if value["id"].is_string() && matches!(value["mutation"]["action"].as_str(), Some("upsert" | "delete" | "move")) => mutation(&value["mutation"]),
        _ => Err("invalid local mask mutation".into()),
    }
}
pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let expected = command.as_object_mut().ok_or("invalid local masks command")?
        .remove("host_epoch").ok_or("local masks missing native epoch")?;
    if expected.as_str() != Some(hex(handle.epoch()).as_str()) { return Err("local mask engine generation changed before dispatch".into()); }
    let request = command["request_id"].as_str().ok_or("missing local mask request")?.to_owned();
    let bound = crate::local_mask_host::binding(
        command["document_id"].as_str().ok_or("missing local mask document")?,
        command["capture_id"].as_str().ok_or("missing local mask capture")?,
        command["ticket"].as_str().ok_or("missing local mask ticket")?)?;
    let mut host = state.local_masks.lock().map_err(|_| "local mask receipt lock poisoned")?;
    host.begin_bound(handle.epoch(), &request, "apply", Some(&bound))?;
    let result = handle.send(command);
    if let Err(error) = &result { host.failed(&request, error); }
    result
}
#[tauri::command]
pub(crate) fn local_masks(state: State<'_, Arc<AppState>>, action: String, request_id: String,
    capture_id: String, ticket: String, mutation: Value) -> Result<Value, String> {
    if action != "apply" { return Err("invalid local mask action".into()); }
    self::request_id(&request_id)?; id16(&capture_id)?; token(&ticket)?; self::mutation(&mutation)?;
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["local_masks_result_protocol"] != 1 {
        return Err("current engine does not support reviewed local masks".into());
    }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let proof = state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?
        .redeem(handle.epoch(), &capture_id, &ticket)?;
    if proof.descriptor["domain"] != "source-input" { return Err("local masks require original source-input capture".into()); }
    let group = if mutation["action"].as_str().is_some_and(|action| action.starts_with("layer_")) { mutation["id"].clone() } else { Value::Null };
    if proof.descriptor["mask_group_id"] != group { return Err("local mask capture belongs to another group; capture the selected group again".into()); }
    state.send_to_engine(json!({"cmd":"local_masks","action":"apply","request_id":request_id,
        "host_epoch":hex(proof.identity.epoch),"document_id":proof.identity.document.to_string(),
        "capture_id":capture_id,"ticket":ticket,"generation":proof.identity.generation.to_string(),
        "recipe_document_id":proof.recipe_document_id,"recipe_revision":proof.recipe_revision,"mutation":mutation}))?;
    Ok(json!({"requested":true}))
}
#[tauri::command]
pub(crate) fn local_masks_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    self::request_id(&request_id)?;
    Ok(state.local_masks.lock().map_err(|_| "local mask receipt lock poisoned")?.status(&request_id))
}
