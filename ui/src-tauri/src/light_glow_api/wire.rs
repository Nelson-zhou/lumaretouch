// SPDX-License-Identifier: GPL-3.0-or-later
//! Dedicated creative:211524 protocol v1; current edited-source evidence v3.
use std::collections::HashSet;
use serde_json::{json, Value};
pub(super) use super::json::{digest, fields, same, size, token, unique_json};
use super::json::{bounded, hash, integer, message, number, revision};
use super::imagery::image;

pub(super) const PROTOCOL: u64 = 1;
pub(super) const OPERATION: &str = "lnx.light_glow.v1";
pub(super) const EVENT: &str = "light_glow_result";
pub(super) const COMMAND_BYTES: usize = 16 * 1024;
// Three independently bounded 4 MiB PNGs expand to at most 16 MiB base64.
pub(super) const RESULT_BYTES: usize = 17 * 1024 * 1024;
pub(super) const CONTEXT_BYTES: usize = 6 * 1024 * 1024;
pub(super) const SMALL_BYTES: usize = 32 * 1024;

pub(super) fn capability(v: &Value) -> bool {
    fields(v, &["version","operation_id","status","abi","math_version","reason","modes"])
        && v["version"] == PROTOCOL && v["operation_id"] == OPERATION && v["abi"] == 1 && v["math_version"] == 65537
        && (v["reason"].is_null() || message(&v["reason"]))
        && v["modes"].as_array().is_some_and(|modes| modes.len() <= 3
            && modes.iter().all(|m| matches!(m.as_str(), Some("black_mist"|"white_mist"|"glow")))
            && modes.iter().filter_map(Value::as_str).collect::<HashSet<_>>().len() == modes.len()
            && ((v["status"] == "available" && !modes.is_empty()) || (v["status"] == "unavailable" && modes.is_empty())))
}
pub(super) fn owner(v: &Value) -> bool {
    let s = &v["source"];
    fields(v, &["document_id","document_epoch","document_revision","source"])
        && token(&v["document_id"]) && token(&v["document_epoch"]) && revision(&v["document_revision"])
        && fields(s, &["sha256","width","height","orientation"]) && hash(&s["sha256"])
        && integer(&s["width"], 2, 1_000_000) && integer(&s["height"], 2, 1_000_000)
        && number(&s["width"]) * number(&s["height"]) <= 100_000_000.0 && s["orientation"] == "exif_normalized_once"
}
pub(super) fn evidence(v: &Value, owner: &Value) -> bool {
    fields(v, &["kind","capture_version","original_sha256","people_graph_sha256","repair_stack_sha256","document_revision","load_id","capture_token"])
        && v["kind"] == "current_full_edited_source" && v["capture_version"] == 3
        && ["original_sha256","people_graph_sha256","repair_stack_sha256"].iter().all(|k| hash(&v[*k]))
        && v["document_revision"] == owner["document_revision"] && token(&v["load_id"]) && token(&v["capture_token"])
}
pub(super) fn context(v: &Value) -> bool {
    fields(v, &["version","operation_id","session_id","owner","source_evidence","before","capability","message"])
        && v["version"] == PROTOCOL && v["operation_id"] == OPERATION && token(&v["session_id"])
        && owner(&v["owner"]) && evidence(&v["source_evidence"], &v["owner"])
        && image(&v["before"], &v["owner"]["source"], false) && capability(&v["capability"])
        && v["capability"]["status"] == "available" && message(&v["message"])
}
pub(super) fn recipe(v: &Value) -> bool {
    fields(v, &["version","operation_id","math_identity","mode","strength","radius_px","threshold","exposure_ev","scattering","tint"])
        && v["version"] == 1 && v["operation_id"] == OPERATION && v["math_identity"] == 65537
        && matches!(v["mode"].as_str(), Some("black_mist"|"white_mist"|"glow"))
        && bounded(&v["strength"], 0.0, 1.0) && integer(&v["radius_px"], 0, 512)
        && bounded(&v["threshold"], 0.0, 1.0) && bounded(&v["exposure_ev"], -4.0, 4.0) && bounded(&v["scattering"], 0.0, 1.0)
        && fields(&v["tint"], &["hue_deg","saturation","lightness"]) && bounded(&v["tint"]["hue_deg"], -180.0, 180.0)
        && bounded(&v["tint"]["saturation"], -1.0, 1.0) && bounded(&v["tint"]["lightness"], -1.0, 1.0)
}
pub(super) fn command(v: &Value) -> bool {
    if v["version"] != PROTOCOL || v["operation_id"] != OPERATION || !token(&v["request_id"])
        || !token(&v["session_id"]) || !owner(&v["owner"]) { return false; }
    let mut keys = vec!["version","operation_id","action","request_id","session_id","owner"];
    match v["action"].as_str() {
        Some("preview") => { keys.push("recipe"); fields(v, &keys) && recipe(&v["recipe"]) }
        Some("cancel") => { keys.push("token"); fields(v, &keys) && (v["token"].is_null() || token(&v["token"])) }
        Some("apply") => {
            keys.extend_from_slice(&["token","recipe_sha256","result_source_sha256","coverage_sha256","before_sha256","after_sha256","coverage_image_sha256","reviewed","return_mode"]);
            fields(v, &keys) && token(&v["token"]) && v["reviewed"] == true && v["return_mode"] == "new_image"
                && ["recipe_sha256","result_source_sha256","coverage_sha256","before_sha256","after_sha256","coverage_image_sha256"].iter().all(|k| hash(&v[*k]))
        }
        _ => false,
    }
}
#[derive(Clone)]
pub(super) struct Request { pub envelope: Value, pub id: String, pub action: String, pub signature: String }
impl Request {
    pub fn write(&self) -> bool { self.action == "submit" }
    pub fn apply(&self) -> bool { self.write() && self.inner()["action"] == "apply" }
    pub fn read(&self) -> bool { matches!(self.action.as_str(), "current"|"preview") }
    pub fn inner(&self) -> &Value { &self.envelope["command"] }
}
pub(super) fn parse_request(v: &Value) -> Result<Request,String> {
    size(v, COMMAND_BYTES)?;
    if v["cmd"] != "light_glow" || !token(&v["request_id"]) { return Err("发光原生信封身份无效".into()); }
    let action = v["action"].as_str().ok_or("发光动作缺失")?;
    if action == "current" {
        if !fields(v, &["cmd","action","request_id"]) { return Err("发光当前来源命令含未知字段".into()); }
    } else {
        if !fields(v, &["cmd","action","request_id","command"]) || !command(&v["command"])
            || (action != "receipt" && v["request_id"] != v["command"]["request_id"]) { return Err("发光完整命令身份、字段或版本无效".into()); }
        let inner = v["command"]["action"].as_str().unwrap_or("");
        if !match action { "preview" => inner == "preview", "submit"|"receipt" => matches!(inner, "apply"|"cancel"), _ => false } {
            return Err("发光传输动作与原命令不匹配".into());
        }
        if action == "receipt" && v["request_id"] == v["command"]["request_id"] { return Err("核对必须使用独立查询身份，不得重发原写入".into()); }
    }
    // Local identity only. Python owns its own domain-separated command digest;
    // cancellation echoes the exact original envelope instead of guessing it.
    let signature = digest(serde_json::to_string(v).map_err(|e| e.to_string())?.as_bytes());
    Ok(Request { envelope: v.clone(), id: v["request_id"].as_str().unwrap().into(), action: action.into(), signature })
}
pub(super) fn receipt(v: &Value, c: &Value) -> bool {
    if !command(c) || !matches!(c["action"].as_str(), Some("apply"|"cancel"))
        || v["version"] != PROTOCOL || v["operation_id"] != OPERATION
        || ["request_id","session_id","action","owner","token"].iter().any(|k| !same(&v[*k], &c[*k]))
        || !message(&v["message"]) { return false; }
    let mut keys = vec!["version","operation_id","request_id","session_id","action","owner","token","message","phase","outcome_unknown"];
    if matches!(v["phase"].as_str(), Some("pending"|"unknown")) { return fields(v, &keys) && v["outcome_unknown"] == true; }
    if v["phase"] != "done" || v["outcome_unknown"] != false { return false; }
    keys.push("outcome");
    if matches!(v["outcome"].as_str(), Some("rejected"|"cancelled")) {
        return fields(v, &keys) && (v["outcome"] != "cancelled" || c["action"] == "cancel");
    }
    keys.extend_from_slice(&["result_document_id","copied_original_document_id","result_revision","result_source_sha256","no_change"]);
    fields(v, &keys) && v["outcome"] == "applied" && c["action"] == "apply"
        && token(&v["result_document_id"]) && v["result_document_id"] != c["owner"]["document_id"]
        && v["copied_original_document_id"] == c["owner"]["document_id"] && revision(&v["result_revision"])
        && v["result_source_sha256"] == c["result_source_sha256"]
        && v["no_change"].as_bool() == Some(v["result_source_sha256"] == c["owner"]["source"]["sha256"])
}
pub(super) fn review(v: &Value, c: &Value) -> bool {
    fields(v, &["version","operation_id","request_id","session_id","owner","source_evidence","token","recipe","recipe_sha256",
        "result_source_sha256","coverage_sha256","before","after","coverage","no_change","notes"])
        && v["version"] == PROTOCOL && v["operation_id"] == OPERATION && c["action"] == "preview"
        && ["request_id","session_id","owner","recipe"].iter().all(|k| same(&v[*k], &c[*k]))
        && owner(&v["owner"]) && evidence(&v["source_evidence"], &v["owner"]) && token(&v["token"]) && recipe(&v["recipe"])
        && ["recipe_sha256","result_source_sha256","coverage_sha256"].iter().all(|k| hash(&v[*k]))
        && image(&v["before"], &c["owner"]["source"], false) && image(&v["after"], &c["owner"]["source"], false)
        && image(&v["coverage"], &c["owner"]["source"], true)
        && ["after","coverage"].iter().all(|k| v[*k]["width"] == v["before"]["width"] && v[*k]["height"] == v["before"]["height"])
        && v["no_change"].as_bool() == Some(v["result_source_sha256"] == c["owner"]["source"]["sha256"])
        && v["notes"].as_array().is_some_and(|a| a.len() <= 32 && a.iter().all(message))
}
pub(super) fn valid_result(v: &Value, req: &Request) -> bool {
    if v["event"] != EVENT || v["request_id"] != req.id || size(v, RESULT_BYTES).is_err() { return false; }
    if req.write() || req.action == "receipt" {
        return fields(v, &["event","request_id","status","receipt"]) && v["status"] == "ready" && receipt(&v["receipt"], req.inner());
    }
    match v["status"].as_str() {
        Some("rejected"|"cancelled") => fields(v, &["event","request_id","status","message"]) && message(&v["message"]),
        Some("ready") => match req.action.as_str() {
            "current" => fields(v, &["event","request_id","status","context"]) && context(&v["context"]),
            "preview" => fields(v, &["event","request_id","status","review"]) && review(&v["review"], req.inner()),
            _ => false,
        },
        _ => false,
    }
}
pub(super) fn terminal(v: &Value) -> bool {
    if v.get("receipt").is_some() { v["receipt"]["phase"] == "done" }
    else { matches!(v["status"].as_str(), Some("ready"|"rejected"|"cancelled")) }
}
pub(super) fn pending(req: &Request, status: &str, why: &str) -> Value {
    if req.write() || req.action == "receipt" {
        let c = req.inner();
        json!({"event":EVENT,"request_id":req.id,"status":"ready","receipt":{"version":PROTOCOL,"operation_id":OPERATION,
            "request_id":c["request_id"],"session_id":c["session_id"],"action":c["action"],"owner":c["owner"],"token":c["token"],
            "phase":status,"outcome_unknown":true,"message":why}})
    } else { json!({"event":EVENT,"request_id":req.id,"status":status,"message":why}) }
}
pub(super) fn rejected(req: &Request, why: &str) -> Value {
    let mut v = pending(req, "unknown", why);
    if req.write() { v["receipt"]["phase"] = json!("done"); v["receipt"]["outcome_unknown"] = json!(false); v["receipt"]["outcome"] = json!("rejected"); }
    else if req.action != "receipt" { v["status"] = json!("rejected"); }
    v
}
pub(super) fn apply_matches(req: &Request, review: &Value) -> bool {
    let c = req.inner();
    req.apply() && review["version"] == PROTOCOL && review["operation_id"] == OPERATION
        && ["session_id","owner","token","recipe_sha256","result_source_sha256","coverage_sha256"].iter().all(|k| same(&c[*k], &review[*k]))
        && c["before_sha256"] == review["before"]["sha256"] && c["after_sha256"] == review["after"]["sha256"]
        && c["coverage_image_sha256"] == review["coverage"]["sha256"]
}
