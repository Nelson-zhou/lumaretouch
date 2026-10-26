//! One serialized native owner drives discovery and journaled core transitions.
//! Timers only progress an explicitly started run and read its original owners.
use std::{collections::BTreeMap, sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}, mpsc::{self, Receiver, SyncSender}}, time::{Duration, Instant}};
use lrt_local_workflow::{DurableRunner, ports::{CommandKind, Receipt, ReceiptResult}, poll::DirectoryPoller,
    scheduler::RunStatus, schema::{Graph, NodeKind, ValidatedGraph}};
use serde_json::{json, Value};
use crate::AppState;
use super::{data::*, ingestion, storage::{self, Store}, transport, view, review, wire::{self, Action, PreflightInput, Request, ReviewImageInput}};

pub enum Message {
    Submit(Request, SyncSender<Result<Value, String>>),
    Preflight(PreflightInput, SyncSender<Result<Value, String>>),
    ReviewImage(ReviewImageInput, SyncSender<Result<Value, String>>),
    Refresh,
    RefreshCatalogue,
    Shutdown,
}
#[derive(Default)]
pub struct Public {
    pub workspace: Value, pub definitions: BTreeMap<String, Value>,
    pub receipts: BTreeMap<String, Value>, pub runs: BTreeMap<String, Value>,
}
pub struct Host { pub tx: SyncSender<Message>, pub public: Arc<Mutex<Public>>, pub closing: Arc<AtomicBool> }
struct Check {
    input: PreflightInput, request: Value, epoch: [u8; 16], expires: u64,
    deadline: Instant, reply: SyncSender<Result<Value, String>>,
    managed_root_identity: [String; 2],
}
struct ImageRead { request: Value, handoff: Value, epoch: [u8; 16], deadline: Instant, reply: SyncSender<Result<Value, String>> }
struct Token { graph_digest: String, lease_id: String, expires: u64, managed_root_identity: [String; 2] }
struct Active { runner: DurableRunner, poller: DirectoryPoller, maximum: usize, last_poll: Instant }
pub struct Runtime {
    store: Store, data: Data, state: Arc<AppState>, public: Arc<Mutex<Public>>,
    active: Option<Active>, checks: Vec<Check>, tokens: BTreeMap<String, Token>,
    images: Vec<ImageRead>,
    profile: Value, profile_request: Option<Value>, profile_epoch: Option<[u8; 16]>,
    closing: bool, shutdown_requested: Arc<AtomicBool>,
}
impl Runtime {
    pub fn create(store: Store, previous: Option<Value>, state: Arc<AppState>, public: Arc<Mutex<Public>>, shutdown_requested: Arc<AtomicBool>) -> Result<Self, String> {
        let mut data: Data = match previous { Some(value) => serde_json::from_value(value).map_err(|e| e.to_string())?, None => Data::new()? };
        data.recover()?;
        // Rebuild the display from the checksummed core journals. Recovery is
        // readback only: an old lease is never adopted by a new engine epoch.
        for run in data.runs.values_mut() {
            match DurableRunner::open(&store.root.join(format!("run-{}", run.run_id))) {
                Ok(runner) => {
                    run.sequence = run.sequence.checked_add(1).filter(|value| *value <= wire::MAX_SAFE).ok_or("运行修订已耗尽")?;
                    run.snapshot = view::run(runner.state(), run);
                    if !run.released {
                        run.snapshot["status"] = json!("paused");
                        run.snapshot["effects_settled"] = json!(false);
                    }
                }
                Err(error) => { data.blocked = Some(format!("原工作流日志需要核对：{error}")); run.error = data.blocked.clone(); }
            }
        }
        let mut runtime = Self { store, data, state, public, active: None, checks: Vec::new(), tokens: BTreeMap::new(),
            images: Vec::new(), profile: Value::Null, profile_request: None, profile_epoch: None, closing: false, shutdown_requested };
        runtime.persist()?; // Bootstrap exposes a stable scope, never a null snapshot.
        Ok(runtime)
    }
    fn persist(&mut self) -> Result<(), String> {
        self.data.revision = self.data.revision.checked_add(1).filter(|value| *value <= wire::MAX_SAFE).ok_or("工作区修订已耗尽")?;
        if let Err(error) = self.store.save(&self.data) {
            self.data.blocked = Some(format!("持久化结果待核对：{error}；没有继续发送操作"));
            self.publish();
            return Err(error);
        }
        self.publish();
        Ok(())
    }
    fn publish(&self) {
        if let Ok(mut shared) = self.public.lock() {
            let available = transport::supported(&self.state) && transport::epoch(&self.state).is_ok() && !self.closing;
            shared.workspace = view::workspace(&self.data, available, &self.profile, self.profile_request.is_some());
            shared.definitions = self.data.definitions.iter().filter_map(|(id, row)| serde_json::to_value(&row.definition).ok().map(|v| (id.clone(), v))).collect();
            shared.receipts = self.data.requests.iter().map(|(id, row)| (id.clone(), row.receipt.clone())).collect();
            shared.runs = self.data.runs.iter().map(|(id, row)| (id.clone(), row.snapshot.clone())).collect();
        }
    }
    pub fn run(mut self, rx: Receiver<Message>) {
        loop {
            if self.shutdown_requested.load(Ordering::Acquire) {
                self.closing = true;
                if let Some(active) = self.active.as_mut() { let _ = active.runner.stop(); }
                let _ = self.update_run();
                self.publish();
                return;
            }
            match rx.recv_timeout(Duration::from_millis(250)) {
                Ok(Message::Submit(request, reply)) => { let result = self.submit(request); let _ = reply.send(result); }
                Ok(Message::Preflight(input, reply)) => self.preflight(input, reply),
                Ok(Message::ReviewImage(input, reply)) => self.review_image(input, reply),
                Ok(Message::Refresh) => {
                    if self.profile_request.is_none() && self.profile["unavailable"] == true { self.profile = Value::Null; }
                    self.refresh_profile();
                }
                Ok(Message::RefreshCatalogue) => {
                    if self.profile_request.is_none() { self.profile = Value::Null; }
                    self.refresh_profile();
                }
                Ok(Message::Shutdown) => {
                    self.closing = true;
                    if let Some(active) = self.active.as_mut() { let _ = active.runner.stop(); }
                    if let Err(error) = self.update_run() { self.fence(error); }
                    self.publish();
                    // App shutdown must not wait indefinitely for native/export
                    // owners. Persisted unresolved ownership remains fenced.
                    return;
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => return,
                Err(mpsc::RecvTimeoutError::Timeout) => (),
            }
            self.refresh_profile();
            self.poll_checks();
            self.poll_images();
            if self.data.blocked.is_none() && !self.closing {
                if self.data.lease.as_ref().is_some_and(|lease| transport::epoch(&self.state).ok() != Some(lease.epoch)) {
                    self.fence("引擎代际已变化，原租约不可恢复；保留原请求，只能核对，不能重放".into());
                    continue;
                }
                if let Err(error) = self.poll_ui().and_then(|_| self.tick_run()) { self.fence(error); }
            }
            self.publish();
        }
    }
    fn fence(&mut self, error: String) {
        self.data.blocked = Some(error.clone());
        for row in self.data.requests.values_mut().filter(|row| wire::unresolved(&row.receipt)) {
            row.receipt = row.request.receipt("unknown", &error);
        }
        if let Some(id) = &self.data.active_run {
            if let Some(meta) = self.data.runs.get_mut(id) {
                meta.error = Some(error.clone()); meta.snapshot["effects_settled"] = json!(false);
                meta.snapshot["status"] = json!("paused");
                meta.snapshot["diagnostics"] = json!([{"severity":"error","code":"native_host_fence","message":error}]);
            }
        }
        let _ = self.persist();
    }
    fn refresh_profile(&mut self) {
        let epoch = match transport::epoch(&self.state) { Ok(epoch) => epoch, Err(_) => return };
        if self.profile_epoch != Some(epoch) {
            self.profile = Value::Null; self.profile_request = None; self.profile_epoch = Some(epoch);
        }
        if !transport::supported(&self.state) { return; }
        if let Some(request) = self.profile_request.clone() {
            if let Ok(reply) = transport::read(&self.state, request["request_id"].as_str().unwrap_or("")) {
                if reply["phase"] == "done" {
                    let result = &reply["result"];
                    if result["supported"] == true && result["recipe_sha256"].as_str().is_some_and(|hash| hash.len() == 64)
                        && result["recipe_profile"].is_object() { self.profile = result.clone(); }
                    else { self.profile = json!({"unavailable":true}); }
                    self.profile_request = None;
                    self.data.revision = self.data.revision.saturating_add(1).min(wire::MAX_SAFE);
                    self.publish();
                }
            }
        } else if self.profile.is_null() {
            if let Ok(id) = storage::uuid() {
                let request = json!({"cmd":"workflow_owner","protocol":1,"action":"profile","request_id":id});
                self.profile_request = Some(request.clone());
                if transport::send(&self.state, request, epoch).is_err() { self.profile_request = None; self.profile = json!({"unavailable":true}); }
            }
        }
    }
    fn lease(&self, id: &str) -> Result<Lease, String> {
        let lease = self.data.lease.as_ref().filter(|lease| lease.lease_id == id).ok_or("没有匹配的实际工程租约")?;
        if transport::epoch(&self.state)? != lease.epoch { return Err("引擎已重启，原租约不可恢复；禁止重发".into()); }
        Ok(lease.clone())
    }
    fn preflight(&mut self, input: PreflightInput, reply: SyncSender<Result<Value, String>>) {
        let prepared = (|| -> Result<(ValidatedGraph, Lease), String> {
            if input.port_version != 1 || self.data.blocked.is_some() || !self.checks.is_empty() || self.active.is_some() { return Err("当前不能检测新工作流；请先核对原运行".into()); }
            let graph = input.graph.clone().validate().map_err(|e| e.to_string())?;
            graph.preflight_filesystem().map_err(|e| e.to_string())?;
            if graph.import().error_policy != lrt_local_workflow::schema::ErrorPolicy::Stop {
                return Err("实际导入 owner 失败或取消后会停止租约；导入节点目前只支持 stop 策略".into());
            }
            let lease = self.lease(&input.lease_id)?;
            if storage::now()? >= lease.expires || lease.binding["project_id"] != graph.project_id() { return Err("工程租约已过期或工程身份不匹配".into()); }
            let NodeKind::ManagedImport { project_path, .. } = &graph.import().operation else { unreachable!() };
            if lease.binding["path"] != *project_path { return Err("当前已保存工程路径不匹配；不会切换工程".into()); }
            Ok((graph, lease))
        })();
        match prepared {
            Err(error) => { let _ = reply.send(Err(error)); }
            Ok((graph, lease)) => {
                let NodeKind::ManagedImport { managed_root, .. } = &graph.import().operation else { unreachable!() };
                let managed_root_identity = match storage::pin_directory(std::path::Path::new(managed_root)) {
                    Ok(value) => value, Err(error) => { let _ = reply.send(Err(error)); return; }
                };
                let request_id = match storage::uuid() { Ok(value) => value, Err(error) => { let _ = reply.send(Err(error)); return; } };
                let request = json!({"cmd":"workflow_owner","protocol":1,"action":"preflight","request_id":request_id,
                    "session_id":lease.lease_id,"graph":input.graph,"graph_sha256":graph.digest()});
                let expires = storage::now().unwrap_or(0).saturating_add(60).min(lease.expires);
                if let Err(error) = transport::send(&self.state, request.clone(), lease.epoch) { let _ = reply.send(Err(error)); return; }
                self.checks.push(Check { input, request, epoch: lease.epoch, expires, deadline: Instant::now() + Duration::from_secs(15), reply, managed_root_identity });
            }
        }
    }
    fn poll_checks(&mut self) {
        let checks = std::mem::take(&mut self.checks);
        for check in checks {
            if check.deadline < Instant::now() || transport::epoch(&self.state).ok() != Some(check.epoch) {
                let _ = check.reply.send(Err("检测回执尚未确认或引擎代际变化；没有启动工作流".into())); continue;
            }
            let result = transport::read(&self.state, check.request["request_id"].as_str().unwrap_or(""));
            match result {
                Ok(value) if value["phase"] == "done" => {
                    let value = &value["result"];
                    let supported = value["supported"] == true && matches!(value["status"].as_str(), Some("readback" | "succeeded"));
                    let token = if supported { storage::uuid().unwrap_or_default() } else { String::new() };
                    if supported && !token.is_empty() {
                        self.tokens.retain(|_, token| token.expires > storage::now().unwrap_or(u64::MAX));
                        if self.tokens.len() < 16 { self.tokens.insert(token.clone(), Token {
                            graph_digest: check.request["graph_sha256"].as_str().unwrap_or("").into(), lease_id: check.input.lease_id.clone(), expires: check.expires,
                            managed_root_identity: check.managed_root_identity.clone() }); }
                    }
                    let report = json!({"workflow_id":check.input.graph.workflow_id,"graph_revision":check.input.graph.revision,
                        "lease_id":check.input.lease_id,"preflight_token":token,"valid_until":storage::timestamp(check.expires).unwrap_or_default(),
                        "can_start":supported && self.tokens.contains_key(&token), "graph_sha256":check.request["graph_sha256"],
                        "diagnostics":value.get("diagnostics").cloned().unwrap_or_else(||json!([{"severity":"error","code":"owner_preflight_failed","message":value["error"].as_str().unwrap_or("owner 检测未通过")}])) ,
                        "recipe_sha256":value["recipe_sha256"],"recipe_profile":value["recipe_profile"]});
                    let _ = check.reply.send(Ok(report));
                }
                Err(error) => { let _ = check.reply.send(Err(error)); }
                _ => self.checks.push(check),
            }
        }
    }
    fn review_image(&mut self, input: ReviewImageInput, reply: SyncSender<Result<Value, String>>) {
        let result = (|| -> Result<(Value, Value, [u8; 16]), String> {
            if self.closing || self.data.blocked.is_some() || self.images.len() >= 4 { return Err("审核图片读取当前不可用；没有批准任何预设".into()); }
            let active = self.active.as_ref().ok_or("没有当前实际运行")?;
            if active.runner.state().run_id() != input.run_id { return Err("审核图片运行身份不匹配".into()); }
            let pending = active.runner.state().pending().ok_or("没有待审核的原操作")?;
            let meta = self.data.runs.get(&input.run_id).ok_or("审核运行不存在")?;
            if pending.identity.operation_id != input.operation_id || !review::image_request(&input, &meta.handoff) {
                return Err("审核图片已过期或不是当前交接的精确内容".into());
            }
            let lease = self.lease(&meta.lease_id)?;
            let request = json!({"cmd":"workflow_owner","protocol":1,"action":"review_image","request_id":storage::uuid()?,
                "session_id":lease.lease_id,"operation_id":input.operation_id,"review_id":input.review_id,
                "review_sha256":input.review_sha256,"side":input.side,"sha256":input.sha256,"page":input.page});
            self.send(request.clone(), lease.epoch)?;
            Ok((request, meta.handoff.clone(), lease.epoch))
        })();
        match result {
            Ok((request, handoff, epoch)) => self.images.push(ImageRead { request, handoff, epoch, deadline: Instant::now() + Duration::from_secs(15), reply }),
            Err(error) => { let _ = reply.send(Err(error)); }
        }
    }
    fn poll_images(&mut self) {
        for read in std::mem::take(&mut self.images) {
            if read.deadline < Instant::now() || transport::epoch(&self.state).ok() != Some(read.epoch) {
                let _ = read.reply.send(Err("审核图像读取超时或引擎已变化；没有批准预设".into())); continue;
            }
            match self.read(&read.request) {
                Ok(response) if response["phase"] == "done" => {
                    let result = &response["result"];
                    let current = self.data.active_run.as_ref().and_then(|id| self.data.runs.get(id));
                    let valid = current.is_some_and(|run| run.handoff == read.handoff)
                        && result["status"] == "readback" && result["operation_id"] == read.request["operation_id"]
                        && review::image_page(&result["image"], &read.request, &read.handoff);
                    let _ = read.reply.send(if valid { Ok(result["image"].clone()) } else {
                        Err(result["error"].as_str().unwrap_or("原审核图片身份、页面或字节校验失败；不能批准").into())
                    });
                }
                Ok(response) if response["phase"] == "unknown" => { let _ = read.reply.send(Err("原审核图像结果未知；没有批准预设".into())); }
                Err(error) => { let _ = read.reply.send(Err(error)); }
                _ => self.images.push(read),
            }
        }
    }
    fn settle(&mut self, id: &str, receipt: Value) -> Result<(), String> {
        let row = self.data.requests.get_mut(id).ok_or("请求身份丢失")?;
        row.receipt = receipt; row.external = None;
        self.persist()
    }
    fn submit(&mut self, request: Request) -> Result<Value, String> {
        if let Some(row) = self.data.requests.get(&request.request_id) {
            if serde_json::to_value(&row.request).map_err(|e| e.to_string())? != serde_json::to_value(&request).map_err(|e| e.to_string())? {
                return Err("原请求身份已绑定其他参数；没有重发".into());
            }
            return Ok(row.receipt.clone());
        }
        if self.data.blocked.is_some() || self.closing { return Err(self.data.blocked.clone().unwrap_or_else(|| "工作流宿主已关闭".into())); }
        if self.data.requests.len() >= wire::MAX_REQUESTS { return Err("工作流请求日志已满；不会丢弃旧回执".into()); }
        if self.data.requests.values().any(|row| wire::unresolved(&row.receipt)) && !matches!(request.command, Action::Stop { .. }) {
            return Err("原请求结果仍待核对；只可查询或停止实际运行".into());
        }
        let id = request.request_id.clone();
        self.data.requests.insert(id.clone(), RequestRow { receipt: request.receipt("pending", "原请求已保留，等待真实结果"), request: request.clone(), external: None });
        self.persist()?; // Durable identity precedes every possible effect.
        if let Err(error) = self.begin(&request) {
            // If an external intent exists, a send failure is never proof that
            // the owner did nothing. Keep that request and fence redispatch.
            if self.data.requests[&id].external.is_some() {
                self.data.requests.get_mut(&id).unwrap().receipt = request.receipt("unknown", &error);
                self.persist()?;
            } else { self.settle(&id, request.receipt("failed", &error))?; }
        }
        Ok(self.data.requests[&id].receipt.clone())
    }
    fn begin(&mut self, request: &Request) -> Result<(), String> {
        match &request.command {
            Action::SaveDefinition { definition, expected_storage_revision } => {
                definition.validate()?;
                if self.active.is_some() { return Err("运行期间不能替换定义".into()); }
                let previous = self.data.definitions.get(&definition.graph.workflow_id);
                if previous.map(|row| &row.definition.storage_revision).unwrap_or(&None) != expected_storage_revision
                    || &definition.storage_revision != expected_storage_revision { return Err("定义存储修订已变化；请读取后再编辑".into()); }
                if previous.is_none() && self.data.definitions.len() >= wire::MAX_DEFINITIONS { return Err("定义容量已满".into()); }
                let mut saved = definition.clone();
                saved.storage_revision = Some(storage::uuid()?);
                self.data.definitions.insert(saved.graph.workflow_id.clone(), SavedDefinition { definition: saved.clone(), updated_at: storage::timestamp(storage::now()?)? });
                self.settle(&request.request_id, request.success(json!({"kind":"save_definition","definition":saved})))
            }
            Action::AcquireProjectLease { project_id, project_path } => {
                if !wire::identity(project_id) || !std::path::Path::new(project_path).is_absolute() || self.data.lease.is_some() || self.active.is_some() {
                    return Err("请先释放原租约并指定当前实际已保存工程".into());
                }
                if !transport::supported(&self.state) { return Err("当前引擎未提供真实本地工作流 owner 协议".into()); }
                self.ui_external(request, "acquire_state", json!({"cmd":"ingest_session","action":"state","request_id":storage::uuid()?}))
            }
            Action::ReleaseProjectLease { lease_id } => {
                let lease = self.lease(lease_id)?;
                if self.active.is_some() || self.data.operations.values().any(|op| !op.settled) { return Err("仍有运行或 owner 结果待核对，不能释放租约".into()); }
                self.ui_external(request, "release", json!({"cmd":"ingest_session","action":"release","request_id":storage::uuid()?,"session_id":lease.lease_id}))
            }
            Action::Start { graph, lease_id, preflight_token, automatic_ack } => self.start(request, graph.clone(), lease_id, preflight_token, automatic_ack.as_ref()),
            Action::Stop { run_id } => {
                if self.data.active_run.as_deref() != Some(run_id) { return Err("没有匹配的活动运行".into()); }
                if !self.data.runs[run_id].handoff.is_null() || self.active.as_ref().and_then(|active| active.runner.state().pending())
                    .is_some_and(|pending| matches!(pending.operation, CommandKind::PreflightPreset { .. } | CommandKind::ApplyPreset { .. })) {
                    return Err(if self.data.runs[run_id].handoff["mode"] == "automatic" {
                        "自动处理尚未到达已核实返回边界；等待原操作回执，未知结果只能查询，不能停止后重启"
                    } else { "预设交接尚未结清，来源监听已暂停。请先取消并返回，或完成保存与返回；停止不能释放半完成的交接" }.into());
                }
                self.active.as_mut().ok_or("原运行仅能恢复核对，不能恢复原引擎租约")?.runner.stop().map_err(|e| e.to_string())?;
                self.update_run()?;
                self.settle(&request.request_id, request.success(json!({"kind":"stop","run":self.data.runs[run_id].snapshot})))
            }
            Action::ReviewStep { run_id, operation_id, step, payload } => {
                let active = self.active.as_ref().ok_or("没有当前实际运行；旧代际交接只能核对")?;
                if active.runner.state().run_id() != run_id { return Err("交接运行身份不匹配".into()); }
                if matches!(active.runner.state().status(), RunStatus::Paused { detail: lrt_local_workflow::scheduler::PauseReason::UncertainOutcome { .. } }) {
                    return Err("原核心操作结果未知；只能查询，不可执行新的交接步骤".into());
                }
                let pending = active.runner.state().pending().ok_or("当前核心没有保留的交接操作")?;
                if self.data.requests.values().any(|row| row.request.request_id != request.request_id && row.receipt["status"] == "succeeded"
                    && matches!(&row.request.command, Action::ReviewStep { run_id: prior_run, operation_id: prior_operation, step: prior_step, .. }
                        if prior_run == run_id && prior_operation == operation_id && prior_step == step)) {
                    return Err("该原始交接步骤已确认；请读取新阶段，不要以新身份重复执行".into());
                }
                let original = self.data.operations.get(operation_id).ok_or("交接原操作不存在")?;
                let handoff = &self.data.runs[run_id].handoff;
                if pending.identity.operation_id != *operation_id || original.settled || !review::handoff(handoff, &original.command)
                    || !review::step_allowed(handoff, step, payload) { return Err("交接身份、阶段或批准内容已变化；没有执行新操作，请读取原状态".into()); }
                let lease = self.lease(&self.data.runs[run_id].lease_id)?;
                self.ui_external(request, "review_step", json!({"cmd":"workflow_owner","protocol":1,"action":"review_step",
                    "request_id":storage::uuid()?,"session_id":lease.lease_id,"operation_id":operation_id,"step":step,"payload":payload}))
            }
            Action::OpenReview { run_id, review_id } => {
                let active = self.active.as_ref().ok_or("没有实际待审核运行")?;
                if active.runner.state().run_id() != run_id { return Err("审核运行身份不匹配".into()); }
                let pending = active.runner.state().pending().ok_or("没有保留的 owner 审核操作")?;
                let snapshot = &self.data.runs[run_id].snapshot;
                if snapshot["review"]["review_id"] != *review_id { return Err("审核身份与原报告不匹配".into()); }
                let lease = self.lease(&self.data.runs[run_id].lease_id)?;
                self.ui_external(request, "open_review", json!({"cmd":"workflow_owner","protocol":1,"action":"open_review",
                    "request_id":storage::uuid()?,"session_id":lease.lease_id,"operation_id":pending.identity.operation_id,"review_id":review_id}))
            }
        }
    }
    fn ui_external(&mut self, request: &Request, phase: &str, envelope: Value) -> Result<(), String> {
        let epoch = transport::epoch(&self.state)?;
        self.data.requests.get_mut(&request.request_id).ok_or("请求身份丢失")?.external = Some(UiExternal { phase: phase.into(), request: envelope.clone(), epoch, query: None });
        self.persist()?;
        self.send(envelope, epoch)
    }
    fn send(&self, request: Value, epoch: [u8; 16]) -> Result<(), String> {
        if self.shutdown_requested.load(Ordering::Acquire) { return Err("应用正在关闭；未派发新的工作流请求".into()); }
        if transport::epoch(&self.state)? != epoch { return Err("引擎代际变化，原请求保持待核对".into()); }
        if request["cmd"] == "ingest_session" { crate::ingest_session_api::submit(&self.state, request).map(|_| ()) }
        else { transport::send(&self.state, request, epoch) }
    }
    fn read(&self, request: &Value) -> Result<Value, String> {
        let id = request["request_id"].as_str().ok_or("原请求身份缺失")?;
        if request["cmd"] == "ingest_session" { crate::ingest_session_api::read_receipt(&self.state, id) }
        else { transport::read(&self.state, id) }
    }
    fn poll_ui(&mut self) -> Result<(), String> {
        let pending: Vec<_> = self.data.requests.values().filter_map(|row| row.external.clone().map(|ext| (row.request.clone(), ext))).collect();
        for (request, external) in pending {
            if transport::epoch(&self.state).ok() != Some(external.epoch) { return Err("引擎代际变化；租约或请求结果未知，禁止重新提交".into()); }
            let response = self.read(&external.request)?;
            if external.phase == "review_step" && (response["phase"] == "pending" || response["phase"] == "unknown"
                || response["result"]["status"] == "unknown") {
                if let Some(query) = &external.query {
                    if self.read(query)?["phase"] == "done" {
                        self.data.requests.get_mut(&request.request_id).unwrap().external.as_mut().unwrap().query = None;
                    }
                } else {
                    let query = json!({"cmd":"workflow_owner","protocol":1,"action":"query","request_id":storage::uuid()?,
                        "session_id":external.request["session_id"],"original_request_id":external.request["request_id"],"operation_id":external.request["operation_id"]});
                    self.data.requests.get_mut(&request.request_id).unwrap().external.as_mut().unwrap().query = Some(query.clone());
                    // The engine republishes only the retained original step
                    // envelope. A readback cannot forge a new write receipt.
                    let _ = self.send(query, external.epoch);
                }
            }
            if response["phase"] == "pending" { continue; }
            if response["phase"] == "unknown" || response["result"]["status"] == "unknown" {
                let receipt = request.receipt("unknown", "原始 owner 结果未知；只保留并查询原请求，不重新执行");
                if self.data.requests[&request.request_id].receipt != receipt {
                    self.data.requests.get_mut(&request.request_id).unwrap().receipt = receipt;
                    self.persist()?;
                }
                continue;
            }
            let result = &response["result"];
            match external.phase.as_str() {
                "acquire_state" => {
                    let Action::AcquireProjectLease { project_id, project_path } = &request.command else { return Err("租约请求阶段不匹配".into()); };
                    let state = &result["state"];
                    if result["status"] != "readback" || state["available"] != true || !result["session"].is_null()
                        || state["current_binding"]["project_id"] != *project_id || state["current_binding"]["path"] != *project_path {
                        self.settle(&request.request_id, request.receipt("failed", state["reason"].as_str().unwrap_or("指定目标不是当前干净、已保存且可独占的工程；未切换或保存工程")))?;
                        continue;
                    }
                    let maximum = state["receipt_capacity"].as_u64().unwrap_or(0).min(64);
                    if maximum == 0 { self.settle(&request.request_id, request.receipt("failed", "工程导入回执容量已满"))?; continue; }
                    self.ui_external(&request, "acquire_arm", json!({"cmd":"ingest_session","action":"arm","request_id":storage::uuid()?,
                        "owner":"workflow","expected":state["current_binding"],"max_operations":maximum}))?;
                }
                "acquire_arm" => {
                    if result["status"] == "succeeded" && result["session"]["owner"] == "workflow" && result["session"]["phase"] == "armed"
                        && result["session"]["binding"] == external.request["expected"] {
                        let lease = Lease { lease_id: result["session"]["session_id"].as_str().ok_or("缺少真实租约身份")?.into(),
                            binding: result["session"]["binding"].clone(), epoch: external.epoch, expires: storage::now()?.saturating_add(3600),
                            arm_request: external.request.clone(), arm_receipt: result.clone() };
                        let public = lease.public(); self.data.lease = Some(lease);
                        self.settle(&request.request_id, request.success(json!({"kind":"acquire_project_lease","lease":public})))?;
                    } else if result["status"] == "failed" && result["session"].is_null() {
                        self.settle(&request.request_id, request.receipt("failed", result["error"].as_str().unwrap_or("工程租约未取得")))?;
                    }
                }
                "release" => {
                    let id = external.request["session_id"].as_str().ok_or("租约身份丢失")?;
                    if result["status"] == "succeeded" && result["session"].is_null() && result["released_session"]["session_id"] == id {
                        self.data.lease = None; self.tokens.clear();
                        self.settle(&request.request_id, request.success(json!({"kind":"release_project_lease","released":true,"lease_id":id})))?;
                    } else if result["status"] == "failed" {
                        self.settle(&request.request_id, request.receipt("failed", result["error"].as_str().unwrap_or("原租约尚未释放")))?;
                    }
                }
                "review_step" => {
                    let Action::ReviewStep { run_id, operation_id, step, .. } = &request.command else { return Err("交接请求阶段不匹配".into()); };
                    if result["operation_id"] != *operation_id || result["step"] != *step { return Err("交接回执不属于原始精确步骤".into()); }
                    // Step replies settle only this explicit request. Core state
                    // advances exclusively from the original execute/query receipt.
                    if result["status"] == "succeeded" {
                        self.settle(&request.request_id, request.success(json!({"kind":"review_step","run_id":run_id,
                            "operation_id":operation_id,"step":step,"message":result["message"].as_str().unwrap_or("已核对交接步骤；等待原操作回执更新")})))?;
                    } else if result["status"] == "failed" && result["dispatch_rejected"] == true {
                        self.settle(&request.request_id, request.receipt("failed", result["error"].as_str().unwrap_or("实际 owner 在执行前拒绝该交接步骤")))?;
                    } else if result["status"] == "failed" {
                        self.data.requests.get_mut(&request.request_id).unwrap().receipt = request.receipt("unknown", "交接步骤没有无效果证明；保留原请求，只读核对");
                        self.persist()?;
                    }
                }
                "open_review" => {
                    if matches!(result["status"].as_str(), Some("succeeded" | "readback")) {
                        self.settle(&request.request_id, request.success(json!({"kind":"open_review","opened":result["opened"] == true,
                            "message":result["message"].as_str().unwrap_or("审核由实际 owner 保留；这里未批准任何报告")})))?;
                    } else if result["status"] == "failed" {
                        self.settle(&request.request_id, request.receipt("failed", result["error"].as_str().unwrap_or("实际审核界面尚不可用")))?;
                    }
                }
                _ => return Err("未知原生请求阶段".into()),
            }
        }
        Ok(())
    }
    fn start(&mut self, request: &Request, graph: Graph, lease_id: &str, token: &str, automatic_ack: Option<&wire::AutomaticStartAck>) -> Result<(), String> {
        if self.active.is_some() || self.data.runs.len() >= wire::MAX_RUNS { return Err("已有运行或运行日志已满".into()); }
        let graph = graph.validate().map_err(|e| e.to_string())?;
        if graph.automatic() {
            if !automatic_ack.is_some_and(|ack| ack.matches(graph.digest())) {
                return Err("自动模式须在本次启动明确确认当前图的范围、预设、保存、导出与失败策略；保存定义不能授权启动".into());
            }
        } else if automatic_ack.is_some() {
            return Err("人工审核模式不能携带自动启动授权".into());
        }
        graph.preflight_filesystem().map_err(|e| e.to_string())?;
        let lease = self.lease(lease_id)?;
        let checked = self.tokens.get(token).ok_or("缺少当前宿主检测令牌")?;
        if checked.graph_digest != graph.digest() || checked.lease_id != lease_id || checked.expires <= storage::now()? || lease.expires <= storage::now()? {
            return Err("检测令牌已过期或与图、租约不匹配".into());
        }
        let saved = self.data.definitions.get(&graph.graph().workflow_id).ok_or("请先保存当前定义")?;
        if saved.definition.graph.clone().validate().map_err(|e| e.to_string())?.digest() != graph.digest() { return Err("当前图与保存定义不一致".into()); }
        let managed_root_identity = checked.managed_root_identity.clone();
        let NodeKind::ManagedImport { managed_root, .. } = &graph.import().operation else { unreachable!() };
        if storage::pin_directory(std::path::Path::new(managed_root))? != managed_root_identity { return Err("检测后托管原片目录已替换；没有开始运行".into()); }
        let run_id = storage::uuid()?;
        let root = self.store.run_directory(&run_id)?;
        let runner = DurableRunner::create(&root, graph, run_id.clone()).map_err(|e| e.to_string())?;
        let poller = runner.source().map_err(|e| e.to_string())?;
        let mut meta = Run { run_id: run_id.clone(), lease_id: lease_id.into(), started_at: storage::timestamp(storage::now()?)?,
            managed_root_identity,
            sequence: 0, snapshot: Value::Null, released: false, release: None, error: None, handoff: Value::Null };
        meta.snapshot = view::run(runner.state(), &meta);
        let maximum = lease.arm_request["max_operations"].as_u64().filter(|value| (1..=64).contains(value)).ok_or("租约导入上限无效")? as usize;
        self.data.runs.insert(run_id.clone(), meta); self.data.active_run = Some(run_id.clone());
        self.active = Some(Active { runner, poller, maximum, last_poll: Instant::now() - Duration::from_secs(1) });
        self.tokens.clear();
        self.settle(&request.request_id, request.success(json!({"kind":"start","run":self.data.runs[&run_id].snapshot})))
    }
    fn update_run(&mut self) -> Result<(), String> {
        if let Some(active) = &self.active {
            let id = active.runner.state().run_id();
            let meta = self.data.runs.get_mut(id).ok_or("运行身份丢失")?;
            meta.sequence = meta.sequence.checked_add(1).filter(|value| *value <= wire::MAX_SAFE).ok_or("运行修订已耗尽")?;
            meta.snapshot = view::run(active.runner.state(), meta);
        }
        self.persist()
    }
    fn tick_run(&mut self) -> Result<(), String> {
        let Some(active) = self.active.as_ref() else { return Ok(()); };
        let id = active.runner.state().run_id().to_owned();
        let lease_id = self.data.runs[&id].lease_id.clone();
        let lease = self.lease(&lease_id)?;
        let handoff_active = !self.data.runs[&id].handoff.is_null() || active.runner.state().pending()
            .is_some_and(|pending| matches!(pending.operation, CommandKind::PreflightPreset { .. } | CommandKind::ApplyPreset { .. }));
        if !handoff_active && storage::now()? >= lease.expires && matches!(active.runner.state().status(), RunStatus::Running) {
            self.active.as_mut().unwrap().runner.stop().map_err(|e| e.to_string())?;
            self.data.runs.get_mut(&id).unwrap().error = Some("工程租约有效期已到；停止新调度，继续核对已启动的 owner 效果".into());
            self.update_run()?;
        }
        let active = self.active.as_mut().unwrap();
        if !handoff_active && matches!(active.runner.state().status(), RunStatus::Running) && !active.runner.state().is_sealed()
            && active.last_poll.elapsed() >= Duration::from_secs(1) {
            active.last_poll = Instant::now();
            if let Err(error) = active.runner.poll_source_bounded(&mut active.poller, crate::monotonic_clock::now_ns() / 1_000_000, active.maximum) {
                // The core records Stop for discovery failures. Do not stop
                // querying an already dispatched import/export on that account.
                self.data.runs.get_mut(&id).unwrap().error = Some(format!("来源读取已停止：{error}；仍会核对原 owner 操作"));
            }
            if active.runner.state().jobs().len() >= active.maximum && !active.runner.state().is_sealed() { active.runner.seal().map_err(|e| e.to_string())?; }
            self.update_run()?;
        }
        if !handoff_active && self.data.operations.len() >= 4096 && self.active.as_ref().unwrap().runner.state().pending().is_none() {
            self.active.as_mut().unwrap().runner.stop().map_err(|e| e.to_string())?;
            self.data.runs.get_mut(&id).unwrap().error = Some("本地 owner 记录容量已满；已停止新调度，未驱逐历史操作".into());
            self.update_run()?;
        }
        let incompatible_source = {
            let scheduler = self.active.as_ref().unwrap().runner.state();
            scheduler.pending().is_none() && scheduler.jobs().iter().any(|job|
                matches!(job.stage, lrt_local_workflow::scheduler::Stage::PrepareImport)
                    && !job.input.source_stat.iter().all(|part| !part.is_empty() && part.len() <= 20
                        && part.bytes().all(|byte| byte.is_ascii_digit()) && (part == "0" || !part.starts_with('0'))))
        };
        if incompatible_source && !handoff_active {
            self.active.as_mut().unwrap().runner.stop().map_err(|e| e.to_string())?;
            self.data.runs.get_mut(&id).unwrap().error = Some("来源时间戳不兼容真实导入协议；未派发导入，已停止接收新照片".into());
            self.update_run()?;
        }
        let command = match self.active.as_mut().unwrap().runner.step() {
            Ok(command) => command,
            Err(error) => {
                // A fresh-operation filesystem failure has no external owner
                // effect yet. If Stop can still be journaled, drain/release the
                // real lease; a poisoned journal instead fails that Stop too.
                self.active.as_mut().unwrap().runner.stop().map_err(|stop| format!("{error}; {stop}"))?;
                self.data.runs.get_mut(&id).unwrap().error = Some(format!("新操作未派发：{error}"));
                self.update_run()?;
                self.release_run(&id)?;
                return Ok(());
            }
        };
        if let Some(command) = command {
            if self.data.operations.contains_key(&command.identity.operation_id) { self.poll_operation(&command.identity.operation_id)?; }
            else if matches!(command.operation, CommandKind::QueryImport { .. } | CommandKind::QueryPreset { .. } | CommandKind::QueryExport { .. }) {
                return Err("原调度意图没有持久化 owner 传输记录；不能重新生成写入".into());
            } else {
                let mut envelope = match &command.operation {
                    CommandKind::PrepareImport { .. } | CommandKind::CommitImport { .. } => ingestion::envelope(&lease, &command)?,
                    _ => json!({"cmd":"workflow_owner","protocol":1,"action":"execute","request_id":storage::uuid()?,"session_id":lease.lease_id,"command":command}),
                };
                if matches!(command.operation, CommandKind::CommitImport { .. }) {
                    let graph = self.active.as_ref().unwrap().runner.state().graph();
                    let NodeKind::ManagedImport { managed_root, .. } = &graph.import().operation else { unreachable!() };
                    envelope["root"] = json!(managed_root);
                    envelope["root_identity"] = json!(self.data.runs[&id].managed_root_identity);
                }
                self.data.operations.insert(command.identity.operation_id.clone(), Operation { command, request: envelope.clone(), epoch: lease.epoch,
                    settled: false, last_receipt: None, query: None });
                self.update_run()?; // Core intent AND exact transport are durable.
                // A failed send is uncertain; retain the original operation and
                // let the next tick query its existing owner, never dispatch it again.
                if let Err(error) = self.send(envelope, lease.epoch) {
                    self.data.runs.get_mut(&id).unwrap().error = Some(error);
                    self.update_run()?;
                }
            }
        } else {
            let status = self.active.as_ref().unwrap().runner.state().status();
            if matches!(status, RunStatus::Stopped | RunStatus::Complete) { self.release_run(&id)?; }
        }
        Ok(())
    }
    fn poll_operation(&mut self, operation_id: &str) -> Result<(), String> {
        let original = self.data.operations.get(operation_id).ok_or("原操作记录丢失")?.clone();
        if original.settled { return Err("已完成 owner 操作仍被调度；拒绝重放".into()); }
        if transport::epoch(&self.state).ok() != Some(original.epoch) { return Err("原操作引擎已重启；不能恢复旧租约或推断效果已结束".into()); }
        let mut lease = self.data.lease.clone().ok_or("原操作租约丢失")?;
        let mut reply = self.read(&original.request)?;
        if let Some(query) = &original.query {
            let query_result = self.read(query)?;
            if query_result["phase"] == "done" {
                reply = query_result;
                self.data.operations.get_mut(operation_id).unwrap().query = None;
            }
        }
        let mut handoff_changed = false;
        if matches!(original.command.operation, CommandKind::PreflightPreset { .. } | CommandKind::ApplyPreset { .. })
            && reply["result"]["receipt"].is_object() {
            let value = reply["result"].get("handoff").ok_or("预设 owner 未提供实际交接状态；不能推断目标已返回")?;
            if !value.is_null() {
                if !review::handoff(value, &original.command) { return Err("预设 owner 交接身份或审核内容不匹配".into()); }
                let automatic = self.active.as_ref().ok_or("原运行不再活动")?.runner.state().graph().automatic();
                if (value["mode"] == "automatic") != automatic { return Err("预设交接模式与原图定义不匹配".into()); }
            }
            let run = self.data.runs.get_mut(&original.command.identity.run_id).ok_or("交接运行丢失")?;
            handoff_changed = run.handoff != *value;
            run.handoff = value.clone();
        }
        let receipt = if original.request["cmd"] == "ingest_session" {
            ingestion::map(&original, &mut lease, &reply).unwrap_or_else(|error| Receipt { schema_version: 1,
                identity: original.command.identity.clone(), result: ReceiptResult::Unknown { reason: error.chars().take(2048).collect() } })
        } else if reply["result"]["receipt"].is_object() {
            let receipt: Receipt = serde_json::from_value(reply["result"]["receipt"].clone()).map_err(|e| e.to_string())?;
            if receipt.identity != original.command.identity { return Err("owner 回执不属于原始精确操作".into()); }
            receipt
        } else if reply["result"]["status"] == "failed" && reply["result"]["dispatch_rejected"] == true {
            Receipt { schema_version: 1, identity: original.command.identity.clone(), result: ReceiptResult::Failed {
                code: "owner_dispatch_rejected".into(), message: reply["result"]["error"].as_str().unwrap_or("实际 owner 在任何派发前拒绝原请求").chars().take(2048).collect(), retained_document: None } }
        } else {
            Receipt { schema_version: 1, identity: original.command.identity.clone(), result:
                if reply["phase"] == "unknown" || matches!(reply["result"]["status"].as_str(), Some("failed" | "unknown")) {
                    ReceiptResult::Unknown { reason: "owner 尚未返回原操作的有效精确回执；只查询，不重发".into() }
                } else { ReceiptResult::Pending { owner_receipt_id: original.request["request_id"].as_str().unwrap_or(operation_id).into() } } }
        };
        let stop_import = original.request["cmd"] == "ingest_session"
            && matches!(receipt.result, ReceiptResult::Failed { .. } | ReceiptResult::Cancelled { .. });
        let changed = self.active.as_mut().ok_or("活动运行丢失")?.runner.record(receipt.clone()).map_err(|e| e.to_string())?;
        if stop_import {
            self.active.as_mut().unwrap().runner.stop().map_err(|e| e.to_string())?;
        }
        // A failed keep-continue result without retained-document proof still
        // leaves the reducer pending. Only the reducer decides settlement.
        let terminal = self.active.as_ref().unwrap().runner.state().pending().is_none();
        self.data.lease = Some(lease.clone());
        let row = self.data.operations.get_mut(operation_id).unwrap();
        row.last_receipt = Some(receipt); row.settled = terminal;
        if changed || terminal || stop_import || handoff_changed { self.update_run()?; }
        if !terminal && self.data.operations[operation_id].query.is_none()
            && !matches!(original.command.operation, CommandKind::PrepareImport { .. }) {
            let query = if original.request["cmd"] == "ingest_session" { ingestion::query(&lease, &original.request)? }
                else { json!({"cmd":"workflow_owner","protocol":1,"action":"query","request_id":storage::uuid()?,
                    "session_id":lease.lease_id,"original_request_id":original.request["request_id"],"operation_id":operation_id}) };
            self.data.operations.get_mut(operation_id).unwrap().query = Some(query.clone());
            // This is a read of the original identity, never another execute.
            let _ = self.send(query, original.epoch);
        }
        Ok(())
    }
    fn release_run(&mut self, id: &str) -> Result<(), String> {
        if !self.data.runs[id].handoff.is_null() || self.active.as_ref().unwrap().runner.state().pending().is_some() || self.data.operations.values().any(|op| !op.settled) { return Ok(()); }
        let lease = self.lease(&self.data.runs[id].lease_id)?;
        if let Some(external) = self.data.runs[id].release.clone() {
            let response = self.read(&external.request)?;
            let result = &response["result"];
            if response["phase"] == "done" && result["status"] == "succeeded" && result["session"].is_null()
                && result["released_session"]["session_id"] == lease.lease_id {
                let meta = self.data.runs.get_mut(id).unwrap(); meta.released = true; meta.release = None;
                self.data.lease = None;
                self.update_run()?;
                self.active = None;
            } else if response["phase"] == "unknown" || result["status"] == "unknown" {
                return Err("停止后的租约释放结果未知；效果仍未结清，禁止新运行".into());
            } else if result["status"] == "failed" { return Err(result["error"].as_str().unwrap_or("owner 拒绝释放原租约").into()); }
        } else {
            let request = json!({"cmd":"ingest_session","action":"release","request_id":storage::uuid()?,"session_id":lease.lease_id});
            self.data.runs.get_mut(id).unwrap().release = Some(UiExternal { phase: "release_run".into(), request: request.clone(), epoch: lease.epoch, query: None });
            self.update_run()?;
            if let Err(error) = self.send(request, lease.epoch) { self.data.runs.get_mut(id).unwrap().error = Some(error); self.update_run()?; }
        }
        Ok(())
    }
}
