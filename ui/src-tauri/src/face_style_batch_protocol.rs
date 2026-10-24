//! Named face-style batch review transport. AUTHORED / UNRUN.
//! The existing batch owner retains the plan, atomic publication and history.
//! Native checks frozen identities and PNG framing, not face/render quality.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use crate::original_shadow_transfer_protocol::{hex, revision, source_proof};
use crate::batch_api::collarbone;

pub(crate) const ACK: &str = "face_style_review_ack";
pub(crate) const MAX_TARGETS: usize = 16;
// Frozen scope order is lexical, not the single-face catalogue's display order.
pub(crate) const OPS: &[&str] = &["lnx.brow_shape.v1", "lnx.chin_length.v1", "lnx.chin_shape.v1",
    "lnx.eye_shape.v1", "lnx.face_contour.v1", "lnx.face_size.v1", "lnx.lower_face.v1",
    "lnx.mid_face.v1", "lnx.mouth_shape.v1", "lnx.nose_shape.v1"];
pub(crate) const LEAVES: &[(&str, &[&str])] = &[
    ("lnx.brow_shape.v1", &["/position/linked", "/position/left", "/position/right"]),
    ("lnx.chin_length.v1", &["/amount"]),
    ("lnx.chin_shape.v1", &["/linked", "/left", "/right"]),
    ("lnx.eye_shape.v1", &["/size/linked", "/size/left", "/size/right", "/spacing/linked", "/spacing/left", "/spacing/right", "/position/linked", "/position/left", "/position/right"]),
    ("lnx.face_contour.v1", &["/temple/linked", "/temple/left", "/temple/right", "/cheekbone/linked", "/cheekbone/left", "/cheekbone/right", "/jaw/linked", "/jaw/left", "/jaw/right"]),
    ("lnx.face_size.v1", &["/amount"]), ("lnx.lower_face.v1", &["/amount"]),
    ("lnx.mid_face.v1", &["/amount"]), ("lnx.mouth_shape.v1", &["/vertical"]),
    ("lnx.nose_shape.v1", &["/height"]),
];
fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|k| m.contains_key(*k)))
}
fn text(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 128 && !s.chars().any(char::is_control))
}
fn safe_revision(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
pub(crate) fn recipe(v: &Value) -> bool {
    fields(v, &["version", "style", "amount"]) && v["version"].as_u64() == Some(1)
        && matches!(v["style"].as_str(), Some("classic" | "youthful" | "bold" | "youth" | "round" | "long" | "square"))
        && v["amount"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n))
}
fn recipe_digest(v: &Value) -> Option<String> {
    if !recipe(v) { return None; }
    let mut hash = Sha256::new();
    hash.update(b"lumaretouch.face-style.v1\0");
    hash.update(v["style"].as_str()?.as_bytes()); hash.update(b"\0");
    let amount = v["amount"].as_f64()?;
    hash.update((if amount == 0.0 { 0.0_f64 } else { amount }).to_be_bytes());
    Some(format!("{:x}", hash.finalize()))
}
pub(crate) fn selection(v: &Value) -> bool {
    fields(v, OPS) && LEAVES.iter().all(|(op, paths)| v[*op].as_array().is_some_and(|selected|
        selected.len() == paths.len() && paths.iter().all(|path| selected.iter().filter(|p| p.as_str() == Some(*path)).count() == 1)))
}
pub(crate) fn endpoint(v: &Value) -> bool {
    let d = &v["document"];
    fields(v, &["document", "people_scope", "state_revision", "association_revision", "graph_sha256", "source_proof"])
        && fields(d, &["document_id", "epoch", "revision"]) && hex(&d["document_id"], 32)
        && text(&d["epoch"]) && safe_revision(&d["revision"])
        && (v["people_scope"] == "project" || v["people_scope"] == d["document_id"])
        && safe_revision(&v["state_revision"]) && safe_revision(&v["association_revision"])
        && hex(&v["graph_sha256"], 64) && source_proof(&v["source_proof"])
}
pub(crate) fn face(v: &Value, asset: &Value) -> bool {
    fields(v, &["asset_sha256", "face_instance_id", "analysis_revision"])
        && hex(&v["asset_sha256"], 64) && &v["asset_sha256"] == asset
        && text(&v["face_instance_id"]) && safe_revision(&v["analysis_revision"])
}
fn request(v: &Value) -> bool {
    if !fields(v, &["target_policy", "source_ref", "selection", "source", "targets", "face_style"])
        || v["target_policy"] != "explicit_face_map" || !recipe(&v["face_style"])
        || !selection(&v["selection"]) || !endpoint(&v["source"])
        || !face(&v["source_ref"], &v["source"]["source_proof"]["asset_sha256"]) { return false; }
    let Some(targets) = v["targets"].as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    !targets.is_empty() && targets.len() <= MAX_TARGETS && targets.iter().all(|row| {
        let owner = &row["target"];
        let Some(refs) = row["target_refs"].as_array() else { return false; };
        let mut faces = std::collections::BTreeSet::new();
        fields(row, &["target", "target_refs"]) && endpoint(owner)
            && owner["document"]["document_id"] != v["source"]["document"]["document_id"]
            && owner["document"]["epoch"] == v["source"]["document"]["epoch"]
            && seen.insert(owner["document"]["document_id"].as_str().unwrap())
            && !refs.is_empty() && refs.len() <= 128 && refs.iter().all(|r|
                face(r, &owner["source_proof"]["asset_sha256"]) && faces.insert(r["face_instance_id"].as_str().unwrap()))
    })
}
fn preflight_request(v: &Value) -> bool {
    let Some(map) = v.as_object() else { return false; };
    let required = ["cmd", "action", "request_id", "docs", "module_scope", "people_transfer"];
    if !required.iter().all(|k| map.contains_key(*k))
        || !map.keys().all(|k| required.contains(&k.as_str()) || k == "conflict_policy")
        || v["cmd"] != "batch" || v["action"] != "preflight" || !text(&v["request_id"])
        || v["module_scope"] != json!(OPS) || !request(&v["people_transfer"])
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
        fields(row, &["document_id", "revision", "before_sha256", "after_sha256", "recipe_sha256"])
        && text(&row["document_id"]) && revision(&row["revision"])
        && ["before_sha256", "after_sha256", "recipe_sha256"].iter().all(|k| hex(&row[*k], 64))
        && seen.insert(row["document_id"].as_str().unwrap()))
}
fn image_request(v: &Value) -> bool {
    fields(v, &["cmd", "action", "request_id", "preflight_token", "document_id", "revision", "side", "sha256"])
        && v["cmd"] == "batch" && v["action"] == "face_style_visual" && text(&v["request_id"])
        && hex(&v["preflight_token"], 32) && text(&v["document_id"]) && revision(&v["revision"])
        && matches!(v["side"].as_str(), Some("before" | "after")) && hex(&v["sha256"], 64)
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if v["people_transfer"]["target_policy"] == "persistent_association" {
        return crate::batch_api::portrait_cohort::command(v);
    }
    if v["action"] == "face_style_visual" {
        return if image_request(v) { Ok(()) } else { Err("Face-style image read needs exact bounded frozen coordinates".into()) };
    }
    if v["people_transfer"].get("face_style").is_some() && !preflight_request(v) {
        return Err("Named face-style batch needs an exact explicit face map and all thirty owned leaves".into());
    }
    if let Some(ack) = v.get(ACK) {
        if !fields(v, &["cmd", "action", "request_id", "preflight_token", ACK])
            || v["cmd"] != "batch" || v["action"] != "commit" || !text(&v["request_id"])
            || !hex(&v["preflight_token"], 32) || !acknowledgments(ack) {
            return Err("Face-style batch commit needs its exact ordered frozen image and recipe acknowledgments".into());
        }
    }
    Ok(())
}
pub(crate) fn read_only(v: &Value) -> bool { image_request(v) || preflight_request(v) }
/// The original request is compared locally after JSON decoding. Recipe amount
/// alone is normalized to float64 so JSON 1 and 1.0 have the same meaning.
pub(crate) fn request_digest(v: &Value) -> String {
    let mut request = v.clone();
    if let Some(amount) = v["face_style"]["amount"].as_f64() {
        request["face_style"]["amount"] = json!(if amount == 0.0 { 0.0_f64 } else { amount });
    }
    collarbone::request_digest(&request)
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    command(v)?;
    if image_request(v) {
        return Ok(Some(json!({"preflight_token":v["preflight_token"], "document_id":v["document_id"],
            "revision":v["revision"], "side":v["side"], "sha256":v["sha256"]})));
    }
    if let Some(ack) = v.get(ACK) {
        return Ok(Some(json!({"module_scope":OPS, "preflight_token":v["preflight_token"], (ACK):ack})));
    }
    if preflight_request(v) {
        return Ok(Some(json!({"module_scope":OPS, "policy":v.get("conflict_policy").cloned().unwrap_or(json!("skip_and_report")),
            "face_style_applies_sha256":request_digest(&v["people_transfer"])})));
    }
    Ok(None)
}
fn coefficient(style: &str, op: &str, path: &str) -> f64 {
    let field = path.split('/').nth(1).unwrap_or("");
    match (style, op, field) {
        ("classic", "lnx.face_contour.v1", "temple") => -0.12,
        ("classic", "lnx.face_contour.v1", "cheekbone") => 0.18,
        ("classic", "lnx.face_contour.v1", "jaw") => -0.20,
        ("classic", "lnx.eye_shape.v1", "size") => 0.18,
        ("youthful", "lnx.mid_face.v1", "amount") => -0.08,
        ("youthful", "lnx.lower_face.v1", "amount") => -0.04,
        ("youthful", "lnx.brow_shape.v1", "position") => -0.04,
        ("youthful", "lnx.eye_shape.v1", "spacing") => 0.04,
        ("youthful", "lnx.eye_shape.v1", "position") => -0.04,
        ("youthful", "lnx.nose_shape.v1", "height") => -0.03,
        ("youthful", "lnx.mouth_shape.v1", "vertical") => -0.03,
        ("bold", "lnx.face_size.v1", "amount") => 0.25,
        ("youth", "lnx.face_contour.v1", "temple") => -0.10,
        ("youth", "lnx.face_contour.v1", "cheekbone") => 0.14,
        ("youth", "lnx.face_contour.v1", "jaw") => -0.16,
        ("youth", "lnx.chin_shape.v1", "left" | "right") => 0.06,
        ("round", "lnx.face_contour.v1", "cheekbone") => 0.25,
        ("round", "lnx.face_contour.v1", "jaw") => -0.12,
        ("round", "lnx.chin_shape.v1", "left" | "right") => 0.18,
        ("round", "lnx.chin_length.v1", "amount") => 0.06,
        ("long", "lnx.mid_face.v1", "amount") => -0.25,
        ("long", "lnx.lower_face.v1", "amount") => -0.18,
        ("long", "lnx.chin_length.v1", "amount") => -0.08,
        ("square", "lnx.face_contour.v1", "jaw") => -0.30,
        ("square", "lnx.chin_shape.v1", "left" | "right") => 0.08,
        _ => 0.0,
    }
}
pub(crate) fn parameters(v: &Value, r: &Value) -> bool {
    if !recipe(r) { return false; }
    let Some(rows) = v.as_array() else { return false; };
    if rows.len() != 30 { return false; }
    let mut wanted: std::collections::BTreeSet<(&str, &str)> = LEAVES.iter()
        .flat_map(|(op, paths)| paths.iter().map(move |path| (*op, *path))).collect();
    rows.iter().all(|row| {
        let (Some(op), Some(path)) = (row["operation_id"].as_str(), row["parameter_path"].as_str()) else { return false; };
        if !fields(row, &["operation_id", "parameter_path", "value"]) || !wanted.remove(&(op, path)) { return false; }
        if path.ends_with("/linked") { return row["value"] == true; }
        let amount = r["amount"].as_f64().unwrap();
        let expected = if amount == 0.0 { 0.0 } else { coefficient(r["style"].as_str().unwrap(), op, path) * amount };
        row["value"].as_f64() == Some(expected)
    }) && wanted.is_empty()
}
fn visual(v: &Value, target: &Value, owner: &Value, r: &Value) -> bool {
    if !fields(v, &["version", "document_id", "revision", "source_proof", "before_state_sha256", "candidate_state_sha256",
        "before_people_sha256", "candidate_people_sha256", "source_size", "before_output_size", "after_output_size", "before", "after", "recipe_sha256"])
        || v["version"].as_u64() != Some(1) || v["document_id"] != target["document_id"] || v["revision"] != target["revision"]
        || v["source_proof"] != owner["source_proof"] || !source_proof(&v["source_proof"])
        || ["before_state_sha256", "candidate_state_sha256", "before_people_sha256", "candidate_people_sha256"].iter().any(|k| !hex(&v[*k], 64))
        || v["recipe_sha256"].as_str() != recipe_digest(r).as_deref() { return false; }
    let (Some(source), Some(before), Some(after)) = (collarbone::size(&v["source_size"]),
        collarbone::size(&v["before_output_size"]), collarbone::size(&v["after_output_size"])) else { return false; };
    let derived = &v["source_proof"]["creative_source"];
    (derived.is_null() || (derived["width"].as_u64() == Some(source.0) && derived["height"].as_u64() == Some(source.1)))
        && collarbone::compact_image(&v["before"], before) && collarbone::compact_image(&v["after"], after)
}
fn target_review(v: &Value, row: &Value, requested: &Value, applies: &Value) -> bool {
    let owner = &requested["target"];
    fields(v, &["version", "source_document", "target_document", "source_ref", "target_refs", "parameters",
        "source_state_revision", "target_state_revision", "source_association_revision", "target_association_revision",
        "transfer_policy", "excluded", "source_owner", "target_owner", "target_policy", "face_style", "face_style_visual"])
        && v["version"].as_u64() == Some(1) && v["target_policy"] == "explicit_face_map"
        && v["transfer_policy"] == "selected_parameter_keys_replace"
        && v["excluded"] == json!(["local_assets", "landmarks", "masks", "identity_links"])
        && v["source_document"] == applies["source"]["document"] && v["target_document"] == owner["document"]
        && v["source_ref"] == applies["source_ref"] && v["target_refs"] == requested["target_refs"]
        && v["source_owner"] == applies["source"] && v["target_owner"] == *owner
        && v["source_state_revision"] == applies["source"]["state_revision"] && v["target_state_revision"] == owner["state_revision"]
        && v["source_association_revision"] == applies["source"]["association_revision"] && v["target_association_revision"] == owner["association_revision"]
        && recipe(&v["face_style"]) && recipe_digest(&v["face_style"]) == recipe_digest(&applies["face_style"])
        && parameters(&v["parameters"], &v["face_style"]) && visual(&v["face_style_visual"], row, owner, &v["face_style"])
}
fn preflight(v: &Value) -> bool {
    let applies = &v["applies"];
    if !request(applies) || v["module_scope"] != json!(OPS) || v["people_transfer"] != true
        || !v["persistent_association"].is_null() || !v["collarbone_cohort"].is_null()
        || !hex(&v["preflight_token"], 32) || v.to_string().len() > 7 * 1024 * 1024
        || !matches!(v["policy"].as_str(), Some("skip_and_report" | "recheck"))
        || v["source_snapshot"]["document_id"] != applies["source"]["document"]["document_id"]
        || v["source_snapshot"]["revision"].as_str() != applies["source"]["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref() { return false; }
    let (Some(targets), Some(rejected)) = (v["targets"].as_array(), v["rejected_docs"].as_array()) else { return false; };
    let requested = applies["targets"].as_array().unwrap();
    if targets.len() > MAX_TARGETS || targets.len() + rejected.len() != requested.len()
        || (v["policy"] == "recheck" && !rejected.is_empty()) { return false; }
    let mut seen = std::collections::BTreeSet::new(); let mut blocked = 0_u64;
    for row in rejected {
        if !fields(row, &["doc", "error"]) || !hex(&row["doc"], 32)
            || !row["error"].as_str().is_some_and(|s| !s.trim().is_empty())
            || !seen.insert(row["doc"].as_str().unwrap())
            || !requested.iter().any(|r| r["target"]["document"]["document_id"] == row["doc"]) { return false; }
    }
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
    }
    v["blocked"].as_u64() == Some(blocked) && v["ok"].as_u64() == Some(targets.len() as u64 - blocked)
}
fn image_receipt(v: &Value) -> bool {
    if v["success"] != true { return true; }
    let required = ["action", "success", "request_id", "preflight_token", "document_id", "revision", "side", "sha256", "compact", "image"];
    if !v.as_object().is_some_and(|m| required.iter().all(|k| m.contains_key(*k))
        && m.keys().all(|k| required.contains(&k.as_str()) || k == "event" || k == "outcome_unknown"))
        || !v.get("event").map_or(true, |event| event == "batch_result")
        || !v.get("outcome_unknown").map_or(true, |unknown| unknown == false) { return false; }
    let image = &v["image"]; let compact = &v["compact"];
    let (Some(w), Some(h)) = (image["width"].as_u64(), image["height"].as_u64()) else { return false; };
    hex(&v["preflight_token"], 32) && text(&v["document_id"]) && revision(&v["revision"])
        && matches!(v["side"].as_str(), Some("before" | "after")) && hex(&v["sha256"], 64)
        && image["sha256"] == v["sha256"] && collarbone::image(image, (w, h))
        && collarbone::compact_image(compact, (w, h))
        && ["mime", "width", "height", "sha256"].iter().all(|k| compact[*k] == image[*k])
}
fn commit(v: &Value) -> bool {
    if v["success"] != true { return true; }
    let (Some(outcomes), Some(acks), Some(applied)) = (v["target_outcomes"].as_array(), v[ACK].as_array(), v["applied"].as_array()) else { return false; };
    if v["people_transfer"] != true || outcomes.is_empty() || outcomes.len() > MAX_TARGETS || acks.is_empty()
        || (!v["batch_id"].is_null() && !text(&v["batch_id"]))
        || !hex(&v["source_snapshot"]["document_id"], 32) || !revision(&v["source_snapshot"]["revision"])
        || !v["source_snapshot"]["path"].as_str().is_some_and(|p| !p.is_empty()) { return false; }
    let mut remaining: std::collections::BTreeMap<_, _> = acks.iter()
        .map(|ack| (ack["document_id"].as_str().unwrap(), &ack["revision"])).collect();
    let mut seen = std::collections::BTreeSet::new();
    let mut indices = std::collections::BTreeSet::new(); let mut actual = Vec::new();
    for row in outcomes {
        if !hex(&row["document_id"], 32) || !revision(&row["expected_revision"])
            || !seen.insert(row["document_id"].as_str().unwrap()) { return false; }
        let ack = remaining.remove(row["document_id"].as_str().unwrap());
        if ack.is_some_and(|revision| revision != &row["expected_revision"]) { return false; }
        match row["outcome"].as_str() {
            Some("applied") => {
                if ack.is_none() || !safe_revision(&row["index"]) || !indices.insert(row["index"].as_u64().unwrap())
                    || !row["blocked"].is_null() || row["current_revision"] != row["expected_revision"]
                    || !revision(&row["result_revision"])
                    || row["result_revision"].as_str().unwrap().parse::<u64>().unwrap()
                        < row["expected_revision"].as_str().unwrap().parse::<u64>().unwrap()
                    || (v["batch_id"].is_null() && row["result_revision"] != row["expected_revision"]) { return false; }
                // A reviewed zero/no-op may leave the revision and batch ID
                // unchanged. It still must retain its exact reviewed target.
                actual.push(row["index"].clone());
            }
            Some("skipped") => {
                if !row["blocked"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000)
                    || (!row["index"].is_null() && !safe_revision(&row["index"]))
                    || (!row["current_revision"].is_null() && !revision(&row["current_revision"]))
                    || (!row["result_revision"].is_null() && !revision(&row["result_revision"])) { return false; }
            }
            _ => return false,
        }
    }
    remaining.is_empty() && !actual.is_empty() && &actual == applied
}
pub(crate) fn receipt(v: &Value) -> bool {
    if v["action"] == "face_style_visual" { return image_receipt(v); }
    if v["applies"]["target_policy"] == "persistent_association" {
        return crate::batch_api::portrait_cohort::receipt(v);
    }
    let target_evidence = v["targets"].as_array().is_some_and(|rows| rows.iter().any(|row|
        row["people_transfer"].get("face_style").is_some() || row["people_transfer"].get("face_style_visual").is_some()));
    let named = v["applies"].get("face_style").is_some() || target_evidence;
    if named && (v["action"] != "preflight" || v["success"] != true || !preflight(v)) { return false; }
    let Some(ack) = v.get(ACK) else { return true; };
    v["action"] == "commit" && acknowledgments(ack) && hex(&v["preflight_token"], 32)
        && v["module_scope"] == json!(OPS)
        && (if v["success"] == true {
            v["outcome_unknown"] == false
        } else { v["success"] == false && v["outcome_unknown"].is_boolean()
            && v["error"].as_str().is_some_and(|error| !error.trim().is_empty()) })
        && !["torso_review_ack", "waist_review_ack", "head_review_ack", "spill_review_ack", "shadow_review_ack", "collarbone_review_ack", "collarbone_cohort", "portrait_cohort_ack", "portrait_cohort"]
            .iter().any(|k| v.get(*k).is_some()) && commit(v)
}

#[cfg(test)]
#[path = "face_style_batch_protocol_tests.rs"]
mod tests;
