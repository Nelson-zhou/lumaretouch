// SPDX-License-Identifier: GPL-3.0-or-later
//! AUTHORED / UNRUN. Source expectations only, not rendered-photo acceptance.
use super::*;
fn sha(c:char)->String {std::iter::repeat(c).take(64).collect()}
fn owner_fixture()->Value {json!({"document_id":"source-document","document_epoch":"source-epoch","document_revision":"18446744073709551615",
    "source":{"sha256":sha('a'),"width":2,"height":2,"orientation":"exif_normalized_once"}})}
fn command_fixture(action:&str)->Value {
    match action {
        "prepare_manual_plane"=>json!({"version":2,"action":action,"request_id":"manual-plane","session_id":"session-one","owner":owner_fixture(),"depth_value":0.5,"acknowledged_manual":true}),
        "preview"=>json!({"version":2,"action":action,"request_id":"preview-one","session_id":"session-one","owner":owner_fixture(),"recipe":recipe_fixture()}),
        "apply"=>json!({"version":2,"action":action,"request_id":"apply-one","session_id":"session-one","owner":owner_fixture(),"token":"preview-token",
            "recipe_sha256":sha('c'),"before_sha256":image_fixture(10)["sha256"],"after_sha256":image_fixture(20)["sha256"],"reviewed":true,"return_mode":"new_image","result_source_sha256":sha('b')}),
        "cancel"=>json!({"version":2,"action":action,"request_id":"cancel-one","session_id":"session-one","owner":owner_fixture(),"token":null}),
        _=>panic!("fixture action"),
    }
}
fn request_fixture(action:&str)->Request {
    if action=="current" {return parse_request(&json!({"cmd":"lens_blur","action":action,"request_id":"current-one"})).unwrap();}
    let command=command_fixture(action);
    parse_request(&json!({"cmd":"lens_blur","action":if matches!(action,"apply"|"cancel"){"submit"}else{action},"request_id":command["request_id"],"command":command})).unwrap()
}
fn provenance_fixture()->Value {json!({"kind":"manual","method":"user_defined_plane","depth_value":0.5,"acknowledgement_id":"manual-plane"})}
fn recipe_fixture()->Value {json!({"version":1,"operation_id":OPERATION,"source":owner_fixture()["source"],
    "depth":{"token":"depth-token","sha256":depth_fixture()["raster"]["sha256"],"provenance":provenance_fixture()},
    "aperture":"circular_disk","max_radius_px":4,"focus":{"mode":"interval","near":0.1,"far":0.3,"point":null},
    "depth_falloff":0.2,"occlusion_tolerance":0.02,"rotation_radians":0,"refinements":[]})}
fn depth_fixture()->Value {
    let bytes=[0,128,0,128,0,128,0,128];
    json!({"version":1,"token":"depth-token","owner":owner_fixture(),"convention":"near-zero-far-one","mapping":"normalized_full_frame_pixel_centres",
        "orientation":"exif_normalized_once","raster":{"format":"u16-le","width":2,"height":2,"sha256":digest(&bytes),"base64":STANDARD.encode(bytes)},
        "provenance":provenance_fixture(),"subject_focus":null})
}
fn chunk(bytes:&mut Vec<u8>,tag:&[u8;4],payload:&[u8]) {
    bytes.extend_from_slice(&(payload.len() as u32).to_be_bytes());let start=bytes.len();bytes.extend_from_slice(tag);bytes.extend_from_slice(payload);
    let checksum=crc(&bytes[start..]);bytes.extend_from_slice(&checksum.to_be_bytes());
}
/// Tiny authored PNG input, not an output of the real lens renderer. Correct
/// chunk framing/CRC/adler is needed to exercise transport integrity gates.
fn image_fixture(tone:u8)->Value {
    let mut bytes=vec![137,80,78,71,13,10,26,10];chunk(&mut bytes,b"IHDR",&[0,0,0,2,0,0,0,2,8,2,0,0,0]);
    let raw=[0,tone,tone,tone,tone,tone,tone,0,tone,tone,tone,tone,tone,tone];
    let mut zlib=vec![0x78,0x01,0x01,14,0,0xf1,0xff];zlib.extend_from_slice(&raw);
    let (mut a,mut b)=(1u32,0u32);for byte in raw {a=(a+u32::from(byte))%65521;b=(b+a)%65521;}zlib.extend_from_slice(&((b<<16)|a).to_be_bytes());
    chunk(&mut bytes,b"IDAT",&zlib);chunk(&mut bytes,b"IEND",&[]);
    json!({"mime":"image/png","width":2,"height":2,"sha256":digest(&bytes),"base64":STANDARD.encode(bytes)})
}
fn review_fixture()->Value {json!({"version":2,"request_id":"preview-one","session_id":"session-one","token":"preview-token","owner":owner_fixture(),
    "recipe":recipe_fixture(),"recipe_sha256":sha('c'),"result_source_sha256":sha('b'),"before":image_fixture(10),"after":image_fixture(20),"notes":["Manual plane, not AI depth"]})}
fn receipt_fixture()->Value {let c=command_fixture("apply");json!({"version":2,"request_id":c["request_id"],"session_id":c["session_id"],"action":"apply","owner":c["owner"],"token":c["token"],
    "phase":"done","outcome_unknown":false,"outcome":"applied","message":"New image published with original provenance",
    "recipe_sha256":c["recipe_sha256"],"before_sha256":c["before_sha256"],"after_sha256":c["after_sha256"],"return_mode":"new_image",
    "copied_original_document_id":c["owner"]["document_id"],"result_document_id":"distinct-result","result_revision":"0","result_source_sha256":c["result_source_sha256"],"no_change":false})}

#[test] fn raw_duplicate_fields_nonfinite_and_trailing_json_fail_closed() {
    for raw in [r#"{"request_id":"x","request_id":"x"}"#,r#"{"owner":{"document_id":"x","document_id":"x"}}"#,"[NaN]","[Infinity]","[1e999]","{} {}"] {
        assert!(unique_json(raw,1024).is_err());
    }
    assert!(unique_json("{}",1).is_err());
}
#[test] fn exact_request_envelope_and_protocol_two_only() {
    for action in ["current","prepare_manual_plane","preview","apply","cancel"] {assert!(parse_request(&request_fixture(action).envelope).is_ok());}
    let mut v=request_fixture("preview").envelope;v["command"]["version"]=json!(1);assert!(parse_request(&v).is_err());
    v=request_fixture("apply").envelope;v["action"]=json!("apply");assert!(parse_request(&v).is_err());
    v=request_fixture("preview").envelope;v["unknown_field"]=json!(true);assert!(parse_request(&v).is_err());
    v=request_fixture("preview").envelope;v["request_id"]=json!("different");assert!(parse_request(&v).is_err());
}
#[test] fn owner_revision_is_exact_u64_decimal_string_not_js_number() {
    let v=owner_fixture();assert!(owner(&v));
    for invalid in [json!(18446744073709551615u64),json!("18446744073709551616"),json!("01"),json!("-1"),json!("1.0")] {
        let mut v=v.clone();v["document_revision"]=invalid;assert!(!owner(&v));
    }
}
#[test] fn capability_requires_actual_known_unique_kernels_and_no_extra_claim() {
    let mut v=json!({"version":1,"operation_id":OPERATION,"status":"available","kernels":["circular_disk"],"reason":"Native ABI verified"});assert!(capability(&v));
    v["kernels"]=json!(["circular_disk","circular_disk"]);assert!(!capability(&v));
    v["kernels"]=json!(["unmeasured_lens"]);assert!(!capability(&v));
    v["kernels"]=json!([]);assert!(!capability(&v));v["status"]=json!("unavailable");assert!(capability(&v));
    v["ai_depth_ready"]=json!(true);assert!(!capability(&v));
}
#[test] fn source_grid_png_hash_crc_dimensions_and_complete_bytes_are_required() {
    let src=owner_fixture()["source"].clone();let v=image_fixture(10);assert!(image(&v,&src));
    let mut wrong=v.clone();wrong["sha256"]=json!(sha('0'));assert!(!image(&wrong,&src));
    wrong=v.clone();wrong["width"]=json!(3);assert!(!image(&wrong,&src));
    let mut bytes=STANDARD.decode(v["base64"].as_str().unwrap()).unwrap();bytes[30]^=1;
    wrong=v.clone();wrong["base64"]=json!(STANDARD.encode(&bytes));wrong["sha256"]=json!(digest(&bytes));assert!(!image(&wrong,&src));
    let mut bytes=STANDARD.decode(v["base64"].as_str().unwrap()).unwrap();bytes.push(0);
    wrong=v;wrong["base64"]=json!(STANDARD.encode(&bytes));wrong["sha256"]=json!(digest(&bytes));assert!(!image(&wrong,&src));
}
#[test] fn manual_plane_is_real_exact_bytes_and_never_an_ai_label() {
    let own=owner_fixture();let v=depth_fixture();assert!(depth(&v,&own));
    let mut wrong=v.clone();wrong["provenance"]["depth_value"]=json!(0.25);assert!(!depth(&wrong,&own));
    wrong=v.clone();wrong["provenance"]=json!({"kind":"model","model_id":"no-model","model_sha256":sha('f'),"inference_id":"invented"});assert!(!depth(&wrong,&own));
    wrong=v;wrong["owner"]["document_revision"]=json!("0");assert!(!depth(&wrong,&own));
    let mut c=command_fixture("prepare_manual_plane");c["acknowledged_manual"]=json!(false);assert!(!command(&c));
}
#[test] fn preview_requires_full_exact_recipe_owner_and_source_bound_images() {
    let c=command_fixture("preview");let r=review_fixture();assert!(review(&r,&c));
    for key in ["recipe_sha256","result_source_sha256"] {let mut wrong=r.clone();wrong[key]=json!("bad");assert!(!review(&wrong,&c));}
    let mut wrong=r.clone();wrong["recipe"]["max_radius_px"]=json!(5);assert!(!review(&wrong,&c));
    wrong=r.clone();wrong["owner"]["source"]["sha256"]=json!(sha('e'));assert!(!review(&wrong,&c));
    wrong=r;wrong["before"]["sha256"]=json!(sha('e'));assert!(!review(&wrong,&c));
}
#[test] fn apply_must_redeem_exact_review_and_canonical_full_output_not_png_hash() {
    let req=request_fixture("apply");let r=review_fixture();assert!(apply_matches(&req,&r));
    for key in ["recipe_sha256","before_sha256","after_sha256","result_source_sha256"] {
        let mut v=req.envelope.clone();v["command"][key]=json!(sha('e'));let changed=parse_request(&v).unwrap();assert!(!apply_matches(&changed,&r));
    }
    let mut v=req.envelope.clone();v["command"]["result_source_sha256"]=r["after"]["sha256"].clone();assert!(!apply_matches(&parse_request(&v).unwrap(),&r));
}
#[test] fn new_copy_receipt_cannot_claim_original_history_entry_or_same_document() {
    let c=command_fixture("apply");let v=receipt_fixture();assert!(receipt(&v,&c));
    for (key,bad) in [("result_document_id",json!("source-document")),("copied_original_document_id",json!("other-source")),("result_revision",json!(0)),("no_change",json!(true)),("result_source_sha256",json!(sha('f')))] {
        let mut wrong=v.clone();wrong[key]=bad;assert!(!receipt(&wrong,&c));
    }
    let mut wrong=v;wrong["history_entry_id"]=json!("fabricated-source-history");assert!(!receipt(&wrong,&c));
}
#[test] fn neutral_output_still_requires_a_distinct_result_document() {
    let mut c=command_fixture("apply");c["result_source_sha256"]=c["owner"]["source"]["sha256"].clone();
    let mut v=receipt_fixture();v["result_source_sha256"]=c["result_source_sha256"].clone();v["no_change"]=json!(true);assert!(receipt(&v,&c));
    v["result_document_id"]=json!("source-document");assert!(!receipt(&v,&c));
}
#[test] fn receipt_query_needs_fresh_outer_id_and_exact_original_write() {
    let c=command_fixture("apply");let mut v=json!({"cmd":"lens_blur","action":"receipt","request_id":"query-one","command":c});
    let req=parse_request(&v).unwrap();assert!(!req.apply());assert!(!req.write());
    let response=json!({"event":EVENT,"request_id":"query-one","status":"ready","receipt":receipt_fixture()});assert!(valid_result(&response,&req));
    v["request_id"]=json!("apply-one");assert!(parse_request(&v).is_err());
    let mut wrong=response;wrong["receipt"]["owner"]["document_epoch"]=json!("other-engine");assert!(!valid_result(&wrong,&req));
}
#[test] fn generic_rejection_or_cancel_ack_cannot_settle_a_write() {
    let req=request_fixture("apply");
    assert!(!valid_result(&json!({"event":EVENT,"request_id":req.id,"status":"rejected","message":"Not an exact write receipt"}),&req));
    let mut v=receipt_fixture();v["outcome"]=json!("cancelled");assert!(!receipt(&v,req.inner()));
    let pending=pending(&req,"unknown","Transport outcome uncertain");assert!(valid_result(&pending,&req));assert!(!terminal(&pending));
}
