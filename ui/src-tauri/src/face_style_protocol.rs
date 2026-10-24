//! Bounded face-style review transport. Source-only implementation; fixtures UNRUN.
//! This validates identity and PNG framing, not the quality of a face solver.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, source_proof};
const STYLES: &[&str] = &["classic", "youthful", "bold", "youth", "round", "long", "square"];
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
fn fields(v: &Value, names: &[&str]) -> bool {
    v.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|k| m.contains_key(*k)))
}
pub(crate) fn action(v: &Value) -> bool {
    matches!(v["action"].as_str(), Some("face_style_catalog" | "face_style_preview" | "face_style_image" | "face_style_confirm"))
}
fn recipe(v: &Value) -> bool {
    fields(v, &["version", "style", "amount"]) && v["version"].as_u64() == Some(1)
        && v["style"].as_str().is_some_and(|s| STYLES.contains(&s))
        && v["amount"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n))
}
fn ack(v: &Value) -> bool {
    fields(v, &["review_sha256", "before_sha256", "after_sha256"])
        && ["review_sha256", "before_sha256", "after_sha256"].iter().all(|k| hex(&v[*k], 64))
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let mut context = json!({});
    for k in CONTEXT { context[*k] = v[*k].clone(); }
    let p = &v["payload"];
    let valid = super::valid_context(&context) && v["target"]["scope"] == "face" && match v["action"].as_str() {
        Some("face_style_catalog") => fields(p, &[]),
        Some("face_style_preview") => recipe(p),
        Some("face_style_image") => fields(p, &["token", "side", "sha256"]) && hex(&p["token"], 32)
            && matches!(p["side"].as_str(), Some("before" | "after")) && hex(&p["sha256"], 64),
        Some("face_style_confirm") => fields(p, &["token", "ack"]) && hex(&p["token"], 32) && ack(&p["ack"]),
        _ => false,
    };
    if valid { Ok(()) } else { Err("新版脸型请求需要精确单脸、版本和冻结预览凭据".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>, String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?;
    let mut request = json!({"action":v["action"], "payload":v["payload"]});
    for k in CONTEXT { request[*k] = v[*k].clone(); }
    Ok(Some(json!({"face_style_request":request})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(), Some("face_style_catalog" | "face_style_preview" | "face_style_image"))
        && command(v).is_ok() && v.as_object().is_some_and(|m| m.len() == 10
            || (m.len() == 11 && hex(&v["host_epoch"], 32)))
        && v["request_id"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128)
}
fn size(v: &Value) -> Option<(u64, u64)> {
    let a = v.as_array()?;
    if a.len() != 2 { return None; }
    let (w, h) = (a[0].as_u64()?, a[1].as_u64()?);
    (w > 0 && h > 0 && w <= u32::MAX as u64 && h <= u32::MAX as u64).then_some((w, h))
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
fn image(v: &Value) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    if !fields(v, &["mime", "width", "height", "sha256", "base64"]) || v["mime"] != "image/png" || !hex(&v["sha256"], 64) { return false; }
    let (Some(w), Some(h), Some(encoded)) = (v["width"].as_u64(), v["height"].as_u64(), v["base64"].as_str()) else { return false; };
    if !(1..=1024).contains(&w) || !(1..=1024).contains(&h) || encoded.is_empty() || encoded.len() > 5_592_408 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= 4 * 1024 * 1024 && STANDARD.encode(&bytes) == encoded
        && crate::torso_transfer_protocol::png(&bytes, w as u32, h as u32)
        && format!("{:x}", Sha256::digest(&bytes)) == v["sha256"].as_str().unwrap()
}
fn visual(v: &Value, owner: &Value) -> bool {
    if !fields(v, &["version", "document_id", "revision", "source_proof", "before_state_sha256", "candidate_state_sha256",
        "before_people_sha256", "candidate_people_sha256", "source_size", "before_output_size", "after_output_size", "before", "after"])
        || v["version"].as_u64() != Some(1) || v["document_id"] != owner["document"]["document_id"]
        || v["revision"].as_str() != owner["document"]["revision"].as_u64().map(|n| n.to_string()).as_deref()
        || v["source_proof"] != owner["source_proof"] || !source_proof(&v["source_proof"])
        || ["before_state_sha256", "candidate_state_sha256", "before_people_sha256", "candidate_people_sha256"].iter().any(|k| !hex(&v[*k], 64)) { return false; }
    let (Some(source), Some(before), Some(after)) = (size(&v["source_size"]), size(&v["before_output_size"]), size(&v["after_output_size"])) else { return false; };
    let derived = &v["source_proof"]["creative_source"];
    (derived.is_null() || (derived["width"].as_u64() == Some(source.0) && derived["height"].as_u64() == Some(source.1)))
        && compact(&v["before"], before) && compact(&v["after"], after)
}
fn review(v: &Value, request: &Value) -> bool {
    let o = &v["owner"];
    fields(v, &["version", "token", "recipe", "owner", "face_ref", "patches_sha256", "visual", "review_sha256"])
        && v["version"].as_u64() == Some(1) && hex(&v["token"], 32) && recipe(&v["recipe"])
        && v["recipe"] == request["payload"] && hex(&v["patches_sha256"], 64) && hex(&v["review_sha256"], 64)
        && fields(o, &["document", "people_scope", "state_revision", "association_revision", "graph_sha256", "source_proof"])
        && fields(&o["document"], &["document_id", "epoch", "revision"])
        && o["document"]["document_id"] == request["document_id"] && o["document"]["epoch"] == request["document_epoch"]
        && o["document"]["revision"] == request["document_revision"] && o["state_revision"] == request["state_revision"]
        && o["association_revision"] == request["association_revision"] && hex(&o["graph_sha256"], 64)
        && (o["people_scope"] == "project" || o["people_scope"] == request["document_id"])
        && v["face_ref"] == request["target"]["face_ref"] && o["source_proof"]["asset_sha256"] == v["face_ref"]["asset_sha256"]
        && visual(&v["visual"], o)
}
fn catalogue(v: &Value) -> bool {
    const OPS: &[&str] = &["lnx.face_contour.v1", "lnx.face_size.v1", "lnx.mid_face.v1", "lnx.lower_face.v1", "lnx.chin_shape.v1",
        "lnx.chin_length.v1", "lnx.brow_shape.v1", "lnx.eye_shape.v1", "lnx.nose_shape.v1", "lnx.mouth_shape.v1"];
    if !fields(v, &["version", "binding_version", "family_control_id", "amount_control_id", "amount_min", "amount_max",
        "coefficient_limit", "origin", "owned_operation_ids", "owned_parameters", "styles"])
        || v["version"].as_u64() != Some(1) || v["binding_version"].as_u64() != Some(1)
        || v["family_control_id"] != "PC-32466-C-3b31aac970" || v["amount_control_id"] != "PC-32466-C-6c86bf2c55"
        || v["amount_min"].as_f64() != Some(0.0) || v["amount_max"].as_f64() != Some(1.0)
        || v["coefficient_limit"].as_f64() != Some(0.30) || v["origin"] != "original-local-composition-not-vendor-calibration"
        || v["owned_operation_ids"] != json!(OPS) || !fields(&v["owned_parameters"], OPS) { return false; }
    if !OPS.iter().all(|op| v["owned_parameters"][*op].as_array().is_some_and(|paths|
        !paths.is_empty() && paths.len() <= 10 && paths.iter().all(|p| p.as_str().is_some_and(|s| s.starts_with('/') && s.len() <= 64))
            && paths.iter().enumerate().all(|(i, p)| !paths[..i].contains(p)))) { return false; }
    let Some(rows) = v["styles"].as_array() else { return false; };
    rows.len() == STYLES.len() && rows.iter().zip(STYLES).all(|(row, id)|
        fields(row, &["id", "label", "control_id", "intent", "version", "binding_version", "owned_operation_ids"])
        && row["id"].as_str() == Some(*id) && row["version"].as_u64() == Some(1) && row["binding_version"].as_u64() == Some(1)
        && ["label", "control_id", "intent"].iter().all(|k| row[*k].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 256))
        && row["owned_operation_ids"] == json!(OPS))
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) { return true; }
    let r = &v["face_style_request"];
    if !fields(r, &["action", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target", "payload"])
        || command(r).is_err() || r["action"] != v["action"] || r["document_id"] != v["document_id"] { return false; }
    if v["success"] != true { return true; }
    let p = &v["payload"];
    match v["action"].as_str() {
        Some("face_style_catalog") => p["kind"] == "face_style_catalog" && fields(p, &["kind", "catalogue"])
            && catalogue(&p["catalogue"]),
        Some("face_style_preview") => fields(p, &["kind", "review"]) && p["kind"] == "face_style_preview" && review(&p["review"], r),
        Some("face_style_image") => fields(p, &["kind", "token", "side", "sha256", "review_sha256", "image"])
            && p["kind"] == "face_style_image" && p["token"] == r["payload"]["token"] && p["side"] == r["payload"]["side"]
            && p["sha256"] == r["payload"]["sha256"] && p["sha256"] == p["image"]["sha256"] && hex(&p["review_sha256"], 64) && image(&p["image"]),
        Some("face_style_confirm") => fields(p, &["kind", "token", "review_sha256", "ack", "recipe", "patches_sha256"])
            && p["kind"] == "face_style_confirm" && p["token"] == r["payload"]["token"] && p["ack"] == r["payload"]["ack"]
            && p["review_sha256"] == p["ack"]["review_sha256"] && recipe(&p["recipe"]) && hex(&p["patches_sha256"], 64),
        _ => false,
    }
}
#[cfg(test)]
#[path = "face_style_protocol_tests.rs"]
mod tests;
