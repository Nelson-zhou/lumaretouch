//! Native pre-WB input presentation proof; the existing WB receipt owns completion.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn engine(state: &AppState) -> Result<Arc<EngineHandle>, String> {
    state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running".into())
}
#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Region { x: u32, y: u32, width: u32, height: u32 }
impl Region {
    fn validate(&self) -> Result<(), String> {
        if self.width == 0 || self.height == 0 || u64::from(self.width)*u64::from(self.height)>121 {
            return Err("WB picker requires 1–121 sample pixels".into());
        }
        Ok(())
    }
}

// Own the exact copy lease through the blocking job AND its awaiting result.
// Dropping an abandoned IPC drops its buffer before admitting another read.
struct CaptureRead {
    state: Arc<AppState>, identity: crate::capture_wire::Identity,
    result: Option<Result<Vec<u8>, String>>, active: bool,
}
impl CaptureRead {
    fn deliver(mut self) -> Result<tauri::ipc::Response, String> {
        let result = self.result.take().ok_or("wb-input reader produced no result")?;
        let mut capture = self.state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?;
        let completion = capture.finish_copy(&self.identity, result.as_ref().err().map(String::as_str));
        self.active = false;
        match completion {
            Ok(()) => {
                capture.confirm_copied(&self.identity)?;
                Ok(tauri::ipc::Response::new(result?))
            }
            Err(error) => { drop(result); Err(error) }
        }
    }
}
impl Drop for CaptureRead {
    fn drop(&mut self) {
        if self.active {
            drop(self.result.take());
            if let Ok(mut capture) = self.state.white_balance_capture.lock() {
                let _ = capture.finish_copy(&self.identity, Some("wb-input copy delivery was abandoned"));
            }
        }
    }
}

#[tauri::command]
pub(crate) fn white_balance_capture(state: State<'_, Arc<AppState>>, action: String,
    capture_id: String, ticket: Option<String>, document_id: String) -> Result<Value, String> {
    id16(&capture_id)?; token(&document_id)?;
    match action.as_str() {
        "arm" => {
            if ticket.is_some() { return Err("arm does not accept an existing capture ticket".into()); }
            if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["white_balance_capture_protocol"] != 1 {
                return Err("current engine does not support wb-input capture".into());
            }
            let revision = {
                let report = state.doc_report.lock().map_err(|_| "document lock poisoned")?;
                if report.as_ref().and_then(|r| r["doc_state"]["document_id"].as_str()) != Some(document_id.as_str()) {
                    return Err("document changed before wb-input capture".into());
                }
                *state.doc_rev.lock().map_err(|_| "revision lock poisoned")?
            };
            let handle = engine(&state)?;
            let mut capture = state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?;
            let ticket = capture.begin(handle.epoch(), capture_id.clone(), document_id.clone(), revision)?;
            let command = json!({"cmd":"white_balance_capture","action":"arm","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"epoch":hex(handle.epoch())});
            if let Err(error) = handle.send(command) {
                capture.cancel(&capture_id, Some(&ticket), &document_id); return Err(error);
            }
            Ok(json!({"ticket":ticket}))
        }
        "presented" => {
            let ticket = ticket.ok_or("presented requires a capture ticket")?; token(&ticket)?;
            let handle = engine(&state)?;
            let mut capture = state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?;
            let proof = capture.presented(&capture_id, &ticket, &document_id)?;
            if proof.identity.epoch != handle.epoch() { capture.invalidate(); return Err("wb-input engine generation changed".into()); }
            if let Err(error) = handle.send(json!({"cmd":"white_balance_capture","action":"presented","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"generation":proof.identity.generation.to_string()})) {
                capture.invalidate(); return Err(error);
            }
            Ok(json!({"eligible":true}))
        }
        "cancel" => {
            if let Some(ticket) = &ticket { token(ticket)?; }
            let proof = state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?
                .cancel(&capture_id, ticket.as_deref(), &document_id);
            // Before arm returns the UI knows no ticket. That cancellation is
            // local only; its eventual ticket-bearing cancellation is forwarded
            // even if this local record has already been invalidated.
            if let Some(ticket) = ticket {
                if let Ok(handle) = engine(&state) {
                    let mut command = json!({"cmd":"white_balance_capture","action":"cancel","capture_id":capture_id,
                        "ticket":ticket,"document_id":document_id});
                    if let Some(proof) = proof.filter(|p| p.identity.epoch == handle.epoch()) {
                        command["generation"] = json!(proof.identity.generation.to_string());
                    }
                    handle.send(command)?;
                }
            }
            Ok(json!({"cancelled":true}))
        }
        _ => Err("invalid WB capture action".into()),
    }
}

#[tauri::command]
pub(crate) fn white_balance_capture_status(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<Value, String> {
    id16(&capture_id)?; token(&ticket)?;
    Ok(state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?.status_for(&capture_id, &ticket))
}

#[tauri::command]
pub(crate) async fn white_balance_capture_frame(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<tauri::ipc::Response, String> {
    id16(&capture_id)?; token(&ticket)?;
    let st = state.inner().clone();
    let root = st.inspection_root.lock().map_err(|_| "inspection root lock poisoned")?.clone().ok_or("wb-input root unavailable")?;
    let identity = st.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?.begin_copy(&capture_id, &ticket)?;
    let mut read = CaptureRead { state: st, identity, result: None, active: true };
    // No capture mutex during disk I/O. The result's Drop also runs if its
    // awaiting IPC was cancelled or the blocking worker unwinds.
    let read = tauri::async_runtime::spawn_blocking(move || {
        read.result = Some(root.read_wb_capture(&read.identity)); read
    }).await.map_err(|error| format!("wb-input reader failed: {error}"))?;
    read.deliver()
}

#[tauri::command]
pub(crate) fn white_balance_pick(state: State<'_, Arc<AppState>>, request_id: String, capture_id: String,
    ticket: String, region: Region) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid WB request ID".into()); }
    id16(&capture_id)?; token(&ticket)?; region.validate()?;
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["white_balance_result_protocol"] != 1 {
        return Err("current engine does not support reviewed WB actions".into());
    }
    let handle = engine(&state)?;
    // Native ownership binds all producer identities; IPC only supplies a bounded region.
    let proof = state.white_balance_capture.lock().map_err(|_| "WB capture lock poisoned")?
        .redeem(handle.epoch(), &capture_id, &ticket)?;
    if u64::from(region.x)+u64::from(region.width)>u64::from(proof.identity.width)
        || u64::from(region.y)+u64::from(region.height)>u64::from(proof.identity.height) {
        return Err("WB region exceeds its presented image".into());
    }
    let command = json!({"cmd":"white_balance","action":"pick","request_id":request_id,
        "host_epoch":hex(proof.identity.epoch),"document_id":proof.identity.document.to_string(),"capture_id":capture_id,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":proof.recipe_document_id,
        "recipe_revision":proof.recipe_revision,"region":region});
    state.send_to_engine(command)?;
    Ok(json!({"requested":true}))
}
