//! Spill-only bounded review protocol. Ordinary ID background limits are unchanged.
//! The WebView also hashes decoded bytes and requires both actual image loads.
use serde_json::Value;
pub(super) const MAX_REVIEW_BYTES: usize = 4 * 1024 * 1024;
const MAX_PNG_BYTES: usize = 1024 * 1024;
const MAX_BASE64: usize = ((MAX_PNG_BYTES + 2) / 3) * 4;
fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|map| map.len() == names.len() && names.iter().all(|name| map.contains_key(*name)))
}
fn text(value: &Value, max: usize) -> bool { value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= max && !s.contains('\0')) }
fn hexadecimal(value: &Value, length: usize) -> bool {
    value.as_str().is_some_and(|s| s.len() == length && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}
fn token(value: &Value) -> bool { hexadecimal(value, 32) && value.as_str().is_some_and(|s| s.bytes().any(|b| b != b'0')) }
fn object_id(value: &Value) -> bool {
    value.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'))
}
fn hash(value: &Value) -> bool { hexadecimal(value, 64) }
fn revision(value: &Value) -> Option<u64> {
    let value = value.as_str()?;
    if value.is_empty() || value.len() > 20 || (value.len() > 1 && value.starts_with('0')) || !value.bytes().all(|b| b.is_ascii_digit()) { return None; }
    value.parse().ok()
}
pub(super) fn is_spill(value: &Value) -> bool { matches!(value["action"].as_str(), Some("id_spill_preview" | "id_spill_apply")) }
pub(super) fn command(value: &Value) -> Result<(), String> {
    if !is_spill(value) { return Ok(()); }
    if value["cmd"] != "background" || !text(&value["request_id"], 128) || !text(&value["document_id"], 256)
        || !text(&value["recipe_document_id"], 256) || revision(&value["recipe_revision"]).is_none() {
        return Err("祛染请求缺少当前照片与配方版本".into());
    }
    if value["action"] == "id_spill_preview" {
        if !fields(value, &["cmd", "action", "request_id", "document_id", "recipe_document_id", "recipe_revision", "parameters", "coverage_ids", "coverage_reviewed"])
            || !fields(&value["parameters"], &["enabled", "strength"]) || !value["parameters"]["enabled"].is_boolean()
            || !value["parameters"]["strength"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n))
            || !value["coverage_reviewed"].is_boolean() { return Err("祛染预览参数无效".into()); }
        let ids = &value["coverage_ids"];
        if ids.is_null() {
            if value["coverage_reviewed"] != false { return Err("保留当前覆盖不能伪造新的手工审核".into()); }
        } else {
            let ids = ids.as_array().ok_or("祛染覆盖必须是当前源图对象列表")?;
            if ids.len() > 64 || !ids.iter().all(object_id)
                || ids.iter().filter_map(Value::as_str).collect::<std::collections::BTreeSet<_>>().len() != ids.len()
                || value["coverage_reviewed"].as_bool() != Some(!ids.is_empty()) { return Err("手工祛染覆盖缺少独立审核或含重复对象".into()); }
        }
    } else if !fields(value, &["cmd", "action", "request_id", "document_id", "recipe_document_id", "recipe_revision", "token", "reviewed", "before_sha256", "after_sha256"])
        || !token(&value["token"]) || value["reviewed"] != true || !hash(&value["before_sha256"]) || !hash(&value["after_sha256"]) {
        return Err("祛染应用必须包含本次冻结审核与前后 PNG 摘要".into());
    }
    Ok(())
}
fn digit(byte: u8) -> Option<u8> { match byte {
    b'A'..=b'Z' => Some(byte - b'A'), b'a'..=b'z' => Some(byte - b'a' + 26),
    b'0'..=b'9' => Some(byte - b'0' + 52), b'+' => Some(62), b'/' => Some(63), _ => None,
} }
fn decode(encoded: &str) -> Option<Vec<u8>> {
    if encoded.is_empty() || encoded.len() > MAX_BASE64 || encoded.len() % 4 != 0 { return None; }
    let mut bytes = Vec::with_capacity(encoded.len() / 4 * 3);
    for (index, chunk) in encoded.as_bytes().chunks_exact(4).enumerate() {
        let last = (index + 1) * 4 == encoded.len();
        let (a, b) = (digit(chunk[0])?, digit(chunk[1])?);
        let (c, d, count) = if chunk[2] == b'=' { if !last || chunk[3] != b'=' || b & 15 != 0 { return None; } (0, 0, 1) }
            else if chunk[3] == b'=' { let c = digit(chunk[2])?; if !last || c & 3 != 0 { return None; } (c, 0, 2) }
            else { (digit(chunk[2])?, digit(chunk[3])?, 3) };
        bytes.extend([a << 2 | b >> 4, b << 4 | c >> 2, c << 6 | d].into_iter().take(count));
        if bytes.len() > MAX_PNG_BYTES { return None; }
    }
    Some(bytes)
}
fn number(bytes: &[u8], offset: usize) -> Option<u32> { Some(u32::from_be_bytes(bytes.get(offset..offset + 4)?.try_into().ok()?)) }
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
    let mut offset = 8usize; let mut image_data = false; let mut data_ended = false;
    while offset < bytes.len() {
        let Some(length) = number(bytes, offset) else { return false; };
        let Some(end) = offset.checked_add(12).and_then(|n| n.checked_add(length as usize)) else { return false; };
        if end > bytes.len() || number(bytes, end - 4) != Some(crc32(&bytes[offset + 4..end - 4])) { return false; }
        let kind = &bytes[offset + 4..offset + 8];
        if offset == 8 {
            if kind != b"IHDR" || length != 13 || number(bytes, offset + 8) != Some(width) || number(bytes, offset + 12) != Some(height)
                || bytes[offset + 16] != 8 || ![2, 6].contains(&bytes[offset + 17]) || bytes[offset + 18..offset + 21] != [0, 0, 0] { return false; }
        } else if kind == b"IDAT" {
            if data_ended { return false; } image_data |= length > 0;
        } else if kind == b"IEND" { return length == 0 && image_data && end == bytes.len(); }
        else {
            // Reject repeated/unknown critical chunks and animated PNG. The
            // browser performs actual decompression before the user can agree.
            if !kind[0].is_ascii_lowercase() || kind == b"acTL" || kind == b"fcTL" || kind == b"fdAT" { return false; }
            if image_data { data_ended = true; }
        }
        offset = end;
    }
    false
}
fn image(value: &Value) -> bool {
    if !fields(value, &["mime", "width", "height", "sha256", "base64"]) || value["mime"] != "image/png" || !hash(&value["sha256"]) { return false; }
    let (Some(width), Some(height), Some(encoded)) = (value["width"].as_u64(), value["height"].as_u64(), value["base64"].as_str()) else { return false; };
    (1..=640).contains(&width) && (1..=640).contains(&height)
        && decode(encoded).is_some_and(|bytes| png(&bytes, width as u32, height as u32))
}
fn review(value: &Value, request: &Value) -> bool {
    fields(value, &["version", "token", "recipe_document_id", "recipe_revision", "source", "candidate_sha256", "before", "after", "boundaries"])
        && value["version"] == 1 && token(&value["token"]) && value["recipe_document_id"] == request["recipe_document_id"]
        && value["recipe_revision"] == request["recipe_revision"] && hash(&value["candidate_sha256"])
        && fields(&value["source"], &["sha256", "width", "height"]) && hash(&value["source"]["sha256"])
        && ["width", "height"].iter().all(|key| value["source"][*key].as_u64().is_some_and(|n| (1..=1000000).contains(&n)))
        && value["before"]["width"] == value["after"]["width"] && value["before"]["height"] == value["after"]["height"]
        && image(&value["before"]) && image(&value["after"])
        && value["boundaries"].as_array().is_some_and(|items| items.len() <= 32 && items.iter().all(|item| item.as_str().is_some_and(|s| s.len() <= 4096)))
}
pub(super) fn receipt(value: &Value, request: &Value) -> bool {
    if value.to_string().len() > MAX_REVIEW_BYTES || value["event"] != "id_background_result" || value["protocol"] != 1
        || value["action"] != request["action"] || value["request_id"] != request["request_id"] || value["document_id"] != request["document_id"]
        || !value["success"].is_boolean() || ["outcome_unknown", "requires_reload"].iter().any(|key| value.get(*key).is_some_and(|v| !v.is_boolean()))
        || (value["success"] == true && (value["outcome_unknown"] == true || value["requires_reload"] == true)) { return false; }
    if value["success"] != true { return value.get("review").map_or(true, |v| v.is_null()); }
    let report = &value["report"];
    if report["recipe_document_id"] != request["recipe_document_id"] { return false; }
    if request["action"] == "id_spill_preview" {
        report["recipe_revision"] == request["recipe_revision"] && review(&value["review"], request)
    } else {
        revision(&report["recipe_revision"]).zip(revision(&request["recipe_revision"])).is_some_and(|(after, before)| after >= before)
            && value.get("review").map_or(true, |v| v.is_null())
    }
}
pub(super) fn apply_matches(request: &Value, original: &Value, result: &Value) -> bool {
    original["action"] == "id_spill_preview" && result["success"] == true && result["review"].is_object()
        && ["document_id", "recipe_document_id", "recipe_revision"].iter().all(|key| request[*key] == original[*key])
        && request["token"] == result["review"]["token"] && request["before_sha256"] == result["review"]["before"]["sha256"]
        && request["after_sha256"] == result["review"]["after"]["sha256"]
}

// Authored only. No compiler, unit test or runtime execution was performed.
#[cfg(test)]
#[path = "spill_removal_protocol_tests.rs"]
mod tests;
