// SPDX-License-Identifier: GPL-3.0-or-later
//! Facial-structure transport admission through the existing people receipt owner.
//! This validates bounded source/consent echoes, not segmentation or render quality.
//! The engine alone owns source, landmark, support and numeric solver authority.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::hex;

const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST_FIELDS: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_REVISION: u64 = 9_007_199_254_740_991;
const MAX_PIXELS: u64 = 4_000_000;
const OPERATION: &str = "lnx.facial_sculpt.v1";

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
    fields(value, &["version", "highlight", "shadow"]) && value["version"].as_u64() == Some(1)
        && number(&value["highlight"], 0.0, 1.0) && number(&value["shadow"], 0.0, 1.0)
}
fn pair(value: &Value, low: f64, high: f64) -> bool {
    value.as_array().is_some_and(|items| items.len() == 2 && items.iter().all(|n| number(n, low, high)))
}
/// This family's affirmative source-normalized brush consent is never a mask
/// from another operation, an alias approval, or proof that skin is visible.
pub(super) fn region(value: &Value) -> bool {
    if !fields(value, &["recipe", "visible", "unoccluded", "ownership_confirmed"])
        || ["visible", "unoccluded", "ownership_confirmed"].iter().any(|key| value[*key] != true) { return false; }
    let stack = &value["recipe"];
    let Some(objects) = stack["objects"].as_array() else { return false; };
    if !fields(stack, &["version", "domain", "objects"]) || stack["version"].as_u64() != Some(1)
        || stack["domain"] != "source-normalized" || !(1..=64).contains(&objects.len()) { return false; }
    let mut ids = std::collections::BTreeSet::new();
    let mut total_points = 0usize;
    let mut adds_visible_area = false;
    for object in objects {
        if !fields(object, &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "points", "axes"])
            || !object["id"].as_str().is_some_and(|s| (1..=64).contains(&s.len())
                && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b)))
            || !ids.insert(object["id"].as_str().unwrap())
            || !object["name"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 80
                && s.chars().all(|c| c as u32 >= 32))
            || !object["enabled"].is_boolean() || object["kind"] != "brush"
            || !matches!(object["operation"].as_str(), Some("add" | "subtract"))
            || !number(&object["opacity"], 0.0, 1.0) || !number(&object["feather"], 0.0, 100.0) { return false; }
        let (Some(points), Some(axes)) = (object["points"].as_array(), object["axes"].as_array()) else { return false; };
        if !(1..=1024).contains(&points.len()) || !points.iter().all(|point| pair(point, 0.0, 1.0))
            || axes.len() != 2 || !axes.iter().all(|axis| pair(axis, -4.0, 4.0)) { return false; }
        total_points += points.len();
        if total_points > 8192 || (axes[0][0].as_f64().unwrap() * axes[1][1].as_f64().unwrap()
            - axes[0][1].as_f64().unwrap() * axes[1][0].as_f64().unwrap()).abs() < 1e-12 { return false; }
        adds_visible_area |= object["enabled"] == true && object["operation"] == "add"
            && object["opacity"].as_f64().unwrap() > 0.0;
    }
    adds_visible_area
}
pub(super) fn reference(value: &Value, target: &Value) -> bool {
    fields(value, &["source", "face_ref", "landmark_digest", "preview_sha256", "reference_request_id"])
        && source(&value["source"]) && value["face_ref"] == target["face_ref"]
        && value["source"]["sha256"] == target["face_ref"]["asset_sha256"]
        && hex(&value["landmark_digest"], 64) && hex(&value["preview_sha256"], 64)
        && identifier(&value["reference_request_id"])
}
pub(crate) fn action(value: &Value) -> bool {
    matches!(value["action"].as_str(), Some("facial_sculpt_reference" | "facial_sculpt_review"))
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
            Some("facial_sculpt_reference") => fields(&value["payload"], &[]),
            Some("facial_sculpt_review") => fields(&value["payload"], &["region", "reference_proof"])
                && reference(&value["payload"]["reference_proof"], &value["target"])
                && region(&value["payload"]["region"]),
            _ => false,
        };
    if valid { Ok(()) } else { Err("面部立体审核需要当前单脸、精确原图凭据和独立确认的可见源图笔迹".into()) }
}
pub(crate) fn binding(value: &Value) -> Result<Option<Value>, String> {
    if value["cmd"] != "people" || !action(value) { return Ok(None); }
    command(value)?;
    let mut request = json!({});
    for key in REQUEST_FIELDS { request[*key] = value[*key].clone(); }
    Ok(Some(json!({"facial_sculpt_request": request})))
}
/// Read classification is captured from the original exact command. No later
/// event label can turn a pending review mutation into a disposable source read.
pub(crate) fn read_only(value: &Value) -> bool {
    value["cmd"] == "people" && value["action"] == "facial_sculpt_reference"
        && identifier(&value["request_id"]) && command(value).is_ok()
}

/// Canonical base64, RGB8 PNG framing/CRC, dimensions and digest only. This does
/// not inflate image data or claim the PNG depicts correctly segmented skin.
fn source_preview(value: &Value, proof: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    let source = &proof["source"];
    if !fields(value, &["mime", "base64", "width", "height", "sha256", "source_sha256", "source_width", "source_height",
        "decoded_width", "decoded_height", "mapping", "orientation"])
        || value["mime"] != "image/png" || value["sha256"] != proof["preview_sha256"]
        || value["source_sha256"] != source["sha256"] || value["source_width"] != source["width"]
        || value["source_height"] != source["height"] || value["mapping"] != "normalized_full_frame"
        || value["orientation"] != "exif_normalized_once" { return false; }
    let dimensions: Option<Vec<u64>> = ["source_width", "source_height", "decoded_width", "decoded_height", "width", "height"]
        .iter().map(|key| value[*key].as_u64()).collect();
    let Some(n) = dimensions else { return false; };
    let (sw, sh, dw, dh, width, height) = (n[0], n[1], n[2], n[3], n[4], n[5]);
    if n.iter().any(|size| !(2..=1_000_000).contains(size)) || dw > sw || dh > sh || width > dw || height > dh
        || width.max(height) > 1280
        || ((dw != sw || dh != sh) && (dw % 8 != 0 || dh % 8 != 0 || dw * sh >= (dh + 8) * sw || dh * sw >= (dw + 8) * sh))
        || (if dw.max(dh) <= 1280 { width != dw || height != dh }
            else { width.max(height) != 1280 || (width * dh).abs_diff(height * dw) > dw.max(dh) }) { return false; }
    let Some(encoded) = value["base64"].as_str() else { return false; };
    if encoded.is_empty() || encoded.len() > 6_990_508 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= 5_242_880 && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, width as u32, height as u32) && bytes.get(25) == Some(&2)
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
fn observation(value: &Value, facts: &Value, report: &Value) -> bool {
    fields(value, &["contract", "source_sha256", "semantic_model_sha256", "producer_width", "producer_height"])
        && value["contract"] == "mediapipe-face-skin-edit-weight-v1"
        && value["source_sha256"] == report["source"]["sha256"]
        && value["semantic_model_sha256"] == facts["semantic_model_sha256"]
        && integer(&value["producer_width"], 1, 1_000_000) && integer(&value["producer_height"], 1, 1_000_000)
}
/// These diagnostics are bounded, internally consistent descriptions, not proof
/// that the original native solver ran or that a result is visually acceptable.
fn facts(value: &Value, report: &Value) -> bool {
    if fields(value, &[]) { return true; }
    let zones = ["forehead_center", "nose_bridge", "nose_tip", "midface_left", "midface_right", "chin"];
    if !fields(value, &["zones", "measured_face_width", "radius", "protected_face_boxes", "recipe", "face_ref",
        "landmark_digest", "semantic_model_sha256", "skin_observation", "source_dimensions", "render_dimensions",
        "positive_structure_pixels", "negative_structure_pixels", "changed_pixels", "reason", "native_solver", "policy",
        "composition", "limitations"])
        || !fields(&value["zones"], &zones) || !zones.iter().all(|key| integer(&value["zones"][*key], 0, MAX_PIXELS))
        || !number(&value["measured_face_width"], 96.0, 5120.0) || !integer(&value["radius"], 2, 128)
        || !integer(&value["protected_face_boxes"], 0, 4096)
        || value["recipe"] != report["recipe"] || value["face_ref"] != report["face_ref"]
        || value["landmark_digest"] != report["landmark_digest"] || !hex(&value["semantic_model_sha256"], 64)
        || !observation(&value["skin_observation"], value, report)
        || !dimensions(&value["source_dimensions"]) || !dimensions(&value["render_dimensions"])
        || value["source_dimensions"][0] != report["source"]["width"] || value["source_dimensions"][1] != report["source"]["height"]
        || !["positive_structure_pixels", "negative_structure_pixels", "changed_pixels"].iter().all(|key| integer(&value[*key], 0, MAX_PIXELS))
        || value["native_solver"] != "rust-facial-two-scale-log-structure-v1"
        || value["policy"] != "reviewed-source-two-scale-facial-log-structure-v1"
        || value["composition"] != "source-log-gain-common-linear-rgb-gamut-bound"
        || value["limitations"] != json!(["not-3d-relighting-or-highlight-recovery", "not-specular-gloss-or-skin-smoothing",
            "review-is-not-complete-occlusion-segmentation", "photo-and-numeric-acceptance-unrun"]) { return false; }
    let positive = value["positive_structure_pixels"].as_u64().unwrap();
    let negative = value["negative_structure_pixels"].as_u64().unwrap();
    let changed = value["changed_pixels"].as_u64().unwrap();
    positive + negative == changed
        && (if changed == 0 { value["reason"] == "no_measurable_broad_structure" } else { value["reason"].is_null() })
}
fn report(value: &Value, payload: &Value, changed: bool) -> bool {
    let proof = &payload["reference_proof"];
    if !fields(value, &["recipe", "facts", "source", "face_ref", "landmark_digest", "reviewed", "source_preview", "reference_proof",
        "support_sha256", "native_available", "support_available", "support_reason", "suspended", "alias_required", "alias_reason"])
        || !recipe(&value["recipe"]) || !facts(&value["facts"], value) || value["source"] != proof["source"]
        || value["face_ref"] != proof["face_ref"] || value["landmark_digest"] != proof["landmark_digest"]
        || !value["reviewed"].is_boolean() || !value["native_available"].is_boolean() || !value["support_available"].is_boolean()
        || !diagnostic(&value["support_reason"]) || !diagnostic(&value["suspended"])
        || !(value["support_sha256"].is_null() || hex(&value["support_sha256"], 64))
        || !value["alias_required"].is_boolean() || !diagnostic(&value["alias_reason"])
        || (value["alias_required"] == true) != !value["alias_reason"].is_null()
        || (value["support_available"] == true && (value["reviewed"] != true || !value["support_reason"].is_null())) { return false; }
    // These two alias diagnostics explain a refusal, never grant another row's
    // permission. Any member/review/ack fields fail the exact report allowlist.
    if changed {
        value["reviewed"] == true && value["support_sha256"] == payload["support_sha256"]
            && value["reference_proof"].is_null() && value["source_preview"].is_null() && value["alias_required"] == false
    } else {
        value["reference_proof"] == *proof && source_preview(&value["source_preview"], proof)
            && (value["reviewed"] == true) == !value["support_sha256"].is_null()
    }
}
fn document(value: &Value, request: &Value, proof: &Value) -> bool {
    let people = &value["doc_state"]["people"];
    let binding = &people["binding"];
    let changed = value["action"] == "facial_sculpt_review";
    binding["document_id"] == request["document_id"] && binding["document_epoch"] == request["document_epoch"]
        && binding["asset_sha256"] == proof["source"]["sha256"]
        && next_revision(&binding["document_revision"], &request["document_revision"], changed)
        && next_revision(&people["revision"], &request["state_revision"], changed)
        && people["association_revision"] == request["association_revision"]
        && people["selected_face_id"] == request["target"]["target_id"] && people["editing_target"] == request["target"]
        && people["resolved"]["face_ref"] == proof["face_ref"]
        && people["resolved"]["state_revision"] == people["revision"]
        && people["resolved"]["association_revision"] == people["association_revision"]
        && ["highlight", "shadow"].iter().all(|key| {
            let path = format!("/{key}");
            people["resolved"]["operations"][OPERATION][path.as_str()]["value"].as_f64()
                == people["facial_sculpt"]["recipe"][*key].as_f64()
        })
        && report(&people["facial_sculpt"], &value["payload"], changed)
}
/// A released source read preserves its known outcome, but carries no image,
/// document state or reusable reference authority. It can never release a write.
pub(crate) fn released_reference(value: &Value) -> bool {
    let request = &value["facial_sculpt_request"];
    fields(value, &["event", "protocol", "action", "request_id", "document_id", "facial_sculpt_request",
        "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && value["event"] == "people_result" && value["protocol"] == 1 && value["action"] == "facial_sculpt_reference"
        && identifier(&value["request_id"]) && value["success"] == true && value["outcome_unknown"] == false
        && value["error"].is_null() && value["created_id"].is_null() && value["batch_id"].is_null()
        && value["frame_emitted"] == false && value["payload_released"] == true
        && fields(request, REQUEST_FIELDS) && command(request).is_ok()
        && request["action"] == value["action"] && request["document_id"] == value["document_id"]
}
pub(crate) fn receipt(value: &Value) -> bool {
    if !action(value) { return true; }
    let required = ["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", "facial_sculpt_request"];
    let optional = ["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "doc_state", "payload_released"];
    if !value.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str())))
        || value["protocol"] != 1 || !identifier(&value["request_id"]) || !value["success"].is_boolean()
        || !value["outcome_unknown"].is_boolean() || value.get("event").is_some_and(|event| event != "people_result")
        || value.get("frame_emitted").is_some_and(|frame| !frame.is_boolean())
        || !value["created_id"].is_null() || !value["batch_id"].is_null() { return false; }
    let request = &value["facial_sculpt_request"];
    if !fields(request, REQUEST_FIELDS) || command(request).is_err()
        || request["action"] != value["action"] || request["document_id"] != value["document_id"] { return false; }
    if value.get("payload_released").is_some() { return released_reference(value); }
    if value["success"] != true { return value["error"].is_string() && diagnostic(&value["error"]); }
    let payload = &value["payload"];
    let proof = &payload["reference_proof"];
    if value["outcome_unknown"] != false || !value["error"].is_null()
        || !reference(proof, &request["target"]) || !document(value, request, proof) { return false; }
    if value["action"] == "facial_sculpt_reference" {
        fields(payload, &["kind", "reference_proof"]) && payload["kind"] == "facial_sculpt_reference"
            && proof["reference_request_id"] == value["request_id"] && value["frame_emitted"] == false
    } else {
        fields(payload, &["kind", "reference_proof", "support_sha256"]) && payload["kind"] == "facial_sculpt_review"
            && proof == &request["payload"]["reference_proof"] && hex(&payload["support_sha256"], 64)
    }
}
/// Redeem the original successful source read in this same epoch-bound ledger.
/// The existing host checks epoch, request identity and first-terminal ownership.
pub(crate) fn reference_matches(command: &Value, status: &Value) -> bool {
    if command["action"] != "facial_sculpt_review" { return true; }
    let result = &status["result"];
    let original = &result["facial_sculpt_request"];
    status["phase"] == "done" && result["success"] == true && result["outcome_unknown"] == false
        && result.get("payload_released").is_none() && result["action"] == "facial_sculpt_reference" && receipt(result)
        && command["payload"]["reference_proof"] == result["payload"]["reference_proof"]
        && command["payload"]["reference_proof"]["reference_request_id"] == result["request_id"]
        && CONTEXT.iter().all(|key| command[*key] == original[*key])
}

#[cfg(test)]
#[path = "facial_sculpt_protocol_unrun.rs"]
mod tests;
