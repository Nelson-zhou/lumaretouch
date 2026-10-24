// SPDX-License-Identifier: GPL-3.0-or-later
//! Shared image bytes and complete-render ownership structure only. No target coverage semantics.
use serde_json::Value;
use crate::original_shadow_transfer_protocol::{hex,revision};
pub(crate) fn fields(value:&Value,names:&[&str])->bool {
    value.as_object().is_some_and(|map|map.len()==names.len()&&names.iter().all(|key|map.contains_key(*key)))
}
pub(crate) fn text(value:&Value)->bool {
    value.as_str().is_some_and(|v|!v.trim().is_empty()&&v.len()<=128&&!v.chars().any(char::is_control))
}
pub(crate) fn size(value:&Value)->Option<(u64,u64)> {
    let array=value.as_array()?;if array.len()!=2{return None;}
    let (w,h)=(array[0].as_u64()?,array[1].as_u64()?);
    (w>0&&h>0&&w<=u32::MAX as u64&&h<=u32::MAX as u64).then_some((w,h))
}
pub(crate) fn compact_image(value:&Value,output:(u64,u64))->bool {
    if !fields(value,&["mime","width","height","sha256"])||value["mime"]!="image/png"||!hex(&value["sha256"],64){return false;}
    let edge=output.0.max(output.1);
    let scaled=|n:u64|{if edge<=1024{return n;}let q=n*1024/edge;let r=n*1024%edge;(q+u64::from(r*2>edge||(r*2==edge&&q%2==1))).max(1)};
    value["width"].as_u64()==Some(scaled(output.0))&&value["height"].as_u64()==Some(scaled(output.1))
}
pub(crate) fn image(value:&Value)->bool {
    use base64::{engine::general_purpose::STANDARD,Engine as _};
    use sha2::{Digest,Sha256};
    if !fields(value,&["mime","width","height","sha256","base64"])||value["mime"]!="image/png"||!hex(&value["sha256"],64){return false;}
    let (Some(w),Some(h),Some(encoded))=(value["width"].as_u64(),value["height"].as_u64(),value["base64"].as_str()) else{return false;};
    if w==0||h==0||w>1024||h>1024||encoded.is_empty()||encoded.len()>5_592_408{return false;}
    let Ok(raw)=STANDARD.decode(encoded) else{return false;};
    raw.len()<=4*1024*1024&&STANDARD.encode(&raw)==encoded&&crate::torso_transfer_protocol::png(&raw,w as u32,h as u32)
        &&format!("{:x}",Sha256::digest(&raw))==value["sha256"].as_str().unwrap()
}
pub(crate) fn visual(value:&Value,document:&Value,revision_value:&Value,source:&Value)->bool {
    if !fields(value,&["version","document_id","revision","source_proof","before_state_sha256","candidate_state_sha256",
        "before_people_sha256","candidate_people_sha256","source_size","before_output_size","after_output_size","coverage_sha256","before","after"])
        ||value["version"].as_u64()!=Some(1)||&value["document_id"]!=document||&value["revision"]!=revision_value
        ||!revision(&value["revision"])||&value["source_proof"]!=source||!crate::original_shadow_transfer_protocol::source_proof(source)
        ||!["before_state_sha256","candidate_state_sha256","before_people_sha256","candidate_people_sha256","coverage_sha256"].iter().all(|key|hex(&value[*key],64)){return false;}
    let (Some(src),Some(before),Some(after))=(size(&value["source_size"]),size(&value["before_output_size"]),size(&value["after_output_size"])) else{return false;};
    let derived=&source["creative_source"];
    (derived.is_null()||(derived["width"].as_u64()==Some(src.0)&&derived["height"].as_u64()==Some(src.1)))
        &&compact_image(&value["before"],before)&&compact_image(&value["after"],after)
}
pub(crate) fn face(value:&Value)->bool {
    fields(value,&["asset_sha256","face_instance_id","analysis_revision"])&&hex(&value["asset_sha256"],64)
        &&text(&value["face_instance_id"])&&value["analysis_revision"].as_u64().is_some()
}
