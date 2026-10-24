// SPDX-License-Identifier: GPL-3.0-or-later
//! Persistent eye-bag cohort transport. AUTHORED / UNRUN.
//! Distinct from ordinary target-only transfers; the existing owner publishes
//! source plus every member atomically and owns all history/replay decisions.
use serde_json::{json, Value};
use crate::batch_api::{collarbone, eye_bag, portrait_cohort as portrait};
use crate::original_shadow_transfer_protocol::{hex, revision};
use crate::preset_api::visual::{fields, text, visual};
#[path = "eye_bag_cohort_review.rs"]
mod review;
pub(crate) const ACK: &str = "eye_bag_cohort_ack";
pub(crate) const KEY: &str = "eye_bag_cohort";
pub(crate) const VISUAL: &str = "eye_bag_cohort_visual";
const FOREIGN: &[&str] = &["eye_bag_review_ack", "eye_bag_preset_ack", "eye_bag_replace_legacy",
    "eye_bag", "eye_bag_coverage", "eye_bag_visual", "eye_bag_preset", "eye_bag_cohort_snapshots",
    "face_style_review_ack", "torso_review_ack", "waist_review_ack", "head_review_ack",
    "spill_review_ack", "shadow_review_ack", "local_mask_transfer", "reference_color"];
// No implicit weakening of another image-review family inside an aggregate.
const UNSUPPORTED: &[&str] = &["lnx.torso_length.v1", "lnx.waist_length.v1", "lnx.head_size.v1",
    "lnx.spill_removal.v1", "lnx.original_shadow.v1", "lnx.id_background.v1"];
fn supported(v: &Value) -> bool {
    v.as_array().is_some_and(|ops| ops.iter().all(|op| !UNSUPPORTED.iter().any(|name| op == *name)))
}
pub(crate) fn routed(v: &Value) -> bool {
    v["action"] == VISUAL || v["people_transfer"].get(KEY).is_some() || v.get(ACK).is_some()
        || (v["people_transfer"]["target_policy"] == "persistent_association"
            && v["people_transfer"]["selection"].get(eye_bag::OP).is_some())
}
/// Called only after the base association owner/reference shape is checked.
/// The source's explicit legacy decision is not inferred from any target.
pub(crate) fn policy(v: &Value) -> bool {
    let policy = &v[KEY];
    if !fields(policy, &["version", "members"]) || policy["version"].as_u64() != Some(1) { return false; }
    let (Some(choices), Some(targets)) = (policy["members"].as_array(), v["targets"].as_array()) else { return false; };
    (2..=portrait::MAX_MEMBERS).contains(&choices.len()) && choices.len() == targets.len() + 1
        && std::iter::once(&v["source"]).chain(targets.iter().map(|r| &r["target"]))
            .zip(choices).all(|(owner, choice)| fields(choice, &["document_id", "replace_legacy"])
                && hex(&choice["document_id"], 32) && choice["document_id"] == owner["document"]["document_id"]
                && choice["replace_legacy"].is_boolean())
}
fn request(v: &Value) -> bool {
    portrait::request(v) && v.get(KEY).is_some() && policy(v)
        && v["selection"].as_object().is_some_and(|selected| selected.iter().all(|(op, paths)|
            !UNSUPPORTED.contains(&op.as_str()) && (op != eye_bag::OP || paths.as_array().is_some_and(|paths|
                paths.iter().all(|path| matches!(path.as_str(), Some("/amount" | "/preserve")))))))
}
fn preflight_request(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    let names = ["cmd", "action", "request_id", "docs", "module_scope", "people_transfer"];
    if !names.iter().all(|k| map.contains_key(*k))
        || !map.keys().all(|k| names.contains(&k.as_str()) || k == "conflict_policy")
        || v["cmd"] != "batch" || v["action"] != "preflight" || !text(&v["request_id"])
        || !v.get("conflict_policy").map_or(true, |p| p == "recheck")
        || !request(&v["people_transfer"]) || !portrait::request_scope(&v["module_scope"], &v["people_transfer"]) { return false; }
    let Some(docs) = v["docs"].as_array() else { return false; };
    let targets = v["people_transfer"]["targets"].as_array().unwrap();
    docs.len() == targets.len() && targets.iter().all(|row|
        docs.iter().filter(|id| *id == &row["target"]["document"]["document_id"]).count() == 1)
}
pub(crate) fn acknowledgments(v: &Value) -> bool {
    eye_bag::acknowledgments(v) && v.as_array().is_some_and(|rows| (2..=portrait::MAX_MEMBERS).contains(&rows.len()))
}
fn paired(v: &Value) -> bool {
    let Some(rows) = v[ACK].as_array() else { return false; };
    [(portrait::ACK, portrait::acknowledgments as fn(&Value) -> bool),
        (collarbone::ACK, collarbone::acknowledgments)].iter().all(|(key, validate)| {
        let Some(other) = v.get(*key) else { return true; };
        validate(other) && other.as_array().is_some_and(|other| other.len() == rows.len()
            && rows.iter().zip(other).all(|(a, b)| ["document_id", "revision", "before_sha256", "after_sha256"]
                .iter().all(|key| a[*key] == b[*key])))
    })
}
fn image_request(v: &Value) -> bool {
    fields(v, &["cmd", "action", "request_id", "preflight_token", "document_id", "revision", "side", "sha256"])
        && v["cmd"] == "batch" && v["action"] == VISUAL && text(&v["request_id"])
        && hex(&v["preflight_token"], 32) && hex(&v["document_id"], 32) && revision(&v["revision"])
        && matches!(v["side"].as_str(), Some("before" | "after")) && hex(&v["sha256"], 64)
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if v["cmd"] != "batch" { return Ok(()); }
    if v["action"] == VISUAL {
        return if image_request(v) { Ok(()) } else { Err("Eye-bag cohort images require exact frozen member coordinates".into()) };
    }
    if v.get(KEY).is_some() { return Err("Eye-bag cohort classification comes only from the frozen engine plan".into()); }
    if v["people_transfer"].get(KEY).is_some() && !preflight_request(v) {
        return Err("Eye-bag cohort requires independent source and all members with ordered per-member legacy choices; unsupported mixed visual families are refused".into());
    }
    if v["people_transfer"]["target_policy"] == "persistent_association"
        && v["people_transfer"]["selection"].get(eye_bag::OP).is_some() && v["people_transfer"].get(KEY).is_none() {
        return Err("Persistent eye-bag intent requires dedicated source-and-member cohort review".into());
    }
    if let Some(ack) = v.get(ACK) {
        let mut names = vec!["cmd", "action", "request_id", "preflight_token", "module_scope", ACK];
        for key in [portrait::ACK, collarbone::ACK] { if v.get(key).is_some() { names.push(key); } }
        if !fields(v, &names) || v["action"] != "commit" || !text(&v["request_id"])
            || !hex(&v["preflight_token"], 32) || !portrait::scope(&v["module_scope"]) || !supported(&v["module_scope"])
            || !acknowledgments(ack) || !paired(v) || (collarbone::selected(v) && v.get(collarbone::ACK).is_none()) {
            return Err("Eye-bag cohort commit requires exact scope and all ordered independent full-image acknowledgments".into());
        }
    }
    Ok(())
}
pub(crate) fn read_only(v: &Value) -> bool { image_request(v) || preflight_request(v) }
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    command(v)?;
    if v["cmd"] != "batch" { return Ok(None); }
    if image_request(v) {
        return Ok(Some(json!({"preflight_token":v["preflight_token"], "document_id":v["document_id"],
            "revision":v["revision"], "side":v["side"], "sha256":v["sha256"]})));
    }
    if let Some(ack) = v.get(ACK) {
        let mut result = json!({"preflight_token":v["preflight_token"], "module_scope":v["module_scope"], (KEY):true, (ACK):ack});
        for (key, marker) in [(portrait::ACK, "portrait_cohort"), (collarbone::ACK, "collarbone_cohort")] {
            if let Some(other) = v.get(key) { result[key] = other.clone(); result[marker] = json!(true); }
        }
        return Ok(Some(result));
    }
    if preflight_request(v) {
        return Ok(Some(json!({"module_scope":v["module_scope"], "policy":"recheck",
            "eye_bag_cohort_applies_sha256":collarbone::request_digest(&v["people_transfer"])})));
    }
    Ok(None)
}
fn failed(v: &Value) -> bool {
    v["success"] == false && v["outcome_unknown"].is_boolean()
        && v["error"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 8000)
        && (v["outcome_unknown"] == true || (v["batch_id"].is_null() && v.get("doc_state").is_none()
            && v["committed"] != true && v["operation_committed"] != true
            && v.get("applied").map_or(true, |rows| rows.as_array().is_some_and(Vec::is_empty))
            && v.get("source_outcome").map_or(true, |row| row.is_object() && row["result_revision"].is_null()
                && matches!(row["outcome"].as_str(), Some("conflict" | "not_applied")))
            && v.get("target_outcomes").map_or(true, |rows| rows.as_array().is_some_and(|rows|
                rows.iter().all(|row| row.is_object() && row["result_revision"].is_null()
                    && matches!(row["outcome"].as_str(), Some("conflict" | "not_applied")))))))
}
fn image_receipt(v: &Value) -> bool {
    // Shared ordinary image receipt checks retain the same byte/hash/framing
    // proof; changing this local copy never upgrades ordinary ACK authority.
    let mut image = v.clone(); image["action"] = json!("eye_bag_visual");
    ![KEY, ACK, "portrait_cohort", "portrait_cohort_ack", "collarbone_cohort"].iter().any(|k| v.get(*k).is_some())
        && eye_bag::receipt(&image)
}
pub(crate) fn evidence(v: &Value) -> bool {
    v.get(KEY).is_some() || v.get(ACK).is_some() || v["applies"].get(KEY).is_some()
        || std::iter::once(&v["association_source"]).chain(v["targets"].as_array().into_iter().flatten())
            .any(|row| row["association"].get(KEY).is_some() || row["association"].get(VISUAL).is_some())
}
pub(crate) fn receipt(v: &Value) -> bool {
    if v["action"] == VISUAL { return image_receipt(v); }
    let inherited = v["applies"]["target_policy"] == "persistent_association"
        && (v["applies"]["selection"].get(eye_bag::OP).is_some()
            || v["persistent_association"]["intent"].as_array().is_some_and(|rows| rows.iter().any(|r| r["op"] == eye_bag::OP)));
    if !evidence(v) {
        return !((inherited || (v["persistent_association"].is_object()
            && v["persistent_association"]["intent"].as_array().is_some_and(|rows| rows.iter().any(|r| r["op"] == eye_bag::OP))))
            && (v["success"] == true || v["outcome_unknown"] == true));
    }
    if FOREIGN.iter().any(|k| v.get(*k).is_some()) || v.get(KEY).is_some_and(|marker| marker != true) { return false; }
    if v["action"] == "preflight" {
        if v.get(ACK).is_some() || v.get(portrait::ACK).is_some() || v.get(collarbone::ACK).is_some()
            || !request(&v["applies"]) || !portrait::request_scope(&v["module_scope"], &v["applies"])
            || v["policy"] != "recheck" { return false; }
        return if v["success"] == true { v[KEY] == true && review::preflight(v) } else { failed(v) };
    }
    v["action"] == "commit" && v[KEY] == true && hex(&v["preflight_token"], 32)
        && portrait::scope(&v["module_scope"]) && supported(&v["module_scope"]) && acknowledgments(&v[ACK]) && paired(v)
        && [ (portrait::ACK, "portrait_cohort"), (collarbone::ACK, "collarbone_cohort") ].iter()
            .all(|(key, marker)| v.get(*key).is_some() == (v[*marker] == true))
        && if v["success"] == true { v["outcome_unknown"] == false && review::commit(v) } else { failed(v) }
}

#[cfg(test)]
#[path = "eye_bag_cohort_protocol_tests.rs"]
mod tests;
