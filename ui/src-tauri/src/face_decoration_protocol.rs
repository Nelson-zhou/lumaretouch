// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded source/face/landmark review through the existing people receipt owner.
//! This is transport admission, not proof of render quality. Fixtures are UNRUN.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::hex;

const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const PATTERNS: &[&str] = &["freckle_dust", "freckle_bridge", "freckle_constellation", "freckle_sunburst", "freckle_scatter",
    "mole_left_cheek", "mole_right_cheek", "mole_pair"];
const MAX_REVISION: u64 = 9_007_199_254_740_991;

fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|key| map.contains_key(*key)))
}
fn text(v: &Value) -> bool {
    v.as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 128 && !s.contains('\0'))
}
fn number(v: &Value, low: f64, high: f64) -> bool {
    v.as_f64().is_some_and(|n| n.is_finite() && (low..=high).contains(&n))
}
fn source(v: &Value) -> bool {
    fields(v, &["sha256", "width", "height"]) && hex(&v["sha256"], 64)
        && ["width", "height"].iter().all(|key| v[*key].as_u64().is_some_and(|n| (2..=1_000_000).contains(&n)))
}
fn recipe(v: &Value) -> bool {
    fields(v, &["version", "pattern", "strength"]) && v["version"].as_u64() == Some(1)
        && v["pattern"].as_str().is_some_and(|name| PATTERNS.contains(&name)) && number(&v["strength"], 0.0, 1.0)
}
fn pair(v: &Value, low: f64, high: f64) -> bool {
    v.as_array().is_some_and(|p| p.len() == 2 && p.iter().all(|n| number(n, low, high)))
}
fn region(v: &Value) -> bool {
    if !fields(v, &["recipe", "visible", "unoccluded", "ownership_confirmed"])
        || ["visible", "unoccluded", "ownership_confirmed"].iter().any(|key| v[*key] != true) { return false; }
    let mask = &v["recipe"];
    let Some(objects) = mask["objects"].as_array() else { return false; };
    if !fields(mask, &["version", "domain", "objects"]) || mask["version"].as_u64() != Some(1)
        || mask["domain"] != "source-normalized" || !(1..=64).contains(&objects.len())
        || !objects.iter().any(|o| o["enabled"] == true && o["operation"] == "add"
            && o["opacity"].as_f64().is_some_and(|n| n > 0.0)) { return false; }
    let mut ids = std::collections::BTreeSet::new();
    let mut total = 0usize;
    objects.iter().all(|object| {
        if !fields(object, &["id", "name", "enabled", "operation", "kind", "opacity", "feather", "points", "axes"])
            || !object["id"].as_str().is_some_and(|s| (1..=64).contains(&s.len())
                && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))
            || !ids.insert(object["id"].as_str().unwrap())
            || !object["name"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 80 && s.chars().all(|c| c as u32 >= 32))
            || !object["enabled"].is_boolean() || object["kind"] != "brush"
            || !matches!(object["operation"].as_str(), Some("add" | "subtract"))
            || !number(&object["opacity"], 0.0, 1.0) || !number(&object["feather"], 0.0, 100.0) { return false; }
        let (Some(points), Some(axes)) = (object["points"].as_array(), object["axes"].as_array()) else { return false; };
        total += points.len();
        (1..=1024).contains(&points.len()) && total <= 8192 && points.iter().all(|p| pair(p, 0.0, 1.0))
            && axes.len() == 2 && axes.iter().all(|p| pair(p, -4.0, 4.0))
            && (axes[0][0].as_f64().unwrap() * axes[1][1].as_f64().unwrap()
                - axes[0][1].as_f64().unwrap() * axes[1][0].as_f64().unwrap()).abs() >= 1e-12
    })
}
fn reference(v: &Value, target: &Value) -> bool {
    fields(v, &["source", "face_ref", "landmark_digest", "preview_sha256", "reference_request_id"])
        && source(&v["source"]) && v["face_ref"] == target["face_ref"]
        && v["source"]["sha256"] == target["face_ref"]["asset_sha256"]
        && hex(&v["landmark_digest"], 64) && hex(&v["preview_sha256"], 64) && text(&v["reference_request_id"])
}
pub(crate) fn action(v: &Value) -> bool {
    matches!(v["action"].as_str(), Some("face_decoration_reference" | "face_decoration_review"))
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let required = ["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
    let envelope = v.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || ["cmd", "request_id", "host_epoch"].contains(&key.as_str())))
        && v.get("request_id").map_or(true, text)
        && v.get("cmd").map_or(true, |name| name == "people" && text(&v["request_id"]))
        && v.get("host_epoch").map_or(true, |epoch| v["cmd"] == "people" && hex(epoch, 32));
    let mut context = json!({}); for key in CONTEXT { context[*key] = v[*key].clone(); }
    let valid = envelope && super::valid_context(&context) && v["target"]["scope"] == "face"
        && match v["action"].as_str() {
            Some("face_decoration_reference") => fields(&v["payload"], &[]),
            Some("face_decoration_review") => fields(&v["payload"], &["reference_proof", "region"])
                && reference(&v["payload"]["reference_proof"], &v["target"]) && region(&v["payload"]["region"]),
            _ => false,
        };
    if valid { Ok(()) } else { Err("面饰审核需要当前单脸、原图凭据和明确确认的可见源图笔迹".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({"action":v["action"], "payload":v["payload"]});
    for key in CONTEXT { request[*key] = v[*key].clone(); }
    Ok(Some(json!({"face_decoration_request":request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    let required = ["cmd", "request_id", "action", "payload", "document_id", "document_epoch", "document_revision",
        "state_revision", "association_revision", "target"];
    v["cmd"] == "people" && v["action"] == "face_decoration_reference" && command(v).is_ok() && text(&v["request_id"])
        && v.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
            && map.keys().all(|key| required.contains(&key.as_str()) || key == "host_epoch"))
        && v.get("host_epoch").map_or(true, |epoch| hex(epoch, 32))
}

fn source_preview(v: &Value, proof: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    let source = &proof["source"];
    if !fields(v, &["mime", "base64", "width", "height", "sha256", "source_sha256", "source_width", "source_height",
        "decoded_width", "decoded_height", "mapping", "orientation"])
        || v["mime"] != "image/png" || v["sha256"] != proof["preview_sha256"]
        || v["source_sha256"] != source["sha256"] || v["source_width"] != source["width"] || v["source_height"] != source["height"]
        || v["mapping"] != "normalized_full_frame" || v["orientation"] != "exif_normalized_once" { return false; }
    let numbers: Option<Vec<u64>> = ["source_width", "source_height", "decoded_width", "decoded_height", "width", "height"]
        .iter().map(|key| v[*key].as_u64()).collect();
    let Some(n) = numbers else { return false; };
    let (sw, sh, dw, dh, w, h) = (n[0], n[1], n[2], n[3], n[4], n[5]);
    if n.iter().any(|n| !(2..=1_000_000).contains(n)) || dw > sw || dh > sh || w > dw || h > dh || w.max(h) > 1280
        || ((dw != sw || dh != sh) && (dw % 8 != 0 || dh % 8 != 0 || dw * sh >= (dh + 8) * sw || dh * sw >= (dw + 8) * sh))
        || (if dw.max(dh) <= 1280 { w != dw || h != dh } else { w.max(h) != 1280 || (w * dh).abs_diff(h * dw) > dw.max(dh) }) { return false; }
    let Some(encoded) = v["base64"].as_str() else { return false; };
    if encoded.is_empty() || encoded.len() > 6_990_508 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= 5_242_880 && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, w as u32, h as u32) && bytes.get(25) == Some(&2)
        && format!("{:x}", Sha256::digest(&bytes)) == proof["preview_sha256"].as_str().unwrap_or("")
}
fn next_revision(actual: &Value, expected: &Value, changed: bool) -> bool {
    actual.as_u64().zip(expected.as_u64()).is_some_and(|(after, before)| after <= MAX_REVISION
        && if changed { before.checked_add(1) == Some(after) } else { before == after })
}
fn diagnostic(v: &Value) -> bool {
    v.is_null() || v.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 4096 && !s.contains('\0'))
}
fn facts(v: &Value, report: &Value) -> bool {
    if fields(v, &[]) { return true; }
    if fields(v, &["reason", "changed_pixels"]) {
        return v["reason"] == "disabled" && v["changed_pixels"].as_u64() == Some(0);
    }
    // Renderer diagnostics are bounded and never authorize support or pixels.
    fields(v, &["reviewed_support_pixels", "face_frame", "visibility_method", "limitation", "face_ref", "recipe",
        "catalogue_sha256", "semantic_model_sha256", "changed_pixels", "reason", "rasterizer", "contribution_model", "composition"])
        && ["reviewed_support_pixels", "changed_pixels"].iter().all(|key| v[*key].as_u64().is_some_and(|n| n <= 4_000_000))
        && v["face_ref"] == report["face_ref"] && v["recipe"] == report["recipe"]
        && hex(&v["catalogue_sha256"], 64) && hex(&v["semantic_model_sha256"], 64)
        && v["face_frame"] == "measured-nose-origin-cheek-width-affine"
        && v["visibility_method"] == "decoration-review-intersected-with-actual-skin-and-exclusions"
        && v["limitation"] == "known-occluders-and-human-review-not-complete-instance-segmentation"
        && v["rasterizer"] == "exact-source-pixel-area-piecewise-linear-pigment-v1"
        && v["contribution_model"] == "bounded-multiplicative-pigment-not-blemish-removal"
        && v["composition"] == "direction-preserving-per-pixel-SDR-headroom-gain-no-channel-clipping"
        && (if v["changed_pixels"].as_u64() == Some(0) { v["reason"] == "no_measurable_change" } else { v["reason"].is_null() })
}
fn report(v: &Value, payload: &Value, changed: bool) -> bool {
    let proof = &payload["reference_proof"];
    if !fields(v, &["recipe", "facts", "source", "face_ref", "landmark_digest", "reviewed", "source_preview", "reference_proof",
        "support_sha256", "native_available", "support_available", "support_reason", "suspended"])
        || !recipe(&v["recipe"]) || !facts(&v["facts"], v) || v["source"] != proof["source"] || v["face_ref"] != proof["face_ref"]
        || v["landmark_digest"] != proof["landmark_digest"] || !v["reviewed"].is_boolean()
        || !v["native_available"].is_boolean() || !v["support_available"].is_boolean()
        || !diagnostic(&v["support_reason"]) || !diagnostic(&v["suspended"])
        || !(v["support_sha256"].is_null() || hex(&v["support_sha256"], 64)) { return false; }
    if changed {
        v["reviewed"] == true && v["support_sha256"] == payload["support_sha256"]
            && v["reference_proof"].is_null() && v["source_preview"].is_null()
    } else {
        v["reference_proof"] == *proof && source_preview(&v["source_preview"], proof)
            && (v["reviewed"] == true) == !v["support_sha256"].is_null()
    }
}
fn document(v: &Value, request: &Value, proof: &Value) -> bool {
    let people = &v["doc_state"]["people"];
    let binding = &people["binding"];
    let changed = v["action"] == "face_decoration_review";
    binding["document_id"] == request["document_id"] && binding["document_epoch"] == request["document_epoch"]
        && binding["asset_sha256"] == proof["source"]["sha256"]
        && next_revision(&binding["document_revision"], &request["document_revision"], changed)
        && next_revision(&people["revision"], &request["state_revision"], changed)
        && people["association_revision"] == request["association_revision"]
        && people["selected_face_id"] == request["target"]["target_id"] && people["editing_target"] == request["target"]
        && people["resolved"]["face_ref"] == proof["face_ref"]
        && people["resolved"]["state_revision"] == people["revision"]
        && people["resolved"]["association_revision"] == people["association_revision"]
        && people["resolved"]["operations"]["lnx.face_decoration.v1"]["/pattern"]["value"] == people["face_decoration"]["recipe"]["pattern"]
        && people["resolved"]["operations"]["lnx.face_decoration.v1"]["/strength"]["value"].as_f64()
            == people["face_decoration"]["recipe"]["strength"].as_f64()
        && report(&people["face_decoration"], &v["payload"], changed)
}
/// A released cached source page preserves only its known successful read.
/// It supplies neither document state nor usable reference/mutation authority.
pub(crate) fn released_reference(v: &Value) -> bool {
    let request = &v["face_decoration_request"];
    fields(v, &["event", "protocol", "action", "request_id", "document_id", "face_decoration_request",
        "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && v["event"] == "people_result" && v["protocol"] == 1 && v["action"] == "face_decoration_reference"
        && text(&v["request_id"]) && v["success"] == true && v["outcome_unknown"] == false
        && v["error"].is_null() && v["created_id"].is_null() && v["batch_id"].is_null()
        && v["frame_emitted"] == false && v["payload_released"] == true
        && fields(request, &["action", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target", "payload"])
        && command(request).is_ok() && request["action"] == v["action"] && request["document_id"] == v["document_id"]
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    let required = ["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", "face_decoration_request"];
    let optional = ["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "doc_state", "payload_released"];
    if !v.as_object().is_some_and(|map| required.iter().all(|key| map.contains_key(*key))
        && map.keys().all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str())))
        || v["protocol"] != 1 || !text(&v["request_id"]) || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()
        || v.get("event").is_some_and(|event| event != "people_result")
        || v.get("frame_emitted").is_some_and(|frame| !frame.is_boolean()) || !v["created_id"].is_null() || !v["batch_id"].is_null() { return false; }
    let request = &v["face_decoration_request"];
    if !fields(request, &["action", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target", "payload"])
        || command(request).is_err() || request["action"] != v["action"] || request["document_id"] != v["document_id"] { return false; }
    if v.get("payload_released").is_some() { return released_reference(v); }
    if v["success"] != true { return v["error"].is_string(); }
    let p = &v["payload"];
    let proof = &p["reference_proof"];
    if v["outcome_unknown"] != false || !v["error"].is_null() || !reference(proof, &request["target"])
        || !document(v, request, proof) { return false; }
    if v["action"] == "face_decoration_reference" {
        fields(p, &["kind", "reference_proof"]) && p["kind"] == "face_decoration_reference"
            && proof["reference_request_id"] == v["request_id"]
    } else {
        fields(p, &["kind", "reference_proof", "support_sha256"]) && p["kind"] == "face_decoration_review"
            && proof == &request["payload"]["reference_proof"] && hex(&p["support_sha256"], 64)
    }
}
/// Redeem only the original successful reference in the same terminal ledger.
/// The engine remains responsible for actual source/landmark/support authority.
pub(crate) fn reference_matches(command: &Value, status: &Value) -> bool {
    if command["action"] != "face_decoration_review" { return true; }
    let result = &status["result"];
    let original = &result["face_decoration_request"];
    status["phase"] == "done" && result["success"] == true && result["outcome_unknown"] == false && result.get("payload_released").is_none()
        && result["action"] == "face_decoration_reference" && receipt(result)
        && command["payload"]["reference_proof"] == result["payload"]["reference_proof"]
        && command["payload"]["reference_proof"]["reference_request_id"] == result["request_id"]
        && CONTEXT.iter().all(|key| command[*key] == original[*key])
}

#[cfg(test)]
#[path = "face_decoration_protocol_unrun.rs"]
mod tests;
