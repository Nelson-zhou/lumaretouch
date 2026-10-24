//! AUTHORED / UNRUN source fixtures, not cargo/test evidence.
use super::*;
fn request(action: &str, payload: Value) -> Value {
    json!({"cmd":"people", "action":action, "payload":payload, "request_id":"request",
        "document_id":"d".repeat(32), "document_epoch":"epoch", "document_revision":7,
        "state_revision":11, "association_revision":3,
        "target":{"scope":"face", "target_id":"face", "face_ref":{"asset_sha256":"a".repeat(64), "face_instance_id":"face", "analysis_revision":2}}})
}
fn painted() -> Value {json!({"left":{"visible":true, "unoccluded":true, "ownership_confirmed":true,
    "recipe":{"version":1, "domain":"source-normalized", "objects":[{"id":"left-1", "name":"人物左眼卧蚕保护", "enabled":true,
        "operation":"add", "kind":"brush", "opacity":1.0, "feather":0, "points":[[0.5,0.55]], "axes":[[0.0015,0],[0,0.002]]}]}}})}
#[test] fn reference_and_images_are_reads_but_confirm_is_never_a_read() {
    assert!(read_only(&request("eye_bag_reference", json!({}))));
    assert!(read_only(&request("eye_bag_image", json!({"token":"b".repeat(32),"side":"support","sha256":"c".repeat(64)}))));
    assert!(!read_only(&request("eye_bag_confirm", json!({"token":"b".repeat(32),"ack":{
        "review_sha256":"c".repeat(64),"before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64),"support_overlay_sha256":"f".repeat(64)}}))));
}
#[test] fn bounded_manual_vectors_keep_hard_core_and_independent_identity() {
    assert!(eyes(&painted(), false));
    let mut value = painted(); value["left"]["recipe"]["objects"][0]["opacity"] = json!(0.5); assert!(!eyes(&value, false));
    let mut value = painted(); value["left"]["recipe"]["objects"][0]["operation"] = json!("intersect"); assert!(!eyes(&value, false));
    let mut value = painted(); value["left"]["visible"] = json!(false); assert!(!eyes(&value, false));
    let mut value = painted(); value["eye_light_visibility"] = value["left"].clone(); assert!(!eyes(&value, false));
}
#[test] fn positive_preview_and_hash_ack_are_required_neutral_uses_safe_patch() {
    let mut command_value = request("eye_bag_preview", json!({"recipe":{"version":2,"amount":0.5,"preserve":1}, "eyes":painted(),"replace_legacy":false}));
    assert!(command(&command_value).is_ok()); assert!(binding(&command_value).unwrap().is_some());
    command_value["payload"]["recipe"]["amount"] = json!(0); assert!(command(&command_value).is_err());
    assert!(command(&request("eye_bag_confirm", json!({"token":"b".repeat(32),"ack":{"reviewed":true}}))).is_err());
}
#[test] fn malformed_read_cannot_bypass_recovery_fence() {
    let mut command_value = request("eye_bag_reference", json!({})); command_value["extra"] = json!(true);
    assert!(!read_only(&command_value));
    let mut command_value = request("eye_bag_reference", json!({})); command_value["target"]["scope"] = json!("all_people");
    assert!(!read_only(&command_value));
}
#[test] fn support_metadata_keeps_canonical_and_decoded_source_distinct() {
    let source = json!({"source_width":4001,"source_height":3001,"decoded_width":4000,"decoded_height":3000});
    let image = json!({"mime":"image/png","width":1024,"height":768,"sha256":"c".repeat(64)});
    assert!(support_mapping(&source,&image,(4001,3001)));
    assert!(!support_mapping(&source,&image,(4000,3000)));
    let bad = json!({"source_width":4001,"source_height":3001,"decoded_width":1000,"decoded_height":1000});
    assert!(!support_mapping(&bad,&image,(4001,3001)));
}

#[test] fn integer_and_float_spellings_keep_the_same_scalar_recipe() {
    assert!(same_recipe(&json!({"version":2,"amount":1,"preserve":1}), &json!({"version":2,"amount":1.0,"preserve":1.0})));
    assert!(!same_recipe(&json!({"version":2,"amount":1,"preserve":1}), &json!({"version":2,"amount":1.0,"preserve":0.0})));
}

fn crop_metadata() -> Value {
    let image = json!({"mime":"image/png","width":2,"height":3,"sha256":"c".repeat(64)});
    json!({"version":1,"token":"b".repeat(32),"mapping":"source_pixel_edges","orientation":"exif_normalized_once",
        "source_sha256":"a".repeat(64),"source_width":4001,"source_height":3001,"input_stage":"committed_repair",
        "snapshot_sha256":"d".repeat(64),"display_encoding":"srgb_rgb8","sampling":"one_source_pixel_per_image_pixel",
        "eyes":{"left":{"rect":[10,20,2,3],"image":image},"right":{"rect":[3999,2998,2,3],"image":image}}})
}
#[test] fn source_crop_metadata_binds_exact_edges_native_sampling_and_source() {
    let source = json!({"sha256":"a".repeat(64),"width":4001,"height":3001});
    let value = crop_metadata(); assert!(source_crops(&value,&source));
    for (path, bad) in [("/mapping",json!("normalized_full_frame")),("/sampling",json!("upsampled")),
        ("/display_encoding",json!("native_rgb16")),("/input_stage",json!("edited_canvas")),
        ("/source_width",json!(4000)),("/source_sha256",json!("e".repeat(64))),
        ("/eyes/left/rect/0",json!(-1)),("/eyes/left/rect/0",json!(0.5)),
        ("/eyes/right/rect/0",json!(4000)),("/eyes/left/image/width",json!(1)),
        ("/token",json!("b".repeat(31))),("/snapshot_sha256",json!("invalid"))] {
        let mut changed=value.clone(); *changed.pointer_mut(path).unwrap()=bad; assert!(!source_crops(&changed,&source),"{path}");
    }
    let mut missing=value.clone(); missing["eyes"].as_object_mut().unwrap().remove("right"); assert!(!source_crops(&missing,&source));
    let mut inline=value; inline["eyes"]["left"]["image"]["base64"]=json!("AAAA"); assert!(!source_crops(&inline,&source));
}
#[test] fn source_crop_total_budget_refuses_two_large_crops_without_downsampling() {
    let source=json!({"sha256":"a".repeat(64),"width":4001,"height":3001});
    let mut value=crop_metadata();
    for side in ["left","right"] {
        value["eyes"][side]["rect"]=json!([0,0,2000,1000]);
        value["eyes"][side]["image"]["width"]=json!(2000); value["eyes"][side]["image"]["height"]=json!(1000);
    }
    assert!(source_crops(&value,&source));
    value["eyes"]["right"]["rect"][3]=json!(1001); value["eyes"]["right"]["image"]["height"]=json!(1001);
    assert!(!source_crops(&value,&source));
}
#[test] fn native_crop_fetch_is_read_only_and_cannot_request_review_or_another_eye() {
    let value=request("eye_bag_source_image",json!({"token":"b".repeat(32),"side":"left","sha256":"c".repeat(64)}));
    assert!(read_only(&value)); assert!(binding(&value).unwrap().is_some());
    let mut bad=value.clone(); bad["payload"]["side"]=json!("before"); assert!(command(&bad).is_err());
    let mut bad=value; bad["payload"]["rect"]=json!([0,0,1,1]); assert!(command(&bad).is_err());
}
#[test] fn source_crop_png_refuses_forged_hash_incomplete_bytes_and_precision_claim() {
    let image=json!({"mime":"image/png","width":1,"height":1,"sha256":"c".repeat(64),"base64":"iVBORw=="});
    assert!(crop_image(&image,1,1).is_none());
    let mut large=image.clone(); large["width"]=json!(2049); assert!(crop_image(&large,2049,1).is_none());
    let mut bad=image; bad["base64"]=json!("A".repeat(5_592_409)); assert!(crop_image(&bad,1,1).is_none());
}

/// Original transport fixture: one RGB pixel, stored zlib block, not a photo.
fn crop_png() -> Value {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest, Sha256};
    fn chunk(bytes: &mut Vec<u8>, kind: &[u8], data: &[u8]) {
        bytes.extend_from_slice(&(data.len() as u32).to_be_bytes());
        let start=bytes.len(); bytes.extend_from_slice(kind); bytes.extend_from_slice(data);
        let mut crc=0xffff_ffffu32;
        for byte in &bytes[start..] {crc ^= u32::from(*byte); for _ in 0..8 {crc=(crc>>1)^((0u32.wrapping_sub(crc&1))&0xedb8_8320);}}
        bytes.extend_from_slice(&(!crc).to_be_bytes());
    }
    let mut bytes=b"\x89PNG\r\n\x1a\n".to_vec();
    chunk(&mut bytes,b"IHDR",&[0,0,0,1,0,0,0,1,8,2,0,0,0]);
    // Filter byte0 + RGB(32,64,96); Adler32 =0x014400c1.
    chunk(&mut bytes,b"IDAT",&[0x78,0x01,0x01,4,0,0xfb,0xff,0,32,64,96,0x01,0x44,0x00,0xc1]);
    chunk(&mut bytes,b"IEND",&[]);
    json!({"mime":"image/png","width":1,"height":1,"sha256":format!("{:x}",Sha256::digest(&bytes)),"base64":STANDARD.encode(bytes)})
}
#[test] fn native_source_crop_receipt_keeps_exact_request_token_eye_digest_and_rgb_bytes() {
    let image=crop_png(); assert!(crop_image(&image,1,1).is_some());
    let request=request("eye_bag_source_image",json!({"token":"b".repeat(32),"side":"left","sha256":image["sha256"]}));
    let envelope=binding(&request).unwrap().unwrap();
    let value=json!({"action":"eye_bag_source_image","document_id":request["document_id"],"success":true,
        "eye_bag_request":envelope["eye_bag_request"],"payload":{"kind":"eye_bag_source_image","token":"b".repeat(32),
            "side":"left","snapshot_sha256":"d".repeat(64),"image":image}});
    assert!(receipt(&value));
    for (path,bad) in [("/payload/side",json!("right")),("/payload/token",json!("e".repeat(32))),
        ("/payload/snapshot_sha256",json!("invalid")),("/payload/image/sha256",json!("e".repeat(64))),
        ("/payload/image/width",json!(2))] {
        let mut changed=value.clone(); *changed.pointer_mut(path).unwrap()=bad; assert!(!receipt(&changed),"{path}");
    }
}
