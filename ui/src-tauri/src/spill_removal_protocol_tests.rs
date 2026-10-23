// AUTHORED, UNRUN. Framing tests do not claim successful image decompression.
use super::*;
use serde_json::json;
fn preview_request() -> Value {
    json!({"cmd":"background","action":"id_spill_preview","request_id":"preview-1","document_id":"photo","recipe_document_id":"a".repeat(32),"recipe_revision":"7","parameters":{"enabled":true,"strength":50},"coverage_ids":null,"coverage_reviewed":false})
}
fn apply_request() -> Value {
    json!({"cmd":"background","action":"id_spill_apply","request_id":"apply-1","document_id":"photo","recipe_document_id":"a".repeat(32),"recipe_revision":"7","token":"b".repeat(32),"reviewed":true,"before_sha256":"1".repeat(64),"after_sha256":"2".repeat(64)})
}
fn encoded_png() -> String {
    fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
        let start = bytes.len(); bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
        let checksum = crc32(&bytes[start..]); bytes.extend_from_slice(&checksum.to_be_bytes());
    }
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes, b"IHDR", &[0,0,0,1,0,0,0,1,8,2,0,0,0]);
    chunk(&mut bytes, b"IDAT", &[0]); chunk(&mut bytes, b"IEND", &[]);
    let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::new();
    for part in bytes.chunks(3) {
        let (a, b, c) = (part[0], *part.get(1).unwrap_or(&0), *part.get(2).unwrap_or(&0));
        output.push(alphabet[(a >> 2) as usize] as char);
        output.push(alphabet[((a & 3) << 4 | b >> 4) as usize] as char);
        output.push(if part.len() > 1 { alphabet[((b & 15) << 2 | c >> 6) as usize] as char } else { '=' });
        output.push(if part.len() > 2 { alphabet[(c & 63) as usize] as char } else { '=' });
    }
    output
}
fn preview_receipt() -> Value {
    let image = |hash: &str| json!({"mime":"image/png","width":1,"height":1,"sha256":hash.repeat(64),"base64":encoded_png()});
    json!({"event":"id_background_result","protocol":1,"action":"id_spill_preview","request_id":"preview-1","document_id":"photo","success":true,
        "report":{"recipe_document_id":"a".repeat(32),"recipe_revision":"7"},
        "review":{"version":1,"token":"b".repeat(32),"recipe_document_id":"a".repeat(32),"recipe_revision":"7","source":{"sha256":"c".repeat(64),"width":6000,"height":4000},"candidate_sha256":"d".repeat(64),"before":image("1"),"after":image("2"),"boundaries":[]}})
}
#[test]
fn command_requires_independent_review_and_exact_fields() {
    assert!(command(&preview_request()).is_ok()); assert!(command(&apply_request()).is_ok());
    let mut value = preview_request(); value["coverage_ids"] = json!(["e".repeat(32)]); assert!(command(&value).is_err());
    value["coverage_reviewed"] = json!(true); assert!(command(&value).is_ok());
    value["coverage_ids"] = json!(["brush_edge-1"]); assert!(command(&value).is_ok());
    value["coverage_ids"] = json!(["e".repeat(32), "e".repeat(32)]); assert!(command(&value).is_err());
    let mut value = apply_request(); value["reviewed"] = json!(false); assert!(command(&value).is_err());
    let mut value = preview_request(); value["parameters"]["strength"] = json!(101); assert!(command(&value).is_err());
    let mut value = preview_request(); value["recipe_revision"] = json!("07"); assert!(command(&value).is_err());
    let mut value = apply_request(); value["recipe"] = json!({}); assert!(command(&value).is_err());
}
#[test]
fn bounded_png_requires_header_dimensions_crc_and_canonical_base64() {
    assert!(receipt(&preview_receipt(), &preview_request()));
    let mut value = preview_receipt(); value["review"]["after"]["width"] = json!(2); assert!(!receipt(&value, &preview_request()));
    let mut value = preview_receipt(); value["review"]["before"]["base64"] = json!("AAAA"); assert!(!receipt(&value, &preview_request()));
    let mut value = preview_receipt(); value["review"]["source"]["foreign_owner"] = json!("other"); assert!(!receipt(&value, &preview_request()));
    for encoded in ["", "AQ==AQ==", "AR==", "AQJ=", "AQ I", "===="] { assert!(decode(encoded).is_none()); }
    let mut bytes = decode(&encoded_png()).unwrap(); bytes[29] ^= 1; assert!(!png(&bytes, 1, 1));
}
#[test]
fn receipt_and_apply_proof_never_cross_photo_recipe_or_png_identity() {
    let result = preview_receipt(); assert!(apply_matches(&apply_request(), &preview_request(), &result));
    for (key, value) in [("document_id", json!("other")), ("recipe_revision", json!("8")), ("token", json!("f".repeat(32))), ("after_sha256", json!("d".repeat(64)))] {
        let mut request = apply_request(); request[key] = value; assert!(!apply_matches(&request, &preview_request(), &result));
    }
    let mut result = preview_receipt(); result["action"] = json!("id_set"); assert!(!receipt(&result, &preview_request()));
    let mut result = preview_receipt(); result["protocol"] = json!(2); assert!(!receipt(&result, &preview_request()));
    let mut result = preview_receipt(); result["requires_reload"] = json!(true); assert!(!receipt(&result, &preview_request()));
}
