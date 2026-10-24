//! Preset-only collarbone image/ack protocol. No numeric or photographic acceptance.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, revision};
pub(crate) const OP: &str = "lnx.collarbone.v1";
pub(crate) const ACK: &str = "collarbone_preset_ack";
fn fields(value:&Value,names:&[&str])->bool {
    value.as_object().is_some_and(|map|map.len()==names.len()&&names.iter().all(|key|map.contains_key(*key)))
}
fn text(value:&Value)->bool {
    value.as_str().is_some_and(|v|!v.trim().is_empty()&&v.len()<=128&&!v.chars().any(char::is_control))
}
pub(crate) fn selected(value:&Value)->bool {
    value["module_scope"].as_array().is_some_and(|ops|ops.iter().any(|op|op==OP))
}
fn image_request(value:&Value)->bool {
    fields(value,&["cmd","action","request_id","id","document_id","preflight_token","revision","side","sha256"])
        &&value["cmd"]=="preset"&&value["action"]=="collarbone_visual"&&text(&value["request_id"])
        &&text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)
        &&revision(&value["revision"])&&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
}
fn size(value:&Value)->Option<(u64,u64)> {
    let array=value.as_array()?;if array.len()!=2{return None;}
    let (w,h)=(array[0].as_u64()?,array[1].as_u64()?);
    (w>0&&h>0&&w<=u32::MAX as u64&&h<=u32::MAX as u64).then_some((w,h))
}
fn compact_image(value:&Value,output:(u64,u64))->bool {
    if !fields(value,&["mime","width","height","sha256"])||value["mime"]!="image/png"||!hex(&value["sha256"],64){return false;}
    let edge=output.0.max(output.1);
    let scaled=|n:u64|{if edge<=1024{return n;}let q=n*1024/edge;let r=n*1024%edge;(q+u64::from(r*2>edge||(r*2==edge&&q%2==1))).max(1)};
    value["width"].as_u64()==Some(scaled(output.0))&&value["height"].as_u64()==Some(scaled(output.1))
}
fn image(value:&Value)->bool {
    use base64::{engine::general_purpose::STANDARD,Engine as _};
    use sha2::{Digest,Sha256};
    if !fields(value,&["mime","width","height","sha256","base64"])||value["mime"]!="image/png"||!hex(&value["sha256"],64){return false;}
    let (Some(w),Some(h),Some(encoded))=(value["width"].as_u64(),value["height"].as_u64(),value["base64"].as_str()) else{return false;};
    if w==0||h==0||w>1024||h>1024||encoded.is_empty()||encoded.len()>5_592_408{return false;}
    let Ok(raw)=STANDARD.decode(encoded) else{return false;};
    raw.len()<=4*1024*1024&&STANDARD.encode(&raw)==encoded&&crate::torso_transfer_protocol::png(&raw,w as u32,h as u32)
        &&format!("{:x}",Sha256::digest(&raw))==value["sha256"].as_str().unwrap()
}
pub(crate) fn acknowledgment(value:&Value)->bool {
    fields(value,&["document_id","revision","before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"])
        &&text(&value["document_id"])&&revision(&value["revision"])
        &&["before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"].iter().all(|key|hex(&value[*key],64))
}
pub(crate) fn command(value:&Value)->Result<(),String> {
    if value["cmd"]!="preset" {return Ok(());}
    if value["action"]=="collarbone_visual" {
        return if image_request(value){Ok(())}else{Err("Preset image retrieval requires its exact preset/load/token/side identity".into())};
    }
    if ["revision","side","sha256"].iter().any(|key|value.get(*key).is_some()) {
        return Err("Preset image coordinates cannot accompany another action".into());
    }
    if let Some(ack)=value.get(ACK) {
        let Some(map)=value.as_object() else{return Err("Invalid preset acknowledgment".into());};
        let allowed=["cmd","action","request_id","id","document_id","preflight_token",ACK,"xmp_review_ack","spill_review_ack","shadow_review_ack","torso_review_ack","waist_review_ack","head_review_ack"];
        if value["action"]!="apply"||!acknowledgment(ack)||!text(&value["request_id"])||!text(&value["id"])||!text(&value["document_id"])
            ||!hex(&value["preflight_token"],32)||map.keys().any(|key|!allowed.contains(&key.as_str())) {
            return Err("Preset collarbone apply requires its exact frozen preset acknowledgment".into());
        }
    }
    if value.get("collarbone_review_ack").is_some(){return Err("A batch collarbone acknowledgment cannot authorize a preset".into());}
    Ok(())
}
pub(crate) fn read_only(value:&Value)->bool {
    if image_request(value){return true;}
    if value["cmd"]!="preset"||value["action"]!="preflight"||!selected(value)||command(value).is_err(){return false;}
    let Some(map)=value.as_object() else{return false;};
    let Some(ops)=value["module_scope"].as_array() else{return false;};
    let required=["cmd","action","request_id","id","document_id","module_scope"];
    required.iter().all(|key|map.contains_key(*key))
        &&map.keys().all(|key|required.contains(&key.as_str())||key=="local_mask_transfer")
        &&text(&value["request_id"])&&text(&value["id"])&&text(&value["document_id"])
        &&!ops.is_empty()&&ops.len()<=256&&ops.iter().all(text)
        &&ops.iter().enumerate().all(|(i,op)|!ops[..i].contains(op))
}
pub(crate) fn binding(value:&Value)->Result<Option<Value>,String> {
    command(value)?;
    if value["cmd"]!="preset"{return Ok(None);}
    if image_request(value){return Ok(Some(json!({"id":value["id"],"document_id":value["document_id"],
        "preflight_token":value["preflight_token"],"revision":value["revision"],"side":value["side"],"sha256":value["sha256"]})));}
    if value.get(ACK).is_some(){
        let mut out=json!({"id":value["id"],"document_id":value["document_id"],"preflight_token":value["preflight_token"],(ACK):value[ACK]});
        for key in ["xmp_review_ack","spill_review_ack","shadow_review_ack","torso_review_ack","waist_review_ack","head_review_ack"] {
            if let Some(v)=value.get(key){out[key]=v.clone();}
        }
        return Ok(Some(out));
    }
    if value["action"]=="preflight"&&selected(value){return Ok(Some(json!({"id":value["id"],"document_id":value["document_id"],"module_scope":value["module_scope"]})));}
    Ok(None)
}
fn visual(value:&Value,document:&Value,revision_value:&Value,source:&Value)->bool {
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
fn face(value:&Value)->bool {
    fields(value,&["asset_sha256","face_instance_id","analysis_revision"])&&hex(&value["asset_sha256"],64)
        &&text(&value["face_instance_id"])&&value["analysis_revision"].as_u64().is_some()
}
fn coverage(value:&Value,reference:&Value)->bool {
    if !fields(value,&["version","support_transfer","targets"])||value["version"].as_u64()!=Some(1)||value["support_transfer"]!="none" {return false;}
    let Some(rows)=value["targets"].as_array() else{return false;};
    if rows.len()!=1{return false;}
    let row=&rows[0];
    if !fields(row,&["face_ref","scope","body_review_sha256","clavicle_category","clavicle_sides"])||&row["face_ref"]!=reference{return false;}
    let Some(sides)=row["clavicle_sides"].as_array() else{return false;};
    match row["scope"].as_str(){
        Some("neutral-no-effect")=>row["body_review_sha256"].is_null()&&row["clavicle_category"].is_null()&&sides.is_empty(),
        Some("reviewed-clavicle-only")=>hex(&row["body_review_sha256"],64)&&matches!(row["clavicle_category"].as_str(),Some("female"|"elder_female"))
            &&(1..=2).contains(&sides.len())&&sides.iter().all(|side|matches!(side.as_str(),Some("left"|"right")))
            &&(sides.len()==1||sides[0]!=sides[1]),
        _=>false,
    }
}
pub(crate) fn review(value:&Value)->bool {
    let p=&value["collarbone_preset"];let owner=&p["owner"];let doc=&owner["document"];
    if !fields(p,&["version","preset_sha256","applies_sha256","load_id","owner","face_ref","coverage","visual"])
        ||p["version"].as_u64()!=Some(1)||p["load_id"]!=value["document_id"]||!text(&p["load_id"])
        ||!hex(&p["preset_sha256"],64)||!hex(&p["applies_sha256"],64)
        ||!fields(owner,&["document","people_scope","state_revision","association_revision","graph_sha256","source_proof"])
        ||!fields(doc,&["document_id","epoch","revision"])||!text(&doc["document_id"])||!text(&doc["epoch"])
        ||doc["revision"].as_u64().map(|n|n.to_string())!=value["revision"].as_str().map(str::to_owned)
        ||!(owner["people_scope"]=="project"||owner["people_scope"]==doc["document_id"])
        ||!owner["state_revision"].is_u64()||!owner["association_revision"].is_u64()||!hex(&owner["graph_sha256"],64)
        ||!face(&p["face_ref"])||p["face_ref"]["asset_sha256"]!=owner["source_proof"]["asset_sha256"]
        ||!coverage(&p["coverage"],&p["face_ref"])||!visual(&p["visual"],&doc["document_id"],&value["revision"],&owner["source_proof"])
        ||p["visual"]["source_proof"]!=value["source_proof"] {return false;}
    p["visual"]["coverage_sha256"].as_str()==Some(crate::batch_api::collarbone::request_digest(&p["coverage"]).as_str())
}
pub(crate) fn receipt(value:&Value)->bool {
    if value["action"]=="collarbone_visual" {
        if value["success"]!=true{return true;}
        return text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)&&revision(&value["revision"])
            &&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
            &&value["image"]["sha256"]==value["sha256"]&&image(&value["image"]);
    }
    if !value["collarbone_preset"].is_null()&&(value["action"]!="preflight"||value["success"]!=true||!selected(value)){return false;}
    if value["action"]=="preflight"&&value["success"]==true&&selected(value){return hex(&value["preflight_token"],32)&&review(value);}
    if let Some(ack)=value.get(ACK){return value["action"]=="apply"&&selected(value)&&acknowledgment(ack)&&hex(&value["preflight_token"],32);}
    !(value["action"]=="apply"&&selected(value)&&(value["success"]==true||value["outcome_unknown"]==true))
}
#[cfg(test)]
#[path="collarbone_preset_protocol_tests.rs"]
mod tests;
