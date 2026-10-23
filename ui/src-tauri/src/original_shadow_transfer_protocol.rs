//! Dedicated scalar original-shadow transfer evidence, shared by batch and preset hosts.
//! PNG framing, dimensions and digest are verified here; the WebView still must
//! decode both images before acknowledging them. This is not a render validator.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub(crate) const SHADOW_OP: &str = "lnx.original_shadow.v1";
pub(crate) const MAX_TARGETS: usize = 8;
const MAX_BASE64: usize = 200_000;
const MAX_PNG_BYTES: usize = 150_000;
const PREVIEW_EDGE: u64 = 256;

fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|name| map.contains_key(*name)))
}
fn text(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128 && !s.contains('\0'))
}
pub(crate) fn hex(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|s| s.len() == length && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
pub(crate) fn revision(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 20
        && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok_and(|n| n.to_string() == s))
}
pub(crate) fn parameters(value: &Value) -> bool {
    fields(value, &["enabled", "strength", "blend"]) && value["enabled"].is_boolean()
        && value["strength"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n))
        && matches!(value["blend"].as_str(), Some("normal" | "multiply" | "softlight"))
}
fn size(value: &Value) -> Option<(u64, u64)> {
    let dimensions = value.as_array()?;
    if dimensions.len() != 2 { return None; }
    let (width, height) = (dimensions[0].as_u64()?, dimensions[1].as_u64()?);
    (width > 0 && height > 0 && width <= u32::MAX as u64 && height <= u32::MAX as u64).then_some((width, height))
}
pub(crate) fn source_proof(value: &Value) -> bool {
    if !fields(value, &["asset_sha256", "original_sha256", "creative_source"])
        || !hex(&value["asset_sha256"], 64) || !hex(&value["original_sha256"], 64) { return false; }
    let creative = &value["creative_source"];
    if creative.is_null() { return value["asset_sha256"] == value["original_sha256"]; }
    fields(creative, &["sha256", "width", "height"]) && creative["sha256"] == value["asset_sha256"]
        && ["width", "height"].iter().all(|key| creative[*key].as_u64().is_some_and(|n| n > 0 && n <= u32::MAX as u64))
}

/// Only the frozen committing action can carry an acknowledgment. Its images
/// are matched to the engine's immutable preflight record there, not inferred
/// from a caller-supplied module list here. An empty batch is a valid no-write.
pub(crate) fn command(value: &Value) -> Result<(), String> {
    let shadow = value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == SHADOW_OP));
    if shadow && value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == "lnx.id_background.v1" || op == "lnx.spill_removal.v1")) {
        return Err("original-shadow scalar transfer cannot combine with whole-ID or spill transfer".into());
    }
    let Some(ack) = value.get("shadow_review_ack") else { return Ok(()); };
    if value.get("spill_review_ack").is_some() { return Err("independent shadow and spill acknowledgments cannot be combined".into()); }
    let preset = value["cmd"] == "preset" && value["action"] == "apply";
    let batch = value["cmd"] == "batch" && value["action"] == "commit";
    let Some(items) = ack.as_array() else { return Err("original-shadow review acknowledgment must be an exact bounded array".into()); };
    if (!preset && !batch) || items.len() > MAX_TARGETS || !text(&value["request_id"])
        || !hex(&value["preflight_token"], 32)
        || (preset && (items.len() != 1 || !text(&value["document_id"]))) {
        return Err("original-shadow application needs a correlated frozen target review".into());
    }
    let mut seen = std::collections::BTreeSet::new();
    for item in items {
        if !fields(item, &["document_id", "revision", "before_sha256", "after_sha256"])
            || !text(&item["document_id"]) || !revision(&item["revision"])
            || !hex(&item["before_sha256"], 64) || !hex(&item["after_sha256"], 64)
            || !seen.insert(item["document_id"].as_str().unwrap())
            || (preset && item["document_id"] != value["document_id"]) {
            return Err("original-shadow acknowledgment does not identify one exact target image pair".into());
        }
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
            // The full-target renderer emits display-only RGB8 PNGs; accepting
            // RGBA8 also preserves a valid bounded transparency representation.
            if kind != b"IHDR" || length != 13 || number(bytes, offset + 8) != Some(width)
                || number(bytes, offset + 12) != Some(height) || bytes[offset + 16] != 8
                || ![2, 6].contains(&bytes[offset + 17]) || bytes[offset + 18..offset + 21] != [0, 0, 0] { return false; }
        } else if kind == b"IDAT" {
            if data_ended { return false; }
            image_data |= length > 0;
        } else if kind == b"IEND" { return length == 0 && image_data && end == bytes.len(); }
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
        || width > output.0 || height > output.1
        || (width * output.1).abs_diff(height * output.0) > output.0.max(output.1)
        || encoded.is_empty() || encoded.len() > MAX_BASE64 || encoded.len() % 4 != 0 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    if bytes.len() > MAX_PNG_BYTES || STANDARD.encode(&bytes) != encoded
        || !png(&bytes, width as u32, height as u32) { return false; }
    format!("{:x}", Sha256::digest(&bytes)) == value["sha256"].as_str().unwrap()
}

pub(crate) fn transfer(value: &Value, document: &Value, rev: &Value, params: &Value, source: &Value) -> bool {
    if !fields(value, &["version", "document_id", "revision", "source_proof", "before_sha256", "candidate_sha256",
        "before_people_sha256", "candidate_people_sha256", "source_size", "before_output_size", "after_output_size", "parameters", "before", "after"])
        || value["version"].as_u64() != Some(1) || !text(document) || &value["document_id"] != document
        || !revision(rev) || &value["revision"] != rev || !parameters(params) || &value["parameters"] != params
        || !source_proof(source) || &value["source_proof"] != source
        || !["before_sha256", "candidate_sha256", "before_people_sha256", "candidate_people_sha256"].iter().all(|key| hex(&value[*key], 64)) { return false; }
    let (Some(source_size), Some(before_size), Some(after_size)) = (size(&value["source_size"]), size(&value["before_output_size"]), size(&value["after_output_size"])) else { return false; };
    let creative = &source["creative_source"];
    (creative.is_null() || (creative["width"].as_u64() == Some(source_size.0) && creative["height"].as_u64() == Some(source_size.1)))
        && preview(&value["before"], before_size) && preview(&value["after"], after_size)
}

// AUTHORED / UNRUN: protocol specifications, not rendered-product acceptance.
#[cfg(test)]
#[path = "original_shadow_transfer_protocol_tests.rs"]
pub(crate) mod tests;
