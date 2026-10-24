// SPDX-License-Identifier: GPL-3.0-or-later
//! Separate source-owned visibility transaction. Scalar alias receipts keep their meaning.
//! These checks bind evidence and complete renders; they do not establish image acceptance.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, revision};
use crate::preset_api::visual::{fields, text, visual};
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST: &str = "face_decoration_support_alias_request";
pub(crate) const MARKER: &str = "face_decoration_support_alias_review";
const MAX_MEMBERS: usize = 16;
const MAX_REVISION: u64 = 9_007_199_254_740_991;
fn optional_hash(v: &Value) -> bool { v.is_null() || hex(v, 64) }
fn next(actual: &Value, before: &Value) -> bool {
    actual.as_u64().zip(before.as_u64()).is_some_and(|(a, b)| a <= MAX_REVISION && b.checked_add(1) == Some(a))
}
fn exact_number_values(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(_), Value::Number(_)) => a.as_f64() == b.as_f64(),
        (Value::Array(a), Value::Array(b)) => a.len() == b.len() && a.iter().zip(b).all(|(a, b)| exact_number_values(a, b)),
        (Value::Object(a), Value::Object(b)) => a.len() == b.len() && a.iter().all(|(k, v)| b.get(k).is_some_and(|b| exact_number_values(v, b))),
        _ => a == b,
    }
}
pub(crate) fn action(v: &Value) -> bool {
    matches!(v["action"].as_str(), Some("face_decoration_support_alias_preview" | "face_decoration_support_alias_image" | "face_decoration_support_alias_confirm"))
}
fn ack(v: &Value) -> bool {
    let Some(rows) = v["members"].as_array() else { return false; };
    let mut ids = std::collections::BTreeSet::new();
    fields(v, &["review_sha256", "members"]) && hex(&v["review_sha256"], 64) && (2..=MAX_MEMBERS).contains(&rows.len())
        && rows.iter().all(|row| fields(row, &["document_id", "revision", "before_sha256", "after_sha256"])
            && text(&row["document_id"]) && revision(&row["revision"])
            && hex(&row["before_sha256"], 64) && hex(&row["after_sha256"], 64)
            && ids.insert(row["document_id"].as_str().unwrap()))
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let required = ["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
    let envelope = v.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || ["cmd", "request_id", "host_epoch"].contains(&key.as_str())))
        && v.get("request_id").map_or(true, text)
        && v.get("cmd").map_or(true, |name| name == "people" && text(&v["request_id"]))
        && v.get("host_epoch").map_or(true, |epoch| v["cmd"] == "people" && hex(epoch, 32));
    let mut context = json!({}); for key in CONTEXT { context[*key] = v[*key].clone(); }
    let p = &v["payload"];
    let valid = envelope && super::valid_context(&context) && v["target"]["scope"] == "face" && match v["action"].as_str() {
        Some("face_decoration_support_alias_preview") => fields(p, &["reference_proof", "region"])
            && super::face_decoration::reference(&p["reference_proof"], &v["target"])
            && super::face_decoration::region(&p["region"]),
        Some("face_decoration_support_alias_image") => fields(p, &["token", "document_id", "side", "sha256", "review_sha256"])
            && hex(&p["token"], 32) && text(&p["document_id"])
            && matches!(p["side"].as_str(), Some("before" | "after")) && hex(&p["sha256"], 64) && hex(&p["review_sha256"], 64),
        Some("face_decoration_support_alias_confirm") => fields(p, &["token", "ack"]) && hex(&p["token"], 32) && ack(&p["ack"])
            && p["ack"]["members"][0]["document_id"] == v["document_id"]
            && p["ack"]["members"][0]["revision"].as_str() == v["document_revision"].as_u64().map(|n| n.to_string()).as_deref(),
        _ => false,
    };
    if valid { Ok(()) } else { Err("Shared decoration support requires exact original proof, visible source strokes and every affected image".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({"action":v["action"], "payload":v["payload"]});
    for key in CONTEXT { request[*key] = v[*key].clone(); }
    Ok(Some(json!({(REQUEST):request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && text(&v["request_id"]) && command(v).is_ok()
        && matches!(v["action"].as_str(), Some("face_decoration_support_alias_preview" | "face_decoration_support_alias_image"))
}
/// Reuse only the retained successful source read, never a scalar alias token.
pub(crate) fn reference_matches(v: &Value, status: &Value) -> bool {
    if v["action"] != "face_decoration_support_alias_preview" { return true; }
    let mut request = v.clone(); request["action"] = json!("face_decoration_review");
    super::face_decoration::reference_matches(&request, status)
}
fn coverage(v: &Value, source: &Value, review: &Value) -> bool {
    if !fields(v, &["version", "support_change", "targets"]) || v["version"] != 1 || v["support_change"] != "selected-face-only" { return false; }
    let Some(rows) = v["targets"].as_array() else { return false; };
    if rows.is_empty() || rows.len() > 64 { return false; }
    let mut prior: Option<&str> = None;
    let mut selected = false;
    rows.iter().all(|row| {
        if !fields(row, &["face_ref", "before_visibility_sha256", "visibility_sha256", "before_recipe_sha256", "recipe_sha256"])
            || !crate::batch_api::face_style::face(&row["face_ref"], &source["asset_sha256"])
            || !optional_hash(&row["before_visibility_sha256"]) || !optional_hash(&row["visibility_sha256"])
            || !hex(&row["before_recipe_sha256"], 64) || row["before_recipe_sha256"] != row["recipe_sha256"] { return false; }
        let id = row["face_ref"]["face_instance_id"].as_str().unwrap();
        if prior.is_some_and(|previous| previous >= id) { return false; } prior = Some(id);
        if row["face_ref"] == review["face_ref"] {
            selected = true;
            row["before_visibility_sha256"] == review["before_support_sha256"] && row["visibility_sha256"] == review["support_sha256"]
        } else { row["before_visibility_sha256"] == row["visibility_sha256"] }
    }) && selected
}
fn review(v: &Value, request: &Value) -> bool {
    if !fields(v, &["version", "token", "target", "owner", "face_ref", "before_support_sha256", "support_sha256", "reference_proof", "region",
        "before_bank_sha256", "candidate_bank_sha256", "candidate_state_revision", "members", "review_sha256"])
        || v["version"] != 1 || !hex(&v["token"], 32) || v["target"] != "face_decoration_visibility"
        || !crate::batch_api::face_style::endpoint(&v["owner"]) || v["face_ref"] != request["target"]["face_ref"]
        || !optional_hash(&v["before_support_sha256"]) || !hex(&v["support_sha256"], 64) || v["before_support_sha256"] == v["support_sha256"]
        || !["review_sha256", "before_bank_sha256", "candidate_bank_sha256"].iter().all(|key| hex(&v[*key], 64))
        || !super::face_decoration::reference(&v["reference_proof"], &request["target"])
        || v["reference_proof"] != request["payload"]["reference_proof"] || !super::face_decoration::region(&v["region"])
        || !exact_number_values(&v["region"], &request["payload"]["region"])
        || v["owner"]["document"]["document_id"] != request["document_id"] || v["owner"]["document"]["epoch"] != request["document_epoch"]
        || v["owner"]["document"]["revision"] != request["document_revision"] || v["owner"]["state_revision"] != request["state_revision"]
        || v["owner"]["association_revision"] != request["association_revision"]
        || v["face_ref"]["asset_sha256"] != v["owner"]["source_proof"]["asset_sha256"]
        || !next(&v["candidate_state_revision"], &request["state_revision"]) { return false; }
    let Some(rows) = v["members"].as_array() else { return false; };
    let mut ids = std::collections::BTreeSet::new();
    (2..=MAX_MEMBERS).contains(&rows.len()) && rows[0]["visual"]["document_id"] == request["document_id"]
        && rows[0]["visual"]["source_proof"] == v["owner"]["source_proof"]
        && rows[0]["visual"]["revision"].as_str() == request["document_revision"].as_u64().map(|n| n.to_string()).as_deref()
        && rows.iter().all(|row| {
            let image = &row["visual"];
            fields(row, &["path", "coverage", "visual"]) && row["path"].as_str().is_some_and(|p| !p.trim().is_empty() && p.len() <= 4096 && !p.contains('\0'))
                && text(&image["document_id"]) && revision(&image["revision"]) && ids.insert(image["document_id"].as_str().unwrap())
                && image["source_proof"]["asset_sha256"] == v["owner"]["source_proof"]["asset_sha256"]
                && image["before_state_sha256"] == image["candidate_state_sha256"] && image["before_output_size"] == image["after_output_size"]
                && image["source_size"] == json!([v["reference_proof"]["source"]["width"], v["reference_proof"]["source"]["height"]])
                && visual(image, &image["document_id"], &image["revision"], &image["source_proof"])
                && coverage(&row["coverage"], &image["source_proof"], v)
                && image["coverage_sha256"].as_str() == Some(crate::batch_api::collarbone::request_digest(&row["coverage"]).as_str())
        })
}
fn document(v: &Value, request: &Value, changed: bool) -> bool {
    let people = &v["doc_state"]["people"]; let b = &people["binding"]; let report = &people["face_decoration"];
    b["document_id"] == request["document_id"] && b["document_epoch"] == request["document_epoch"]
        && b["asset_sha256"] == request["target"]["face_ref"]["asset_sha256"]
        && (if changed { next(&b["document_revision"], &request["document_revision"]) && next(&people["revision"], &request["state_revision"]) }
            else { b["document_revision"] == request["document_revision"] && people["revision"] == request["state_revision"] })
        && people["association_revision"] == request["association_revision"]
        && people["selected_face_id"] == request["target"]["target_id"] && people["editing_target"] == request["target"]
        && people["resolved"]["face_ref"] == request["target"]["face_ref"] && people["resolved"]["state_revision"] == people["revision"]
        && people["resolved"]["association_revision"] == people["association_revision"]
        && report["face_ref"] == request["target"]["face_ref"] && report["source"]["sha256"] == b["asset_sha256"]
        && super::face_decoration::recipe(&report["recipe"])
        && people["resolved"]["operations"]["lnx.face_decoration.v1"]["/pattern"]["value"] == report["recipe"]["pattern"]
        && people["resolved"]["operations"]["lnx.face_decoration.v1"]["/strength"]["value"].as_f64() == report["recipe"]["strength"].as_f64()
}
fn confirmed(v: &Value, request: &Value) -> bool {
    let p = &v["payload"]; let a = &request["payload"]["ack"];
    if !fields(p, &["kind", "token", "review_sha256", "target", "face_ref", "before_support_sha256", "support_sha256", "before_bank_sha256",
        "candidate_bank_sha256", "candidate_state_revision", "ack", "history_review_sha256", "alias_members"])
        || p["kind"] != "face_decoration_support_alias_confirm" || p["token"] != request["payload"]["token"]
        || p["target"] != "face_decoration_visibility" || p["face_ref"] != request["target"]["face_ref"]
        || p["ack"] != *a || p["review_sha256"] != a["review_sha256"]
        || p["history_review_sha256"].as_str() != Some(crate::batch_api::collarbone::request_digest(a).as_str())
        || !optional_hash(&p["before_support_sha256"]) || p["before_support_sha256"] == p["support_sha256"] || !["support_sha256", "before_bank_sha256", "candidate_bank_sha256"].iter().all(|key| hex(&p[*key], 64))
        || !next(&p["candidate_state_revision"], &request["state_revision"]) || !text(&v["batch_id"]) || !document(v, request, true) { return false; }
    let (Some(rows), Some(acks)) = (p["alias_members"].as_array(), a["members"].as_array()) else { return false; };
    rows.len() == acks.len() && rows.iter().zip(acks).all(|(row, ack)| fields(row, &["document_id", "expected_revision", "result_revision"])
        && row["document_id"] == ack["document_id"] && row["expected_revision"] == ack["revision"] && revision(&row["result_revision"])
        && row["result_revision"].as_str().and_then(|s| s.parse::<u64>().ok()) == ack["revision"].as_str().and_then(|s| s.parse::<u64>().ok()).and_then(|n| n.checked_add(1)))
        && v["doc_state"]["people"]["revision"] == p["candidate_state_revision"]
        && v["doc_state"]["people"]["face_decoration"]["support_sha256"] == p["support_sha256"]
        && v["doc_state"]["people"]["face_decoration"]["reviewed"] == true
}
fn failed(v: &Value) -> bool {
    if v["success"] != false || !v["outcome_unknown"].is_boolean() || !v["error"].as_str().is_some_and(|s| !s.trim().is_empty())
        || v.get("doc_state").is_some_and(|s| !s.is_null()) || v.get("payload").is_some_and(|p| !p.is_null())
        || (v["frame_emitted"] == true && v["outcome_unknown"] != true) || v["operation_committed"] == true || v["committed"] == true { return false; }
    if v["outcome_unknown"] == true { return v["no_write"] != true && v["rolled_back"] != true; }
    v["requires_reload"] != true && v["requires_readback"] != true
        && ((v["no_write"] == true && v["rolled_back"] != true && v["batch_id"].is_null())
            || (v["no_write"] == false && v["rolled_back"] == true))
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return v.get(REQUEST).is_none(); }
    let required = ["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", REQUEST];
    let optional = ["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "doc_state", "payload_released",
        "no_write", "rolled_back", "requires_reload", "requires_readback", MARKER, "alias_members", "module_scope"];
    if !v.as_object().is_some_and(|m| required.iter().all(|k| m.contains_key(*k)) && m.keys().all(|k| required.contains(&k.as_str()) || optional.contains(&k.as_str())))
        || v["protocol"] != 1 || !text(&v["request_id"]) || v.get("event").is_some_and(|e| e != "people_result") || !v["created_id"].is_null()
        || ["frame_emitted", "no_write", "rolled_back", "requires_reload", "requires_readback"].iter().any(|k| v.get(*k).is_some_and(|b| !b.is_boolean())) { return false; }
    let request = &v[REQUEST];
    if !fields(request, &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"])
        || command(request).is_err() || request["action"] != v["action"] || request["document_id"] != v["document_id"] { return false; }
    if v.get(MARKER).is_some() || v.get("alias_members").is_some() || v.get("module_scope").is_some() {
        if request["action"] != "face_decoration_support_alias_confirm" || !publication(v, request) { return false; }
    }
    if v["success"] != true { return failed(v); }
    if v["outcome_unknown"] != false || !v["error"].is_null() || v["requires_reload"] == true || v["requires_readback"] == true
        || v["rolled_back"] == true { return false; }
    if v.get("payload_released").is_some() {
        return v["action"] == "face_decoration_support_alias_image" && v["payload_released"] == true
            && v.get("payload").map_or(true, Value::is_null) && v.get("doc_state").is_none() && v["batch_id"].is_null() && v["frame_emitted"] == false;
    }
    let p = &v["payload"];
    match v["action"].as_str() {
        Some("face_decoration_support_alias_preview") => fields(p, &["kind", "review"]) && p["kind"] == v["action"] && review(&p["review"], request)
            && v["batch_id"].is_null() && v["frame_emitted"] == false && document(v, request, false)
            && v["doc_state"]["people"]["face_decoration"]["support_alias_review"] == p["review"]
            && v["doc_state"]["people"]["face_decoration"]["support_sha256"] == p["review"]["before_support_sha256"],
        Some("face_decoration_support_alias_image") => fields(p, &["kind", "token", "document_id", "side", "sha256", "review_sha256", "image"])
            && p["kind"] == v["action"] && v.get("doc_state").is_none() && v["batch_id"].is_null() && v["frame_emitted"] == false
            && ["token", "document_id", "side", "sha256", "review_sha256"].iter().all(|k| p[*k] == request["payload"][*k])
            && p["image"]["sha256"] == p["sha256"] && crate::preset_api::visual::image(&p["image"]),
        Some("face_decoration_support_alias_confirm") => v["no_write"] == false && publication(v, request) && confirmed(v, request),
        _ => false,
    }
}
pub(crate) fn summary(v: &Value) -> bool {
    fields(v, &["version", "review_sha256", "member_count"]) && v["version"] == 1 && hex(&v["review_sha256"], 64)
        && v["member_count"].as_u64().is_some_and(|n| (2..=MAX_MEMBERS as u64).contains(&n))
}
fn publication(v: &Value, request: &Value) -> bool {
    let a = &request["payload"]["ack"];
    summary(&v[MARKER]) && v[MARKER]["review_sha256"].as_str() == Some(crate::batch_api::collarbone::request_digest(a).as_str())
        && v[MARKER]["member_count"].as_u64() == a["members"].as_array().map(|r| r.len() as u64) && text(&v["batch_id"])
        && v["module_scope"] == json!(["lnx.people_graph.v1"])
        && v["alias_members"].as_array().zip(a["members"].as_array()).is_some_and(|(rows, acks)| rows.len() == acks.len()
            && rows.iter().zip(acks).all(|(row, ack)| fields(row, &["document_id", "expected_revision", "result_revision"])
                && row["document_id"] == ack["document_id"] && row["expected_revision"] == ack["revision"] && revision(&row["result_revision"])
                && row["result_revision"].as_str().and_then(|s| s.parse::<u64>().ok()) == ack["revision"].as_str().and_then(|s| s.parse::<u64>().ok()).and_then(|n| n.checked_add(1))))
}
pub(crate) fn retained_publication(v: &Value) -> Option<Value> {
    if !receipt(v) || !publication(v, &v[REQUEST]) { return None; }
    Some(json!({"batch_id":v["batch_id"], (MARKER):v[MARKER], "alias_members":v["alias_members"], "module_scope":v["module_scope"]}))
}
pub(crate) fn report_metadata(v: &Value) -> bool {
    let keys = ["support_alias_review", "support_alias_reason"];
    if keys.iter().all(|key| v.get(*key).is_none()) { return true; }
    if keys.iter().any(|key| v.get(*key).is_none()) || !(v["support_alias_reason"].is_null()
        || v["support_alias_reason"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096 && !s.contains('\0'))) { return false; }
    if v["support_alias_review"].is_null() { return true; }
    let r = &v["support_alias_review"]; let owner = &r["owner"];
    let request = json!({"document_id":owner["document"]["document_id"], "document_epoch":owner["document"]["epoch"],
        "document_revision":owner["document"]["revision"], "state_revision":owner["state_revision"], "association_revision":owner["association_revision"],
        "target":{"scope":"face", "target_id":r["face_ref"]["face_instance_id"], "face_ref":r["face_ref"]},
        "payload":{"reference_proof":r["reference_proof"], "region":r["region"]}});
    r["face_ref"] == v["face_ref"] && r["owner"]["source_proof"]["asset_sha256"] == v["source"]["sha256"] && review(r, &request)
}
pub(crate) fn applies(v: &Value) -> bool { v["cmd"] == "people" && v["action"] == "face_decoration_support_alias_confirm" && command(v).is_ok() }
pub(crate) fn matches_request(command: &Value, value: &Value) -> bool {
    let Ok(Some(bound)) = binding(command) else { return false; };
    value["event"] == "people_result" && receipt(value) && bound.as_object().is_some_and(|m| m.iter().all(|(k, v)| value.get(k) == Some(v)))
}
#[cfg(test)]
#[path = "face_decoration_support_alias_protocol_unrun.rs"]
mod tests;
