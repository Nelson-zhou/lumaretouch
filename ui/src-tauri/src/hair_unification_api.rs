// SPDX-License-Identifier: GPL-3.0-or-later
//! Source-owned hair-unification transport, not another renderer or undo owner.
//! AUTHORED / UNRUN. Queue admission is never evidence of applied image pixels.
use std::{collections::{HashMap, HashSet, VecDeque}, fmt, io::{self, Write}, sync::{Arc, Mutex, OnceLock}};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{de::{self, MapAccess, SeqAccess, Visitor}, Deserialize, Deserializer};
use serde_json::{json, Map, Number, Value};
use sha2::{Digest, Sha256};
use tauri::State;
use crate::{engine::EngineHandle, AppState};

const OPERATION: &str = "lnx.hair_unification.v1";
const EVENT: &str = "hair_unification_result";
const REQUEST_BYTES: usize = 512 * 1024;
const IMAGE_BYTES: usize = 8 * 1024 * 1024;
const RESULT_BYTES: usize = 25 * 1024 * 1024;
const STORE_BYTES: usize = 96 * 1024 * 1024;
const MAX_ROWS: usize = 64;
const TOMBSTONE_BYTES: usize = 16 * 1024 * 1024;
const MAX_TOMBSTONES: usize = 16_384;

fn fields(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|object| object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key)))
}
fn token(value: &Value) -> bool {
    value.as_str().is_some_and(|text| !text.is_empty() && text.len() <= 160 && !text.chars().any(char::is_control))
}
fn hex(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|text| text.len() == length && text.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn number(value: &Value, low: f64, high: f64) -> bool {
    value.as_f64().is_some_and(|n| n.is_finite() && (low..=high).contains(&n))
}
fn pair(value: &Value, low: f64, high: f64) -> bool {
    value.as_array().is_some_and(|items| items.len() == 2 && items.iter().all(|n| number(n, low, high)))
}
fn recipe(value: &Value) -> bool {
    fields(value, &["version", "amount"]) && value["version"] == 1 && number(&value["amount"], -1.0, 1.0)
}
/// JSON numeric meaning is retained, including Python's 1.0 echo of JSON 1.
/// This compares original values, never hashes of cross-language serialization.
fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(a), Value::Number(b)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a,b)| same(a,b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(key,a)| b.get(key).is_some_and(|b| same(a,b))),
        _ => a == b,
    }
}
fn sample(value: &Value) -> bool {
    if !fields(value, &["version", "domain", "objects"]) || value["version"] != 1 || value["domain"] != "source-normalized" { return false; }
    let Some(objects) = value["objects"].as_array().filter(|items| items.len() <= 64) else { return false; };
    let mut ids = HashSet::new();
    let mut total = 0usize;
    for object in objects {
        let kind = object["kind"].as_str().unwrap_or("");
        let expected = match kind {
            "brush" => &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "axes", "points"][..],
            "radial" => &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "axes", "center"][..],
            _ => return false,
        };
        let Some(id) = object["id"].as_str().filter(|id| !id.is_empty() && id.len() <= 64
            && id.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))) else { return false; };
        if !fields(object, expected) || !ids.insert(id) || !object["name"].as_str().is_some_and(|name|
            !name.trim().is_empty() && name.chars().count() <= 80 && !name.chars().any(|c| c < ' '))
            || !object["enabled"].is_boolean() || !matches!(object["operation"].as_str(), Some("add"|"subtract"))
            || !number(&object["opacity"], 0.0, 1.0) || !number(&object["feather"], 0.0, 100.0) { return false; }
        let Some(axes) = object["axes"].as_array().filter(|a| a.len() == 2 && a.iter().all(|p| pair(p, -4.0, 4.0))) else { return false; };
        let determinant = axes[0][0].as_f64().unwrap() * axes[1][1].as_f64().unwrap()
            - axes[0][1].as_f64().unwrap() * axes[1][0].as_f64().unwrap();
        if determinant.abs() < 1e-12 { return false; }
        if kind == "brush" {
            let Some(points) = object["points"].as_array().filter(|p| (1..=1024).contains(&p.len()) && p.iter().all(|p| pair(p, 0.0, 1.0))) else { return false; };
            total += points.len();
        } else if !pair(&object["center"], 0.0, 1.0) { return false; }
    }
    total <= 8192
}
fn review_identity(value: &Value) -> bool { hex(&value["preview_id"], 32) && hex(&value["review_token"], 64) }
fn ack(value: &Value) -> bool {
    review_identity(value) && ["before_sha256", "after_sha256", "support_sha256"].iter().all(|key| hex(&value[*key], 64))
}
fn valid_payload(action: &str, payload: &Value) -> bool {
    match action {
        "context" | "clear" => fields(payload, &[]),
        "preview" => fields(payload, &["recipe", "root_sample", "tip_sample", "ownership_confirmed"])
            && recipe(&payload["recipe"]) && payload["recipe"]["amount"].as_f64() != Some(0.0)
            && sample(&payload["root_sample"]) && sample(&payload["tip_sample"]) && payload["ownership_confirmed"] == true,
        "presented" => fields(payload, &["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"]) && ack(payload),
        "commit" => fields(payload, &["preview_id", "review_token", "confirmed"]) && review_identity(payload) && payload["confirmed"] == true,
        _ => false,
    }
}
fn validate(request: &Value) -> Result<(), String> {
    if !fields(request, &["cmd", "protocol", "operation_id", "request_id", "action", "people_context", "payload"])
        || request["cmd"] != "hair_unification" || request["protocol"] != 1 || request["operation_id"] != OPERATION
        || !token(&request["request_id"]) || !crate::people_api::valid_context(&request["people_context"])
        || request["people_context"]["target"]["scope"] != "face"
        || !valid_payload(request["action"].as_str().unwrap_or(""), &request["payload"]) {
        return Err("发色统一请求缺少完整来源、独立人物范围或有效审核内容".into());
    }
    size(request, REQUEST_BYTES).map(|_| ())
}
fn mutation(request: &Value) -> bool { matches!(request["action"].as_str(), Some("commit"|"clear")) }
pub(crate) fn read_only(request: &Value) -> bool {
    request["cmd"] == "hair_unification" && matches!(request["action"].as_str(), Some("context"|"preview"|"presented"|"status"))
}
fn reservation(action: &str) -> usize { match action { "preview" => RESULT_BYTES, "context" => 9 * 1024 * 1024, _ => 8 * 1024 * 1024 } }
fn size(value: &Value, limit: usize) -> Result<usize, String> {
    struct Count { count: usize, limit: usize }
    impl Write for Count {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.count = self.count.checked_add(bytes.len()).ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "size overflow"))?;
            if self.count > self.limit { return Err(io::Error::new(io::ErrorKind::InvalidData, "size limit")); }
            Ok(bytes.len())
        }
        fn flush(&mut self) -> io::Result<()> { Ok(()) }
    }
    let mut counter = Count { count: 0, limit };
    serde_json::to_writer(&mut counter, value).map_err(|_| "发色统一数据超过安全大小上限".to_owned())?;
    Ok(counter.count)
}

struct Tombstone { epoch: [u8;16], request: Value }
struct Row {
    epoch: [u8;16], request: Value, request_bytes: usize, reserved: usize,
    result: Option<Value>, reviewed: Option<Value>, settled: bool, dispatched: bool, retired: bool,
}
impl Row { fn bytes(&self) -> usize { self.request_bytes.saturating_add(self.reserved) } }
#[derive(Default)]
struct Mailbox {
    epoch: [u8;16], supported: bool, native_available: bool, ended: bool,
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
            None => json!({"request_id":id,"phase":"unavailable","error":"原发色统一回执未保留或身份不存在；不能认定没有执行，请核对，不会重发"}),
        }
    }
    fn replay(&self, request: &Value) -> Result<bool, String> {
        match request["request_id"].as_str().and_then(|id| self.seen.get(id)) {
            None => Ok(false),
            Some(prior) if same(&prior.request, request) => Ok(true),
            Some(_) => Err("原发色统一请求身份已绑定其他内容；只能查询原请求，不能重新提交".into()),
        }
    }
    fn make_room(&mut self, additional: usize) -> Result<(), String> {
        while self.rows.len() >= MAX_ROWS || self.rows.iter().map(Row::bytes).sum::<usize>().saturating_add(additional) > STORE_BYTES {
            let Some(index) = self.rows.iter().position(|row| row.settled || row.retired) else {
                return Err("发色统一回执安全容量已满；先核对未确认请求，未提交新操作".into());
            };
            self.rows.remove(index);
        }
        Ok(())
    }
    fn review_admission(&self, epoch: [u8;16], request: &Value) -> Result<Option<Value>, String> {
        let action = request["action"].as_str().unwrap_or("");
        if !matches!(action, "presented"|"commit") { return Ok(None); }
        let payload = &request["payload"];
        let origin_action = if action == "presented" { "preview" } else { "presented" };
        let original = self.rows.iter().find(|row| row.epoch == epoch && row.settled && !row.retired
            && row.request["action"] == origin_action && same(&row.request["people_context"], &request["people_context"])
            && row.result.as_ref().is_some_and(|result| result["success"] == true
                && result["payload"]["preview_id"] == payload["preview_id"] && result["payload"]["review_token"] == payload["review_token"]));
        let Some(original) = original else { return Err("未保留本引擎、同一人物与版本的完整已显示审核；未应用".into()); };
        if action == "presented" && !["before_sha256", "after_sha256", "support_sha256"].iter().all(|key|
            original.result.as_ref().is_some_and(|result| result["payload"][*key] == payload[*key])) {
            return Err("已显示的前后图或支持图与原审核摘要不符；未应用".into());
        }
        if action == "commit" && self.seen.values().any(|old| old.epoch == epoch && old.request["action"] == "commit"
            && old.request["payload"]["preview_id"] == payload["preview_id"] && old.request["payload"]["review_token"] == payload["review_token"]) {
            return Err("原发色统一审核已用于提交；仅可查询原请求，不会重复应用".into());
        }
        if action == "presented" {
            let preview = &original.result.as_ref().ok_or("原审核结果缺失")?["payload"];
            Ok(Some(json!({"recipe":preview["recipe"],"sample_asset_sha256":preview["sample_asset_sha256"]})))
        } else {
            original.reviewed.clone().map(Some).ok_or_else(|| "已显示审核缺少原配方与样本资产证明".into())
        }
    }
    fn begin(&mut self, epoch: [u8;16], request: &Value) -> Result<(), String> {
        validate(request)?;
        if self.replay(request)? { return Err("原发色统一请求已经登记；只查询原请求，不会重新提交".into()); }
        if epoch == [0;16] || self.epoch != epoch || self.ended || !self.supported {
            return Err("引擎变化或未声明发色统一协议；未提交".into());
        }
        if matches!(request["action"].as_str(), Some("preview"|"commit")) && !self.native_available {
            return Err("发色统一原生核心缺失或 ABI 不匹配；仍可读取或恢复中性，未替代算法".into());
        }
        if mutation(request) && self.rows.iter().any(|row| mutation(&row.request) && !row.settled && !row.retired) {
            return Err("原发色统一修改仍在处理或结果未知；只查询原请求，不能提交另一修改".into());
        }
        let request_bytes = size(request, REQUEST_BYTES)?;
        let tombstone_size = request_bytes.saturating_add(request["request_id"].as_str().unwrap_or("").len()).saturating_add(32);
        if self.seen.len() >= MAX_TOMBSTONES || self.tombstone_bytes.saturating_add(tombstone_size) > TOMBSTONE_BYTES {
            return Err("发色统一进程级防重放记录已满；未提交，旧身份不会因回执释放或引擎重启被删除".into());
        }
        let reserved = reservation(request["action"].as_str().unwrap_or(""));
        self.make_room(request_bytes.saturating_add(reserved).saturating_add(1024))?;
        // Capacity eviction may remove a preview. Validate retained evidence last.
        let reviewed = self.review_admission(epoch, request)?;
        let review_bytes = reviewed.as_ref().map(|proof| size(proof, 1024)).transpose()?.unwrap_or(0);
        self.tombstone_bytes += tombstone_size;
        self.seen.insert(request["request_id"].as_str().unwrap().to_owned(), Tombstone { epoch, request: request.clone() });
        self.rows.push_back(Row { epoch, request: request.clone(), request_bytes:request_bytes + review_bytes, reserved,
            result: None, reviewed, settled: false, dispatched: false, retired: false });
        Ok(())
    }
    fn unknown(&mut self, epoch: [u8;16], id: &str, reason: &str) {
        if let Some(row) = self.rows.iter_mut().find(|row| row.epoch == epoch && row.request["request_id"] == id && !row.settled && !row.retired) {
            row.result = Some(failure(&row.request, reason));
            // Keep the reservation. A later original terminal can still arrive.
        }
    }
    fn end(&mut self, epoch: [u8;16]) {
        for row in self.rows.iter_mut().filter(|row| row.epoch == epoch && !row.settled && !row.retired) {
            row.result = Some(failure(&row.request, "原引擎结束前未确认结果；只保留原请求查询，不会向新引擎重发"));
            // Unfinished reads cannot mutate a document and may release capacity.
            if !mutation(&row.request) { row.retired = true; row.reserved = size(row.result.as_ref().unwrap(), RESULT_BYTES).unwrap_or(RESULT_BYTES); }
        }
        if self.epoch == epoch { self.supported = false; self.native_available = false; self.ended = true; }
    }
    fn reopen(&mut self, epoch: [u8;16], value: &Value) {
        if value["event"] != "project_opened" || !value["docs"].is_u64()
            || self.epoch != epoch || self.ended { return; }
        // Include unresolved reads retired by end(). They also need explicit
        // native proof that the replacement workspace was authoritatively read.
        // A settled success/rejection remains immutable across every reopen.
        for row in self.rows.iter_mut().filter(|row| !row.settled) {
            let mut result = failure(&row.request, "工程已明确重新打开；旧操作结果仍未知，以重新读取的工程为准，不会重发");
            result["workspace_reopened"] = json!(true);
            row.reserved = size(&result, RESULT_BYTES).unwrap_or(RESULT_BYTES);
            row.result = Some(result); row.retired = true;
        }
    }
    fn observe(&mut self, epoch: [u8;16], value: &Value) -> Option<Value> {
        if value["event"] != EVENT { return None; }
        let id = value["request_id"].as_str()?;
        let row = self.rows.iter_mut().find(|row| row.epoch == epoch && row.request["request_id"] == id)?;
        if row.settled || row.retired || !row.dispatched { return None; }
        let length = size(value, reservation(row.request["action"].as_str().unwrap_or("")));
        let reviewed_publication = row.request["action"] != "commit" || value["success"] != true
            || row.reviewed.as_ref().is_some_and(|proof| same(&proof["recipe"], &value["payload"]["recipe"])
                && proof["sample_asset_sha256"] == value["payload"]["asset_sha256"]);
        if length.is_err() || !valid_result(value, &row.request) || !reviewed_publication {
            row.result = Some(failure(&row.request, "原生回执身份、内容或审核图片不匹配；实际结果未知，只查询原请求"));
            return None;
        }
        row.settled = value["outcome_unknown"] == false;
        row.result = Some(value.clone());
        if row.settled { row.reserved = length.ok()?; }
        if row.settled && mutation(&row.request) {
            // Only this post-validation receipt may settle the recovery fence
            // or refresh visible state. Preserve any stricter host readback flag.
            Some(value.clone())
        } else { None }
    }
}

fn image_matches(payload: &Value, prefix: &str) -> bool {
    let Some(url) = payload[format!("{prefix}_png")].as_str().filter(|url| url.len() <= IMAGE_BYTES) else { return false; };
    let Some(encoded) = url.strip_prefix("data:image/png;base64,") else { return false; };
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    if bytes.len() < 33 || &bytes[..8] != b"\x89PNG\r\n\x1a\n" || &bytes[12..16] != b"IHDR" || bytes[8..12] != [0,0,0,13] { return false; }
    let width = u32::from_be_bytes(bytes[16..20].try_into().unwrap());
    let height = u32::from_be_bytes(bytes[20..24].try_into().unwrap());
    (1..=1024).contains(&width) && (1..=1024).contains(&height)
        && payload[format!("{prefix}_width")].as_u64() == Some(width as u64)
        && payload[format!("{prefix}_height")].as_u64() == Some(height as u64)
        && payload[format!("{prefix}_sha256")] == format!("{:x}", Sha256::digest(&bytes))
}
fn nonregressing(after: &Value, before: &Value) -> bool {
    after.as_u64().zip(before.as_u64()).is_some_and(|(after, before)| after >= before && after <= 9_007_199_254_740_991)
}
fn publication(value: &Value, request: &Value) -> bool {
    let payload = &value["payload"];
    let context = &request["people_context"];
    let people = &value["doc_state"]["people"];
    let binding = &people["binding"];
    let resolved = &people["resolved"];
    let expected_kind = if request["action"] == "commit" { "confirmed" } else { "cleared" };
    payload["kind"] == expected_kind && payload["committed"] == true && recipe(&payload["recipe"])
        && (if request["action"] == "commit" { hex(&payload["asset_sha256"], 64) && payload["recipe"]["amount"].as_f64() != Some(0.0) }
            else { payload["recipe"]["amount"].as_f64() == Some(0.0) })
        && binding["document_id"] == context["document_id"] && binding["document_epoch"] == context["document_epoch"]
        && binding["asset_sha256"] == context["target"]["face_ref"]["asset_sha256"]
        && nonregressing(&binding["document_revision"], &context["document_revision"])
        && nonregressing(&people["revision"], &context["state_revision"])
        && people["association_revision"] == context["association_revision"]
        && same(&resolved["face_ref"], &context["target"]["face_ref"])
        && resolved["state_revision"] == people["revision"] && resolved["association_revision"] == people["association_revision"]
        && resolved["operations"][OPERATION]["/amount"]["value"].as_f64() == payload["recipe"]["amount"].as_f64()
}
fn valid_result(value: &Value, request: &Value) -> bool {
    // This marker can only be produced by the native reopen path. Even false
    // or null backend values cannot impersonate native recovery provenance.
    if value.get("workspace_reopened").is_some()
        || value["event"] != EVENT || value["protocol"] != 1 || value["operation_id"] != OPERATION
        || value["request_id"] != request["request_id"] || value["action"] != request["action"]
        || value["document_id"] != request["people_context"]["document_id"]
        || !same(&value["people_context"], &request["people_context"])
        || !same(&value["request_payload"], &request["payload"])
        || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean()
        || value["requires_readback"] == true || value["requires_reload"] == true { return false; }
    if value["success"] == false {
        return value["error"].as_str().is_some_and(|error| !error.trim().is_empty() && error.len() <= 8192);
    }
    if value["outcome_unknown"] != false || !value["payload"].is_object() { return false; }
    let payload = &value["payload"];
    match request["action"].as_str() {
        Some("preview") => ack(payload) && hex(&payload["sample_asset_sha256"], 64) && payload["preview_sha256"] == payload["review_token"]
            && same(&payload["face_ref"], &request["people_context"]["target"]["face_ref"])
            && payload["source"]["sha256"] == request["people_context"]["target"]["face_ref"]["asset_sha256"]
            && ["recipe", "root_sample", "tip_sample"].iter().all(|key| same(&payload[*key], &request["payload"][*key]))
            && ["before", "after", "support"].iter().all(|prefix| image_matches(payload, prefix))
            && payload["before_width"] == payload["after_width"] && payload["before_height"] == payload["after_height"],
        Some("presented") => payload["kind"] == "presented" && payload["presented"] == true
            && ["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"].iter()
                .all(|key| payload[*key] == request["payload"][*key]),
        Some("commit"|"clear") => publication(value, request),
        _ => true,
    }
}

pub(crate) fn reset(epoch: [u8;16]) {
    if let Ok(mut host) = mailbox().lock() {
        if host.epoch != epoch { let old = host.epoch; host.end(old); }
        host.epoch = epoch; host.supported = false; host.native_available = false; host.ended = false;
    }
}
pub(crate) fn ready(epoch: [u8;16], supported: bool, native_available: bool) {
    if let Ok(mut host) = mailbox().lock() {
        if host.epoch == epoch && !host.ended { host.supported = supported; host.native_available = supported && native_available; }
    }
}
pub(crate) fn ended(epoch: [u8;16]) { if let Ok(mut host) = mailbox().lock() { host.end(epoch); } }
/// Protect tombstones too: a wrong event name cannot bypass receipt validation.
pub(crate) fn guards_result(epoch: [u8;16], id: &str) -> bool {
    mailbox().lock().map(|host| host.seen.get(id).is_some_and(|old| old.epoch == epoch)).unwrap_or(true)
}
/// Trusted in-process input only. Engine stdout must enter through observe_line.
pub(crate) fn receive(epoch: [u8;16], value: &Value) -> Option<Value> { mailbox().lock().ok()?.observe(epoch, value) }
pub(crate) fn blocks_mutation(epoch: [u8;16], command: &Value) -> Result<(), String> {
    let host = mailbox().lock().map_err(|_| "发色统一回执屏障锁不可用")?;
    let Some(pending) = host.rows.iter().find(|row| mutation(&row.request) && !row.settled && !row.retired) else { return Ok(()); };
    let safe = read_only(command) || matches!(command["cmd"].as_str(), Some("hello"|"shutdown"))
        || command["cmd"] == "project_recovery"
        || (command["cmd"] == "project" && matches!(command["action"].as_str(), Some("open"|"create"|"state")));
    if safe || (pending.epoch == epoch && pending.dispatched && same(command, &pending.request)) { return Ok(()); }
    Err("原发色统一修改尚未确认；只查询原请求或明确重新打开工程，不能继续写入、撤销、保存或导出".into())
}
/// Explicit, authoritative workspace reopening is a recovery escape, not proof
/// that an old operation failed. Old unknown receipts and tombstones stay intact.
pub(crate) fn project_reopened(epoch: [u8;16], value: &Value) {
    if let Ok(mut host) = mailbox().lock() { host.reopen(epoch, value); }
}
/// Called once by the parent's epoch-bound shared dispatch path, for reads too.
pub(crate) fn enqueue(handle: &EngineHandle, command: Value) -> Result<(), String> {
    validate(&command)?;
    {
        let mut host = mailbox().lock().map_err(|_| "发色统一回执锁不可用")?;
        if host.epoch != handle.epoch() || host.ended || !host.supported || !handle.is_alive() {
            return Err("原发色统一引擎已结束或协议变化；不向新引擎重发".into());
        }
        let row = host.rows.iter_mut().find(|row| row.epoch == handle.epoch() && row.request["request_id"] == command["request_id"])
            .ok_or("发色统一命令没有原始登记")?;
        if row.dispatched || row.settled || row.retired || !same(&row.request, &command) { return Err("发色统一请求已发送或原始内容变化；不会重发".into()); }
        // Set before enqueue; all errors after this point are conservatively
        // query-only. A write failure never becomes a false not_sent receipt.
        row.dispatched = true;
    }
    handle.send(command)
}
fn not_sent(request: &Value, error: &str) -> Value {
    json!({"requested":false,"not_sent":true,"request_id":request["request_id"],"error":error})
}
#[tauri::command]
pub(crate) fn hair_unification(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    // Check process-lifetime identity before any rejection. Reused IDs must not
    // imply that the earlier admitted request never ran, even after eviction.
    {
        let host = mailbox().lock().map_err(|_| "发色统一回执锁不可用")?;
        if host.replay(&request)? { return Ok(json!({"requested":true,"request_id":request["request_id"]})); }
    }
    if let Err(error) = validate(&request) { return Ok(not_sent(&request, &error)); }
    let epoch = {
        let guard = state.engine.lock().map_err(|_| "引擎锁不可用")?;
        let Some(handle) = guard.as_ref().filter(|handle| handle.is_alive()) else {
            return Ok(not_sent(&request, "引擎未运行；发色统一请求未提交"));
        };
        handle.epoch()
    };
    {
        let mut host = mailbox().lock().map_err(|_| "发色统一回执锁不可用")?;
        if host.replay(&request)? { return Ok(json!({"requested":true,"request_id":request["request_id"]})); }
        if let Err(error) = host.begin(epoch, &request) { return Ok(not_sent(&request, &error)); }
    }
    let id = request["request_id"].as_str().unwrap().to_owned();
    if let Err(error) = state.send_to_engine_at_epoch(request, epoch) {
        if let Ok(mut host) = mailbox().lock() { host.unknown(epoch, &id, "发色统一发送结果未确认；只查询原请求，不能自动或换身份重发"); }
        return Err(format!("发色统一发送结果待核对，不会重发：{error}"));
    }
    Ok(json!({"requested":true,"request_id":id}))
}
#[tauri::command]
pub(crate) fn hair_unification_status(request_id: String) -> Result<Value, String> {
    if !token(&json!(&request_id)) { return Err("发色统一原请求身份无效".into()); }
    Ok(mailbox().lock().map_err(|_| "发色统一回执锁不可用")?.status(&request_id))
}

/// Parse every nesting level without losing duplicate-key evidence first.
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
                Number::from_f64(value).map(|value| Unique(Value::Number(value))).ok_or_else(|| E::custom("nonfinite number"))
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
pub(crate) fn observe_line(epoch: [u8;16], line: &str) -> Option<Value> {
    if !line.contains(EVENT) { return None; }
    let value = unique_json(line)?;
    receive(epoch, &value)
}

// AUTHORED / UNRUN. Transport specifications only, not runtime or image-quality evidence.
#[cfg(test)]
mod unrun_fixtures {
    use super::*;
    const EPOCH: [u8;16] = [67;16];
    fn context() -> Value {
        json!({"document_id":"doc","document_epoch":"workspace","document_revision":2,"state_revision":3,
            "association_revision":4,"target":{"scope":"face","target_id":"face",
                "face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":5}}})
    }
    fn request(id: &str, action: &str, payload: Value) -> Value {
        json!({"cmd":"hair_unification","protocol":1,"operation_id":OPERATION,"request_id":id,
            "action":action,"people_context":context(),"payload":payload})
    }
    fn host() -> Mailbox { Mailbox { epoch:EPOCH,supported:true,native_available:true,..Default::default() } }
    fn result(request: &Value, payload: Value) -> Value {
        let mut value = failure(request, "fixture");
        value.as_object_mut().unwrap().remove("error");
        value["success"] = json!(true); value["outcome_unknown"] = json!(false); value["payload"] = payload;
        if mutation(request) {
            let amount = if request["action"] == "commit" { 0.5 } else { 0.0 };
            value["payload"] = json!({"kind":if request["action"] == "commit" { "confirmed" } else { "cleared" },
                "committed":true,"recipe":{"version":1,"amount":amount},"asset_sha256":"b".repeat(64)});
            value["doc_state"] = json!({"people":{"revision":4,"association_revision":4,
                "binding":{"document_id":"doc","document_epoch":"workspace","document_revision":3,"asset_sha256":"a".repeat(64)},
                "resolved":{"face_ref":context()["target"]["face_ref"],"state_revision":4,"association_revision":4,
                    "operations":{OPERATION:{"/amount":{"value":amount}}}}}});
        }
        value
    }
    fn admit(host: &mut Mailbox, request: &Value) {
        host.begin(EPOCH, request).unwrap();
        host.rows.back_mut().unwrap().dispatched = true;
    }
    fn sample_fixture() -> Value {
        json!({"version":1,"domain":"source-normalized","objects":[{
            "id":"root","name":"Root sample","enabled":true,"kind":"brush","operation":"add",
            "opacity":1,"feather":0,"axes":[[0.02,0],[0,0.02]],"points":[[0.2,0.3],[0.3,0.4]]}]})
    }
    fn preview_request() -> Value {
        request("preview", "preview", json!({"recipe":{"version":1,"amount":0.5},
            "root_sample":sample_fixture(),"tip_sample":{"version":1,"domain":"source-normalized","objects":[]},
            "ownership_confirmed":true}))
    }
    fn preview_result(request: &Value) -> Value {
        // A fixed PNG fixture, not a generated/product image or inference output.
        let encoded = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j0xkAAAAASUVORK5CYII=";
        let bytes = STANDARD.decode(encoded).unwrap();
        let mut payload = json!({"preview_id":"1".repeat(32),"review_token":"2".repeat(64),
            "preview_sha256":"2".repeat(64),"sample_asset_sha256":"b".repeat(64),"face_ref":context()["target"]["face_ref"],
            "source":{"sha256":"a".repeat(64),"width":100,"height":100},
            "recipe":request["payload"]["recipe"],"root_sample":request["payload"]["root_sample"],
            "tip_sample":request["payload"]["tip_sample"]});
        for prefix in ["before", "after", "support"] {
            payload[format!("{prefix}_png")] = json!(format!("data:image/png;base64,{encoded}"));
            payload[format!("{prefix}_sha256")] = json!(format!("{:x}", Sha256::digest(&bytes)));
            payload[format!("{prefix}_width")] = json!(1);
            payload[format!("{prefix}_height")] = json!(1);
        }
        result(request, payload)
    }
    fn acknowledgment(preview: &Value) -> Value {
        let mut value = json!({});
        for key in ["preview_id", "review_token", "before_sha256", "after_sha256", "support_sha256"] {
            value[key] = preview["payload"][key].clone();
        }
        value
    }
    #[test]
    fn exact_envelope_and_manual_source_vectors_only() {
        let valid = preview_request(); assert!(validate(&valid).is_ok());
        for path in ["/protocol", "/operation_id", "/people_context/target/scope", "/payload/root_sample/domain"] {
            let mut changed = valid.clone(); *changed.pointer_mut(path).unwrap() = json!("wrong");
            assert!(validate(&changed).is_err());
        }
        let mut changed = valid.clone(); changed["payload"]["root_sample"]["objects"][0]["kind"] = json!("semantic");
        assert!(validate(&changed).is_err());
        let mut changed = valid.clone(); changed["payload"]["recipe"]["amount"] = json!(0);
        assert!(validate(&changed).is_err());
        let mut changed = valid; changed["extra"] = json!(true); assert!(validate(&changed).is_err());
    }
    #[test]
    fn strict_context_payload_epoch_and_first_terminal_binding() {
        let req = request("clear", "clear", json!({})); let done = result(&req, json!({"kind":"clear"}));
        for path in ["/event", "/operation_id", "/action", "/document_id", "/people_context/document_revision", "/request_payload"] {
            let mut host = host(); admit(&mut host, &req);
            let mut wrong = done.clone(); *wrong.pointer_mut(path).unwrap() = json!("changed");
            assert!(host.observe(EPOCH, &wrong).is_none()); assert!(!host.rows[0].settled);
        }
        let mut host = host(); admit(&mut host, &req);
        assert!(host.observe([68;16], &done).is_none()); assert!(!host.rows[0].settled);
        assert!(host.observe(EPOCH, &done).is_some());
        assert!(host.observe(EPOCH, &failure(&req, "contradiction")).is_none());
        assert_eq!(host.status("clear")["result"], done);
    }
    #[test]
    fn only_validated_mutations_produce_recovery_markers() {
        let mut host = host(); let read = request("context", "context", json!({})); admit(&mut host, &read);
        assert!(host.observe(EPOCH, &result(&read, json!({}))).is_none()); assert!(host.rows[0].settled);
        let clear = request("clear", "clear", json!({})); admit(&mut host, &clear);
        assert!(host.observe(EPOCH, &failure(&clear, "lost reply")).is_none()); assert!(!host.rows[1].settled);
        assert!(host.observe(EPOCH, &result(&clear, json!({}))).is_some());
    }
    #[test]
    fn metadata_only_or_foreign_publication_cannot_settle_mutation() {
        let req = request("clear", "clear", json!({})); let done = result(&req, json!({}));
        for path in ["/payload", "/doc_state/people/binding/asset_sha256", "/doc_state/people/binding/document_epoch",
            "/doc_state/people/resolved/face_ref", "/doc_state/people/resolved/operations/lnx.hair_unification.v1/~1amount/value"] {
            let mut changed = done.clone(); *changed.pointer_mut(path).unwrap() = json!({});
            let mut host = host(); admit(&mut host, &req);
            assert!(host.observe(EPOCH, &changed).is_none()); assert!(!host.rows[0].settled);
        }
    }
    #[test]
    fn png_bytes_dimensions_and_presented_tuple_are_bound() {
        let req = preview_request(); let good = preview_result(&req); assert!(valid_result(&good, &req));
        for key in ["before_sha256", "after_sha256", "support_sha256", "preview_sha256"] {
            let mut changed = good.clone(); changed["payload"][key] = json!("3".repeat(64));
            assert!(!valid_result(&changed, &req));
        }
        let mut changed = good.clone(); changed["payload"]["before_width"] = json!(2); assert!(!valid_result(&changed, &req));
        let mut host = host(); admit(&mut host, &req); host.observe(EPOCH, &good);
        let mut presented = request("presented", "presented", acknowledgment(&good));
        presented["payload"]["support_sha256"] = json!("4".repeat(64)); assert!(host.begin(EPOCH, &presented).is_err());
        presented["payload"] = acknowledgment(&good); admit(&mut host, &presented);
        let mut payload = presented["payload"].clone(); payload["kind"] = json!("presented"); payload["presented"] = json!(true);
        assert!(host.observe(EPOCH, &result(&presented, payload)).is_none()); assert!(host.rows.back().unwrap().settled);
        let commit = request("commit", "commit", json!({"preview_id":good["payload"]["preview_id"],
            "review_token":good["payload"]["review_token"],"confirmed":true}));
        admit(&mut host, &commit);
        let mut foreign = result(&commit, json!({})); foreign["payload"]["asset_sha256"] = json!("c".repeat(64));
        assert!(host.observe(EPOCH, &foreign).is_none()); assert!(!host.rows.back().unwrap().settled);
        assert!(host.observe(EPOCH, &result(&commit, json!({}))).is_some());
        let mut second = commit.clone(); second["request_id"] = json!("second-commit");
        assert!(host.begin(EPOCH, &second).is_err());
    }
    #[test]
    fn commit_without_retained_presented_proof_is_never_admitted() {
        let mut host = host(); let req = preview_request(); let preview = preview_result(&req);
        admit(&mut host, &req); host.observe(EPOCH, &preview);
        let commit = request("commit", "commit", json!({"preview_id":"1".repeat(32),"review_token":"2".repeat(64),"confirmed":true}));
        assert!(host.begin(EPOCH, &commit).is_err()); assert!(!host.seen.contains_key("commit"));
    }
    #[test]
    fn missing_native_allows_context_and_neutral_clear_not_preview() {
        let mut host = host(); host.native_available = false;
        host.begin(EPOCH, &request("context", "context", json!({}))).unwrap();
        host.begin(EPOCH, &request("clear", "clear", json!({}))).unwrap();
        assert!(host.begin(EPOCH, &preview_request()).is_err());
    }
    #[test]
    fn old_terminal_and_unknown_mutation_survive_engine_replacement() {
        let mut host = host(); let read = request("context", "context", json!({})); admit(&mut host, &read);
        let done = result(&read, json!({})); host.observe(EPOCH, &done);
        let clear = request("clear", "clear", json!({})); admit(&mut host, &clear);
        host.end(EPOCH); host.epoch = [68;16]; host.ended = false; host.supported = true; host.native_available = true;
        assert_eq!(host.status("context")["result"], done);
        assert_eq!(host.status("clear")["result"]["outcome_unknown"], true);
        assert!(host.begin([68;16], &request("new-clear", "clear", json!({}))).is_err());
        assert!(host.replay(&clear).unwrap());
        assert!(host.observe(EPOCH, &result(&clear, json!({}))).is_some());
    }
    #[test]
    fn native_reopen_marks_retired_unknown_reads_but_never_settled_outcomes() {
        let mut host = host();
        let settled = request("settled", "context", json!({})); admit(&mut host, &settled);
        let terminal = result(&settled, json!({})); host.observe(EPOCH, &terminal);
        let read = request("retired-read", "context", json!({})); admit(&mut host, &read);
        let clear = request("uncertain-clear", "clear", json!({})); admit(&mut host, &clear);
        host.end(EPOCH); assert!(host.rows[1].retired); assert!(!host.rows[2].retired);
        let replacement = [68;16]; host.epoch = replacement; host.ended = false;
        let opened = json!({"event":"project_opened","docs":1});
        host.reopen(EPOCH, &opened);
        host.reopen(replacement, &json!({"event":"project_opened"}));
        assert!(host.status("retired-read")["result"].get("workspace_reopened").is_none());
        host.reopen(replacement, &opened);
        for original in [&read, &clear] {
            let result = host.status(original["request_id"].as_str().unwrap())["result"].clone();
            assert_eq!(result["workspace_reopened"], true); assert_eq!(result["success"], false);
            assert_eq!(result["outcome_unknown"], true);
            for key in ["protocol", "operation_id", "request_id", "action", "people_context"] {
                assert_eq!(result[key], original[key]);
            }
            assert_eq!(result["request_payload"], original["payload"]);
            assert_eq!(result["document_id"], original["people_context"]["document_id"]);
        }
        assert_eq!(host.status("settled")["result"], terminal);
        assert!(host.rows[2].retired); assert!(host.replay(&clear).unwrap());
    }
    #[test]
    fn backend_cannot_forge_native_workspace_reopen_proof() {
        let original = request("clear", "clear", json!({}));
        for marker in [json!(true), json!(false), Value::Null] {
            let mut host = host(); admit(&mut host, &original);
            let mut forged = result(&original, json!({})); forged["workspace_reopened"] = marker;
            assert!(!valid_result(&forged, &original)); assert!(host.observe(EPOCH, &forged).is_none());
            let retained = host.status("clear")["result"].clone();
            assert_eq!(retained["outcome_unknown"], true); assert!(retained.get("workspace_reopened").is_none());
            assert!(!host.rows[0].settled); assert!(!host.rows[0].retired);
        }
    }
    #[test]
    fn tombstones_prevent_replay_after_terminal_capacity_eviction() {
        let mut host = host(); let first = request("first", "context", json!({})); admit(&mut host, &first);
        host.observe(EPOCH, &result(&first, json!({})));
        for i in 0..MAX_ROWS {
            let req = request(&format!("read-{i}"), "context", json!({})); admit(&mut host, &req);
            host.observe(EPOCH, &result(&req, json!({})));
        }
        assert_eq!(host.status("first")["phase"], "unavailable"); assert!(host.replay(&first).unwrap());
        let mut changed = first; changed["people_context"]["document_revision"] = json!(99);
        assert!(host.replay(&changed).is_err()); assert!(host.rows.len() <= MAX_ROWS);
    }
    #[test]
    fn pending_reservations_and_tombstones_are_bounded_without_eviction() {
        let mut host = host();
        for index in 0..3 { let mut req = preview_request(); req["request_id"] = json!(format!("preview-{index}")); admit(&mut host, &req); }
        let mut extra = preview_request(); extra["request_id"] = json!("extra");
        assert!(host.begin(EPOCH, &extra).is_err()); assert_eq!(host.rows.len(), 3);
        let mut host = self::host(); host.tombstone_bytes = TOMBSTONE_BYTES;
        assert!(host.begin(EPOCH, &request("read", "context", json!({}))).is_err()); assert!(host.rows.is_empty());
    }
    #[test]
    fn unique_json_rejects_duplicate_nested_keys_and_trailing_values() {
        for raw in [r#"{"event":"hair_unification_result","event":"other"}"#,
            r#"{"payload":{"review_token":"a","review_token":"b"}}"#, "{} {}", "{\"number\":1e999}"] {
            assert!(unique_json(raw).is_none());
        }
        assert!(unique_json("{}").is_some());
        assert!(same(&json!({"point":[1,0.5]}), &json!({"point":[1.0,0.5]})));
        assert!(!same(&json!({"point":[1,0.5]}), &json!({"point":[1.0,0.6]})));
    }
}
