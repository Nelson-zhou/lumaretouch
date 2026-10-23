//! Actual shutdown only; idle polling must never terminate optional workers.
use std::sync::Arc;
use tauri::State;
use crate::AppState;

pub(crate) fn optional_models(state:&AppState) {
    crate::body_pose_model_api::shutdown();
    crate::prompted_model_api::shutdown(state);
    crate::sky_semantic_model_api::shutdown(state);
}

#[tauri::command]
pub(crate) fn quit(state: State<'_, Arc<AppState>>) {
    state.common_background_preview.lock().unwrap().invalidate();
    optional_models(&state);
    state.sky_semantic.lock().unwrap().invalidate();
    state.source_patch_capture.lock().unwrap().invalidate();
    state.recovery_preview.lock().unwrap().invalidate(); state.liquify_preview.lock().unwrap().invalidate(); state.studio_background_preview.lock().unwrap().invalidate(); state.optics_preview.lock().unwrap().invalidate(); state.sky_preview.lock().unwrap().invalidate();
    state.white_balance_capture.lock().unwrap().invalidate();
    state.color_picker_capture.lock().unwrap().invalidate();
    state.inspection.lock().unwrap().invalidate();
    let handle=state.engine.lock().unwrap().clone();
    if let Some(handle)=handle{handle.shutdown();}
    std::process::exit(0);
}

