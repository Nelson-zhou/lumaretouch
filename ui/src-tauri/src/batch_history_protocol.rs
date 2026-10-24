// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact identity for existing correlated batch undo/redo. AUTHORED / UNRUN.
//! Status summaries describe protected history; they never grant replay authority.
use serde_json::{json, Value};
use crate::preset_api::visual::{fields, text};
use crate::original_shadow_transfer_protocol::hex;
const MAX_ROWS: usize = 10_000;
const PRESET_ALIAS_MARKER: &str = "eye_bag_preset_alias_review";
const EYE_MARKERS: &[&str] = &["eye_bag_batch_review", "eye_bag_cohort_review", "eye_bag_alias_review", "eye_bag_recovery_alias_review", PRESET_ALIAS_MARKER];
fn action(v: &Value) -> bool { matches!(v["action"].as_str(), Some("undo" | "redo")) }
fn index(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
pub(crate) fn command(v: &Value) -> Result<(), String> {
    // Leave historical uncorrelated callers on their unchanged route. A new
    // correlated request can carry only the existing selected batch identity.
    if v["cmd"] != "batch" || !action(v) || v.get("request_id").is_none() { return Ok(()); }
    if !fields(v, &["cmd", "action", "request_id", "batch_id"])
        || !text(&v["request_id"]) || !text(&v["batch_id"]) {
        return Err("Batch history requires its exact existing batch ID and request identity".into());
    }
    Ok(())
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    command(v)?;
    Ok((v["cmd"] == "batch" && action(v) && v.get("request_id").is_some())
        .then(|| json!({"batch_id":v["batch_id"]})))
}
fn summary(v: &Value) -> bool {
    fields(v, &["version", "review_sha256", "member_count"]) && v["version"].as_u64() == Some(1)
        && hex(&v["review_sha256"], 64) && v["member_count"].as_u64().is_some_and(|n| (1..=16).contains(&n))
}
/// A distinct composite marker describes the active recipe and shared graph.
/// It is read-only provenance, never an undo/redo request or replay authority.
pub(crate) fn preset_alias_summary(v: &Value) -> bool {
    let Some(modules) = v["selected_modules"].as_array() else { return false; };
    fields(v, &["version", "review_sha256", "preset_sha256", "applies_sha256", "current_document_id", "member_count", "selected_modules"])
        && v["version"].as_u64() == Some(1) && text(&v["current_document_id"])
        && ["review_sha256", "preset_sha256", "applies_sha256"].iter().all(|key| hex(&v[*key], 64))
        && v["member_count"].as_u64().is_some_and(|n| (2..=16).contains(&n))
        && !modules.is_empty() && modules.len() <= 256 && modules.iter().all(text)
        && modules.iter().any(|op| op == crate::preset_api::eye_bag::OP)
        && modules.iter().all(|op| op != "lnx.people_graph.v1")
        && modules.iter().enumerate().all(|(index, op)| !modules[..index].contains(op))
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    for key in ["face_decoration_batch_review","face_decoration_cohort_review","face_decoration_alias_review"] {
        if let Some(marker)=v.get(key) {
        if !summary(marker)||(key!="face_decoration_batch_review"&&marker["member_count"].as_u64().unwrap()<2) {return false;}
        if v["success"]==true && (v["module_scope"]!=json!(["lnx.people_graph.v1"])
            ||v["restored"].as_array().map(|rows|rows.len() as u64)!=marker["member_count"].as_u64()
            ||v["conflicts"].as_array().map_or(true,|rows|!rows.is_empty())){return false;}
    }
    }
    if ["face_decoration_batch_review","face_decoration_cohort_review","face_decoration_alias_review"].iter().filter(|k|v.get(**k).is_some()).count()>1{return false;}
    if !text(&v["batch_id"]) || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean() { return false; }
    for key in EYE_MARKERS {
        if let Some(marker) = v.get(*key) {
            if *key == PRESET_ALIAS_MARKER {
                if !preset_alias_summary(marker) { return false; }
            } else if !summary(marker) || (*key != "eye_bag_batch_review" && marker["member_count"].as_u64().unwrap() < 2) { return false; }
        }
    }
    if EYE_MARKERS.iter().filter(|key| v.get(**key).is_some()).count() > 1 { return false; }
    if v["success"] != true {
        if v.get("eye_bag_recovery_alias_review").is_some()
            && (v["module_scope"] != json!(["lnx.people_graph.v1"]) || !v["no_write"].is_boolean()
                || (v["outcome_unknown"] == true && (v["no_write"] == true || v.get("restored").is_some()))
                || (v["outcome_unknown"] == false && (!v["restored"].as_array().is_some_and(|rows| rows.is_empty())
                    || !((v["no_write"] == true && v["rolled_back"] != true) || (v["no_write"] == false && v["rolled_back"] == true))))) {
            return false;
        }
        return v["error"].as_str().is_some_and(|s| !s.trim().is_empty())
            && (v["outcome_unknown"] == true || (v.get("doc_state").is_none()
                && v["operation_committed"] != true && v["committed"] != true
                && v.get("applied").map_or(true, |rows| rows.as_array().is_some_and(|rows| rows.is_empty()))
                && v.get("restored").map_or(true, |rows| rows.as_array().is_some_and(|rows| rows.is_empty()))));
    }
    let (Some(restored), Some(conflicts)) = (v["restored"].as_array(), v["conflicts"].as_array()) else { return false; };
    if v["outcome_unknown"] != false || restored.len() > MAX_ROWS || conflicts.len() > MAX_ROWS
        || !restored.iter().all(index) || restored.iter().enumerate().any(|(i, n)| restored[..i].contains(n))
        || !conflicts.iter().all(|row| row.is_object()
            && row["path"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096)
            && row["reason"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000)
            && row.get("index").map_or(true, |n| n.is_null() || index(n))) { return false; }
    // Old success envelopes remain valid. If the optional compact eye marker
    // is echoed, it cannot describe a partial or differently scoped restore.
    EYE_MARKERS.iter().all(|key| v.get(*key).map_or(true, |marker|
        marker["member_count"].as_u64() == Some(restored.len() as u64) && conflicts.is_empty()
            && v["module_scope"] == json!(["lnx.people_graph.v1"])))
}

#[cfg(test)]
#[path = "batch_history_protocol_tests.rs"]
mod tests;
