//! Source patch uses its own input capture and the existing ordered edit queue.
use std::sync::Arc;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, engine::EngineHandle, color_capture_host::{id16, token}, frame_identity::hex};

fn engine(state: &AppState) -> Result<Arc<EngineHandle>, String> {
    state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running".into())
}
fn geometry(polygon: &[[f64;2]], offset: &[f64;2]) -> Result<(), String> {
    if !(3..=256).contains(&polygon.len()) || !polygon.iter().flatten().all(|n| n.is_finite() && (0.0..=1.0).contains(n)) {
        return Err("source patch needs 3 to 256 finite normalized polygon points".into());
    }
    if !offset.iter().all(|n| n.is_finite() && (-1.0..=1.0).contains(n)) { return Err("invalid normalized source patch offset".into()); }
    Ok(())
}

// Own the exact copy lease through the blocking job AND its awaiting result.
// Dropping an abandoned IPC drops its buffer before admitting another read.
struct CaptureRead {
    state: Arc<AppState>, identity: crate::capture_wire::Identity,
    result: Option<Result<Vec<u8>, String>>, active: bool,
}
impl CaptureRead {
    fn deliver(mut self) -> Result<tauri::ipc::Response, String> {
        let result = self.result.take().ok_or("repair-input reader produced no result")?;
        let mut capture = self.state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?;
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
            if let Ok(mut capture) = self.state.source_patch_capture.lock() {
                let _ = capture.finish_copy(&self.identity, Some("repair-input copy delivery was abandoned"));
            }
        }
    }
}

/// Called by AppState::send_to_engine, after its ordinary edit invalidations.
/// The private epoch is removed before dispatch and prevents a redeemed proof
/// from being relabelled if the process restarted between IPC and queue entry.
pub(crate) fn enqueue(state: &AppState, handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let expected_epoch = command.as_object_mut().ok_or("invalid source patch command")?
        .remove("host_epoch").ok_or("source patch is missing its native epoch")?;
    let current_epoch = hex(handle.epoch());
    if expected_epoch.as_str() != Some(current_epoch.as_str()) { return Err("source patch engine generation changed before dispatch".into()); }
    let request = command["request_id"].as_str().ok_or("missing source patch request")?.to_owned();
    let bound = crate::source_patch_host::binding(
        command["document_id"].as_str().ok_or("missing source patch document")?,
        command["capture_id"].as_str().ok_or("missing source patch capture")?,
        command["ticket"].as_str().ok_or("missing source patch ticket")?)?;
    let mut host = state.source_patch.lock().map_err(|_| "source patch receipt lock poisoned")?;
    host.begin_bound(handle.epoch(), &request, "apply", Some(&bound))?;
    // No interactive/coalescing key: each apply is a distinct ordered edit.
    let result = handle.send(command);
    if let Err(error) = &result { host.failed(&request, error); }
    result
}

#[tauri::command]
pub(crate) fn source_patch_capture(state: State<'_, Arc<AppState>>, action: String,
    capture_id: String, ticket: Option<String>, document_id: String, purpose: Option<String>, group_id: Option<String>) -> Result<Value, String> {
    id16(&capture_id)?; token(&document_id)?;
    if action != "arm" && purpose.is_some() { return Err("capture purpose is only accepted when arming".into()); }
    let domain = match purpose.as_deref() { None | Some("repair") => "repair-input", Some("local-masks") => "source-input", _ => return Err("invalid capture purpose".into()) };
    if group_id.is_some() && (action != "arm" || domain != "source-input") { return Err("group ID is only accepted when arming local masks".into()); }
    match action.as_str() {
        "arm" => {
            if ticket.is_some() { return Err("arm does not accept an existing capture ticket".into()); }
            if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["source_patch_capture_protocol"] != 1 {
                return Err("current engine does not support repair-input capture".into());
            }
            let revision = {
                let report = state.doc_report.lock().map_err(|_| "document lock poisoned")?;
                if report.as_ref().and_then(|r| r["doc_state"]["document_id"].as_str()) != Some(document_id.as_str()) {
                    return Err("document changed before repair-input capture".into());
                }
                *state.doc_rev.lock().map_err(|_| "revision lock poisoned")?
            };
            let handle = engine(&state)?;
            let mut capture = state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?;
            let ticket = capture.begin_for_scope(handle.epoch(), capture_id.clone(), document_id.clone(), revision, domain, group_id.clone())?;
            let mut command = json!({"cmd":"source_patch_capture","action":"arm","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"epoch":hex(handle.epoch()),"purpose":purpose.unwrap_or_else(|| "repair".into())});
            if domain == "source-input" { command["group_id"] = json!(group_id); }
            if let Err(error) = handle.send(command) {
                capture.cancel(&capture_id, Some(&ticket), &document_id); return Err(error);
            }
            Ok(json!({"ticket":ticket}))
        }
        "presented" => {
            let ticket = ticket.ok_or("presented requires a capture ticket")?; token(&ticket)?;
            let handle = engine(&state)?;
            let mut capture = state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?;
            let proof = capture.presented(&capture_id, &ticket, &document_id)?;
            if proof.identity.epoch != handle.epoch() { capture.invalidate(); return Err("repair-input engine generation changed".into()); }
            if let Err(error) = handle.send(json!({"cmd":"source_patch_capture","action":"presented","capture_id":capture_id,
                "ticket":ticket,"document_id":document_id,"generation":proof.identity.generation.to_string()})) {
                capture.invalidate(); return Err(error);
            }
            Ok(json!({"eligible":true}))
        }
        "cancel" => {
            if let Some(ticket) = &ticket { token(ticket)?; }
            let proof = state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?
                .cancel(&capture_id, ticket.as_deref(), &document_id);
            // Before arm returns the UI knows no ticket. That cancellation is
            // local only; its eventual ticket-bearing cancellation is forwarded
            // even if this local record has already been invalidated.
            if let Some(ticket) = ticket {
                if let Ok(handle) = engine(&state) {
                    let mut command = json!({"cmd":"source_patch_capture","action":"cancel","capture_id":capture_id,
                        "ticket":ticket,"document_id":document_id});
                    if let Some(proof) = proof.filter(|p| p.identity.epoch == handle.epoch()) {
                        command["generation"] = json!(proof.identity.generation.to_string());
                    }
                    handle.send(command)?;
                }
            }
            Ok(json!({"cancelled":true}))
        }
        _ => Err("invalid source patch capture action".into()),
    }
}

#[tauri::command]
pub(crate) fn source_patch_capture_status(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<Value, String> {
    id16(&capture_id)?; token(&ticket)?;
    Ok(state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?.status_for(&capture_id, &ticket))
}

#[tauri::command]
pub(crate) async fn source_patch_capture_frame(state: State<'_, Arc<AppState>>, capture_id: String, ticket: String) -> Result<tauri::ipc::Response, String> {
    id16(&capture_id)?; token(&ticket)?;
    let st = state.inner().clone();
    let root = st.inspection_root.lock().map_err(|_| "inspection root lock poisoned")?.clone().ok_or("repair-input root unavailable")?;
    let identity = st.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?.begin_copy(&capture_id, &ticket)?;
    let mut read = CaptureRead { state: st, identity, result: None, active: true };
    // No capture mutex during disk I/O. The result's Drop also runs if its
    // awaiting IPC was cancelled or the blocking worker unwinds.
    let read = tauri::async_runtime::spawn_blocking(move || {
        read.result = Some(root.read_capture(&read.identity)); read
    }).await.map_err(|error| format!("repair-input reader failed: {error}"))?;
    read.deliver()
}

#[tauri::command]
pub(crate) fn source_patch(state: State<'_, Arc<AppState>>, request_id: String, capture_id: String,
    ticket: String, polygon: Vec<[f64;2]>, offset: [f64;2]) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid source patch request ID".into()); }
    id16(&capture_id)?; token(&ticket)?; geometry(&polygon, &offset)?;
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["source_patch_result_protocol"] != 1 {
        return Err("current engine does not support reviewed source patch actions".into());
    }
    let handle = engine(&state)?;
    // Redeem before the ordinary path invalidates all editable captures. No UI
    // RGB, projection, gains, generation, recipe ID or revision is accepted.
    let proof = state.source_patch_capture.lock().map_err(|_| "source patch capture lock poisoned")?
        .redeem(handle.epoch(), &capture_id, &ticket)?;
    if proof.descriptor["domain"] != "repair-input" { return Err("source patch requires repair-input capture".into()); }
    let command = json!({"cmd":"source_patch","action":"apply","request_id":request_id,
        "host_epoch":hex(proof.identity.epoch),"document_id":proof.identity.document.to_string(),"capture_id":capture_id,"ticket":ticket,
        "generation":proof.identity.generation.to_string(),"recipe_document_id":proof.recipe_document_id,
        "recipe_revision":proof.recipe_revision,"polygon":polygon,"offset":offset});
    state.send_to_engine(command)?;
    Ok(json!({"requested":true}))
}

#[tauri::command]
pub(crate) fn source_patch_result(state: State<'_, Arc<AppState>>, request_id: String) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid source patch request ID".into()); }
    Ok(state.source_patch.lock().map_err(|_| "source patch receipt lock poisoned")?.status(&request_id))
}

#[cfg(test)]
mod tests {
    use super::*;
    const CAP: &str = "0123456789abcdef0123456789abcdef";
    fn ready_capture(host: &mut crate::source_patch_capture_host::SourcePatchCaptureHost) -> String {
        let ticket=host.begin([1;16],CAP.into(),"123".into(),4).unwrap();
        host.armed_event([1;16],&json!({"event":"source_patch_capture","action":"arm","success":true,"capture_id":CAP,"ticket":ticket,
            "descriptor":{"version":1,"epoch":hex([1;16]),"domain":"repair-input","quality":"proxy-float-input","profile":"working-srgb",
            "shm_instance":"11111111111111111111111111111111","seq":"1","generation":"7","document_id":"123",
            "recipe_document_id":"22222222222222222222222222222222","recipe_revision":"0","width":2,"height":2,"presentation_width":2,"presentation_height":2,"full_source":[20,20],
            "projection":{"version":"crop-rotate-fixed-proxy-v1","source_proxy":[2,2],"rect":[0,0,1,1],"integer_crop":[0,0,2,2],
                "rotation":0,"quarter_turn":0,"rotated":[2,2],"target":[2,2],"resize":"bilinear","align_corners":false,"antialias":false}}}),4);
        ticket
    }
    fn completed_read() -> (CaptureRead, String) {
        let state=Arc::new(AppState::new());
        let (identity,ticket)={let mut host=state.source_patch_capture.lock().unwrap();host.reset([1;16]);host.ready([1;16],true);
            let ticket=ready_capture(&mut host);(host.begin_copy(CAP,&ticket).unwrap(),ticket)};
        (CaptureRead {state,identity,result:Some(Ok(vec![0;16])),active:true},ticket)
    }
    #[test] fn geometry_accepts_only_bounded_finite_normalized_inputs() {
        let polygon = [[0.1,0.1],[0.3,0.1],[0.2,0.3]];
        assert!(geometry(&polygon,&[0.1,-0.1]).is_ok());
        assert!(geometry(&polygon[..2],&[0.0,0.0]).is_err());
        assert!(geometry(&vec![[0.5,0.5];257],&[0.0,0.0]).is_err());
        for n in [f64::NAN,f64::INFINITY,-0.1,1.1] {
            let mut bad=polygon;bad[1][0]=n;assert!(geometry(&bad,&[0.0,0.0]).is_err());
        }
        for n in [f64::NAN,f64::INFINITY,-1.1,1.1] { assert!(geometry(&polygon,&[n,0.0]).is_err()); }
    }
    #[test] fn unconsumed_worker_result_keeps_the_single_copy_lease_until_drop() {
        let (read,_)=completed_read();let state=read.state.clone();
        let ticket={let mut host=state.source_patch_capture.lock().unwrap();host.invalidate();let ticket=ready_capture(&mut host);
            assert!(host.begin_copy(CAP,&ticket).is_err());ticket};
        drop(read);
        assert!(state.source_patch_capture.lock().unwrap().begin_copy(CAP,&ticket).is_ok());
    }
    #[test] fn delivery_marks_copied_but_stale_delivery_never_becomes_eligible() {
        let (read,ticket)=completed_read();let state=read.state.clone();assert!(read.deliver().is_ok());
        assert_eq!(state.source_patch_capture.lock().unwrap().status_for(CAP,&ticket)["phase"],"copied");
        let (read,ticket)=completed_read();let state=read.state.clone();state.source_patch_capture.lock().unwrap().invalidate();
        assert!(read.deliver().is_err());
        assert!(state.source_patch_capture.lock().unwrap().presented(CAP,&ticket,"123").is_err());
    }
}
