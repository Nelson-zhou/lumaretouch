// SPDX-License-Identifier: GPL-3.0-or-later
//! Complete decoration mixed-preset alias boundary. AUTHORED / UNRUN.
//! All member images retain their own source provenance and nonportrait recipe.
use serde_json::{Map, Value};
use super::{fields, text, visual, hex, ACK, ALIAS_MARKER};

const MAX_MEMBERS: usize = 16;
const MAX_REVISION: u64 = 9_007_199_254_740_991;
fn revision(value: &Value) -> Option<u64> {
    let raw = value.as_str()?;
    if raw.is_empty() || raw.len() > 16 || !raw.bytes().all(|b| b.is_ascii_digit()) { return None; }
    let number = raw.parse::<u64>().ok()?;
    (number <= MAX_REVISION && number.to_string() == raw).then_some(number)
}
fn review_revision(value: &Value) -> bool { revision(value).is_some_and(|n| n < MAX_REVISION) }
fn foreign_evidence(value: &Value) -> bool {
    ["face_style_alias_review", "eye_bag_preset_ack", "eye_bag_preset_alias_review", "eye_bag_recovery_alias_review", "eye_bag_alias_review",
        "eye_bag_batch_review", "eye_bag_cohort_review", "face_decoration_alias_review", "face_decoration_support_alias_review",
        "face_decoration_batch_review", "face_decoration_cohort_review"].iter().any(|key| value.get(*key).is_some())
}
pub(super) fn image_identity(value: &Value) -> bool {
    text(&value["member_document_id"]) && review_revision(&value["member_revision"]) && review_revision(&value["revision"])
}
pub(super) fn acknowledgment(value: &Value) -> bool {
    let Some(members) = value["members"].as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    fields(value, &["review_sha256", "preset_sha256", "applies_sha256", "members"])
        && ["review_sha256", "preset_sha256", "applies_sha256"].iter().all(|key| hex(&value[*key], 64))
        && (2..=MAX_MEMBERS).contains(&members.len())
        && members.iter().all(|member| fields(member, &["document_id", "revision", "before_sha256", "after_sha256", "coverage_sha256"])
            && text(&member["document_id"]) && review_revision(&member["revision"])
            && ["before_sha256", "after_sha256", "coverage_sha256"].iter().all(|key| hex(&member[*key], 64))
            && seen.insert(member["document_id"].as_str().unwrap()))
}
pub(super) fn review(value: &Value) -> bool {
    let wrapper = &value["face_decoration_preset"];
    if foreign_evidence(value) || !fields(wrapper, &["version", "preset_sha256", "applies_sha256", "load_id", "owner", "face_ref",
        "coverage", "visual", "before_bank_sha256", "members", "review_sha256"])
        || wrapper["version"].as_u64() != Some(2) || !super::review_base(value)
        || wrapper["owner"]["people_scope"] != "project"
        || !hex(&wrapper["before_bank_sha256"], 64) || !hex(&wrapper["review_sha256"], 64) { return false; }
    let Some(members) = wrapper["members"].as_array() else { return false; };
    let active = &wrapper["visual"];
    let mut seen = std::collections::BTreeSet::new();
    if !(2..=MAX_MEMBERS).contains(&members.len()) || members[0]["visual"] != *active
        || !members.iter().enumerate().all(|(index, member)| {
            let own = &member["visual"];
            fields(member, &["path", "role", "visual"])
                && member["path"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.contains('\0'))
                && member["role"] == (if index == 0 { "active" } else { "sibling" })
                && text(&own["document_id"]) && review_revision(&own["revision"])
                // Equal effective bytes do not make original provenance equal.
                && visual(own, &own["document_id"], &own["revision"], &own["source_proof"])
                && own["source_proof"]["asset_sha256"] == wrapper["face_ref"]["asset_sha256"]
                && ["source_size", "coverage_sha256", "before_people_sha256", "candidate_people_sha256"]
                    .iter().all(|key| own[*key] == active[*key])
                && (index == 0 || (own["before_state_sha256"] == own["candidate_state_sha256"]
                    && own["before_output_size"] == own["after_output_size"]))
                && seen.insert(own["document_id"].as_str().unwrap())
        }) { return false; }
    let mut identity = wrapper.clone();
    identity.as_object_mut().unwrap().remove("review_sha256");
    wrapper["review_sha256"].as_str() == Some(crate::batch_api::collarbone::request_digest(&identity).as_str())
}
/// Retained decoration can require review even when decoration is not selected.
/// This compact provenance never grants permission to replay a batch.
pub(super) fn summary(value: &Value) -> bool {
    let Some(modules) = value["selected_modules"].as_array() else { return false; };
    fields(value, &["version", "review_sha256", "preset_sha256", "applies_sha256", "current_document_id", "member_count", "selected_modules"])
        && value["version"].as_u64() == Some(1) && text(&value["current_document_id"])
        && ["review_sha256", "preset_sha256", "applies_sha256"].iter().all(|key| hex(&value[*key], 64))
        && value["member_count"].as_u64().is_some_and(|n| (2..=MAX_MEMBERS as u64).contains(&n))
        && !modules.is_empty() && modules.len() <= 32 && modules.iter().all(text)
        && modules.iter().all(|op| op != "lnx.people_graph.v1")
        && modules.iter().enumerate().all(|(index, op)| !modules[..index].contains(op))
}
fn marker_matches(value: &Value, acknowledgment: &Value) -> bool {
    let marker = &value[ALIAS_MARKER];
    summary(marker) && ["review_sha256", "preset_sha256", "applies_sha256"].iter().all(|key| marker[*key] == acknowledgment[*key])
        && marker["current_document_id"] == acknowledgment["members"][0]["document_id"]
        && marker["member_count"].as_u64() == acknowledgment["members"].as_array().map(|members| members.len() as u64)
        && marker["selected_modules"] == value["module_scope"]
}
fn publication(value: &Value) -> bool {
    let ack = &value[ACK];
    let (Some(actual), Some(expected)) = (value["alias_members"].as_array(), ack["members"].as_array()) else { return false; };
    text(&value["batch_id"]) && marker_matches(value, ack) && actual.len() == expected.len()
        && actual.iter().zip(expected).all(|(actual, expected)| fields(actual, &["document_id", "expected_revision", "result_revision"])
            && actual["document_id"] == expected["document_id"] && actual["expected_revision"] == expected["revision"]
            && revision(&expected["revision"]).and_then(|n| n.checked_add(1)) == revision(&actual["result_revision"]))
}
pub(super) fn receipt(value: &Value) -> bool {
    let ack = &value[ACK];
    // Never reinterpret a direct/support/cohort or eye-bag alias as this family.
    if foreign_evidence(value)
        || !acknowledgment(ack) || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean()
        || ["no_write", "rolled_back", "requires_reload", "requires_readback"].iter().any(|key| value.get(*key).is_some_and(|v| !v.is_boolean()))
        || (value["success"] == true && value["outcome_unknown"] != false)
        || (value["outcome_unknown"] == true && (value["no_write"] == true || value["rolled_back"] == true)) { return false; }
    if value["success"] != true {
        if !value["error"].as_str().is_some_and(|s| !s.trim().is_empty()) { return false; }
        if value["outcome_unknown"] == true {
            return if value.get("alias_members").is_some() || value.get(ALIAS_MARKER).is_some() { publication(value) }
                else { value.get("batch_id").map_or(true, text) };
        }
        return ["batch_id", "alias_members", ALIAS_MARKER, "doc_state", "before", "after"].iter().all(|key| value.get(*key).is_none())
            && value["operation_committed"] != true && value["committed"] != true
            && value["requires_reload"] != true && value["requires_readback"] != true
            && ["applied", "restored"].iter().all(|key| value.get(*key).map_or(true, |rows| rows.as_array().is_some_and(|rows| rows.is_empty())));
    }
    publication(value) && value["no_write"] != true && value["no_change"] != true && value["rolled_back"] != true
        && value["requires_reload"] != true && value["requires_readback"] != true
        && value["doc_state"]["document_id"] == value["document_id"]
        && value["doc_state"]["people"]["binding"]["document_id"] == ack["members"][0]["document_id"]
        && value["doc_state"]["people"]["binding"]["document_revision"].as_u64() == revision(&value["alias_members"][0]["result_revision"])
}
/// Only the request-bound receipt host may retain this diagnostic publication.
pub(super) fn retained_publication(value: &Value) -> Option<Value> {
    if value["action"] != "apply" || value["success"] != false || value["outcome_unknown"] != true || !receipt(value) { return None; }
    let mut retained = Map::new();
    for key in ["batch_id", "alias_members", ALIAS_MARKER] {
        if let Some(field) = value.get(key) { retained.insert(key.to_owned(), field.clone()); }
    }
    if value.get(ALIAS_MARKER).is_some() { retained.insert("module_scope".to_owned(), value["module_scope"].clone()); }
    // Required after compaction, including expired/unknown reads without scope.
    retained.insert("face_decoration_visual_required".to_owned(), Value::Bool(true));
    Some(Value::Object(retained))
}

#[cfg(test)]
#[path = "face_decoration_preset_alias_protocol_unrun.rs"]
mod tests;
