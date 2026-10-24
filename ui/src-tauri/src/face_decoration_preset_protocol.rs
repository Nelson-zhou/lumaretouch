// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact full mixed-preset face-decoration image/ack protocol. No numeric or photographic acceptance.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, revision};
use super::visual::{fields,text,image,visual,face};
pub(crate) const OP: &str = "lnx.face_decoration.v1";
pub(crate) const ACK: &str = "face_decoration_preset_ack";
pub(crate) fn selected(value:&Value)->bool {
    value["module_scope"].as_array().is_some_and(|ops|ops.iter().any(|op|op==OP))
}
fn image_request(value:&Value)->bool {
    fields(value,&["cmd","action","request_id","id","document_id","preflight_token","revision","side","sha256"])
        &&value["cmd"]=="preset"&&value["action"]=="face_decoration_visual"&&text(&value["request_id"])
        &&text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)
        &&revision(&value["revision"])&&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
}
pub(crate) fn acknowledgment(value:&Value)->bool {
    fields(value,&["document_id","revision","before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"])
        &&text(&value["document_id"])&&revision(&value["revision"])
        &&["before_sha256","after_sha256","coverage_sha256","preset_sha256","applies_sha256"].iter().all(|key|hex(&value[*key],64))
}
pub(crate) fn command(value:&Value)->Result<(),String> {
    if value["cmd"]!="preset" {return Ok(());}
    if matches!(value["action"].as_str(),Some("eye_bag_visual"|"collarbone_visual")){return Ok(());}
    if value["action"]=="face_decoration_visual" {
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
            return Err("Preset face_decoration apply requires its exact frozen preset acknowledgment".into());
        }
    }
    if value.get("face_decoration_review_ack").is_some(){return Err("A batch face_decoration acknowledgment cannot authorize a preset".into());}
    Ok(())
}
pub(crate) fn read_only(value:&Value)->bool {
    if image_request(value){return true;}
    if value["cmd"]!="preset"||value["action"]!="preflight"||command(value).is_err(){return false;}
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
    if read_only(value)&&value["action"]=="preflight"{return Ok(Some(json!({"id":value["id"],"document_id":value["document_id"],"module_scope":value["module_scope"]})));}
    Ok(None)
}
pub(crate) fn coverage(value:&Value,source:&Value,required:&Value)->bool {
    if !fields(value,&["version","support_transfer","targets"]) || value["version"].as_u64()!=Some(1)
        || value["support_transfer"]!="none" {return false;}
    let (Some(rows),Some(refs))=(value["targets"].as_array(),required.as_array()) else{return false;};
    if rows.is_empty() || rows.len()>64 {return false;}
    let mut prior:Option<&str>=None;
    if !rows.iter().all(|row| {
        if !fields(row,&["face_ref","scope","visibility_sha256","recipe_sha256"])
            || !face(&row["face_ref"]) || row["face_ref"]["asset_sha256"]!=source["asset_sha256"]
            || !hex(&row["recipe_sha256"],64) {return false;}
        let id=row["face_ref"]["face_instance_id"].as_str().unwrap();
        if prior.is_some_and(|previous|previous>=id){return false;} prior=Some(id);
        match row["scope"].as_str(){
            Some("neutral-no-effect")=>row["visibility_sha256"].is_null(),
            Some("target-reviewed-visible-skin")=>hex(&row["visibility_sha256"],64),
            _=>false,
        }
    }) {return false;}
    refs.iter().all(|reference|rows.iter().any(|row|&row["face_ref"]==reference))
}
pub(crate) fn review(value:&Value)->bool {
    let p=&value["face_decoration_preset"];let owner=&p["owner"];let doc=&owner["document"];
    if !fields(p,&["version","preset_sha256","applies_sha256","load_id","owner","face_ref","coverage","visual"])
        ||p["version"].as_u64()!=Some(1)||p["load_id"]!=value["document_id"]||!text(&p["load_id"])
        ||!hex(&p["preset_sha256"],64)||!hex(&p["applies_sha256"],64)
        ||!fields(owner,&["document","people_scope","state_revision","association_revision","graph_sha256","source_proof"])
        ||!fields(doc,&["document_id","epoch","revision"])||!text(&doc["document_id"])||!text(&doc["epoch"])
        ||doc["revision"].as_u64().map(|n|n.to_string())!=value["revision"].as_str().map(str::to_owned)
        ||!(owner["people_scope"]=="project"||owner["people_scope"]==doc["document_id"])
        ||!owner["state_revision"].is_u64()||!owner["association_revision"].is_u64()||!hex(&owner["graph_sha256"],64)
        ||!face(&p["face_ref"])||p["face_ref"]["asset_sha256"]!=owner["source_proof"]["asset_sha256"]
        ||!coverage(&p["coverage"],&owner["source_proof"],&json!([p["face_ref"]]))||!visual(&p["visual"],&doc["document_id"],&value["revision"],&owner["source_proof"])
        ||p["visual"]["source_proof"]!=value["source_proof"] {return false;}
    p["visual"]["coverage_sha256"].as_str()==Some(crate::batch_api::collarbone::request_digest(&p["coverage"]).as_str())
}
fn parameters(value:&Value)->bool {
    let recipe=&value["recipe"];
    fields(value,&["recipe"])&&fields(recipe,&["version","pattern","strength"])
        &&recipe["version"].as_u64()==Some(1)
        &&recipe["strength"].as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n))
        &&matches!(recipe["pattern"].as_str(),Some("freckle_dust"|"freckle_bridge"|"freckle_constellation"|"freckle_sunburst"|"freckle_scatter"|"mole_left_cheek"|"mole_right_cheek"|"mole_pair"))
}
pub(crate) fn receipt(value:&Value)->bool {
    let required=value["face_decoration_visual_required"]==true;
    if value.get("face_decoration_visual_required").is_some()&&!required{return false;}

    if value["action"]=="face_decoration_visual" {
        if value["success"]!=true{return true;}
        return text(&value["id"])&&text(&value["document_id"])&&hex(&value["preflight_token"],32)&&revision(&value["revision"])
            &&matches!(value["side"].as_str(),Some("before"|"after"))&&hex(&value["sha256"],64)
            &&value["image"]["sha256"]==value["sha256"]&&image(&value["image"]);
    }
    if !value["face_decoration_preset"].is_null()&&(!required||value["action"]!="preflight"||value["success"]!=true){return false;}
    if value["action"]=="preflight"&&value["success"]==true&&(selected(value)||required||value.get("face_decoration_preset").is_some()){return (!selected(value)||parameters(&value["applies"][OP]))&&hex(&value["preflight_token"],32)&&review(value);}
    if let Some(ack)=value.get(ACK){return required&&value["action"]=="apply"&&acknowledgment(ack)&&hex(&value["preflight_token"],32);}
    !(value["action"]=="apply"&&(selected(value)||required)&&(value["success"]==true||value["outcome_unknown"]==true))
}
#[cfg(test)]
#[path="face_decoration_preset_protocol_tests.rs"]
mod tests;
