// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. No compiler, tests, engine, image inference or product ran.
use super::*;

fn sha(character: char) -> String { std::iter::repeat(character).take(64).collect() }
fn source_fixture(key: char) -> Value {
    json!({"asset_sha256":sha(key),"original_sha256":sha(key),"source_kind":"original",
        "width":100,"height":100,"orientation":"exif_normalized_once","retained_asset_id":format!("retained-{key}")})
}
fn binding_fixture() -> Value {
    json!({"document_id":"original-document","document_epoch":"document-epoch","load_id":"load-one",
        "document_revision":2,"state_revision":3,"association_revision":4,"people_graph_sha256":sha('e'),"source":source_fixture('a')})
}
fn face_fixture(key: char) -> Value {
    json!({"face_ref":{"asset_sha256":sha(key),"face_instance_id":format!("face-{key}"),"analysis_revision":1},
        "enabled":true,"analysis_status":"verified","manual":false,"landmarks_count":478,"landmarks_sha256":sha('d'),
        "crop":{"left":10,"top":10,"width":32,"height":32},"eligibility_sha256":sha('e'),"protection_sha256":sha('f')})
}
fn preview_command_fixture() -> Value {
    json!({"version":1,"operation_id":OPERATION,"action":"preview","request_id":"preview-fixture","binding":binding_fixture(),
        "target":{"source":source_fixture('a'),"face":face_fixture('a')},"donor":{"source":source_fixture('b'),"face":face_fixture('b')},
        "fusion":{"version":1,"coordinates":"source_normalized_pixel_centres","initial":"empty",
            "strokes":[{"mode":"add","radius_px":4,"points":[[0.2,0.2],[0.25,0.25]]}]},
        "settings":{"density":0.5,"pyramid_levels":3,"colour_match_strength":0},
        "confirmations":{"same_person":true,"same_session":true,"real_measured_landmarks":true,
            "reviewed_pose":true,"both_unoccluded":true,"fusion_reviewed":true}})
}
fn request_fixture(command: Value) -> Value {
    let bytes = serde_json::to_string(&command).unwrap();
    json!({"cmd":"expression_replacement","action":command["action"],"request_id":command["request_id"],
        "packet":{"command":command,"command_json":bytes,"command_sha256":digest(bytes.as_bytes())}})
}

// Self-contained tiny true PNG fixture: two RGB scanlines in a stored DEFLATE
// block with Adler32 and PNG CRC32. This is authored source, not generated output
// or evidence of a real-photo preview, numerical quality or successful execution.
fn crc(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for byte in bytes { crc ^= u32::from(*byte); for _ in 0..8 { crc = (crc >> 1) ^ (0xedb8_8320 & (0u32.wrapping_sub(crc & 1))); } }
    !crc
}
fn chunk(png: &mut Vec<u8>, tag: &[u8;4], data: &[u8]) {
    png.extend_from_slice(&(data.len() as u32).to_be_bytes());
    let start = png.len(); png.extend_from_slice(tag); png.extend_from_slice(data);
    let checksum = crc(&png[start..]); png.extend_from_slice(&checksum.to_be_bytes());
}
fn image_fixture(tone: u8) -> Value {
    let mut png = vec![137,80,78,71,13,10,26,10];
    chunk(&mut png,b"IHDR",&[0,0,0,2,0,0,0,2,8,2,0,0,0]);
    let raw = [0,tone,tone,tone,tone,tone,tone,0,tone,tone,tone,tone,tone,tone];
    let mut zlib = vec![0x78,0x01,0x01,14,0,0xf1,0xff]; zlib.extend_from_slice(&raw);
    let (mut a,mut b) = (1u32,0u32);
    for byte in &raw { a = (a + u32::from(*byte))%65521; b = (b+a)%65521; }
    zlib.extend_from_slice(&((b<<16)|a).to_be_bytes());
    chunk(&mut png,b"IDAT",&zlib); chunk(&mut png,b"IEND",&[]);
    json!({"mime":"image/png","width":2,"height":2,"sha256":digest(&png),"base64":STANDARD.encode(png),
        "source_sha256":sha('a'),"source_width":100,"source_height":100,"mapping":"normalized_full_frame","orientation":"exif_normalized_once"})
}
fn ready_fixture(req: &Request) -> Value {
    json!({"event":EVENT,"request_id":req.id,"receipt":{"version":1,"operation_id":OPERATION,"action":"preview",
        "request_id":req.id,"command_sha256":req.command_sha256,"binding":binding_fixture(),"phase":"ready",
        "preview":{"preview_token":"retained-preview","candidate_sha256":sha('c'),"fusion_mask_sha256":sha('f'),
            "output_width":100,"output_height":100,"before":image_fixture(10),"after":image_fixture(20),"fusion_image":image_fixture(30)}}})
}
fn apply_fixture(preview: &Request, ready: &Value) -> Value {
    let p = &ready["receipt"]["preview"];
    request_fixture(json!({"version":1,"operation_id":OPERATION,"action":"apply","request_id":"apply-fixture","binding":binding_fixture(),
        "return_mode":"new_image","preview_request_id":preview.id,"preview_command_sha256":preview.command_sha256,
        "preview_token":p["preview_token"],"candidate_sha256":p["candidate_sha256"],"fusion_mask_sha256":p["fusion_mask_sha256"],
        "before_image_sha256":p["before"]["sha256"],"after_image_sha256":p["after"]["sha256"],"fusion_image_sha256":p["fusion_image"]["sha256"],
        "review":"full_before_after_and_fusion_confirmed"}))
}

#[test]
fn supplied_bytes_are_hashed_without_demanding_reserialized_spelling() {
    let command = preview_command_fixture(); let mut req = request_fixture(command.clone());
    let pretty = serde_json::to_string_pretty(&command).unwrap();
    req["packet"]["command_json"] = json!(pretty);
    req["packet"]["command_sha256"] = json!(digest(pretty.as_bytes()));
    assert!(parse_request(&req).is_ok());
    req["packet"]["command_sha256"] = json!(sha('0')); assert!(parse_request(&req).is_err());
}
#[test]
fn duplicate_nested_fields_nonfinite_trailing_and_mismatched_objects_are_refused() {
    for bad in ["{\"request_id\":\"a\",\"request_id\":\"a\"}","{\"nested\":{\"width\":2,\"width\":2}}","[NaN]","[Infinity]","[1e999]","{} {}"] {
        assert!(unique_json(bad,1024).is_err());
    }
    let mut req = request_fixture(preview_command_fixture());
    req["packet"]["command"]["binding"]["document_revision"] = json!(9);
    assert!(parse_request(&req).is_err());
}
#[test]
fn current_digest_uses_exact_sorted_string_only_envelope() {
    let req = parse_request(&json!({"cmd":"expression_replacement","request_id":"current-one","action":"current"})).unwrap();
    assert_eq!(req.command_sha256,digest(br#"{"action":"current","cmd":"expression_replacement","request_id":"current-one"}"#));
    assert!(parse_request(&json!({"cmd":"expression_replacement","request_id":"current-one","action":"current","path":"/tmp/no"})).is_err());
}
#[test]
fn exact_face_proofs_limits_and_original_pair_are_required() {
    let baseline = preview_command_fixture(); assert!(command(&baseline));
    for (key,bad) in [("manual",json!(true)),("landmarks_count",json!(477)),("enabled",json!(false)),("analysis_status",json!("synthetic"))] {
        let mut c = baseline.clone(); c["target"]["face"][key] = bad; assert!(!command(&c));
    }
    let mut c = baseline.clone(); c["donor"]["source"]["original_sha256"] = json!(sha('a')); assert!(!command(&c));
    let mut c = baseline.clone(); c["fusion"]["strokes"][0]["points"] = json!([[0.99,0.99]]); assert!(!command(&c));
    let mut c = baseline.clone(); c["settings"]["colour_match_strength"] = json!(0.1); assert!(!command(&c));
    let mut c = baseline; c["confirmations"]["automatic_identity"] = json!(true); assert!(!command(&c));
}
#[test]
fn donor_path_is_native_only_and_cannot_escape_its_exact_action() {
    let mut req = request_fixture(preview_command_fixture()); req["path"] = json!("/tmp/donor.png"); assert!(parse_request(&req).is_err());
    let donor = json!({"version":1,"operation_id":OPERATION,"action":"choose_donor","request_id":"donor-one","binding":binding_fixture()});
    let mut req = request_fixture(donor); assert!(parse_request(&req).is_ok());
    req["path"] = json!("relative.png"); assert!(parse_request(&req).is_err());
    req["path"] = json!("/tmp/donor.png"); assert!(parse_request(&req).is_ok());
    req["path"] = json!("https://example.test/photo.png"); assert!(parse_request(&req).is_err());
}
#[test]
fn all_three_png_bytes_projection_and_original_binding_are_required() {
    let req = parse_request(&request_fixture(preview_command_fixture())).unwrap();
    let ready = ready_fixture(&req); assert!(valid_result(&ready,&req));
    for image in ["before","after","fusion_image"] {
        let mut bad = ready.clone(); bad["receipt"]["preview"][image]["sha256"] = json!(sha('0')); assert!(!valid_result(&bad,&req));
        let mut bad = ready.clone(); bad["receipt"]["preview"][image]["mapping"] = json!("face_crop"); assert!(!valid_result(&bad,&req));
        let mut bad = ready.clone(); bad["receipt"]["preview"][image]["source_width"] = json!(99); assert!(!valid_result(&bad,&req));
        let mut bad = ready.clone(); bad["receipt"]["preview"][image]["width"] = json!(3); assert!(!valid_result(&bad,&req));
    }
    let mut bad = ready.clone(); bad["receipt"]["binding"]["load_id"] = json!("different-load"); assert!(!valid_result(&bad,&req));
    let mut bad = ready; bad["receipt"]["unproved"] = json!(true); assert!(!valid_result(&bad,&req));
}
#[test]
fn apply_binds_retained_preview_and_actual_new_copy_not_original() {
    let preview = parse_request(&request_fixture(preview_command_fixture())).unwrap(); let ready = ready_fixture(&preview);
    let apply = parse_request(&apply_fixture(&preview,&ready)).unwrap(); assert!(apply_matches(&apply,&preview,&ready));
    let c = &apply.packet.as_ref().unwrap().command;
    let receipt = json!({"event":EVENT,"request_id":apply.id,"receipt":{"version":1,"operation_id":OPERATION,"action":"apply",
        "request_id":apply.id,"command_sha256":apply.command_sha256,"binding":binding_fixture(),"phase":"committed",
        "preview_token":c["preview_token"],"candidate_sha256":c["candidate_sha256"],"fusion_mask_sha256":c["fusion_mask_sha256"],
        "result_document_id":"new-copy-document","copied_original_document_id":"original-document","result_source_sha256":c["candidate_sha256"],"result_revision":0,"no_change":false}});
    assert!(valid_result(&receipt,&apply));
    for (key,bad) in [("result_document_id",json!("original-document")),("copied_original_document_id",json!("someone-else")),("result_source_sha256",json!(sha('a')))] {
        let mut value = receipt.clone(); value["receipt"][key] = bad; assert!(!valid_result(&value,&apply));
    }
    let mut altered = apply_fixture(&preview,&ready); altered["packet"]["command"]["before_image_sha256"] = json!(sha('0'));
    let altered = parse_request(&request_fixture(altered["packet"]["command"].clone())).unwrap(); assert!(!apply_matches(&altered,&preview,&ready));
    assert!(!super::receipt(&wire_cancelled(&apply),apply.packet.as_ref().unwrap()));
}
fn wire_cancelled(req: &Request) -> Value {
    let mut v = pending(req,"cancelled","not allowed for apply")["receipt"].clone(); v["no_write"] = json!(true); v
}

#[test]
fn donor_hints_are_bounded_optional_clues_not_selection() {
    let mut hints = json!({"version":1,"cohorts":[{"association_id":"person","target_ref":face_fixture('a')["face_ref"],
        "blocked":null,"candidates":[{"document_id":"donor","filename":"donor.jpg","face_ref":face_fixture('b')["face_ref"],"eye_aperture":null}]}],"unavailable":null});
    assert!(donor_hints(&hints));
    hints["cohorts"][0]["candidates"][0]["eye_aperture"] = json!(-1);
    assert!(!donor_hints(&hints));
    assert!(!donor_hints(&json!({"version":1,"cohorts":[],"unavailable":null,"best_donor":"donor"})));
}
