// SPDX-License-Identifier: GPL-3.0-or-later
//! Tauri/engine bridge. No aliasing of another effect's dispatch or cancel lane.
use std::sync::Arc;
use serde_json::{json, Value};
use crate::{engine::EngineHandle, AppState};
use super::{mailbox, wire};

pub(super) fn reset(epoch: [u8;16]) { if let Ok(mut host) = mailbox::store().lock() { host.reset(epoch); } }
pub(super) fn ready(epoch: [u8;16], capability: &Value) { if let Ok(mut host) = mailbox::store().lock() { host.ready(epoch, capability); } }
pub(super) fn ended(epoch: [u8;16]) { if let Ok(mut host) = mailbox::store().lock() { host.end(epoch); } }
/// Call on the original stdout line BEFORE any generic recovery settlement.
pub(super) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    if !line.contains(wire::EVENT) { return None; }
    let value = match wire::unique_json(line, wire::RESULT_BYTES) {
        Ok(value) => value,
        Err(_) => { if let Ok(mut host) = mailbox::store().lock() { host.malformed(epoch); } return None; }
    };
    mailbox::store().lock().ok()?.observe(epoch, &value)
}
pub(super) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox::store().lock().map(|host| host.guards_result(epoch, id)).unwrap_or(true)
}
pub(super) fn read_only(command: &Value) -> bool {
    command["cmd"] == "upscale_restore" && matches!(command["action"].as_str(), Some("current"|"preview"|"receipt"))
}
pub(super) fn blocks_mutation(epoch: [u8;16], command: &Value) -> Result<(),String> {
    mailbox::store().lock().map_err(|_| "AI 超清原请求屏障锁不可用")?.ingress(epoch, command)
}
/// Shared native dispatch calls once; private host_epoch must not cross stdin.
pub(super) fn enqueue(handle: &EngineHandle, mut command: Value) -> Result<(),String> {
    let epoch = command.as_object_mut().ok_or("AI 超清信封无效")?.remove("host_epoch").ok_or("缺少原AI 超清引擎身份")?;
    if epoch.as_str() != Some(crate::frame_identity::hex(handle.epoch()).as_str()) { return Err("引擎已变化，未向新引擎重发原AI 超清请求".into()); }
    if !handle.is_alive() { return Err("原AI 超清引擎已结束，未重新提交".into()); }
    let id = command["request_id"].as_str().ok_or("AI 超清请求身份缺失")?.to_owned();
    mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.begin_enqueue(handle.epoch(), &command)?;
    let sent = handle.send(command);
    if let Ok(mut host) = mailbox::store().lock() { host.finish_enqueue(handle.epoch(), &id); }
    sent
}
pub(super) fn capability(state: &Arc<AppState>) -> Result<Value,String> {
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let epoch = engine.as_ref().filter(|h| h.is_alive()).map(|h| h.epoch());
    Ok(mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.capability(epoch))
}
pub(super) fn request(state: &Arc<AppState>, request: Value) -> Result<Value,String> {
    let req = wire::parse_request(&request)?;
    let id = req.id.clone(); let apply = req.apply();
    {
        let mut host = mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?;
        if host.replay(&req)? { return Ok(host.status(&id)); }
    }
    let handle = state.engine.lock().map_err(|_| "引擎锁不可用")?.clone();
    let epoch = handle.as_ref().map(|h| h.epoch()).unwrap_or([0;16]);
    let dispatch = mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.begin(epoch, req)?;
    if dispatch {
        let mut envelope = request; envelope["host_epoch"] = json!(crate::frame_identity::hex(epoch));
        let sent = if apply { state.send_to_engine(envelope) }
            else { handle.as_ref().ok_or_else(|| "引擎未运行".to_string()).and_then(|h| enqueue(h, envelope)) };
        if let Err(error) = sent {
            let why = format!("原AI 超清请求发送未获确认：{}；不会自动重发", error.chars().take(512).collect::<String>());
            mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.unknown(epoch, &id, &why);
        }
    }
    Ok(mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.status(&id))
}
pub(super) fn status(id: String) -> Result<Value,String> {
    if !wire::token(&json!(&id)) { return Err("AI 超清请求身份无效".into()); }
    Ok(mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.status(&id))
}
pub(super) fn cancel(state: &Arc<AppState>, id: String) -> Result<Value,String> {
    if !wire::token(&json!(&id)) { return Err("AI 超清取消请求身份无效".into()); }
    let engine = state.engine.lock().map_err(|_| "引擎锁不可用")?;
    let handle = engine.as_ref().filter(|h| h.is_alive()).ok_or("原引擎不可用；不能确认读取已停止")?;
    let epoch = handle.epoch();
    let (ack, original) = mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.request_cancel(epoch, &id)?;
    if let Some(original) = original {
        if let Err(error) = handle.cancel_upscale_restore_read(&id, &original) {
            mailbox::store().lock().map_err(|_| "AI 超清回执锁不可用")?.unknown(epoch, &id, "取消控制发送未获确认；仍须等待原读取终态，不会重发取消");
            return Err(error);
        }
    }
    Ok(ack)
}
