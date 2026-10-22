//! Capture and receipt hosts share the same engine epoch, never retained pixels.
use crate::AppState;

impl AppState {
    pub(crate) fn reset_capture_hosts(&self, epoch: [u8; 16]) {
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
        self.manual_liquify.lock().unwrap().reset(epoch);
        self.liquify_preview.lock().unwrap().reset(epoch);
        self.effect_recovery.lock().unwrap().reset(epoch);
        self.recovery_preview.lock().unwrap().reset(epoch);
        self.local_grade_live.lock().unwrap().reset(epoch);
    }
}
