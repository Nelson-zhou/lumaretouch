//! Mutation fences and command-specific receipt admission share one dispatch path.
use serde_json::Value;
use crate::AppState;

impl AppState {
    pub(crate) fn send_interactive(&self, key: String, cmd: Value) -> Result<(), String> {
        self.source_patch_capture.lock().map_err(|_|"source patch capture lock poisoned")?.invalidate();
        self.recovery_preview.lock().map_err(|_|"recovery preview lock poisoned")?.invalidate();
        self.optics_preview.lock().map_err(|_|"optics preview lock poisoned")?.invalidate();
        self.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?.invalidate();
        self.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?.invalidate();
        self.studio_background_preview.lock().map_err(|_|"studio preview lock poisoned")?.invalidate();
        self.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?.invalidate();
        self.white_balance_capture.lock().map_err(|_|"WB capture lock poisoned")?.invalidate();
        self.color_picker_capture.lock().map_err(|_|"color picker capture lock poisoned")?.invalidate();
        self.color_capture.lock().map_err(|_|"capture lock poisoned")?.invalidate();
        self.color_scopes.lock().map_err(|_|"scope lock poisoned")?.invalidate();
        let mut inspection=self.inspection.lock().map_err(|_| "inspection lock poisoned".to_string())?;
        inspection.invalidate();
        let guard=self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        guard.as_ref().ok_or("引擎未启动")?.send_interactive(key,cmd)?;
        *self.history_dirty.lock().unwrap()=true;
        Ok(())
    }

    pub(crate) fn send_to_engine(&self, cmd: Value) -> Result<(), String> {
        // M5-b：命令名先取出来（cmd 下面会被 send 吃掉）。它只用来标"可能有新的一步"，
        // 宿主不数步数、不自己判哪条命令算编辑——名单由引擎的 ready 报
        let name = cmd.get("cmd").and_then(|c| c.as_str()).unwrap_or("").to_string();
        if name!="hello" && name!="inspection_snapshot" {self.source_patch_capture.lock().map_err(|_|"source patch capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.recovery_preview.lock().map_err(|_|"recovery preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.white_balance_capture.lock().map_err(|_|"WB capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.color_picker_capture.lock().map_err(|_|"color picker capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.color_scopes.lock().map_err(|_|"scope lock poisoned")?.invalidate();}
        if name!="hello" {self.color_capture.lock().map_err(|_|"capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.studio_background_preview.lock().map_err(|_|"studio preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.optics_preview.lock().map_err(|_|"optics preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {
            self.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?.invalidate();
            self.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?.invalidate();
        }
        let edited = self.history_edit_cmds.lock().unwrap().iter().any(|c| c == &name);
        let mut inspection=self.inspection.lock().map_err(|_| "inspection lock poisoned".to_string())?;
        if name!="hello" && name!="inspection_snapshot"{inspection.invalidate();}
        let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        let handle=guard.as_ref().ok_or_else(|| "引擎未启动".to_string())?;
        match name.as_str() {
            "brow_shape" => crate::brow_shape_api::enqueue(handle, cmd)?,
            "nose_shape" => crate::nose_shape_api::enqueue(handle, cmd)?,
            "batch" => crate::batch_api::enqueue(self, handle, cmd)?,
            "preset" => crate::preset_api::enqueue(self, handle, cmd)?,
            "white_balance" => crate::white_balance_api::enqueue(self, handle, cmd)?,
            "color_picker" => crate::color_picker_api::enqueue(self, handle, cmd)?,
            "local_masks" => crate::local_mask_api::enqueue(self, handle, cmd)?,
            "sky_replacement" => crate::sky_replacement_api::enqueue(self, handle, cmd)?,
            "optics" => crate::optics_api::enqueue(self, handle, cmd)?,
            "studio_background" => crate::studio_background_api::enqueue(self, handle, cmd)?,
            "manual_liquify" => crate::manual_liquify_api::enqueue(self, handle, cmd)?,
            "effect_recovery" => crate::effect_recovery_api::enqueue(self, handle, cmd)?,
            "local_grade_live" => crate::local_grade_live_api::enqueue(self, handle, cmd)?,
            "source_patch" | "clone_stamp" => crate::source_patch_api::enqueue(self, handle, cmd)?,
            _ => handle.send(cmd)?,
        }
        if edited {
            *self.history_dirty.lock().unwrap() = true;
        }
        Ok(())
    }
}
