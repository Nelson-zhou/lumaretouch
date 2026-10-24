//! Torso scalar transfer is a separate, target-owned, frozen review family.
//! PNG framing and digest validation are not a renderer or browser acceptance test.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use sha2::{Digest, Sha256};
pub(crate) use crate::original_shadow_transfer_protocol::{hex, revision, source_proof};

pub(crate) const TORSO_OP: &str = "lnx.torso_length.v1";
pub(crate) const MAX_TARGETS: usize = 8;
const MAX_BASE64: usize = 200_000;
const MAX_PNG_BYTES: usize = 150_000;
const PREVIEW_EDGE: u64 = 256;
fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|name| map.contains_key(*name)))
}
fn text(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128 && !s.chars().any(|c| c.is_control()))
}
fn ref_id(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.:-".contains(&b)))
}
fn safe_revision(value: &Value) -> bool { value.as_u64().is_some_and(|n| n <= 9_007_199_254_740_991) }
pub(crate) fn parameters(value: &Value) -> bool {
    fields(value, &["version", "amount"]) && value["version"].as_u64() == Some(1)
        && value["amount"].as_f64().is_some_and(|n| n.is_finite() && (-1.0..=1.0).contains(&n))
}
fn size(value: &Value) -> Option<(u64, u64)> {
    let dimensions = value.as_array()?;
    if dimensions.len() != 2 { return None; }
    let (width, height) = (dimensions[0].as_u64()?, dimensions[1].as_u64()?);
    (width > 0 && height > 0 && width <= u32::MAX as u64 && height <= u32::MAX as u64).then_some((width, height))
}
fn body_ref(value: &Value, asset: &Value) -> bool {
    fields(value, &["asset_sha256", "body_instance_id", "analysis_revision"])
        && hex(&value["asset_sha256"], 64) && &value["asset_sha256"] == asset
        && ref_id(&value["body_instance_id"]) && safe_revision(&value["analysis_revision"])
}
fn face_binding(value: &Value, asset: &Value) -> bool {
    if !fields(value, &["associated_face_ref", "associated_face_box", "associated_face_evidence_sha256"])
        || !hex(&value["associated_face_evidence_sha256"], 64) { return false; }
    let face = &value["associated_face_ref"];
    let Some(b) = value["associated_face_box"].as_array() else { return false; };
    fields(face, &["asset_sha256", "face_instance_id", "analysis_revision"])
        && hex(&face["asset_sha256"], 64) && &face["asset_sha256"] == asset
        && ref_id(&face["face_instance_id"]) && safe_revision(&face["analysis_revision"])
        && b.len() == 4 && b.iter().all(|n| n.as_f64().is_some_and(|n| n.is_finite() && n > 0.0 && n < 1.0))
        && b[0].as_f64() < b[2].as_f64() && b[1].as_f64() < b[3].as_f64()
}
/// Shape only. The engine matches these exact ordered PNG hashes to its frozen record.
pub(crate) fn acknowledgments(value: &Value) -> bool {
    let Some(items) = value.as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    items.len() <= MAX_TARGETS && items.iter().all(|item|
        fields(item, &["document_id", "revision", "before_sha256", "after_sha256"])
        && text(&item["document_id"]) && revision(&item["revision"])
        && hex(&item["before_sha256"], 64) && hex(&item["after_sha256"], 64)
        && seen.insert(item["document_id"].as_str().unwrap()))
}
pub(crate) fn command(value: &Value) -> Result<(), String> {
    scalar_command(value, TORSO_OP, "torso_review_ack")
}
/// Shared validation is not a shared receipt family: scope and acknowledgment keys stay exact.
pub(crate) fn scalar_command(value: &Value, operation: &str, ack_key: &str) -> Result<(), String> {
    let selected = value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == operation));
    let conflicting = ["people_transfer", "local_mask_transfer", "reference_color", "spill_review_ack", "shadow_review_ack", "torso_review_ack", "waist_review_ack", "xmp_ack", "xmp_review_ack"]
        .iter().any(|key| *key != ack_key && value.get(*key).is_some());
    if selected && (value["module_scope"].as_array().map_or(true, |ops| ops.len() != 1) || conflicting) {
        return Err(format!("{operation} scalar transfer requires its own scope and never creates body ownership"));
    }
    let Some(ack) = value.get(ack_key) else { return Ok(()); };
    if (value.get("module_scope").is_some() && !selected) || conflicting {
        return Err(format!("{operation} review cannot be combined with another transfer or acknowledgment family"));
    }
    let preset = value["cmd"] == "preset" && value["action"] == "apply";
    let batch = value["cmd"] == "batch" && value["action"] == "commit";
    if (!preset && !batch) || !acknowledgments(ack) || !text(&value["request_id"])
        || !hex(&value["preflight_token"], 32)
        || (preset && (!text(&value["document_id"]) || ack.as_array().map_or(true, |items| items.len() != 1 || items[0]["document_id"] != value["document_id"]))) {
        return Err(format!("{operation} application needs one exact frozen PNG-pair acknowledgment per eligible target"));
    }
    Ok(())
}
fn number(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_be_bytes(bytes.get(offset..offset.checked_add(4)?)?.try_into().ok()?))
}
fn crc32(bytes: &[u8]) -> u32 {
    static TABLE: std::sync::OnceLock<[u32; 256]> = std::sync::OnceLock::new();
    let table = TABLE.get_or_init(|| std::array::from_fn(|index| {
        let mut value = index as u32;
        for _ in 0..8 { value = if value & 1 == 0 { value >> 1 } else { (value >> 1) ^ 0xedb88320 }; }
        value
    }));
    let mut value = u32::MAX;
    for byte in bytes { value = table[((value ^ u32::from(*byte)) & 255) as usize] ^ (value >> 8); }
    !value
}
fn png(bytes: &[u8], width: u32, height: u32) -> bool {
    if bytes.get(..8) != Some(b"\x89PNG\r\n\x1a\n".as_slice()) { return false; }
    let mut offset = 8usize;
    let mut image_data = false;
    let mut data_ended = false;
    while offset < bytes.len() {
        let Some(length) = number(bytes, offset) else { return false; };
        let Some(end) = offset.checked_add(12).and_then(|n| n.checked_add(length as usize)) else { return false; };
        if end > bytes.len() || number(bytes, end - 4) != Some(crc32(&bytes[offset + 4..end - 4])) { return false; }
        let kind = &bytes[offset + 4..offset + 8];
        if !kind.iter().all(u8::is_ascii_alphabetic) || !kind[2].is_ascii_uppercase() { return false; }
        if offset == 8 {
            if kind != b"IHDR" || length != 13 || number(bytes, offset + 8) != Some(width) || number(bytes, offset + 12) != Some(height)
                || bytes[offset + 16] != 8 || ![2, 6].contains(&bytes[offset + 17]) || bytes[offset + 18..offset + 21] != [0, 0, 0] { return false; }
        } else if kind == b"IHDR" { return false; }
        else if kind == b"IDAT" { if data_ended || length == 0 { return false; } image_data = true; }
        else if kind == b"IEND" { return length == 0 && image_data && end == bytes.len(); }
        else {
            if !kind[0].is_ascii_lowercase() || kind == b"acTL" || kind == b"fcTL" || kind == b"fdAT" { return false; }
            if image_data { data_ended = true; }
        }
        offset = end;
    }
    false
}
fn preview(value: &Value, output: (u64, u64)) -> bool {
    if !fields(value, &["mime", "width", "height", "sha256", "base64"])
        || value["mime"] != "image/png" || !hex(&value["sha256"], 64) { return false; }
    let (Some(width), Some(height), Some(encoded)) = (value["width"].as_u64(), value["height"].as_u64(), value["base64"].as_str()) else { return false; };
    if !(1..=PREVIEW_EDGE).contains(&width) || !(1..=PREVIEW_EDGE).contains(&height)
        || width > output.0 || height > output.1 || (width * output.1).abs_diff(height * output.0) > output.0.max(output.1)
        || encoded.is_empty() || encoded.len() > MAX_BASE64 || encoded.len() % 4 != 0 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    if bytes.len() > MAX_PNG_BYTES || STANDARD.encode(&bytes) != encoded || !png(&bytes, width as u32, height as u32) { return false; }
    format!("{:x}", Sha256::digest(&bytes)) == value["sha256"].as_str().unwrap()
}
pub(crate) fn transfer(value: &Value, document: &Value, rev: &Value, params: &Value, source: &Value) -> bool {
    if !fields(value, &["version", "document_id", "revision", "source_proof", "before_sha256", "candidate_sha256", "before_people_sha256", "candidate_people_sha256",
        "source_size", "before_output_size", "after_output_size", "parameters", "body_ref", "associated_face", "body_support_sha256", "body_review_sha256", "before_bank_sha256", "candidate_bank_sha256", "before", "after"])
        || value["version"].as_u64() != Some(1) || !text(document) || &value["document_id"] != document
        || !revision(rev) || &value["revision"] != rev || !parameters(params) || &value["parameters"] != params
        || !source_proof(source) || &value["source_proof"] != source
        || !body_ref(&value["body_ref"], &source["asset_sha256"]) || !face_binding(&value["associated_face"], &source["asset_sha256"])
        || !["before_sha256", "candidate_sha256", "before_people_sha256", "candidate_people_sha256", "body_support_sha256", "body_review_sha256", "before_bank_sha256", "candidate_bank_sha256"].iter().all(|key| hex(&value[*key], 64)) { return false; }
    let (Some(source_size), Some(before_size), Some(after_size)) = (size(&value["source_size"]), size(&value["before_output_size"]), size(&value["after_output_size"])) else { return false; };
    let creative = &source["creative_source"];
    (creative.is_null() || (creative["width"].as_u64() == Some(source_size.0) && creative["height"].as_u64() == Some(source_size.1)))
        && preview(&value["before"], before_size) && preview(&value["after"], after_size)
}
// AUTHORED / UNRUN: protocol fixtures only, not product acceptance.
#[cfg(test)]
#[path = "torso_transfer_protocol_tests.rs"]
pub(crate) mod tests;
