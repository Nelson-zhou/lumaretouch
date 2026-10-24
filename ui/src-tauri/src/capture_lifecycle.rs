//! Capture and receipt hosts share the same engine epoch, never retained pixels.
use crate::AppState;
use serde_json::{Value,json};

impl AppState {
    /// 三条带 doc_state 的事件都进这里落一份"引擎最新说的文档状态 + 它是谁说的"。
    pub(crate) fn note_doc(&self, v: &Value, src: &str) {
        self.common_background_preview.lock().unwrap().invalidate();
        self.fringe_repair_preview.lock().unwrap().invalidate();
        self.source_patch_capture.lock().unwrap().invalidate();
        self.recovery_preview.lock().unwrap().invalidate(); self.liquify_preview.lock().unwrap().invalidate(); self.studio_background_preview.lock().unwrap().invalidate(); self.optics_preview.lock().unwrap().invalidate(); self.sky_preview.lock().unwrap().invalidate();
        self.sky_semantic.lock().unwrap().invalidate();
        self.white_balance_capture.lock().unwrap().invalidate();
        self.color_picker_capture.lock().unwrap().invalidate();
        self.note_face(v, src);
        {
            let mut report = self.doc_report.lock().unwrap();
            *report = v.get("doc_state").filter(|ds| !ds.is_null())
                .map(|ds| json!({"source": src, "doc_state": ds}));
            *self.doc_rev.lock().unwrap() += 1;
        }
        *self.history_dirty.lock().unwrap() = false;
    }


    pub(crate) fn reset_capture_hosts(&self, epoch: [u8; 16]) {
        crate::shoulder_shape_api::reset(epoch);
        crate::leg_shape_api::reset(epoch);
        crate::waist_shape_api::reset(epoch);
        crate::leg_length_api::reset(epoch);
        crate::torso_length_api::reset(epoch);
        crate::waist_length_api::reset(epoch);
        crate::head_size_api::reset(epoch);
        crate::neck_shape_api::reset(epoch);
        crate::arm_shape_api::reset(epoch);
        crate::sample_library_api::reset(epoch);
        crate::preset_organisation_api::reset(epoch);
        crate::semantic_colour_api::reset(epoch);
        self.color_capture.lock().unwrap().reset(epoch);
        self.source_patch.lock().unwrap().reset(epoch);
        self.local_masks.lock().unwrap().reset(epoch);
        self.prompted_masks.lock().unwrap().reset(epoch);
        self.source_patch_capture.lock().unwrap().reset(epoch);
        self.white_balance_capture.lock().unwrap().reset(epoch);
        self.color_picker_capture.lock().unwrap().reset(epoch);
        self.color_picker_results.lock().unwrap().reset(epoch);
        self.color_picker_probes.lock().unwrap().reset(epoch);
        self.batch_results.lock().unwrap().reset(epoch);
        self.preset_results.lock().unwrap().reset(epoch);
        self.white_balance_results.lock().unwrap().reset(epoch);
        self.sky_replacement.lock().unwrap().reset(epoch);
        self.sky_preview.lock().unwrap().reset(epoch);
        self.sky_semantic.lock().unwrap().reset(epoch);
        self.optics.lock().unwrap().reset(epoch);
        self.optics_preview.lock().unwrap().reset(epoch);
        self.studio_background.lock().unwrap().reset(epoch);
        self.studio_background_preview.lock().unwrap().reset(epoch);
        self.common_background.lock().unwrap().reset(epoch);
        self.common_background_preview.lock().unwrap().reset(epoch);
        self.fringe_repair.lock().unwrap().reset(epoch);
        self.fringe_repair_preview.lock().unwrap().reset(epoch);
        self.manual_liquify.lock().unwrap().reset(epoch);
        self.liquify_preview.lock().unwrap().reset(epoch);
        self.effect_recovery.lock().unwrap().reset(epoch);
        self.recovery_preview.lock().unwrap().reset(epoch);
        self.local_grade_live.lock().unwrap().reset(epoch);
    }
}
