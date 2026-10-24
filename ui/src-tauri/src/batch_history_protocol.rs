// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact identity for existing correlated batch undo/redo. AUTHORED / UNRUN.
//! Status summaries describe protected history; they never grant replay authority.
use serde_json::{json, Value};
use crate::preset_api::visual::{fields, text};
use crate::original_shadow_transfer_protocol::hex;
const MAX_ROWS: usize = 10_000;
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
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    if !text(&v["batch_id"]) || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean() { return false; }
    for key in ["eye_bag_batch_review", "eye_bag_cohort_review"] {
        if let Some(marker) = v.get(key) {
            if !summary(marker) || (key == "eye_bag_cohort_review" && marker["member_count"].as_u64().unwrap() < 2) { return false; }
        }
    }
    if v.get("eye_bag_batch_review").is_some() && v.get("eye_bag_cohort_review").is_some() { return false; }
    if v["success"] != true {
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
    ["eye_bag_batch_review", "eye_bag_cohort_review"].iter().all(|key| v.get(*key).map_or(true, |marker|
        marker["member_count"].as_u64() == Some(restored.len() as u64) && conflicts.is_empty()
            && v["module_scope"] == json!(["lnx.people_graph.v1"])))
}

#[cfg(test)]
#[path = "batch_history_protocol_tests.rs"]
mod tests;
