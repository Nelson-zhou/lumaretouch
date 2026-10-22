// SPDX-License-Identifier: GPL-3.0-or-later
//! Local sample-library transport. Acceptance is not durability or rollback.
//! Payloads have explicit ownership: poll, consume in the UI, then release. No
//! receipt is evicted to admit a new request, and no request is replayed on restart.
use std::collections::{HashMap, HashSet, VecDeque};
use std::path::Path;
use std::sync::{atomic::{AtomicBool, Ordering}, Arc, Mutex, OnceLock};
use serde_json::{json, Value};
use tauri::State;
use tauri_plugin_dialog::DialogExt;
use crate::{engine::EngineHandle, AppState};

const MAX_REQUEST_BYTES: usize = 8 * 1024 * 1024;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;
const MAX_THUMBNAIL_BYTES: usize = 1_400_000;
const MAX_MAILBOX_BYTES: usize = 16 * 1024 * 1024;
const MAX_RECORDS: usize = 64;
// Bounded process-lifetime replay protection, including released IDs. Exhaustion
// fails before submission rather than forgetting a previous mutation identity.
const MAX_REQUEST_IDS: usize = 65_536;
const MAX_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

fn fields(value: &Value, keys: &[&str]) -> bool {
    value.as_object().is_some_and(|object| object.len() == keys.len()
        && keys.iter().all(|key| object.contains_key(*key)))
}
fn text(value: &Value, max: usize) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max && !s.contains('\0'))
}
fn request_id(value: &Value) -> Option<&str> {
    value.as_str().filter(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b)))
}
fn identifier(value: &Value) -> bool {
    value.as_str().is_some_and(|s| s.len() == 32
        && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn group(value: &Value) -> bool { value == "ungrouped" || identifier(value) }
fn revision(value: &Value) -> bool { value.as_u64().is_some_and(|n| n <= MAX_SAFE_INTEGER) }
fn document_revision(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20
        && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok())
}
fn name(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.trim().is_empty() && s.trim().chars().count() <= 120
        && !s.chars().any(|c| c <= '\u{1f}' || c == '\u{7f}'))
}
fn ids(value: &Value, max: usize, allow_empty: bool, groups: bool) -> bool {
    let Some(items) = value.as_array() else { return false };
    if items.len() > max || (!allow_empty && items.is_empty()) { return false; }
    let mut seen = HashSet::new();
    items.iter().all(|item| (if groups { group(item) } else { identifier(item) })
        && seen.insert(item.as_str().unwrap()))
}
fn local_path(value: &str) -> bool {
    !value.is_empty() && value.len() <= 4096 && !value.contains('\0') && Path::new(value).is_absolute()
}
fn query(value: &Value) -> bool {
    if !fields(value, &["view", "search", "limit", "cursor"]) { return false; }
    let view = &value["view"];
    (matches!(view.as_str(), Some("all" | "ungrouped" | "trash"))
        || (fields(view, &["group"]) && group(&view["group"])))
        && value["search"].as_str().is_some_and(|s| s.chars().count() <= 240 && !s.contains('\0'))
        && value["limit"].as_u64().is_some_and(|n| (1..=100).contains(&n))
        && (value["cursor"].is_null() || value["cursor"].as_str().is_some_and(|s|
            !s.is_empty() && s.len() <= 320 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-=".contains(&b))))
}
fn operation(request: &Value) -> bool {
    let payload = &request["payload"];
    match request["op"].as_str() {
        Some("group_create") => fields(payload, &["name"]) && name(&payload["name"]),
        Some("group_rename" | "sample_rename") => fields(payload, &["id", "name"])
            && identifier(&payload["id"]) && name(&payload["name"]),
        Some("group_delete") => fields(payload, &["id"]) && identifier(&payload["id"]),
        Some("group_reorder") => fields(payload, &["ids"]) && ids(&payload["ids"], 200, false, true),
        Some("import_paths") => fields(payload, &["paths", "group_id"]) && group(&payload["group_id"])
            && payload["paths"].as_array().is_some_and(|paths| !paths.is_empty() && paths.len() <= 1000
                && paths.iter().all(|path| path.as_str().is_some_and(local_path))),
        Some("sample_move") => fields(payload, &["ids", "group_id"])
            && ids(&payload["ids"], 2000, false, false) && group(&payload["group_id"]),
        Some("sample_remove" | "sample_restore") => fields(payload, &["ids"])
            && ids(&payload["ids"], 2000, false, false),
        Some("sample_reorder") => fields(payload, &["ids"]) && ids(&payload["ids"], 2000, true, false),
        _ => false,
    }
}
fn valid_request(value: &Value) -> bool {
    if value.to_string().len() > MAX_REQUEST_BYTES { return false; }
    match value["method"].as_str() {
        Some("snapshot" | "context" | "reclaim_plan") => fields(value, &["method"]),
        Some("thumbnail") => fields(value, &["method", "id"]) && identifier(&value["id"]),
        Some("page") => fields(value, &["method", "query", "expected_revision"])
            && revision(&value["expected_revision"]) && query(&value["query"]),
        Some("select") => fields(value, &["method", "id", "expected_revision"])
            && identifier(&value["id"]) && revision(&value["expected_revision"]),
        Some("command") => fields(value, &["method", "op", "payload", "expected_revision"])
            && revision(&value["expected_revision"]) && operation(value),
        Some("capture") => {
            let context = &value["expected_context"];
            fields(value, &["method", "name", "group_id", "expected_revision", "expected_context"])
                && name(&value["name"]) && group(&value["group_id"]) && revision(&value["expected_revision"])
                && fields(context, &["document_id", "revision"]) && text(&context["document_id"], 128)
                && document_revision(&context["revision"])
        }
        _ => false,
    }
}
fn result_budget(method: &str) -> usize {
    match method {
        "context" => 16 * 1024,
        "snapshot" => 1024 * 1024,
        "thumbnail" => MAX_THUMBNAIL_BYTES + 4096,
        "page" => 4 * 1024 * 1024,
        _ => MAX_RESULT_BYTES,
    }
}
fn failure(id: &str, error: &str, code: &str, unknown: bool) -> Value {
    json!({"event":"sample_library_result", "protocol":1, "request_id":id, "action":"request",
        "success":false, "outcome_unknown":unknown, "committed":if unknown { Value::Null } else { json!(false) },
        "error":error, "error_code":code})
}
fn terminal(id: &str, result: Value) -> Value { json!({"phase":"done", "request_id":id, "result":result}) }

struct Record {
    id: String,
    epoch: [u8; 16],
    method: String,
    budget: usize,
    result: Option<Value>,
    bytes: usize,
    cancel_requested: bool,
}
enum Seen { Admitted, CancelledBeforeAdmission }
#[derive(Default)]
struct Mailbox {
    epoch: [u8; 16],
    supported: bool,
    records: VecDeque<Record>,
    seen: HashMap<String, Seen>,
}
fn mailbox() -> &'static Mutex<Mailbox> {
    static HOST: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    HOST.get_or_init(|| Mutex::new(Mailbox::default()))
}
impl Mailbox {
    fn status(&self, id: &str) -> Value {
        match self.records.iter().find(|record| record.id == id) {
            Some(record) => match &record.result {
                Some(result) => terminal(id, result.clone()),
                None => json!({"phase":"pending", "request_id":id, "cancel_requested":record.cancel_requested}),
            },
            None if matches!(self.seen.get(id), Some(Seen::CancelledBeforeAdmission)) => terminal(id,
                failure(id, "请求在进入引擎队列前已取消，未提交", "cancelled", false)),
            None => json!({"phase":"unavailable", "request_id":id, "outcome_unknown":true,
                "error":"样片回执不可用或已释放；不能据此认定操作没有执行"}),
        }
    }
    fn finish(&mut self, id: &str, result: Value) {
        if let Some(record) = self.records.iter_mut().find(|record| record.id == id && record.result.is_none()) {
            record.bytes = result.to_string().len();
            record.result = Some(result);
        }
    }
    fn end_epoch(&mut self, epoch: [u8; 16]) {
        for record in &mut self.records {
            if record.epoch == epoch && record.result.is_none() {
                let result = failure(&record.id, "引擎结束前未确认操作结果，请核对目录，不要自动重试", "outcome_unknown", true);
                record.bytes = result.to_string().len();
                record.result = Some(result);
            }
        }
    }
    fn begin(&mut self, epoch: [u8; 16], id: &str, method: &str) -> Result<(), &'static str> {
        if epoch == [0; 16] || self.epoch != epoch || !self.supported { return Err("样片引擎已变化或未声明协议，未提交"); }
        if self.seen.contains_key(id) { return Err("样片请求身份已使用，未重新提交"); }
        if self.seen.len() >= MAX_REQUEST_IDS { return Err("样片请求身份预算已满，请重启应用，未提交"); }
        let budget = result_budget(method);
        let reserved: usize = self.records.iter().map(|record| if record.result.is_some() { record.bytes } else { record.budget }).sum();
        if self.records.len() >= MAX_RECORDS || reserved + budget > MAX_MAILBOX_BYTES {
            return Err("样片回执邮箱已满，请等待并释放已读回执，未提交");
        }
        self.seen.insert(id.into(), Seen::Admitted);
        self.records.push_back(Record { id:id.into(), epoch, method:method.into(), budget, result:None, bytes:0, cancel_requested:false });
        Ok(())
    }
}

pub(crate) fn reset(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() {
        let previous = host.epoch;
        host.end_epoch(previous);
        host.epoch = epoch;
        host.supported = false;
    }
}
pub(crate) fn ready(epoch: [u8; 16], supported: bool) {
    if let Ok(mut host) = mailbox().lock() { if host.epoch == epoch { host.supported = supported; } }
}
pub(crate) fn ended(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() {
        host.end_epoch(epoch);
        if host.epoch == epoch { host.supported = false; }
    }
}
fn valid_result(method: &str, value: &Value) -> bool {
    if !value.is_object() { return false; }
    match method {
        "snapshot" => value["version"] == 1 && revision(&value["revision"])
            && value.get("samples").is_none() && ids(&value["order_ids"], 2000, true, false)
            && value["groups"].as_array().is_some_and(|groups| !groups.is_empty() && groups.len() <= 200
                && groups.iter().all(|item| fields(item, &["id", "name"]) && group(&item["id"]) && name(&item["name"]))),
        "page" => revision(&value["revision"]) && value["samples"].as_array().is_some_and(|items| items.len() <= 100)
            && value["limit"].as_u64().is_some_and(|n| (1..=100).contains(&n))
            && revision(&value["offset"]) && revision(&value["total"]),
        "thumbnail" => fields(value, &["data_url"]) && value["data_url"].as_str().is_some_and(|s|
            s.len() <= MAX_THUMBNAIL_BYTES && s.strip_prefix("data:image/jpeg;base64,").is_some_and(|data|
                !data.is_empty() && data.bytes().all(|b| b.is_ascii_alphanumeric() || b"+/=".contains(&b)))),
        "context" => value["available"].is_boolean() && value["document_id"].is_string()
            && value["load_id"].as_str().is_some_and(|s| s.len() <= 128 && !s.contains('\0'))
            && document_revision(&value["revision"]) && value["key"].is_string() && value["label"].is_string()
            && (value["available"] != true || (text(&value["load_id"], 128)
                && text(&value["document_id"], 128) && text(&value["key"], 512))),
        "command" | "select" | "capture" => revision(&value["revision"])
            && value.get("samples").is_none() && value.get("snapshot").is_none()
            && ids(&value["affected_ids"], 20_000, true, false)
            && value.get("outcomes").map_or(true, |items| items.as_array().is_some_and(|items| items.len() <= 1000)),
        "reclaim_plan" => value["safe_to_delete"] == false,
        _ => false,
    }
}
pub(crate) fn receive(epoch: [u8; 16], value: &Value) {
    let Some(id) = request_id(&value["request_id"]) else { return };
    let Ok(mut host) = mailbox().lock() else { return };
    let Some(record) = host.records.iter().find(|record| record.id == id && record.epoch == epoch && record.result.is_none()) else { return };
    let valid = value["event"] == "sample_library_result" && value["protocol"] == 1 && value["action"] == "request"
        && value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
        && value.get("committed").map_or(true, |v| v.is_null() || v.is_boolean())
        && value.to_string().len() <= record.budget.min(MAX_RESULT_BYTES)
        && if value["success"] == true {
            value["outcome_unknown"] == false && valid_result(&record.method, &value["result"])
        } else { text(&value["error"], 4096) && value.get("error_code").map_or(true, |code| text(code, 128)) };
    let result = if valid { value.clone() } else {
        failure(id, "样片回执无效或超出大小限制；实际写入结果未知，请核对目录", "invalid_receipt", true)
    };
    host.finish(id, result);
}

/// Called under the engine lock before editor intent enters the normal queue.
/// Only pending captures are cancelled; importing local files is independent of edits.
pub(crate) fn invalidate_captures(handle: &EngineHandle) -> Result<(), String> {
    let mut host = mailbox().lock().map_err(|_| "样片回执锁失败")?;
    for record in &mut host.records {
        if record.epoch == handle.epoch() && record.method == "capture" && record.result.is_none() && !record.cancel_requested {
            handle.cancel_sample_library(&record.id)?;
            record.cancel_requested = true;
        }
    }
    Ok(())
}
pub(crate) fn invalidates_capture(command: &Value) -> bool {
    // Conservative intent fence: exempt only explicitly read-only command shapes.
    // Unknown/new editing commands must not save the previously visible result.
    match command["cmd"].as_str().unwrap_or("") {
        "hello" | "inspection_snapshot" | "color_scopes" | "color_capture"
        | "source_patch_capture" | "white_balance_capture" | "color_picker_capture"
        | "color_picker_probe" | "prompted_masks" | "effect_recovery_preview"
        | "manual_liquify_preview" | "studio_background_preview" | "optics_preview"
        | "sky_replacement_preview" | "sample_library" | "sample_library_cancel" => false,
        _ => !matches!(command["action"].as_str(), Some("state" | "list" | "get" | "status" | "limits" | "preflight")),
    }
}
fn cancel(state: &AppState, id: &str) -> Result<Value, String> {
    let guard = state.engine.lock().map_err(|_| "引擎锁失败")?;
    let mut host = mailbox().lock().map_err(|_| "样片回执锁失败")?;
    if !host.records.iter().any(|record| record.id == id) {
        if !host.seen.contains_key(id) {
            // A timed-out IPC may arrive after its cancel control. Preserve this
            // negative admission proof so the late request cannot start a write.
            if host.seen.len() < MAX_REQUEST_IDS {
                host.seen.insert(id.into(), Seen::CancelledBeforeAdmission);
                return Ok(host.status(id));
            }
            // begin() permanently refuses new IDs once this fixed budget is full.
            return Ok(terminal(id, failure(id, "请求身份预算已满，未提交", "not_submitted", false)));
        }
        return Ok(host.status(id));
    }
    let record = host.records.iter_mut().find(|record| record.id == id).unwrap();
    if record.result.is_some() { return Ok(host.status(id)); }
    let handle = guard.as_ref().filter(|handle| handle.epoch() == record.epoch && handle.is_alive());
    if let Some(handle) = handle {
        if !record.cancel_requested {
            // Failure to send cancellation is not failure of the original request.
            // Keep its receipt pending; the caller can still observe real completion.
            if let Err(error) = handle.cancel_sample_library(id) {
                return Ok(json!({"phase":"pending", "request_id":id, "cancel_requested":false,
                    "cancel_error":error, "outcome_unknown":true}));
            }
            record.cancel_requested = true;
        }
    }
    // stdout may already be closed while accepted receipts are still draining.
    // Only ended(), after that drain, may synthesize an unknown terminal outcome.
    Ok(host.status(id))
}

#[tauri::command]
pub(crate) fn sample_library(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = request_id(&request["request_id"]).ok_or("样片请求身份无效")?;
    let action = request["action"].as_str().ok_or("样片请求动作无效")?;
    match action {
        "status" | "release" | "cancel" => {
            if !fields(&request, &["action", "request_id"]) { return Err("样片控制请求字段无效".into()); }
            if action == "cancel" { return cancel(&state, id); }
            let mut host = mailbox().lock().map_err(|_| "样片回执锁失败")?;
            if action == "status" { return Ok(host.status(id)); }
            if let Some(index) = host.records.iter().position(|record| record.id == id) {
                if host.records[index].result.is_none() { return Ok(json!({"released":false, "phase":"pending", "request_id":id})); }
                host.records.remove(index);
            }
            return Ok(json!({"released":true, "request_id":id}));
        }
        "request" => (),
        _ => return Err("未知样片动作".into()),
    }
    let host = mailbox().lock().map_err(|_| "样片回执锁失败")?;
    // A duplicate is an observation of the original operation, never a resend.
    if host.records.iter().any(|record| record.id == id) { return Ok(host.status(id)); }
    if host.seen.contains_key(id) { return Ok(host.status(id)); }
    drop(host);
    let refuse = |error: &str, code: &str| terminal(id, failure(id, error, code, false));
    if !fields(&request, &["action", "request_id", "request"]) || !valid_request(&request["request"]) {
        return Ok(refuse("样片请求格式、大小、名称、路径或版本无效，未提交", "invalid_request"));
    }
    let guard = match state.engine.lock() {
        Ok(guard) => guard,
        Err(_) => return Ok(refuse("引擎锁不可用，未提交", "engine_unavailable")),
    };
    let Some(handle) = guard.as_ref().filter(|handle| handle.is_alive()) else {
        return Ok(refuse("引擎尚未启动或已退出，未提交", "engine_unavailable"));
    };
    let mut host = mailbox().lock().map_err(|_| "样片回执锁失败")?;
    // Recheck after acquiring the engine lock: another caller may have admitted ID.
    if host.seen.contains_key(id) { return Ok(host.status(id)); }
    if let Err(error) = host.begin(handle.epoch(), id, request["request"]["method"].as_str().unwrap()) {
        return Ok(refuse(error, "not_submitted"));
    }
    // Do not use AppState::send_to_engine: library reads must not invalidate
    // editor previews, captures, document reports or history state.
    let command = json!({"cmd":"sample_library", "request_id":id, "action":"request", "request":request["request"]});
    if let Err(error) = handle.send(command) {
        // Dispatcher::enqueue errors mean the command was not inserted. A later
        // stdin write failure is instead handled by engine-ended unknown receipts.
        host.finish(id, failure(id, &error, "not_submitted", false));
        return Ok(host.status(id));
    }
    Ok(json!({"requested":true, "phase":"pending", "request_id":id}))
}

static PICKER_OPEN: AtomicBool = AtomicBool::new(false);
struct PickerGuard;
impl Drop for PickerGuard { fn drop(&mut self) { PICKER_OPEN.store(false, Ordering::Release); } }

#[tauri::command]
pub(crate) async fn sample_library_choose(app: tauri::AppHandle, kind: String) -> Result<Option<Vec<String>>, String> {
    if kind != "images" && kind != "folder" { return Err("样片选择类型无效".into()); }
    if PICKER_OPEN.swap(true, Ordering::AcqRel) { return Err("样片文件选择器已打开".into()); }
    let guard = PickerGuard;
    // Existing native dialog plugin only returns paths. No upload, photo read,
    // preview decoder, file permission expansion or additional dependency here.
    tauri::async_runtime::spawn_blocking(move || -> Result<Option<Vec<String>>, String> {
        let _guard = guard;
        let chooser = app.dialog().file().set_title("选择本地样片（保留原文件）");
        let selected = if kind == "folder" { chooser.blocking_pick_folder().map(|path| vec![path]) }
            else { chooser.add_filter("样片图片", &["jpg", "jpeg", "png", "tif", "tiff", "webp"]).blocking_pick_files() };
        let Some(selected) = selected else { return Ok(None) };
        if selected.is_empty() || selected.len() > 1000 { return Err("每次最多选择 1000 张样片，未截断选择".into()); }
        let mut paths = Vec::with_capacity(selected.len());
        for selected in selected {
            let path = selected.into_path().map_err(|_| "只接受本机文件路径，不接受网络或内容 URI")?;
            let path = path.to_str().filter(|path| local_path(path)).ok_or("样片路径不是有效的本地绝对路径或超过 4096 字节")?;
            paths.push(path.to_owned());
        }
        if json!(paths).to_string().len() > MAX_REQUEST_BYTES - 4096 { return Err("所选路径总长度超出请求预算，未截断选择".into()); }
        Ok(Some(paths))
    }).await.map_err(|error| error.to_string())?
}
