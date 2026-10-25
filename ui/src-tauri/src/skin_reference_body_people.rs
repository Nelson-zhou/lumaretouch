// SPDX-License-Identifier: GPL-3.0-or-later
//! Body-only selected-reference transport in the existing people mailbox.
//! Shape/ownership/receipt/PNG validation only; no new solver or numerical path.
//! AUTHORED / UNRUN: these fixtures are not product or photographic acceptance.
use serde_json::{json, Value};
use std::collections::BTreeSet;
use crate::original_shadow_transfer_protocol::{hex, source_proof};
// Pure, operation-neutral validators only. Face selection/review semantics stay private.
use super::skin_reference_match::{fields, allowed, identifier, revision, next_revision,
    decimal_revision, amount, face_ref, face_refs, ack, source, source_image, owner,
    visual, diagnostic, availability, face_box, image};

pub(crate) const MARKER: &str = "skin_reference_body_request";
pub(crate) const ACTIONS: &[&str] = &["skin_reference_body_catalog", "skin_reference_body_preview",
    "skin_reference_body_image", "skin_reference_body_confirm", "skin_reference_body_clear"];
const OP: &str = "lnx.skin_reference_body_match.v1";
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_FACES: usize = 64;
const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;

fn body_ref(v: &Value, asset: &Value) -> bool {
    fields(v, &["asset_sha256", "body_instance_id", "analysis_revision"])
        && hex(asset, 64) && v["asset_sha256"] == *asset && identifier(&v["body_instance_id"])
        && revision(&v["analysis_revision"])
}
fn pair(reference: &Value, target: &Value, asset: &Value) -> bool {
    face_ref(reference, asset) && face_ref(target, asset)
        && (reference["face_instance_id"] != target["face_instance_id"] || reference == target)
}
fn coordinates(v: &Value, point: bool) -> bool {
    v.as_array().is_some_and(|items| items.len() == 2 && items.iter().all(|n|
        n.as_f64().is_some_and(|n| n.is_finite() && if point { (0.0..=1.0).contains(&n) } else { (-4.0..=4.0).contains(&n) })))
}
/// Manual vectors only: semantics, inferred geometry and unrelated masks are not consent.
fn mask(v: &Value) -> bool {
    if !fields(v, &["version", "domain", "objects"]) || v["version"].as_u64() != Some(1)
        || v["domain"] != "source-normalized" { return false; }
    let Some(objects) = v["objects"].as_array() else { return false; };
    let mut ids = BTreeSet::new(); let mut points = 0; let mut positive_add = false;
    (1..=64).contains(&objects.len()) && objects.iter().all(|row| {
        if !fields(row, &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "points", "axes"])
            || !row["id"].as_str().is_some_and(|id| !id.is_empty() && id.len() <= 64
                && id.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b)) && ids.insert(id))
            || !row["name"].as_str().is_some_and(|name| !name.trim().is_empty() && name.chars().count() <= 80
                && name.chars().all(|c| c >= ' '))
            || !row["enabled"].is_boolean() || !matches!(row["operation"].as_str(), Some("add" | "subtract"))
            || row["kind"] != "brush" || !amount(&row["opacity"], false)
            || !row["feather"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n)) { return false; }
        let Some(stroke) = row["points"].as_array() else { return false; };
        let Some(axes) = row["axes"].as_array() else { return false; };
        if !(1..=1024).contains(&stroke.len()) || !stroke.iter().all(|p| coordinates(p, true))
            || axes.len() != 2 || !axes.iter().all(|axis| coordinates(axis, false)) { return false; }
        let determinant = axes[0][0].as_f64().unwrap() * axes[1][1].as_f64().unwrap()
            - axes[0][1].as_f64().unwrap() * axes[1][0].as_f64().unwrap();
        if determinant.abs() < 1e-12 { return false; }
        points += stroke.len();
        positive_add |= row["enabled"] == true && row["operation"] == "add" && amount(&row["opacity"], true);
        true
    }) && points <= 8192 && positive_add
}
fn consent(v: &Value, asset: &Value) -> bool {
    fields(v, &["operation_id", "body_ref", "points_sha256", "recipe", "visible", "unoccluded", "ownership_confirmed", "reference_unchanged"])
        && v["operation_id"] == OP && body_ref(&v["body_ref"], asset) && hex(&v["points_sha256"], 64)
        && mask(&v["recipe"]) && ["visible", "unoccluded", "ownership_confirmed", "reference_unchanged"].iter().all(|key| v[*key] == true)
}
pub(crate) fn action(v: &Value) -> bool { v["action"].as_str().is_some_and(|name| ACTIONS.contains(&name)) }
pub(crate) fn mutation(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(), Some("skin_reference_body_confirm" | "skin_reference_body_clear"))
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let mut context = json!({}); for key in CONTEXT { context[*key] = v[*key].clone(); }
    let envelope = allowed(v, REQUEST, &["cmd", "request_id", "host_epoch"])
        && v.get("request_id").map_or(true, identifier)
        && v.get("cmd").map_or(true, |cmd| cmd == "people" && identifier(&v["request_id"]))
        && v.get("host_epoch").map_or(true, |epoch| v["cmd"] == "people" && hex(epoch, 32));
    let p = &v["payload"]; let asset = &v["target"]["target_id"];
    let valid = envelope && v.to_string().len() <= MAX_REQUEST_BYTES && super::valid_context(&context)
        && identifier(&v["document_id"]) && identifier(&v["document_epoch"])
        && fields(&v["target"], &["scope", "target_id", "face_ref"])
        && v["target"]["scope"] == "all_people" && v["target"]["face_ref"].is_null() && hex(asset, 64)
        && match v["action"].as_str() {
            Some("skin_reference_body_catalog" | "skin_reference_body_clear") => fields(p, &[]),
            Some("skin_reference_body_preview") => fields(p, &["version", "reference_face_ref", "target_face_ref", "review", "amount", "source_review_sha256", "ownership_confirmed"])
                && p["version"].as_u64() == Some(1) && p["ownership_confirmed"] == true && amount(&p["amount"], true)
                && hex(&p["source_review_sha256"], 64) && pair(&p["reference_face_ref"], &p["target_face_ref"], asset)
                && consent(&p["review"], asset),
            Some("skin_reference_body_image") => fields(p, &["token", "side", "sha256", "review_sha256"])
                && hex(&p["token"], 32) && matches!(p["side"].as_str(), Some("before" | "after"))
                && hex(&p["sha256"], 64) && hex(&p["review_sha256"], 64),
            Some("skin_reference_body_confirm") => fields(p, &["token", "ack"]) && hex(&p["token"], 32) && ack(&p["ack"]),
            _ => false,
        };
    if valid { Ok(()) } else { Err("身体肤色参照匹配需要当前照片、明确身体归属、独立手绘审核及完整图像凭据".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({}); for key in REQUEST { request[*key] = v[*key].clone(); }
    Ok(Some(json!({"skin_reference_body_request": request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(), Some("skin_reference_body_catalog" | "skin_reference_body_preview" | "skin_reference_body_image"))
        && identifier(&v["request_id"]) && command(v).is_ok()
}

/// Complete body lane. An active face lane may retain a donor when this lane is empty.
fn report(v: &Value, asset: &Value) -> bool {
    if !fields(v, &["version", "operation_id", "reference_face_ref", "target_face_refs", "amounts", "bank_sha256"])
        || v["version"].as_u64() != Some(1) || v["operation_id"] != OP || !hex(&v["bank_sha256"], 64)
        || !face_refs(&v["target_face_refs"], asset, 0, MAX_FACES) { return false; }
    let refs = v["target_face_refs"].as_array().unwrap();
    let Some(amounts) = v["amounts"].as_array() else { return false; };
    if amounts.len() != refs.len() || (v["reference_face_ref"].is_null() && !refs.is_empty())
        || (!v["reference_face_ref"].is_null() && !face_ref(&v["reference_face_ref"], asset)) { return false; }
    let mut seen = BTreeSet::new();
    amounts.iter().all(|row| fields(row, &["face_ref", "amount", "support_sha256"])
        && face_ref(&row["face_ref"], asset) && refs.contains(&row["face_ref"])
        && seen.insert(row["face_ref"]["face_instance_id"].as_str().unwrap())
        && pair(&v["reference_face_ref"], &row["face_ref"], asset)
        && amount(&row["amount"], true) && hex(&row["support_sha256"], 64))
}
/// Only one selected target may be added/replaced. Every retained row is exact.
fn retained(v: &Value) -> bool {
    let before = &v["before_current"]; let after = &v["candidate_current"]; let selected = &v["target_face_ref"];
    let before_refs = before["target_face_refs"].as_array().unwrap(); let after_refs = after["target_face_refs"].as_array().unwrap();
    let expected: Vec<&Value> = before_refs.iter().filter(|row| *row != selected).chain(std::iter::once(selected)).collect();
    after["reference_face_ref"] == v["reference_face_ref"]
        && (before["reference_face_ref"].is_null() || before["reference_face_ref"] == v["reference_face_ref"])
        && after_refs.len() == expected.len() && after_refs.iter().all(|row| expected.contains(&row))
        && after["amounts"].as_array().unwrap().iter().all(|row| if row["face_ref"] == *selected {
            row["amount"].as_f64() == v["amount"].as_f64() && row["support_sha256"] == v["support_sha256"]
        } else { before["amounts"].as_array().unwrap().contains(row) })
}
fn same_report(a: &Value, b: &Value) -> bool {
    ["version", "operation_id", "reference_face_ref", "bank_sha256"].iter().all(|key| a[*key] == b[*key])
        && ["target_face_refs", "amounts"].iter().all(|key| {
            let (Some(left), Some(right)) = (a[*key].as_array(), b[*key].as_array()) else { return false; };
            left.len() == right.len() && left.iter().all(|row| right.contains(row))
        })
}
fn review(v: &Value, r: &Value) -> bool {
    let p = &r["payload"]; let asset = &r["target"]["target_id"];
    fields(v, &["version", "token", "operation_id", "owner", "source", "reference_face_ref", "target_face_ref", "body_ref", "body_review",
        "amount", "source_review_sha256", "body_bank_sha256", "before_current", "candidate_current", "candidate_state_revision",
        "before_bank_sha256", "candidate_bank_sha256", "support_sha256", "visual", "review_sha256"])
        && v["version"].as_u64() == Some(1) && v["operation_id"] == OP && hex(&v["token"], 32)
        && owner(&v["owner"], r) && source(&v["source"], asset)
        && pair(&v["reference_face_ref"], &v["target_face_ref"], asset)
        && v["reference_face_ref"] == p["reference_face_ref"] && v["target_face_ref"] == p["target_face_ref"]
        && consent(&v["body_review"], asset) && v["body_review"] == p["review"] && v["body_ref"] == p["review"]["body_ref"]
        && amount(&v["amount"], true) && v["amount"].as_f64() == p["amount"].as_f64()
        && hex(&v["source_review_sha256"], 64) && v["source_review_sha256"] == p["source_review_sha256"]
        && ["body_bank_sha256", "before_bank_sha256", "candidate_bank_sha256", "support_sha256", "review_sha256"].iter().all(|key| hex(&v[*key], 64))
        && next_revision(&v["candidate_state_revision"], &r["state_revision"])
        && report(&v["before_current"], asset) && report(&v["candidate_current"], asset)
        && v["before_current"]["bank_sha256"] == v["before_bank_sha256"]
        && v["candidate_current"]["bank_sha256"] == v["candidate_bank_sha256"]
        && retained(v) && visual(&v["visual"], &v["owner"], &v["source"])
}
fn catalogue(v: &Value, r: &Value) -> bool {
    let asset = &r["target"]["target_id"];
    if !fields(v, &["kind", "version", "operation_id", "scope", "source", "source_proof", "document_id", "revision", "source_image",
        "source_review_sha256", "faces", "targets", "current", "body_matching", "automatic_reference", "skin_reference_body_available", "skin_reference_body_reason"])
        || v["kind"] != "skin_reference_body_catalog" || v["version"].as_u64() != Some(1) || v["operation_id"] != OP
        || v["scope"] != "current-photo-body-only" || v["document_id"] != r["document_id"]
        || !decimal_revision(&v["revision"], &r["document_revision"]) || !source(&v["source"], asset)
        || !source_proof(&v["source_proof"]) || v["source_proof"]["asset_sha256"] != *asset
        || !hex(&v["source_review_sha256"], 64) || v["body_matching"] != true || v["automatic_reference"] != false
        || !availability(&v["skin_reference_body_available"], &v["skin_reference_body_reason"])
        || !report(&v["current"], asset) { return false; }
    let creative = &v["source_proof"]["creative_source"];
    if !creative.is_null() && (creative["width"] != v["source"]["width"] || creative["height"] != v["source"]["height"]) { return false; }
    let (Some(faces), Some(targets)) = (v["faces"].as_array(), v["targets"].as_array()) else { return false; };
    let mut seen = BTreeSet::new();
    if faces.len() > MAX_FACES || targets.len() > MAX_FACES || !faces.iter().all(|row|
        fields(row, &["face_ref", "box", "enabled", "available", "reason", "amount"])
        && face_ref(&row["face_ref"], asset) && seen.insert(row["face_ref"]["face_instance_id"].as_str().unwrap())
        && face_box(&row["box"]) && row["enabled"].is_boolean() && availability(&row["available"], &row["reason"])
        && (row["available"] != true || row["enabled"] == true) && amount(&row["amount"], false)) { return false; }
    let mut owners = BTreeSet::new(); let mut bodies = BTreeSet::new();
    if !targets.iter().all(|row| {
        let link = &row["association"];
        fields(row, &["face_ref", "body_ref", "points_sha256", "source", "association", "box", "amount"])
            && face_ref(&row["face_ref"], asset) && body_ref(&row["body_ref"], asset) && hex(&row["points_sha256"], 64)
            && owners.insert(row["face_ref"]["face_instance_id"].as_str().unwrap())
            && bodies.insert(row["body_ref"]["body_instance_id"].as_str().unwrap())
            && fields(&row["source"], &["sha256", "width", "height", "orientation"])
            && row["source"]["orientation"] == "exif_normalized_once"
            && ["sha256", "width", "height"].iter().all(|key| row["source"][*key] == v["source"][*key])
            && fields(link, &["person_id", "body_ref", "people_association_revision", "confirmation_revision"])
            && identifier(&link["person_id"]) && link["body_ref"] == row["body_ref"]
            && link["people_association_revision"] == r["association_revision"] && revision(&link["confirmation_revision"])
            && faces.iter().any(|face| face["face_ref"] == row["face_ref"] && face["enabled"] == true
                && face["box"] == row["box"] && face["amount"].as_f64() == row["amount"].as_f64())
    }) { return false; }
    let current = &v["current"];
    (current["reference_face_ref"].is_null() || faces.iter().any(|face| face["face_ref"] == current["reference_face_ref"]))
        && current["amounts"].as_array().unwrap().iter().all(|row| faces.iter().any(|face| face["face_ref"] == row["face_ref"]
            && face["enabled"] == true && face["amount"].as_f64() == row["amount"].as_f64()))
        && faces.iter().all(|face| face["enabled"] != true || face["amount"].as_f64() == Some(0.0)
            || current["target_face_refs"].as_array().unwrap().contains(&face["face_ref"]))
        && source_image(&v["source_image"], &v["source"])
}
fn document(v: &Value, r: &Value) -> bool {
    let people = &v["doc_state"]["people"]; let binding = &people["binding"];
    fields(binding, &["document_id", "document_epoch", "document_revision", "asset_sha256"])
        && binding["document_id"] == r["document_id"] && binding["document_epoch"] == r["document_epoch"]
        && binding["asset_sha256"] == r["target"]["target_id"]
        && next_revision(&binding["document_revision"], &r["document_revision"])
        && next_revision(&people["revision"], &r["state_revision"])
        && people["revision"] == v["payload"]["candidate_state_revision"]
        && people["association_revision"] == r["association_revision"]
        && report(&people["skin_reference_body_match"], &r["target"]["target_id"])
}
fn confirmation(v: &Value, r: &Value) -> bool {
    let p = &v["payload"]; let frozen = &p["review"]; let expected = &r["payload"];
    if !fields(p, &["kind", "token", "review_sha256", "ack", "reference_face_ref", "target_face_ref", "body_ref", "amount",
        "candidate_state_revision", "support_sha256", "candidate_bank_sha256", "review"])
        || p["kind"] != "skin_reference_body_confirm" || p["token"] != expected["token"] || p["ack"] != expected["ack"]
        || p["review_sha256"] != expected["ack"]["review_sha256"] { return false; }
    // The full frozen review proves retained rows and source/consent again.
    // It is a receipt, never a substitute for the host's token and served-image admission.
    let mut preview = r.clone(); preview["action"] = json!("skin_reference_body_preview");
    preview["payload"] = json!({"version":1, "reference_face_ref":frozen["reference_face_ref"], "target_face_ref":frozen["target_face_ref"],
        "review":frozen["body_review"], "amount":frozen["amount"], "source_review_sha256":frozen["source_review_sha256"], "ownership_confirmed":true});
    command(&preview).is_ok() && review(frozen, &preview)
        && ["token", "review_sha256", "reference_face_ref", "target_face_ref", "body_ref", "amount", "candidate_state_revision", "support_sha256", "candidate_bank_sha256"]
            .iter().all(|key| p[*key] == frozen[*key])
        && p["ack"]["before_sha256"] == frozen["visual"]["before"]["sha256"]
        && p["ack"]["after_sha256"] == frozen["visual"]["after"]["sha256"]
        && document(v, r) && same_report(&v["doc_state"]["people"]["skin_reference_body_match"], &frozen["candidate_current"])
}
fn clear(v: &Value, r: &Value) -> bool {
    let p = &v["payload"]; let actual = &v["doc_state"]["people"]["skin_reference_body_match"];
    fields(p, &["kind", "candidate_state_revision", "cleared_face_refs"])
        && p["kind"] == "skin_reference_body_clear" && face_refs(&p["cleared_face_refs"], &r["target"]["target_id"], 1, MAX_FACES)
        && document(v, r) && actual["target_face_refs"].as_array().is_some_and(Vec::is_empty)
        && actual["amounts"].as_array().is_some_and(Vec::is_empty)
}
pub(crate) fn released_read(v: &Value) -> bool {
    let r = &v[MARKER];
    fields(v, &["event", "protocol", "action", "request_id", "document_id", MARKER,
        "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && matches!(v["action"].as_str(), Some("skin_reference_body_catalog" | "skin_reference_body_preview" | "skin_reference_body_image"))
        && v["event"] == "people_result" && v["protocol"].as_u64() == Some(1) && identifier(&v["request_id"])
        && v["success"] == true && v["outcome_unknown"] == false && v["error"].is_null()
        && v["created_id"].is_null() && v["batch_id"].is_null() && v["frame_emitted"] == false && v["payload_released"] == true
        && fields(r, REQUEST) && command(r).is_ok() && r["action"] == v["action"] && r["document_id"] == v["document_id"]
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    let required = ["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", MARKER];
    let optional = ["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "doc_state", "payload_released"];
    if !allowed(v, &required, &optional) || v.to_string().len() > MAX_RESULT_BYTES || v["protocol"].as_u64() != Some(1)
        || !identifier(&v["request_id"]) || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()
        || v.get("event").is_some_and(|event| event != "people_result")
        || v.get("frame_emitted").is_some_and(|frame| !frame.is_boolean()) || !v["created_id"].is_null() || !v["batch_id"].is_null() { return false; }
    let r = &v[MARKER];
    if !fields(r, REQUEST) || command(r).is_err() || r["action"] != v["action"] || r["document_id"] != v["document_id"] { return false; }
    if v.get("payload_released").is_some() { return released_read(v); }
    if v["success"] == false {
        return diagnostic(&v["error"]) && v.get("payload").is_none() && v.get("doc_state").is_none() && v["frame_emitted"] != true;
    }
    if v["outcome_unknown"] != false || !v["error"].is_null() { return false; }
    let p = &v["payload"];
    if matches!(v["action"].as_str(), Some("skin_reference_body_catalog" | "skin_reference_body_preview" | "skin_reference_body_image"))
        && (v.get("doc_state").is_some() || v["frame_emitted"] == true) { return false; }
    match v["action"].as_str() {
        Some("skin_reference_body_catalog") => catalogue(p, r),
        Some("skin_reference_body_preview") => fields(p, &["kind", "review"]) && p["kind"] == "skin_reference_body_preview" && review(&p["review"], r),
        Some("skin_reference_body_image") => fields(p, &["kind", "token", "side", "sha256", "review_sha256", "image"])
            && p["kind"] == "skin_reference_body_image" && ["token", "side", "sha256", "review_sha256"].iter().all(|key| p[*key] == r["payload"][*key])
            && p["sha256"] == p["image"]["sha256"] && image(&p["image"]),
        Some("skin_reference_body_confirm") => confirmation(v, r),
        Some("skin_reference_body_clear") => clear(v, r),
        _ => false,
    }
}
/// Cross-domain recovery may settle only the exact original, validated receipt.
pub(crate) fn matches_request(command: &Value, value: &Value) -> bool {
    if command["cmd"] != "people" || !action(command) || !receipt(value)
        || value["event"] != "people_result" || command["request_id"] != value["request_id"]
        || command["action"] != value["action"] { return false; }
    let Ok(Some(identity)) = binding(command) else { return false; };
    identity[MARKER] == value[MARKER]
}
/// Admission reads existing bounded receipts only. A tombstone or an evicted
/// preview cannot grant new confirmation authority, even with a claimed hash.
pub(crate) fn confirmation_preview(command: &Value, previous: &Value) -> bool {
    let frozen = &previous["payload"]["review"]; let p = &command["payload"];
    command["cmd"] == "people" && command["action"] == "skin_reference_body_confirm" && self::command(command).is_ok()
        && previous["action"] == "skin_reference_body_preview" && previous["success"] == true
        && previous["outcome_unknown"] == false && receipt(previous)
        && CONTEXT.iter().all(|key| command[*key] == previous[MARKER][*key])
        && frozen["token"] == p["token"] && frozen["review_sha256"] == p["ack"]["review_sha256"]
        && frozen["visual"]["before"]["sha256"] == p["ack"]["before_sha256"]
        && frozen["visual"]["after"]["sha256"] == p["ack"]["after_sha256"]
}
pub(crate) fn confirmation_image(command: &Value, frozen: &Value, previous: &Value, side: &str) -> bool {
    let p = &previous["payload"]; let pixels = &p["image"];
    matches!(side, "before" | "after") && previous["action"] == "skin_reference_body_image"
        && previous["success"] == true && previous["outcome_unknown"] == false && receipt(previous)
        && CONTEXT.iter().all(|key| command[*key] == previous[MARKER][*key])
        && p["token"] == frozen["token"] && p["review_sha256"] == frozen["review_sha256"] && p["side"] == side
        && ["mime", "width", "height", "sha256"].iter().all(|key| pixels[*key] == frozen["visual"][side][*key])
}
/// Local-only digest of already parsed JSON, never a replacement for the engine
/// review SHA-256. Both sides use the same native canonicalizer and data types.
pub(crate) fn frozen_digest(value: &Value) -> String { crate::batch_api::collarbone::request_digest(value) }

// AUTHORED / UNRUN. Transport refusals only, not native fitting, rendered image,
// browser decoding, model inference, real photographs, or performance acceptance.
#[cfg(test)]
mod tests {
    use super::*;
    fn h(c: char) -> String { c.to_string().repeat(64) }
    fn face(id: &str) -> Value { json!({"asset_sha256":h('a'),"face_instance_id":id,"analysis_revision":2}) }
    fn body() -> Value { json!({"asset_sha256":h('a'),"body_instance_id":"body-target","analysis_revision":5}) }
    fn vectors() -> Value {
        json!({"version":1,"domain":"source-normalized","objects":[{"id":"brush-1","name":"Visible body skin",
            "enabled":true,"operation":"add","kind":"brush","opacity":1.0,"feather":0.0,
            "points":[[0.4,0.6],[0.4,0.7]],"axes":[[0.02,0.0],[0.0,0.02]]}]})
    }
    fn consent_fixture() -> Value {
        json!({"operation_id":OP,"body_ref":body(),"points_sha256":h('b'),"recipe":vectors(),
            "visible":true,"unoccluded":true,"ownership_confirmed":true,"reference_unchanged":true})
    }
    fn request(action: &str, payload: Value) -> Value {
        json!({"cmd":"people","request_id":"body-fixture","action":action,"payload":payload,
            "document_id":"doc","document_epoch":"epoch","document_revision":4,"state_revision":3,"association_revision":2,
            "target":{"scope":"all_people","target_id":h('a'),"face_ref":null}})
    }
    fn preview_request() -> Value {
        request("skin_reference_body_preview",json!({"version":1,"reference_face_ref":face("donor"),"target_face_ref":face("selected"),
            "review":consent_fixture(),"amount":0.5,"source_review_sha256":h('c'),"ownership_confirmed":true}))
    }
    fn source_proof_fixture() -> Value { json!({"asset_sha256":h('a'),"original_sha256":h('a'),"creative_source":null}) }
    fn current(candidate: bool) -> Value {
        let mut v = json!({"version":1,"operation_id":OP,"reference_face_ref":face("donor"),"target_face_refs":[face("retained")],
            "bank_sha256":if candidate {h('7')} else {h('6')},
            "amounts":[{"face_ref":face("retained"),"amount":0.25,"support_sha256":h('1')}]});
        if candidate {
            v["target_face_refs"].as_array_mut().unwrap().push(face("selected"));
            v["amounts"].as_array_mut().unwrap().push(json!({"face_ref":face("selected"),"amount":0.5,"support_sha256":h('2')}));
        }
        v
    }
    fn empty_current() -> Value {
        // Independently active FACE matching retains this donor after body clear.
        json!({"version":1,"operation_id":OP,"reference_face_ref":face("donor"),"target_face_refs":[],"amounts":[],"bank_sha256":h('6')})
    }
    fn review_fixture() -> (Value, Value) {
        let r = preview_request(); let proof = source_proof_fixture();
        let visual = json!({"version":1,"document_id":"doc","revision":"4","source_proof":proof,"source_size":[2048,1024],
            "before_output_size":[1200,1200],"after_output_size":[1200,1200],
            "before":{"mime":"image/png","width":1024,"height":1024,"sha256":h('e')},
            "after":{"mime":"image/png","width":1024,"height":1024,"sha256":h('f')},
            "before_state_sha256":h('3'),"candidate_state_sha256":h('4'),"before_people_sha256":h('5'),"candidate_people_sha256":h('8')});
        let frozen = json!({"version":1,"token":"c".repeat(32),"operation_id":OP,
            "owner":{"document":{"document_id":"doc","epoch":"epoch","revision":4},"people_scope":"project",
                "state_revision":3,"association_revision":2,"graph_sha256":h('5'),"source_proof":proof},
            "source":{"sha256":h('a'),"width":2048,"height":1024},"reference_face_ref":r["payload"]["reference_face_ref"],
            "target_face_ref":r["payload"]["target_face_ref"],"body_ref":body(),"body_review":consent_fixture(),"amount":0.5,
            "source_review_sha256":h('c'),"body_bank_sha256":h('9'),"before_current":current(false),"candidate_current":current(true),
            "candidate_state_revision":4,"before_bank_sha256":h('6'),"candidate_bank_sha256":h('7'),"support_sha256":h('2'),
            "visual":visual,"review_sha256":h('d')});
        (r,frozen)
    }
    fn result(r: &Value, payload: Value) -> Value {
        json!({"event":"people_result","protocol":1,"request_id":r["request_id"],"action":r["action"],"document_id":r["document_id"],
            "success":true,"outcome_unknown":false,"error":null,"created_id":null,"batch_id":null,"frame_emitted":false,
            "skin_reference_body_request":binding(r).unwrap().unwrap()[MARKER],"payload":payload})
    }
    fn document_fixture(report: Value) -> Value {
        json!({"people":{"binding":{"document_id":"doc","document_epoch":"epoch","document_revision":5,"asset_sha256":h('a')},
            "revision":4,"association_revision":2,"skin_reference_body_match":report,
            "selected_face_id":"unrelated-cursor","editing_target":{"scope":"person","target_id":"another-person","face_ref":null}}})
    }
    fn confirmation_fixture() -> (Value, Value) {
        confirmation_for(review_fixture().1)
    }
    fn confirmation_for(frozen: Value) -> (Value, Value) {
        let r = request("skin_reference_body_confirm",json!({"token":frozen["token"],
            "ack":{"review_sha256":frozen["review_sha256"],"before_sha256":frozen["visual"]["before"]["sha256"],"after_sha256":frozen["visual"]["after"]["sha256"]}}));
        let mut payload = json!({"kind":"skin_reference_body_confirm","ack":r["payload"]["ack"],"review":frozen});
        for key in ["token","review_sha256","reference_face_ref","target_face_ref","body_ref","amount", "candidate_state_revision","support_sha256","candidate_bank_sha256"] {
            payload[key] = frozen[key].clone();
        }
        let mut v = result(&r,payload); v["doc_state"] = document_fixture(current(true)); (r,v)
    }
    fn failure(r: &Value) -> Value {
        let mut v = result(r,Value::Null); v.as_object_mut().unwrap().remove("payload");
        v["success"] = json!(false); v["error"] = json!("Source or body ownership changed"); v
    }
    #[test]
    fn exact_photo_body_consent_and_same_owner_reference_are_required() {
        let good = preview_request(); assert!(command(&good).is_ok()); assert!(read_only(&good));
        let mut own_face = good.clone(); own_face["payload"]["reference_face_ref"] = face("selected"); assert!(command(&own_face).is_ok());
        own_face["payload"]["reference_face_ref"]["analysis_revision"] = json!(3); assert!(command(&own_face).is_err());
        for (path,bad) in [("/target/scope",json!("face")),("/target/face_ref",face("selected")),("/payload/amount",json!(0)),
            ("/payload/review/operation_id",json!("lnx.body_face_match.v1")),("/payload/review/body_ref/asset_sha256",json!(h('0'))),
            ("/payload/review/ownership_confirmed",json!(false)),("/payload/review/unoccluded",json!(false)),
            ("/payload/review/reference_unchanged",json!(false)),("/payload/review/recipe/objects/0/kind",json!("semantic")),
            ("/payload/review/recipe/objects/0/operation",json!("intersect")),("/payload/review/recipe/objects/0/enabled",json!(false)),
            ("/payload/review/recipe/objects/0/opacity",json!(0)),("/payload/review/recipe/objects/0/axes",json!([[0.0,0.0],[0.0,0.02]])),
            ("/payload/review/recipe/objects/0/points",json!([[1.01,0.5]])),("/payload/review/recipe/objects/0/name",json!(" \n")),
            ("/payload/review/recipe/objects/0/id",json!("bad:brush")),("/payload/source_review_sha256",json!("F".repeat(64)))] {
            let mut bad_request = good.clone(); *bad_request.pointer_mut(path).unwrap() = bad;
            assert!(command(&bad_request).is_err(),"{path}"); assert!(!read_only(&bad_request));
        }
        let mut bad = good; bad["payload"]["review"]["face_only_review"] = json!(true); assert!(command(&bad).is_err());
        assert!(!read_only(&confirmation_fixture().0)); assert!(!read_only(&request("skin_reference_body_clear",json!({}))));
    }
    #[test]
    fn frozen_review_retains_every_other_target_amount_and_support_exactly() {
        let (r,frozen) = review_fixture(); let good = result(&r,json!({"kind":"skin_reference_body_preview","review":frozen}));
        assert!(receipt(&good));
        for (path,bad) in [("/payload/review/body_ref/body_instance_id",json!("another-body")),
            ("/payload/review/body_review/points_sha256",json!(h('0'))),("/payload/review/source/width",json!(1024)),
            ("/payload/review/owner/document/epoch",json!("old")),("/payload/review/candidate_state_revision",json!(3)),
            ("/payload/review/source_review_sha256",json!(h('0'))),("/payload/review/before_bank_sha256",json!(h('0'))),
            ("/payload/review/candidate_current/amounts/0/amount",json!(0.8)),
            ("/payload/review/candidate_current/amounts/0/support_sha256",json!(h('0'))),
            ("/payload/review/candidate_current/target_face_refs/0",face("hidden")),
            ("/payload/review/candidate_current/reference_face_ref",face("replacement")),
            ("/payload/review/visual/before/width",json!(1023)),("/payload/review/visual/after_output_size",json!([1200,1199]))] {
            let mut bad_result = good.clone(); *bad_result.pointer_mut(path).unwrap() = bad; assert!(!receipt(&bad_result),"{path}");
        }
        let mut bad = good.clone(); bad["payload"]["review"]["candidate_current"]["target_face_refs"] = json!([face("selected")]);
        bad["payload"]["review"]["candidate_current"]["amounts"].as_array_mut().unwrap().remove(0); assert!(!receipt(&bad));
        bad = good; bad["doc_state"] = document_fixture(current(true)); assert!(!receipt(&bad));
    }
    #[test]
    fn confirm_checks_full_review_ack_exact_publication_and_unrelated_rows() {
        let (r,good) = confirmation_fixture(); assert!(receipt(&good)); assert!(matches_request(&r,&good));
        for (path,bad) in [("/payload/ack/before_sha256",json!(h('0'))),("/payload/body_ref/analysis_revision",json!(6)),
            ("/payload/review/body_review/operation_id",json!("lnx.skin_reference_match.v1")),
            ("/payload/review/visual/after/sha256",json!(h('0'))),("/payload/review/support_sha256",json!(h('0'))),
            ("/doc_state/people/binding/document_revision",json!(4)),("/doc_state/people/binding/document_epoch",json!("old")),
            ("/doc_state/people/association_revision",json!(3)),("/doc_state/people/revision",json!(5)),
            ("/doc_state/people/skin_reference_body_match/bank_sha256",json!(h('0'))),
            ("/doc_state/people/skin_reference_body_match/amounts/0/amount",json!(0.6)),
            ("/doc_state/people/skin_reference_body_match/amounts/0/support_sha256",json!(h('0')))] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
        }
        let mut changed = good.clone(); changed["payload"].as_object_mut().unwrap().remove("review"); assert!(!receipt(&changed));
        changed = good; changed["doc_state"]["people"]["skin_reference_body_match"]["target_face_refs"].as_array_mut().unwrap().reverse();
        changed["doc_state"]["people"]["skin_reference_body_match"]["amounts"].as_array_mut().unwrap().reverse(); assert!(receipt(&changed));
    }
    #[test]
    fn clear_is_body_only_and_may_preserve_an_active_face_lane_donor() {
        let r = request("skin_reference_body_clear",json!({}));
        let mut v = result(&r,json!({"kind":"skin_reference_body_clear","candidate_state_revision":4,"cleared_face_refs":[face("disabled-dormant")]}));
        v["doc_state"] = document_fixture(empty_current()); assert!(receipt(&v));
        v["doc_state"]["people"]["skin_reference_body_match"]["reference_face_ref"] = Value::Null; assert!(receipt(&v));
        v["doc_state"]["people"]["skin_reference_body_match"] = current(false); assert!(!receipt(&v));
    }
    #[test]
    fn failure_cannot_smuggle_a_publication_or_borrow_a_face_marker() {
        let r = confirmation_fixture().0; let mut good = failure(&r); assert!(receipt(&good));
        good["outcome_unknown"] = json!(true); assert!(receipt(&good));
        let mut changed = good.clone(); changed["payload"] = json!({}); assert!(!receipt(&changed));
        changed = good.clone(); changed["doc_state"] = document_fixture(current(true)); assert!(!receipt(&changed));
        changed = good.clone(); changed["frame_emitted"] = json!(true); assert!(!receipt(&changed));
        changed = good; changed["skin_reference_match_request"] = changed[MARKER].clone();
        changed.as_object_mut().unwrap().remove(MARKER); assert!(!receipt(&changed));
    }
    // The source fixture is a bounded RGB PNG, constructed only when future tests run.
    fn png_fixture() -> Value {
        use base64::{engine::general_purpose::STANDARD, Engine as _}; use sha2::{Digest,Sha256};
        fn crc(bytes: &[u8]) -> u32 {
            let mut n = u32::MAX; for byte in bytes { n ^= u32::from(*byte);
                for _ in 0..8 { n = if n & 1 == 0 { n >> 1 } else { (n >> 1) ^ 0xedb88320 }; } } !n
        }
        fn chunk(out: &mut Vec<u8>, kind: &[u8;4], data: &[u8]) {
            out.extend_from_slice(&(data.len() as u32).to_be_bytes()); let start = out.len();
            out.extend_from_slice(kind); out.extend_from_slice(data); let sum = crc(&out[start..]); out.extend_from_slice(&sum.to_be_bytes());
        }
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec(); chunk(&mut bytes,b"IHDR",&[0,0,0,1,0,0,0,1,8,2,0,0,0]);
        chunk(&mut bytes,b"IDAT",&[0x78,0x01,0x01,0x04,0x00,0xfb,0xff,0,0,0,0,0,4,0,1]); chunk(&mut bytes,b"IEND",&[]);
        json!({"mime":"image/png","width":1,"height":1,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(&bytes)})
    }
    fn catalog_fixture() -> Value {
        let r = request("skin_reference_body_catalog",json!({}));
        result(&r,json!({"kind":"skin_reference_body_catalog","version":1,"operation_id":OP,"scope":"current-photo-body-only",
            "source":{"sha256":h('a'),"width":1,"height":1},"source_proof":source_proof_fixture(),"document_id":"doc","revision":"4",
            "source_image":png_fixture(),"source_review_sha256":h('c'),"faces":[
                {"face_ref":face("donor"),"box":[0.0,0.0,0.4,1.0],"enabled":true,"available":true,"reason":null,"amount":0.0},
                {"face_ref":face("selected"),"box":[0.6,0.0,1.0,1.0],"enabled":true,"available":false,"reason":"No face donor semantics","amount":0.0}],
            "targets":[{"face_ref":face("selected"),"body_ref":body(),"points_sha256":h('b'),
                "source":{"sha256":h('a'),"width":1,"height":1,"orientation":"exif_normalized_once"},
                "association":{"person_id":"person-target","body_ref":body(),"people_association_revision":2,"confirmation_revision":1},
                "box":[0.6,0.0,1.0,1.0],"amount":0.0}],"current":empty_current(),"body_matching":true,"automatic_reference":false,
            "skin_reference_body_available":false,"skin_reference_body_reason":"Native extension unavailable"}))
    }
    #[test]
    fn catalog_separates_target_body_ownership_from_donor_skin_eligibility() {
        let good = catalog_fixture(); assert!(receipt(&good));
        for (path,bad) in [("/payload/source_image/sha256",json!(h('0'))),("/payload/source_image/base64",json!("AAAA")),
            ("/payload/targets/0/source/width",json!(2)),("/payload/targets/0/body_ref/asset_sha256",json!(h('0'))),
            ("/payload/targets/0/association/people_association_revision",json!(3)),("/payload/targets/0/association/body_ref/body_instance_id",json!("other")),
            ("/payload/targets/0/box",json!([0.0,0.0,0.5,1.0])),("/payload/faces/1/enabled",json!(false)),
            ("/payload/body_matching",json!(false)),("/payload/skin_reference_body_reason",Value::Null)] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
        }
    }
    #[test]
    fn images_and_released_reads_keep_exact_source_request_without_write_authority() {
        let pixels = png_fixture(); let r = request("skin_reference_body_image",json!({"token":"c".repeat(32),"side":"after","sha256":pixels["sha256"],"review_sha256":h('d')}));
        let mut v = result(&r,json!({"kind":"skin_reference_body_image","token":r["payload"]["token"],"side":"after",
            "sha256":pixels["sha256"],"review_sha256":h('d'),"image":pixels})); assert!(receipt(&v));
        v["payload"]["side"] = json!("before"); assert!(!receipt(&v));
        v = catalog_fixture(); v.as_object_mut().unwrap().remove("payload"); v["payload_released"] = json!(true);
        assert!(released_read(&v)); assert!(receipt(&v)); v["doc_state"] = document_fixture(empty_current()); assert!(!receipt(&v));
        v = confirmation_fixture().1; v.as_object_mut().unwrap().remove("payload"); v.as_object_mut().unwrap().remove("doc_state");
        v["payload_released"] = json!(true); assert!(!receipt(&v));
    }
    struct Kind;
    impl crate::receipt_host::ReceiptKind for Kind {
        const NAME: &'static str = "people";
        const ACTIONS: &'static [&'static str] = super::ACTIONS;
        fn valid(v: &Value, document: Option<&str>) -> bool { v["document_id"].as_str() == document && receipt(v) }
        fn decorate_failure(v: &mut Value, document: Option<&str>) { v["protocol"] = json!(1); v["document_id"] = json!(document); }
    }
    fn preview_with_images() -> (Value, Value, Vec<(Value, Value)>) {
        let (mut command,mut frozen) = review_fixture(); command["request_id"] = json!("body-preview");
        let pixels = png_fixture(); let mut compact = pixels.clone(); compact.as_object_mut().unwrap().remove("base64");
        frozen["visual"]["before_output_size"] = json!([1,1]); frozen["visual"]["after_output_size"] = json!([1,1]);
        frozen["visual"]["before"] = compact.clone(); frozen["visual"]["after"] = compact;
        let preview = result(&command,json!({"kind":"skin_reference_body_preview","review":frozen}));
        let images = ["before","after"].iter().map(|side| {
            let mut r = request("skin_reference_body_image",json!({"token":frozen["token"],"side":side,
                "sha256":pixels["sha256"],"review_sha256":frozen["review_sha256"]}));
            r["request_id"] = json!(format!("body-{side}"));
            let image = result(&r,json!({"kind":"skin_reference_body_image","token":frozen["token"],"side":side,
                "sha256":pixels["sha256"],"review_sha256":frozen["review_sha256"],"image":pixels})); (r,image)
        }).collect();
        (command,preview,images)
    }
    fn seed_confirmation(host: &mut crate::receipt_host::ReceiptHost<Kind>, epoch: [u8;16]) -> (Value, Value) {
        let (request,preview,images) = preview_with_images();
        host.begin_command(epoch,&request).unwrap(); host.receive(epoch,&preview);
        for (request,image) in images { host.begin_command(epoch,&request).unwrap(); host.receive(epoch,&image); }
        confirmation_for(preview["payload"]["review"].clone())
    }
    #[test]
    fn mailbox_reconciles_only_exact_late_reads_never_unknown_mutations() {
        let epoch = [17,38,21,7,0,0,0,0,0,0,0,0,0,0,0,1];
        let r = request("skin_reference_body_catalog",json!({}));
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        host.begin_command(epoch,&r).unwrap(); host.failed("body-fixture","Lost read transport");
        let terminal = catalog_fixture(); host.receive(epoch,&terminal); assert_eq!(host.status("body-fixture")["result"],terminal);
        let mut mutations = crate::receipt_host::ReceiptHost::<Kind>::default(); mutations.reset(epoch); mutations.ready(epoch,true);
        let (write,success) = seed_confirmation(&mut mutations,epoch);
        mutations.begin_command(epoch,&write).unwrap(); mutations.failed("body-fixture","Unknown write transport");
        let unknown = mutations.status("body-fixture")["result"].clone(); mutations.receive(epoch,&success);
        assert_eq!(mutations.status("body-fixture")["result"],unknown); assert!(mutations.guards_review(epoch,"body-fixture"));
        assert!(mutations.begin_command(epoch,&write).is_err());
    }
    #[test]
    fn captured_eight_field_echo_applies_even_to_a_claimed_safe_refusal() {
        let epoch = [17,38,21,7,0,0,0,0,0,0,0,0,0,0,0,2];
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        let r = seed_confirmation(&mut host,epoch).0;
        let binding = binding(&r).unwrap().unwrap(); assert_eq!(binding[MARKER].as_object().unwrap().len(),8);
        host.begin_command(epoch,&r).unwrap();
        let mut changed = failure(&r); changed[MARKER]["payload"]["ack"]["review_sha256"] = json!(h('0'));
        assert!(receipt(&changed)); host.receive(epoch,&changed);
        assert_eq!(host.status("body-fixture")["result"]["outcome_unknown"],true);
        assert_eq!(host.status("body-fixture")["result"][MARKER],binding[MARKER]);
    }
    #[test]
    fn native_confirm_requires_retained_preview_and_both_exact_image_receipts() {
        let epoch = [17,38,21,7,0,0,0,0,0,0,0,0,0,0,0,4];
        let (r,preview,images) = preview_with_images(); let write = confirmation_for(preview["payload"]["review"].clone()).0;
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        assert!(host.begin_command(epoch,&write).is_err());
        host.begin_command(epoch,&r).unwrap(); host.receive(epoch,&preview);
        assert!(host.begin_command(epoch,&write).is_err());
        host.begin_command(epoch,&images[0].0).unwrap(); host.receive(epoch,&images[0].1);
        assert!(host.begin_command(epoch,&write).is_err());
        host.begin_command(epoch,&images[1].0).unwrap(); host.receive(epoch,&images[1].1);
        let mut changed = write.clone(); changed["payload"]["ack"]["before_sha256"] = json!(h('0'));
        assert!(host.begin_command(epoch,&changed).is_err());
        host.begin_command(epoch,&write).unwrap();
    }
    #[test]
    fn a_shape_valid_confirmation_cannot_replace_the_captured_manual_consent() {
        let epoch = [17,38,21,7,0,0,0,0,0,0,0,0,0,0,0,5];
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        let (write,mut changed) = seed_confirmation(&mut host,epoch); host.begin_command(epoch,&write).unwrap();
        changed["payload"]["review"]["body_review"]["recipe"]["objects"][0]["points"] = json!([[0.8,0.8]]);
        // Echoed token/hash/ACK and shape alone are insufficient. The native
        // ledger captured the original parsed review before dispatch.
        assert!(receipt(&changed)); host.receive(epoch,&changed);
        assert_eq!(host.status("body-fixture")["result"]["outcome_unknown"],true);
    }
    #[test]
    fn pending_body_mutation_is_query_only_and_bare_reopen_cannot_release_it() {
        let epoch = [17,38,21,7,0,0,0,0,0,0,0,0,0,0,0,3]; let write = confirmation_fixture().0;
        crate::project_recovery_fence::issued(epoch,&write).unwrap();
        let mut read = request("skin_reference_body_catalog",json!({}));
        assert!(crate::project_recovery_fence::issued(epoch,&read).is_err()); read["request_id"] = json!("separate-read");
        crate::project_recovery_fence::issued(epoch,&read).unwrap(); assert!(crate::project_recovery_fence::proof(epoch).is_err());
        let mut clear = request("skin_reference_body_clear",json!({})); clear["request_id"] = json!("new-clear");
        assert!(crate::project_recovery_fence::issued(epoch,&clear).is_err());
        let mut refusal = failure(&write); refusal[MARKER]["document_epoch"] = json!("other");
        crate::project_recovery_fence::observed(epoch,&refusal); assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"})); assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened","open":true,"path":"/project","project_id":"project","docs":1,"dirty":false}));
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
}
