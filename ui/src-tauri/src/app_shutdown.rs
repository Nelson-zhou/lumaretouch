//! Actual shutdown only; idle polling must never terminate optional workers.
use std::sync::Arc;
use tauri::State;
use crate::AppState;
use serde_json::{json, Value};

pub(crate) fn optional_models(state:&AppState) {
    crate::local_workflow_host::shutdown();
    crate::tether_host::shutdown();
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


#[tauri::command]
pub(crate) fn shutdown_engine(state: State<'_, Arc<AppState>>) -> Value {
    crate::local_workflow_host::shutdown();
    crate::tether_host::shutdown();
    state.common_background_preview.lock().unwrap().invalidate();
    state.fringe_repair_preview.lock().unwrap().invalidate();
    state.source_patch_capture.lock().unwrap().invalidate();
    state.recovery_preview.lock().unwrap().invalidate(); state.liquify_preview.lock().unwrap().invalidate(); state.studio_background_preview.lock().unwrap().invalidate(); state.optics_preview.lock().unwrap().invalidate(); state.sky_preview.lock().unwrap().invalidate();
    state.sky_semantic.lock().unwrap().invalidate();
    state.white_balance_capture.lock().unwrap().invalidate();
    state.color_picker_capture.lock().unwrap().invalidate();
    state.color_capture.lock().unwrap().invalidate();
    state.inspection.lock().unwrap().invalidate();
    state.color_scopes.lock().unwrap().invalidate();
    let h = state.engine.lock().unwrap().clone();
    // 引擎停了，它报过的 image_ready / precompute_ready 也随之作废；留着会让下一次
    // 自动流程拿陈尺寸与陈掩膜状态起跑
    *state.image.lock().unwrap() = None;
    *state.precompute.lock().unwrap() = None;
    *state.face.lock().unwrap() = None;
    *state.inpaint.lock().unwrap() = None;
    *state.light.lock().unwrap() = None;
    *state.deform.lock().unwrap() = None;
    *state.lut.lock().unwrap() = None;
    *state.grade.lock().unwrap() = None;
    *state.background.lock().unwrap() = None;   // 换底层也随会话走：进程没了就没有层
    *state.presets.lock().unwrap() = Vec::new();   // 引擎没了，它报过的清单也就没了
    *state.grade_limits.lock().unwrap() = Vec::new();
    *state.export.lock().unwrap() = None;
    *state.export_progress.lock().unwrap() = None;
    *state.export_caps.lock().unwrap() = Value::Null;
    *state.raw_backends.lock().unwrap() = Value::Null;    // 能力是引擎报的，不是永久的
    *state.matting_backends.lock().unwrap() = Value::Null; // 同上（M6）
    *state.image_exts.lock().unwrap() = Value::Null;
    *state.export_bits.lock().unwrap() = Value::Null;  // 同上
    *state.last_error.lock().unwrap() = None;          // 同上
    *state.session.lock().unwrap() = None;
    state.thumbs.lock().unwrap().clear();
    *state.session_rev.lock().unwrap() += 1;
    *state.history.lock().unwrap() = None;
    *state.history_rev.lock().unwrap() += 1;
    {
        let mut report = state.doc_report.lock().unwrap();
        *report = None;
        *state.doc_rev.lock().unwrap() += 1;
    }
    state.history_edit_cmds.lock().unwrap().clear();
    *state.history_dirty.lock().unwrap() = false;
    match h {
        Some(h) => {
            h.shutdown();
            json!({"shutdown": true})
        }
        None => json!({"shutdown": false, "reason": "引擎未启动"}),
    }
}
