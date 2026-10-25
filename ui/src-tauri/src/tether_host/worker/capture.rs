//! Explicit camera operations and bounded occurrence/preview handling.
use super::*;

impl Owner {
    pub(super) fn open_session(&mut self, request: &Request) -> Result<(), String> {
        let session = self.session.as_ref().ok_or("会话不存在")?;
        let token = session.token.clone(); let key = session.device_id.clone();
        let device = self.devices.get(&key).ok_or("原设备检测身份丢失")?.clone();
        let result: Result<DeviceEvent, String> = (|| {
            self.device.open_selected(&device, &token).map_err(|e| e.to_string())?;
            self.driver_open = true;
            let settings = self.settings();
            let first = self.device.wait_event(POLL, &token).map_err(|e| e.to_string())?;
            let caps = self.device.capabilities().map_err(|e| e.to_string())?;
            if caps.events != Support::Verified || caps.original_download == Support::Unsupported {
                return Err("本次连接没有已验证事件，或驱动明确不支持原片下载".into());
            }
            self.update_device(&key, Some(caps), settings)?;
            Ok(first)
        })();
        match result {
            Ok(first) if !token.is_cancelled() && self.host.snapshot()?["session"]["phase"] != "stopping" => {
                self.host.edit(true, |shared| { shared.snapshot["session"]["phase"] = json!("active"); Ok(()) })?;
                self.host.settle(request, true, false, None)?;
                // Engine arm established the exact lease; no engine mutation has
                // run since it, and imports independently recheck at precommit.
                self.lease_checked = Some(Instant::now()); self.lease_ok = true;
                self.next_read = true;
                if let DeviceEvent::FileAdded(object) = first { self.file_added(object)?; }
            }
            Ok(_) => {
                self.close_driver()?;
                self.host.settle(request, false, false, Some("停止请求已到达；相机没有进入接收状态"))?;
            }
            Err(error) => {
                self.close_driver()?;
                self.pause(&format!("相机连接未完成：{error}"), false)?;
                self.host.settle(request, false, false, Some(&error))?;
            }
        }
        Ok(())
    }
    pub(super) fn close_driver(&mut self) -> Result<(), String> {
        self.lease_ok = false;
        if let Some(session) = self.session.as_mut() { session.live = false; session.token.cancel(); }
        if let Some(optional) = self.optional.take() {
            self.host.settle(&optional, false, false, Some("停止前未调用相机"))?;
        }
        if self.driver_open {
            // Native close unrefs even if exit reports an error. Its return is
            // not a promise that the physical device has no firmware work left.
            let result = self.device.close();
            self.driver_open = false;
            if let Err(error) = result {
                self.host.edit(true, |shared| {
                    shared.snapshot["session"]["error"] = json!(format!("驱动已释放本地句柄，但退出报告错误：{error}"));
                    Ok(())
                })?;
            }
        }
        self.host.edit(true, |shared| {
            if shared.snapshot["session"].is_object() { shared.snapshot["session"]["live_view"] = json!("off"); }
            Ok(())
        })?;
        Ok(())
    }
    pub(super) fn maybe_release(&mut self) -> Result<(), String> {
        if self.stop.is_none() || self.flight.is_some() || self.driver_open { return Ok(()); }
        let request = self.stop.as_ref().ok_or("停止请求丢失")?.clone();
        let engine_id = self.session.as_ref().and_then(|session| session.engine_id.clone());
        let Some(engine_id) = engine_id else {
            self.host.edit(true, |shared| {
                shared.snapshot["session"]["phase"] = json!("stopped"); shared.snapshot["session"]["live_view"] = json!("off"); Ok(())
            })?;
            self.session = None; self.stop = None;
            self.host.settle(&request, true, false, None)?; self.next_read = true;
            return Ok(());
        };
        let id = storage::uuid()?;
        self.submit(Flight { id:id.clone(),operation:None,kind:FlightKind::Release(request),
            payload:json!({"cmd":"ingest_session","action":"release","request_id":id,"session_id":engine_id}) })
    }
    pub(super) fn execute_optional(&mut self, request: Request) -> Result<(), String> {
        if let Err(error) = self.require_active() { return self.host.settle(&request, false, false, Some(&error)); }
        let session = self.session.as_ref().ok_or("会话不存在")?;
        let token = session.token.clone(); let key = session.device_id.clone();
        if matches!(request.action, Action::Capture) {
            if !self.device.capabilities().map_err(|e| e.to_string())?.remote_trigger.can_request() {
                return self.host.settle(&request, false, false, Some("本次驱动没有声明事件式远程快门；同步拍摄接口不能替代事件接收"));
            }
            // Only this exact explicit request enters gp_camera_trigger_capture.
            // Its API is event-driven; no synchronous returned object is dropped
            // or deduplicated against an independent FileAdded occurrence.
            let result = self.device.trigger_capture(&token);
            self.update_device(&key, self.device.capabilities().ok(), None)?;
            match result {
                Ok(_) => self.host.settle(&request, true, false, None)?,
                Err(error) => {
                    self.host.settle(&request, false, error.outcome_unknown, Some(&error.to_string()))?;
                    self.pause(if error.outcome_unknown { "快门可能已经触发；原请求结果未知，只能查询，绝不自动补拍" }
                        else { "远程快门未完成；请核对相机与原请求" }, error.outcome_unknown)?;
                }
            }
        } else {
            if !self.device.capabilities().map_err(|e| e.to_string())?.preview.can_request() {
                return self.host.settle(&request, false, false, Some("本次驱动没有声明实时取景能力"));
            }
            self.host.edit(true, |shared| { shared.snapshot["session"]["live_view"] = json!("starting"); Ok(()) })?;
            if let Some(session) = self.session.as_mut() { session.live = true; }
            match self.capture_frame() {
                Ok(()) => self.host.settle(&request, true, false, None)?,
                Err(error) => {
                    if let Some(session) = self.session.as_mut() { session.live = false; }
                    self.host.edit(true, |shared| { shared.snapshot["session"]["live_view"] = json!("error"); Ok(()) })?;
                    self.host.settle(&request, false, false, Some(&error))?;
                }
            }
        }
        Ok(())
    }
    pub(super) fn poll_camera(&mut self) -> Result<(), String> {
        let session = self.session.as_ref().ok_or("会话不存在")?;
        if session.remaining == 0 || self.bytes >= wire::MAX_BYTES {
            return self.pause("本次会话已到真实接入额度或 4 GiB 暂存上限，请明确停止；不自动换工程", false);
        }
        let token = session.token.clone();
        if token.is_cancelled() { return Ok(()); }
        let event = self.device.wait_event(POLL, &token);
        match event {
            Ok(DeviceEvent::FileAdded(object)) => {
                if !token.is_cancelled() && self.host.snapshot()?["session"]["phase"] == "active" { self.file_added(object)?; }
            }
            // FileChanged, CaptureComplete and matching paths/hashes are NEVER
            // synthetic captures, dedup identities or permission to download.
            Ok(_) => (),
            Err(error) if token.is_cancelled() => { let _ = error; },
            Err(error) => self.pause(&format!("设备事件读取失败：{error}"), false)?,
        }
        Ok(())
    }
    pub(super) fn file_added(&mut self, object: lrt_tether_capture::CameraObject) -> Result<(), String> {
        let transfer = storage::uuid()?;
        let (session_id, generation, ordinal, kind) = {
            let session = self.session.as_mut().ok_or("会话不存在")?;
            let ordinal = session.ordinal;
            session.ordinal = session.ordinal.checked_add(1).ok_or("事件计数已耗尽")?;
            (session.id.clone(),session.generation,ordinal,wire::format(&object.name))
        };
        self.host.edit(true, |shared| {
            let rows = shared.snapshot["transfers"].as_array_mut().ok_or("传输列表无效")?;
            if rows.len() >= wire::MAX_TRANSFERS { return Err("事件回执已满；不会静默丢弃旧事件").map_err(str::to_owned); }
            rows.push(json!({"transfer_id":transfer,"session_id":session_id,"session_generation":generation,
                "camera_filename":object.name,"format":kind,"phase":"queued","retryable":false}));
            Ok(())
        })?;
        if kind == "other" {
            return self.transfer_error(&transfer,"skipped","该相机对象不是当前支持的 RAW/JPEG；未下载，未伪造伴随文件");
        }
        let (stage, local_name, token) = {
            let session = self.session.as_ref().ok_or("会话不存在")?;
            let name = match wire::local_name(&session.naming, &object.name, &session.date, ordinal) {
                Ok(name) => name, Err(error) => return self.transfer_error(&transfer,"failed",&error),
            };
            // Unique occurrence directory makes repeated identical camera names
            // collision-safe without changing the selected naming pattern.
            (session.stage.child(&format!("occurrence-{transfer}"))?,name,session.token.clone())
        };
        self.host.edit(true, |shared| {
            if let Some(row) = transfer_mut(&mut shared.snapshot, &transfer) {
                row["local_filename"] = json!(local_name); row["phase"] = json!("downloading");
            }
            Ok(())
        })?;
        let request = StagingRequest { directory:stage.path.clone(),local_name,
            max_bytes:lrt_tether_capture::MAX_ORIGINAL_BYTES.min(wire::MAX_BYTES.saturating_sub(self.bytes)),timeout:Duration::from_secs(600) };
        let receipt = match self.device.download_to_staging(&object, &request, &token) {
            Ok(receipt) => receipt,
            Err(error) => {
                self.transfer_error(&transfer, if token.is_cancelled() { "cancelled" } else { "failed" }, &error.to_string())?;
                if !token.is_cancelled() { self.pause("原片下载未完成；保留相机原片，不自动重试", false)?; }
                return Ok(());
            }
        };
        self.bytes = self.bytes.checked_add(receipt.bytes).ok_or("暂存字节计数溢出")?;
        if let Some(session) = self.session.as_ref() {
            self.update_device(&session.device_id, self.device.capabilities().ok(), None)?;
        }
        self.host.edit(false, |shared| {
            if let Some(row) = transfer_mut(&mut shared.snapshot, &transfer) {
                row["phase"] = json!("validating"); row["bytes_received"] = json!(receipt.bytes); row["bytes_total"] = json!(receipt.bytes);
            }
            Ok(())
        })?;
        let proof = match storage::completed_source(&stage, &receipt, &transfer) {
            Ok(proof) => proof,
            Err(error) => { self.transfer_error(&transfer,"failed",&error)?; return self.pause("原片完整性校验失败；没有提交导入", false); }
        };
        if token.is_cancelled() || self.host.closing.load(Ordering::Acquire) || self.host.snapshot()?["session"]["phase"] != "active" {
            return self.transfer_error(&transfer,"cancelled","停止请求已到达；完整暂存保留，但没有开始新导入");
        }
        let session = self.session.as_ref().ok_or("会话不存在")?;
        session.destination.writable()?;
        let engine_id = session.engine_id.as_ref().ok_or("工程租约未建立")?.clone();
        let id = storage::uuid()?;
        let operation = crate::ingest_receipt_validation::operation_id(&engine_id, &id)?;
        let root = session.destination.path.to_str().ok_or("目标路径不是 UTF-8")?.to_owned();
        let root_identity = session.destination.identity();
        self.host.edit(true, |shared| {
            if let Some(row) = transfer_mut(&mut shared.snapshot, &transfer) { row["phase"] = json!("importing"); }
            Ok(())
        })?;
        self.submit(Flight { id:id.clone(),operation:Some(operation),kind:FlightKind::Import { transfer,proof:proof.clone() },
            payload:json!({"cmd":"ingest_session","action":"import","request_id":id,"session_id":engine_id,
                "root":root,"root_identity":root_identity,"paths":[proof["path"]],"completed_sources":[proof]}) })
    }
    pub(super) fn transfer_error(&self, transfer: &str, phase: &str, error: &str) -> Result<(), String> {
        self.host.edit(true, |shared| {
            if let Some(row) = transfer_mut(&mut shared.snapshot, transfer) {
                row["phase"] = json!(phase); row["error"] = json!(error); row["retryable"] = json!(false);
            }
            Ok(())
        })?; Ok(())
    }
    pub(super) fn live_frame(&mut self) -> Result<(), String> {
        let due = self.session.as_ref().map_or(false, |s| s.live && s.last_frame.elapsed() >= Duration::from_millis(500));
        if due && self.host.snapshot()?["session"]["live_view"] == "on" {
            if let Err(error) = self.capture_frame() {
                if let Some(session) = self.session.as_mut() { session.live = false; }
                self.host.edit(true, |shared| {
                    if shared.snapshot["session"]["phase"] == "active" && shared.snapshot["session"]["live_view"] != "stopping" {
                        shared.snapshot["session"]["live_view"] = json!("error");
                    }
                    shared.snapshot["session"]["error"] = json!(format!("实时取景已暂停：{error}")); Ok(())
                })?;
            }
        }
        Ok(())
    }
    pub(super) fn capture_frame(&mut self) -> Result<(), String> {
        let session = self.session.as_ref().ok_or("会话不存在")?;
        let token = session.token.clone(); let key = session.device_id.clone();
        let frame = self.device.capture_preview(lrt_tether_capture::MAX_PREVIEW_BYTES, &token).map_err(|e| e.to_string())?;
        let dimensions = if frame.mime_type == "image/jpeg" { wire::jpeg_dimensions(&frame.bytes) }
            else if frame.mime_type == "image/png" && frame.bytes.len() >= 24 && frame.bytes.starts_with(b"\x89PNG\r\n\x1a\n") && &frame.bytes[12..16] == b"IHDR" {
                let w = u32::from_be_bytes(frame.bytes[16..20].try_into().map_err(|_| "PNG 宽度无效")?);
                let h = u32::from_be_bytes(frame.bytes[20..24].try_into().map_err(|_| "PNG 高度无效")?);
                (w > 0 && h > 0 && w <= 16384 && h <= 16384
                    && u64::from(w) * u64::from(h) <= 16 * 1024 * 1024).then_some((w,h))
            } else { None };
        let (width, height) = dimensions.ok_or("实际预览缺少支持且有界的 JPEG/PNG 尺寸；未显示")?;
        self.update_device(&key, self.device.capabilities().ok(), None)?;
        let session = self.session.as_mut().ok_or("会话不存在")?;
        session.last_frame = Instant::now();
        if token.is_cancelled() || self.host.closing.load(Ordering::Acquire) { return Err("停止后丢弃晚到预览".into()); }
        session.frame = session.frame.checked_add(1).filter(|v| *v <= wire::MAX_SAFE).ok_or("预览帧序号已耗尽")?;
        let id = session.id.clone(); let generation = session.generation; let sequence = session.frame;
        let snapshot = self.host.edit(false, |shared| {
            if shared.snapshot["session"]["phase"] != "active" || shared.snapshot["session"]["session_id"] != id
                || shared.snapshot["session"]["generation"].as_u64() != Some(generation)
                || shared.snapshot["session"]["live_view"] == "stopping" { return Err("旧会话或已停止取景的预览不再发布".into()); }
            shared.snapshot["session"]["live_view"] = json!("on"); Ok(())
        })?;
        let image_url = format!("data:{};base64,{}",frame.mime_type,base64::engine::general_purpose::STANDARD.encode(frame.bytes));
        // Last gate serialized with stop acceptance; no new frame event after a
        // stop receipt has acquired this same native admission lock.
        let shared = self.host.shared.lock().map_err(|_| "联机状态锁不可用")?;
        if shared.snapshot["session"]["phase"] == "active" && shared.snapshot["session"]["session_id"] == id
            && shared.snapshot["session"]["live_view"] == "on"
            && !shared.cancel.is_cancelled() && !self.host.closing.load(Ordering::Acquire) {
            let _ = self.host.app.emit(crate::tether_host::EVENT, json!({"type":"live_frame","frame":{
                "host_id":snapshot["host_id"],"session_id":id,"session_generation":generation,"sequence":sequence,
                "image_url":image_url,"width":width,"height":height}}));
        }
        Ok(())
    }
}
