// SPDX-License-Identifier: GPL-3.0-or-later
//! Preset-only eye-bag v2 image/ack protocol; target-owned ridge evidence only. No numeric or photographic acceptance.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, revision};
use super::visual::{fields,text,image,visual,face};
#[path="eye_bag_preset_alias_protocol.rs"]
mod alias;
pub(crate) const OP: &str = "lnx.eye_bags.v2";
pub(crate) const ACK: &str = "eye_bag_preset_ack";
pub(crate) fn selected(value:&Value)->bool {
    value["module_scope"].as_array().is_some_and(|ops|ops.iter().any(|op|op==OP))
}
fn image_request(value:&Value)->bool {
    let mut keys=vec!["cmd","action","request_id","id","document_id","preflight_token","revision","side","sha256"];
    if value.get("member_document_id").is_some()||value.get("member_revision").is_some(){
        keys.extend(["member_document_id","member_revision"]);
        if !alias::image_identity(value){return false;}
    }
    fields(value,&keys)
        &&value["cmd"]=="preset"&&value["action"]=="eye_bag_visual"&&text(&value["request_id"])
        &&text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)
        &&revision(&value["revision"])&&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
}
pub(crate) fn acknowledgment(value:&Value)->bool {
    if value.get("members").is_some(){return alias::acknowledgment(value);}
    fields(value,&["document_id","revision","before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256","replace_legacy"])
        &&value["replace_legacy"].is_boolean()&&text(&value["document_id"])&&revision(&value["revision"])
        &&["before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"].iter().all(|key|hex(&value[*key],64))
}
/// Only the new alias form requires every failure to retain the exact request.
/// A missing member or ACK must not be reclassified as an ordinary local edit.
pub(crate) fn strict_failure_identity(value:&Value)->bool {
    value["cmd"]=="preset"&&(value[ACK].get("members").is_some()
        ||(value["action"]=="eye_bag_visual"&&value.get("member_document_id").is_some()))
}
pub(crate) fn retained_alias_publication(value:&Value)->Option<Value> {alias::retained_publication(value)}
pub(crate) fn command(value:&Value)->Result<(),String> {
    if value["cmd"]!="preset" {return Ok(());}
    if value["action"]=="eye_bag_visual" {
        return if image_request(value){Ok(())}else{Err("Eye-bag preset image requires exact preset/load/token/side identity".into())};
    }
    if value.get("member_document_id").is_some()||value.get("member_revision").is_some(){
        return Err("Preset member coordinates belong only to an immutable eye-bag image read".into());
    }
    if value.get("eye_bag_replace_legacy").is_some() && !(value["action"]=="preflight"&&selected(value)&&value["eye_bag_replace_legacy"].is_boolean()) {
        return Err("Eye-bag legacy replacement is an explicit preflight-only choice".into());
    }
    if let Some(ack)=value.get(ACK) {
        let Some(map)=value.as_object() else{return Err("Invalid eye-bag preset acknowledgment".into());};
        let allowed=["cmd","action","request_id","id","document_id","preflight_token",ACK,"collarbone_preset_ack","xmp_review_ack","spill_review_ack","shadow_review_ack","torso_review_ack","waist_review_ack","head_review_ack"];
        if value["action"]!="apply"||!acknowledgment(ack)||!text(&value["request_id"])||!text(&value["id"])||!text(&value["document_id"])
            ||!hex(&value["preflight_token"],32)||map.keys().any(|key|!allowed.contains(&key.as_str())) {
            return Err("Eye-bag preset apply requires its exact frozen image acknowledgment".into());
        }
    }
    if value.get("eye_bag_review_ack").is_some(){return Err("Another eye-bag review cannot authorize a preset".into());}
    Ok(())
}
pub(crate) fn read_only(value:&Value)->bool {
    if image_request(value){return true;}
    if value["cmd"]!="preset"||value["action"]!="preflight"||!selected(value)||command(value).is_err(){return false;}
    let Some(map)=value.as_object() else{return false;};
    let Some(ops)=value["module_scope"].as_array() else{return false;};
    let required=["cmd","action","request_id","id","document_id","module_scope","eye_bag_replace_legacy"];
    required.iter().all(|key|map.contains_key(*key))
        &&map.keys().all(|key|required.contains(&key.as_str())||key=="local_mask_transfer")
        &&text(&value["request_id"])&&text(&value["id"])&&text(&value["document_id"])
        &&!ops.is_empty()&&ops.len()<=256&&ops.iter().all(text)
        &&ops.iter().enumerate().all(|(i,op)|!ops[..i].contains(op))
}
pub(crate) fn binding(value:&Value)->Result<Option<Value>,String> {
    command(value)?;
    if value["cmd"]!="preset"{return Ok(None);}
    if image_request(value){
        let mut out=json!({"id":value["id"],"document_id":value["document_id"],
            "preflight_token":value["preflight_token"],"revision":value["revision"],"side":value["side"],"sha256":value["sha256"]});
        if value.get("member_document_id").is_some(){
            out["member_document_id"]=value["member_document_id"].clone();
            out["member_revision"]=value["member_revision"].clone();
        }
        return Ok(Some(out));
    }
    if value.get(ACK).is_some(){
        let mut out=json!({"id":value["id"],"document_id":value["document_id"],"preflight_token":value["preflight_token"],(ACK):value[ACK]});
        for key in ["xmp_review_ack","spill_review_ack","shadow_review_ack","torso_review_ack","waist_review_ack","head_review_ack","collarbone_preset_ack"] {
            if let Some(v)=value.get(key){out[key]=v.clone();}
        }
        return Ok(Some(out));
    }
    if value["action"]=="preflight"&&selected(value)&&value.get("eye_bag_replace_legacy").is_some(){return Ok(Some(json!({"id":value["id"],"document_id":value["document_id"],"module_scope":value["module_scope"],"eye_bag_replace_legacy":value["eye_bag_replace_legacy"]})));}
    Ok(None)
}
fn coverage(value:&Value,reference:&Value)->bool {
    if !fields(value,&["version","support_transfer","targets"])||value["version"].as_u64()!=Some(1)||value["support_transfer"]!="none" {return false;}
    let Some(rows)=value["targets"].as_array() else{return false;};
    if rows.len()!=1{return false;}
    let row=&rows[0];
    if !fields(row,&["face_ref","scope","ridge_sha256","sides"])||&row["face_ref"]!=reference{return false;}
    let Some(sides)=row["sides"].as_array() else{return false;};
    match row["scope"].as_str(){
        Some("neutral-no-effect")=>row["ridge_sha256"].is_null()&&sides.is_empty(),
        Some("target-reviewed-ridge")=>hex(&row["ridge_sha256"],64)
            &&(sides==&vec![json!("left")]||sides==&vec![json!("right")]||sides==&vec![json!("left"),json!("right")]),
        _=>false,
    }
}
pub(crate) fn review(value:&Value)->bool {
    let p=&value["eye_bag_preset"];
    if p["version"].as_u64()==Some(2){return alias::review(value);}
    fields(p,&["version","preset_sha256","applies_sha256","load_id","owner","face_ref","coverage","visual","replace_legacy"])
        &&p["version"].as_u64()==Some(1)&&review_base(value)
}
fn review_base(value:&Value)->bool {
    let p=&value["eye_bag_preset"];let owner=&p["owner"];let doc=&owner["document"];
    if !p["replace_legacy"].is_boolean()||p["replace_legacy"]!=value["eye_bag_replace_legacy"]||p["load_id"]!=value["document_id"]||!text(&p["load_id"])
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
fn parameters(value:&Value)->bool {
    let recipe=&value["recipe"];
    fields(value,&["recipe"])&&fields(recipe,&["version","amount","preserve"])
        &&recipe["version"].as_u64()==Some(2)
        &&["amount","preserve"].iter().all(|key|recipe[*key].as_f64().is_some_and(|v|v.is_finite()&&(0.0..=1.0).contains(&v)))
}
pub(crate) fn receipt(value:&Value)->bool {
    if (value.get("eye_bag_preset_alias_review").is_some()||value.get("alias_members").is_some())
        &&(value["action"]!="apply"||value[ACK].get("members").is_none()){return false;}
    if value["action"]=="eye_bag_visual" {
        if value["success"]!=true{return true;}
        return text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)&&revision(&value["revision"])
            &&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
            &&((value.get("member_document_id").is_none()&&value.get("member_revision").is_none())||alias::image_identity(value))
            &&value["image"]["sha256"]==value["sha256"]&&image(&value["image"]);
    }
    if !value["eye_bag_preset"].is_null()&&(value["action"]!="preflight"||value["success"]!=true||!selected(value)){return false;}
    if value["action"]=="preflight"&&value["success"]==true&&selected(value){
        if !parameters(&value["applies"][OP]) {return false;}
        return if value.get("eye_bag_replace_legacy").is_some(){hex(&value["preflight_token"],32)&&review(value)}
            else {value["applies"][OP]["recipe"]["amount"].as_f64()==Some(0.)};
    }
    if let Some(ack)=value.get(ACK){
        // Expiry can discard the plan's module names, but never the submitted
        // v2 acknowledgment. Its exact bound no-write refusal is still usable.
        let scope=selected(value)||(ack.get("members").is_some()&&value["success"]==false&&value.get("module_scope").is_none());
        return value["action"]=="apply"&&scope&&acknowledgment(ack)&&hex(&value["preflight_token"],32)
            &&(ack.get("members").is_none()||alias::receipt(value));
    }
    if value["action"]=="apply"&&selected(value)&&value["success"]==true {
        return parameters(&value["after"][OP])&&value["after"][OP]["recipe"]["amount"].as_f64()==Some(0.);
    }
    true
}
#[cfg(test)]
#[path="eye_bag_preset_protocol_tests.rs"]
mod tests;
