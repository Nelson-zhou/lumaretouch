//! Mutation fences and command-specific receipt admission share one dispatch path.
use serde_json::Value;
use crate::AppState;

impl AppState {
    pub(crate) fn send_interactive(&self, key: String, cmd: Value) -> Result<(), String> {
        self.common_background_preview.lock().map_err(|_|"common background preview lock poisoned")?.invalidate();
        self.fringe_repair_preview.lock().map_err(|_|"fringe repair preview lock poisoned")?.invalidate();
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
        let handle = guard.as_ref().ok_or("引擎未启动")?;
        crate::sample_library_api::invalidate_captures(handle)?;
        handle.send_interactive(key,cmd)?;
        *self.history_dirty.lock().unwrap()=true;
        Ok(())
    }

    pub(crate) fn send_to_engine(&self, cmd: Value) -> Result<(), String> {
        // M5-b：命令名先取出来（cmd 下面会被 send 吃掉）。它只用来标"可能有新的一步"，
        // 宿主不数步数、不自己判哪条命令算编辑——名单由引擎的 ready 报
        let name = cmd.get("cmd").and_then(|c| c.as_str()).unwrap_or("").to_string();
        if name == "common_background" { crate::common_background_readback::precheck_client(&cmd)?; }
        if name == "fringe_repair" { crate::fringe_repair_audit::precheck_client(&cmd)?; }
        // Arm selection and owned proposal queries/cancellation do not alter
        // image pixels or revoke unrelated capture lifetimes.
        // A library view changes neither image history nor any capture lease.
        if name == "canvas_guides" || name == "project_recovery" || crate::managed_import_api::read_only(&cmd) || (name == "session" && cmd.get("action").and_then(Value::as_str) == Some("query"))
            || (name == "virtual_copy" && matches!(cmd.get("action").and_then(Value::as_str), Some("state") | Some("query"))) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return guard.as_ref().ok_or("引擎未启动")?.send(cmd);
        }
        if crate::people_api::face_style::read_only(&cmd) || crate::people_api::eye_bag::read_only(&cmd) || crate::people_api::face_decoration::read_only(&cmd) || crate::people_api::facial_sculpt::read_only(&cmd) || crate::people_api::eye_makeup_enhance::read_only(&cmd) || crate::people_api::decoration_alias::read_only(&cmd) || crate::people_api::decoration_support_alias::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::people_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if crate::preset_api::read_only(&cmd) {
            let guard=self.engine.lock().map_err(|_|"引擎锁中毒".to_string())?;
            return crate::preset_api::enqueue(self,guard.as_ref().ok_or("引擎未启动")?,cmd);
        }
        if crate::batch_api::read_only(&cmd) {
            let guard=self.engine.lock().map_err(|_|"引擎锁中毒".to_string())?;
            return crate::batch_api::enqueue(self,guard.as_ref().ok_or("引擎未启动")?,cmd);
        }
        if crate::arm_shape_api::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::arm_shape_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if crate::torso_length_api::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::torso_length_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if crate::waist_length_api::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::waist_length_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if crate::head_size_api::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::head_size_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if crate::body_slim_api::read_only(&cmd) {
            let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
            return crate::body_slim_api::enqueue(guard.as_ref().ok_or("引擎未启动")?, cmd);
        }
        if name!="hello" && name!="inspection_snapshot" {self.source_patch_capture.lock().map_err(|_|"source patch capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.recovery_preview.lock().map_err(|_|"recovery preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.white_balance_capture.lock().map_err(|_|"WB capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.color_picker_capture.lock().map_err(|_|"color picker capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.color_scopes.lock().map_err(|_|"scope lock poisoned")?.invalidate();}
        if name!="hello" {self.color_capture.lock().map_err(|_|"capture lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.liquify_preview.lock().map_err(|_|"liquify preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {self.studio_background_preview.lock().map_err(|_|"studio preview lock poisoned")?.invalidate();}
        // Common apply redeems its own exact proof while admitting the command.
        // Every other mutation still invalidates it before entering the queue.
        if name!="hello" && name!="inspection_snapshot" && name!="common_background" {
            self.common_background_preview.lock().map_err(|_|"common background preview lock poisoned")?.invalidate();
        }
        if name!="hello" && name!="inspection_snapshot" && name!="fringe_repair" {
            self.fringe_repair_preview.lock().map_err(|_|"fringe repair preview lock poisoned")?.invalidate();
        }
        if name!="hello" && name!="inspection_snapshot" {self.optics_preview.lock().map_err(|_|"optics preview lock poisoned")?.invalidate();}
        if name!="hello" && name!="inspection_snapshot" {
            self.sky_preview.lock().map_err(|_|"sky preview lock poisoned")?.invalidate();
            self.sky_semantic.lock().map_err(|_|"semantic lock poisoned")?.invalidate();
        }
        let edited = self.history_edit_cmds.lock().unwrap().iter().any(|c| c == &name)
            && (name != "torso_length" || cmd["action"] == "edit")
            && (name != "waist_length" || cmd["action"] == "edit")
            && (name != "head_size" || cmd["action"] == "edit")
            && (name != "body_slim" || cmd["action"] == "edit")
            && (name != "arm_shape" || cmd["action"] == "execute")
            && (name != "hair_colour" || matches!(cmd["action"].as_str(), Some("commit_support" | "commit_recovery" | "clear_recovery" | "clear_support")));
        let mut inspection=self.inspection.lock().map_err(|_| "inspection lock poisoned".to_string())?;
        if name!="hello" && name!="inspection_snapshot"{inspection.invalidate();}
        let guard = self.engine.lock().map_err(|_| "引擎锁中毒".to_string())?;
        let handle=guard.as_ref().ok_or_else(|| "引擎未启动".to_string())?;
        if crate::sample_library_api::invalidates_capture(&cmd) {
            crate::sample_library_api::invalidate_captures(handle)?;
        }
        match name.as_str() {
            "shoulder_shape" => crate::shoulder_shape_api::enqueue(handle, cmd)?,
            "leg_shape" => crate::leg_shape_api::enqueue(handle, cmd)?,
            "waist_shape" => crate::waist_shape_api::enqueue(handle, cmd)?,
            "leg_length" => crate::leg_length_api::enqueue(handle, cmd)?,
            "torso_length" => crate::torso_length_api::enqueue(handle, cmd)?,
            "waist_length" => crate::waist_length_api::enqueue(handle, cmd)?,
            "head_size" => crate::head_size_api::enqueue(handle, cmd)?,
            "lens_blur" => crate::lens_blur_api::enqueue(handle, cmd)?,
            "expression_replacement" => crate::expression_replacement_api::enqueue(handle, cmd)?,
            "body_slim" => crate::body_slim_api::enqueue(handle, cmd)?,
            "neck_shape" => crate::neck_shape_api::enqueue(handle, cmd)?,
            "arm_shape" => crate::arm_shape_api::enqueue(handle, cmd)?,
            "people" => crate::people_api::enqueue(handle, cmd)?,
            "hair_colour" => crate::hair_colour_api::enqueue(handle, cmd)?,
            "brow_shape" => crate::brow_shape_api::enqueue(handle, cmd)?,
            "nose_shape" => crate::nose_shape_api::enqueue(handle, cmd)?,
            "eye_shape" => crate::eye_shape_api::enqueue(handle, cmd)?,
            "mouth_shape" => crate::mouth_shape_api::enqueue(handle, cmd)?,
            "batch" => crate::batch_api::enqueue(self, handle, cmd)?,
            "preset" => crate::preset_api::enqueue(self, handle, cmd)?,
            "white_balance" => crate::white_balance_api::enqueue(self, handle, cmd)?,
            "color_picker" => crate::color_picker_api::enqueue(self, handle, cmd)?,
            "local_masks" => crate::local_mask_api::enqueue(self, handle, cmd)?,
            "sky_replacement" => crate::sky_replacement_api::enqueue(self, handle, cmd)?,
            "optics" => crate::optics_api::enqueue(self, handle, cmd)?,
            "studio_background" => crate::studio_background_api::enqueue(self, handle, cmd)?,
            "common_background" => crate::common_background_api::enqueue(self, handle, cmd)?,
            "fringe_repair" => crate::fringe_repair_api::enqueue(self, handle, cmd)?,
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

/// 把结果回显到 `tauri dev` 的标准输出，便于跑靶脚本直接采集。
#[tauri::command]
pub(crate) fn report(line: String) {
    println!("{line}");
}
