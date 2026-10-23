//! Native targeted color input presentation proof; the existing targeted color receipt owns completion.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn engine(state: &AppState) -> Result<Arc<EngineHandle>, String> {
    state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running".into())
}
#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Region { pub x: u32, pub y: u32, pub width: u32, pub height: u32 }
impl Region {
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.width == 0 || self.height == 0 || u64::from(self.width)*u64::from(self.height)>121 {
            return Err("targeted color picker requires 1–121 sample pixels".into());
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
        let result = self.result.take().ok_or("color-action-input reader produced no result")?;
        let mut capture = self.state.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?;
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
            if let Ok(mut capture) = self.state.color_picker_capture.lock() {
                let _ = capture.finish_copy(&self.identity, Some("color-action-input copy delivery was abandoned"));
            }
        }
    }
}

#[tauri::command]
pub(crate) fn color_picker_capture(state: State<'_, Arc<AppState>>, action: String,
    capture_id: String, ticket: Option<String>, document_id: String, picker_action: Option<String>, picker_channel: Option<String>, reference: Option<Value>) -> Result<Value, String> {
    id16(&capture_id)?; token(&document_id)?;
    if action!="arm" && reference.is_some(){return Err("reference is only valid while arming a capture".into());}
    match action.as_str() {
        "arm" => {
            if ticket.is_some() { return Err("arm does not accept an existing capture ticket".into()); }
            if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["color_picker_capture_protocol"] != 1 {
                return Err("current engine does not support color-action-input capture".into());
            }
            let action = picker_action.ok_or("missing color picker action")?;
            let channel = picker_channel.ok_or("missing color picker channel")?;
            crate::color_picker_host::selection(&action, &channel)?;
            if reference.is_some() && action!="id_background_reference" {return Err("reference is only accepted by the reference-image picker".into());}
            if action=="id_background_reference" && !reference.as_ref().is_some_and(|v|v.is_object()&&v.to_string().len()<=4096){return Err("choose a verified library reference first".into());}
            let revision = {
                let report = state.doc_report.lock().map_err(|_| "document lock poisoned")?;
                if report.as_ref().and_then(|r| r["doc_state"]["document_id"].as_str()) != Some(document_id.as_str()) {
                    return Err("document changed before color-action-input capture".into());
                }
                *state.doc_rev.lock().map_err(|_| "revision lock poisoned")?
            };
            let handle = engine(&state)?;
            let mut capture = state.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?;
            let ticket = capture.begin(handle.epoch(), capture_id.clone(), document_id.clone(), revision, action.clone(), channel.clone())?;
            let mut command = json!({"cmd":"color_picker_capture","action":"arm","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"epoch":hex(handle.epoch()),"picker_action":action,"picker_channel":channel});
            if let Some(value)=reference {command["reference"]=value;}
            if let Err(error) = handle.send(command) {
                capture.cancel(&capture_id, Some(&ticket), &document_id); return Err(error);
            }
            Ok(json!({"ticket":ticket}))
        }
        "presented" => {
            let ticket = ticket.ok_or("presented requires a capture ticket")?; token(&ticket)?;
            let handle = engine(&state)?;
            let mut capture = state.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?;
            let proof = capture.presented(&capture_id, &ticket, &document_id)?;
            if proof.identity.epoch != handle.epoch() { capture.invalidate(); return Err("color-action-input engine generation changed".into()); }
            if let Err(error) = handle.send(json!({"cmd":"color_picker_capture","action":"presented","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"generation":proof.identity.generation.to_string()})) {
                capture.invalidate(); return Err(error);
            }
            Ok(json!({"eligible":true}))
        }
        "cancel" => {
            if let Some(ticket) = &ticket { token(ticket)?; }
            let proof = state.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?
                .cancel(&capture_id, ticket.as_deref(), &document_id);
            // Before arm returns the UI knows no ticket. That cancellation is
            // local only; its eventual ticket-bearing cancellation is forwarded
            // even if this local record has already been invalidated.
            if let Some(ticket) = ticket {
                if let Ok(handle) = engine(&state) {
                    let mut command = json!({"cmd":"color_picker_capture","action":"cancel","capture_id":capture_id,
                        "ticket":ticket,"document_id":document_id});
                    if let Some(proof) = proof.filter(|p| p.identity.epoch == handle.epoch()) {
                        command["generation"] = json!(proof.identity.generation.to_string());
                    }
                    handle.send(command)?;
                }
            }
            Ok(json!({"cancelled":true}))
        }
        _ => Err("invalid targeted color capture action".into()),
    }
}

#[tauri::command]
pub(crate) fn color_picker_capture_status(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<Value, String> {
    id16(&capture_id)?; token(&ticket)?;
    Ok(state.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?.status_for(&capture_id, &ticket))
}

#[tauri::command]
pub(crate) async fn color_picker_capture_frame(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<tauri::ipc::Response, String> {
    id16(&capture_id)?; token(&ticket)?;
    let st = state.inner().clone();
    let root = st.inspection_root.lock().map_err(|_| "inspection root lock poisoned")?.clone().ok_or("color-action-input root unavailable")?;
    let identity = st.color_picker_capture.lock().map_err(|_| "targeted color capture lock poisoned")?.begin_copy(&capture_id, &ticket)?;
    let mut read = CaptureRead { state: st, identity, result: None, active: true };
    // No capture mutex during disk I/O. The result's Drop also runs if its
    // awaiting IPC was cancelled or the blocking worker unwinds.
    let read = tauri::async_runtime::spawn_blocking(move || {
        read.result = Some(root.read_color_picker_capture(&read.identity)); read
    }).await.map_err(|error| format!("color-action-input reader failed: {error}"))?;
    read.deliver()
}
