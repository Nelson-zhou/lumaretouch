// SPDX-License-Identifier: GPL-3.0-or-later
//! Same-engine-epoch, bounded, replay-safe expression receipt mailbox.
//! The engine owns immutable images, new-copy publication and undo. This module
//! never simulates a render, commits a document, or creates a second undo stack.
use std::{collections::{HashMap, VecDeque}, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::{engine::EngineHandle, expression_replacement_protocol as wire, AppState};

const STORE_BYTES: usize = 128 * 1024 * 1024;
const MAX_ROWS: usize = 64;
const TOMBSTONE_BYTES: usize = 8 * 1024 * 1024;
const MAX_TOMBSTONES: usize = 16_384;
struct Tombstone { epoch: [u8;16], signature: String }
struct Row {
    epoch: [u8;16], request: wire::Request, result: Value, terminal: bool,
    dispatched: bool, cancel_requested: bool, request_bytes: usize, reserved: usize,
    before: Option<Value>, redeemed: bool, released: bool, retired_read: bool,
}
impl Row {
    fn evictable(&self) -> bool {
        self.retired_read || self.terminal && (wire::phase(&self.result) != "ready" || self.redeemed || self.released)
    }
    fn bytes(&self) -> usize { self.request_bytes.saturating_add(self.reserved) }
}
#[derive(Default)]
struct Mailbox {
    epoch: [u8;16], supported: bool, ended: bool,
    rows: VecDeque<Row>, seen: HashMap<String,Tombstone>, tombstone_bytes: usize,
}
fn mailbox() -> &'static Mutex<Mailbox> {
    static STORE: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    STORE.get_or_init(|| Mutex::new(Mailbox::default()))
}
fn unavailable(id: &str) -> Value {
    json!({"event":wire::EVENT,"request_id":id,"phase":"unknown",
        "message":"原请求回执未保留或身份不存在；不能据此认定未执行，不会重新提交"})
}
fn reservation(action: &str) -> usize {
    match action { "preview" => wire::RESULT_BYTES, "current" | "choose_donor" => wire::PHOTO_BYTES, _ => 32 * 1024 }
}
impl Mailbox {
    fn status(&self, id: &str) -> Value {
        self.rows.iter().find(|r| r.request.id == id).map(|r| r.result.clone()).unwrap_or_else(|| unavailable(id))
    }
    fn replay(&self, req: &wire::Request) -> Result<bool,String> {
        match self.seen.get(&req.id) {
            None => Ok(false), Some(old) if old.signature == req.signature => Ok(true),
            Some(_) => Err("表情替换请求身份已绑定其他原始内容或供体路径，未重新提交".into()),
        }
    }
    fn end(&mut self, epoch: [u8;16]) {
        for row in self.rows.iter_mut().filter(|r| r.epoch == epoch && r.request.action != "apply"
            && (!r.terminal || matches!(wire::phase(&r.result),"ready"|"current_ready"|"donor_ready"))) {
            // Engine-owned pixel leases no longer exist in this epoch. Keep
            // request tombstones, not permanently pinned old read imagery.
            row.retired_read = true; row.terminal = true; row.before = None; row.reserved = 32 * 1024;
            row.result = wire::rejected(&row.request,"原引擎的只读结果租约已失效，未修改照片；这不表示强制停止了计算。请在新引擎明确重新读取");
        }
        for row in self.rows.iter_mut().filter(|r| r.epoch == epoch && r.request.action == "apply" && !r.terminal) {
            row.result = wire::pending(&row.request,"unknown","引擎结束前未确认原请求；结果未知，不会自动重试或认定没有写入");
            // Keep the original response reservation: draining stdout can still
            // establish a genuine original terminal outcome after EOF.
        }
        if self.epoch == epoch { self.supported = false; self.ended = true; }
    }
    fn make_room(&mut self, additional: usize) -> Result<(),String> {
        while self.rows.len() >= MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(additional) > STORE_BYTES {
            let Some(index) = self.rows.iter().position(Row::evictable) else {
                return Err("表情替换回执安全容量已满；请核对原请求或释放已完成预览，未提交新操作".into());
            };
            self.rows.remove(index);
        }
        Ok(())
    }
    fn preview_origin(&self, epoch: [u8;16], req: &wire::Request) -> Result<Option<Value>,String> {
        if req.action != "preview" { return Ok(None); }
        let cmd = &req.packet.as_ref().ok_or("缺少预览命令")?.command;
        let source_photo = self.rows.iter().rev().filter(|r| r.epoch == epoch && wire::phase(&r.result) == "current_ready")
            .find(|r| wire::same(&r.result["current"]["binding"],&cmd["binding"]) && r.result["current"]["available"] == true
                && r.result["current"]["photo"]["faces"].as_array().is_some_and(|faces| faces.iter().any(|f| wire::same(f,&cmd["target"]["face"]))));
        let Some(source_photo) = source_photo else { return Err("未找到本引擎中完全匹配的当前照片与真实人脸证据；请重新读取当前照片".into()); };
        let donor = self.rows.iter().any(|r| r.epoch == epoch && wire::phase(&r.result) == "donor_ready"
            && wire::same(&r.result["receipt"]["photo"]["source"],&cmd["donor"]["source"])
            && r.result["receipt"]["photo"]["faces"].as_array().is_some_and(|faces| faces.iter().any(|f| wire::same(f,&cmd["donor"]["face"]))));
        if !donor { return Err("未找到本引擎中完全匹配的供体原图与真实人脸证据；请重新选择供体".into()); }
        let image = &source_photo.result["current"]["photo"]["image"];
        Ok(Some(json!({"sha256":image["sha256"],"width":image["width"],"height":image["height"]})))
    }
    fn admission(&self, epoch: [u8;16], req: &wire::Request) -> Result<Option<Value>,String> {
        if epoch == [0;16] || self.epoch != epoch || !self.supported || self.ended { return Err("引擎未声明匹配的表情替换协议，或引擎已变化；未提交".into()); }
        if req.action == "apply" {
            let found = self.rows.iter().any(|r| r.epoch == epoch && !r.redeemed && !r.released && wire::apply_matches(req,&r.request,&r.result));
            if !found { return Err("没有本引擎中未消费且三图证据完全匹配的预览；未创建新副本".into()); }
            if self.rows.iter().any(|r| r.epoch == epoch && r.request.action == "apply" && !r.terminal) {
                return Err("之前的新副本请求尚未确认，不能再次写入或撤销".into());
            }
        }
        if req.action == "release" {
            let token = &req.envelope["preview_token"];
            if self.rows.iter().any(|r| r.epoch == epoch && r.request.action == "apply" && !r.terminal
                && r.request.packet.as_ref().is_some_and(|p| &p.command["preview_token"] == token)) {
                return Err("新副本结果尚未确认，不能释放其原预览证据".into());
            }
            if !self.rows.iter().any(|r| r.epoch == epoch && wire::phase(&r.result) == "ready" && &r.result["receipt"]["preview"]["preview_token"] == token) {
                return Err("未找到本引擎持有的预览令牌；未向其他引擎发送释放命令".into());
            }
        }
        self.preview_origin(epoch,req)
    }
    fn begin(&mut self, epoch: [u8;16], req: wire::Request) -> Result<bool,String> {
        if self.replay(&req)? { return Ok(false); }
        let tombstone_size = req.id.len() + req.signature.len() + 64;
        if self.seen.len() >= MAX_TOMBSTONES || self.tombstone_bytes.saturating_add(tombstone_size) > TOMBSTONE_BYTES {
            return Err("表情替换防重放身份记录已满；未提交。旧身份不会因释放预览而被删除".into());
        }
        let proof = self.admission(epoch,&req);
        let request_bytes = wire::size(&req.envelope,wire::COMMAND_BYTES * 3)?;
        let reserve = if proof.is_ok() { reservation(&req.action) } else { 32*1024 };
        self.make_room(request_bytes + reserve)?;
        // Mark the preview consumed before queue admission. Even an uncertain
        // send may have executed: its token cannot authorize a second copy.
        if req.action == "apply" && proof.is_ok() {
            if let Some(preview) = self.rows.iter_mut().find(|r| r.epoch == epoch && !r.redeemed && !r.released && wire::apply_matches(&req,&r.request,&r.result)) { preview.redeemed = true; }
            else { return Err("预览在容量整理时已失效，未提交新副本".into()); }
        }
        let terminal = proof.is_err();
        let result = match &proof { Ok(_) => wire::pending(&req,"pending","原请求已登记，等待宿主终态回执"), Err(why) => wire::rejected(&req,why) };
        self.tombstone_bytes += tombstone_size;
        self.seen.insert(req.id.clone(),Tombstone { epoch, signature:req.signature.clone() });
        self.rows.push_back(Row { epoch, request:req, result, terminal, dispatched:false, cancel_requested:false,
            request_bytes, reserved:reserve, before:proof.ok().flatten(), redeemed:false, released:false, retired_read:false });
        Ok(!terminal)
    }
    fn unknown(&mut self, epoch: [u8;16], id: &str, why: &str) {
        if let Some(row) = self.rows.iter_mut().find(|r| r.epoch == epoch && r.request.id == id && !r.terminal) {
            row.result = wire::pending(&row.request,"unknown",why);
        }
    }
    fn observe(&mut self, epoch: [u8;16], value: &Value) -> Option<Value> {
        let id = value["request_id"].as_str()?;
        let index = self.rows.iter().position(|r| r.epoch == epoch && r.request.id == id)?;
        let row = &self.rows[index];
        // The first validated terminal is immutable. Duplicate, late, stale or
        // contradictory receipts cannot replace it or settle another request.
        if row.terminal || !row.dispatched { return None; }
        let before_matches = wire::phase(value) != "ready" || row.before.as_ref().is_some_and(|expected|
            ["sha256","width","height"].iter().all(|key| wire::same(&expected[*key],&value["receipt"]["preview"]["before"][*key])));
        let bytes = wire::size(value,reservation(&row.request.action));
        if bytes.is_err() || !wire::valid_result(value,&row.request) || !before_matches {
            self.unknown(epoch,id,"宿主回执字段、原始身份或完整三图证据不匹配；实际结果待核对，不会自动重试");
            return None;
        }
        let terminal = wire::terminal(value);
        // A pending update must not erase a cancellation/uncertainty notice.
        if !terminal && wire::phase(value) == "pending" && matches!(wire::phase(&row.result),"unknown"|"cancelling") { return None; }
        let action = row.request.action.clone();
        let token = row.request.envelope["preview_token"].clone();
        let row = &mut self.rows[index];
        row.result = value.clone(); row.terminal = terminal;
        if terminal { row.reserved = bytes.ok()?; }
        if terminal && action == "release" && wire::phase(value) == "released" {
            for preview in self.rows.iter_mut().filter(|r| r.epoch == epoch && wire::phase(&r.result) == "ready" && r.result["receipt"]["preview"]["preview_token"] == token) { preview.released = true; }
        }
        // This normalization is internal recovery evidence, NOT the UI result.
        // It is produced only after original request/binding/hash/proof checks.
        if terminal && action == "apply" {
            Some(json!({"event":wire::EVENT,"request_id":id,"phase":wire::phase(value),"outcome_unknown":false}))
        } else { None }
    }
}

pub(crate) fn reset(epoch: [u8;16]) {
    if let Ok(mut host) = mailbox().lock() { let old = host.epoch; host.end(old); host.epoch = epoch; host.supported = false; host.ended = false; }
}
pub(crate) fn ready(epoch: [u8;16], supported: bool) {
    if let Ok(mut host) = mailbox().lock() { if host.epoch == epoch && !host.ended { host.supported = supported; } }
}
pub(crate) fn ended(epoch: [u8;16]) { if let Ok(mut host) = mailbox().lock() { host.end(epoch); } }
/// Call on the RAW engine line, before the generic recovery observer. Parsing a
/// Value first loses duplicate-field evidence. A parse failure cannot settle.
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    let value = match wire::unique_json(line,wire::RESULT_BYTES) {
        Ok(value) => value,
        Err(_) => {
            // Duplicate IDs cannot be trusted even to select an original row.
            // Keep every outstanding row unsettled, and surface uncertainty.
            if let Ok(mut host) = mailbox().lock() {
                for row in host.rows.iter_mut().filter(|r| r.epoch == epoch && r.dispatched && !r.terminal) {
                    row.result = wire::pending(&row.request,"unknown","宿主回执包含重复字段、非法 JSON 或超限内容；原请求结果未知");
                }
            }
            return None;
        },
    };
    mailbox().lock().ok()?.observe(epoch,&value)
}
/// Trusted in-process callers only. Engine stdout must use observe_line.
pub(crate) fn observe(epoch: [u8;16], value: &Value) -> Option<Value> {
    mailbox().lock().ok()?.observe(epoch,value)
}
/// Includes terminal tombstones: a contradictory late event must never bypass
/// this domain's receipt validator and settle a generic recovery fence.
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox().lock().map(|host| host.seen.get(id).is_some_and(|r| r.epoch == epoch)).unwrap_or(true)
}
pub(crate) fn read_only(value: &Value) -> bool {
    value["cmd"] == "expression_replacement" && matches!(value["action"].as_str(),Some("current"|"choose_donor"|"preview"|"release"))
}
/// Consult for BOTH ordinary and interactive EngineHandle ingress. A pending or
/// unknown write is not cleared by cancellation, timeouts, navigation, malformed
/// events, terminal read receipts, or an attempted undo/save/export.
pub(crate) fn blocks_mutation(epoch: [u8;16], command: &Value) -> Result<(),String> {
    let host = mailbox().lock().map_err(|_| "表情替换写入屏障锁不可用")?;
    let Some(pending) = host.rows.iter().find(|r| r.epoch == epoch && r.request.action == "apply" && !r.terminal) else { return Ok(()); };
    if read_only(command) || matches!(command["cmd"].as_str(),Some("shutdown"|"hello")) { return Ok(()); }
    if command["cmd"] == "expression_replacement" && command["action"] == "apply" && command["request_id"] == pending.request.id
        && pending.dispatched && wire::same(command,&pending.request.envelope) { return Ok(()); }
    Err("表情替换新副本请求尚未确认；请查询原请求，暂不允许继续写入、撤销、保存或导出".into())
}
/// Shared native dispatch calls this once; host_epoch never crosses the wire.
pub(crate) fn enqueue(handle: &EngineHandle, mut command: Value) -> Result<(),String> {
    let epoch = command.as_object_mut().ok_or("表情替换命令无效")?.remove("host_epoch").ok_or("表情替换缺少原生引擎身份")?;
    if epoch.as_str() != Some(crate::frame_identity::hex(handle.epoch()).as_str()) { return Err("引擎已变化，未向新引擎重发原请求".into()); }
    let id = command["request_id"].as_str().ok_or("表情替换请求身份缺失")?.to_owned();
    {
        let mut host = mailbox().lock().map_err(|_| "表情替换回执锁不可用")?;
        if host.epoch != handle.epoch() || host.ended || !host.supported || !handle.is_alive() {
            return Err("原表情替换引擎已结束或协议不再有效，未向新引擎重发".into());
        }
        let row = host.rows.iter_mut().find(|r| r.epoch == handle.epoch() && r.request.id == id).ok_or("表情替换命令没有原生登记")?;
        if row.terminal || row.dispatched || !wire::same(&command,&row.request.envelope) { return Err("表情替换原请求已提交或内容已变化，不会重发".into()); }
        row.dispatched = true;
    }
    handle.send(command)
}

#[tauri::command]
pub(crate) fn expression_replacement_capability(state: State<'_,Arc<AppState>>) -> Result<Value,String> {
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let host = mailbox().lock().map_err(|_| "表情替换回执锁不可用")?;
    let available = engine.as_ref().is_some_and(|h| h.is_alive() && h.epoch() == host.epoch) && host.supported && !host.ended;
    Ok(json!({"protocol":1,"operation_id":wire::OPERATION,"available":available,
        "reason":if available { Value::Null } else { json!("配套引擎未声明表情替换协议，或引擎暂不可用") }}))
}
#[tauri::command]
pub(crate) fn expression_replacement_request(state: State<'_,Arc<AppState>>, request: Value) -> Result<Value,String> {
    let req = wire::parse_request(&request)?;
    let id = req.id.clone(); let action = req.action.clone();
    // Do not acquire the engine mutex while holding the mailbox mutex.
    { let host = mailbox().lock().map_err(|_| "表情替换回执锁不可用")?; if host.replay(&req)? { return Ok(host.status(&id)); } }
    let handle = state.engine.lock().map_err(|_| "引擎锁不可用")?.clone();
    let epoch = handle.as_ref().map(|h| h.epoch()).unwrap_or([0;16]);
    let dispatch = mailbox().lock().map_err(|_| "表情替换回执锁不可用")?.begin(epoch,req)?;
    if dispatch {
        let mut command = request;
        command["host_epoch"] = json!(crate::frame_identity::hex(epoch));
        let sent = if action == "apply" { state.send_to_engine(command) }
            else { handle.as_ref().ok_or_else(|| "引擎未运行".to_string()).and_then(|h| enqueue(h,command)) };
        if let Err(error) = sent {
            // A write/flush/queue error is not proof of no execution. Keeping
            // the original reserved row prevents unsafe automatic re-dispatch.
            let why = format!("原请求发送未获确认：{}；不会自动重发",error.chars().take(1024).collect::<String>());
            mailbox().lock().map_err(|_| "表情替换回执锁不可用")?.unknown(epoch,&id,&why);
        }
    }
    Ok(mailbox().lock().map_err(|_| "表情替换回执锁不可用")?.status(&id))
}
#[tauri::command]
pub(crate) fn expression_replacement_status(_state: State<'_,Arc<AppState>>, request_id: String) -> Result<Value,String> {
    if !wire::id(&json!(request_id)) { return Err("表情替换请求身份无效".into()); }
    Ok(mailbox().lock().map_err(|_| "表情替换回执锁不可用")?.status(&request_id))
}
#[tauri::command]
pub(crate) fn expression_replacement_cancel(state: State<'_,Arc<AppState>>, request_id: String, command_sha256: String) -> Result<Value,String> {
    if !wire::id(&json!(request_id)) || !wire::hash(&json!(command_sha256)) { return Err("取消请求身份或摘要无效".into()); }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let handle = engine.as_ref().filter(|h| h.is_alive()).ok_or("原引擎不可用，未确认取消")?;
    let epoch = handle.epoch();
    {
        let mut host = mailbox().lock().map_err(|_| "表情替换回执锁不可用")?;
        let row = host.rows.iter_mut().find(|r| r.request.id == request_id && r.epoch == epoch).ok_or("原请求不属于当前引擎，不能盲目取消")?;
        if row.request.command_sha256 != command_sha256 || !matches!(row.request.action.as_str(),"current"|"choose_donor"|"preview") { return Err("取消仅适用于原身份和摘要完全匹配的读取或预览，不能取消 apply".into()); }
        if row.terminal { return Ok(json!({"requested":false,"request_id":request_id,"command_sha256":command_sha256,"message":"原请求已有终态，请读取原回执"})); }
        if !row.dispatched { return Err("原请求尚未进入引擎，不能发送脱离原工作的取消命令".into()); }
        if row.cancel_requested { return Ok(json!({"requested":true,"request_id":request_id,"command_sha256":command_sha256})); }
        // Set before ingress, so repeated clicks never create another cancel
        // write. A failed/uncertain ingress remains unknown until original end.
        row.cancel_requested = true;
        row.result = wire::pending(&row.request,"cancelling","已请求停止原读取或预览，仍需等待原请求终态；不代表已取消");
    }
    if let Err(error) = handle.cancel_expression_replacement(&request_id,&command_sha256) {
        mailbox().lock().map_err(|_| "表情替换回执锁不可用")?.unknown(epoch,&request_id,"取消控制消息未获确认；仍需等待原请求终态，不能认定已停止");
        return Err(error);
    }
    Ok(json!({"requested":true,"request_id":request_id,"command_sha256":command_sha256}))
}

#[cfg(test)]
mod mailbox_unrun {
    use super::*;
    // AUTHORED / UNRUN. These are source contracts, not runtime evidence.
    #[test] fn rejected_first_terminal_is_immutable_and_original_is_not_replayed() {
        let req = wire::parse_request(&json!({"cmd":"expression_replacement","action":"current","request_id":"current-fixture"})).unwrap();
        let mut host = Mailbox::default();
        assert!(!host.begin([1;16],req.clone()).unwrap());
        let original = host.status(&req.id);
        assert!(!host.begin([2;16],req.clone()).unwrap());
        assert_eq!(host.status(&req.id),original);
        assert!(host.observe([1;16],&json!({"event":wire::EVENT,"request_id":req.id,"phase":"cancelled","no_write":true,"message":"late"})).is_none());
        assert_eq!(host.status("current-fixture"),original);
    }
    #[test] fn malformed_then_valid_original_terminal_can_settle_but_late_cannot_overwrite() {
        let req = wire::parse_request(&json!({"cmd":"expression_replacement","action":"current","request_id":"pending-fixture"})).unwrap();
        let mut host = Mailbox { epoch:[3;16], supported:true, ..Mailbox::default() };
        assert!(host.begin([3;16],req).unwrap()); host.rows[0].dispatched = true;
        host.observe([3;16],&json!({"event":"wrong_result","request_id":"pending-fixture"}));
        assert_eq!(wire::phase(&host.status("pending-fixture")),"unknown");
        let terminal = json!({"event":wire::EVENT,"request_id":"pending-fixture","phase":"cancelled","no_write":true,"message":"original cancelled"});
        host.observe([3;16],&terminal); assert_eq!(host.status("pending-fixture"),terminal);
        host.end([3;16]); assert_eq!(host.status("pending-fixture"),terminal);
    }
    #[test] fn eviction_never_deletes_identity_or_reissues() {
        let req = wire::parse_request(&json!({"cmd":"expression_replacement","action":"current","request_id":"retained-id"})).unwrap();
        let mut host = Mailbox::default(); host.begin([9;16],req.clone()).unwrap(); host.rows.clear();
        assert!(host.replay(&req).unwrap()); assert!(!host.begin([10;16],req).unwrap());
        assert_eq!(wire::phase(&host.status("retained-id")),"unknown");
    }
}
