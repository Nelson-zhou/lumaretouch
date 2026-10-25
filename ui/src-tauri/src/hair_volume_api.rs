// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated hair-volume receipt owner, not a renderer, source bank or undo owner.
//! AUTHORED / UNRUN. Queue admission is not evidence of changed pixels.
use std::{collections::{HashMap, VecDeque}, fmt, sync::{Arc, Mutex, OnceLock}};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use tauri::State;
use crate::{engine::EngineHandle, AppState};
use crate::hair_volume_protocol::{self as protocol, EVENT, OPERATION, RESULT_BYTES, REQUEST_BYTES,
    mutation, reservation, same, size, token, valid_result, validate};

const STORE_BYTES: usize = 96 * 1024 * 1024;
const MAX_ROWS: usize = 64;
const TOMBSTONE_BYTES: usize = 16 * 1024 * 1024;
const MAX_TOMBSTONES: usize = 16_384;
const PROOF_BYTES: usize = 4096;

struct Tombstone { epoch: [u8; 16], request: Value }
struct Row {
    epoch: [u8; 16], request: Value, request_bytes: usize, reserved: usize,
    result: Option<Value>, proof: Option<Value>, settled: bool, dispatched: bool, retired: bool,
}
impl Row { fn bytes(&self) -> usize { self.request_bytes.saturating_add(self.reserved) } }
#[derive(Default)]
struct Mailbox {
    epoch: [u8; 16], supported: bool, native_available: bool, ended: bool,
    rows: VecDeque<Row>, seen: HashMap<String, Tombstone>, tombstone_bytes: usize,
}
fn mailbox() -> &'static Mutex<Mailbox> {
    static BOX: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    BOX.get_or_init(|| Mutex::new(Mailbox::default()))
}
fn failure(request: &Value, message: &str) -> Value {
    json!({"event":EVENT,"protocol":1,"operation_id":OPERATION,"request_id":request["request_id"],
        "action":request["action"],"document_id":request["people_context"]["document_id"],
        "people_context":request["people_context"],"request_payload":request["payload"],
        "success":false,"outcome_unknown":true,"error":message})
}
impl Mailbox {
    fn status(&self, id: &str) -> Value {
        match self.rows.iter().find(|row| row.request["request_id"] == id) {
            Some(row) => match &row.result {
                Some(result) => json!({"request_id":id,"phase":"done","result":result}),
                None => json!({"request_id":id,"phase":"pending"}),
            },
            None => json!({"request_id":id,"phase":"unavailable", "error":"原发量回执未保留或身份不存在；不能认定没有执行，请核对，不会重发"}),
        }
    }
    fn replay(&self, request: &Value) -> Result<bool, String> {
        match request["request_id"].as_str().and_then(|id| self.seen.get(id)) {
            None => Ok(false),
            Some(prior) if same(&prior.request, request) => Ok(true),
            Some(_) => Err("原发量请求身份已绑定其他内容；只能查询原请求，不能重新提交".into()),
        }
    }
    fn make_room(&mut self, additional: usize) -> Result<(), String> {
        while self.rows.len() >= MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(additional) > STORE_BYTES {
            let Some(index) = self.rows.iter().position(|row| row.settled || row.retired) else {
                return Err("发量回执安全容量已满；先核对未确认请求，未提交新操作".into());
            };
            self.rows.remove(index);
        }
        Ok(())
    }
    fn proof_admission(&self, epoch: [u8; 16], request: &Value) -> Result<Option<Value>, String> {
        let action = request["action"].as_str().unwrap_or("");
        if action == "preview" {
            // No request field grants source authority. Redeem a retained,
            // byte-validated context from this exact engine/document/face.
            let original = self.rows.iter().rev().find(|row| row.epoch == epoch && row.settled && !row.retired
                && row.request["action"] == "context" && same(&row.request["people_context"], &request["people_context"])
                && row.result.as_ref().is_some_and(|result| result["success"] == true));
            let Some(original) = original else { return Err("先加载并保留本照片、本人物的真实源图，再生成发量候选".into()); };
            let payload = &original.result.as_ref().ok_or("原源图回执缺失")?["payload"];
            if payload["native_available"] != true || !payload["semantic_evidence_sha256"].is_string()
                || !protocol::source_geometry(&request["payload"], &payload["source"]) {
                return Err("当前人物真实头发证据、原生核心或源图像素范围不足；未生成候选".into());
            }
            return Ok(Some(json!({"source":payload["source"], "semantic_evidence_sha256":payload["semantic_evidence_sha256"]})));
        }
        if !matches!(action, "presented" | "commit") { return Ok(None); }
        let payload = &request["payload"];
        let origin_action = if action == "presented" { "preview" } else { "presented" };
        let original = self.rows.iter().find(|row| row.epoch == epoch && row.settled && !row.retired
            && row.request["action"] == origin_action && same(&row.request["people_context"], &request["people_context"])
            && row.result.as_ref().is_some_and(|result| result["success"] == true
                && result["payload"]["preview_id"] == payload["preview_id"] && result["payload"]["review_token"] == payload["review_token"]));
        let Some(original) = original else { return Err("未保留本引擎、同一人物与版本的完整发量审核或显示确认；未应用".into()); };
        if action == "presented" && !["before_sha256", "after_sha256", "support_sha256"].iter().all(|key|
            original.result.as_ref().is_some_and(|result| result["payload"][*key] == payload[*key])) {
            return Err("已显示的完整前后图或支持图与原审核摘要不符；未应用".into());
        }
        if action == "commit" && self.seen.values().any(|old| old.epoch == epoch && old.request["action"] == "commit"
            && old.request["payload"]["preview_id"] == payload["preview_id"] && old.request["payload"]["review_token"] == payload["review_token"]) {
            return Err("原发量审核已用于提交；仅可查询原请求，不会重复应用".into());
        }
        if action == "presented" {
            let preview = &original.result.as_ref().ok_or("原审核结果缺失")?["payload"];
            Ok(Some(json!({"recipe":preview["recipe"], "support_asset_sha256":preview["support_asset_sha256"],
                "source":preview["source"], "semantic_evidence_sha256":preview["semantic_evidence_sha256"]})))
        } else {
            original.proof.clone().map(Some).ok_or_else(|| "已显示审核缺少原配方、源图与独立发量支持证明".into())
        }
    }
    fn begin(&mut self, epoch: [u8; 16], request: &Value) -> Result<(), String> {
        validate(request)?;
        if self.replay(request)? { return Err("原发量请求已经登记；只查询原请求，不会重新提交".into()); }
        if epoch == [0; 16] || self.epoch != epoch || self.ended || !self.supported {
            return Err("引擎变化或未声明发量协议；未提交".into());
        }
        if matches!(request["action"].as_str(), Some("preview" | "commit")) && !self.native_available {
            return Err("发量原生核心缺失或 ABI 不匹配；仍可读取或恢复中性，未使用替代算法".into());
        }
        if mutation(request) && self.rows.iter().any(|row| mutation(&row.request) && !row.settled && !row.retired) {
            return Err("原发量修改仍在处理或结果未知；只查询原请求，不能提交另一修改".into());
        }
        let request_bytes = size(request, REQUEST_BYTES)?;
        let tombstone_size = request_bytes.saturating_add(request["request_id"].as_str().unwrap_or("").len()).saturating_add(32);
        if self.seen.len() >= MAX_TOMBSTONES || self.tombstone_bytes.saturating_add(tombstone_size) > TOMBSTONE_BYTES {
            return Err("发量进程级防重放记录已满；未提交，旧身份不会因回执释放或引擎重启被删除".into());
        }
        let reserved = reservation(request["action"].as_str().unwrap_or(""));
        self.make_room(request_bytes.saturating_add(reserved).saturating_add(PROOF_BYTES))?;
        // Eviction may remove proof, so redeem it only after capacity admission.
        let proof = self.proof_admission(epoch, request)?;
        let proof_bytes = proof.as_ref().map(|proof| size(proof, PROOF_BYTES)).transpose()?.unwrap_or(0);
        self.tombstone_bytes += tombstone_size;
        self.seen.insert(request["request_id"].as_str().unwrap().to_owned(), Tombstone { epoch, request: request.clone() });
        self.rows.push_back(Row { epoch, request: request.clone(), request_bytes: request_bytes + proof_bytes, reserved,
            result: None, proof, settled: false, dispatched: false, retired: false });
        Ok(())
    }
    fn unknown(&mut self, epoch: [u8; 16], id: &str, reason: &str) {
        if let Some(row) = self.rows.iter_mut().find(|row| row.epoch == epoch && row.request["request_id"] == id && !row.settled && !row.retired) {
            row.result = Some(failure(&row.request, reason));
            // Reservation remains: a late original terminal may still arrive.
        }
    }
    fn end(&mut self, epoch: [u8; 16]) {
        for row in self.rows.iter_mut().filter(|row| row.epoch == epoch && !row.settled && !row.retired) {
            row.result = Some(failure(&row.request, "原引擎结束前未确认结果；只保留原请求查询，不会向新引擎重发"));
            if !mutation(&row.request) {
                row.retired = true;
                row.reserved = size(row.result.as_ref().unwrap(), RESULT_BYTES).unwrap_or(RESULT_BYTES);
            }
        }
        if self.epoch == epoch { self.supported = false; self.native_available = false; self.ended = true; }
    }
    fn reopen(&mut self, epoch: [u8; 16], value: &Value) {
        if value["event"] != "project_opened" || !value["docs"].is_u64() || self.epoch != epoch || self.ended { return; }
        for row in self.rows.iter_mut().filter(|row| !row.settled) {
            let mut result = failure(&row.request, "工程已明确重新打开；旧操作结果仍未知，以重新读取的工程为准，不会重发");
            result["workspace_reopened"] = json!(true);
            row.reserved = size(&result, RESULT_BYTES).unwrap_or(RESULT_BYTES);
            row.result = Some(result); row.retired = true;
        }
    }
    fn observe(&mut self, epoch: [u8; 16], value: &Value) -> Option<Value> {
        if value["event"] != EVENT { return None; }
        let id = value["request_id"].as_str()?;
        let row = self.rows.iter_mut().find(|row| row.epoch == epoch && row.request["request_id"] == id)?;
        if row.settled || row.retired || !row.dispatched { return None; }
        let length = size(value, reservation(row.request["action"].as_str().unwrap_or("")));
        let proof_matches = value["success"] != true || match row.request["action"].as_str() {
            Some("preview") => row.proof.as_ref().is_some_and(|proof|
                same(&proof["source"], &value["payload"]["source"])
                    && proof["semantic_evidence_sha256"] == value["payload"]["semantic_evidence_sha256"]),
            Some("commit") => row.proof.as_ref().is_some_and(|proof|
                same(&proof["recipe"], &value["payload"]["recipe"])
                    && proof["support_asset_sha256"] == value["payload"]["asset_sha256"]),
            _ => true,
        };
        if length.is_err() || !valid_result(value, &row.request) || !proof_matches {
            row.result = Some(failure(&row.request, "原生发量回执身份、来源、内容或审核图片不匹配；实际结果未知，只查询原请求"));
            return None;
        }
        row.settled = value["outcome_unknown"] == false;
        row.result = Some(value.clone());
        if row.settled { row.reserved = length.ok()?; }
        // Only the original fully validated mutation may settle a global fence
        // or refresh current state. A status query has no such authority.
        if row.settled && mutation(&row.request) { Some(value.clone()) } else { None }
    }
}

pub(crate) fn read_only(request: &Value) -> bool { protocol::read_only(request) }
pub(crate) fn reset(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() {
        if host.epoch != epoch { let old = host.epoch; host.end(old); }
        host.epoch = epoch; host.supported = false; host.native_available = false; host.ended = false;
    }
}
pub(crate) fn ready(epoch: [u8; 16], supported: bool, native_available: bool) {
    if let Ok(mut host) = mailbox().lock() {
        if host.epoch == epoch && !host.ended { host.supported = supported; host.native_available = supported && native_available; }
    }
}
pub(crate) fn ended(epoch: [u8; 16]) { if let Ok(mut host) = mailbox().lock() { host.end(epoch); } }
/// Includes evicted tombstones: changed event labels cannot bypass validation.
pub(crate) fn guards_result(epoch: [u8; 16], id: &str) -> bool {
    mailbox().lock().map(|host| host.seen.get(id).is_some_and(|old| old.epoch == epoch)).unwrap_or(true)
}
/// Trusted in-process input only. Stdout must first use observe_line.
pub(crate) fn receive(epoch: [u8; 16], value: &Value) -> Option<Value> { mailbox().lock().ok()?.observe(epoch, value) }
pub(crate) fn blocks_mutation(epoch: [u8; 16], command: &Value) -> Result<(), String> {
    let host = mailbox().lock().map_err(|_| "发量回执屏障锁不可用")?;
    let Some(pending) = host.rows.iter().find(|row| mutation(&row.request) && !row.settled && !row.retired) else { return Ok(()); };
    let safe = read_only(command) || matches!(command["cmd"].as_str(), Some("hello" | "shutdown"))
        || command["cmd"] == "project_recovery"
        || (command["cmd"] == "project" && matches!(command["action"].as_str(), Some("open" | "create" | "state")));
    if safe || (pending.epoch == epoch && pending.dispatched && same(command, &pending.request)) { return Ok(()); }
    Err("原发量修改尚未确认；只查询原请求或明确重新打开工程，不能继续写入、撤销、保存或导出".into())
}
pub(crate) fn project_reopened(epoch: [u8; 16], value: &Value) {
    if let Ok(mut host) = mailbox().lock() { host.reopen(epoch, value); }
}
/// Called once by shared epoch-bound dispatch, including read-only operations.
pub(crate) fn enqueue(handle: &EngineHandle, command: Value) -> Result<(), String> {
    validate(&command)?;
    {
        let mut host = mailbox().lock().map_err(|_| "发量回执锁不可用")?;
        if host.epoch != handle.epoch() || host.ended || !host.supported || !handle.is_alive() {
            return Err("原发量引擎已结束或协议变化；不向新引擎重发".into());
        }
        let row = host.rows.iter_mut().find(|row| row.epoch == handle.epoch() && row.request["request_id"] == command["request_id"])
            .ok_or("发量命令没有原始登记")?;
        if row.dispatched || row.settled || row.retired || !same(&row.request, &command) {
            return Err("发量请求已发送或原始内容变化；不会重发".into());
        }
        row.dispatched = true;
    }
    // Every error after admission remains conservatively query-only, not a
    // fabricated not_sent response after an uncertain queue/write operation.
    handle.send(command)
}
fn not_sent(request: &Value, error: &str) -> Value {
    json!({"requested":false,"not_sent":true,"request_id":request["request_id"],"error":error})
}
#[tauri::command]
pub(crate) fn hair_volume(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    // Reused IDs must never imply the first request did not run after eviction.
    {
        let host = mailbox().lock().map_err(|_| "发量回执锁不可用")?;
        if host.replay(&request)? { return Ok(json!({"requested":true,"request_id":request["request_id"]})); }
    }
    if let Err(error) = validate(&request) { return Ok(not_sent(&request, &error)); }
    let epoch = {
        let guard = state.engine.lock().map_err(|_| "引擎锁不可用")?;
        let Some(handle) = guard.as_ref().filter(|handle| handle.is_alive()) else {
            return Ok(not_sent(&request, "引擎未运行；发量请求未提交"));
        };
        handle.epoch()
    };
    {
        let mut host = mailbox().lock().map_err(|_| "发量回执锁不可用")?;
        if host.replay(&request)? { return Ok(json!({"requested":true,"request_id":request["request_id"]})); }
        if let Err(error) = host.begin(epoch, &request) { return Ok(not_sent(&request, &error)); }
    }
    let id = request["request_id"].as_str().unwrap().to_owned();
    if let Err(error) = state.send_to_engine_at_epoch(request, epoch) {
        if let Ok(mut host) = mailbox().lock() { host.unknown(epoch, &id, "发量发送结果未确认；只查询原请求，不能自动或换身份重发"); }
        return Err(format!("发量发送结果待核对，不会重发：{error}"));
    }
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command(rename_all = "snake_case")]
pub(crate) fn hair_volume_status(request_id: String) -> Result<Value, String> {
    if !token(&json!(&request_id)) { return Err("发量原请求身份无效".into()); }
    Ok(mailbox().lock().map_err(|_| "发量回执锁不可用")?.status(&request_id))
}

/// Parse each nesting level before duplicate-key evidence can be discarded.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct UniqueVisitor;
        impl<'de> Visitor<'de> for UniqueVisitor {
            type Value = Unique;
            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result { formatter.write_str("finite JSON without duplicate fields") }
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Unique, E> { Ok(Unique(json!(value))) }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Unique, E> { Ok(Unique(json!(value))) }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Unique, E> { Ok(Unique(json!(value))) }
            fn visit_f64<E: de::Error>(self, value: f64) -> Result<Unique, E> {
                Number::from_f64(value).map(|n| Unique(Value::Number(n))).ok_or_else(|| E::custom("nonfinite number"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Unique, E> { Ok(Unique(Value::String(value.into()))) }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Unique, E> { Ok(Unique(Value::String(value))) }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> { Ok(Unique(Value::Null)) }
            fn visit_none<E: de::Error>(self) -> Result<Unique, E> { Ok(Unique(Value::Null)) }
            fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Unique, A::Error> {
                let mut items = Vec::new();
                while let Some(Unique(value)) = sequence.next_element::<Unique>()? { items.push(value); }
                Ok(Unique(Value::Array(items)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Unique, A::Error> {
                let mut fields = Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if fields.contains_key(&key) { return Err(de::Error::custom("duplicate JSON field")); }
                    fields.insert(key, map.next_value::<Unique>()?.0);
                }
                Ok(Unique(Value::Object(fields)))
            }
        }
        deserializer.deserialize_any(UniqueVisitor)
    }
}
fn unique_json(line: &str) -> Option<Value> {
    if line.len() > RESULT_BYTES { return None; }
    let mut parser = serde_json::Deserializer::from_str(line);
    let value = Unique::deserialize(&mut parser).ok()?.0;
    parser.end().ok()?;
    Some(value)
}
pub(crate) fn observe_line(epoch: [u8; 16], line: &str) -> Option<Value> {
    if !line.contains(EVENT) { return None; }
    let value = unique_json(line)?;
    receive(epoch, &value)
}

#[cfg(test)]
#[path = "hair_volume_protocol_unrun.rs"]
mod unrun_fixtures;
