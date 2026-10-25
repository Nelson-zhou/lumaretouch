// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded source-only reference suggestions inside the existing people owner.
//! Metadata/identity validation only. Never a fit, consent, render or write path.
//! AUTHORED / UNRUN: source fixtures below have not been compiled or executed.
use serde_json::{json, Value};
use std::collections::BTreeSet;
use crate::original_shadow_transfer_protocol::{hex, source_proof};
use super::skin_reference_match::{fields, allowed, identifier, revision,
    decimal_revision, face_ref, diagnostic, source};

pub(crate) const MARKER: &str = "skin_reference_choice_request";
pub(crate) const ACTION: &str = "skin_reference_choice";
const FACE_OP: &str = "lnx.skin_reference_match.v1";
const BODY_OP: &str = "lnx.skin_reference_body_match.v1";
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const REQUEST: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_FACES: usize = 64;
const MAX_REQUEST_BYTES: usize = 256 * 1024;
const MAX_RESULT_BYTES: usize = 1024 * 1024;
const LIMITATIONS: &[&str] = &["not-a-complete-photograph-face-census",
    "observed-source-luminance-not-intrinsic-complexion",
    "confidence-is-not-brightness-and-no-demographic-inference",
    "unknown-occlusion-and-model-errors-require-visual-review",
    "resampled-semantic-observation-is-not-fresh-full-resolution-inference",
    "not-proprietary-metric-parity-or-complete-ai-multi-person-feature"];

pub(crate) fn action(v: &Value) -> bool { v["action"] == ACTION }
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let mut context = json!({}); for key in CONTEXT { context[*key] = v[*key].clone(); }
    let p = &v["payload"]; let asset = &v["target"]["target_id"];
    let valid = allowed(v, REQUEST, &["cmd", "request_id", "host_epoch"])
        && v.to_string().len() <= MAX_REQUEST_BYTES
        && v.get("request_id").map_or(true, identifier)
        && v.get("cmd").map_or(true, |cmd| cmd == "people" && identifier(&v["request_id"]))
        && v.get("host_epoch").map_or(true, |epoch| v["cmd"] == "people" && hex(epoch, 32))
        && super::valid_context(&context) && identifier(&v["document_id"]) && identifier(&v["document_epoch"])
        && fields(&v["target"], &["scope", "target_id", "face_ref"])
        && v["target"]["scope"] == "all_people" && v["target"]["face_ref"].is_null() && hex(asset, 64)
        && allowed(p, &["family", "source_review_sha256"], &["manual_reference"])
        && matches!(p["family"].as_str(), Some("face" | "body")) && hex(&p["source_review_sha256"], 64)
        && p.get("manual_reference").map_or(true, |r| r.is_null() || face_ref(r, asset));
    if valid { Ok(()) } else { Err("参照建议需要当前整张照片、原有审核来源及明确的同图手动参照；不会自动应用".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({}); for key in REQUEST { request[*key] = v[*key].clone(); }
    Ok(Some(json!({"skin_reference_choice_request":request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && action(v) && identifier(&v["request_id"]) && command(v).is_ok()
}

fn finite(v: &Value) -> Option<f64> { v.as_f64().filter(|n| n.is_finite()) }
fn close(a: f64, b: f64) -> bool { (a - b).abs() <= 1e-12 * a.abs().max(b.abs()).max(1.0) }
fn positive_integer(v: &Value) -> bool { revision(v) && v.as_u64().is_some_and(|n| n > 0) }
fn window(v: &Value, s: &Value) -> Option<u64> {
    let rows = v.as_array()?; if rows.len() != 4 { return None; }
    let (y, x, h, w) = (rows[0].as_u64()?, rows[1].as_u64()?, rows[2].as_u64()?, rows[3].as_u64()?);
    if h == 0 || w == 0 || y.checked_add(h)? > s["height"].as_u64()?
        || x.checked_add(w)? > s["width"].as_u64()? { return None; }
    let pixels = h.checked_mul(w)?;
    // The native self-fit counts the same ROI twice against its 32 MP limit.
    (pixels <= 16_000_000).then_some(pixels)
}
fn evidence(v: &Value, s: &Value) -> bool {
    fields(v, &["backend", "detector_model_sha256", "semantic_model_sha256", "landmark_digest", "status", "source_width", "source_height", "orientation"])
        && v["backend"] == "mediapipe" && v["status"] == "verified" && v["orientation"] == "exif_normalized_once"
        && v["source_width"] == s["width"] && v["source_height"] == s["height"]
        && ["detector_model_sha256", "semantic_model_sha256", "landmark_digest"].iter().all(|key| hex(&v[*key], 64))
}
fn observation(v: &Value, e: &Value, asset: &Value) -> bool {
    fields(v, &["contract", "source_sha256", "semantic_model_sha256", "producer_width", "producer_height"])
        && v["contract"] == "mediapipe-face-skin-edit-weight-v1" && v["source_sha256"] == *asset
        && v["semantic_model_sha256"] == e["semantic_model_sha256"]
        && ["producer_width", "producer_height"].iter().all(|key|
            v[*key].as_u64().is_some_and(|n| (1..=1_000_000).contains(&n)))
}
fn measurement(v: &Value, pixels: u64) -> bool {
    if !fields(v, &["log_luminance", "linear_luminance", "initial_log_luminance_mad", "robust_sample_count", "robust_weight", "effective_samples", "retained_weight_fraction"])
        || !v.as_object().unwrap().values().all(|n| finite(n).is_some()) { return false; }
    let log = finite(&v["log_luminance"]).unwrap(); let linear = finite(&v["linear_luminance"]).unwrap();
    let Some(count) = v["robust_sample_count"].as_u64() else { return false; };
    let ceiling = count as f64 + (count as f64 * 1e-6).max(1e-7);
    (0.01_f64.ln()..0.90_f64.ln()).contains(&log) && log > 0.01_f64.ln()
        && close(linear, log.exp()) && (64..=pixels).contains(&count)
        && (0.0..=0.50 + 1e-12).contains(&finite(&v["initial_log_luminance_mad"]).unwrap())
        && ["robust_weight", "effective_samples"].iter().all(|key| (64.0..=ceiling).contains(&finite(&v[*key]).unwrap()))
        && (0.5..=1.0 + 1e-6).contains(&finite(&v["retained_weight_fraction"]).unwrap())
}
fn candidate(v: &Value, s: &Value, total: usize) -> bool {
    if !face_ref(&v["face_ref"], &s["sha256"]) { return false; }
    match v["status"].as_str() {
        Some("disabled" | "unavailable") => {
            match v["reason"].as_str() {
                None => v["status"] == "disabled" && fields(v, &["face_ref", "status"]),
                Some("actual-face-analysis-unavailable") => fields(v, &["face_ref", "status", "reason"]),
                Some("actual-face-analysis-invalid" | "source-measurement-refused") =>
                    fields(v, &["face_ref", "status", "reason", "detail"]) && diagnostic(&v["detail"])
                    && (v["status"] != "disabled" || v["reason"] != "source-measurement-refused"),
                _ => false,
            }
        }
        Some("measured") => {
            if !fields(v, &["face_ref", "status", "measurement", "source_window", "support_sha256", "evidence", "landmark_digest", "face_skin_observation", "protected_face_boxes", "protected_actual_face_ovals"])
                || !evidence(&v["evidence"], s) || !observation(&v["face_skin_observation"], &v["evidence"], &s["sha256"])
                || !hex(&v["support_sha256"], 64) || v["landmark_digest"] != v["evidence"]["landmark_digest"]
                || v["protected_face_boxes"].as_u64() != Some(total.saturating_sub(1) as u64)
                || !v["protected_actual_face_ovals"].as_u64().is_some_and(|n| n < total as u64) { return false; }
            window(&v["source_window"], s).is_some_and(|pixels| measurement(&v["measurement"], pixels))
        }
        _ => false,
    }
}

/// Reconstruct only displayed ranking and refusal semantics from admitted facts.
/// Counts/confidence/IDs cannot make a darker or tied face the automatic donor.
fn selection(v: &Value, r: &Value) -> bool {
    let rows = v["candidates"].as_array().unwrap();
    let enabled: Vec<&Value> = rows.iter().filter(|row| row["status"] != "disabled").collect();
    let mut ranked: Vec<&Value> = enabled.iter().copied().filter(|row| row["status"] == "measured").collect();
    ranked.sort_by(|a, b| finite(&b["measurement"]["log_luminance"]).unwrap()
        .total_cmp(&finite(&a["measurement"]["log_luminance"]).unwrap())
        .then_with(|| a["face_ref"]["face_instance_id"].as_str().unwrap().cmp(b["face_ref"]["face_instance_id"].as_str().unwrap())));
    let mut blockers: Vec<&str> = Vec::new();
    if enabled.len() < 2 { blockers.push("fewer-than-two-enabled-retained-faces"); }
    if enabled.iter().any(|row| row["status"] != "measured") { blockers.push("enabled-face-measurement-unavailable"); }
    if v["detector_limit_reached"] == true { blockers.push("detector-limit-reached"); }
    let minimum = 1.02_f64.ln();
    if !finite(&v["minimum_log_luminance_gap"]).is_some_and(|n| close(n, minimum)) { return false; }
    let mut ambiguous: Vec<Value> = Vec::new();
    if ranked.len() >= 2 {
        let top = finite(&ranked[0]["measurement"]["log_luminance"]).unwrap();
        let gap = top - finite(&ranked[1]["measurement"]["log_luminance"]).unwrap();
        if !finite(&v["top_log_luminance_gap"]).is_some_and(|n| close(n, gap)) { return false; }
        ambiguous = ranked.iter().filter(|row| top - finite(&row["measurement"]["log_luminance"]).unwrap() <= minimum)
            .map(|row| row["face_ref"].clone()).collect();
        if ambiguous.len() > 1 { blockers.push("brightest-measurements-too-close"); } else { ambiguous.clear(); }
    } else if !v["top_log_luminance_gap"].is_null() { return false; }
    let automatic = if blockers.is_empty() { ranked.first().map(|row| row["face_ref"].clone()).unwrap_or(Value::Null) } else { Value::Null };
    let manual = &r["payload"]["manual_reference"];
    let (selected, mode) = if !manual.is_null() {
        if !ranked.iter().any(|row| row["face_ref"] == *manual) { return false; }
        (manual.clone(), "manual-override-proposal")
    } else if !automatic.is_null() { (automatic.clone(), "automatic-proposal") } else { (Value::Null, "none") };
    v["reference_face_ref"] == selected && v["selection_mode"] == mode
        && v["automatic_status"] == (if automatic.is_null() { "blocked" } else { "proposed" })
        && v["automatic_reference_face_ref"] == automatic && v["automatic_blockers"] == json!(blockers)
        && v["ranked_face_refs"] == json!(ranked.iter().map(|row| row["face_ref"].clone()).collect::<Vec<_>>())
        && v["ambiguous_face_refs"] == json!(ambiguous)
}
fn proposal(v: &Value, p: &Value, r: &Value) -> bool {
    if !fields(v, &["version", "operation_id", "control_id", "method", "source", "source_stage", "source_pixels_sha256", "source_kind", "source_bits", "source_encoding", "state_revision", "association_revision", "candidate_scope", "census_complete", "detector_limit_reached", "candidates", "read_only_proposal", "review_required", "reference_face_exclusion_required", "body_extension_enabled", "fit_retained", "portable", "memory_admission_bytes", "limitations", "reference_face_ref", "selection_mode", "automatic_status", "automatic_reference_face_ref", "automatic_blockers", "ranked_face_refs", "top_log_luminance_gap", "minimum_log_luminance_gap", "ambiguous_face_refs", "proposal_sha256"])
        || v["version"].as_u64() != Some(1) || v["operation_id"] != FACE_OP || v["control_id"] != "control:PC-32465:19"
        || v["method"] != "rust-self-fit-robust-log-linear-srgb-y-v1" || v["source"] != p["source"]
        || v["source_pixels_sha256"] != p["source_pixels_sha256"] || v["source_encoding"] != "encoded-working-srgb-d65-sdr"
        || v["source_stage"] != "immutable-source-before-repair-and-portrait-v1"
        || v["state_revision"] != r["state_revision"] || v["association_revision"] != r["association_revision"]
        || v["candidate_scope"] != "all-enabled-retained-same-source-faces" || v["census_complete"] != false
        || !(v["detector_limit_reached"].is_null() || v["detector_limit_reached"].is_boolean())
        || !["read_only_proposal", "review_required", "reference_face_exclusion_required"].iter().all(|key| v[*key] == true)
        || !["body_extension_enabled", "fit_retained", "portable"].iter().all(|key| v[*key] == false)
        || !positive_integer(&v["memory_admission_bytes"]) || !hex(&v["proposal_sha256"], 64)
        || v["limitations"] != json!(LIMITATIONS) { return false; }
    let creative = !p["source_proof"]["creative_source"].is_null();
    if !(if creative { v["source_kind"] == "creative" && v["source_bits"].as_u64() == Some(32) }
        else { v["source_kind"] == "original" && matches!(v["source_bits"].as_u64(), Some(8 | 16)) }) { return false; }
    let Some(rows) = v["candidates"].as_array() else { return false; };
    let mut seen = BTreeSet::new();
    if rows.len() > MAX_FACES || !rows.iter().all(|row| candidate(row, &p["source"], rows.len())
        && seen.insert(row["face_ref"]["face_instance_id"].as_str().unwrap()))
        || !rows.windows(2).all(|pair| pair[0]["face_ref"]["face_instance_id"].as_str() < pair[1]["face_ref"]["face_instance_id"].as_str()) { return false; }
    selection(v, r)
}
fn memory(v: &Value, p: &Value) -> bool {
    if !fields(v, &["resident_input_bytes", "verification_workspace_bytes", "total_byte_budget", "capture_byte_budget", "measurement_byte_budget", "estimated_peak_bytes"])
        || !v.as_object().unwrap().values().all(positive_integer) { return false; }
    let resident = v["resident_input_bytes"].as_u64().unwrap(); let budget = v["total_byte_budget"].as_u64().unwrap();
    let verification = v["verification_workspace_bytes"].as_u64().unwrap();
    let capture = v["capture_byte_budget"].as_u64().unwrap(); let measure = v["measurement_byte_budget"].as_u64().unwrap();
    let peak = v["estimated_peak_bytes"].as_u64().unwrap(); let admitted = p["memory_admission_bytes"].as_u64().unwrap();
    let Some(reserved) = resident.checked_add(verification) else { return false; };
    // Capture/helper budgets are historical invocation allowances, not claims
    // about final free memory. Never require retrospective budget relabeling.
    // Actual admitted work plus the final resident/verifier reserve must fit.
    reserved < budget && capture <= budget && measure <= budget && admitted <= measure
        && reserved.checked_add(admitted).is_some_and(|minimum| minimum <= peak) && peak <= budget
}
fn report(v: &Value, r: &Value) -> bool {
    if !fields(v, &["kind", "version", "operation_id", "family", "target", "document_id", "revision", "source", "source_proof", "source_review_sha256", "source_image_sha256", "source_pixels_sha256", "graph_sha256", "document_snapshot_sha256", "analysis_sha256", "body_bank_sha256", MARKER, "proposal", "memory", "read_only_proposal", "source_image_load_required", "review_required", "grants_consent", "render_committed", "portable", "report_sha256"])
        || v["kind"] != ACTION || v["version"].as_u64() != Some(1) || v["family"] != r["payload"]["family"]
        || v["operation_id"] != (if v["family"] == "face" { FACE_OP } else { BODY_OP })
        || v["target"] != r["target"] || v["document_id"] != r["document_id"] || !decimal_revision(&v["revision"], &r["document_revision"])
        || v[MARKER] != r["payload"] || v["source_review_sha256"] != r["payload"]["source_review_sha256"]
        || !source(&v["source"], &r["target"]["target_id"]) || !source_proof(&v["source_proof"])
        || v["source_proof"]["asset_sha256"] != r["target"]["target_id"]
        || !["source_review_sha256", "source_image_sha256", "source_pixels_sha256", "graph_sha256", "document_snapshot_sha256", "analysis_sha256", "body_bank_sha256", "report_sha256"].iter().all(|key| hex(&v[*key], 64))
        || !["read_only_proposal", "source_image_load_required", "review_required"].iter().all(|key| v[*key] == true)
        || !["grants_consent", "render_committed", "portable"].iter().all(|key| v[*key] == false) { return false; }
    let width = v["source"]["width"].as_u64().unwrap(); let height = v["source"]["height"].as_u64().unwrap();
    let creative = &v["source_proof"]["creative_source"];
    (2..=65_536).contains(&width) && (2..=65_536).contains(&height) && width * height <= 32_000_000
        && (creative.is_null() || (creative["width"] == v["source"]["width"] && creative["height"] == v["source"]["height"]))
        && proposal(&v["proposal"], v, r) && memory(&v["memory"], &v["proposal"])
}

/// Capture only already validated source metadata from the same receipt owner.
/// No PNG duplication, source-catalog regeneration or independently mutable store.
pub(crate) fn source_catalog_binding(command: &Value, result: &Value) -> Option<Value> {
    if !read_only(command) || result["success"] != true || result["outcome_unknown"] != false
        || result.get("payload_released").is_some() { return None; }
    let (action, marker, valid) = if command["payload"]["family"] == "face" {
        ("skin_reference_match_catalog", super::skin_reference_match::MARKER, super::skin_reference_match::receipt(result))
    } else { ("skin_reference_body_catalog", super::skin_reference_body::MARKER, super::skin_reference_body::receipt(result)) };
    let request = &result[marker]; let p = &result["payload"];
    if !valid || result["action"] != action || !CONTEXT.iter().all(|key| request[*key] == command[*key])
        || p["source_review_sha256"] != command["payload"]["source_review_sha256"] { return None; }
    Some(json!({"family":command["payload"]["family"], "source":p["source"], "source_proof":p["source_proof"],
        "source_review_sha256":p["source_review_sha256"], "source_image_sha256":p["source_image"]["sha256"],
        "faces":p["faces"].as_array().unwrap().iter().map(|row| json!({"face_ref":row["face_ref"],"enabled":row["enabled"]})).collect::<Vec<_>>()}))
}
pub(crate) fn matches_source_catalog(binding: &Value, result: &Value) -> bool {
    if result["success"] != true || result["payload_released"] == true { return true; }
    let p = &result["payload"];
    if !["family", "source", "source_proof", "source_review_sha256", "source_image_sha256"].iter().all(|key| binding[*key] == p[*key]) { return false; }
    let (Some(faces), Some(candidates)) = (binding["faces"].as_array(), p["proposal"]["candidates"].as_array()) else { return false; };
    faces.len() == candidates.len() && candidates.iter().all(|candidate| faces.iter().any(|face|
        face["face_ref"] == candidate["face_ref"] && (face["enabled"] == true) == (candidate["status"] != "disabled")))
}
pub(crate) fn released_read(v: &Value) -> bool {
    let r = &v[MARKER];
    fields(v, &["event", "protocol", "action", "request_id", "document_id", MARKER, "success", "outcome_unknown", "error", "created_id", "batch_id", "frame_emitted", "payload_released"])
        && v["event"] == "people_result" && v["protocol"].as_u64() == Some(1) && action(v) && identifier(&v["request_id"])
        && v["success"] == true && v["outcome_unknown"] == false && v["error"].is_null()
        && v["created_id"].is_null() && v["batch_id"].is_null() && v["frame_emitted"] == false && v["payload_released"] == true
        && fields(r, REQUEST) && command(r).is_ok() && r["action"] == v["action"] && r["document_id"] == v["document_id"]
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    if !allowed(v, &["protocol", "request_id", "action", "document_id", "success", "outcome_unknown", MARKER],
            &["event", "error", "created_id", "batch_id", "frame_emitted", "payload", "payload_released"])
        || v.to_string().len() > MAX_RESULT_BYTES || v["protocol"].as_u64() != Some(1) || !identifier(&v["request_id"])
        || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()
        || v.get("event").is_some_and(|event| event != "people_result")
        || v.get("frame_emitted").is_some_and(|value| value != false)
        || !v["created_id"].is_null() || !v["batch_id"].is_null() { return false; }
    let r = &v[MARKER];
    if !fields(r, REQUEST) || command(r).is_err() || r["action"] != v["action"] || r["document_id"] != v["document_id"] { return false; }
    if v.get("payload_released").is_some() { return released_read(v); }
    if v["success"] == false { return diagnostic(&v["error"]) && v.get("payload").is_none(); }
    v["event"] == "people_result" && v["frame_emitted"] == false
        && v["outcome_unknown"] == false && v["error"].is_null() && report(&v["payload"], r)
}
pub(crate) fn valid_result(v: &Value) -> bool { receipt(v) }

// AUTHORED / UNRUN. Metadata fixtures do not execute a source capture, numerical
// fit, inference, render, browser image load or photographic quality evaluation.
#[cfg(test)]
mod tests {
    use super::*;
    use crate::receipt_host::{ReceiptHost, ReceiptKind};
    fn h(c: char) -> String { c.to_string().repeat(64) }
    fn reference(id: &str) -> Value { json!({"asset_sha256":h('a'),"face_instance_id":id,"analysis_revision":2}) }
    fn request(family: &str) -> Value {
        json!({"cmd":"people","request_id":"choice-fixture","action":ACTION,
            "payload":{"family":family,"source_review_sha256":h('b')},
            "document_id":"doc","document_epoch":"epoch","document_revision":4,
            "state_revision":3,"association_revision":2,
            "target":{"scope":"all_people","target_id":h('a'),"face_ref":null}})
    }
    fn measured(id: &str, luminance: f64) -> Value {
        json!({"face_ref":reference(id),"status":"measured",
            "measurement":{"log_luminance":luminance.ln(),"linear_luminance":luminance,
                "initial_log_luminance_mad":0.01,"robust_sample_count":128,
                "robust_weight":110.0,"effective_samples":115.0,"retained_weight_fraction":0.9},
            "source_window":[0,0,16,16],"support_sha256":h('c'),"landmark_digest":h('d'),
            "evidence":{"backend":"mediapipe","detector_model_sha256":h('e'),"semantic_model_sha256":h('f'),
                "landmark_digest":h('d'),"status":"verified","source_width":32,"source_height":16,"orientation":"exif_normalized_once"},
            "face_skin_observation":{"contract":"mediapipe-face-skin-edit-weight-v1","source_sha256":h('a'),
                "semantic_model_sha256":h('f'),"producer_width":32,"producer_height":16},
            "protected_face_boxes":1,"protected_actual_face_ovals":1})
    }
    fn payload(r: &Value) -> Value {
        let source = json!({"sha256":h('a'),"width":32,"height":16});
        let proposal = json!({"version":1,"operation_id":FACE_OP,"control_id":"control:PC-32465:19",
            "method":"rust-self-fit-robust-log-linear-srgb-y-v1","source":source,
            "source_stage":"immutable-source-before-repair-and-portrait-v1","source_pixels_sha256":h('1'),
            "source_kind":"original","source_bits":16,"source_encoding":"encoded-working-srgb-d65-sdr",
            "state_revision":3,"association_revision":2,"candidate_scope":"all-enabled-retained-same-source-faces",
            "census_complete":false,"detector_limit_reached":null,"candidates":[measured("a",0.4),measured("b",0.2)],
            "read_only_proposal":true,"review_required":true,"reference_face_exclusion_required":true,
            "body_extension_enabled":false,"fit_retained":false,"portable":false,"memory_admission_bytes":268435456,
            "limitations":LIMITATIONS,"reference_face_ref":reference("a"),"selection_mode":"automatic-proposal",
            "automatic_status":"proposed","automatic_reference_face_ref":reference("a"),"automatic_blockers":[],
            "ranked_face_refs":[reference("a"),reference("b")],"top_log_luminance_gap":0.4_f64.ln()-0.2_f64.ln(),
            "minimum_log_luminance_gap":1.02_f64.ln(),"ambiguous_face_refs":[],"proposal_sha256":h('2')});
        json!({"kind":ACTION,"version":1,"operation_id":if r["payload"]["family"] == "face" { FACE_OP } else { BODY_OP },
            "family":r["payload"]["family"],"target":r["target"],"document_id":"doc","revision":"4","source":source,
            "source_proof":{"asset_sha256":h('a'),"original_sha256":h('a'),"creative_source":null},
            "source_review_sha256":h('b'),"source_image_sha256":h('3'),"source_pixels_sha256":h('1'),
            "graph_sha256":h('4'),"document_snapshot_sha256":h('5'),"analysis_sha256":h('6'),"body_bank_sha256":h('7'),
            "skin_reference_choice_request":r["payload"],"proposal":proposal,
            "memory":{"resident_input_bytes":67108864,"verification_workspace_bytes":67108864,
                "total_byte_budget":1073741824,"capture_byte_budget":939524096,
                "measurement_byte_budget":939524096,"estimated_peak_bytes":402653184},
            "read_only_proposal":true,"source_image_load_required":true,"review_required":true,
            "grants_consent":false,"render_committed":false,"portable":false,"report_sha256":h('8')})
    }
    fn result(r: &Value) -> Value {
        json!({"event":"people_result","protocol":1,"action":ACTION,"request_id":r["request_id"],"document_id":r["document_id"],
            "skin_reference_choice_request":binding(r).unwrap().unwrap()[MARKER],"success":true,"outcome_unknown":false,
            "error":null,"created_id":null,"batch_id":null,"frame_emitted":false,"payload":payload(r)})
    }
    #[test]
    fn exact_photo_family_and_optional_manual_echo_without_consent_fields() {
        let good = request("face"); assert!(command(&good).is_ok()); assert!(read_only(&good));
        assert_eq!(binding(&good).unwrap().unwrap()[MARKER].as_object().unwrap().len(), 8);
        for (path, value) in [("/target/scope",json!("face")),("/target/face_ref",reference("a")),
            ("/payload/family",json!("AI")),("/payload/source_review_sha256",json!("A".repeat(64))),
            ("/document_revision",json!(-1)),("/association_revision",json!(true))] {
            let mut bad = good.clone(); *bad.pointer_mut(path).unwrap() = value;
            assert!(command(&bad).is_err(), "{path}"); assert!(!read_only(&bad));
        }
        for name in ["ownership_confirmed", "apply", "amount", "confidence", "brightness", "body_ref"] {
            let mut bad = good.clone(); bad["payload"][name] = json!(true); assert!(command(&bad).is_err(), "{name}");
        }
        let mut manual = good.clone(); manual["payload"]["manual_reference"] = reference("b"); assert!(command(&manual).is_ok());
        manual["payload"]["manual_reference"]["asset_sha256"] = json!(h('f')); assert!(command(&manual).is_err());
        manual = good.clone(); manual["payload"]["manual_reference"] = Value::Null; assert!(command(&manual).is_ok());
        assert_ne!(binding(&good).unwrap(), binding(&manual).unwrap());
        let mut bad = result(&good); bad["payload"][MARKER]["manual_reference"] = Value::Null; assert!(!receipt(&bad));
    }
    #[test]
    fn unknown_whole_photo_census_does_not_erase_a_measured_bounded_proposal() {
        for family in ["face", "body"] {
            let good = result(&request(family)); assert!(receipt(&good));
            assert_eq!(good["payload"]["proposal"]["census_complete"], false);
            assert_eq!(good["payload"]["proposal"]["automatic_status"], "proposed");
            assert_eq!(good["payload"]["proposal"]["operation_id"], FACE_OP);
            let mut bad = good; bad["payload"]["proposal"]["census_complete"] = json!(true); assert!(!receipt(&bad));
        }
    }
    #[test]
    fn historical_measurement_allowance_stays_truthful_when_final_reserve_grows() {
        let mut good = result(&request("face"));
        // Measurement's historical allowance may exceed both initial capture
        // allowance and final remaining space; actual admitted work fits.
        good["payload"]["memory"]["resident_input_bytes"] = json!(134217728);
        good["payload"]["memory"]["capture_byte_budget"] = json!(805306368);
        good["payload"]["memory"]["measurement_byte_budget"] = json!(939524096);
        good["payload"]["memory"]["estimated_peak_bytes"] = json!(469762048);
        assert!(receipt(&good));
        good["payload"]["memory"]["estimated_peak_bytes"] = json!(335544320); assert!(!receipt(&good));
    }
    #[test]
    fn result_rejects_mutations_wrong_source_partial_rows_and_invented_scores() {
        let good = result(&request("face"));
        for (path, value) in [("/frame_emitted",json!(true)),("/payload/grants_consent",json!(true)),
            ("/payload/render_committed",json!(true)),("/payload/review_required",json!(false)),
            ("/payload/source_image_load_required",json!(false)),("/payload/operation_id",json!(BODY_OP)),
            ("/payload/source_review_sha256",json!(h('9'))),("/payload/document_snapshot_sha256",json!("missing")),
            ("/payload/proposal/source_pixels_sha256",json!(h('9'))),("/payload/proposal/source_bits",json!(8.5)),
            ("/payload/proposal/source_stage",json!("edited-preview")),("/payload/proposal/state_revision",json!(4)),
            ("/payload/proposal/candidates/0/status",json!("pending")),
            ("/payload/proposal/candidates/0/face_ref/analysis_revision",json!(-1)),
            ("/payload/proposal/candidates/0/measurement/robust_sample_count",json!(63)),
            ("/payload/proposal/candidates/0/measurement/linear_luminance",json!(0.8)),
            ("/payload/proposal/candidates/0/measurement/robust_weight",json!(500.0)),
            ("/payload/proposal/candidates/0/evidence/backend",json!("synthetic")),
            ("/payload/proposal/candidates/0/landmark_digest",json!(h('8'))),
            ("/payload/proposal/candidates/0/protected_face_boxes",json!(0)),
            ("/payload/proposal/candidates/0/source_window",json!([0,0,17,16])),
            ("/payload/proposal/ranked_face_refs",json!([reference("b"),reference("a")])),
            ("/payload/proposal/reference_face_ref",reference("b")),("/payload/proposal/automatic_blockers",json!(["census-unknown"])),
            ("/payload/memory/estimated_peak_bytes",json!(1073741825_u64))] {
            let mut bad = good.clone(); *bad.pointer_mut(path).unwrap() = value; assert!(!receipt(&bad), "{path}");
        }
        for name in ["doc_state", "frame", "review", "token", "support_bank"] {
            let mut bad = good.clone(); bad[name] = json!({}); assert!(!receipt(&bad), "{name}");
        }
        let mut bad = good; bad["payload"]["proposal"]["candidates"][0]["measurement"]["confidence"] = json!(0.99); assert!(!receipt(&bad));
    }
    fn blocked(v: &mut Value, blockers: Value) {
        let p = &mut v["payload"]["proposal"];
        p["automatic_status"] = json!("blocked"); p["automatic_reference_face_ref"] = Value::Null;
        p["automatic_blockers"] = blockers; p["reference_face_ref"] = Value::Null; p["selection_mode"] = json!("none");
    }
    #[test]
    fn ties_unmeasurable_faces_and_detector_cap_keep_blockers_with_manual_override() {
        let base = result(&request("face"));
        let mut tied = base.clone(); tied["payload"]["proposal"]["candidates"][1] = measured("b",0.4);
        tied["payload"]["proposal"]["top_log_luminance_gap"] = json!(0.0);
        tied["payload"]["proposal"]["ambiguous_face_refs"] = json!([reference("a"),reference("b")]);
        blocked(&mut tied, json!(["brightest-measurements-too-close"])); assert!(receipt(&tied));
        let mut fake = tied.clone(); fake["payload"]["proposal"]["reference_face_ref"] = reference("a"); assert!(!receipt(&fake));
        let mut unavailable = base.clone(); unavailable["payload"]["proposal"]["candidates"][1] =
            json!({"face_ref":reference("b"),"status":"unavailable","reason":"actual-face-analysis-unavailable"});
        unavailable["payload"]["proposal"]["ranked_face_refs"] = json!([reference("a")]);
        unavailable["payload"]["proposal"]["top_log_luminance_gap"] = Value::Null;
        blocked(&mut unavailable,json!(["enabled-face-measurement-unavailable"])); assert!(receipt(&unavailable));
        let mut capped = base; capped["payload"]["proposal"]["detector_limit_reached"] = json!(true);
        blocked(&mut capped,json!(["detector-limit-reached"])); assert!(receipt(&capped));
        for mut v in [tied, unavailable, capped] {
            v[MARKER]["payload"]["manual_reference"] = reference("a");
            v["payload"][MARKER]["manual_reference"] = reference("a");
            v["payload"]["proposal"]["reference_face_ref"] = reference("a");
            v["payload"]["proposal"]["selection_mode"] = json!("manual-override-proposal"); assert!(receipt(&v));
            v["payload"]["proposal"]["reference_face_ref"] = reference("b"); assert!(!receipt(&v));
        }
    }
    #[test]
    fn near_tie_disabled_faces_and_face_cap_never_supply_hidden_winners() {
        let mut near = result(&request("face")); near["payload"]["proposal"]["candidates"][1] = measured("b",0.399);
        near["payload"]["proposal"]["top_log_luminance_gap"] = json!(0.4_f64.ln()-0.399_f64.ln());
        near["payload"]["proposal"]["ambiguous_face_refs"] = json!([reference("a"),reference("b")]);
        blocked(&mut near,json!(["brightest-measurements-too-close"])); assert!(receipt(&near));
        let mut disabled = result(&request("face")); disabled["payload"]["proposal"]["candidates"][1] =
            json!({"face_ref":reference("b"),"status":"disabled"});
        disabled["payload"]["proposal"]["ranked_face_refs"] = json!([reference("a")]);
        disabled["payload"]["proposal"]["top_log_luminance_gap"] = Value::Null;
        blocked(&mut disabled,json!(["fewer-than-two-enabled-retained-faces"])); assert!(receipt(&disabled));
        disabled[MARKER]["payload"]["manual_reference"] = reference("b");
        disabled["payload"][MARKER]["manual_reference"] = reference("b");
        disabled["payload"]["proposal"]["reference_face_ref"] = reference("b");
        disabled["payload"]["proposal"]["selection_mode"] = json!("manual-override-proposal"); assert!(!receipt(&disabled));
        let mut capped = result(&request("face")); capped["payload"]["proposal"]["candidates"] =
            json!((0..=MAX_FACES).map(|n| json!({"face_ref":reference(&format!("face-{n:02}")),"status":"disabled"})).collect::<Vec<_>>());
        assert!(!receipt(&capped));
        let mut missing = result(&request("face")); missing.as_object_mut().unwrap().remove("frame_emitted"); assert!(!receipt(&missing));
    }
    #[test]
    fn failed_or_released_reads_still_require_exact_identity_and_no_publication() {
        let good = result(&request("face")); let mut failed = good.clone(); failed.as_object_mut().unwrap().remove("payload");
        failed["success"] = json!(false); failed["error"] = json!("Actual source changed; no replacement selected"); assert!(receipt(&failed));
        failed["outcome_unknown"] = json!(true); assert!(receipt(&failed));
        let mut bad = failed.clone(); bad["doc_state"] = json!({}); assert!(!receipt(&bad));
        bad = failed.clone(); bad["frame_emitted"] = json!(true); assert!(!receipt(&bad));
        bad = failed; bad.as_object_mut().unwrap().remove(MARKER); assert!(!receipt(&bad));
        let mut released = good; released.as_object_mut().unwrap().remove("payload"); released["payload_released"] = json!(true);
        assert!(released_read(&released)); assert!(receipt(&released));
        released["payload"] = json!({"kind":ACTION}); assert!(!receipt(&released));
    }

    // A framed source PNG for native metadata fixtures only. Stored DEFLATE,
    // CRC and Adler-32 are authored here; not decoded or run during this work.
    fn source_image() -> Value {
        use base64::{engine::general_purpose::STANDARD, Engine as _};
        use sha2::{Digest, Sha256};
        fn chunk(bytes: &mut Vec<u8>, kind: &[u8;4], data: &[u8]) {
            bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
            let start = bytes.len(); bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
            let mut crc = u32::MAX;
            for byte in &bytes[start..] { crc ^= *byte as u32; for _ in 0..8 { crc = (crc >> 1) ^ (0xedb88320 & (0_u32.wrapping_sub(crc & 1))); } }
            bytes.extend_from_slice(&(!crc).to_be_bytes());
        }
        let raw = vec![0_u8; (32 * 3 + 1) * 16]; let length = raw.len() as u16;
        let mut deflate = vec![0x78,0x01,0x01]; deflate.extend_from_slice(&length.to_le_bytes());
        deflate.extend_from_slice(&(!length).to_le_bytes()); deflate.extend_from_slice(&raw);
        let (mut a, mut b) = (1_u32,0_u32); for byte in raw { a = (a + byte as u32) % 65521; b = (b + a) % 65521; }
        deflate.extend_from_slice(&((b << 16) | a).to_be_bytes());
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec(); let mut header = Vec::new();
        header.extend_from_slice(&32_u32.to_be_bytes()); header.extend_from_slice(&16_u32.to_be_bytes()); header.extend_from_slice(&[8,2,0,0,0]);
        chunk(&mut bytes,b"IHDR",&header); chunk(&mut bytes,b"IDAT",&deflate); chunk(&mut bytes,b"IEND",&[]);
        json!({"mime":"image/png","width":32,"height":16,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(&bytes)})
    }
    fn catalog() -> (Value,Value) {
        let mut r = request("face"); r["request_id"] = json!("catalog"); r["action"] = json!("skin_reference_match_catalog"); r["payload"] = json!({});
        let base = payload(&request("face"));
        let p = json!({"kind":"skin_reference_match_catalog","version":1,"operation_id":FACE_OP,"scope":"current-photo-face-only",
            "source":base["source"],"source_proof":base["source_proof"],"document_id":"doc","revision":"4",
            "source_image":source_image(),"source_review_sha256":h('b'),
            "faces":[{"face_ref":reference("a"),"box":[0.0,0.0,0.5,1.0],"enabled":true,"available":true,"reason":null,"amount":0.0},
                {"face_ref":reference("b"),"box":[0.5,0.0,1.0,1.0],"enabled":true,"available":true,"reason":null,"amount":0.0}],
            "current":{"version":1,"operation_id":FACE_OP,"reference_face_ref":null,"target_face_refs":[],"amounts":[],"bank_sha256":h('7')},
            "body_matching":false,"automatic_reference":false,"skin_reference_match_available":true,"skin_reference_match_reason":null});
        let result = json!({"event":"people_result","protocol":1,"action":r["action"],"request_id":r["request_id"],"document_id":"doc",
            "skin_reference_match_request":super::super::skin_reference_match::binding(&r).unwrap().unwrap()[super::super::skin_reference_match::MARKER],
            "success":true,"outcome_unknown":false,"error":null,"created_id":null,"batch_id":null,"frame_emitted":false,"payload":p});
        (r,result)
    }
    struct Kind;
    impl ReceiptKind for Kind {
        const NAME: &'static str = "people";
        const ACTIONS: &'static [&'static str] = &[ACTION,"skin_reference_match_catalog"];
        fn valid(v: &Value, document: Option<&str>) -> bool {
            v["document_id"].as_str() == document && receipt(v) && super::super::skin_reference_match::receipt(v)
        }
        fn decorate_failure(v: &mut Value, document: Option<&str>) { v["protocol"] = json!(1); v["document_id"] = json!(document); }
    }
    #[test]
    fn same_ledger_retains_family_source_and_reconciles_only_exact_late_read() {
        let mut host = ReceiptHost::<Kind>::default(); let epoch = [91;16]; host.reset(epoch); host.ready(epoch,true);
        let r = request("face"); assert!(host.begin_command(epoch,&r).is_err());
        let (cr,cv) = catalog(); assert!(super::super::skin_reference_match::receipt(&cv));
        host.begin_command(epoch,&cr).unwrap(); host.receive(epoch,&cv);
        assert!(source_catalog_binding(&request("body"),&cv).is_none());
        let compact = source_catalog_binding(&r,&cv).unwrap(); assert!(compact.get("source_image").is_none());
        let mut stale = r.clone(); stale["state_revision"] = json!(4); assert!(host.begin_command(epoch,&stale).is_err());
        host.begin_command(epoch,&r).unwrap(); host.failed("choice-fixture","transport lost during read");
        assert_eq!(host.status("choice-fixture")["result"]["outcome_unknown"],true);
        let mut terminal = result(&r); terminal["payload"]["source_image_sha256"] = cv["payload"]["source_image"]["sha256"].clone();
        let mut foreign = terminal.clone(); foreign[MARKER]["document_epoch"] = json!("another-epoch"); host.receive(epoch,&foreign);
        assert_eq!(host.status("choice-fixture")["result"]["outcome_unknown"],true);
        foreign = terminal.clone(); foreign["payload"]["source_image_sha256"] = json!(h('9')); host.receive(epoch,&foreign);
        assert_eq!(host.status("choice-fixture")["result"]["outcome_unknown"],true);
        host.receive([92;16],&terminal); assert_eq!(host.status("choice-fixture")["result"]["outcome_unknown"],true);
        host.receive(epoch,&terminal); assert_eq!(host.status("choice-fixture")["result"],terminal);
        foreign = terminal.clone(); foreign["payload"]["graph_sha256"] = json!(h('9')); host.receive(epoch,&foreign);
        assert_eq!(host.status("choice-fixture")["result"],terminal);
        let mut missing = terminal.clone(); missing["payload"]["proposal"]["candidates"].as_array_mut().unwrap().pop();
        assert!(!matches_source_catalog(&compact,&missing));
        let mut disabled = compact; disabled["faces"][0]["enabled"] = json!(false);
        assert!(!matches_source_catalog(&disabled,&terminal));
    }
}
