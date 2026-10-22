//! Bound preview bytes before they reach the WebView. Never a commit receipt.
use serde_json::Value;
const MAX_PNG_BYTES: usize = 2 * 1024 * 1024;
const MAX_BASE64_BYTES: usize = ((MAX_PNG_BYTES + 2) / 3) * 4;
fn digit(value: u8) -> Option<u8> {
    match value {
        b'A'..=b'Z' => Some(value - b'A'),
        b'a'..=b'z' => Some(value - b'a' + 26),
        b'0'..=b'9' => Some(value - b'0' + 52),
        b'+' => Some(62), b'/' => Some(63), _ => None,
    }
}
fn decode(value: &str) -> Option<Vec<u8>> {
    if value.is_empty() || value.len() > MAX_BASE64_BYTES || value.len() % 4 != 0 { return None; }
    let mut bytes = Vec::with_capacity(value.len() / 4 * 3);
    let chunks = value.as_bytes().chunks_exact(4);
    let count = chunks.len();
    for (index, part) in chunks.enumerate() {
        let a = digit(part[0])?;
        let b = digit(part[1])?;
        bytes.push((a << 2) | (b >> 4));
        if part[2] == b'=' {
            if index + 1 != count || part[3] != b'=' || b & 15 != 0 { return None; }
        } else {
            let c = digit(part[2])?;
            bytes.push((b << 4) | (c >> 2));
            if part[3] == b'=' {
                if index + 1 != count || c & 3 != 0 { return None; }
            } else { bytes.push((c << 6) | digit(part[3])?); }
        }
    }
    (bytes.len() <= MAX_PNG_BYTES).then_some(bytes)
}
fn u32_at(bytes: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_be_bytes(bytes.get(offset..offset + 4)?.try_into().ok()?))
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
    while offset < bytes.len() {
        let Some(length) = u32_at(bytes, offset) else { return false };
        let Some(end) = offset.checked_add(12).and_then(|n| n.checked_add(length as usize)) else { return false };
        if end > bytes.len() || u32_at(bytes, end - 4) != Some(crc32(&bytes[offset + 4..end - 4])) { return false; }
        let kind = &bytes[offset + 4..offset + 8];
        if offset == 8 {
            if kind != b"IHDR" || length != 13 || u32_at(bytes, offset + 8) != Some(width)
                || u32_at(bytes, offset + 12) != Some(height)
                || &bytes[offset + 16..offset + 21] != [8, 2, 0, 0, 0] { return false; }
        } else if kind == b"IDAT" { image_data |= length > 0; }
        else if kind == b"IEND" { return length == 0 && image_data && end == bytes.len(); }
        else { return false; }
        offset = end;
    }
    false
}
pub(crate) fn valid(value: &Value) -> bool {
    if value["format"] != "png" || value["domain"] != "targeted-tool-stage"
        || value["quality"] != "bounded-proxy-float-operator" { return false; }
    let (Some(width), Some(height), Some(data)) =
        (value["width"].as_u64(), value["height"].as_u64(), value["data"].as_str()) else { return false };
    if !(1..=512).contains(&width) || !(1..=512).contains(&height) { return false; }
    decode(data).is_some_and(|bytes| png(&bytes, width as u32, height as u32))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn base64_rejects_noncanonical_or_unbounded_payloads() {
        assert_eq!(decode("AQID"), Some(vec![1, 2, 3]));
        assert_eq!(decode("AQI="), Some(vec![1, 2]));
        assert_eq!(decode("AQ=="), Some(vec![1]));
        for value in ["", "A", "AQ==AQ==", "AR==", "AQJ=", "AQ I", "===="] {
            assert!(decode(value).is_none());
        }
    }
    #[test]
    fn png_requires_actual_bounded_rgb_header_and_complete_chunks() {
        // Framing fixture only: image decoding remains the WebView's job.
        fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
            bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
            bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
            let checksum = crc32(&bytes[bytes.len() - data.len() - 4..]);
            bytes.extend_from_slice(&checksum.to_be_bytes());
        }
        assert_eq!(crc32(b"123456789"), 0xcbf43926);
        let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
        chunk(&mut bytes, b"IHDR", &[0, 0, 0, 1, 0, 0, 0, 1, 8, 2, 0, 0, 0]);
        chunk(&mut bytes, b"IDAT", &[0]);
        chunk(&mut bytes, b"IEND", &[]);
        assert!(png(&bytes, 1, 1));
        assert!(!png(&bytes, 512, 512));
        let mut corrupt = bytes.clone(); corrupt[29] ^= 1; assert!(!png(&corrupt, 1, 1));
        bytes.pop(); assert!(!png(&bytes, 1, 1));
    }
}
