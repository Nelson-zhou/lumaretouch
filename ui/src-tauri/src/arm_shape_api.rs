// SPDX-License-Identifier: GPL-3.0-or-later
//! Epoch-bound arm receipts. Proposal jobs never authorize image mutations.
//! Released request identities remain tombstoned for the process lifetime.
use std::{collections::{HashSet, VecDeque}, sync::{Arc, Mutex, OnceLock}};
use serde_json::{json, Value};
use tauri::State;
use crate::{engine::EngineHandle, AppState};

const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;
const MAX_BYTES: usize = 32 * 1024 * 1024;
const CANCEL_BYTES: usize = 64 * 1024;
const MAX_RECORDS: usize = 32;
const SEGMENTS: [&str; 4] = ["left_upper", "left_forearm", "right_upper", "right_forearm"];
const FLAGS: [&str; 8] = ["joints_visible", "entire_segment_visible", "not_crossing",
    "not_foreshortened", "clear_torso_border", "ownership_confirmed",
    "visible_material_only", "transition_pixels_reviewed"];

fn fields(v: &Value, keys: &[&str]) -> bool {
    v.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|key| o.contains_key(*key)))
}
fn token(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b)))
}
fn text(v: &Value, max: usize) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max && !s.contains('\0'))
}
fn revision(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
fn digest(v: &Value) -> bool {
    v.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn binding(v: &Value) -> bool {
    fields(v, &["document_id", "document_epoch", "document_revision", "asset_sha256"])
        && token(&v["document_id"]) && token(&v["document_epoch"])
        && revision(&v["document_revision"]) && digest(&v["asset_sha256"])
}
fn body_ref(v: &Value) -> bool {
    fields(v, &["asset_sha256", "body_instance_id", "analysis_revision"])
        && digest(&v["asset_sha256"]) && token(&v["body_instance_id"]) && revision(&v["analysis_revision"])
}
fn unit(v: &Value) -> bool { v.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n)) }
fn segment(v: &Value) -> bool { v.as_str().is_some_and(|s| SEGMENTS.contains(&s)) }
fn strategy(v: &Value) -> bool { matches!(v.as_str(), Some("reviewed-contour" | "sam2-prompted-contour")) }
fn recipe(v: &Value) -> bool {
    fields(v, &["version", "strategy", "amount"]) && v["version"].as_u64() == Some(1)
        && strategy(&v["strategy"]) && unit(&v["amount"])
}
fn family(v: &Value) -> bool { fields(v, &SEGMENTS) && SEGMENTS.iter().all(|key| recipe(&v[*key])) }
fn rectangle(v: &Value) -> bool {
    v.as_array().is_some_and(|a| a.len() == 4 && a.iter().all(unit)
        && a[0].as_f64() < a[2].as_f64() && a[1].as_f64() < a[3].as_f64())
}
fn region(v: &Value) -> bool {
    fields(v, &["selection_box", "exclusions"]) && rectangle(&v["selection_box"])
        && v["exclusions"].as_array().is_some_and(|a| (1..=32).contains(&a.len()) && a.iter().all(rectangle))
}
fn widths(v: &Value) -> bool {
    // The backend checks these source-normalized widths against the measured
    // segment axis. A panorama's short-edge normalization can exceed one.
    v.as_array().is_some_and(|a| a.len() == 9
        && a.iter().all(|n| n.as_f64().is_some_and(|n| n.is_finite() && n > 0.0)))
}
fn confirmations(v: &Value) -> bool { fields(v, &FLAGS) && FLAGS.iter().all(|key| v[*key] == true) }
fn anchors(v: &Value, key: &Value) -> bool {
    match key.as_str() {
        Some("left_upper") => *v == json!([11, 13]),
        Some("left_forearm") => *v == json!([13, 15]),
        Some("right_upper") => *v == json!([12, 14]),
        Some("right_forearm") => *v == json!([14, 16]),
        _ => false,
    }
}
fn valid_payload(action: &str, v: &Value) -> bool {
    match action {
        "recipe" => {
            if !fields(v, &["base", "recipe", "targets", "linked"]) || !family(&v["base"])
                || !family(&v["recipe"]) || !v["linked"].is_boolean() { return false; }
            let Some(targets) = v["targets"].as_array().filter(|a| !a.is_empty() && a.len() <= 4) else { return false };
            let mut seen = HashSet::new();
            if !targets.iter().all(|key| segment(key) && seen.insert(key.as_str().unwrap())) { return false; }
            if SEGMENTS.iter().any(|key| !seen.contains(key) && v["base"][*key] != v["recipe"][*key]) { return false; }
            if v["linked"] == true {
                for (left, right) in [("left_upper", "right_upper"), ("left_forearm", "right_forearm")] {
                    if seen.contains(left) != seen.contains(right)
                        || (seen.contains(left) && v["recipe"][left] != v["recipe"][right]) { return false; }
                }
            }
            true
        }
        "support_review" => {
            if !fields(v, &["segment", "strategy", "points_sha256", "visible_anchors", "ownership_confirmed",
                "confirmations", "manual", "proposal_id", "candidate"])
                || !segment(&v["segment"]) || !strategy(&v["strategy"]) || !digest(&v["points_sha256"])
                || !anchors(&v["visible_anchors"], &v["segment"]) || v["ownership_confirmed"] != true
                || !confirmations(&v["confirmations"]) { return false; }
            if v["strategy"] == "reviewed-contour" {
                fields(&v["manual"], &["negative", "positive", "region"])
                    && widths(&v["manual"]["negative"]) && widths(&v["manual"]["positive"])
                    && region(&v["manual"]["region"]) && v["proposal_id"].is_null() && v["candidate"].is_null()
            } else {
                v["manual"].is_null() && token(&v["proposal_id"]) && v["candidate"].as_u64().is_some_and(|n| n < 3)
            }
        }
        "operation_status" => fields(v, &["segment", "enabled"]) && segment(&v["segment"]) && v["enabled"].is_boolean(),
        "proposal" => fields(v, &["segment", "region", "device"]) && segment(&v["segment"])
            && region(&v["region"]) && matches!(v["device"].as_str(), Some("cpu" | "cuda")),
        _ => false,
    }
}
fn envelope(v: &Value, proposal: bool) -> bool {
    fields(v, &["request_id", "gesture_id", "document_id", "document_epoch", "document_revision", "state_revision",
        "association_revision", "people_association_revision", "body_graph_sha256", "people_graph_sha256",
        "body_ref", "family_id", "action", "payload"])
        && ["request_id", "gesture_id", "document_id", "document_epoch"].iter().all(|key| token(&v[*key]))
        && ["document_revision", "state_revision", "association_revision", "people_association_revision"].iter().all(|key| revision(&v[*key]))
        && digest(&v["body_graph_sha256"]) && digest(&v["people_graph_sha256"]) && body_ref(&v["body_ref"])
        && v["family_id"] == "lnx.arm_shape.v1"
        && (if proposal { v["action"] == "proposal" } else { matches!(v["action"].as_str(), Some("recipe" | "support_review" | "operation_status")) })
        && valid_payload(v["action"].as_str().unwrap_or(""), &v["payload"])
}
fn valid_request(action: &str, v: &Value) -> bool {
    if v.to_string().len() > MAX_REQUEST_BYTES { return false; }
    match action {
        "view" => fields(v, &[]),
        "select" => fields(v, &["binding", "body_ref"]) && binding(&v["binding"]) && body_ref(&v["body_ref"])
            && v["binding"]["asset_sha256"] == v["body_ref"]["asset_sha256"],
        "execute" => envelope(v, false),
        "status" => fields(v, &["request_id"]) && token(&v["request_id"]),
        "proposal_start" => envelope(v, true),
        "proposal_status" | "proposal_cancel" => fields(v, &["job_id"]) && token(&v["job_id"]),
        _ => false,
    }
}

struct Record {
    id: String, action: String, epoch: [u8; 16], request: Value,
    result: Option<Value>, request_bytes: usize, result_bytes: usize,
}
#[derive(Default)]
struct Mailbox { epoch: [u8; 16], supported: bool, seen: HashSet<String>, records: VecDeque<Record> }
fn mailbox() -> &'static Mutex<Mailbox> {
    static HOST: OnceLock<Mutex<Mailbox>> = OnceLock::new();
    HOST.get_or_init(|| Mutex::new(Mailbox::default()))
}
fn failure(id: &str, action: &str, error: &str, unknown: bool) -> Value {
    json!({"event":"arm_shape_result", "protocol":1, "request_id":id, "action":action,
        "success":false, "outcome_unknown":unknown, "error":error})
}
fn terminal(id: &str, result: Value) -> Value { json!({"phase":"done", "request_id":id, "result":result}) }
fn reservation(action: &str) -> usize { if action == "proposal_cancel" { CANCEL_BYTES } else { MAX_RESULT_BYTES } }
impl Mailbox {
    fn status(&self, id: &str) -> Value {
        match self.records.iter().find(|r| r.id == id) {
            Some(r) => match &r.result {
                Some(value) => terminal(id, value.clone()),
                None => json!({"phase":"pending", "request_id":id}),
            },
            None => json!({"phase":"unavailable", "request_id":id, "outcome_unknown":true,
                "error":"手臂回执不可用，不能认定操作没有执行"}),
        }
    }
    fn existing(&self, id: &str, action: &str, request: &Value) -> Option<Value> {
        if !self.seen.contains(id) { return None; }
        if self.records.iter().any(|r| r.id == id && (r.action != action || r.request != *request)) {
            return Some(terminal(id, failure(id, action, "手臂请求身份已被其他内容使用，原结果仍需查询，不会重发", true)));
        }
        Some(self.status(id))
    }
    fn end(&mut self, epoch: [u8; 16]) {
        for r in &mut self.records {
            if r.epoch == epoch && r.result.is_none() {
                let value = failure(&r.id, &r.action, "引擎退出前未确认手臂结果，请核对，不会自动重发", true);
                r.result_bytes = value.to_string().len(); r.result = Some(value);
            }
        }
        if self.epoch == epoch { self.supported = false; }
    }
    fn finish(&mut self, id: &str, value: Value) {
        if let Some(r) = self.records.iter_mut().find(|r| r.id == id && r.result.is_none()) {
            r.result_bytes = value.to_string().len(); r.result = Some(value);
        }
    }
    fn begin(&mut self, epoch: [u8; 16], id: &str, action: &str, request: &Value) -> Result<(), String> {
        if epoch == [0; 16] || epoch != self.epoch || !self.supported {
            return Err("引擎变化或未声明手臂协议，未提交".into());
        }
        if self.seen.contains(id) { return Err("手臂请求身份已用过，不会重发".into()); }
        let request_bytes = request.to_string().len();
        let used: usize = self.records.iter().map(|r| r.request_bytes
            + if r.result.is_some() { r.result_bytes } else { reservation(&r.action) }).sum();
        // Ordinary admissions cannot consume the final small cancellation slot.
        let (record_limit, byte_limit) = if action == "proposal_cancel" { (MAX_RECORDS, MAX_BYTES) }
            else { (MAX_RECORDS - 1, MAX_BYTES - CANCEL_BYTES - MAX_REQUEST_BYTES) };
        let id_limit = if action == "proposal_cancel" { 65_536 } else { 65_535 };
        if self.seen.len() >= id_limit || self.records.len() >= record_limit
            || used + request_bytes + reservation(action) > byte_limit {
            return Err("手臂回执预算已满，请先查询并释放已有结果".into());
        }
        self.seen.insert(id.into());
        self.records.push_back(Record { id: id.into(), action: action.into(), epoch,
            request: request.clone(), result: None, request_bytes, result_bytes: 0 });
        Ok(())
    }
}
pub(crate) fn reset(epoch: [u8; 16]) {
    if let Ok(mut host) = mailbox().lock() { let old = host.epoch; host.end(old); host.epoch = epoch; host.supported = false; }
}
pub(crate) fn ready(epoch: [u8; 16], supported: bool) {
    if let Ok(mut host) = mailbox().lock() { if host.epoch == epoch { host.supported = supported; } }
}
pub(crate) fn ended(epoch: [u8; 16]) { if let Ok(mut host) = mailbox().lock() { host.end(epoch); } }

fn dimensions(v: &Value) -> bool {
    ["width", "height"].iter().all(|key| v[*key].as_u64().is_some_and(|n| (2..=1_000_000).contains(&n)))
}
fn source(v: &Value) -> bool {
    fields(v, &["sha256", "width", "height", "orientation"]) && digest(&v["sha256"])
        && dimensions(v) && v["orientation"] == "exif_normalized_once"
}
fn selection(v: &Value) -> bool {
    let mask = &v["mask"]; let b = &v["binding"];
    v["version"].as_u64() == Some(1) && source(&v["source"]) && body_ref(&v["body_ref"])
        && v["source"]["sha256"] == v["body_ref"]["asset_sha256"] && digest(&v["points_sha256"])
        && segment(&v["segment"]) && v["score"].as_f64().is_some_and(f64::is_finite) && digest(&v["runtime_sha256"])
        && matches!(v["actual_device"].as_str(), Some("CPU" | "CUDA" | "ROCm"))
        && fields(b, &["prompts", "candidate", "model", "input_sha256", "device"])
        && b["prompts"].is_object() && b["model"].is_object() && digest(&b["input_sha256"])
        && digest(&b["model"]["checkpoint_sha256"]) && digest(&b["model"]["config_sha256"])
        && b["candidate"].as_u64().is_some_and(|n| n < 3)
        && matches!(b["device"].as_str(), Some("cpu" | "cuda"))
        && (b["device"] == "cpu") == (v["actual_device"] == "CPU")
        && v["ownership"].is_object() && v["ownership"]["asset_sha256"] == v["source"]["sha256"]
        && fields(mask, &["width", "height", "encoding", "chunks", "sha256"])
        && ["width", "height"].iter().all(|key| mask[*key].as_u64().is_some_and(|n| (2..=2048).contains(&n)))
        && mask["encoding"] == "packbits-big-base64" && digest(&mask["sha256"])
        && mask["chunks"].as_array().is_some_and(|chunks| (1..=172).contains(&chunks.len())
            && chunks.iter().all(|c| c.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096
                && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"+/=".contains(&b)))))
}
fn support(v: &Value, key: &str, body: &Value) -> bool {
    fields(v, &["version", "segment", "strategy", "stations", "negative", "positive", "region", "selection", "confirmations"])
        && v["version"].as_u64() == Some(1) && v["segment"] == key && strategy(&v["strategy"])
        && v["stations"] == json!([0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9])
        && widths(&v["negative"]) && widths(&v["positive"]) && region(&v["region"]) && confirmations(&v["confirmations"])
        && if v["strategy"] == "reviewed-contour" { v["selection"].is_null() }
            else { selection(&v["selection"]) && unit(&v["selection"]["score"]) && v["selection"]["segment"] == key
                && v["selection"]["source"] == body["source"] && v["selection"]["body_ref"] == body["body_ref"]
                && v["selection"]["points_sha256"] == body["points_sha256"] }
}
fn valid_view(v: &Value) -> bool {
    if !binding(&v["binding"]) || !["state_revision", "association_revision", "people_association_revision"].iter().all(|key| revision(&v[*key]))
        || !digest(&v["body_graph_sha256"]) || !digest(&v["people_graph_sha256"])
        || !v["refusals"].is_array() || !family(&v["recipe"]) || v["runtime_quality_accepted"] != false { return false; }
    if !v["selected_body_ref"].is_null() && !body_ref(&v["selected_body_ref"]) { return false; }
    let Some(bodies) = v["bodies"].as_array().filter(|b| b.len() <= 128) else { return false };
    if !v["selected_body_ref"].is_null() && !bodies.iter().any(|b| b["body_ref"] == v["selected_body_ref"]) { return false; }
    bodies.iter().all(|body| body_ref(&body["body_ref"]) && body["body_ref"]["asset_sha256"] == v["binding"]["asset_sha256"]
        && body["enabled"].is_boolean() && digest(&body["points_sha256"]) && source(&body["source"])
        && body["source"]["sha256"] == v["binding"]["asset_sha256"]
        && fields(&body["operations"], &SEGMENTS) && SEGMENTS.iter().all(|key| {
            let op = &body["operations"][*key];
            op["enabled"].is_boolean() && op["reviewed"].is_boolean()
                && (op["support"].is_null() || support(&op["support"], key, body))
        })
        && body["points"].as_array().is_some_and(|points| points.len() == 33 && points.iter().enumerate().all(|(index, p)|
            p["index"].as_u64() == Some(index as u64)
                && ["x", "y", "z", "visibility", "presence"].iter().all(|key| p[*key].as_f64().is_some_and(f64::is_finite))
                && unit(&p["visibility"]) && unit(&p["presence"]))))
}
fn valid_source(v: &Value, view: &Value) -> bool {
    let (Some(sw), Some(sh), Some(dw), Some(dh), Some(pw), Some(ph)) = (
        v["source_width"].as_u64(), v["source_height"].as_u64(), v["decoded_width"].as_u64(),
        v["decoded_height"].as_u64(), v["width"].as_u64(), v["height"].as_u64()) else { return false };
    if [sw, sh, dw, dh].iter().any(|n| !(2..=1_000_000).contains(n))
        || dw > sw || dh > sh || !(2..=1280).contains(&pw) || !(2..=1280).contains(&ph) || pw > dw || ph > dh { return false; }
    if (dw != sw || dh != sh) && (dw % 8 != 0 || dh % 8 != 0 || dw * sh >= (dh + 8) * sw || dh * sw >= (dw + 8) * sh) { return false; }
    if dw.max(dh) <= 1280 { if pw != dw || ph != dh { return false; } }
    else if pw.max(ph) != 1280 || (pw * dh).abs_diff(ph * dw) > dw.max(dh) { return false; }
    v["mime"] == "image/png" && text(&v["base64"], 7_000_000)
        && v["source_sha256"] == view["binding"]["asset_sha256"] && v["mapping"] == "normalized_full_frame"
        && v["orientation"] == "exif_normalized_once"
        && view["bodies"].as_array().is_some_and(|b| b.iter().all(|body|
            body["source"]["width"] == v["source_width"] && body["source"]["height"] == v["source_height"]))
}
fn context(v: &Value) -> bool {
    fields(v, &["document_id", "document_epoch", "body_graph_sha256", "people_graph_sha256"])
        && token(&v["document_id"]) && token(&v["document_epoch"])
        && digest(&v["body_graph_sha256"]) && digest(&v["people_graph_sha256"])
}
fn proposal(v: &Value) -> bool {
    v["version"].as_u64() == Some(1) && source(&v["source"]) && body_ref(&v["body_ref"])
        && v["source"]["sha256"] == v["body_ref"]["asset_sha256"] && digest(&v["points_sha256"])
        && segment(&v["segment"]) && region(&v["region"]) && v["reviewed"] == false && v["runtime_quality_accepted"] == false
        && v["proposals"].as_array().is_some_and(|rows| rows.len() == 3 && rows.iter().enumerate().all(|(index, row)|
            selection(&row["selection"]) && row["selection"]["binding"]["candidate"].as_u64() == Some(index as u64)
                && ["source", "body_ref", "points_sha256", "segment"].iter().all(|key| row["selection"][*key] == v[*key])
                && if row["refusal"].is_null() { unit(&row["selection"]["score"]) && widths(&row["negative"]) && widths(&row["positive"]) }
                    else { text(&row["refusal"], 8192) && row["negative"].is_null() && row["positive"].is_null() }))
}
fn proposal_receipt(v: &Value, record: &Record) -> bool {
    let id = if record.action == "proposal_start" { &record.request["request_id"] } else { &record.request["job_id"] };
    if v["job_id"] != *id || !v["success"].is_boolean()
        || !matches!(v["phase"].as_str(), Some("pending" | "done" | "unavailable")) { return false; }
    if record.action == "proposal_cancel" && (v["phase"] != "done" || v["success"] != false || !v["proposal"].is_null()) { return false; }
    if let Some(c) = v.get("context") {
        if !context(c) || (record.action == "proposal_start"
            && ["document_id", "document_epoch", "body_graph_sha256", "people_graph_sha256"].iter().any(|key| c[*key] != record.request[*key])) { return false; }
    }
    if v["success"] == true {
        if v["phase"] != "done" || !context(&v["context"]) || !proposal(&v["proposal"]) { return false; }
        if record.action == "proposal_start" && (v["proposal"]["body_ref"] != record.request["body_ref"]
            || v["proposal"]["segment"] != record.request["payload"]["segment"]
            || v["proposal"]["region"] != record.request["payload"]["region"]) { return false; }
    } else if !v["proposal"].is_null() { return false; }
    if v["phase"] == "pending" { context(&v["context"]) && v["success"] == false }
    else { v["success"] == true || text(&v["error"], 8192) }
}
fn edit_receipt(v: &Value, record: &Record) -> bool {
    if v["request_id"] != record.request["request_id"]
        || !matches!(v["phase"].as_str(), Some("pending" | "done" | "unavailable")) { return false; }
    if v.get("protocol").is_some_and(|p| p.as_u64() != Some(1))
        || v.get("success").is_some_and(|p| !p.is_boolean())
        || v.get("outcome_unknown").is_some_and(|p| !p.is_boolean())
        || v.get("view").is_some_and(|p| !valid_view(p)) { return false; }
    if v["phase"] == "done" && (!v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()) { return false; }
    if v["success"] == true {
        if v["phase"] != "done" || v["outcome_unknown"] != false || v["protocol"].as_u64() != Some(1)
            || !valid_view(&v["view"]) || !v["rendered"].is_boolean() { return false; }
        if record.action == "execute" && !bound_view(&v["view"], &record.request) { return false; }
    }
    true
}
fn bound_view(view: &Value, request: &Value) -> bool {
    let b = if request.get("binding").is_some() { &request["binding"] } else { request };
    ["document_id", "document_epoch"].iter().all(|key| view["binding"][*key] == b[*key])
        && view["binding"]["asset_sha256"] == request["body_ref"]["asset_sha256"]
}
fn valid_result(v: &Value, record: &Record) -> bool {
    if v["event"] != "arm_shape_result" || v["protocol"].as_u64() != Some(1) || v["request_id"] != record.id
        || v["action"] != record.action || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()
        || v.to_string().len() > reservation(&record.action) { return false; }
    if v["success"] != true {
        if !text(&v["error"], 8192) { return false; }
        // A rejected/uncertain edit may still carry its authoritative receipt.
        // Validate that identity too before the UI is allowed to reconcile it.
        return v.get("result").map_or(true, |data| data.is_object()
            && matches!(record.action.as_str(), "execute" | "status")
            && edit_receipt(&data["receipt"], record));
    }
    let data = &v["result"];
    if !data.is_object() || data.get("view").is_some_and(|p| !valid_view(p))
        || data.get("model").is_some_and(|p| !p.is_object())
        || data.get("view_error").is_some_and(|p| !text(p, 4096)) { return false; }
    if let Some(preview) = data.get("source_preview") {
        if !valid_view(&data["view"]) || !valid_source(preview, &data["view"]) { return false; }
    }
    match record.action.as_str() {
        "view" => valid_view(&data["view"]) && data["model"].is_object(),
        "select" => valid_view(&data["view"]) && data["model"].is_object()
            && bound_view(&data["view"], &record.request) && data["view"]["selected_body_ref"] == record.request["body_ref"],
        // The retained receipt is authoritative even if the current source was
        // deleted or replaced, so neither route requires a fresh source preview.
        "execute" | "status" => edit_receipt(&data["receipt"], record),
        "proposal_start" | "proposal_status" | "proposal_cancel" => proposal_receipt(&data["proposal"], record),
        _ => false,
    }
}
pub(crate) fn receive(epoch: [u8; 16], v: &Value) -> bool {
    let Some(id) = v["request_id"].as_str() else { return false };
    let Ok(mut host) = mailbox().lock() else { return false };
    let Some(record) = host.records.iter().find(|r| r.id == id && r.epoch == epoch && r.result.is_none()) else { return false };
    let valid = valid_result(v, record);
    let result = if valid { v.clone() } else { failure(id, &record.action, "手臂回执无效，实际结果未知，请核对当前配方", true) };
    host.finish(id, result);
    valid
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "arm_shape" && matches!(v["action"].as_str(),
        Some("view" | "select" | "status" | "proposal_start" | "proposal_status" | "proposal_cancel"))
}
pub(crate) fn enqueue(handle: &EngineHandle, mut command: Value) -> Result<(), String> {
    let epoch = command.as_object_mut().ok_or("手臂命令无效")?.remove("host_epoch").ok_or("手臂命令缺少引擎身份")?;
    if epoch.as_str() != Some(crate::frame_identity::hex(handle.epoch()).as_str()) {
        return Err("引擎已变化，未向新引擎重发手臂操作".into());
    }
    handle.send(command)
}
#[tauri::command]
pub(crate) fn arm_shape(state: State<'_, Arc<AppState>>, request: Value) -> Result<Value, String> {
    let id = request["request_id"].as_str().filter(|_| token(&request["request_id"])).ok_or("手臂请求身份无效")?;
    let action = request["action"].as_str().ok_or("手臂动作无效")?;
    if matches!(action, "mailbox_status" | "release") {
        if !fields(&request, &["action", "request_id"]) { return Err("手臂查询字段无效".into()); }
        let mut host = mailbox().lock().map_err(|_| "手臂回执锁失败")?;
        if action == "mailbox_status" { return Ok(host.status(id)); }
        if let Some(index) = host.records.iter().position(|r| r.id == id) {
            if host.records[index].result.is_none() { return Ok(host.status(id)); }
            host.records.remove(index);
        }
        return Ok(json!({"released":true, "request_id":id}));
    }
    let refused = |why: &str| terminal(id, failure(id, action, why, false));
    {
        let host = mailbox().lock().map_err(|_| "手臂回执锁失败")?;
        if let Some(value) = host.existing(id, action, &request["request"]) { return Ok(value); }
    }
    if !fields(&request, &["action", "request_id", "request"]) || !valid_request(action, &request["request"]) {
        return Ok(refused("手臂命令字段、版本或动作无效，未提交"));
    }
    let epoch = {
        let guard = state.engine.lock().map_err(|_| "引擎锁失败")?;
        let Some(handle) = guard.as_ref().filter(|h| h.is_alive()) else { return Ok(refused("引擎不可用，未提交")) };
        handle.epoch()
    };
    {
        let mut host = mailbox().lock().map_err(|_| "手臂回执锁失败")?;
        if let Some(value) = host.existing(id, action, &request["request"]) { return Ok(value); }
        if let Err(error) = host.begin(epoch, id, action, &request["request"]) { return Ok(refused(&error)); }
    }
    let mut command = request.clone(); command["cmd"] = json!("arm_shape");
    command["host_epoch"] = json!(crate::frame_identity::hex(epoch));
    let sent = if read_only(&command) {
        // Read-only proposal ownership and cancellation must not invalidate an
        // unrelated image capture, semantic draft, or history transaction.
        match state.engine.lock() {
            Ok(guard) => match guard.as_ref() { Some(handle) => enqueue(handle, command), None => Err("引擎已停止，未提交".into()) },
            Err(_) => Err("引擎锁失败，未提交".into()),
        }
    } else { state.send_to_engine(command) };
    if let Err(error) = sent {
        let mut host = mailbox().lock().map_err(|_| "手臂回执锁失败")?;
        host.finish(id, failure(id, action, &error, false)); return Ok(host.status(id));
    }
    Ok(json!({"phase":"pending", "request_id":id, "requested":true}))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn query_and_proposal_inputs_never_accept_mutations_or_source_paths() {
        assert!(valid_request("view", &json!({})));
        assert!(!valid_request("view", &json!({"binding":{}})));
        assert!(!valid_request("proposal_cancel", &json!({"job_id":"job", "path":"/tmp/source"})));
        assert!(!valid_request("install", &json!({})));
        assert!(!body_ref(&json!({"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":0})));
        for action in ["view", "select", "status", "proposal_start", "proposal_status", "proposal_cancel"] {
            assert!(read_only(&json!({"cmd":"arm_shape", "action":action})));
        }
        assert!(!read_only(&json!({"cmd":"arm_shape", "action":"execute"})));
    }
    #[test]
    fn epoch_end_and_release_do_not_allow_replay() {
        let mut host = Mailbox::default(); host.epoch = [1; 16]; host.supported = true;
        host.begin([1; 16], "outer", "execute", &json!({"request_id":"inner"})).unwrap();
        host.end([1; 16]);
        assert_eq!(host.status("outer")["result"]["outcome_unknown"], true);
        host.records.clear(); host.supported = true;
        assert!(host.begin([1; 16], "outer", "execute", &json!({})).is_err());
        assert_eq!(host.status("outer")["phase"], "unavailable");
    }
    #[test]
    fn duplicate_identity_cannot_change_content() {
        let mut host = Mailbox::default(); host.epoch = [1; 16]; host.supported = true;
        host.begin([1; 16], "outer", "view", &json!({})).unwrap();
        assert_eq!(host.existing("outer", "view", &json!({})).unwrap()["phase"], "pending");
        assert_eq!(host.existing("outer", "status", &json!({"request_id":"inner"})).unwrap()["result"]["outcome_unknown"], true);
    }
    #[test]
    fn status_retains_authoritative_failure_without_current_source() {
        let record = Record { id:"outer".into(), action:"status".into(), epoch:[1;16],
            request:json!({"request_id":"inner"}), result:None, request_bytes:0, result_bytes:0 };
        let value = json!({"event":"arm_shape_result", "protocol":1, "request_id":"outer", "action":"status",
            "success":true, "outcome_unknown":false, "result":{"receipt":{"phase":"done", "request_id":"inner",
            "success":false, "outcome_unknown":false, "error":"rejected"}, "view_error":"source missing"}});
        assert!(valid_result(&value, &record));
        let mut wrong = value.clone(); wrong["result"]["receipt"]["request_id"] = json!("other");
        assert!(!valid_result(&wrong, &record));
        wrong = value.clone(); wrong["result"]["view"] = json!({}); assert!(!valid_result(&wrong, &record));
        for phase in ["pending", "unavailable"] {
            let mut uncertain = value.clone();
            uncertain["result"] = json!({"receipt":{"phase":phase, "request_id":"inner"}});
            assert!(valid_result(&uncertain, &record));
        }
        let edit = Record { action:"execute".into(), ..record };
        let mut rejected = value.clone(); rejected["action"] = json!("execute");
        rejected["success"] = json!(false); rejected["error"] = json!("rejected");
        assert!(valid_result(&rejected, &edit));
        rejected["result"]["receipt"]["request_id"] = json!("other");
        assert!(!valid_result(&rejected, &edit));
    }
    #[test]
    fn saturated_data_mailbox_keeps_a_cancellation_slot() {
        let mut host = Mailbox::default(); host.epoch = [1;16]; host.supported = true;
        for id in ["one", "two", "three"] { host.begin([1;16], id, "view", &json!({})).unwrap(); }
        assert!(host.begin([1;16], "four", "view", &json!({})).is_err());
        assert!(host.begin([1;16], "cancel", "proposal_cancel", &json!({"job_id":"job"})).is_ok());
    }
}
