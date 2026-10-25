// SPDX-License-Identifier: GPL-3.0-or-later
//! Validate real PNG transport bytes, not a renderer or display-success claim.
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde_json::Value;
use super::json::{digest, fields, hash, integer, number};

const IMAGE_BYTES: usize = 4 * 1024 * 1024;
fn crc(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 { crc = (crc >> 1) ^ (0xedb8_8320 & (0u32.wrapping_sub(crc & 1))); }
    }
    !crc
}
/// Native verifies canonical base64, full PNG hash, chunk CRCs, framing and
/// whole-source dimensions. Actual pixel decode/display and green coverage are
/// independently checked by the UI; this gate never synthesizes missing images.
pub(super) fn image(v: &Value, source: &Value, coverage: bool) -> bool {
    if !fields(v, &["mime", "width", "height", "sha256", "base64"]) || v["mime"] != "image/png" || !hash(&v["sha256"])
        || !integer(&v["width"], 2, 1280) || !integer(&v["height"], 2, 1280)
        || number(&v["width"]) * number(&v["height"]) > 1_000_000.0
        || number(&v["width"]) > number(&source["width"]) || number(&v["height"]) > number(&source["height"])
        || (number(&v["width"]) * number(&source["height"]) - number(&v["height"]) * number(&source["width"])).abs()
            > number(&source["width"]).max(number(&source["height"])) { return false; }
    let Some(encoded) = v["base64"].as_str().filter(|s| s.len() <= ((IMAGE_BYTES + 2) / 3) * 4 && s.len() % 4 == 0) else { return false; };
    let Ok(bytes) = STANDARD.decode(encoded) else { return false; };
    if bytes.len() < 57 || bytes.len() > IMAGE_BYTES || bytes[..8] != [137,80,78,71,13,10,26,10]
        || STANDARD.encode(&bytes) != encoded || digest(&bytes) != v["sha256"].as_str().unwrap() { return false; }
    let mut at = 8usize;
    let (mut header, mut data, mut seen_data, mut data_ended) = (false, false, false, false);
    while at.checked_add(12).is_some_and(|end| end <= bytes.len()) {
        let length = u32::from_be_bytes(bytes[at..at+4].try_into().unwrap()) as usize;
        let Some(end) = at.checked_add(12).and_then(|i| i.checked_add(length)).filter(|i| *i <= bytes.len()) else { return false; };
        let tag = &bytes[at+4..at+8];
        if !tag.iter().all(|b| b.is_ascii_alphabetic()) || !tag[2].is_ascii_uppercase()
            || crc(&bytes[at+4..end-4]) != u32::from_be_bytes(bytes[end-4..end].try_into().unwrap()) { return false; }
        if !header {
            if tag != b"IHDR" || length != 13
                || u32::from_be_bytes(bytes[at+8..at+12].try_into().unwrap()) as f64 != number(&v["width"])
                || u32::from_be_bytes(bytes[at+12..at+16].try_into().unwrap()) as f64 != number(&v["height"])
                || bytes[at+16] != 8 || ![2,6].contains(&bytes[at+17]) || (coverage && bytes[at+17] != 6)
                || bytes[at+18..at+21] != [0,0,0] { return false; }
            header = true;
        } else if tag == b"IDAT" {
            if data_ended { return false; }
            seen_data = true; data |= length > 0;
        } else if tag == b"IEND" {
            return length == 0 && data && end == bytes.len();
        } else {
            if !tag[0].is_ascii_lowercase() || tag == b"acTL" || tag == b"fcTL" || tag == b"fdAT" { return false; }
            if seen_data { data_ended = true; }
        }
        at = end;
    }
    false
}
