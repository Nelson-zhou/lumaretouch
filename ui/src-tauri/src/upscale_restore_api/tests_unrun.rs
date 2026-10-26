// AUTHORED / UNRUN. No fixtures were executed by the author.
use super::wire;
use serde_json::json;
#[test]
fn fixed_model_and_unrun_capability_contract() {
    assert!(wire::recipe(&json!({"version":1,"model_id":"Swin2SR-classical-sr-x2-64"})));
    assert!(!wire::recipe(&json!({"version":1,"model_id":"lanczos3"})));
    assert!(!wire::recipe(&json!({"version":1,"model_id":"Swin2SR-classical-sr-x2-64","sharpen":1})));
    let capability=json!({"version":1,"operation_id":"lnx.upscale_restore.v1","status":"unavailable",
        "reason":"Missing authenticated model","model_id":"Swin2SR-classical-sr-x2-64","acceptance":"unrun","output_mode":"restore_native_dimensions"});
    assert!(wire::capability(&capability));
    let mut claimed=capability.clone(); claimed["acceptance"]=json!("passed");
    assert!(!wire::capability(&claimed));
}
#[test]
fn cannot_apply_without_exact_source_and_review() {
    assert!(!wire::command(&json!({"version":1,"operation_id":"lnx.upscale_restore.v1","action":"apply","reviewed":true})));
}

// Synthetic PNG transport fixtures only; no model inference or product execution.
use super::Mailbox;
use serde_json::Value;
use base64::{engine::general_purpose::STANDARD, Engine as _};
fn crc(bytes: &[u8]) -> u32 {
    let mut c = 0xffff_ffffu32;
    for b in bytes { c ^= u32::from(*b); for _ in 0..8 { c = (c >> 1) ^ (0xedb8_8320 & (0u32.wrapping_sub(c & 1))); } }
    !c
}
fn chunk(bytes: &mut Vec<u8>, tag: &[u8;4], payload: &[u8]) {
    bytes.extend_from_slice(&(payload.len() as u32).to_be_bytes());
    let start = bytes.len(); bytes.extend_from_slice(tag); bytes.extend_from_slice(payload);
    bytes.extend_from_slice(&crc(&bytes[start..]).to_be_bytes());
}
fn png(tone: u8, rgba: bool) -> Value {
    let channels = if rgba {4} else {3};
    let mut bytes = vec![137,80,78,71,13,10,26,10];
    chunk(&mut bytes, b"IHDR", &[0,0,0,2,0,0,0,2,8,if rgba {6} else {2},0,0,0]);
    let mut raw = Vec::new();
    for _ in 0..2 { raw.push(0); for _ in 0..2 { raw.extend_from_slice(&[0,255,0]); if channels == 4 {raw.push(tone);} } }
    let len = raw.len() as u16;
    let mut zlib = vec![0x78,0x01,0x01]; zlib.extend_from_slice(&len.to_le_bytes()); zlib.extend_from_slice(&(!len).to_le_bytes());
    zlib.extend_from_slice(&raw);
    let (mut a, mut b) = (1u32,0u32);
    for byte in raw { a = (a + u32::from(byte)) % 65521; b = (b + a) % 65521; }
    zlib.extend_from_slice(&((b << 16) | a).to_be_bytes());
    chunk(&mut bytes, b"IDAT", &zlib); chunk(&mut bytes, b"IEND", &[]);
    json!({"mime":"image/png","width":2,"height":2,"sha256":wire::digest(&bytes),"base64":STANDARD.encode(bytes)})
}

#[test]
fn unavailable_protocol_allows_explicit_current_and_valid_current_refreshes_readiness() {
    let epoch=[5;16]; let mut host=Mailbox::default(); host.reset(epoch);
    let unavailable=super::unavailable_capability(); host.ready(epoch,&unavailable);
    let envelope=json!({"cmd":"upscale_restore","action":"current","request_id":"current-one"});
    let req=wire::parse_request(&envelope).unwrap();
    assert!(host.begin(epoch,req).unwrap());
    host.begin_enqueue(epoch,&envelope).unwrap(); host.finish_enqueue(epoch,"current-one");
    let mut available=unavailable.clone(); available["status"]=json!("available"); available["reason"]=Value::Null;
    let owner=json!({"document_id":"doc","document_epoch":"epoch","document_revision":"2",
        "source":{"sha256":"a".repeat(64),"width":16,"height":16,"orientation":"exif_normalized_once"}});
    let evidence=json!({"kind":"current_full_edited_source","capture_version":3,"original_sha256":"b".repeat(64),
        "people_graph_sha256":"c".repeat(64),"repair_stack_sha256":"d".repeat(64),"document_revision":"2","load_id":"load","capture_token":"capture"});
    let result=json!({"event":wire::EVENT,"request_id":"current-one","status":"ready","context":{
        "version":1,"operation_id":wire::OPERATION,"session_id":"session","owner":owner,"source_evidence":evidence,
        "before":png(10,false),"capability":available,"message":"Synthetic context, not inference evidence"}});
    host.observe(epoch,&result);
    assert_eq!(host.capability(Some(epoch))["status"],"available");
    assert_eq!(host.status("current-one")["status"],"ready");
}

#[test]
fn single_full_frame_profile_rejects_oversized_source_without_proxy_substitution() {
    let mut source=json!({"document_id":"doc","document_epoch":"epoch","document_revision":"1",
        "source":{"sha256":"a".repeat(64),"width":1024,"height":1024,"orientation":"exif_normalized_once"}});
    assert!(wire::owner(&source));
    source["source"]["width"]=json!(1025); source["source"]["height"]=json!(16);
    assert!(!wire::owner(&source));
    source["source"]["width"]=json!(15);
    assert!(!wire::owner(&source));
}
