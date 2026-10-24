// SPDX-License-Identifier: GPL-3.0-or-later
//! Ordinary explicit-face-map eye-bag review transport. AUTHORED / UNRUN.
//! The existing frozen batch owns plans, publication and history. This module
//! checks scalar intent, target-local evidence and receipts, not image quality.
use serde_json::{json, Value};
use crate::batch_api::{collarbone, face_style};
use crate::original_shadow_transfer_protocol::{hex, revision};
use crate::preset_api::visual::{fields, text, visual};

pub(crate) const OP: &str = "lnx.eye_bags.v2";
pub(crate) const ACK: &str = "eye_bag_review_ack";
pub(crate) const MAX_TARGETS: usize = 16;
const FOREIGN: &[&str] = &["eye_bag_preset_ack", "eye_bag_preset", "face_style_review_ack",
    "portrait_cohort_ack", "portrait_cohort", "collarbone_cohort", "persistent_association",
    "association_source", "eye_bag_cohort", "eye_bag_cohort_ack", "torso_review_ack", "waist_review_ack", "head_review_ack",
    "spill_review_ack", "shadow_review_ack"];
fn index(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
fn token(v: &Value) -> bool {
    text(v) && v.as_str().unwrap().bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b))
}
fn scope(v: &Value, selected: &Value) -> bool {
    let (Some(ops), Some(selection)) = (v.as_array(), selected.as_object()) else { return false; };
    !ops.is_empty() && ops.len() <= 256 && ops.len() == selection.len()
        && ops.iter().all(|op| token(op) && selection.contains_key(op.as_str().unwrap()))
        && ops.iter().enumerate().all(|(i, op)| !ops[..i].contains(op))
}
fn selection(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    if !map.contains_key(OP) || map.is_empty() || map.len() > 256 { return false; }
    let mut count = 0;
    map.iter().all(|(op, paths)| {
        let Some(paths) = paths.as_array() else { return false; };
        count += paths.len();
        token(&json!(op)) && !paths.is_empty() && count <= 256
            && paths.iter().all(|p| p.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 512
                && s.starts_with('/') && !s.chars().any(char::is_control)
                && (op != OP || matches!(s, "/amount" | "/preserve"))))
            && paths.iter().enumerate().all(|(i, p)| !paths[..i].contains(p))
    })
}
/// This envelope never accepts portable support, a named style or a cohort.
fn request(v: &Value) -> bool {
    if !fields(v, &["target_policy", "source_ref", "selection", "source", "targets", "eye_bag"])
        || v["target_policy"] != "explicit_face_map" || !selection(&v["selection"])
        || !face_style::endpoint(&v["source"])
        || !face_style::face(&v["source_ref"], &v["source"]["source_proof"]["asset_sha256"])
        || !fields(&v["eye_bag"], &["version", "targets"]) || v["eye_bag"]["version"].as_u64() != Some(1) { return false; }
    let (Some(targets), Some(choices)) = (v["targets"].as_array(), v["eye_bag"]["targets"].as_array()) else { return false; };
    if targets.is_empty() || targets.len() > MAX_TARGETS || choices.len() != targets.len() { return false; }
    let mut documents = std::collections::BTreeSet::new();
    let mut chosen = std::collections::BTreeSet::new();
    targets.iter().all(|row| {
        let owner = &row["target"];
        let Some(refs) = row["target_refs"].as_array() else { return false; };
        let mut faces = std::collections::BTreeSet::new();
        fields(row, &["target", "target_refs"]) && face_style::endpoint(owner)
            && owner["document"]["document_id"] != v["source"]["document"]["document_id"]
            && owner["document"]["epoch"] == v["source"]["document"]["epoch"]
            && documents.insert(owner["document"]["document_id"].as_str().unwrap())
            && !refs.is_empty() && refs.len() <= 128 && refs.iter().all(|r|
                face_style::face(r, &owner["source_proof"]["asset_sha256"])
                    && faces.insert(r["face_instance_id"].as_str().unwrap()))
    }) && choices.iter().all(|choice| fields(choice, &["document_id", "replace_legacy"])
        && hex(&choice["document_id"], 32) && choice["replace_legacy"].is_boolean()
        && documents.contains(choice["document_id"].as_str().unwrap())
        && chosen.insert(choice["document_id"].as_str().unwrap()))
        && targets.iter().enumerate().all(|(i, row)| {
            let owner = &row["target"];
            let choice = choices.iter().find(|c| c["document_id"] == owner["document"]["document_id"]).unwrap();
            targets[..i].iter().all(|other| {
                if other["target"]["people_scope"] != owner["people_scope"]
                    || other["target"]["source_proof"]["asset_sha256"] != owner["source_proof"]["asset_sha256"] { return true; }
                let prior = choices.iter().find(|c| c["document_id"] == other["target"]["document"]["document_id"]).unwrap();
                prior["replace_legacy"] == choice["replace_legacy"]
            })
        })
}
fn preflight_request(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    let names = ["cmd", "action", "request_id", "docs", "module_scope", "people_transfer"];
    if !names.iter().all(|k| map.contains_key(*k))
        || !map.keys().all(|k| names.contains(&k.as_str()) || k == "conflict_policy")
        || v["cmd"] != "batch" || v["action"] != "preflight" || !text(&v["request_id"])
        || !request(&v["people_transfer"]) || !scope(&v["module_scope"], &v["people_transfer"]["selection"])
        || !v.get("conflict_policy").map_or(true, |p| matches!(p.as_str(), Some("skip_and_report" | "recheck"))) { return false; }
    let Some(docs) = v["docs"].as_array() else { return false; };
    let targets = v["people_transfer"]["targets"].as_array().unwrap();
    docs.len() == targets.len() && targets.iter().all(|row|
        docs.iter().filter(|id| *id == &row["target"]["document"]["document_id"]).count() == 1)
}
pub(crate) fn acknowledgments(v: &Value) -> bool {
    let Some(rows) = v.as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    rows.len() <= MAX_TARGETS && rows.iter().all(|row|
        fields(row, &["document_id", "revision", "before_sha256", "after_sha256", "coverage_sha256", "replace_legacy"])
        && hex(&row["document_id"], 32) && revision(&row["revision"]) && row["replace_legacy"].is_boolean()
        && ["before_sha256", "after_sha256", "coverage_sha256"].iter().all(|k| hex(&row[*k], 64))
        && seen.insert(row["document_id"].as_str().unwrap()))
}
/// A mixed complete render has two independent coverage hashes but the same
/// ordered document/revision/image identities. Neither family replaces another.
fn paired_acknowledgments(v: &Value) -> bool {
    let Some(other) = v.get(collarbone::ACK) else { return true; };
    if !collarbone::acknowledgments(other) { return false; }
    let (Some(eye), Some(collarbone)) = (v[ACK].as_array(), other.as_array()) else { return false; };
    eye.len() == collarbone.len() && eye.iter().zip(collarbone).all(|(a, b)|
        ["document_id", "revision", "before_sha256", "after_sha256"].iter().all(|k| a[*k] == b[*k]))
}
fn image_request(v: &Value) -> bool {
    fields(v, &["cmd", "action", "request_id", "preflight_token", "document_id", "revision", "side", "sha256"])
        && v["cmd"] == "batch" && v["action"] == "eye_bag_visual" && text(&v["request_id"])
        && hex(&v["preflight_token"], 32) && hex(&v["document_id"], 32) && revision(&v["revision"])
        && matches!(v["side"].as_str(), Some("before" | "after")) && hex(&v["sha256"], 64)
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if v["cmd"] != "batch" { return Ok(()); }
    if v["action"] == "eye_bag_visual" {
        return if image_request(v) { Ok(()) } else { Err("Eye-bag batch image read requires exact frozen target coordinates".into()) };
    }
    if v["people_transfer"].get("eye_bag").is_some() && !preflight_request(v) {
        return Err("Eye-bag batch requires an exact explicit face map and each target's legacy choice".into());
    }
    if v.get("eye_bag_preset_ack").is_some() || v.get("eye_bag_replace_legacy").is_some() {
        return Err("Preset or document-wide eye-bag consent cannot authorize batch targets".into());
    }
    if let Some(ack) = v.get(ACK) {
        let mut names = vec!["cmd", "action", "request_id", "preflight_token", ACK];
        if v.get(collarbone::ACK).is_some() { names.push(collarbone::ACK); }
        if !fields(v, &names) || v["action"] != "commit" || !text(&v["request_id"])
            || !hex(&v["preflight_token"], 32) || !acknowledgments(ack) || !paired_acknowledgments(v) {
            return Err("Eye-bag batch commit needs exact ordered PNG/coverage acknowledgments and per-target legacy choices".into());
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
        let mut result = json!({"preflight_token":v["preflight_token"], (ACK):ack});
        if let Some(other) = v.get(collarbone::ACK) { result[collarbone::ACK] = other.clone(); }
        return Ok(Some(result));
    }
    if preflight_request(v) {
        return Ok(Some(json!({"module_scope":v["module_scope"],
            "policy":v.get("conflict_policy").cloned().unwrap_or(json!("skip_and_report")),
            "eye_bag_applies_sha256":collarbone::request_digest(&v["people_transfer"])})));
    }
    // Existing neutral/dormant generic transfers stay separate. The engine
    // still rejects any active generic candidate without dedicated review.
    Ok(None)
}
fn coverage(v: &Value, refs: &Value) -> bool {
    if !fields(v, &["version", "support_transfer", "targets"]) || v["version"].as_u64() != Some(1)
        || v["support_transfer"] != "none" { return false; }
    let (Some(rows), Some(refs)) = (v["targets"].as_array(), refs.as_array()) else { return false; };
    rows.len() == refs.len() && rows.iter().zip(refs).all(|(row, reference)| {
        if !fields(row, &["face_ref", "scope", "ridge_sha256", "sides"]) || &row["face_ref"] != reference { return false; }
        match row["scope"].as_str() {
            Some("neutral-no-effect") => row["ridge_sha256"].is_null() && row["sides"] == json!([]),
            Some("target-reviewed-ridge") => hex(&row["ridge_sha256"], 64)
                && [json!(["left"]), json!(["right"]), json!(["left", "right"])].contains(&row["sides"]),
            _ => false,
        }
    })
}
pub(crate) fn collarbone_coverage(v: &Value, refs: &Value) -> bool {
    if !fields(v, &["version", "support_transfer", "targets"]) || v["version"].as_u64() != Some(1)
        || v["support_transfer"] != "none" { return false; }
    let (Some(rows), Some(refs)) = (v["targets"].as_array(), refs.as_array()) else { return false; };
    rows.len() == refs.len() && rows.iter().zip(refs).all(|(row, reference)| {
        if !fields(row, &["face_ref", "scope", "body_review_sha256", "clavicle_category", "clavicle_sides"])
            || &row["face_ref"] != reference { return false; }
        let Some(sides) = row["clavicle_sides"].as_array() else { return false; };
        match row["scope"].as_str() {
            Some("neutral-no-effect") => row["body_review_sha256"].is_null() && row["clavicle_category"].is_null() && sides.is_empty(),
            Some("reviewed-clavicle-only") => hex(&row["body_review_sha256"], 64)
                && matches!(row["clavicle_category"].as_str(), Some("female" | "elder_female"))
                && (1..=2).contains(&sides.len()) && sides.iter().all(|s| matches!(s.as_str(), Some("left" | "right")))
                && (sides.len() == 1 || sides[0] != sides[1]),
            _ => false,
        }
    })
}
fn parameters(v: &Value, selected: &Value, coverage: &Value) -> bool {
    let Some(rows) = v.as_array() else { return false; };
    let mut wanted: std::collections::BTreeSet<(&str, &str)> = selected.as_object().unwrap().iter()
        .flat_map(|(op, paths)| paths.as_array().unwrap().iter().map(move |p| (op.as_str(), p.as_str().unwrap()))).collect();
    if rows.len() != wanted.len() { return false; }
    let records = coverage["targets"].as_array().unwrap();
    rows.iter().all(|row| {
        let (Some(op), Some(path)) = (row["operation_id"].as_str(), row["parameter_path"].as_str()) else { return false; };
        if !fields(row, &["operation_id", "parameter_path", "value"]) || !wanted.remove(&(op, path)) { return false; }
        let value = &row["value"];
        if op == OP {
            let Some(n) = value.as_f64().filter(|n| n.is_finite() && (0.0..=1.0).contains(n)) else { return false; };
            return path != "/amount" || records.iter().all(|r|
                r["scope"] == if n == 0.0 { "neutral-no-effect" } else { "target-reviewed-ridge" });
        }
        if op == "lnx.enhance.v1" && path == "/eye_bags" {
            let Some(n) = value.as_f64().filter(|n| n.is_finite() && (0.0..=1.0).contains(n)) else { return false; };
            // Replacement consent never silently discards a selected active
            // legacy effect. Neutral v2 transfers may still retain it.
            return n == 0.0 || records.iter().all(|r| r["scope"] == "neutral-no-effect");
        }
        value.is_boolean() || value.as_str().is_some_and(|s| s.len() <= 4096)
            || value.as_f64().is_some_and(f64::is_finite)
    }) && wanted.is_empty()
}
fn target_review(v: &Value, row: &Value, wanted: &Value, applies: &Value) -> bool {
    let names = ["version", "source_document", "target_document", "source_ref", "target_refs", "parameters",
        "source_state_revision", "target_state_revision", "source_association_revision", "target_association_revision",
        "transfer_policy", "excluded", "source_owner", "target_owner", "target_policy", "eye_bag", "eye_bag_coverage", "eye_bag_visual"];
    let optional = [("lnx.skin_colour.v1", "skin_colour_coverage"), ("lnx.skin_finish.v1", "skin_finish_coverage"),
        (collarbone::OP, "collarbone_coverage"), (collarbone::OP, "collarbone_visual"),
        ("lnx.body_skin_evenness.v1", "body_skin_evenness_coverage"), ("lnx.body_face_match.v1", "body_face_match_coverage")];
    let Some(map) = v.as_object() else { return false; };
    let owner = &wanted["target"];
    let choice = applies["eye_bag"]["targets"].as_array().unwrap().iter()
        .find(|choice| choice["document_id"] == row["document_id"]).unwrap();
    if !names.iter().all(|k| map.contains_key(*k)) || map.keys().any(|k|
        !names.contains(&k.as_str()) && !optional.iter().any(|(op, key)| k.as_str() == *key && applies["selection"].get(*op).is_some()))
        || v["version"].as_u64() != Some(1) || v["target_policy"] != "explicit_face_map"
        || v["transfer_policy"] != "selected_parameter_keys_replace"
        || v["excluded"] != json!(["local_assets", "landmarks", "masks", "identity_links"])
        || v["source_document"] != applies["source"]["document"] || v["target_document"] != owner["document"]
        || v["source_ref"] != applies["source_ref"] || v["target_refs"] != wanted["target_refs"]
        || v["source_owner"] != applies["source"] || v["target_owner"] != *owner
        || v["source_state_revision"] != applies["source"]["state_revision"] || v["target_state_revision"] != owner["state_revision"]
        || v["source_association_revision"] != applies["source"]["association_revision"]
        || v["target_association_revision"] != owner["association_revision"]
        || !fields(&v["eye_bag"], &["version", "replace_legacy"]) || v["eye_bag"]["version"].as_u64() != Some(1)
        || v["eye_bag"]["replace_legacy"] != choice["replace_legacy"]
        || !coverage(&v["eye_bag_coverage"], &v["target_refs"])
        || !parameters(&v["parameters"], &applies["selection"], &v["eye_bag_coverage"])
        || !visual(&v["eye_bag_visual"], &row["document_id"], &row["revision"], &owner["source_proof"])
        || v["eye_bag_visual"]["coverage_sha256"].as_str() != Some(collarbone::request_digest(&v["eye_bag_coverage"]).as_str()) { return false; }
    if applies["selection"].get(collarbone::OP).is_some() {
        if !collarbone_coverage(&v["collarbone_coverage"], &v["target_refs"])
            || !visual(&v["collarbone_visual"], &row["document_id"], &row["revision"], &owner["source_proof"])
            || v["collarbone_visual"]["coverage_sha256"].as_str() != Some(collarbone::request_digest(&v["collarbone_coverage"]).as_str()) { return false; }
        let mut eye = v["eye_bag_visual"].clone(); let mut other = v["collarbone_visual"].clone();
        eye.as_object_mut().unwrap().remove("coverage_sha256"); other.as_object_mut().unwrap().remove("coverage_sha256");
        if eye != other { return false; }
    }
    true
}
fn preflight(v: &Value) -> bool {
    let applies = &v["applies"];
    if !request(applies) || !scope(&v["module_scope"], &applies["selection"])
        || !matches!(v["policy"].as_str(), Some("skip_and_report" | "recheck")) { return false; }
    if v["success"] != true { return failed(v); }
    if v["people_transfer"] != true || !hex(&v["preflight_token"], 32) || v.to_string().len() > 7 * 1024 * 1024
        || v["source_snapshot"]["document_id"] != applies["source"]["document"]["document_id"]
        || v["source_snapshot"]["revision"].as_str() != applies["source"]["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref() { return false; }
    let (Some(targets), Some(rejected)) = (v["targets"].as_array(), v["rejected_docs"].as_array()) else { return false; };
    let requested = applies["targets"].as_array().unwrap();
    // This family reviews the complete requested set. Unavailable documents
    // cannot disappear into a generic rejected-docs list under either policy.
    if targets.len() > MAX_TARGETS || targets.len() != requested.len() || !rejected.is_empty() { return false; }
    let mut seen = std::collections::BTreeSet::new(); let mut blocked = 0_u64;
    let mut parameters_seen: Option<&Value> = None;
    for row in targets {
        if !hex(&row["document_id"], 32) || !revision(&row["revision"])
            || !seen.insert(row["document_id"].as_str().unwrap()) { return false; }
        let Some(wanted) = requested.iter().find(|r| r["target"]["document"]["document_id"] == row["document_id"]) else { return false; };
        if !row["blocked"].is_null() {
            if !row["blocked"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000)
                || !row["people_transfer"].is_null() { return false; }
            blocked += 1; continue;
        }
        if row["revision"].as_str() != wanted["target"]["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref()
            || !target_review(&row["people_transfer"], row, wanted, applies) { return false; }
        let params = &row["people_transfer"]["parameters"];
        if parameters_seen.is_some_and(|prior| prior != params) { return false; }
        parameters_seen = Some(params);
    }
    v["blocked"].as_u64() == Some(blocked) && v["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
fn failed(v: &Value) -> bool {
    v["success"] == false && v["outcome_unknown"].is_boolean()
        && v["error"].as_str().is_some_and(|s| !s.trim().is_empty())
        && (v["outcome_unknown"] == true || (v["batch_id"].is_null() && v.get("doc_state").is_none()
            && v["committed"] != true && v["operation_committed"] != true
            && v.get("applied").map_or(true, |rows| rows.as_array().is_some_and(|rows| rows.is_empty()))
            && v.get("target_outcomes").map_or(true, |rows| rows.as_array().is_some_and(|rows|
                rows.iter().all(|row| row.is_object() && row["result_revision"].is_null()
                    && matches!(row["outcome"].as_str(), Some("conflict" | "not_applied")))))))
}
fn image_receipt(v: &Value) -> bool {
    if !hex(&v["preflight_token"], 32) || !hex(&v["document_id"], 32) || !revision(&v["revision"])
        || !matches!(v["side"].as_str(), Some("before" | "after")) || !hex(&v["sha256"], 64)
        || FOREIGN.iter().any(|key| v.get(*key).is_some())
        || ["doc_state", "batch_id", "applied", "target_outcomes", ACK, collarbone::ACK].iter().any(|k| v.get(*k).is_some()) { return false; }
    if v["success"] != true { return failed(v) && v.get("image").is_none() && v.get("compact").is_none(); }
    let names = ["action", "success", "request_id", "preflight_token", "document_id", "revision", "side", "sha256", "compact", "image"];
    if !v.as_object().is_some_and(|m| names.iter().all(|k| m.contains_key(*k))
        && m.keys().all(|k| names.contains(&k.as_str()) || k == "event" || k == "outcome_unknown"))
        || !v.get("event").map_or(true, |e| e == "batch_result")
        || !v.get("outcome_unknown").map_or(true, |unknown| unknown == false) { return false; }
    let image = &v["image"]; let compact = &v["compact"];
    let (Some(w), Some(h)) = (image["width"].as_u64(), image["height"].as_u64()) else { return false; };
    image["sha256"] == v["sha256"] && collarbone::image(image, (w, h))
        && collarbone::compact_image(compact, (w, h))
        && ["mime", "width", "height", "sha256"].iter().all(|k| compact[*k] == image[*k])
}
fn commit(v: &Value) -> bool {
    if v["success"] != true { return failed(v); }
    let (Some(outcomes), Some(acks), Some(applied), Some(ops)) = (v["target_outcomes"].as_array(),
        v[ACK].as_array(), v["applied"].as_array(), v["module_scope"].as_array()) else { return false; };
    if v["outcome_unknown"] != false || v["people_transfer"] != true || outcomes.is_empty()
        || outcomes.len() > MAX_TARGETS || acks.is_empty() || !ops.contains(&json!(OP))
        || ops.len() > 256 || !ops.iter().all(token) || ops.iter().enumerate().any(|(i, op)| ops[..i].contains(op))
        || (ops.contains(&json!(collarbone::OP)) != v.get(collarbone::ACK).is_some())
        || (!v["batch_id"].is_null() && !text(&v["batch_id"]))
        || !hex(&v["source_snapshot"]["document_id"], 32) || !revision(&v["source_snapshot"]["revision"])
        || !v["source_snapshot"]["path"].as_str().is_some_and(|p| !p.is_empty()) { return false; }
    let mut remaining: std::collections::BTreeMap<_, _> = acks.iter()
        .map(|ack| (ack["document_id"].as_str().unwrap(), &ack["revision"])).collect();
    let mut seen = std::collections::BTreeSet::new(); let mut indices = std::collections::BTreeSet::new();
    let mut actual = Vec::new(); let mut noops = 0;
    for row in outcomes {
        if !hex(&row["document_id"], 32) || !revision(&row["expected_revision"])
            || !seen.insert(row["document_id"].as_str().unwrap()) { return false; }
        let ack = remaining.remove(row["document_id"].as_str().unwrap());
        if ack.is_some_and(|r| r != &row["expected_revision"]) { return false; }
        match row["outcome"].as_str() {
            Some("applied") => {
                if ack.is_none() || !index(&row["index"]) || !indices.insert(row["index"].as_u64().unwrap())
                    || !row["blocked"].is_null() || row["current_revision"] != row["expected_revision"]
                    || !revision(&row["result_revision"])
                    || row["result_revision"].as_str().unwrap().parse::<u64>().unwrap() <= row["expected_revision"].as_str().unwrap().parse::<u64>().unwrap()
                    || v["batch_id"].is_null() { return false; }
                actual.push(row["index"].clone());
            }
            Some("noop") => {
                if ack.is_none() || !index(&row["index"]) || !indices.insert(row["index"].as_u64().unwrap())
                    || !row["blocked"].is_null() || row["current_revision"] != row["expected_revision"]
                    || row["result_revision"] != row["expected_revision"] { return false; }
                noops += 1;
            }
            Some("skipped") => {
                if !row["blocked"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000)
                    || (!row["index"].is_null() && !index(&row["index"]))
                    || (!row["current_revision"].is_null() && !revision(&row["current_revision"]))
                    || (!row["result_revision"].is_null() && !revision(&row["result_revision"])) { return false; }
            }
            _ => return false,
        }
    }
    remaining.is_empty() && (!actual.is_empty() || noops > 0) && &actual == applied
        && (v["batch_id"].is_null() == actual.is_empty())
}
pub(crate) fn receipt(v: &Value) -> bool {
    if v["action"] == "eye_bag_visual" { return image_receipt(v); }
    let evidence = v["applies"].get("eye_bag").is_some() || v["targets"].as_array().is_some_and(|rows|
        rows.iter().any(|row| ["eye_bag", "eye_bag_coverage", "eye_bag_visual"].iter()
            .any(|key| row["people_transfer"].get(*key).is_some())));
    if (evidence || v.get(ACK).is_some()) && FOREIGN.iter().any(|key| v.get(*key).is_some()) { return false; }
    if evidence && (v["action"] != "preflight" || v.get(ACK).is_some() || !preflight(v)) { return false; }
    let Some(ack) = v.get(ACK) else { return true; };
    v["action"] == "commit" && hex(&v["preflight_token"], 32) && acknowledgments(ack)
        && paired_acknowledgments(v) && commit(v)
}

#[cfg(test)]
#[path = "eye_bag_batch_protocol_tests.rs"]
mod tests;
