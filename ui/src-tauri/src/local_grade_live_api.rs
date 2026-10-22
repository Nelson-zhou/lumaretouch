//! Latest-value scheduling is owned by the UI gesture, not repeated transactions.
use serde_json::{json, Value};
use std::sync::Arc;
use tauri::State;
use crate::{AppState, engine::EngineHandle, frame_identity::hex, local_grade_live_host::{binding, identity}};

pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let expected = command.as_object_mut().ok_or("invalid live grade command")?
        .remove("host_epoch").ok_or("live grade command missing engine epoch")?;
    if expected.as_str() != Some(hex(handle.epoch()).as_str()) { return Err("live grade engine changed before dispatch".into()); }
    let request = command["request_id"].as_str().ok_or("missing live grade request")?.to_owned();
    let action = command["action"].as_str().ok_or("missing live grade action")?.to_owned();
    let bound = binding(command["document_id"].as_str().ok_or("missing photo")?,
        command["session_id"].as_str().ok_or("missing gesture")?, command["group_id"].as_str().ok_or("missing group")?)?;
    let mut host = state.local_grade_live.lock().map_err(|_| "live grade receipt lock poisoned")?;
    host.begin_bound(handle.epoch(), &request, &action, Some(&bound))?;
    let sent = handle.send(command);
    if let Err(error) = &sent { host.failed(&request, error); }
    sent
}

#[tauri::command]
pub(crate) fn local_grade_live(state: State<'_, Arc<AppState>>, action: String, request_id: String,
    document_id: String, session_id: String, group_id: String, grade: Option<Value>) -> Result<Value, String> {
    if !["begin", "preview", "commit", "cancel"].contains(&action.as_str()) || !identity(&request_id, 128) {
        return Err("invalid live grade action or request identity".into());
    }
    binding(&document_id, &session_id, &group_id)?;
    let has_grade = ["begin", "preview"].contains(&action.as_str());
    if has_grade != grade.is_some() || grade.as_ref().is_some_and(|g|
        !g.as_array().is_some_and(|a| a.len() == 4 && a.iter().all(Value::is_number))) {
        return Err("invalid live grade numeric parameters".into());
    }
    let epoch = state.engine.lock().map_err(|_| "engine lock poisoned")?.as_ref()
        .ok_or("engine is not running")?.epoch();
    let mut command = json!({"cmd":"local_grade_live", "action":action, "request_id":request_id,
        "document_id":document_id, "session_id":session_id, "group_id":group_id, "host_epoch":hex(epoch)});
    if let Some(value) = grade { command["grade"] = value; }
    state.send_to_engine(command)?;
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn local_grade_live_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if !identity(&request_id, 128) { return Err("invalid live grade receipt identity".into()); }
    Ok(state.local_grade_live.lock().map_err(|_| "live grade receipt lock poisoned")?.status(&request_id))
}
