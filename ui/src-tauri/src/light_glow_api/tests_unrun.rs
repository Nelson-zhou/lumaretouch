// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Tiny synthetic protocol inputs only. These fixtures do not
//! prove a native render, full-source capture, UI display or canonical return.
use super::*;
use base64::{engine::general_purpose::STANDARD, Engine as _};
use super::super::{imagery, json as primitives};

fn sha(c: char) -> String { std::iter::repeat(c).take(64).collect() }
fn owner() -> Value {
    json!({"document_id":"source-document","document_epoch":"document-epoch","document_revision":"12",
        "source":{"sha256":sha('a'),"width":2,"height":2,"orientation":"exif_normalized_once"}})
}
fn capability() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"status":"available","abi":1,"math_version":65537,"reason":null,
        "modes":["black_mist","white_mist","glow"]})
}
fn evidence() -> Value {
    json!({"kind":"current_full_edited_source","capture_version":3,"original_sha256":sha('c'),"people_graph_sha256":sha('d'),
        "repair_stack_sha256":sha('e'),"document_revision":"12","load_id":"load-one","capture_token":"capture-one"})
}
fn recipe() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"math_identity":65537,"mode":"black_mist","strength":0.3,"radius_px":24,
        "threshold":0.65,"exposure_ev":0,"scattering":0,"tint":{"hue_deg":0,"saturation":0,"lightness":0}})
}
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
fn context() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"session_id":"session-one","owner":owner(),"source_evidence":evidence(),
        "before":png(10,true),"capability":capability(),"message":"Synthetic transport fixture only"})
}
fn preview_command() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"action":"preview","request_id":"preview-one","session_id":"session-one","owner":owner(),"recipe":recipe()})
}
fn review() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"request_id":"preview-one","session_id":"session-one","owner":owner(),"source_evidence":evidence(),
        "token":"review-one","recipe":recipe(),"recipe_sha256":sha('c'),"result_source_sha256":sha('b'),"coverage_sha256":sha('f'),
        "before":png(10,true),"after":png(20,true),"coverage":png(30,true),"no_change":false,"notes":["Fixture, not native output"]})
}
fn apply_command() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"action":"apply","request_id":"apply-one","session_id":"session-one","owner":owner(),
        "token":"review-one","recipe_sha256":sha('c'),"result_source_sha256":sha('b'),"coverage_sha256":sha('f'),"before_sha256":png(10,true)["sha256"],
        "after_sha256":png(20,true)["sha256"],"coverage_image_sha256":png(30,true)["sha256"],"reviewed":true,"return_mode":"new_image"})
}
fn cancel_command() -> Value {
    json!({"version":1,"operation_id":wire::OPERATION,"action":"cancel","request_id":"cancel-one","session_id":"session-one","owner":owner(),"token":null})
}
fn request(action: &str) -> wire::Request {
    let command = match action {"preview" => preview_command(), "apply" => apply_command(), "cancel" => cancel_command(), _ => Value::Null};
    let value = if action == "current" { json!({"cmd":"light_glow","action":"current","request_id":"current-one"}) }
        else { json!({"cmd":"light_glow","action":if action == "preview" {"preview"} else {"submit"},"request_id":command["request_id"],"command":command}) };
    wire::parse_request(&value).unwrap()
}
fn response(req: &wire::Request) -> Value {
    let payload = if req.action == "current" {json!({"context":context()})} else {json!({"review":review()})};
    let mut value = json!({"event":wire::EVENT,"request_id":req.id,"status":"ready"});
    value.as_object_mut().unwrap().extend(payload.as_object().unwrap().clone()); value
}
fn applied(req: &wire::Request, outer_id: &str) -> Value {
    let c = req.inner();
    json!({"event":wire::EVENT,"request_id":outer_id,"status":"ready","receipt":{"version":1,"operation_id":wire::OPERATION,
        "request_id":c["request_id"],"session_id":c["session_id"],"action":c["action"],"owner":c["owner"],"token":c["token"],
        "phase":"done","outcome_unknown":false,"outcome":"applied","message":"Synthetic authoritative-readback fixture",
        "result_document_id":"new-document","copied_original_document_id":"source-document","result_revision":"0",
        "result_source_sha256":c["result_source_sha256"],"no_change":false}})
}
fn host() -> Mailbox { let mut h = Mailbox::default(); h.reset([1;16]); h.ready([1;16], &capability()); h }
fn dispatch(host: &mut Mailbox, req: wire::Request) {
    assert!(host.begin([1;16], req.clone()).unwrap()); host.begin_enqueue([1;16], &req.envelope).unwrap();
    host.ingress([1;16], &req.envelope).unwrap(); host.finish_enqueue([1;16], &req.id);
}
fn prepared() -> Mailbox {
    let mut host = host();
    for action in ["current","preview"] { let req = request(action); dispatch(&mut host, req.clone()); host.observe([1;16], &response(&req)); }
    host
}

#[test] fn strict_raw_json_never_loses_duplicate_field_evidence() {
    for raw in [r#"{"request_id":"a","request_id":"a"}"#,r#"{"owner":{"source":1,"source":2}}"#,"[NaN]","[1e999]","{} {}"] {
        assert!(wire::unique_json(raw, 1024).is_err());
    }
    assert!(wire::unique_json("{}", 1).is_err());
}
#[test] fn only_dedicated_glow_protocol_and_exact_envelopes_are_accepted() {
    for action in ["current","preview","apply","cancel"] { assert!(wire::parse_request(&request(action).envelope).is_ok()); }
    let mut wrong = request("preview").envelope; wrong["cmd"] = json!("lens_blur"); assert!(wire::parse_request(&wrong).is_err());
    wrong = request("preview").envelope; wrong["command"]["version"] = json!(3); assert!(wire::parse_request(&wrong).is_err());
    wrong = request("apply").envelope; wrong["command"]["return_mode"] = json!("replace_original"); assert!(wire::parse_request(&wrong).is_err());
    wrong = request("current").envelope; wrong["path"] = json!("arbitrary.png"); assert!(wire::parse_request(&wrong).is_err());
}
#[test] fn capability_is_versioned_real_math_not_a_filename_or_an_ai_claim() {
    assert!(wire::capability(&capability()));
    for (key,bad) in [("abi",json!(2)),("math_version",json!(65538)),("modes",json!(["glow","glow"])),("modes",json!([]))] {
        let mut value = capability(); value[key] = bad; assert!(!wire::capability(&value));
    }
    let mut value = capability(); value["ai_segmentation"] = json!(true); assert!(!wire::capability(&value));
    let mut h = host(); h.ready([1;16], &Value::Null); assert!(!h.begin([1;16], request("current")).unwrap());
    assert_eq!(h.status("current-one")["status"], "rejected");
}
#[test] fn capture_three_and_exact_revision_are_required() {
    assert!(wire::context(&context()));
    for (key,bad) in [("capture_version",json!(2)),("document_revision",json!("13")),("repair_stack_sha256",json!("missing"))] {
        let mut value = context(); value["source_evidence"][key] = bad; assert!(!wire::context(&value));
    }
    for bad in [json!(12),json!("012"),json!("18446744073709551616")] {
        let mut value = owner(); value["document_revision"] = bad; assert!(!wire::owner(&value));
    }
}
#[test] fn real_png_bytes_crc_sha_and_alpha_are_mandatory() {
    let src = owner()["source"].clone(); let valid = png(10,true);
    assert!(imagery::image(&valid, &src, true)); assert!(!imagery::image(&png(10,false), &src, true));
    let mut wrong = valid.clone(); wrong["sha256"] = json!(sha('0')); assert!(!imagery::image(&wrong, &src, false));
    let mut bytes = STANDARD.decode(valid["base64"].as_str().unwrap()).unwrap(); bytes[30] ^= 1;
    wrong = valid.clone(); wrong["base64"] = json!(STANDARD.encode(&bytes)); wrong["sha256"] = json!(wire::digest(&bytes));
    assert!(!imagery::image(&wrong, &src, false));
    bytes = STANDARD.decode(valid["base64"].as_str().unwrap()).unwrap(); bytes.push(0);
    wrong = valid; wrong["base64"] = json!(STANDARD.encode(&bytes)); wrong["sha256"] = json!(wire::digest(&bytes));
    assert!(!imagery::image(&wrong, &src, false));
}
#[test] fn preview_evidence_must_equal_retained_capture_not_merely_be_well_formed() {
    let mut h = host(); let current = request("current"); dispatch(&mut h, current.clone()); h.observe([1;16], &response(&current));
    let preview = request("preview"); dispatch(&mut h, preview.clone());
    let mut wrong = response(&preview); wrong["review"]["source_evidence"]["repair_stack_sha256"] = json!(sha('0'));
    assert!(wire::valid_result(&wrong, &preview)); // Structurally valid is insufficient.
    assert!(h.observe([1;16], &wrong).is_none()); assert_eq!(h.status(&preview.id)["status"], "unknown");
    assert!(!h.rows.back().unwrap().terminal);
}
#[test] fn apply_binds_full_result_coverage_and_all_three_presented_pngs() {
    let req = request("apply"); assert!(wire::apply_matches(&req, &review()));
    for key in ["recipe_sha256","result_source_sha256","coverage_sha256","before_sha256","after_sha256","coverage_image_sha256"] {
        let mut wrong = req.envelope.clone(); wrong["command"][key] = json!(sha('0'));
        assert!(!wire::apply_matches(&wire::parse_request(&wrong).unwrap(), &review()));
    }
}
#[test] fn original_document_may_never_be_reported_as_new_copy() {
    let req = request("apply"); let mut value = applied(&req, &req.id); assert!(wire::valid_result(&value, &req));
    value["receipt"]["result_document_id"] = json!("source-document"); assert!(!wire::valid_result(&value, &req));
    value = applied(&req, &req.id); value["receipt"]["history_entry_id"] = json!("invented"); assert!(!wire::valid_result(&value, &req));
    assert!(!wire::valid_result(&json!({"event":wire::EVENT,"request_id":req.id,"status":"rejected","message":"Not a write receipt"}), &req));
}
#[test] fn read_cancel_acceptance_is_not_unwind_and_is_never_repeated() {
    let mut h = host(); let req = request("current"); dispatch(&mut h, req.clone());
    let (ack, original) = h.request_cancel([1;16], &req.id).unwrap();
    assert_eq!(ack["requested"], true); assert_eq!(original.unwrap(), req.envelope); assert!(!h.rows[0].terminal);
    assert!(h.request_cancel([1;16], &req.id).unwrap().1.is_none());
    let done = json!({"event":wire::EVENT,"request_id":req.id,"status":"cancelled","message":"Worker actually unwound"});
    h.observe([1;16], &done); h.end([1;16]); assert_eq!(h.status(&req.id), done);
}
#[test] fn unknown_apply_survives_epoch_end_and_blocks_new_epoch_mutation() {
    let mut h = prepared(); let req = request("apply"); dispatch(&mut h, req.clone());
    assert!(h.request_cancel([1;16], &req.id).is_err()); h.reset([2;16]); h.ready([2;16], &capability());
    assert_eq!(h.status(&req.id)["receipt"]["phase"], "unknown");
    assert!(h.ingress([2;16], &json!({"cmd":"history","action":"undo"})).is_err());
    assert!(h.ingress([2;16], &json!({"cmd":"shutdown"})).is_ok());
    let result = applied(&req, &req.id); assert!(h.observe([1;16], &result).is_some());
    assert_eq!(h.status(&req.id), result); assert!(h.ingress([2;16], &json!({"cmd":"history","action":"undo"})).is_ok());
}
#[test] fn readback_settles_original_without_resubmitting_and_cannot_overwrite_terminal() {
    let mut h = prepared(); let req = request("apply"); dispatch(&mut h, req.clone());
    let query = wire::parse_request(&json!({"cmd":"light_glow","action":"receipt","request_id":"query-one","command":req.inner()})).unwrap();
    dispatch(&mut h, query.clone()); let result = applied(&req, &query.id); let marker = h.observe([1;16], &result).unwrap();
    assert_eq!(marker["request_id"], req.id); let original = h.status(&req.id);
    assert_eq!(original["receipt"], result["receipt"]);
    let mut contradiction = wire::rejected(&req, "Contradictory fixture"); contradiction["request_id"] = json!(req.id);
    assert!(h.observe([1;16], &contradiction).is_none()); assert_eq!(h.status(&req.id), original);
}
#[test] fn unknown_queries_are_evictable_but_all_original_writes_are_retained() {
    let mut h = prepared(); let req = request("apply"); dispatch(&mut h, req.clone());
    let query = wire::parse_request(&json!({"cmd":"light_glow","action":"receipt","request_id":"query-one","command":req.inner()})).unwrap();
    dispatch(&mut h, query.clone()); h.observe([1;16], &wire::pending(&query, "unknown", "No authoritative proof"));
    assert!(h.rows.back().unwrap().evictable());
    assert!(!h.rows.iter().find(|r| r.request.id == req.id).unwrap().evictable());
    h.observe([1;16], &applied(&req, &req.id));
    assert!(!h.rows.iter().find(|r| r.request.id == req.id).unwrap().evictable());
}
#[test] fn tombstones_survive_read_cleanup_and_replay_keeps_original_result() {
    let req = request("current"); let mut h = Mailbox::default(); assert!(!h.begin([1;16], req.clone()).unwrap());
    let rejected = h.status(&req.id); h.end([1;16]); assert_eq!(h.status(&req.id), rejected);
    h.rows.clear(); assert!(!h.begin([2;16], req).unwrap()); assert_eq!(h.status("current-one")["status"], "unknown");
}
#[test] fn native_ingress_has_no_generic_direct_or_interactive_replay() {
    let mut h = prepared(); let req = request("apply"); dispatch(&mut h, req.clone());
    assert!(h.ingress([1;16], &req.envelope).is_err());
    assert!(h.ingress([1;16], &json!({"cmd":"light_glow","action":"receipt","request_id":"unregistered","command":req.inner()})).is_err());
    assert!(h.ingress([1;16], &json!({"cmd":"creative_document","action":"state"})).is_err());
}
#[test] fn scalar_finite_ranges_and_unknown_fields_fail_closed() {
    assert!(wire::recipe(&recipe()));
    for (key,bad) in [("radius_px",json!(0.5)),("radius_px",json!(513)),("strength",json!(1.1)),("exposure_ev",json!(-4.1)),("math_identity",json!(65538))] {
        let mut r = recipe(); r[key] = bad; assert!(!wire::recipe(&r));
    }
    let mut r = recipe(); r["preset_id"] = json!("quarter"); assert!(!wire::recipe(&r));
    assert!(primitives::size(&json!({"test":"a".repeat(wire::COMMAND_BYTES)}), wire::COMMAND_BYTES).is_err());
}
