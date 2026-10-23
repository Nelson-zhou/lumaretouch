//! AUTHORED / UNRUN. These are protocol fixtures, never acceptance evidence of
//! a real portrait render. No compiler, tests or application were executed.
use super::*;
use base64::Engine as _;
use serde_json::json;

fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
    bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
    bytes.extend_from_slice(kind);
    bytes.extend_from_slice(data);
    let checksum = crc32(&bytes[bytes.len() - data.len() - 4..]);
    bytes.extend_from_slice(&checksum.to_be_bytes());
}
/// A tiny RGB8 PNG with a complete uncompressed zlib stream. It exercises the
/// transport without an image-codec dependency or claiming a product render.
fn sample_image(width: u32, height: u32) -> Value {
    assert!((1..=2).contains(&width) && (1..=2).contains(&height));
    let mut raw = Vec::new();
    for _ in 0..height {
        raw.push(0); // PNG row filter: None.
        for _ in 0..width { raw.extend_from_slice(&[32, 64, 96]); }
    }
    let length = raw.len() as u16;
    let mut zlib = vec![0x78, 0x01, 0x01]; // zlib header and final stored block.
    zlib.extend_from_slice(&length.to_le_bytes());
    zlib.extend_from_slice(&(!length).to_le_bytes());
    zlib.extend_from_slice(&raw);
    let (mut a, mut b) = (1_u32, 0_u32);
    for byte in raw { a = (a + u32::from(byte)) % 65521; b = (b + a) % 65521; }
    zlib.extend_from_slice(&((b << 16) | a).to_be_bytes());
    let mut bytes = b"\x89PNG\r\n\x1a\n".to_vec();
    let mut ihdr = Vec::new();
    ihdr.extend_from_slice(&width.to_be_bytes());
    ihdr.extend_from_slice(&height.to_be_bytes());
    ihdr.extend_from_slice(&[8, 2, 0, 0, 0]);
    chunk(&mut bytes, b"IHDR", &ihdr);
    chunk(&mut bytes, b"IDAT", &zlib);
    chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png", "width":width, "height":height,
        "sha256":format!("{:x}", Sha256::digest(&bytes)), "base64":STANDARD.encode(&bytes)})
}
pub(crate) fn sample_transfer(document: &Value, rev: &Value, params: &Value, source: &Value) -> Value {
    let image = sample_image(1, 1);
    json!({"version":1, "document_id":document, "revision":rev, "parameters":params, "source_proof":source,
        "before_sha256":"a".repeat(64), "candidate_sha256":"b".repeat(64),
        "before_people_sha256":"c".repeat(64), "candidate_people_sha256":"d".repeat(64),
        "source_size":[1,1], "before_output_size":[1,1], "after_output_size":[1,1], "before":image, "after":image})
}
fn sample() -> Value {
    sample_transfer(&json!("loaded-photo"), &json!("4"), &json!({"enabled":true,"strength":61}),
        &json!({"asset_sha256":"1".repeat(64),"original_sha256":"1".repeat(64),"creative_source":null}))
}
fn valid(value: &Value) -> bool {
    let original = sample();
    transfer(value, &original["document_id"], &original["revision"], &original["parameters"], &original["source_proof"])
}
fn acknowledgment() -> Value {
    let value = sample();
    json!({"document_id":value["document_id"], "revision":value["revision"],
        "before_sha256":value["before"]["sha256"], "after_sha256":value["after"]["sha256"]})
}
fn request() -> Value {
    json!({"cmd":"batch", "action":"commit", "request_id":"spill-commit",
        "preflight_token":"f".repeat(32), "spill_review_ack":[acknowledgment()]})
}

#[test]
fn exact_complete_images_and_separate_crop_geometry_are_accepted() {
    let mut value = sample();
    assert!(valid(&value));
    value["before_output_size"] = json!([2,1]);
    value["before"] = sample_image(2,1);
    value["after_output_size"] = json!([1,2]);
    value["after"] = sample_image(1,2);
    assert!(valid(&value));
    value["after_output_size"] = json!([4,1]);
    assert!(!valid(&value));
}

#[test]
fn evidence_is_exact_and_binds_target_revision_source_and_parameters() {
    let original = sample();
    for key in original.as_object().unwrap().keys() {
        let mut value = original.clone(); value.as_object_mut().unwrap().remove(key);
        assert!(!valid(&value), "missing {key}");
    }
    for (key, replacement) in [("unrequested", json!(true)), ("version", json!(2)),
        ("document_id", json!("another-photo")), ("revision", json!("04")),
        ("parameters", json!({"enabled":true,"strength":60})), ("source_proof", Value::Null),
        ("before_sha256", json!("A".repeat(64))), ("candidate_people_sha256", json!(false)),
        ("source_size", json!([0,1])), ("after_output_size", json!([4_294_967_296_u64,1]))] {
        let mut value = original.clone(); value[key] = replacement; assert!(!valid(&value), "{key}");
    }
    for params in [json!({"enabled":1,"strength":61}), json!({"enabled":true,"strength":101}),
        json!({"enabled":true,"strength":61,"coverage":null})] {
        let mut value = original.clone(); value["parameters"] = params.clone();
        assert!(!transfer(&value, &value["document_id"], &value["revision"], &params, &value["source_proof"]));
    }
}

#[test]
fn derived_source_hash_and_extent_are_bound_independently_of_originals() {
    let mut value = sample();
    value["source_proof"] = json!({"asset_sha256":"2".repeat(64),"original_sha256":"1".repeat(64),
        "creative_source":{"sha256":"2".repeat(64),"width":32,"height":24}});
    value["source_size"] = json!([32,24]);
    let source = value["source_proof"].clone();
    assert!(transfer(&value, &value["document_id"], &value["revision"], &value["parameters"], &source));
    value["source_size"] = json!([24,32]);
    assert!(!transfer(&value, &value["document_id"], &value["revision"], &value["parameters"], &source));
    let mut source = source;
    source["creative_source"]["sha256"] = json!("3".repeat(64)); assert!(!source_proof(&source));
    source = sample()["source_proof"].clone(); source["asset_sha256"] = json!("2".repeat(64)); assert!(!source_proof(&source));
}

#[test]
fn png_signature_dimensions_crc_digest_and_bounds_are_not_metadata_only() {
    let original = sample();
    for side in ["before", "after"] {
        for (key, replacement) in [("sha256", json!("e".repeat(64))), ("width", json!(2)),
            ("height", json!(257)), ("mime", json!("image/jpeg")), ("base64", json!("iVBORw==")),
            ("base64", json!("A".repeat(MAX_BASE64 + 4))), ("extra", json!(true))] {
            let mut value = original.clone(); value[side][key] = replacement; assert!(!valid(&value), "{side}.{key}");
        }
        let bytes = STANDARD.decode(original[side]["base64"].as_str().unwrap()).unwrap();
        // Updating SHA after corruption must not turn invalid PNG structure into
        // admissible evidence. Browser decoding remains required beyond framing.
        for index in [0, 16, 29] {
            let mut damaged = bytes.clone(); damaged[index] ^= 1;
            let mut value = original.clone(); value[side]["base64"] = json!(STANDARD.encode(&damaged));
            value[side]["sha256"] = json!(format!("{:x}", Sha256::digest(&damaged)));
            assert!(!valid(&value));
        }
        let mut trailing = bytes.clone(); trailing.push(0);
        assert!(!png(&trailing, 1, 1));
        assert!(!png(&bytes[..bytes.len()-1], 1, 1));
    }
}

#[test]
fn commands_bound_each_image_ack_to_frozen_commits_only() {
    let original = request(); assert!(command(&original).is_ok());
    let mut empty = original.clone(); empty["spill_review_ack"] = json!([]); assert!(command(&empty).is_ok());
    let mut preset = original.clone(); preset["cmd"] = json!("preset"); preset["action"] = json!("apply");
    preset["document_id"] = json!("loaded-photo"); assert!(command(&preset).is_ok());
    preset["document_id"] = json!("other-photo"); assert!(command(&preset).is_err());
    preset["document_id"] = json!("loaded-photo"); preset["spill_review_ack"] = json!([]); assert!(command(&preset).is_err());
    for action in ["preflight", "undo", "redo", "people_targets", "save", "import", "apply"] {
        let mut value = original.clone(); value["action"] = json!(action); assert!(command(&value).is_err(), "{action}");
    }
    for key in ["preflight_token", "request_id"] {
        let mut value = original.clone(); value.as_object_mut().unwrap().remove(key); assert!(command(&value).is_err());
    }
    let mut value = original.clone(); value["spill_review_ack"] = Value::Null; assert!(command(&value).is_err());
    value = original.clone(); value["preflight_token"] = json!("A".repeat(32)); assert!(command(&value).is_err());
    value = original.clone(); value["spill_review_ack"] = json!(vec![acknowledgment(); 2]); assert!(command(&value).is_err());
    value = original.clone(); value["spill_review_ack"] = json!((0..9).map(|i| {
        let mut item = acknowledgment(); item["document_id"] = json!(format!("target-{i}")); item
    }).collect::<Vec<_>>()); assert!(command(&value).is_err());
    value["spill_review_ack"].as_array_mut().unwrap().pop(); assert!(command(&value).is_ok());
    value = original.clone(); value.as_object_mut().unwrap().remove("spill_review_ack");
    value["action"] = json!("preflight"); assert!(command(&value).is_ok());
}

#[test]
fn acknowledgment_fields_and_revisions_are_canonical() {
    for rev in ["", "00", "04", "-1", "+4", "4.0", "18446744073709551616"] {
        let mut value = request(); value["spill_review_ack"][0]["revision"] = json!(rev); assert!(command(&value).is_err(), "{rev}");
    }
    for rev in ["0", "4", "18446744073709551615"] {
        let mut value = request(); value["spill_review_ack"][0]["revision"] = json!(rev); assert!(command(&value).is_ok());
    }
    for (key, replacement) in [("document_id", json!("")), ("document_id", json!("a".repeat(129))),
        ("revision", json!(4)), ("before_sha256", json!("A".repeat(64))), ("after_sha256", json!("f".repeat(63))),
        ("approved", json!(true))] {
        let mut value = request(); value["spill_review_ack"][0][key] = replacement; assert!(command(&value).is_err(), "{key}");
    }
    for key in ["document_id", "revision", "before_sha256", "after_sha256"] {
        let mut value = request(); value["spill_review_ack"][0].as_object_mut().unwrap().remove(key); assert!(command(&value).is_err());
    }
}
