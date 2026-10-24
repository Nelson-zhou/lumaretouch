// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact shared-graph effect-recovery evidence. AUTHORED / UNRUN.
//! Review metadata cannot authorize a write without every immutable image pair.
use serde_json::{json, Value};
use crate::preset_api::visual::{fields, text, face};
use crate::original_shadow_transfer_protocol::hex;
use crate::source_patch_capture_host::Proof;
pub(crate) const MARKER: &str = "eye_bag_recovery_alias_review";
fn document(value: &Value) -> bool { value.as_str().is_some_and(|s| crate::color_capture_host::id16(s).is_ok()) }
pub(crate) const PROOF: &[&str] = &["document_id", "capture_id", "ticket", "generation", "recipe_document_id", "recipe_revision"];
const MAX_REVISION: u64 = 9_007_199_254_740_991;
pub(crate) fn revision(value: &Value) -> Option<u64> {
    let raw = value.as_str()?;
    if raw.is_empty() || raw.len() > 16 || !raw.bytes().all(|b| b.is_ascii_digit()) { return None; }
    let n = raw.parse::<u64>().ok()?;
    (n <= MAX_REVISION && raw == n.to_string()).then_some(n)
}
pub(crate) fn acknowledgment(value: &Value) -> bool {
    let Some(rows) = value["members"].as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    fields(value, &["review_sha256", "members"]) && hex(&value["review_sha256"], 64)
        && (2..=16).contains(&rows.len()) && rows.iter().all(|row|
            fields(row, &["document_id", "revision", "before_sha256", "after_sha256"])
                && document(&row["document_id"]) && revision(&row["revision"]).is_some_and(|n| n < MAX_REVISION)
                && hex(&row["before_sha256"], 64) && hex(&row["after_sha256"], 64)
                && seen.insert(row["document_id"].as_str().unwrap()))
}
pub(crate) fn expected_ack(review: &Value) -> Value {
    json!({"review_sha256":review["review_sha256"], "members":review["members"].as_array().unwrap().iter().map(|row| {
        let own = &row["visual"];
        json!({"document_id":own["document_id"], "revision":own["revision"],
            "before_sha256":own["before"]["sha256"], "after_sha256":own["after"]["sha256"]})
    }).collect::<Vec<_>>()})
}
pub(crate) fn review(value: &Value, proof: &Proof) -> bool {
    let Some(rows) = value["members"].as_array() else { return false; };
    let active = &value["visual"];
    let mut seen = std::collections::BTreeSet::new();
    if !fields(value, &["version", "token", "target", "face_ref", "before_recovery_sha256", "recovery_sha256", "visual", "members", "review_sha256"])
        || value["version"] != 2 || value["target"] != "eye_bag_preserve" || !document(&value["token"])
        || !face(&value["face_ref"]) || !hex(&value["review_sha256"], 64)
        || !["before_recovery_sha256", "recovery_sha256"].iter().all(|key| value[*key].is_null() || hex(&value[*key], 64))
        || active["document_id"] != proof.recipe_document_id || active["revision"] != proof.recipe_revision
        || active["source_size"] != proof.descriptor["full_source"]
        || !(2..=16).contains(&rows.len()) || rows[0]["visual"] != *active
        || !rows.iter().all(|row| {
            let own = &row["visual"];
            fields(row, &["path", "visual"])
                && row["path"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.chars().any(char::is_control))
                && document(&own["document_id"]) && revision(&own["revision"]).is_some_and(|n| n < MAX_REVISION)
                && crate::people_api::face_style::visual_shape(own)
                && own["source_proof"]["asset_sha256"] == value["face_ref"]["asset_sha256"]
                // Only one recovery asset changes. Each member retains its own
                // complete recipe/repair identity and original/creative source.
                && own["before_state_sha256"] == own["candidate_state_sha256"]
                && own["before_output_size"] == own["after_output_size"]
                && ["source_size", "before_people_sha256", "candidate_people_sha256"].iter().all(|key| own[*key] == active[*key])
                && seen.insert(own["document_id"].as_str().unwrap())
        }) { return false; }
    let mut identity = value.clone(); identity.as_object_mut().unwrap().remove("review_sha256");
    value["review_sha256"].as_str() == Some(crate::batch_api::collarbone::request_digest(&identity).as_str())
}
pub(crate) fn command(value: &Value) -> Result<(), String> {
    let required = ["cmd", "action", "request_id", "protocol", "preview_id", "document_id", "capture_id", "ticket",
        "generation", "recipe_document_id", "recipe_revision", "ack"];
    let exact = value.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || key == "host_epoch"));
    if !exact || value["cmd"] != "effect_recovery" || value["action"] != "apply" || value["protocol"] != 2
        || !text(&value["request_id"]) || !acknowledgment(&value["ack"])
        || !["capture_id", "preview_id", "recipe_document_id"].iter().all(|key| value[*key].as_str().is_some_and(|s| crate::color_capture_host::id16(s).is_ok()))
        || !["document_id", "ticket", "generation"].iter().all(|key| value[*key].as_str().is_some_and(|s| crate::color_capture_host::token(s).is_ok()))
        || revision(&value["recipe_revision"]).is_none()
        || value["ack"]["members"][0]["document_id"] != value["recipe_document_id"]
        || value["ack"]["members"][0]["revision"] != value["recipe_revision"]
        || !value.get("host_epoch").map_or(true, |epoch| hex(epoch, 32)) {
        return Err("Shared effect recovery requires the exact source proof and every reviewed alias image pair".into());
    }
    Ok(())
}
pub(crate) fn binding(value: &Value) -> Result<Option<Value>, String> {
    if value["cmd"] != "effect_recovery" || (value.get("ack").is_none() && value["protocol"] != 2) { return Ok(None); }
    command(value)?;
    let mut bound = json!({"protocol":2, "preview_id":value["preview_id"], "ack":value["ack"]});
    for key in PROOF { bound[*key] = value[*key].clone(); }
    Ok(Some(bound))
}
pub(crate) fn applies(value: &Value) -> bool { value["cmd"] == "effect_recovery" && value["protocol"] == 2 && command(value).is_ok() }
pub(crate) fn summary(value: &Value) -> bool {
    fields(value, &["version", "review_sha256", "member_count"]) && value["version"] == 1
        && hex(&value["review_sha256"], 64) && value["member_count"].as_u64().is_some_and(|n| (2..=16).contains(&n))
}
fn publication(value: &Value) -> bool {
    let ack = &value["ack"];
    let (Some(actual), Some(expected)) = (value["alias_members"].as_array(), ack["members"].as_array()) else { return false; };
    text(&value["batch_id"]) && summary(&value[MARKER]) && value[MARKER]["review_sha256"] == ack["review_sha256"]
        && value[MARKER]["member_count"].as_u64() == Some(expected.len() as u64)
        && value["module_scope"] == json!(["lnx.people_graph.v1"])
        && actual.len() == expected.len() && actual.iter().zip(expected).all(|(after, before)|
            fields(after, &["document_id", "expected_revision", "result_revision"])
                && after["document_id"] == before["document_id"] && after["expected_revision"] == before["revision"]
                && revision(&before["revision"]).and_then(|n| n.checked_add(1)) == revision(&after["result_revision"]))
}
pub(crate) fn receipt(value: &Value) -> bool {
    if ["face_decoration_preset_alias_review", "face_decoration_preset_ack", "eye_bag_preset_alias_review", "eye_bag_alias_review", "eye_bag_batch_review", "eye_bag_cohort_review",
        "eye_bag_preset_ack", "eye_bag_request", "people_transfer"].iter().any(|key| value.get(*key).is_some()) { return false; }
    if value["protocol"] != 2 || value["action"] != "apply" || !acknowledgment(&value["ack"])
        || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean() || !value["requires_reload"].is_boolean() || !value["no_write"].is_boolean()
        || value["recipe_document_id"] != value["ack"]["members"][0]["document_id"]
        || value["recipe_revision"] != value["ack"]["members"][0]["revision"] { return false; }
    if value["success"] != true {
        if !value["error"].as_str().is_some_and(|s| !s.trim().is_empty()) { return false; }
        if value["outcome_unknown"] == true {
            if value["no_write"] == true { return false; }
            return if value.get("alias_members").is_some() || value.get(MARKER).is_some() { publication(value) }
                else { value.get("batch_id").map_or(true, text) };
        }
        return value["requires_reload"] == false
            && ((value["no_write"] == true && value["rolled_back"] != true) || (value["no_write"] == false && value["rolled_back"] == true))
            && ["batch_id", "alias_members", MARKER, "doc_state", "module_scope", "before", "after"]
            .iter().all(|key| value.get(*key).is_none()) && value["operation_committed"] != true && value["committed"] != true
            && ["applied", "restored"].iter().all(|key| value.get(*key).map_or(true, |rows| rows.as_array().is_some_and(|rows| rows.is_empty())));
    }
    let current = &value["doc_state"]["people"]["binding"];
    publication(value) && value["outcome_unknown"] == false && value["requires_reload"] == false && value["no_change"] == false && value["no_write"] == false && value["rolled_back"] != true
        && value["doc_state"]["document_id"] == value["document_id"]
        && current["document_id"] == value["recipe_document_id"]
        && current["document_revision"].as_u64() == revision(&value["alias_members"][0]["result_revision"])
        && ["undo_steps", "redo_steps"].iter().all(|key| value["history"][*key].as_u64().is_some())
}
pub(crate) fn matches_request(command: &Value, value: &Value) -> bool {
    receipt(value) && binding(command).ok().flatten().is_some_and(|bound|
        bound.as_object().unwrap().iter().all(|(key, expected)| value.get(key) == Some(expected)))
}
pub(crate) fn retained_publication(value: &Value) -> Option<Value> {
    if value["success"] != false || value["outcome_unknown"] != true || !receipt(value) { return None; }
    let mut out = serde_json::Map::new();
    for key in ["batch_id", "alias_members", MARKER, "module_scope"] {
        if let Some(field) = value.get(key) { out.insert(key.to_owned(), field.clone()); }
    }
    (!out.is_empty()).then_some(Value::Object(out))
}
