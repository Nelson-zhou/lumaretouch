// SPDX-License-Identifier: GPL-3.0-or-later
//! Strict selected-reference transport inside the existing people mailbox.
//! Shape, identity and PNG framing only; no decoding, fitting or image inference.
//! Fixtures below are AUTHORED / UNRUN, not product or photographic acceptance.
use serde_json::{json, Value};
use std::collections::BTreeSet;
use crate::original_shadow_transfer_protocol::{hex, source_proof};

pub(crate) const MARKER: &str = "skin_reference_match_request";
pub(crate) const ACTIONS: &[&str] = &["skin_reference_match_catalog", "skin_reference_match_preview",
    "skin_reference_match_image", "skin_reference_match_confirm", "skin_reference_match_clear"];
const OP: &str = "lnx.skin_reference_match.v1";
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_REVISION: u64 = 9_007_199_254_740_991;
const MAX_FACES: usize = 64;
const MAX_TARGETS: usize = MAX_FACES - 1;
const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;
const MAX_PNG_BYTES: usize = 4 * 1024 * 1024;
const MAX_BASE64_BYTES: usize = 5_592_408;

fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|key| m.contains_key(*key)))
}
fn allowed(v: &Value, required: &[&str], optional: &[&str]) -> bool {
    v.as_object().is_some_and(|m| required.iter().all(|key| m.contains_key(*key))
        && m.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str())))
}
fn identifier(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b)))
}
fn revision(v: &Value) -> bool { v.as_u64().is_some_and(|n| n <= MAX_REVISION) }
fn next_revision(v: &Value, before: &Value) -> bool {
    revision(v) && v.as_u64().zip(before.as_u64()).is_some_and(|(after, before)| before.checked_add(1) == Some(after))
}
fn decimal_revision(v: &Value, expected: &Value) -> bool {
    revision(expected) && v.as_str() == expected.as_u64().map(|n| n.to_string()).as_deref()
}
fn amount(v: &Value, active: bool) -> bool {
    v.as_f64().is_some_and(|n| n.is_finite() && n <= 1.0 && if active { n > 0.0 } else { n >= 0.0 })
}
fn face_ref(v: &Value, asset: &Value) -> bool {
    fields(v, &["asset_sha256", "face_instance_id", "analysis_revision"])
        && hex(asset, 64) && v["asset_sha256"] == *asset && identifier(&v["face_instance_id"])
        && revision(&v["analysis_revision"])
}
fn face_refs(v: &Value, asset: &Value, minimum: usize, maximum: usize) -> bool {
    let Some(rows) = v.as_array() else { return false; };
    let mut seen = BTreeSet::new();
    (minimum..=maximum).contains(&rows.len()) && rows.iter().all(|row|
        face_ref(row, asset) && seen.insert(row["face_instance_id"].as_str().unwrap()))
}
fn selection(reference: &Value, targets: &Value, asset: &Value) -> bool {
    face_ref(reference, asset) && face_refs(targets, asset, 1, MAX_TARGETS)
        && targets.as_array().unwrap().iter().all(|row| row["face_instance_id"] != reference["face_instance_id"])
}
fn ack(v: &Value) -> bool {
    fields(v, &["review_sha256", "before_sha256", "after_sha256"])
        && ["review_sha256", "before_sha256", "after_sha256"].iter().all(|key| hex(&v[*key], 64))
}
pub(crate) fn action(v: &Value) -> bool { v["action"].as_str().is_some_and(|name| ACTIONS.contains(&name)) }
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
        && v["target"]["scope"] == "all_people" && v["target"]["face_ref"].is_null()
        && hex(asset, 64) && match v["action"].as_str() {
            Some("skin_reference_match_catalog" | "skin_reference_match_clear") => fields(p, &[]),
            Some("skin_reference_match_preview") => fields(p, &["version", "reference_face_ref", "target_face_refs", "amount", "source_review_sha256", "ownership_confirmed"])
                && p["version"].as_u64() == Some(1) && p["ownership_confirmed"] == true && amount(&p["amount"], true)
                && hex(&p["source_review_sha256"], 64) && selection(&p["reference_face_ref"], &p["target_face_refs"], asset),
            Some("skin_reference_match_image") => fields(p, &["token", "side", "sha256", "review_sha256"])
                && hex(&p["token"], 32) && matches!(p["side"].as_str(), Some("before" | "after"))
                && hex(&p["sha256"], 64) && hex(&p["review_sha256"], 64),
            Some("skin_reference_match_confirm") => fields(p, &["token", "ack"]) && hex(&p["token"], 32) && ack(&p["ack"]),
            _ => false,
        };
    if valid { Ok(()) } else { Err("肤色参照匹配需要当前整张照片、明确参照与目标及冻结审核凭据".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({}); for key in REQUEST { request[*key] = v[*key].clone(); }
    Ok(Some(json!({"skin_reference_match_request":request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(), Some("skin_reference_match_catalog" | "skin_reference_match_preview" | "skin_reference_match_image"))
        && identifier(&v["request_id"]) && command(v).is_ok()
}

fn size(v: &Value) -> Option<(u64, u64)> {
    let items = v.as_array()?; if items.len() != 2 { return None; }
    let (w, h) = (items[0].as_u64()?, items[1].as_u64()?);
    (w > 0 && h > 0 && w <= u32::MAX as u64 && h <= u32::MAX as u64).then_some((w, h))
}
fn source(v: &Value, asset: &Value) -> bool {
    fields(v, &["sha256", "width", "height"]) && v["sha256"] == *asset && hex(asset, 64)
        && ["width", "height"].iter().all(|key| v[*key].as_u64().is_some_and(|n| n > 0 && n <= u32::MAX as u64))
}
fn compact(v: &Value, output: (u64, u64)) -> bool {
    let edge = output.0.max(output.1);
    let scaled = |n: u64| {
        if edge <= 1024 { return n; }
        let (q, r) = (n * 1024 / edge, n * 1024 % edge);
        (q + u64::from(r * 2 > edge || (r * 2 == edge && q % 2 == 1))).max(1)
    };
    fields(v, &["mime", "width", "height", "sha256"]) && v["mime"] == "image/png" && hex(&v["sha256"], 64)
        && v["width"].as_u64() == Some(scaled(output.0)) && v["height"].as_u64() == Some(scaled(output.1))
}
/// Hashes and checks chunk framing/CRC without decompressing pixels or loading an image model.
pub(crate) fn image(v: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    if !fields(v, &["mime", "width", "height", "sha256", "base64"]) || v["mime"] != "image/png" || !hex(&v["sha256"], 64) { return false; }
    let (Some(w), Some(h), Some(encoded)) = (v["width"].as_u64(), v["height"].as_u64(), v["base64"].as_str()) else { return false; };
    if !(1..=1024).contains(&w) || !(1..=1024).contains(&h) || encoded.is_empty() || encoded.len() > MAX_BASE64_BYTES || encoded.len() % 4 != 0 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= MAX_PNG_BYTES && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, w as u32, h as u32)
        && bytes.get(25) == Some(&2)
        && format!("{:x}", Sha256::digest(&bytes)) == v["sha256"].as_str().unwrap()
}
fn source_image(v: &Value, s: &Value) -> bool {
    let meta = json!({"mime":v["mime"], "width":v["width"], "height":v["height"], "sha256":v["sha256"]});
    image(v) && compact(&meta, (s["width"].as_u64().unwrap(), s["height"].as_u64().unwrap()))
}
fn owner(v: &Value, r: &Value) -> bool {
    fields(v, &["document", "people_scope", "state_revision", "association_revision", "graph_sha256", "source_proof"])
        && fields(&v["document"], &["document_id", "epoch", "revision"])
        && v["document"]["document_id"] == r["document_id"] && v["document"]["epoch"] == r["document_epoch"]
        && v["document"]["revision"] == r["document_revision"] && v["state_revision"] == r["state_revision"]
        && v["association_revision"] == r["association_revision"] && hex(&v["graph_sha256"], 64)
        && (v["people_scope"] == "project" || v["people_scope"] == r["document_id"])
        && source_proof(&v["source_proof"]) && v["source_proof"]["asset_sha256"] == r["target"]["target_id"]
}
fn visual(v: &Value, o: &Value, s: &Value) -> bool {
    if !fields(v, &["version", "document_id", "revision", "source_proof", "source_size", "before_output_size", "after_output_size",
        "before", "after", "before_state_sha256", "candidate_state_sha256", "before_people_sha256", "candidate_people_sha256"])
        || v["version"].as_u64() != Some(1) || v["document_id"] != o["document"]["document_id"]
        || !decimal_revision(&v["revision"], &o["document"]["revision"]) || v["source_proof"] != o["source_proof"]
        || ["before_state_sha256", "candidate_state_sha256", "before_people_sha256", "candidate_people_sha256"].iter().any(|key| !hex(&v[*key], 64)) { return false; }
    let (Some(src), Some(before), Some(after)) = (size(&v["source_size"]), size(&v["before_output_size"]), size(&v["after_output_size"])) else { return false; };
    let creative = &v["source_proof"]["creative_source"];
    s["width"].as_u64() == Some(src.0) && s["height"].as_u64() == Some(src.1)
        && (creative.is_null() || (creative["width"].as_u64() == Some(src.0) && creative["height"].as_u64() == Some(src.1)))
        && before == after && compact(&v["before"], before) && compact(&v["after"], after)
}
fn support_hashes(v: &Value, refs: &Value) -> bool {
    let (Some(map), Some(refs)) = (v.as_object(), refs.as_array()) else { return false; };
    map.len() == refs.len() && refs.iter().all(|r| r["face_instance_id"].as_str().is_some_and(|id| hex(&v[id], 64)))
}
fn review(v: &Value, r: &Value) -> bool {
    let p = &r["payload"]; let asset = &r["target"]["target_id"];
    fields(v, &["version", "token", "operation_id", "owner", "source", "reference_face_ref", "target_face_refs", "amount", "before_target_face_refs",
        "candidate_state_revision", "before_bank_sha256", "candidate_bank_sha256", "support_sha256", "source_review_sha256", "visual", "review_sha256"])
        && v["version"].as_u64() == Some(1) && v["operation_id"] == OP && hex(&v["token"], 32)
        && owner(&v["owner"], r) && source(&v["source"], asset)
        && v["reference_face_ref"] == p["reference_face_ref"] && v["target_face_refs"] == p["target_face_refs"]
        && v["amount"].as_f64() == p["amount"].as_f64() && v["source_review_sha256"] == p["source_review_sha256"]
        && face_refs(&v["before_target_face_refs"], asset, 0, MAX_TARGETS)
        && next_revision(&v["candidate_state_revision"], &r["state_revision"])
        && ["before_bank_sha256", "candidate_bank_sha256", "review_sha256"].iter().all(|key| hex(&v[*key], 64))
        && support_hashes(&v["support_sha256"], &v["target_face_refs"]) && visual(&v["visual"], &v["owner"], &v["source"])
}
fn diagnostic(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.contains('\0'))
}
fn availability(available: &Value, reason: &Value) -> bool {
    available.is_boolean() && if available == true { reason.is_null() } else { diagnostic(reason) }
}
fn face_box(v: &Value) -> bool {
    v.as_array().is_some_and(|items| items.len() == 4
        && items.iter().all(|n| n.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n)))
        && v[0].as_f64() < v[2].as_f64() && v[1].as_f64() < v[3].as_f64()
}
/// A source-wide report is independent of the currently selected face/cursor.
fn report(v: &Value, asset: &Value) -> bool {
    if !fields(v, &["version", "operation_id", "reference_face_ref", "target_face_refs", "amounts", "bank_sha256"])
        || v["version"].as_u64() != Some(1) || v["operation_id"] != OP || !hex(&v["bank_sha256"], 64)
        || !face_refs(&v["target_face_refs"], asset, 0, MAX_TARGETS) { return false; }
    let refs = v["target_face_refs"].as_array().unwrap();
    let Some(amounts) = v["amounts"].as_array() else { return false; };
    if refs.is_empty() { return v["reference_face_ref"].is_null() && amounts.is_empty(); }
    let mut seen = BTreeSet::new();
    selection(&v["reference_face_ref"], &v["target_face_refs"], asset) && amounts.len() == refs.len()
        && amounts.iter().all(|row| fields(row, &["face_ref", "amount", "support_sha256"])
            && face_ref(&row["face_ref"], asset) && refs.contains(&row["face_ref"])
            && seen.insert(row["face_ref"]["face_instance_id"].as_str().unwrap())
            && amount(&row["amount"], true) && hex(&row["support_sha256"], 64))
}
fn catalogue(v: &Value, r: &Value) -> bool {
    let asset = &r["target"]["target_id"];
    if !fields(v, &["kind", "version", "operation_id", "scope", "source", "source_proof", "document_id", "revision", "source_image",
        "source_review_sha256", "faces", "current", "body_matching", "automatic_reference", "skin_reference_match_available", "skin_reference_match_reason"])
        || v["kind"] != "skin_reference_match_catalog" || v["version"].as_u64() != Some(1) || v["operation_id"] != OP
        || v["scope"] != "current-photo-face-only" || v["document_id"] != r["document_id"]
        || !decimal_revision(&v["revision"], &r["document_revision"]) || !source(&v["source"], asset)
        || !source_proof(&v["source_proof"]) || v["source_proof"]["asset_sha256"] != *asset
        || !hex(&v["source_review_sha256"], 64) || v["body_matching"] != false || v["automatic_reference"] != false
        || !availability(&v["skin_reference_match_available"], &v["skin_reference_match_reason"])
        || !report(&v["current"], asset) { return false; }
    let creative = &v["source_proof"]["creative_source"];
    if !creative.is_null() && (creative["width"] != v["source"]["width"] || creative["height"] != v["source"]["height"]) { return false; }
    let Some(faces) = v["faces"].as_array() else { return false; };
    let mut seen = BTreeSet::new();
    if faces.len() > MAX_FACES || !faces.iter().all(|row|
        fields(row, &["face_ref", "box", "enabled", "available", "reason", "amount"])
        && face_ref(&row["face_ref"], asset) && seen.insert(row["face_ref"]["face_instance_id"].as_str().unwrap())
        && face_box(&row["box"]) && row["enabled"].is_boolean() && availability(&row["available"], &row["reason"])
        && (row["available"] != true || row["enabled"] == true) && amount(&row["amount"], false)) { return false; }
    let current = &v["current"];
    let known_enabled = |reference: &Value| faces.iter().any(|face| face["face_ref"] == *reference && face["enabled"] == true);
    (current["reference_face_ref"].is_null() || known_enabled(&current["reference_face_ref"]))
        && current["amounts"].as_array().unwrap().iter().all(|row| faces.iter().any(|face|
            face["face_ref"] == row["face_ref"] && face["enabled"] == true && face["amount"].as_f64() == row["amount"].as_f64()))
        && faces.iter().all(|face| face["enabled"] != true || face["amount"].as_f64() == Some(0.0)
            || current["target_face_refs"].as_array().unwrap().contains(&face["face_ref"]))
        && source_image(&v["source_image"], &v["source"])
}
fn document(v: &Value, r: &Value) -> bool {
    let people = &v["doc_state"]["people"]; let binding = &people["binding"]; let p = &v["payload"];
    fields(binding, &["document_id", "document_epoch", "document_revision", "asset_sha256"])
        && binding["document_id"] == r["document_id"] && binding["document_epoch"] == r["document_epoch"]
        && binding["asset_sha256"] == r["target"]["target_id"]
        && next_revision(&binding["document_revision"], &r["document_revision"])
        && next_revision(&people["revision"], &r["state_revision"])
        && people["revision"] == p["candidate_state_revision"]
        && people["association_revision"] == r["association_revision"]
        && report(&people["skin_reference_match"], &r["target"]["target_id"])
}
fn confirmation(v: &Value, r: &Value) -> bool {
    let p = &v["payload"]; let expected = &r["payload"]; let asset = &r["target"]["target_id"];
    if !fields(p, &["kind", "token", "review_sha256", "ack", "reference_face_ref", "target_face_refs", "amount",
        "candidate_state_revision", "support_sha256", "candidate_bank_sha256"])
        || p["kind"] != "skin_reference_match_confirm" || p["token"] != expected["token"] || p["ack"] != expected["ack"]
        || p["review_sha256"] != expected["ack"]["review_sha256"] || !amount(&p["amount"], true)
        || !selection(&p["reference_face_ref"], &p["target_face_refs"], asset)
        || !support_hashes(&p["support_sha256"], &p["target_face_refs"])
        || !hex(&p["candidate_bank_sha256"], 64) || !document(v, r) { return false; }
    let actual = &v["doc_state"]["people"]["skin_reference_match"];
    let targets = p["target_face_refs"].as_array().unwrap();
    actual["reference_face_ref"] == p["reference_face_ref"] && actual["bank_sha256"] == p["candidate_bank_sha256"]
        && actual["target_face_refs"].as_array().unwrap().len() == targets.len()
        && actual["target_face_refs"].as_array().unwrap().iter().all(|face| targets.contains(face))
        && actual["amounts"].as_array().unwrap().iter().all(|row| row["amount"].as_f64() == p["amount"].as_f64()
            && row["support_sha256"] == p["support_sha256"][row["face_ref"]["face_instance_id"].as_str().unwrap()])
}
fn clear(v: &Value, r: &Value) -> bool {
    let p = &v["payload"]; let actual = &v["doc_state"]["people"]["skin_reference_match"];
    fields(p, &["kind", "candidate_state_revision", "cleared_face_refs"])
        && p["kind"] == "skin_reference_match_clear" && face_refs(&p["cleared_face_refs"], &r["target"]["target_id"], 1, MAX_FACES)
        && document(v, r) && actual["reference_face_ref"].is_null()
        && actual["target_face_refs"].as_array().is_some_and(Vec::is_empty) && actual["amounts"].as_array().is_some_and(Vec::is_empty)
}
/// A released read preserves only its earlier known terminal outcome. It has no
/// image, preview, acknowledgment or fresh mutation authority to redeem.
pub(crate) fn released_read(v: &Value) -> bool {
    let r = &v[MARKER];
    fields(v, &["event", "protocol", "action", "request_id", "document_id", MARKER,
        "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && matches!(v["action"].as_str(), Some("skin_reference_match_catalog" | "skin_reference_match_preview" | "skin_reference_match_image"))
        && v["event"] == "people_result" && v["protocol"].as_u64() == Some(1) && identifier(&v["request_id"])
        && v["success"] == true && v["outcome_unknown"] == false && v["error"].is_null()
        && v["created_id"].is_null() && v["batch_id"].is_null() && v["frame_emitted"] == false && v["payload_released"] == true
        && fields(r, REQUEST) && command(r).is_ok() && r["action"] == v["action"] && r["document_id"] == v["document_id"]
}
/// Identity must be checked against ReceiptHost's immutable captured binding as
/// well. This function never grants authority based only on a claimed kind.
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
        return diagnostic(&v["error"]) && v.get("payload").is_none() && v.get("doc_state").is_none();
    }
    if v["outcome_unknown"] != false || !v["error"].is_null() { return false; }
    let p = &v["payload"];
    if matches!(v["action"].as_str(), Some("skin_reference_match_catalog" | "skin_reference_match_preview" | "skin_reference_match_image"))
        && (v.get("doc_state").is_some() || v["frame_emitted"] == true) { return false; }
    match v["action"].as_str() {
        Some("skin_reference_match_catalog") => catalogue(p, r),
        Some("skin_reference_match_preview") => fields(p, &["kind", "review"]) && p["kind"] == "skin_reference_match_preview" && review(&p["review"], r),
        Some("skin_reference_match_image") => fields(p, &["kind", "token", "side", "sha256", "review_sha256", "image"])
            && p["kind"] == "skin_reference_match_image"
            && ["token", "side", "sha256", "review_sha256"].iter().all(|key| p[*key] == r["payload"][*key])
            && p["sha256"] == p["image"]["sha256"] && image(&p["image"]),
        Some("skin_reference_match_confirm") => confirmation(v, r),
        Some("skin_reference_match_clear") => clear(v, r),
        _ => false,
    }
}
pub(crate) fn valid_result(v: &Value) -> bool { receipt(v) }

// AUTHORED / UNRUN. These fixtures specify transport refusals, not numerical,
// renderer, inference, browser-decoding or real-photograph acceptance.
#[cfg(test)]
mod tests {
    use super::*;
    fn h(character: char) -> String { character.to_string().repeat(64) }
    fn reference(id: &str) -> Value {
        json!({"asset_sha256":h('a'), "face_instance_id":id, "analysis_revision":2})
    }
    fn request(action: &str, payload: Value) -> Value {
        json!({"cmd":"people", "request_id":"skin-fixture", "action":action, "payload":payload,
            "document_id":"doc", "document_epoch":"epoch", "document_revision":4, "state_revision":3, "association_revision":2,
            "target":{"scope":"all_people", "target_id":h('a'), "face_ref":null}})
    }
    fn preview_request() -> Value {
        request("skin_reference_match_preview", json!({"version":1,"reference_face_ref":reference("donor"),
            "target_face_refs":[reference("target-z"),reference("target-a")],"amount":0.5,
            "source_review_sha256":h('b'),"ownership_confirmed":true}))
    }
    fn confirm_request() -> Value {
        request("skin_reference_match_confirm", json!({"token":"c".repeat(32),
            "ack":{"review_sha256":h('d'),"before_sha256":h('e'),"after_sha256":h('f')}}))
    }
    fn result(r: &Value, payload: Value) -> Value {
        json!({"event":"people_result","protocol":1,"request_id":r["request_id"],"action":r["action"],"document_id":r["document_id"],
            "success":true,"outcome_unknown":false,"error":null,"created_id":null,"batch_id":null,"frame_emitted":false,
            "skin_reference_match_request":binding(r).unwrap().unwrap()[MARKER],"payload":payload})
    }
    fn source_proof_fixture() -> Value {
        json!({"asset_sha256":h('a'),"original_sha256":h('a'),"creative_source":null})
    }
    fn current() -> Value {
        // Current owner reports sorted IDs; review retains the user's order.
        json!({"version":1,"operation_id":OP,"reference_face_ref":reference("donor"),
            "target_face_refs":[reference("target-a"),reference("target-z")],"bank_sha256":h('7'),
            "amounts":[{"face_ref":reference("target-a"),"amount":0.5,"support_sha256":h('1')},
                       {"face_ref":reference("target-z"),"amount":0.5,"support_sha256":h('2')}]})
    }
    fn neutral() -> Value {
        json!({"version":1,"operation_id":OP,"reference_face_ref":null,"target_face_refs":[],"amounts":[],"bank_sha256":h('7')})
    }
    fn document_fixture(report: Value) -> Value {
        json!({"people":{"binding":{"document_id":"doc","document_epoch":"epoch","document_revision":5,"asset_sha256":h('a')},
            "revision":4,"association_revision":2,"skin_reference_match":report,
            "selected_face_id":"unrelated-cursor","editing_target":{"scope":"person","target_id":"another-person","face_ref":null}}})
    }
    fn confirmation_fixture() -> Value {
        let r = confirm_request(); let mut v = result(&r, json!({"kind":"skin_reference_match_confirm","token":r["payload"]["token"],
            "review_sha256":r["payload"]["ack"]["review_sha256"],"ack":r["payload"]["ack"],"reference_face_ref":reference("donor"),
            "target_face_refs":[reference("target-z"),reference("target-a")],"amount":0.5,"candidate_state_revision":4,
            "support_sha256":{"target-a":h('1'),"target-z":h('2')},"candidate_bank_sha256":h('7')}));
        v["doc_state"] = document_fixture(current()); v
    }
    fn review_fixture() -> (Value, Value) {
        let r = preview_request(); let proof = source_proof_fixture();
        let visual = json!({"version":1,"document_id":"doc","revision":"4","source_proof":proof,"source_size":[2048,1024],
            "before_output_size":[1200,1200],"after_output_size":[1200,1200],
            "before":{"mime":"image/png","width":1024,"height":1024,"sha256":h('e')},
            "after":{"mime":"image/png","width":1024,"height":1024,"sha256":h('f')},
            "before_state_sha256":h('1'),"candidate_state_sha256":h('2'),"before_people_sha256":h('3'),"candidate_people_sha256":h('4')});
        let review = json!({"version":1,"token":"c".repeat(32),"operation_id":OP,
            "owner":{"document":{"document_id":"doc","epoch":"epoch","revision":4},"people_scope":"project",
                "state_revision":3,"association_revision":2,"graph_sha256":h('5'),"source_proof":proof},
            "source":{"sha256":h('a'),"width":2048,"height":1024},"reference_face_ref":r["payload"]["reference_face_ref"],
            "target_face_refs":r["payload"]["target_face_refs"],"amount":0.5,"before_target_face_refs":[],"candidate_state_revision":4,
            "before_bank_sha256":h('6'),"candidate_bank_sha256":h('7'),"support_sha256":{"target-a":h('1'),"target-z":h('2')},
            "source_review_sha256":h('b'),"visual":visual,"review_sha256":h('d')});
        (r, review)
    }
    #[test]
    fn exact_current_photo_nonzero_explicit_selection_only() {
        let good = preview_request(); assert!(command(&good).is_ok()); assert!(read_only(&good));
        for (path, bad) in [("/target/scope",json!("face")),("/target/face_ref",reference("target-z")),
            ("/target/target_id",json!(h('c'))),("/payload/version",json!(2)),("/payload/ownership_confirmed",json!(false)),
            ("/payload/amount",json!(0)),("/payload/amount",json!(-0.01)),("/payload/amount",json!(1.01)),("/payload/amount",json!(true)),
            ("/payload/reference_face_ref/face_instance_id",json!("target-z")),("/payload/target_face_refs/1",reference("target-z")),
            ("/payload/target_face_refs/0/asset_sha256",json!(h('b'))),("/payload/target_face_refs/0/analysis_revision",json!(-1)),
            ("/payload/target_face_refs",json!([])),("/payload/source_review_sha256",json!("A".repeat(64)))] {
            let mut bad_request = good.clone(); *bad_request.pointer_mut(path).unwrap() = bad;
            assert!(command(&bad_request).is_err(), "{path}"); assert!(!read_only(&bad_request));
        }
        let mut extra = good.clone(); extra["payload"]["body_ref"] = json!({}); assert!(command(&extra).is_err());
        extra = good.clone(); extra["selected_face_id"] = json!("donor"); assert!(command(&extra).is_err());
        extra = good; extra["payload"]["target_face_refs"] = json!((0..MAX_FACES).map(|n| reference(&format!("target-{n}"))).collect::<Vec<_>>());
        assert!(command(&extra).is_err());
    }
    #[test]
    fn captured_binding_is_exact_and_cannot_become_a_write_read_guard() {
        let mut c = preview_request(); let frozen = binding(&c).unwrap().unwrap();
        c["payload"]["target_face_refs"][0] = reference("replacement");
        assert_ne!(frozen[MARKER]["payload"], c["payload"]);
        assert_eq!(frozen[MARKER].as_object().unwrap().len(), REQUEST.len());
        assert!(!read_only(&confirm_request()));
        assert!(!read_only(&request("skin_reference_match_clear", json!({}))));
        c["host_epoch"] = json!("not-an-epoch"); assert!(command(&c).is_err()); assert!(!read_only(&c));
        let mut no_command = preview_request(); no_command.as_object_mut().unwrap().remove("cmd"); assert!(!read_only(&no_command));
    }
    #[test]
    fn review_is_complete_source_and_candidate_bound_not_a_claimed_kind() {
        let (r, review) = review_fixture(); let good = result(&r, json!({"kind":"skin_reference_match_preview","review":review}));
        assert!(receipt(&good));
        for (path, bad) in [("/payload/review/operation_id",json!("lnx.body_face_match.v1")),
            ("/payload/review/owner/document/epoch",json!("old-epoch")),("/payload/review/owner/state_revision",json!(2)),
            ("/payload/review/source/sha256",json!(h('c'))),("/payload/review/source/width",json!(1024)),
            ("/payload/review/target_face_refs/0",reference("not-selected")),("/payload/review/amount",json!(0.6)),
            ("/payload/review/candidate_state_revision",json!(3)),("/payload/review/source_review_sha256",json!(h('c'))),
            ("/payload/review/visual/revision",json!(4)),("/payload/review/visual/before/height",json!(512)),
            ("/payload/review/visual/after_output_size",json!([2048,1024])),("/payload/review/visual/source_proof/asset_sha256",json!(h('b'))),
            ("/payload/review/support_sha256/target-a",Value::Null)] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed), "{path}");
        }
        let mut changed = good.clone(); changed["payload"]["review"]["support_sha256"]["hidden-target"] = json!(h('9')); assert!(!receipt(&changed));
        changed = good.clone(); changed["doc_state"] = document_fixture(current()); assert!(!receipt(&changed));
        changed = good; changed["payload"] = json!({"kind":"skin_reference_match_preview"}); assert!(!receipt(&changed));
    }
    #[test]
    fn confirm_proves_entire_selection_support_bank_and_exact_publication() {
        let good = confirmation_fixture(); assert!(receipt(&good));
        for (path, bad) in [("/doc_state/people/binding/asset_sha256",json!(h('b'))),("/doc_state/people/binding/document_id",json!("old-photo")),
            ("/doc_state/people/binding/document_revision",json!(4)),("/doc_state/people/binding/document_revision",json!(6)),
            ("/doc_state/people/revision",json!(5)),("/doc_state/people/association_revision",json!(3)),
            ("/doc_state/people/skin_reference_match/reference_face_ref",reference("another-donor")),
            ("/doc_state/people/skin_reference_match/amounts/0/amount",json!(0.75)),
            ("/doc_state/people/skin_reference_match/amounts/0/support_sha256",json!(h('9'))),
            ("/doc_state/people/skin_reference_match/bank_sha256",json!(h('8'))),
            ("/doc_state/people/skin_reference_match/target_face_refs/0",reference("extra-target")),
            ("/payload/ack/before_sha256",json!(h('9'))),("/payload/review_sha256",json!(h('9'))),
            ("/payload/target_face_refs/0",reference("donor"))] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed), "{path}");
        }
        let mut changed = good.clone(); changed["doc_state"]["people"]["skin_reference_match"]["amounts"].as_array_mut().unwrap().pop();
        assert!(!receipt(&changed));
        changed = good; changed["doc_state"]["people"]["skin_reference_match"]["target_face_refs"].as_array_mut().unwrap().reverse();
        // Canonical report ordering and review ordering are not mutation authority.
        assert!(receipt(&changed));
    }
    #[test]
    fn clear_must_prove_no_remaining_active_faces_and_not_depend_on_cursor() {
        let r = request("skin_reference_match_clear", json!({}));
        let mut good = result(&r, json!({"kind":"skin_reference_match_clear","candidate_state_revision":4,"cleared_face_refs":[reference("dormant-target")]}));
        good["doc_state"] = document_fixture(neutral()); assert!(receipt(&good));
        let mut bad = good.clone(); bad["doc_state"]["people"]["skin_reference_match"] = current(); assert!(!receipt(&bad));
        bad = good.clone(); bad["payload"]["cleared_face_refs"] = json!([]); assert!(!receipt(&bad));
        bad = good; bad["doc_state"]["people"]["binding"]["document_revision"] = json!(4); assert!(!receipt(&bad));
    }
    #[test]
    fn failure_needs_captured_request_and_cannot_carry_stale_success_proofs() {
        let r = confirm_request(); let mut good = result(&r, Value::Null);
        good.as_object_mut().unwrap().remove("payload"); good["success"] = json!(false); good["error"] = json!("Reviewed source changed");
        assert!(receipt(&good)); good["outcome_unknown"] = json!(true); assert!(receipt(&good));
        let mut bad = good.clone(); bad.as_object_mut().unwrap().remove(MARKER); assert!(!receipt(&bad));
        bad = good.clone(); bad["doc_state"] = document_fixture(current()); assert!(!receipt(&bad));
        bad = good.clone(); bad["payload"] = json!({"kind":"skin_reference_match_confirm"}); assert!(!receipt(&bad));
        bad = good; bad[MARKER]["document_id"] = json!("old-photo"); assert!(!receipt(&bad));
    }
    // Exact uncompressed 1x1 RGB PNG fixture. Construction only, never invoked
    // during this source-only work; WebView decode remains a separate gate.
    fn png_fixture() -> Value {
        use base64::{engine::general_purpose::STANDARD, Engine as _};
        use sha2::{Digest, Sha256};
        fn crc(bytes: &[u8]) -> u32 {
            let mut value = u32::MAX;
            for byte in bytes { value ^= u32::from(*byte); for _ in 0..8 { value = if value & 1 == 0 { value >> 1 } else { (value >> 1) ^ 0xedb88320 }; } }
            !value
        }
        fn chunk(output: &mut Vec<u8>, kind: &[u8;4], data: &[u8]) {
            output.extend_from_slice(&(data.len() as u32).to_be_bytes()); let start = output.len();
            output.extend_from_slice(kind); output.extend_from_slice(data); let sum = crc(&output[start..]); output.extend_from_slice(&sum.to_be_bytes());
        }
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
        chunk(&mut bytes, b"IHDR", &[0,0,0,1,0,0,0,1,8,2,0,0,0]);
        chunk(&mut bytes, b"IDAT", &[0x78,0x01,0x01,0x04,0x00,0xfb,0xff,0,0,0,0,0,4,0,1]);
        chunk(&mut bytes, b"IEND", &[]);
        json!({"mime":"image/png","width":1,"height":1,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(&bytes)})
    }
    fn catalog_fixture() -> Value {
        let r = request("skin_reference_match_catalog", json!({}));
        result(&r, json!({"kind":"skin_reference_match_catalog","version":1,"operation_id":OP,"scope":"current-photo-face-only",
            "source":{"sha256":h('a'),"width":1,"height":1},"source_proof":source_proof_fixture(),"document_id":"doc","revision":"4",
            "source_image":png_fixture(),"source_review_sha256":h('b'),"faces":[
                {"face_ref":reference("donor"),"box":[0.0,0.0,0.4,1.0],"enabled":true,"available":true,"reason":null,"amount":0.0},
                {"face_ref":reference("target-a"),"box":[0.6,0.0,1.0,1.0],"enabled":true,"available":false,"reason":"No retained evidence","amount":0.0}],
            "current":neutral(),"body_matching":false,"automatic_reference":false,"skin_reference_match_available":false,"skin_reference_match_reason":"Native extension unavailable"}))
    }
    #[test]
    fn catalog_requires_actual_bounded_png_and_same_source_face_inventory() {
        let good = catalog_fixture(); assert!(receipt(&good));
        for (path,bad) in [("/payload/source_image/sha256",json!(h('0'))),("/payload/source_image/width",json!(2)),
            ("/payload/source_image/base64",json!("AAAA")),("/payload/source/sha256",json!(h('c'))),
            ("/payload/revision",json!("04")),("/payload/faces/0/box",json!([0.4,0.0,0.2,1.0])),
            ("/payload/faces/1/face_ref",reference("donor")),("/payload/faces/0/available",json!(false)),
            ("/payload/body_matching",json!(true)),("/payload/automatic_reference",json!(true)),
            ("/payload/skin_reference_match_reason",Value::Null)] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
        }
        let mut changed = good; changed["payload"]["source_image"]["width"] = json!(1025); assert!(!receipt(&changed));
    }
    #[test]
    fn image_receipt_binds_bytes_token_side_and_review_not_any_old_photo() {
        let pixels = png_fixture(); let r = request("skin_reference_match_image", json!({"token":"c".repeat(32),"side":"after","sha256":pixels["sha256"],"review_sha256":h('d')}));
        let good = result(&r, json!({"kind":"skin_reference_match_image","token":r["payload"]["token"],"side":"after",
            "sha256":pixels["sha256"],"review_sha256":h('d'),"image":pixels}));
        assert!(receipt(&good));
        for (path,bad) in [("/payload/token",json!("e".repeat(32))),("/payload/side",json!("before")),
            ("/payload/review_sha256",json!(h('e'))),("/payload/image/sha256",json!(h('e'))),("/payload/image/base64",json!("AAAA"))] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
        }
        let mut changed = good; changed["payload"]["image"]["old_photo"] = json!(true); assert!(!receipt(&changed));
    }
    #[test]
    fn released_read_is_a_terminal_tombstone_not_an_image_or_mutation_ack() {
        let mut good = catalog_fixture(); good.as_object_mut().unwrap().remove("payload"); good["payload_released"] = json!(true);
        assert!(released_read(&good)); assert!(receipt(&good));
        for (path,bad) in [("/outcome_unknown",json!(true)),("/success",json!(false)),("/payload_released",json!(false)),("/frame_emitted",json!(true))] {
            let mut changed = good.clone(); *changed.pointer_mut(path).unwrap() = bad; assert!(!receipt(&changed),"{path}");
        }
        let mut changed = good.clone(); changed["payload"] = json!({}); assert!(!receipt(&changed));
        changed = good; changed["doc_state"] = document_fixture(current()); assert!(!receipt(&changed));
        changed = confirmation_fixture(); changed.as_object_mut().unwrap().remove("payload"); changed.as_object_mut().unwrap().remove("doc_state");
        changed["payload_released"] = json!(true); assert!(!released_read(&changed)); assert!(!receipt(&changed));
    }
    struct Kind;
    impl crate::receipt_host::ReceiptKind for Kind {
        const NAME: &'static str = "people";
        const ACTIONS: &'static [&'static str] = super::ACTIONS;
        fn valid(v: &Value, document: Option<&str>) -> bool {
            v["document_id"].as_str() == document && receipt(v)
        }
        fn decorate_failure(v: &mut Value, document: Option<&str>) {
            v["protocol"] = json!(1); v["document_id"] = json!(document);
        }
    }
    #[test]
    fn immutable_mailbox_binding_rejects_changed_echo_even_on_proven_refusal() {
        let epoch = [184;16]; let r = confirm_request();
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        host.begin_command(epoch,&r).unwrap();
        let mut bad = confirmation_fixture(); bad["success"] = json!(false); bad["error"] = json!("Claimed refusal");
        bad.as_object_mut().unwrap().remove("payload"); bad.as_object_mut().unwrap().remove("doc_state");
        bad[MARKER]["payload"]["ack"]["review_sha256"] = json!(h('0'));
        // Local shape remains valid. The existing mailbox owns exact capture.
        assert!(receipt(&bad)); host.receive(epoch,&bad);
        let retained = host.status("skin-fixture")["result"].clone();
        assert_eq!(retained["outcome_unknown"],true);
        assert_eq!(retained[MARKER],binding(&r).unwrap().unwrap()[MARKER]);
        assert!(host.guards_review(epoch,"skin-fixture"));
    }
    #[test]
    fn mailbox_rejects_an_old_document_success_and_keeps_mutation_unknown() {
        let epoch = [185;16]; let r = confirm_request();
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        host.begin_command(epoch,&r).unwrap();
        let mut bad = confirmation_fixture(); bad["doc_state"]["people"]["binding"]["document_epoch"] = json!("old-epoch");
        host.receive(epoch,&bad);
        assert_eq!(host.status("skin-fixture")["result"]["outcome_unknown"],true);
        assert!(host.guards_review(epoch,"skin-fixture"));
    }
    #[test]
    fn lost_read_can_settle_but_unknown_confirm_never_reopens() {
        let epoch = [186;16]; let r = request("skin_reference_match_catalog",json!({}));
        let mut host = crate::receipt_host::ReceiptHost::<Kind>::default(); host.reset(epoch); host.ready(epoch,true);
        host.begin_command(epoch,&r).unwrap(); host.failed("skin-fixture","Read transport unavailable");
        assert_eq!(host.status("skin-fixture")["result"]["outcome_unknown"],true);
        let terminal = catalog_fixture(); host.receive(epoch,&terminal);
        assert_eq!(host.status("skin-fixture")["result"],terminal);
        let mut mutation_host = crate::receipt_host::ReceiptHost::<Kind>::default(); mutation_host.reset(epoch); mutation_host.ready(epoch,true);
        mutation_host.begin_command(epoch,&confirm_request()).unwrap(); mutation_host.failed("skin-fixture","Mutation transport unavailable");
        let unknown = mutation_host.status("skin-fixture")["result"].clone();
        mutation_host.receive(epoch,&confirmation_fixture());
        assert_eq!(mutation_host.status("skin-fixture")["result"],unknown);
        assert!(mutation_host.guards_review(epoch,"skin-fixture"));
    }
    #[test]
    fn read_guard_does_not_settle_or_replace_an_existing_mutation_fence() {
        let epoch = [187;16]; let write = confirm_request();
        crate::project_recovery_fence::issued(epoch,&write).unwrap();
        let read = request("skin_reference_match_catalog",json!({}));
        assert!(crate::project_recovery_fence::issued(epoch,&read).is_err());
        crate::project_recovery_fence::observed(epoch,&catalog_fixture());
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch,&json!({"event":"project_opened"}));
        crate::project_recovery_fence::issued(epoch,&read).unwrap();
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
}
