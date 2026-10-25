//! Epoch-bound ingestion lease, read-only reconciliation and exact document proof.
use super::*;

impl Owner {
    pub(super) fn begin_read(&mut self) -> Result<(), String> {
        self.next_read = false;
        self.last_read = Instant::now();
        let id = storage::uuid()?;
        let (query, payload) = if let Some(Flight { operation:Some(operation), kind:FlightKind::Import { .. }, .. }) = self.flight.as_ref() {
            let session = self.session.as_ref().and_then(|s| s.engine_id.as_ref()).ok_or("缺少原导入租约身份")?;
            (true, json!({"cmd":"ingest_session","action":"query","request_id":id,"session_id":session,"operation_id":operation}))
        } else {
            // State is not used across the managed-import write fence.
            (false, json!({"cmd":"ingest_session","action":"state","request_id":id}))
        };
        self.read = Some(Read { id:id.clone(),query,issued:Instant::now(),serial:self.lease_serial });
        if let Err(error) = crate::ingest_session_api::submit(&self.state, payload) {
            self.lease_ok = false;
            self.host.edit(false, |shared| {
                if shared.snapshot["ingestion_target"].is_object() {
                    shared.snapshot["ingestion_target"]["available"] = json!(false);
                    shared.snapshot["ingestion_target"]["reason"] = json!(format!("引擎读取待核对：{error}"));
                }
                Ok(())
            })?;
            // Keep this read identity until its outcome is known. Never create
            // unbounded unanswered read requests on a stalled transport.
        }
        Ok(())
    }
    pub(super) fn observe_read(&mut self) -> Result<(), String> {
        let Some(read) = self.read.as_ref() else { return Ok(()) };
        let envelope = crate::ingest_session_api::read_receipt(&self.state, &read.id)?;
        if envelope["phase"] == "unknown" {
            if envelope["reason"].is_string() {
                self.epoch_lost = true;
                self.pause("引擎代次已变化；原租约不能通过新会话恢复，原操作只保留待核对，未重发", true)?;
            } else if read.issued.elapsed() >= READ_INTERVAL {
                self.lease_ok = false;
                // Native transport may prune a completed, unobserved READ.
                // A fresh state/query is safe: it cannot replay arm/import/
                // release/shutter. Pending retained reads are never replaced.
                self.read = None;
                self.next_read = true;
            }
            return Ok(());
        }
        if envelope["phase"] != "done" {
            if read.issued.elapsed() > LEASE_FRESH { self.lease_ok = false; }
            return Ok(());
        }
        let read = self.read.take().ok_or("引擎读取身份丢失")?;
        let result = envelope["result"].clone();
        if read.serial != self.lease_serial { self.next_read = true; return Ok(()); }
        if result["request_id"] != read.id || result["protocol"] != 1
            || result["action"] != if read.query { "query" } else { "state" } {
            self.pause("引擎回读身份或协议不匹配；未采用", true)?; return Ok(());
        }
        if read.query {
            // Query advances engine reconciliation, but publication only uses
            // the original epoch-bound import receipt below, never this query.
            if let Some(flight) = self.flight.as_ref() {
                if result["operation"].is_object() && (result["operation"]["request_id"] != flight.id
                    || result["operation"]["operation_id"].as_str() != flight.operation.as_deref()) {
                    self.pause("原操作查询关联不匹配；停止接收", true)?;
                }
            }
            self.observe_flight()?;
            return Ok(());
        }
        if result["status"] != "readback" || !result["state"].is_object() {
            self.lease_ok = false;
            if self.session.is_some() {
                self.pause(result["error"].as_str().unwrap_or("工程租约读取失败；停止接收"), false)?;
            } else {
                self.host.edit(false, |shared| { shared.binding = None; shared.snapshot["ingestion_target"] = Value::Null; Ok(()) })?;
            }
            return Ok(());
        }
        self.adopt_state(&result)?;
        if let Some(request) = self.optional.take() {
            if self.lease_ok && self.flight.is_none() && self.stop.is_none() {
                self.execute_optional(request)?;
            } else {
                self.host.settle(&request, false, false, Some("原工程租约未重新核验通过，未调用相机"))?;
            }
        }
        Ok(())
    }
    pub(super) fn adopt_state(&mut self, result: &Value) -> Result<(), String> {
        let binding = &result["state"]["current_binding"];
        let capacity = result["state"]["receipt_capacity"].as_u64().unwrap_or(0).min(64);
        let mut available = result["state"]["available"] == true;
        let mut remaining = capacity;
        let mut reason = result["state"]["reason"].as_str().unwrap_or("").to_owned();
        if let Some(session) = self.session.as_ref() {
            let lease = &result["session"];
            let same = session.engine_id.as_deref() == lease["session_id"].as_str()
                && lease["owner"] == "tether" && lease["binding"] == session.binding
                && binding == &session.binding;
            available = same && lease["phase"] == "armed" && lease["requires_readback"] == false
                && result["state"]["reason"].is_null() && self.host.snapshot()?["session"]["phase"] == "active";
            remaining = if same { lease["remaining_operations"].as_u64().unwrap_or(0) } else { 0 };
            if !available && reason.is_empty() { reason = "原工程租约不再允许接收；不会切换工程或自动保存".into(); }
            self.lease_ok = available && remaining > 0;
            self.lease_checked = Some(Instant::now());
        }
        let valid = binding["project_id"].as_str().is_some() && binding["path"].as_str().is_some()
            && binding["workspace"].as_str().is_some() && binding["disk_sha256"].as_str().map_or(false, |s| s.len() == 64);
        let byte_budget_available = self.bytes < wire::MAX_BYTES;
        self.host.edit(false, |shared| {
            shared.binding = valid.then(|| binding.clone());
            if valid {
                let path = binding["path"].as_str().unwrap_or("");
                let name = std::path::Path::new(path).file_name().and_then(|v| v.to_str()).unwrap_or(path);
                let left = (wire::MAX_TRANSFERS - shared.snapshot["transfers"].as_array().map_or(0, Vec::len).min(wire::MAX_TRANSFERS)) as u64;
                let reason = if left == 0 { "宿主事件回执容量已满；不会丢弃原回执".to_owned() }
                    else if !byte_budget_available { "本次运行已到 4 GiB 完整暂存上限".to_owned() }
                    else if remaining == 0 && reason.is_empty() { "工程本次接入额度已耗尽".to_owned() }
                    else { reason.clone() };
                shared.snapshot["ingestion_target"] = json!({"project_id":binding["project_id"],"path":path,"name":name,
                    "available":available && remaining > 0 && left > 0 && byte_budget_available,
                    "reason":reason,"remaining_operations":remaining.min(left)});
            } else { shared.snapshot["ingestion_target"] = Value::Null; }
            Ok(())
        })?;
        if self.session.is_some() && self.flight.is_none() && self.stop.is_none()
            && self.host.snapshot()?["session"]["phase"] == "active" && !self.lease_ok {
            self.pause("当前工程、磁盘保存状态或接入额度已变化；已暂停，不会转移导入目标", false)?;
        }
        Ok(())
    }
    pub(super) fn observe_flight(&mut self) -> Result<(), String> {
        let Some(flight) = self.flight.as_ref() else { return Ok(()) };
        let envelope = crate::ingest_session_api::read_receipt(&self.state, &flight.id)?;
        if envelope["phase"] == "unknown" {
            if envelope["reason"].is_string() && !self.epoch_lost {
                self.epoch_lost = true;
                self.pause("引擎代次已变化；原操作结果仍未知，不重发、不切换工程", true)?;
            }
            return Ok(());
        }
        let result = &envelope["result"];
        if result.is_null() || result["status"] == "pending" { return Ok(()); }
        if self.last_observed.as_ref().map_or(false, |(id, prior)| id == &flight.id && prior == result) { return Ok(()); }
        self.last_observed = Some((flight.id.clone(), result.clone()));
        if result["request_id"] != flight.id || result["action"] != flight.payload["action"] || result["protocol"] != 1 {
            return self.pause("原始引擎回执身份不匹配，停止接收", true);
        }
        if terminal_unknown(result) {
            let unchanged = self.host.snapshot()?["session"]["phase"] == "error";
            if !unchanged { self.pause(result["error"].as_str().unwrap_or("原操作结果未知，只查询原身份"), true)?; }
            return Ok(());
        }
        if !matches!(result["status"].as_str(), Some("succeeded" | "failed")) { return Ok(()); }
        let result = result.clone();
        self.lease_serial += 1;
        let flight = self.flight.take().ok_or("原操作身份丢失")?;
        match flight.kind {
            FlightKind::Arm(request) => {
                if result["status"] == "failed" {
                    self.record_engine_result(&result)?;
                    self.clear_engine_pending()?;
                    self.pause(result["error"].as_str().unwrap_or("工程拒绝建立接入租约"), false)?;
                    self.host.settle(&request, false, false, result["error"].as_str())?;
                } else {
                    let session = self.session.as_mut().ok_or("启动会话已丢失")?;
                    let lease = &result["session"];
                    let id = lease["session_id"].as_str().ok_or("启动回执缺少引擎会话身份")?;
                    if lease["owner"] != "tether" || lease["binding"] != session.binding || lease["phase"] != "armed"
                        || lease["max_operations"].as_u64() != Some(session.max_operations)
                        || lease["remaining_operations"].as_u64() != Some(session.max_operations) {
                        self.flight = Some(Flight { id:flight.id,operation:None,payload:flight.payload,kind:FlightKind::Arm(request.clone()) });
                        self.pause("启动回执的工程、额度或租约不匹配", true)?;
                        self.host.settle(&request, false, true, Some("工程启动结果待核对"))?;
                        return Ok(());
                    }
                    session.engine_id = Some(id.to_owned());
                    self.record_engine_result(&result)?;
                    self.clear_engine_pending()?;
                    if self.stop.is_some() || self.host.snapshot()?["session"]["phase"] == "stopping" {
                        self.host.settle(&request, false, false, Some("启动期间已收到停止；没有打开相机"))?;
                    } else {
                        self.open_session(&request)?;
                    }
                }
            }
            FlightKind::Import { transfer, proof } => {
                if result["status"] == "failed" {
                    self.record_engine_result(&result)?;
                    self.clear_engine_pending()?;
                    self.host.edit(true, |shared| {
                        if let Some(row) = transfer_mut(&mut shared.snapshot, &transfer) {
                            row["phase"] = json!("failed"); row["retryable"] = json!(false);
                            row["error"] = json!(result["error"].as_str().unwrap_or("原导入未成功；不自动重试"));
                        }
                        Ok(())
                    })?;
                    self.pause("原托管导入没有成功，已停止接收；保留来源与原操作身份供核对", false)?;
                } else {
                    match self.imported_receipt(&flight.id, flight.operation.as_deref().unwrap_or(""), &transfer, &proof, &result) {
                        Ok(receipt) => {
                            if let Some(session) = self.session.as_mut() {
                                session.binding = result["session"]["binding"].clone();
                                session.remaining = result["session"]["remaining_operations"].as_u64().unwrap_or(0);
                            }
                            self.host.edit(true, |shared| {
                                if let Some(record) = shared.engine_records.get_mut(&flight.id) { record["receipt"] = result.clone(); }
                                shared.engine_pending = Value::Null;
                                if let Some(row) = transfer_mut(&mut shared.snapshot, &transfer) {
                                    row["phase"] = json!("imported"); row["retryable"] = json!(false);
                                    row["imported_document"] = receipt.clone();
                                    if let Some(object) = row.as_object_mut() { object.remove("error"); }
                                }
                                Ok(())
                            })?;
                            // Completing an already-authorized import during stop
                            // may be recorded, but must not publish a new document
                            // notification or navigate a newer/stopped session.
                            let shared = self.host.shared.lock().map_err(|_| "联机状态锁不可用")?;
                            if !self.host.closing.load(Ordering::Acquire) && !shared.cancel.is_cancelled()
                                && shared.snapshot["session"]["phase"] == "active"
                                && shared.snapshot["session"]["session_id"] == receipt["session_id"]
                                && shared.snapshot["session"]["generation"] == receipt["session_generation"] {
                                let _ = self.host.app.emit(crate::tether_host::EVENT, json!({"type":"imported_document","snapshot":shared.snapshot,"receipt":receipt}));
                            }
                            drop(shared);
                            self.next_read = true;
                        }
                        Err(error) => {
                            self.flight = Some(Flight { id:flight.id,operation:flight.operation,payload:flight.payload,kind:FlightKind::Import { transfer, proof } });
                            self.pause(&format!("完整导入回读未通过：{error}"), true)?;
                        }
                    }
                }
            }
            FlightKind::Release(request) => {
                let expected = self.session.as_ref().and_then(|session| session.engine_id.as_deref());
                if result["status"] == "succeeded" && result["released_session"]["session_id"].as_str() == expected
                    && result["session"].is_null() && !self.driver_open {
                    self.host.edit(true, |shared| {
                        if let Some(record) = shared.engine_records.get_mut(&flight.id) { record["receipt"] = result.clone(); }
                        shared.engine_pending = Value::Null;
                        shared.snapshot["session"]["phase"] = json!("stopped");
                        shared.snapshot["session"]["live_view"] = json!("off");
                        Ok(())
                    })?;
                    self.session = None; self.stop = None; self.lease_ok = false;
                    self.host.settle(&request, true, false, None)?;
                    self.next_read = true;
                } else if result["status"] == "failed" {
                    self.record_engine_result(&result)?;
                    self.clear_engine_pending()?;
                    self.stop = None;
                    self.host.settle(&request, false, false, result["error"].as_str())?;
                    self.pause("驱动已返回关闭，但引擎明确拒绝释放原工程租约；尚未完全停止，请核对原工程", false)?;
                } else {
                    self.flight = Some(Flight { id:flight.id,operation:None,payload:flight.payload,kind:FlightKind::Release(request.clone()) });
                    self.host.settle(&request, false, true, Some("驱动已返回关闭，但工程租约释放未核验；不能报告完全停止"))?;
                    self.pause("工程租约释放结果待核对；没有自动重发", true)?;
                }
            }
        }
        Ok(())
    }
    pub(super) fn clear_engine_pending(&self) -> Result<(), String> {
        self.host.edit(true, |shared| { shared.engine_pending = Value::Null; Ok(()) })?; Ok(())
    }
    pub(super) fn record_engine_result(&self, result: &Value) -> Result<(), String> {
        self.host.edit(true, |shared| {
            let id = result["request_id"].as_str().ok_or("原引擎回执缺少身份")?;
            let record = shared.engine_records.get_mut(id).ok_or("原引擎意图不存在")?;
            record["receipt"] = result.clone(); Ok(())
        })?; Ok(())
    }
    pub(super) fn imported_receipt(&self, request: &str, operation: &str, transfer: &str, proof: &Value, result: &Value) -> Result<Value, String> {
        let session = self.session.as_ref().ok_or("会话不存在")?;
        let lease = &result["session"];
        if lease["session_id"].as_str() != session.engine_id.as_deref() || lease["owner"] != "tether"
            || !["project_id","path","workspace"].iter().all(|key| lease["binding"][*key] == session.binding[*key])
            || lease["binding"]["disk_sha256"].as_str().map_or(true, |v| v.len() != 64)
            || result["operation"]["request_id"] != request || result["operation"]["operation_id"] != operation
            || result["operation"]["status"] != "succeeded" {
            return Err("工程租约或原始操作关联不符".into());
        }
        let rows = result["operation"]["documents"].as_array().filter(|v| v.len() == 1).ok_or("缺少唯一实际导入文档")?;
        let row = &rows[0];
        let source = proof["path"].as_str().ok_or("来源路径缺失")?;
        let extension = std::path::Path::new(source).extension().and_then(|v| v.to_str()).ok_or("来源扩展名缺失")?.to_ascii_lowercase();
        let name = crate::ingest_receipt_validation::uuid_v5(operation, source)?;
        let expected = session.destination.path.join(format!("{name}.{extension}"));
        let original_name = std::path::Path::new(source).file_name().and_then(|v| v.to_str()).ok_or("来源名称缺失")?;
        if row["import_receipt_id"] != operation || row["original_path"] != proof["path"]
            || row["source_sha256"] != proof["sha256"] || row["size"] != proof["size"]
            || row["stat"] != proof["stat"] || row["occurrence_id"] != proof["occurrence_id"]
            || row["completion"] != "completed_transfer" || row["filename"] != original_name
            || row["path"].as_str() != expected.to_str()
            || row["document_id"].as_str().map_or(true, str::is_empty)
            || row["source_asset_id"].as_str().map_or(true, str::is_empty)
            || row["recipe_version_id"].as_str().map_or(true, str::is_empty) {
            return Err("已保存文档的完整内容、来源 stat、命名、事件或托管路径不符".into());
        }
        session.destination.verify()?;
        Ok(json!({"import_receipt_id":operation,"transfer_id":transfer,"session_id":session.id,
            "session_generation":session.generation,"document_id":row["document_id"],
            "project_id":session.binding["project_id"],"project_path":session.binding["path"],
            "managed_path":row["path"],"sha256":proof["sha256"],"bytes":proof["size"]}))
    }
}
