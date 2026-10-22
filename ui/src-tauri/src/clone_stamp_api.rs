//! Clone brush commits an owned vector gesture, never UI-rendered RGB pixels.
//! Capture lease, epoch fence, queue, and terminal receipts are shared with repair.
use std::sync::Arc;
use serde::Deserialize;
use serde_json::{json, Value};
use tauri::State;
use crate::{AppState, color_capture_host::{id16, token}, frame_identity::hex};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct CloneStroke {
    points: Vec<[f64; 2]>,
    source: [f64; 2],
    size: f64,
    hardness: f64,
    opacity: f64,
}
impl CloneStroke {
    fn validate(&self) -> Result<(), String> {
        let point = |p: &[f64; 2]| p.iter().all(|n| n.is_finite() && (0.0..=1.0).contains(n));
        if self.points.is_empty() || self.points.len() > 1024 || !self.points.iter().all(point) || !point(&self.source) {
            return Err("clone stroke requires 1 to 1024 finite normalized points and a selected source".into());
        }
        if !self.size.is_finite() || !(0.001..=1.0).contains(&self.size)
            || ![self.hardness, self.opacity].iter().all(|n| n.is_finite() && (0.0..=1.0).contains(n)) {
            return Err("invalid clone brush size, hardness or opacity".into());
        }
        Ok(())
    }
}

#[tauri::command]
pub(crate) fn clone_stamp(state: State<'_, Arc<AppState>>, request_id: String,
    capture_id: String, ticket: String, stroke: CloneStroke) -> Result<Value, String> {
    if request_id.is_empty() || request_id.len() > 128 { return Err("invalid clone request ID".into()); }
    id16(&capture_id)?; token(&ticket)?; stroke.validate()?;
    if state.ready_caps.lock().map_err(|_| "capability lock poisoned")?["clone_stamp_protocol"] != 1 {
        return Err("current engine does not support clone-stamp strokes".into());
    }
    let handle = state.engine.lock().map_err(|_| "engine lock poisoned")?.clone().ok_or("engine is not running")?;
    let proof = state.source_patch_capture.lock().map_err(|_| "repair capture lock poisoned")?
        .redeem(handle.epoch(), &capture_id, &ticket)?;
    let command = json!({"cmd":"clone_stamp","kind":"clone_stamp","action":"apply","request_id":request_id,
        "host_epoch":hex(proof.identity.epoch),"document_id":proof.identity.document.to_string(),
        "capture_id":capture_id,"ticket":ticket,"generation":proof.identity.generation.to_string(),
        "recipe_document_id":proof.recipe_document_id,"recipe_revision":proof.recipe_revision,
        "stroke":{"points":stroke.points,"source":stroke.source,"size":stroke.size,"hardness":stroke.hardness,"opacity":stroke.opacity}});
    // Redeemed native identity is removed before the normal mutation fence.
    // Distinct request IDs, no coalescing, and no retry on uncertain delivery.
    state.send_to_engine(command)?;
    Ok(json!({"requested":true}))
}
