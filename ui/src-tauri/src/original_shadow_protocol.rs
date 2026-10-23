//! Dedicated reviewed photographed-shadow protocol. This is not a spill request.
//! The engine renders complete source-owned candidates before making display
//! PNGs; the WebView must additionally decode and show both images to the user.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub(super) const MAX_REVIEW_BYTES: usize = 4 * 1024 * 1024;
const MAX_PNG_BYTES: usize = 1024 * 1024;
const MAX_BASE64: usize = ((MAX_PNG_BYTES + 2) / 3) * 4;
const PREVIEW_EDGE: u64 = 512;

fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|name| map.contains_key(*name)))
}
fn text(value: &Value, max: usize) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max && !s.contains('\0'))
}
fn hexadecimal(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|s| s.len() == length && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn token(value: &Value) -> bool {
    hexadecimal(value, 32) && value.as_str().is_some_and(|s| s.bytes().any(|b| b != b'0'))
}
fn hash(value: &Value) -> bool { hexadecimal(value, 64) }
fn revision(value: &Value) -> Option<u64> {
    let s = value.as_str()?;
    if s.is_empty() || s.len() > 20 || (s.len() > 1 && s.starts_with('0')) || !s.bytes().all(|b| b.is_ascii_digit()) { return None; }
    s.parse().ok()
}
fn object_id(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))
}
fn selection(value: &Value) -> bool {
    if value.is_null() { return true; }
    value.as_array().is_some_and(|ids| !ids.is_empty() && ids.len() <= 64 && ids.iter().all(object_id)
        && ids.iter().filter_map(Value::as_str).collect::<std::collections::BTreeSet<_>>().len() == ids.len())
}
pub(super) fn is_shadow(value: &Value) -> bool {
    matches!(value["action"].as_str(), Some("id_original_shadow_preview" | "id_original_shadow_apply"))
}
pub(super) fn command(value: &Value) -> Result<(), String> {
    if !is_shadow(value) { return Ok(()); }
    if value["cmd"] != "background" || !text(&value["request_id"], 128) || !text(&value["document_id"], 256)
        || !text(&value["recipe_document_id"], 256) || revision(&value["recipe_revision"]).is_none() {
        return Err("原阴影请求缺少当前照片与配方版本".into());
    }
    if value["action"] == "id_original_shadow_preview" {
        if !fields(value, &["cmd", "action", "request_id", "document_id", "recipe_document_id", "recipe_revision",
            "parameters", "lit_ids", "retention_ids", "samples_reviewed", "uniform_floor_confirmed"])
            || !fields(&value["parameters"], &["enabled", "strength", "blend"])
            || !value["parameters"]["enabled"].is_boolean()
            || !value["parameters"]["strength"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n))
            || !matches!(value["parameters"]["blend"].as_str(), Some("normal" | "multiply" | "softlight"))
            || !value["samples_reviewed"].is_boolean() || !value["uniform_floor_confirmed"].is_boolean()
            || !selection(&value["lit_ids"]) || !selection(&value["retention_ids"])
            || value["samples_reviewed"].as_bool() != Some(!value["lit_ids"].is_null() || !value["retention_ids"].is_null())
            || (value["parameters"]["enabled"] == true && value["uniform_floor_confirmed"] != true) {
            return Err("原阴影仅接受有界参数、独立审核的地面/保留范围和均匀漫反射地面确认".into());
        }
    } else if !fields(value, &["cmd", "action", "request_id", "document_id", "recipe_document_id", "recipe_revision",
        "token", "reviewed", "before_sha256", "after_sha256"])
        || !token(&value["token"]) || value["reviewed"] != true || !hash(&value["before_sha256"]) || !hash(&value["after_sha256"]) {
        return Err("原阴影应用必须包含本次冻结审核与真实前后 PNG 摘要".into());
    }
    Ok(())
}

// Same framing policy as the existing bounded transfer protocol, isolated here
// so adding this feature does not change legacy spill receipt admission.
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
    let mut seen_data = false;
    let mut data_ended = false;
    while offset < bytes.len() {
        let Some(length) = number(bytes, offset) else { return false; };
        let Some(end) = offset.checked_add(12).and_then(|n| n.checked_add(length as usize)) else { return false; };
        if end > bytes.len() || number(bytes, end - 4) != Some(crc32(&bytes[offset + 4..end - 4])) { return false; }
        let kind = &bytes[offset + 4..offset + 8];
        if !kind.iter().all(u8::is_ascii_alphabetic) || !kind[2].is_ascii_uppercase() { return false; }
        if offset == 8 {
            if kind != b"IHDR" || length != 13 || number(bytes, offset + 8) != Some(width)
                || number(bytes, offset + 12) != Some(height) || bytes[offset + 16] != 8
                || ![2, 6].contains(&bytes[offset + 17]) || bytes[offset + 18..offset + 21] != [0, 0, 0] { return false; }
        } else if kind == b"IDAT" {
            if data_ended { return false; }
            seen_data = true;
            image_data |= length > 0;
        } else if kind == b"IEND" { return length == 0 && image_data && end == bytes.len(); }
        else {
            if !kind[0].is_ascii_lowercase() || kind == b"acTL" || kind == b"fcTL" || kind == b"fdAT" { return false; }
            if seen_data { data_ended = true; }
        }
        offset = end;
    }
    false
}
fn image(value: &Value) -> bool {
    if !fields(value, &["mime", "width", "height", "sha256", "base64"])
        || value["mime"] != "image/png" || !hash(&value["sha256"]) { return false; }
    let (Some(width), Some(height), Some(encoded)) = (value["width"].as_u64(), value["height"].as_u64(), value["base64"].as_str()) else { return false; };
    if !(1..=PREVIEW_EDGE).contains(&width) || !(1..=PREVIEW_EDGE).contains(&height)
        || encoded.is_empty() || encoded.len() > MAX_BASE64 || encoded.len() % 4 != 0 { return false; }
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    bytes.len() <= MAX_PNG_BYTES && STANDARD.encode(&bytes) == encoded && png(&bytes, width as u32, height as u32)
        && format!("{:x}", Sha256::digest(&bytes)) == value["sha256"].as_str().unwrap_or_default()
}
fn review(value: &Value, request: &Value) -> bool {
    fields(value, &["version", "token", "recipe_document_id", "recipe_revision", "source", "candidate_sha256", "before", "after", "boundaries"])
        && value["version"].as_u64() == Some(1) && token(&value["token"])
        && value["recipe_document_id"] == request["recipe_document_id"] && value["recipe_revision"] == request["recipe_revision"]
        && hash(&value["candidate_sha256"]) && fields(&value["source"], &["sha256", "width", "height"])
        && hash(&value["source"]["sha256"])
        && ["width", "height"].iter().all(|key| value["source"][*key].as_u64().is_some_and(|n| (1..=1000000).contains(&n)))
        // Full completed output includes crop/rotation, so its aspect is not
        // required to equal the immutable pre-edit source extent.
        && value["before"]["width"] == value["after"]["width"] && value["before"]["height"] == value["after"]["height"]
        && image(&value["before"]) && image(&value["after"])
        && value["boundaries"].as_array().is_some_and(|items| items.len() <= 32
            && items.iter().all(|item| item.as_str().is_some_and(|s| s.len() <= 4096 && !s.contains('\0'))))
}
pub(super) fn receipt(value: &Value, request: &Value) -> bool {
    if !is_shadow(request) || command(request).is_err() || value.to_string().len() > MAX_REVIEW_BYTES
        || value["event"] != "id_background_result" || value["protocol"].as_u64() != Some(1)
        || value["action"] != request["action"] || value["request_id"] != request["request_id"] || value["document_id"] != request["document_id"]
        || !value["success"].is_boolean() || !value["outcome_unknown"].is_boolean() || !value["requires_reload"].is_boolean()
        || value.as_object().map_or(true, |map| map.keys().any(|key| !["event", "protocol", "action", "request_id", "document_id",
            "success", "outcome_unknown", "requires_reload", "report", "shadow_review", "history", "error", "replayed", "frame_delivery_unknown"].contains(&key.as_str())))
        || ["replayed", "frame_delivery_unknown"].iter().any(|key| value.get(*key).is_some_and(|v| !v.is_boolean()))
        || value.get("error").is_some_and(|v| !v.as_str().is_some_and(|s| s.len() <= 8192))
        || (value["success"] == true && (value["outcome_unknown"] == true || value["requires_reload"] == true || value.get("error").is_some())) { return false; }
    if value["success"] != true { return value.get("shadow_review").map_or(true, Value::is_null); }
    let report = &value["report"];
    if !report.is_object() || report["recipe_document_id"] != request["recipe_document_id"] { return false; }
    if request["action"] == "id_original_shadow_preview" {
        report["recipe_revision"] == request["recipe_revision"] && value.get("history").is_none()
            && review(&value["shadow_review"], request)
    } else {
        revision(&report["recipe_revision"]).zip(revision(&request["recipe_revision"])).is_some_and(|(after, before)| after >= before)
            && value.get("shadow_review").map_or(true, Value::is_null)
    }
}
pub(super) fn apply_matches(request: &Value, original: &Value, result: &Value) -> bool {
    request["action"] == "id_original_shadow_apply" && command(request).is_ok()
        && original["action"] == "id_original_shadow_preview" && result["success"] == true && receipt(result, original)
        && ["document_id", "recipe_document_id", "recipe_revision"].iter().all(|key| request[*key] == original[*key])
        && request["token"] == result["shadow_review"]["token"]
        && request["before_sha256"] == result["shadow_review"]["before"]["sha256"]
        && request["after_sha256"] == result["shadow_review"]["after"]["sha256"]
}

// AUTHORED / UNRUN. No compilation, tests, inference or image render performed.
#[cfg(test)]
#[path = "original_shadow_protocol_tests.rs"]
pub(super) mod tests;
