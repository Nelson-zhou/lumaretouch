//! AUTHORED / UNRUN. Transport fixtures are not photo-quality acceptance or
//! evidence of a successful application render, image load or native build.
use super::*;
use base64::Engine as _;
use serde_json::json;

pub(crate) fn preview_request() -> Value {
    json!({"cmd":"background","action":"id_original_shadow_preview","request_id":"shadow-preview-1",
        "document_id":"photo","recipe_document_id":"a".repeat(32),"recipe_revision":"7",
        "parameters":{"enabled":true,"strength":75,"blend":"normal"},"lit_ids":["floor-lit"],
        "retention_ids":["floor-shadow"],"samples_reviewed":true,"uniform_floor_confirmed":true})
}
fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
    bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
    let start = bytes.len(); bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
    let checksum = crc32(&bytes[start..]); bytes.extend_from_slice(&checksum.to_be_bytes());
}
/// A bounded RGB8 PNG with a complete stored zlib stream, not a product photo.
fn sample_image(width: u32, height: u32, shade: u8) -> Value {
    assert!((1..=2).contains(&width) && (1..=2).contains(&height));
    let mut raw = Vec::new();
    for _ in 0..height {
        raw.push(0);
        for _ in 0..width { raw.extend_from_slice(&[shade, 64, 96]); }
    }
    let length = raw.len() as u16;
    let mut zlib = vec![0x78, 0x01, 0x01];
    zlib.extend_from_slice(&length.to_le_bytes()); zlib.extend_from_slice(&(!length).to_le_bytes());
    zlib.extend_from_slice(&raw);
    let (mut a, mut b) = (1_u32, 0_u32);
    for byte in raw { a = (a + u32::from(byte)) % 65521; b = (b + a) % 65521; }
    zlib.extend_from_slice(&((b << 16) | a).to_be_bytes());
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec(); let mut ihdr = Vec::new();
    ihdr.extend_from_slice(&width.to_be_bytes()); ihdr.extend_from_slice(&height.to_be_bytes());
    ihdr.extend_from_slice(&[8, 2, 0, 0, 0]);
    chunk(&mut bytes, b"IHDR", &ihdr); chunk(&mut bytes, b"IDAT", &zlib); chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png","width":width,"height":height,
        "sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(&bytes)})
}
pub(crate) fn preview_receipt() -> Value {
    json!({"event":"id_background_result","protocol":1,"action":"id_original_shadow_preview",
        "request_id":"shadow-preview-1","document_id":"photo","success":true,"outcome_unknown":false,"requires_reload":false,
        "report":{"recipe_document_id":"a".repeat(32),"recipe_revision":"7"},
        "shadow_review":{"version":1,"token":"b".repeat(32),"recipe_document_id":"a".repeat(32),"recipe_revision":"7",
        "source":{"sha256":"c".repeat(64),"width":6000,"height":4000},"candidate_sha256":"d".repeat(64),
        "before":sample_image(1,1,32),"after":sample_image(1,1,48),"boundaries":["Manual uniform diffuse floor only"]}})
}
pub(crate) fn apply_request() -> Value {
    let result = preview_receipt(); let review = &result["shadow_review"];
    json!({"cmd":"background","action":"id_original_shadow_apply","request_id":"shadow-apply-1","document_id":"photo",
        "recipe_document_id":"a".repeat(32),"recipe_revision":"7","token":review["token"],"reviewed":true,
        "before_sha256":review["before"]["sha256"],"after_sha256":review["after"]["sha256"]})
}

#[test]
fn original_shadow_is_separate_exact_schema_not_a_spill_request() {
    assert!(is_shadow(&preview_request())); assert!(command(&preview_request()).is_ok()); assert!(command(&apply_request()).is_ok());
    for base in [preview_request(), apply_request()] {
        for field in base.as_object().unwrap().keys().filter(|key| key.as_str() != "action") {
            let mut value = base.clone(); value.as_object_mut().unwrap().remove(field);
            assert!(command(&value).is_err(), "missing {field}");
        }
        let mut value = base; value["spill"] = json!({"enabled":true}); assert!(command(&value).is_err());
    }
    let mut request = preview_request(); request["coverage_ids"] = json!(["borrowed-subject"]); assert!(command(&request).is_err());
    let mut request = preview_request(); request["parameters"]["source"] = json!("external.png"); assert!(command(&request).is_err());
    let mut result = preview_receipt(); result["review"] = result["shadow_review"].clone(); assert!(!receipt(&result, &preview_request()));
    let mut result = preview_receipt(); let review = result.as_object_mut().unwrap().remove("shadow_review").unwrap(); result["review"] = review;
    assert!(!receipt(&result, &preview_request()));
}

#[test]
fn manual_selections_are_independent_bounded_and_explicitly_reviewed() {
    for (lit, retained, reviewed, accepted) in [
        (Value::Null, Value::Null, false, true), (Value::Null, Value::Null, true, false),
        (json!(["lit"]), Value::Null, true, true), (Value::Null, json!(["retained"]), true, true),
        (json!(["lit"]), json!(["retained"]), false, false), (json!([]), Value::Null, true, false),
        (json!(["lit", "lit"]), Value::Null, true, false), (json!(["a/b"]), Value::Null, true, false),
        (json!(["x".repeat(65)]), Value::Null, true, false), (json!([null]), Value::Null, true, false),
    ] {
        let mut request = preview_request(); request["lit_ids"] = lit; request["retention_ids"] = retained;
        request["samples_reviewed"] = json!(reviewed); assert_eq!(command(&request).is_ok(), accepted);
    }
    let mut request = preview_request(); request["lit_ids"] = json!((0..65).map(|n| format!("lit-{n}")).collect::<Vec<_>>());
    assert!(command(&request).is_err());
    let mut request = preview_request(); request["uniform_floor_confirmed"] = json!(false); assert!(command(&request).is_err());
    request["parameters"]["enabled"] = json!(false); assert!(command(&request).is_ok());
}

#[test]
fn parameters_tokens_and_revision_never_coerce_invalid_values() {
    for blend in ["normal", "multiply", "softlight"] {
        let mut value = preview_request(); value["parameters"]["blend"] = json!(blend); assert!(command(&value).is_ok());
    }
    for (key, value) in [("strength", json!(-0.01)), ("strength", json!(100.01)), ("strength", json!(true)),
        ("enabled", json!(1)), ("blend", json!("overlay"))] {
        let mut request = preview_request(); request["parameters"][key] = value; assert!(command(&request).is_err());
    }
    for (key, value) in [("recipe_revision", json!("07")), ("recipe_revision", json!(7)),
        ("recipe_revision", json!("18446744073709551616")), ("token", json!("0".repeat(32))),
        ("token", json!("B".repeat(32))), ("reviewed", json!(false)), ("after_sha256", json!("F".repeat(64)))] {
        let mut request = apply_request(); request[key] = value; assert!(command(&request).is_err());
    }
}

#[test]
fn receipt_requires_exact_full_candidate_identity_and_both_real_png_hashes() {
    let request = preview_request(); assert!(receipt(&preview_receipt(), &request));
    let review = preview_receipt()["shadow_review"].clone();
    for key in review.as_object().unwrap().keys() {
        let mut result = preview_receipt(); result["shadow_review"].as_object_mut().unwrap().remove(key);
        assert!(!receipt(&result, &request), "missing {key}");
    }
    for (key, replacement) in [("version", json!(2)), ("token", json!("0".repeat(32))),
        ("candidate_sha256", json!("short")), ("recipe_revision", json!("8")), ("recipe_document_id", json!("other")),
        ("unrequested", json!(true)), ("boundaries", json!(vec!["boundary";33]))] {
        let mut result = preview_receipt(); result["shadow_review"][key] = replacement; assert!(!receipt(&result, &request));
    }
    let mut result = preview_receipt(); result["shadow_review"]["source"]["foreign_owner"] = json!("other"); assert!(!receipt(&result, &request));
    for key in ["before", "after"] {
        let mut result = preview_receipt(); result["shadow_review"][key]["sha256"] = json!("f".repeat(64)); assert!(!receipt(&result, &request));
    }
    // A square completed crop need not match the immutable 3:2 source extent.
    assert!(receipt(&preview_receipt(), &request));
    let mut result = preview_receipt(); result["shadow_review"]["after"] = sample_image(2,1,48); assert!(!receipt(&result, &request));
}

#[test]
fn png_framing_checks_crc_canonical_bytes_dimensions_and_limits() {
    let original = sample_image(1,1,32); assert!(image(&original));
    for (key, value) in [("width", json!(2)), ("width", json!(513)), ("height", json!(0)),
        ("mime", json!("image/jpeg")), ("base64", json!("AAAA")), ("unrequested", json!(true))] {
        let mut picture = original.clone(); picture[key] = value; assert!(!image(&picture));
    }
    let mut bytes = STANDARD.decode(original["base64"].as_str().unwrap()).unwrap(); bytes[29] ^= 1;
    let mut bad = original.clone(); bad["base64"] = json!(STANDARD.encode(&bytes)); bad["sha256"] = json!(format!("{:x}",Sha256::digest(&bytes)));
    assert!(!image(&bad)); // Even a self-consistent SHA cannot authorize bad CRC.
    let mut bad = original.clone(); bad["base64"] = json!(format!("{}\n", original["base64"].as_str().unwrap())); assert!(!image(&bad));
    let mut bad = original.clone(); bad["base64"] = json!("A".repeat(MAX_BASE64 + 4)); assert!(!image(&bad));
    let bytes = STANDARD.decode(original["base64"].as_str().unwrap()).unwrap();
    for end in 0..bytes.len() { assert!(!png(&bytes[..end],1,1)); }
    let mut trailing = bytes.clone(); trailing.push(0); assert!(!png(&trailing,1,1));
    for kind in [b"acTL", b"fcTL", b"fdAT", b"ZZZZ", b"aaab", b"a1Aa"] {
        let mut altered = bytes[..33].to_vec(); chunk(&mut altered, kind, &[]); altered.extend_from_slice(&bytes[33..]);
        assert!(!png(&altered,1,1));
    }
    let mut split = bytes[..33].to_vec(); chunk(&mut split, b"IDAT", &[]); chunk(&mut split, b"tEXt", &[]);
    split.extend_from_slice(&bytes[33..]); assert!(!png(&split,1,1));
}

#[test]
fn successful_apply_requires_prior_successful_shadow_receipt_and_exact_pair() {
    let original = preview_request(); let result = preview_receipt(); let apply = apply_request();
    assert!(apply_matches(&apply, &original, &result));
    for (key, replacement) in [("document_id", json!("other")), ("recipe_document_id", json!("other")),
        ("recipe_revision", json!("8")), ("token", json!("c".repeat(32))),
        ("before_sha256", json!("d".repeat(64))), ("after_sha256", json!("e".repeat(64))), ("reviewed", json!(false))] {
        let mut request = apply.clone(); request[key] = replacement; assert!(!apply_matches(&request, &original, &result));
    }
    for (key, replacement) in [("success", json!(false)), ("document_id", json!("other")),
        ("action", json!("id_spill_preview")), ("protocol", json!(2)), ("request_id", json!("other")),
        ("requires_reload", json!(true)), ("outcome_unknown", json!(true))] {
        let mut failed = result.clone(); failed[key] = replacement; assert!(!apply_matches(&apply, &original, &failed));
    }
    let mut result = result; result["shadow_review"]["after"]["sha256"] = apply["before_sha256"].clone();
    assert!(!apply_matches(&apply, &original, &result));
}

#[test]
fn terminal_receipts_keep_known_failure_distinct_from_uncertain_mutation() {
    let apply = apply_request();
    let mut result = json!({"event":"id_background_result","protocol":1,"action":"id_original_shadow_apply",
        "request_id":apply["request_id"],"document_id":apply["document_id"],"success":false,
        "outcome_unknown":false,"requires_reload":false,"error":"Not committed"});
    assert!(receipt(&result,&apply));
    result["outcome_unknown"] = json!(true); result["requires_reload"] = json!(true); assert!(receipt(&result,&apply));
    result["success"] = json!(true); assert!(!receipt(&result,&apply));
    result["outcome_unknown"] = json!(false); result["requires_reload"] = json!(false);
    result.as_object_mut().unwrap().remove("error");
    result["report"] = json!({"recipe_document_id":apply["recipe_document_id"],"recipe_revision":"8"}); assert!(receipt(&result,&apply));
    result["report"]["recipe_revision"] = json!("6"); assert!(!receipt(&result,&apply));
    result["report"]["recipe_revision"] = json!("8"); result["shadow_review"] = preview_receipt()["shadow_review"].clone(); assert!(!receipt(&result,&apply));
}
