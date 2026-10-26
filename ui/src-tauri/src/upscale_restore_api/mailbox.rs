// SPDX-License-Identifier: GPL-3.0-or-later
//! Engine-lifetime read leases and non-evicting exact write receipts.
use std::{collections::{HashMap, VecDeque}, sync::{Mutex, OnceLock}, time::{Duration, Instant}};
use serde_json::{json, Value};
use super::wire;

const STORE_BYTES: usize = 128 * 1024 * 1024;
const MAX_ROWS: usize = 256;
const MAX_WRITES: usize = 128;
const MAX_IDENTITIES: usize = 16_384;
const IDENTITY_BYTES: usize = 8 * 1024 * 1024;
const SESSION_TTL: Duration = Duration::from_secs(900);
const PREVIEW_TTL: Duration = Duration::from_secs(180);
struct Identity { epoch: [u8;16], signature: String }
struct Row {
    epoch: [u8;16], request: wire::Request, result: Value, terminal: bool, dispatched: bool,
    cancel_requested: bool, ingress_once: bool, redeemed: bool, retired: bool,
    reserved: usize, request_bytes: usize, source_proof: Option<Value>, expires: Option<Instant>,
}
impl Row {
    fn bytes(&self) -> usize { self.request_bytes.saturating_add(self.reserved) }
    fn imagery(&self) -> bool { self.result["context"].is_object() || self.result["review"].is_object() }
    fn evictable(&self) -> bool {
        // A write is retained whether known or unknown. Read/query cleanup can
        // never turn a known terminal into absence of proof or allow a replay.
        !self.request.write() && self.terminal && (!self.imagery() || self.redeemed || self.retired)
    }
}
struct Session { epoch: [u8;16], id: Value, owner: Value, proof: Value, expires: Instant }
#[derive(Default)]
pub(super) struct Mailbox {
    epoch: [u8;16], supported: bool, ended: bool, capability: Value,
    rows: VecDeque<Row>, seen: HashMap<String,Identity>, identity_bytes: usize, session: Option<Session>,
}
pub(super) fn store() -> &'static Mutex<Mailbox> {
    static STORE: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    static REAPER: OnceLock<bool> = OnceLock::new();
    let store = STORE.get_or_init(|| Mutex::new(Mailbox::default()));
    let running = *REAPER.get_or_init(|| std::thread::Builder::new().name("light-upscale-leases".into()).spawn(move || loop {
        std::thread::sleep(Duration::from_secs(15));
        if let Ok(mut host) = store.lock() { host.expire(Instant::now()); }
    }).is_ok());
    if !running {
        if let Ok(mut host) = store.lock() { host.supported = false; host.ended = true; host.capability = unavailable_capability(); }
    }
    store
}
pub(super) fn unavailable_capability() -> Value {
    json!({"version":wire::PROTOCOL,"operation_id":wire::OPERATION,"status":"unavailable",
        "reason":"配套引擎尚未声明已核验的 AI 超清运行条件；不使用占位或锐化替代", "model_id":"Swin2SR-classical-sr-x2-64","acceptance":"unrun","output_mode":"restore_native_dimensions"})
}
fn unavailable(id: &str) -> Value {
    json!({"event":wire::EVENT,"request_id":id,"status":"unknown","message":"原请求身份或回执未保留；不能认定未执行，也不会重新提交"})
}
fn reservation(action: &str) -> usize {
    match action { "current" => wire::CONTEXT_BYTES, "preview" => wire::RESULT_BYTES, _ => wire::SMALL_BYTES }
}
fn source_proof(context: &Value) -> Value {
    json!({"before":{"sha256":context["before"]["sha256"],"width":context["before"]["width"],"height":context["before"]["height"]},
        "source_evidence":context["source_evidence"]})
}
impl Mailbox {
    fn expire(&mut self, now: Instant) {
        if self.session.as_ref().is_some_and(|s| now >= s.expires) { self.session = None; }
        for row in &mut self.rows {
            if row.terminal && row.imagery() && row.expires.is_some_and(|end| now >= end) {
                row.result = wire::rejected(&row.request, "只读图像租约已过期；原请求不会重跑。请明确重新读取当前照片或生成新对比");
                row.source_proof = None; row.retired = true; row.expires = None; row.reserved = wire::SMALL_BYTES;
            }
        }
    }
    pub fn status(&mut self, id: &str) -> Value {
        self.expire(Instant::now());
        self.rows.iter().find(|r| r.request.id == id).map(|r| r.result.clone()).unwrap_or_else(|| unavailable(id))
    }
    pub fn replay(&self, req: &wire::Request) -> Result<bool,String> {
        match self.seen.get(&req.id) {
            None => Ok(false), Some(old) if old.signature == req.signature => Ok(true),
            Some(_) => Err("AI 超清请求身份已绑定其他完整原始内容，未重新提交".into()),
        }
    }
    pub fn reset(&mut self, epoch: [u8;16]) {
        self.end(self.epoch); self.epoch = epoch; self.supported = false; self.ended = false; self.capability = unavailable_capability();
    }
    pub fn ready(&mut self, epoch: [u8;16], capability: &Value) {
        if self.epoch == epoch && !self.ended {
            // Protocol support is distinct from current model readiness. A current read rechecks the installed runtime.
            self.supported = wire::capability(capability);
            self.capability = if wire::capability(capability) { capability.clone() } else { unavailable_capability() };
        }
    }
    pub fn capability(&self, epoch: Option<[u8;16]>) -> Value {
        if epoch == Some(self.epoch) && !self.ended && wire::capability(&self.capability) { self.capability.clone() }
        else { unavailable_capability() }
    }
    pub fn end(&mut self, epoch: [u8;16]) {
        if self.session.as_ref().is_some_and(|s| s.epoch == epoch) { self.session = None; }
        for row in self.rows.iter_mut().filter(|r| r.epoch == epoch) {
            if row.request.read() && (!row.terminal || row.imagery()) {
                row.result = wire::rejected(&row.request, "原引擎的只读图像租约已失效；没有据此修改照片，也不表示强制停止了计算");
                row.terminal = true; row.retired = true; row.source_proof = None; row.expires = None; row.reserved = wire::SMALL_BYTES;
            } else if !row.terminal {
                row.result = wire::pending(&row.request, "unknown", "原引擎结束前未收到确定回执；原写入结果未知，只能核对，不能重发");
                // Queries may retire, original writes may not. A late validated
                // original terminal from draining stdout may still settle it.
                if row.request.action == "receipt" { row.terminal = true; }
            }
        }
        if self.epoch == epoch { self.ended = true; self.supported = false; }
    }
    fn make_room(&mut self, additional: usize) -> Result<(),String> {
        self.expire(Instant::now());
        while self.rows.len() >= MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(additional) > STORE_BYTES {
            let Some(index) = self.rows.iter().position(Row::evictable) else {
                return Err("AI 超清回执容量已满；未提交新操作，请先核对原请求或等待只读租约释放".into());
            };
            self.rows.remove(index);
        }
        Ok(())
    }
    fn admission(&self, epoch: [u8;16], req: &wire::Request) -> Result<Option<Value>,String> {
        if epoch == [0;16] || self.epoch != epoch || self.ended || !self.supported {
            return Err("原引擎不可用或未声明匹配的AI 超清原生能力；未执行".into());
        }
        if req.action == "receipt" {
            let Some(original) = self.rows.iter().find(|r| r.epoch == epoch && r.request.write() && r.request.id == req.inner()["request_id"]) else {
                return Err("当前引擎未保留该原写入；不会向另一个引擎猜测或重发".into());
            };
            if !wire::same(original.request.inner(), req.inner()) { return Err("查询内容与保留的原写入不完全一致".into()); }
            return Ok(None);
        }
        if self.rows.iter().any(|r| r.request.write() && !r.terminal) {
            return Err("上一AI 超清写入或取消尚未确认；只可查询原请求，切换引擎也不授予重发权限".into());
        }
        if req.read() && self.rows.iter().any(|r| r.epoch == epoch && r.request.read() && !r.terminal) {
            return Err("已有当前来源读取或预览正在运行；请等待原请求终态或请求停止它".into());
        }
        if req.action == "current" { return Ok(None); }
        let session = self.session.as_ref().filter(|s| s.epoch == epoch && s.id == req.inner()["session_id"]
            && wire::same(&s.owner, &req.inner()["owner"])).ok_or("缺少完全匹配的原文档身份及有效来源会话租约")?;
        if req.action == "preview" && self.capability["model_id"] != req.inner()["recipe"]["model_id"] {
            return Err("原生AI 超清模块没有声明该模型，不会换用另一种效果".into());
        }
        if req.apply() && !self.rows.iter().any(|r| r.epoch == epoch && r.terminal && !r.retired && !r.redeemed
            && r.request.action == "preview" && wire::apply_matches(req, &r.result["review"])) {
            return Err("缺少本引擎未消费且来源、配方、完整输出与两张真实图像哈希全部匹配的预览".into());
        }
        if req.write() && req.inner()["action"] == "cancel" && !req.inner()["token"].is_null()
            && !self.rows.iter().any(|r| r.epoch == epoch && r.request.action == "preview" && !r.retired
                && r.result["review"]["token"] == req.inner()["token"] && r.result["review"]["session_id"] == session.id
                && wire::same(&r.result["review"]["owner"], &session.owner)) {
            return Err("取消令牌不属于当前保留会话，未发送猜测性取消".into());
        }
        Ok(Some(session.proof.clone()))
    }
    pub fn begin(&mut self, epoch: [u8;16], req: wire::Request) -> Result<bool,String> {
        self.expire(Instant::now());
        if self.replay(&req)? { return Ok(false); }
        let identity_bytes = req.id.len() + req.signature.len() + 64;
        if self.seen.len() >= MAX_IDENTITIES || self.identity_bytes.saturating_add(identity_bytes) > IDENTITY_BYTES {
            return Err("AI 超清防重放身份容量已满；未提交。释放图像不会删除旧身份".into());
        }
        if req.write() && self.rows.iter().filter(|r| r.request.write()).count() >= MAX_WRITES {
            return Err("AI 超清写入回执容量已满；未发送新操作，旧写入证明不会被清理".into());
        }
        let proof = self.admission(epoch, &req);
        let request_bytes = wire::size(&req.envelope, wire::COMMAND_BYTES)?;
        let reserved = if proof.is_ok() { reservation(&req.action) } else { wire::SMALL_BYTES };
        self.make_room(request_bytes + reserved)?;
        if req.apply() && proof.is_ok() {
            let Some(preview) = self.rows.iter_mut().find(|r| r.epoch == epoch && !r.retired && !r.redeemed
                && r.request.action == "preview" && wire::apply_matches(&req, &r.result["review"])) else {
                return Err("原预览租约已失效，未提交新副本".into());
            };
            preview.redeemed = true; // Consume before queue/write/flush uncertainty.
        }
        let dispatch = proof.is_ok();
        let result = match &proof {
            Ok(_) => wire::pending(&req, "pending", "原AI 超清请求已登记，等待真实宿主回执"),
            Err(why) => wire::rejected(&req, why),
        };
        if dispatch && req.action == "current" { self.session = None; }
        if dispatch && req.read() {
            for row in self.rows.iter_mut().filter(|r| r.epoch == epoch && r.request.action == "preview") { row.redeemed = true; }
        }
        self.identity_bytes += identity_bytes;
        self.seen.insert(req.id.clone(), Identity { epoch, signature: req.signature.clone() });
        self.rows.push_back(Row { epoch, request: req, result, terminal: !dispatch, dispatched: false, cancel_requested: false,
            ingress_once: false, redeemed: false, retired: false, reserved, request_bytes, source_proof: proof.ok().flatten(), expires: None });
        Ok(dispatch)
    }
    pub fn unknown(&mut self, epoch: [u8;16], id: &str, why: &str) {
        if let Some(row) = self.rows.iter_mut().find(|r| r.epoch == epoch && r.request.id == id && !r.terminal) {
            row.result = wire::pending(&row.request, "unknown", why);
        }
    }
    pub fn malformed(&mut self, epoch: [u8;16]) {
        for row in self.rows.iter_mut().filter(|r| r.epoch == epoch && r.dispatched && !r.terminal) {
            row.result = wire::pending(&row.request, "unknown", "宿主原始 JSON 重复、超限或无效；原请求结果仍未知，不会自动重发");
        }
    }
    pub fn guards_result(&self, epoch: [u8;16], id: &str) -> bool {
        self.seen.get(id).is_some_and(|s| s.epoch == epoch)
    }
    pub fn begin_enqueue(&mut self, epoch: [u8;16], command: &Value) -> Result<(),String> {
        if self.epoch != epoch || self.ended || !self.supported { return Err("原AI 超清引擎已结束或协议已失效，未重新提交".into()); }
        let row = self.rows.iter_mut().find(|r| r.epoch == epoch && command["request_id"] == r.request.id).ok_or("AI 超清命令没有原生登记")?;
        if row.terminal || row.dispatched || !wire::same(command, &row.request.envelope) { return Err("AI 超清原请求已发送或内容变化，不会重发".into()); }
        row.dispatched = true; row.ingress_once = true;
        Ok(())
    }
    pub fn finish_enqueue(&mut self, epoch: [u8;16], id: &str) {
        if let Some(row) = self.rows.iter_mut().find(|r| r.epoch == epoch && r.request.id == id) { row.ingress_once = false; }
    }
    pub fn ingress(&mut self, epoch: [u8;16], command: &Value) -> Result<(),String> {
        let mut admitted = false;
        if command["cmd"] == "upscale_restore" {
            let row = self.rows.iter_mut().find(|r| r.epoch == epoch && command["request_id"] == r.request.id)
                .ok_or("AI 超清原请求未经过专用登记，禁止旁路提交")?;
            if !row.dispatched || !row.ingress_once || row.terminal || !wire::same(command, &row.request.envelope) {
                return Err("AI 超清原请求单次入口已使用或内容变化，不能从普通或交互入口重发".into());
            }
            row.ingress_once = false; admitted = true;
        }
        if !self.rows.iter().any(|r| r.request.write() && !r.terminal) { return Ok(()); }
        if admitted || matches!(command["cmd"].as_str(), Some("hello"|"shutdown")) { return Ok(()); }
        Err("AI 超清原写入尚未确认；只可查询原请求，不能继续编辑、撤销、保存或导出".into())
    }
    pub fn request_cancel(&mut self, epoch: [u8;16], id: &str) -> Result<(Value,Option<Value>),String> {
        let row = self.rows.iter_mut().find(|r| r.epoch == epoch && r.request.id == id).ok_or("该读取不属于当前引擎，未发送盲目取消")?;
        if !row.request.read() { return Err("此控制只能停止原读取或预览，不能中断 apply、伪造取消或撤销新图".into()); }
        if row.terminal { return Ok((json!({"requested":false,"request_id":id,"message":"原请求已有终态，请读取原回执"}), None)); }
        if !row.dispatched { return Err("原读取未进入引擎，不能发送脱离原工作的取消".into()); }
        let ack = json!({"requested":true,"request_id":id,"message":"已请求停止原读取，仍须等待原请求实际终态"});
        if row.cancel_requested { return Ok((ack, None)); }
        row.cancel_requested = true;
        row.result = wire::pending(&row.request, "unknown", "已请求停止原读取；接受请求不代表已取消，必须等待实际终态");
        Ok((ack, Some(row.request.envelope.clone())))
    }
    pub fn observe(&mut self, epoch: [u8;16], value: &Value) -> Option<Value> {
        self.expire(Instant::now());
        if value["event"] != wire::EVENT { return None; }
        let id = value["request_id"].as_str()?;
        let index = self.rows.iter().position(|r| r.epoch == epoch && r.request.id == id)?;
        let row = &self.rows[index];
        if row.terminal || !row.dispatched { return None; }
        let same_source = row.request.action != "preview" || value["status"] != "ready"
            || row.source_proof.as_ref().is_some_and(|proof| wire::same(proof, &source_proof(&value["review"])));
        let consistent_capability = row.request.action != "current" || value["status"] != "ready"
            || wire::capability(&value["context"]["capability"]);
        let consistent_terminal = row.request.action != "receipt" || self.rows.iter().find(|r| r.epoch == epoch && r.request.write()
            && r.request.id == row.request.inner()["request_id"] && wire::same(r.request.inner(), row.request.inner()))
            .is_some_and(|original| !original.terminal || wire::same(&original.result["receipt"], &value["receipt"]));
        let bytes = wire::size(value, reservation(&row.request.action));
        if bytes.is_err() || !wire::valid_result(value, &row.request) || !same_source || !consistent_capability || !consistent_terminal {
            self.unknown(epoch, id, "宿主回执字段、来源证据、图像字节哈希或原身份不匹配；不能据此确认写入或取消");
            return None;
        }
        let terminal = wire::terminal(value);
        if !terminal && value["receipt"]["phase"] == "pending" && row.result["receipt"]["phase"] == "unknown" { return None; }
        let action = row.request.action.clone();
        let is_write = row.request.write();
        let inner = row.request.inner().clone();
        if terminal && value["context"].is_object() && epoch == self.epoch && !self.ended {
            let context = &value["context"];
            // Only a fully validated, matched current-source reply can refresh runtime readiness.
            self.capability = context["capability"].clone();
            self.session = Some(Session { epoch, id: context["session_id"].clone(), owner: context["owner"].clone(),
                proof: source_proof(context), expires: Instant::now() + SESSION_TTL });
        }
        let expiry = self.session.as_ref().filter(|s| s.epoch == epoch).map(|s| s.expires);
        let image_expiry = if action == "preview" { Some(expiry.map_or(Instant::now(), |end| end.min(Instant::now() + PREVIEW_TTL))) } else { expiry };
        let row = &mut self.rows[index]; row.result = value.clone(); row.terminal = terminal || action == "receipt";
        if row.terminal {
            row.reserved = bytes.ok()?; row.source_proof = None; row.expires = if row.imagery() { image_expiry } else { None };
        }
        let mut settled = None;
        if action == "receipt" {
            if let Some(original) = self.rows.iter_mut().find(|r| r.epoch == epoch && r.request.write() && r.request.id == inner["request_id"]
                && wire::same(r.request.inner(), &inner) && !r.terminal) {
                let receipt = &value["receipt"];
                if receipt["phase"] != "pending" || original.result["receipt"]["phase"] != "unknown" {
                    original.result = json!({"event":wire::EVENT,"request_id":original.request.id,"status":"ready","receipt":receipt});
                    original.terminal = terminal;
                    if terminal { original.reserved = wire::SMALL_BYTES; original.source_proof = None; }
                }
                if terminal { settled = Some(original.request.id.clone()); }
            }
        } else if terminal && is_write { settled = Some(id.to_owned()); }
        if terminal && matches!(action.as_str(), "submit"|"receipt") && matches!(value["receipt"]["outcome"].as_str(), Some("applied"|"cancelled")) {
            if self.session.as_ref().is_some_and(|s| s.epoch == epoch && s.id == inner["session_id"] && wire::same(&s.owner, &inner["owner"])) { self.session = None; }
            for row in self.rows.iter_mut().filter(|r| r.epoch == epoch && r.imagery()) { row.expires = Some(Instant::now()); }
            self.expire(Instant::now());
        }
        // An internal recovery-fence marker only, never a substitute user-facing
        // receipt, invented history entry, render, or publication success flag.
        settled.map(|original| json!({"event":wire::EVENT,"request_id":original,"phase":"done","outcome_unknown":false}))
    }
}

#[cfg(test)]
#[path = "tests_unrun.rs"]
mod tests;
