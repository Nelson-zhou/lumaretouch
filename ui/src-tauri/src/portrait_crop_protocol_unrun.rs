// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Synthetic byte fixtures are not photographic, numerical,
//! UI, detector, performance or runtime acceptance evidence.
use super::*;
fn sha(c:char)->String {std::iter::repeat(c).take(64).collect()}
fn request(action:&str,id:&str)->Request {
    parse_request(&json!({"cmd":"portrait_crop","action":action,"request_id":id})).unwrap()
}
fn event(req:&Request,phase:&str)->Value {
    json!({"event":EVENT,"version":1,"request_id":req.id,"action":req.action,"command_sha256":sha('a'),
        "original_request":req.envelope,"phase":phase})
}
fn chunk(bytes:&mut Vec<u8>,tag:&[u8;4],payload:&[u8]) {
    bytes.extend_from_slice(&(payload.len() as u32).to_be_bytes());let start=bytes.len();bytes.extend_from_slice(tag);bytes.extend_from_slice(payload);
    let checksum=crc(&bytes[start..]);bytes.extend_from_slice(&checksum.to_be_bytes());
}
fn png(width:u32,height:u32,source_width:u32,source_height:u32,tone:u8)->Value {
    let mut bytes=vec![137,80,78,71,13,10,26,10];let mut header=Vec::new();
    header.extend_from_slice(&width.to_be_bytes());header.extend_from_slice(&height.to_be_bytes());header.extend_from_slice(&[8,2,0,0,0]);chunk(&mut bytes,b"IHDR",&header);
    let mut raw=Vec::new();for _ in 0..height {raw.push(0);raw.extend(std::iter::repeat(tone).take(width as usize*3));}
    let length=raw.len() as u16;let mut zlib=vec![0x78,0x01,0x01];zlib.extend_from_slice(&length.to_le_bytes());zlib.extend_from_slice(&(!length).to_le_bytes());zlib.extend_from_slice(&raw);
    let (mut a,mut b)=(1u32,0u32);for byte in raw {a=(a+u32::from(byte))%65521;b=(b+a)%65521;}zlib.extend_from_slice(&((b<<16)|a).to_be_bytes());
    chunk(&mut bytes,b"IDAT",&zlib);chunk(&mut bytes,b"IEND",&[]);
    json!({"mime":"image/png","width":width,"height":height,"sha256":digest(&bytes),"base64":STANDARD.encode(bytes),
        "source_width":source_width,"source_height":source_height,"mapping":"normalized_full_frame"})
}
fn captured()->Value {
    json!({"session_id":"session-fixture","capture_sha256":sha('b'),"binding":{
        "document_id":"document-fixture","revision":"12","document_epoch":"workspace-fixture","load_id":"load-fixture",
        "original_sha256":sha('c'),"source_proof":{"original_sha256":sha('c'),"asset_sha256":sha('c'),"creative_source":null},
        "state_sha256":sha('d'),"non_crop_sha256":sha('e'),"people_sha256":sha('f'),"repair_sha256":sha('1'),"uncropped_sha256":sha('2')},
        "source":{"width":8,"height":8,"orientation":"exif_normalized_once","mapping":"source_edge_pixels","source_sha256":sha('2'),
            "analysis_sha256":sha('3'),"model_sha256":sha('4'),"semantic_model_sha256":sha('5'),"proxy_sha256":sha('6'),"proxy_size":[2,2],
            "inference":"fresh_whole_frame_display_proxy","image":png(2,2,8,8,32),"faces":[{"face_id":format!("face:{}",sha('7')),
                "landmarks_sha256":sha('7'),"bbox":[2,2,6,6],"chin_proposal":[4,6],"center_proposal":[4,4]}]},
        // Existing full edited crop, intentionally NOT the uncropped source.
        "before":png(1,2,4,8,64)})
}
fn preview_request_fixture()->Request {
    let current=captured();parse_request(&json!({"cmd":"portrait_crop","action":"preview","request_id":"preview-fixture",
        "session_id":current["session_id"],"capture_sha256":current["capture_sha256"],"face_id":current["source"]["faces"][0]["face_id"],
        "anchors":{"version":1,"crown":[4,2],"chin":[4,6],"face_center":[4,4]},
        "rules":{"version":1,"aspect_ratio":0.5,"headroom_fraction":0,"head_fraction":1,"horizontal_position":0.5},
        "anchor_review":{"image_sha256":current["source"]["image"]["sha256"],"crown_confirmed":true,"chin_confirmed":true,"center_confirmed":true}})).unwrap()
}
fn preview_fixture()->Value {
    let req=preview_request_fixture();json!({"preview_token":"candidate-fixture","capture_sha256":sha('b'),"candidate_sha256":sha('8'),"preview_request_id":req.id,
        "before":captured()["before"],"after":png(1,2,2,4,96),"plan":{"version":1,"convention":"lrt.portrait-crop.source-edge-pixels.v1","operation_id":"lnx.crop.v1",
            "rotation_degrees":0,"source_size":[8,8],"anchors":req.envelope["anchors"],"rules":req.envelope["rules"],"continuous_rect_pixels":[3,2,5,6],
            "rect_normalized":[0.375,0.25,0.625,0.75],"pixel_bounds":[3,2,5,6],"output_size":[2,4],
            "requested":{"aspect_ratio":0.5,"headroom_fraction":0,"head_fraction":1,"horizontal_position":0.5,"vertical_position":0.5},
            "achieved":{"aspect_ratio":0.5,"headroom_fraction":0,"head_fraction":1,"horizontal_position":0.5,"vertical_position":0.5,"head_height_pixels":4},
            "is_full_frame":false,"backend":"rust-portrait-crop-v1"}})
}
#[test] fn duplicate_keys_nonfinite_trailing_and_oversized_raw_json_fail() {
    for raw in [r#"{"request_id":"a","request_id":"b"}"#,r#"{"original_request":{"action":"apply","action":"current"}}"#,"[NaN]","[1e999]","{} {}"] {assert!(unique_json(raw,1024).is_err());}
    assert!(unique_json("{}",1).is_err());
}
#[test] fn original_schema_has_no_shadow_action_or_private_epoch() {
    let mut v=request("current","current-fixture").envelope;v["host_epoch"]=json!("forged");assert!(parse_request(&v).is_err());
    v=preview_request_fixture().envelope;v["anchor_review"]["crown_confirmed"]=json!(false);assert!(parse_request(&v).is_err());
    assert!(parse_request(&json!({"cmd":"portrait_crop","action":"status","request_id":"same","target_request_id":"same"})).is_err());
}
#[test] fn working_requires_exact_original_server_digest_and_explicit_no_write() {
    let req=request("current","working-fixture");let mut value=event(&req,"working");value["no_write"]=json!(true);
    assert!(valid_result(&value,&req,None,None));assert!(valid_result(&value,&req,Some(&sha('a')),None));
    assert!(!valid_result(&value,&req,Some(&sha('b')),None));
    value["original_request"]["request_id"]=json!("other");assert!(!valid_result(&value,&req,None,None));
    value=event(&req,"working");assert!(!valid_result(&value,&req,None,None));
}
#[test] fn png_hash_crc_whole_frame_and_no_trailing_or_partial_image() {
    let value=png(2,2,8,8,16);assert!(image(&value));
    let mut wrong=value.clone();wrong["source_width"]=json!(16);assert!(!image(&wrong));
    wrong=value.clone();wrong["sha256"]=json!(sha('0'));assert!(!image(&wrong));
    let mut bytes=STANDARD.decode(value["base64"].as_str().unwrap()).unwrap();bytes[30]^=1;
    wrong=value.clone();wrong["base64"]=json!(STANDARD.encode(&bytes));wrong["sha256"]=json!(digest(&bytes));assert!(!image(&wrong));
    let mut bytes=STANDARD.decode(value["base64"].as_str().unwrap()).unwrap();bytes.push(0);
    wrong=value;wrong["base64"]=json!(STANDARD.encode(&bytes));wrong["sha256"]=json!(digest(&bytes));assert!(!image(&wrong));
}
#[test] fn current_distinguishes_complete_measurement_source_and_existing_cropped_before() {
    let value=captured();assert!(current(&value));let proof=current_proof(&value);
    assert!(proof["before"].get("base64").is_none());assert!(proof["source"]["image"].get("base64").is_none());
    assert_ne!(proof["before"],proof["source"]["image"]);
    let mut wrong=value.clone();wrong["binding"]["source_proof"]["asset_sha256"]=json!(sha('0'));assert!(!current(&wrong));
    wrong=value;wrong["source"]["faces"][0]["face_id"]=json!("invented");assert!(!current(&wrong));
}
#[test] fn preview_requires_original_full_cropped_before_and_actual_geometry_proof() {
    let req=preview_request_fixture();let c=current_proof(&captured());let v=preview_fixture();assert!(preview(&v,&req,&c));
    let mut wrong=v.clone();wrong["before"]=captured()["source"]["image"].clone();assert!(!preview(&wrong,&req,&c));
    wrong=v.clone();wrong["after"]["source_height"]=json!(8);assert!(!preview(&wrong,&req,&c));
    wrong=v.clone();wrong["plan"]["achieved"]["head_fraction"]=json!(0.9);assert!(!preview(&wrong,&req,&c));
    wrong=v.clone();wrong["plan"]["rect_normalized"][0]=json!(0.25);assert!(!preview(&wrong,&req,&c));
    wrong=v;wrong["plan"]["backend"]=json!("python-reference-unrun");assert!(!preview(&wrong,&req,&c));
}
#[test] fn copy_mode_extra_fields_and_wrong_commit_document_never_confirm_apply() {
    let c=current_proof(&captured());let p=preview_fixture();
    let req=parse_request(&json!({"cmd":"portrait_crop","action":"apply","request_id":"apply-fixture","session_id":c["session_id"],
        "capture_sha256":c["capture_sha256"],"preview_request_id":p["preview_request_id"],"preview_token":p["preview_token"],
        "candidate_sha256":p["candidate_sha256"],"before_image_sha256":p["before"]["sha256"],"after_image_sha256":p["after"]["sha256"],"review":"full_before_after_confirmed"})).unwrap();
    assert!(apply_matches(&req,&p,&c));let mut result=event(&req,"committed");
    result["result"]=json!({"status":"applied","document_id":"document-fixture","revision":"13"});result["preview_token"]=p["preview_token"].clone();
    result["candidate_sha256"]=p["candidate_sha256"].clone();result["original_request_id"]=json!(req.id);result["recovered"]=json!(false);
    assert!(valid_result(&result,&req,None,Some(&c)));
    result["result"]["document_id"]=json!("another-document");assert!(!valid_result(&result,&req,None,Some(&c)));
    let mut changed=req.envelope;changed["return_mode"]=json!("new_image");assert!(parse_request(&changed).is_err());
}
