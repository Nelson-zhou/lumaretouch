// SPDX-License-Identifier: GPL-3.0-or-later
//! Existing-eye-makeup transport admission through the existing people receipt owner.
//! This validates bounded source/consent echoes, not cosmetic segmentation, inferred visibility or render quality.
//! The engine alone owns source, landmark, support and numeric solver authority.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::hex;

const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST_FIELDS: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_REVISION: u64 = 9_007_199_254_740_991;
const MAX_PIXELS: u64 = 4_000_000;
const CONTROLS: &[&str] = &["amount", "saturation", "brightness", "structure"];
const SIDES: &[&str] = &["left", "right"];
const OPERATION: &str = "lnx.eye_makeup_enhance.v1";

fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|key| map.contains_key(*key)))
}
fn identifier(value: &Value) -> bool {
    value.as_str().is_some_and(|s| (1..=128).contains(&s.len())
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b)))
}
fn number(value: &Value, low: f64, high: f64) -> bool {
    value.as_f64().is_some_and(|n| n.is_finite() && (low..=high).contains(&n))
}
fn integer(value: &Value, low: u64, high: u64) -> bool {
    value.as_u64().is_some_and(|n| (low..=high).contains(&n))
}
fn source(value: &Value) -> bool {
    fields(value, &["sha256", "width", "height"]) && hex(&value["sha256"], 64)
        && ["width", "height"].iter().all(|key| integer(&value[*key], 2, 1_000_000))
}
pub(super) fn recipe(value: &Value) -> bool {
    fields(value, &["version", "amount", "saturation", "brightness", "structure"])
        && value["version"].as_u64() == Some(1) && CONTROLS.iter().all(|key| {
            let row = &value[*key];
            fields(row, &["linked", "left", "right"]) && row["linked"].is_boolean()
                && SIDES.iter().all(|side| number(&row[*side], -1.0, 1.0))
                && (row["linked"] != true || row["left"].as_f64() == row["right"].as_f64())
        })
}
fn cross(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> f64 {
    (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
}
fn on_segment(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> bool {
    cross(a,b,c).abs() <= 1e-12 && (0..2).all(|axis|
        c[axis] >= a[axis].min(b[axis])-1e-12 && c[axis] <= a[axis].max(b[axis])+1e-12)
}
/// Match the support producer's simple, non-touching source-normalized polygon.
/// Geometry validates authored consent, not cosmetic detection or visibility.
pub(super) fn polygon(value: &Value) -> bool {
    let Some(raw) = value.as_array() else { return false; };
    if !(3..=96).contains(&raw.len()) || !raw.iter().all(|point| point.as_array()
        .is_some_and(|pair| pair.len() == 2 && pair.iter().all(|n| number(n, 0.0, 1.0)))) { return false; }
    let points: Vec<[f64; 2]> = raw.iter().map(|p| [p[0].as_f64().unwrap(),p[1].as_f64().unwrap()]).collect();
    let count = points.len();
    let mut area = 0.0;
    for i in 0..count {
        if points[..i].contains(&points[i]) { return false; }
        let (a,b) = (points[i],points[(i+1)%count]);
        area += a[0]*b[1]-b[0]*a[1];
        for j in (i+1)..count {
            if j == i+1 || (i == 0 && j == count-1) { continue; }
            let (c,d) = (points[j],points[(j+1)%count]);
            if (cross(a,b,c)*cross(a,b,d) < 0.0 && cross(c,d,a)*cross(c,d,b) < 0.0)
                || on_segment(a,b,c) || on_segment(a,b,d) || on_segment(c,d,a) || on_segment(c,d,b) { return false; }
        }
    }
    area.abs() >= 1e-10
}
pub(super) fn eyes(value: &Value) -> bool {
    let Some(map) = value.as_object() else { return false; };
    !map.is_empty() && map.keys().all(|key| SIDES.contains(&key.as_str())) && map.values().all(|eye| {
        if !fields(eye, &["makeup", "exclusions", "reference_a", "reference_b", "reference_confirmed",
            "visible_makeup", "unoccluded", "ownership_confirmed", "globe_lashes_brows_excluded"])
            || ["visible_makeup", "unoccluded", "ownership_confirmed", "globe_lashes_brows_excluded"].iter().any(|key| eye[*key] != true)
            || !eye["reference_confirmed"].is_boolean() || !polygon(&eye["makeup"])
            || !eye["exclusions"].as_array().is_some_and(|rows| rows.len() <= 12 && rows.iter().all(polygon)) { return false; }
        if eye["reference_a"].is_null() || eye["reference_b"].is_null() {
            eye["reference_a"].is_null() && eye["reference_b"].is_null() && eye["reference_confirmed"] == false
        } else {
            polygon(&eye["reference_a"]) && polygon(&eye["reference_b"]) && eye["reference_confirmed"] == true
        }
    })
}
pub(super) fn reference(value: &Value, target: &Value) -> bool {
    fields(value, &["source", "face_ref", "landmark_digest", "preview_sha256", "reference_request_id"])
        && source(&value["source"]) && value["face_ref"] == target["face_ref"]
        && value["source"]["sha256"] == target["face_ref"]["asset_sha256"]
        && hex(&value["landmark_digest"], 64) && hex(&value["preview_sha256"], 64)
        && identifier(&value["reference_request_id"])
}
pub(crate) fn action(value: &Value) -> bool {
    matches!(value["action"].as_str(), Some("eye_makeup_enhance_reference" | "eye_makeup_enhance_review"))
}
pub(crate) fn command(value: &Value) -> Result<(), String> {
    if !action(value) { return Ok(()); }
    let envelope = value.as_object().is_some_and(|map| REQUEST_FIELDS.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| REQUEST_FIELDS.contains(&key.as_str()) || ["cmd", "request_id", "host_epoch"].contains(&key.as_str())))
        && value.get("request_id").map_or(true, identifier)
        && value.get("cmd").map_or(true, |name| name == "people" && identifier(&value["request_id"]))
        && value.get("host_epoch").map_or(true, |epoch| value["cmd"] == "people" && hex(epoch, 32));
    let mut context = json!({});
    for key in CONTEXT { context[*key] = value[*key].clone(); }
    let valid = envelope && value.to_string().len() <= 256 * 1024
        && super::valid_context(&context) && value["target"]["scope"] == "face"
        && match value["action"].as_str() {
            Some("eye_makeup_enhance_reference") => fields(&value["payload"], &[]),
            Some("eye_makeup_enhance_review") => fields(&value["payload"], &["eyes", "reference_proof"])
                && reference(&value["payload"]["reference_proof"], &value["target"])
                && eyes(&value["payload"]["eyes"]),
            _ => false,
        };
    if valid { Ok(()) } else { Err("已有眼妆审核需要当前单脸、精确源图凭据及各眼独立可见妆区和参考确认".into()) }
}
pub(crate) fn binding(value: &Value) -> Result<Option<Value>, String> {
    if value["cmd"] != "people" || !action(value) { return Ok(None); }
    command(value)?;
    let mut request = json!({});
    for key in REQUEST_FIELDS { request[*key] = value[*key].clone(); }
    Ok(Some(json!({"eye_makeup_enhance_request": request})))
}
/// Read classification is captured from the original exact command. No later
/// event label can turn a pending review mutation into a disposable source read.
pub(crate) fn read_only(value: &Value) -> bool {
    value["cmd"] == "people" && value["action"] == "eye_makeup_enhance_reference"
        && identifier(&value["request_id"]) && command(value).is_ok()
}

/// Exact eye-crop producer schema, canonical RGB8 PNG framing/CRC and digest.
/// Unlike full-frame sculpt previews this crop has no decoded_width/orientation.
/// Bounds allow the producer's half-decoded-pixel border in source coordinates;
/// decoded grid/crop provenance and actual eye measurement remain engine-owned.
fn source_preview(value: &Value, proof: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    if !fields(value, &["mime", "base64", "sha256", "source", "width", "height", "view_box", "mapping", "minimum_eye_width"])
        || value["mime"] != "image/png" || value["sha256"] != proof["preview_sha256"]
        || !source(&value["source"]) || value["source"] != proof["source"]
        || value["mapping"] != "source_pixel_centre_periocular_crop"
        || !["width", "height"].iter().all(|key| integer(&value[*key], 2, 1280))
        || !number(&value["minimum_eye_width"], 40.0, 1280.0 * 2.0_f64.sqrt()) { return false; }
    let Some(bounds) = value["view_box"].as_array() else { return false; };
    if bounds.len() != 4 || !bounds.iter().all(|n| n.as_f64().is_some_and(f64::is_finite)) { return false; }
    for (axis, key) in ["width", "height"].iter().enumerate() {
        let extent = value["source"][*key].as_f64().unwrap();
        // Whole-source proxies are downward ALIGN=8; otherwise they are original.
        let maximum_scale = if extent >= 8.0 { ((extent-1.0)/7.0).max(1.0) } else { 1.0 };
        let start = bounds[axis].as_f64().unwrap();
        let length = bounds[axis+2].as_f64().unwrap();
        if length <= 0.0 || start < -0.5*maximum_scale-1e-7
            || start+length > extent-1.0+0.5*maximum_scale+1e-7 { return false; }
    }
    let Some(encoded) = value["base64"].as_str() else { return false; };
    if encoded.is_empty() || encoded.len() > 6_990_508 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= 5_242_880 && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, value["width"].as_u64().unwrap() as u32, value["height"].as_u64().unwrap() as u32)
        && bytes.get(25) == Some(&2)
        && format!("{:x}", Sha256::digest(&bytes)) == proof["preview_sha256"].as_str().unwrap_or("")
}
fn next_revision(actual: &Value, before: &Value, changed: bool) -> bool {
    actual.as_u64().zip(before.as_u64()).is_some_and(|(after, before)| after <= MAX_REVISION
        && if changed { before.checked_add(1) == Some(after) } else { before == after })
}
fn diagnostic(value: &Value) -> bool {
    value.is_null() || value.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 4096 && !s.contains('\0'))
}
fn dimensions(value: &Value) -> bool {
    value.as_array().is_some_and(|items| items.len() == 2 && items.iter().all(|n| integer(n, 1, 1_000_000)))
}
fn observation(value: &Value, report: &Value) -> bool {
    fields(value, &["contract", "source_sha256", "semantic_model_sha256", "producer_width", "producer_height"])
        && value["contract"] == "mediapipe-face-skin-edit-weight-v1"
        && value["source_sha256"] == report["source"]["sha256"] && hex(&value["semantic_model_sha256"], 64)
        && integer(&value["producer_width"], 1, 1_000_000) && integer(&value["producer_height"], 1, 1_000_000)
}
/// Bounded producer diagnostics, never proof of automatic cosmetic visibility,
/// recovered hidden skin, native execution or photographic quality acceptance.
fn facts(value: &Value, report: &Value) -> bool {
    if fields(value, &[]) { return true; }
    if !fields(value, &["recipe", "review_sha256", "face_ref", "sides", "landmark_digest", "face_skin_observation",
        "changed_pixels", "native_solver", "source_dimensions", "render_dimensions", "protected_face_boxes", "limitations"])
        || value["recipe"] != report["recipe"] || value["face_ref"] != report["face_ref"]
        || value["landmark_digest"] != report["landmark_digest"] || !hex(&value["review_sha256"], 64)
        || value["review_sha256"] != report["support_sha256"] || !observation(&value["face_skin_observation"], report)
        || !dimensions(&value["source_dimensions"]) || !dimensions(&value["render_dimensions"])
        || value["source_dimensions"][0] != report["source"]["width"] || value["source_dimensions"][1] != report["source"]["height"]
        || !integer(&value["changed_pixels"], 0, 2*MAX_PIXELS) || !integer(&value["protected_face_boxes"], 0, 4096)
        || value["native_solver"] != "rust-eye-makeup-enhance-v1"
        || value["limitations"] != json!(["user-reviewed-visible-makeup-not-cosmetic-segmentation",
            "paired-nearby-skin-reference-not-known-underlying-skin", "bounded-appearance-fading-not-makeup-removal",
            "no-pigment-pattern-generation-or-hidden-anatomy", "authored-unrun-no-photo-quality-acceptance"]) { return false; }
    let Some(sides) = value["sides"].as_object() else { return false; };
    if sides.is_empty() || sides.keys().any(|key| !SIDES.contains(&key.as_str())) { return false; }
    let mut changed = 0u64;
    for side in SIDES {
        let active = CONTROLS.iter().any(|key| report["recipe"][*key][*side].as_f64().is_some_and(|n| n != 0.0));
        if sides.contains_key(*side) != active { return false; }
        let Some(row) = sides.get(*side) else { continue; };
        if !fields(row, &["reviewed_makeup_pixels", "permitted_makeup_pixels", "reference_pixels", "measured_eye_width", "radius", "controls", "changed_pixels", "reason"])
            || !integer(&row["reviewed_makeup_pixels"], 32, MAX_PIXELS) || !integer(&row["permitted_makeup_pixels"], 32, MAX_PIXELS)
            || !integer(&row["changed_pixels"], 0, MAX_PIXELS) || !number(&row["measured_eye_width"], 32.0, 1_500_000.0)
            || !integer(&row["radius"], 1, 64) || !fields(&row["controls"], CONTROLS)
            || !CONTROLS.iter().all(|key| number(&row["controls"][*key], -1.0, 1.0)
                && row["controls"][*key].as_f64() == report["recipe"][*key][*side].as_f64())
            || !row["reference_pixels"].as_array().is_some_and(|items| items.len() == 2 && items.iter().all(|n| integer(n, 0, MAX_PIXELS))) { return false; }
        let raw = row["reviewed_makeup_pixels"].as_u64().unwrap();
        let permitted = row["permitted_makeup_pixels"].as_u64().unwrap();
        if permitted > raw || permitted*10 < raw*7 { return false; }
        let needs_reference = row["controls"]["amount"].as_f64().unwrap() != 0.0;
        if !row["reference_pixels"].as_array().unwrap().iter().all(|n|
            if needs_reference { n.as_u64().unwrap() >= 16 } else { n.as_u64() == Some(0) }) { return false; }
        let pixels = row["changed_pixels"].as_u64().unwrap();
        if (pixels == 0 && row["reason"] != "no_measurable_change") || (pixels != 0 && !row["reason"].is_null()) { return false; }
        changed += pixels;
    }
    value["changed_pixels"].as_u64() == Some(changed)
}
fn report(value: &Value, payload: &Value, request: &Value, changed: bool) -> bool {
    let proof = &payload["reference_proof"];
    if !fields(value, &["recipe", "facts", "source", "face_ref", "landmark_digest", "reviewed", "source_preview", "reference_proof",
        "support_sha256", "sides", "native_available", "support_available", "support_reason", "suspended"])
        || !recipe(&value["recipe"]) || !facts(&value["facts"], value) || value["source"] != proof["source"]
        || value["face_ref"] != proof["face_ref"] || value["landmark_digest"] != proof["landmark_digest"]
        || !value["reviewed"].is_boolean() || !value["native_available"].is_boolean() || !value["support_available"].is_boolean()
        || !diagnostic(&value["support_reason"]) || !diagnostic(&value["suspended"])
        || !(value["support_sha256"].is_null() || hex(&value["support_sha256"], 64))
        || (value["reviewed"] == true) != !value["support_sha256"].is_null() { return false; }
    let Some(sides) = value["sides"].as_object() else { return false; };
    if sides.keys().any(|key| !SIDES.contains(&key.as_str())) || !sides.values().all(|side|
        fields(side, &["reviewed", "reference_reviewed"]) && side["reviewed"] == true && side["reference_reviewed"].is_boolean())
        || (value["reviewed"] != true && !sides.is_empty())
        || (value["support_available"] == true && (value["reviewed"] != true || sides.is_empty())) { return false; }
    if changed {
        value["reviewed"] == true && value["support_sha256"] == payload["support_sha256"]
            && value["reference_proof"].is_null() && value["source_preview"].is_null()
            // The producer omits side availability if live analysis is missing.
            // It never invents automatic review to fill an unavailable side.
            && (value["support_available"] != true || request["payload"]["eyes"].as_object().is_some_and(|eyes|
                eyes.iter().all(|(side, eye)| value["sides"][side]["reviewed"] == true
                    && value["sides"][side]["reference_reviewed"] == eye["reference_confirmed"])))
    } else {
        value["reference_proof"] == *proof && source_preview(&value["source_preview"], proof)
    }
}
fn document(value: &Value, request: &Value, proof: &Value) -> bool {
    let people = &value["doc_state"]["people"];
    let binding = &people["binding"];
    let changed = value["action"] == "eye_makeup_enhance_review";
    binding["document_id"] == request["document_id"] && binding["document_epoch"] == request["document_epoch"]
        && binding["asset_sha256"] == proof["source"]["sha256"]
        && next_revision(&binding["document_revision"], &request["document_revision"], changed)
        && next_revision(&people["revision"], &request["state_revision"], changed)
        && people["association_revision"] == request["association_revision"]
        && people["selected_face_id"] == request["target"]["target_id"] && people["editing_target"] == request["target"]
        && people["resolved"]["face_ref"] == proof["face_ref"]
        && people["resolved"]["state_revision"] == people["revision"]
        && people["resolved"]["association_revision"] == people["association_revision"]
        && CONTROLS.iter().all(|key| {
            let linked = format!("/{key}/linked");
            let operation = &people["resolved"]["operations"][OPERATION];
            operation[linked.as_str()]["value"] == people["eye_makeup_enhance"]["recipe"][*key]["linked"]
                && SIDES.iter().all(|side| {
                    let path = format!("/{key}/{side}");
                    operation[path.as_str()]["value"].as_f64()
                        == people["eye_makeup_enhance"]["recipe"][*key][*side].as_f64()
                })
        })
        && report(&people["eye_makeup_enhance"], &value["payload"], request, changed)
}
/// A released source read preserves its known outcome, but carries no image,
/// document state or reusable reference authority. It can never release a write.
pub(crate) fn released_reference(value: &Value) -> bool {
    let request = &value["eye_makeup_enhance_request"];
    fields(value, &["event", "protocol", "action", "request_id", "document_id", "eye_makeup_enhance_request",
        "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && value["event"] == "people_result" && value["protocol"] == 1 && value["action"] == "eye_makeup_enhance_reference"
        && identifier(&value["request_id"]) && value["success"] == true && value["outcome_unknown"] == false
        && value["error"].is_null() && value["created_id"].is_null() && value["batch_id"].is_null()
        && value["frame_emitted"] == false && value["payload_released"] == true
        && fields(request, REQUEST_FIELDS) && command(request).is_ok()
        && request["action"] == value["action"] && request["document_id"] == value["document_id"]
}
pub(crate) fn receipt(value: &Value) -> bool {
    if !action(value) { return true; }
    let required = ["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", "eye_makeup_enhance_request"];
    let optional = ["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "doc_state", "payload_released"];
    if !value.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str())))
        || value["protocol"] != 1 || !identifier(&value["request_id"]) || !value["success"].is_boolean()
        || !value["outcome_unknown"].is_boolean() || value.get("event").is_some_and(|event| event != "people_result")
        || value.get("frame_emitted").is_some_and(|frame| !frame.is_boolean())
        || !value["created_id"].is_null() || !value["batch_id"].is_null() { return false; }
    let request = &value["eye_makeup_enhance_request"];
    if !fields(request, REQUEST_FIELDS) || command(request).is_err()
        || request["action"] != value["action"] || request["document_id"] != value["document_id"] { return false; }
    if value.get("payload_released").is_some() { return released_reference(value); }
    if value["success"] != true { return value["error"].is_string() && diagnostic(&value["error"]); }
    let payload = &value["payload"];
    let proof = &payload["reference_proof"];
    if value["outcome_unknown"] != false || !value["error"].is_null()
        || !reference(proof, &request["target"]) || !document(value, request, proof) { return false; }
    if value["action"] == "eye_makeup_enhance_reference" {
        fields(payload, &["kind", "reference_proof"]) && payload["kind"] == "eye_makeup_enhance_reference"
            && proof["reference_request_id"] == value["request_id"] && value["frame_emitted"] == false
    } else {
        fields(payload, &["kind", "reference_proof", "support_sha256"]) && payload["kind"] == "eye_makeup_enhance_review"
            && proof == &request["payload"]["reference_proof"] && hex(&payload["support_sha256"], 64)
    }
}
/// Redeem the original successful source read in this same epoch-bound ledger.
/// The existing host checks epoch, request identity and first-terminal ownership.
pub(crate) fn reference_matches(candidate: &Value, status: &Value) -> bool {
    if candidate["action"] != "eye_makeup_enhance_review" { return true; }
    let result = &status["result"];
    let original = &result["eye_makeup_enhance_request"];
    command(candidate).is_ok() && status["phase"] == "done" && result["success"] == true && result["outcome_unknown"] == false
        && result.get("payload_released").is_none() && result["action"] == "eye_makeup_enhance_reference" && receipt(result)
        && candidate["payload"]["reference_proof"] == result["payload"]["reference_proof"]
        && status["request_id"] == result["request_id"]
        && candidate["payload"]["reference_proof"]["reference_request_id"] == result["request_id"]
        && CONTEXT.iter().all(|key| candidate[*key] == original[*key])
}

#[cfg(test)]
#[path = "eye_makeup_enhance_protocol_unrun.rs"]
mod tests;
