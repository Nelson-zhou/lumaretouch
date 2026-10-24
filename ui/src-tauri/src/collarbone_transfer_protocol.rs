//! Collarbone visual review transport only; no anatomy or render acceptance claim.
use serde_json::{json, Value};
use crate::original_shadow_transfer_protocol::{hex, revision};
pub(crate) const OP: &str = "lnx.collarbone.v1";
pub(crate) const ACK: &str = "collarbone_review_ack";
pub(crate) const MAX_TARGETS: usize = 16;
fn fields(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|m| m.len() == names.len() && names.iter().all(|key| m.contains_key(*key)))
}
fn text(value: &Value) -> bool {
    value.as_str().is_some_and(|v| !v.trim().is_empty() && v.len() <= 128 && !v.chars().any(char::is_control))
}
pub(crate) fn selected(value: &Value) -> bool {
    value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == OP))
}
fn cohort(value: &Value) -> bool { value["collarbone_cohort"] == true }
fn persistent_request(value: &Value) -> bool {
    let request=&value["people_transfer"];
    let mut names=vec!["target_policy","operation","association_id","source_ref","selection","source","targets"];
    if request.get("face_style").is_some(){
        names.push("face_style");
        if !crate::batch_api::portrait_cohort::request(request){return false;}
    }
    if !fields(request,&names)
        || request["target_policy"]!="persistent_association"
        || !matches!(request["operation"].as_str(),Some("create"|"patch"|"unlink"))
        || !text(&request["association_id"]) || !request["source_ref"].is_object()
        || !request["source"].is_object() || !request["selection"].is_object() {return false;}
    let (Some(targets),Some(docs),Some(ops))=(request["targets"].as_array(),value["docs"].as_array(),value["module_scope"].as_array()) else{return false;};
    let selection=request["selection"].as_object().unwrap();
    if targets.is_empty() || targets.len()>15 || docs.len()!=targets.len() || ops.len()!=selection.len()
        || ops.iter().any(|op|op.as_str().map_or(true,|name|!selection.contains_key(name)))
        || ops.iter().enumerate().any(|(i,op)|ops[..i].contains(op))
        || (request["operation"]=="unlink" && !selection.is_empty()) {return false;}
    targets.iter().all(|target|fields(target,&["target","target_refs"])
        && target["target"].is_object() && target["target_refs"].as_array().is_some_and(|refs|refs.len()==1 && refs[0].is_object())
        && docs.iter().any(|id|id==&target["target"]["document"]["document_id"]))
}
pub(crate) fn acknowledgments(value: &Value) -> bool {
    let Some(items) = value.as_array() else { return false; };
    let mut seen = std::collections::BTreeSet::new();
    items.len() <= MAX_TARGETS && items.iter().all(|item|
        fields(item, &["document_id", "revision", "before_sha256", "after_sha256", "coverage_sha256"])
        && text(&item["document_id"]) && revision(&item["revision"])
        && hex(&item["before_sha256"], 64) && hex(&item["after_sha256"], 64)
        && hex(&item["coverage_sha256"], 64) && seen.insert(item["document_id"].as_str().unwrap()))
}
pub(crate) fn command(value: &Value) -> Result<(), String> {
    if value["cmd"]=="batch" && (value["action"]=="face_decoration_visual"||value.get(crate::batch_api::face_decoration::ACK).is_some()) {return crate::batch_api::face_decoration::command(value);}
    if crate::batch_api::eye_cohort::routed(value) { return crate::batch_api::eye_cohort::command(value); }
    if value["cmd"] == "batch" && (value["action"] == "eye_bag_visual"
        || value["people_transfer"].get("eye_bag").is_some()
        || value.get(crate::batch_api::eye_bag::ACK).is_some()) {
        // Exact eye-only or eye-plus-collarbone forms are owned by that
        // validator. An action label never exempts generic image coordinates.
        return crate::batch_api::eye_bag::command(value);
    }
    // A separate exact validator owns this image family. Never exempt generic
    // batch coordinates merely because the caller supplied an action label.
    if value["action"] == "face_style_visual" {
        return crate::batch_api::face_style::command(value);
    }
    if value["action"] == "portrait_cohort_visual" || value.get(crate::batch_api::portrait_cohort::ACK).is_some()
        || (value["people_transfer"]["target_policy"] == "persistent_association" && value["people_transfer"].get("face_style").is_some()) {
        return crate::batch_api::portrait_cohort::command(value);
    }
    if value["action"] == "collarbone_visual" {
        return if image_request(value) {Ok(())} else {Err("Invalid bounded collarbone image retrieval".into())};
    }
    if value["cmd"] == "batch" && ["document_id","revision","side","sha256"].iter().any(|key|value.get(*key).is_some()) {
        return Err("Image retrieval coordinates cannot accompany another batch action".into());
    }
    if value["cmd"] == "batch" && selected(value)
        && (value["action"] != "preflight" || !value["people_transfer"].is_object()
            || !matches!(value["people_transfer"]["target_policy"].as_str(), Some("confirmed_person_only" | "explicit_face_map" | "persistent_association"))
            || (value["people_transfer"]["target_policy"]=="persistent_association" && !persistent_request(value))) {
        return Err("Collarbone batch requires exact confirmed, explicit or persistent-cohort people visual review".into());
    }
    let Some(ack) = value.get(ACK) else { return Ok(()); };
    if value["cmd"] != "batch" || value["action"] != "commit"
        || !fields(value, &["cmd", "action", "request_id", "preflight_token", ACK])
        || !text(&value["request_id"]) || !hex(&value["preflight_token"], 32) || !acknowledgments(ack) {
        return Err("Collarbone commit requires its exact frozen target PNG/coverage acknowledgments".into());
    }
    Ok(())
}
/// Preserve the exact request token and ordered coverage-bound acknowledgments.
/// Scope is not invented at commit time: the engine alone resolves the frozen token.
pub(crate) fn binding(value: &Value) -> Result<Option<Value>, String> {
    command(value)?;
    if image_request(value) {
        return Ok(Some(json!({"preflight_token":value["preflight_token"],"document_id":value["document_id"],
            "revision":value["revision"],"side":value["side"],"sha256":value["sha256"]})));
    }
    if let Some(ack) = value.get(ACK) {
        return Ok(Some(json!({"preflight_token": value["preflight_token"], (ACK): ack})));
    }
    if value["cmd"] == "batch" && value["action"] == "preflight" && persistent_request(value) {
        return Ok(Some(json!({"module_scope":value["module_scope"],"collarbone_applies_sha256":request_digest(&value["people_transfer"])})));
    }
    if value["cmd"] == "batch" && value["action"] == "preflight" && selected(value)
        && value["people_transfer"].is_object() {
        return Ok(Some(json!({"module_scope": value["module_scope"]})));
    }
    Ok(None)
}
pub(crate) fn receipt(value: &Value) -> bool {
    if value.get(crate::batch_api::face_decoration::ACK).is_some(){return crate::batch_api::face_decoration::receipt(value);}
    if value.get(crate::batch_api::eye_cohort::ACK).is_some() { return crate::batch_api::eye_cohort::receipt(value); }
    if value.get("collarbone_cohort").is_some() && !cohort(value) {return false;}
    if value.get(crate::batch_api::eye_bag::ACK).is_some() {
        // A mixed ordinary transfer retains both independent coverage ACKs.
        // This cannot admit cohort/alias evidence or a substituted image pair.
        return crate::batch_api::eye_bag::receipt(value);
    }
    if value.get(crate::batch_api::portrait_cohort::ACK).is_some() {
        // A dual family exists only on an engine-proven persistent cohort.
        // The portrait validator retains both ordered bindings independently.
        return crate::batch_api::portrait_cohort::receipt(value)
            && (value.get(ACK).is_some() == cohort(value));
    }
    let Some(ack) = value.get(ACK) else {
        return !(value["action"] == "commit" && (selected(value) || cohort(value))
            && (value["success"] == true || value["outcome_unknown"] == true));
    };
    value["action"] == "commit" && (selected(value) || cohort(value)) && acknowledgments(ack)
        && hex(&value["preflight_token"], 32)
        && !["torso_review_ack", "waist_review_ack", "head_review_ack", "spill_review_ack", "shadow_review_ack", "face_style_review_ack"]
            .iter().any(|key| value.get(*key).is_some())
}
#[cfg(test)]
#[path="collarbone_transfer_protocol_tests.rs"]
mod tests;

pub(crate) fn size(value: &Value) -> Option<(u64,u64)> {
    let v=value.as_array()?;
    if v.len()!=2 { return None; }
    let (w,h)=(v[0].as_u64()?,v[1].as_u64()?);
    (w>0 && h>0 && w<=u32::MAX as u64 && h<=u32::MAX as u64).then_some((w,h))
}
pub(crate) fn image(value: &Value, output: (u64,u64)) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use sha2::{Digest,Sha256};
    if !fields(value,&["mime","width","height","sha256","base64"])
        || value["mime"]!="image/png" || !hex(&value["sha256"],64) { return false; }
    let (Some(w),Some(h),Some(encoded))=(value["width"].as_u64(),value["height"].as_u64(),value["base64"].as_str()) else{return false;};
    if w==0 || h==0 || w>1024 || h>1024 || w>output.0 || h>output.1
        || (w*output.1).abs_diff(h*output.0)>output.0.max(output.1)
        || encoded.is_empty() || encoded.len()>5_592_408 { return false; }
    let Ok(bytes)=STANDARD.decode(encoded) else{return false;};
    bytes.len()<=4*1024*1024 && STANDARD.encode(&bytes)==encoded
        && crate::torso_transfer_protocol::png(&bytes,w as u32,h as u32)
        && format!("{:x}",Sha256::digest(&bytes))==value["sha256"].as_str().unwrap()
}
fn visual(value: &Value, target: &Value) -> bool {
    if !fields(value,&["version","document_id","revision","source_proof","before_state_sha256",
        "candidate_state_sha256","before_people_sha256","candidate_people_sha256","source_size",
        "before_output_size","after_output_size","coverage_sha256","before","after"])
        || value["version"].as_u64()!=Some(1) || value["document_id"]!=target["document_id"]
        || value["revision"]!=target["revision"] || !revision(&value["revision"])
        || !crate::original_shadow_transfer_protocol::source_proof(&value["source_proof"]) { return false; }
    if ["before_state_sha256","candidate_state_sha256","before_people_sha256","candidate_people_sha256","coverage_sha256"]
        .iter().any(|key| !hex(&value[*key],64)) { return false; }
    let (Some(source),Some(before),Some(after))=(size(&value["source_size"]),size(&value["before_output_size"]),size(&value["after_output_size"])) else{return false;};
    let derived=&value["source_proof"]["creative_source"];
    if !derived.is_null() && (derived["width"].as_u64()!=Some(source.0) || derived["height"].as_u64()!=Some(source.1)) {return false;}
    compact_image(&value["before"],before) && compact_image(&value["after"],after)
}
pub(crate) fn preflight(value: &Value) -> bool {
    if value["success"]!=true || value["action"]!="preflight" {return true;}
    if value["applies"]["target_policy"]=="persistent_association" {
        let inherited=value["persistent_association"]["intent"].as_array().is_some_and(|leaves|leaves.iter().any(|leaf|leaf["op"]==OP));
        if cohort(value) {return cohort_preflight(value);}
        return !selected(value) && !inherited;
    }
    if cohort(value) {return false;}
    if !selected(value) {return true;}
    if value["people_transfer"]!=true || !value["persistent_association"].is_null()
        || !matches!(value["applies"]["target_policy"].as_str(),Some("confirmed_person_only"|"explicit_face_map")) { return false; }
    let Some(targets)=value["targets"].as_array() else{return false;};
    if targets.len()>MAX_TARGETS || value.to_string().len()>7*1024*1024 {return false;}
    let mut ids=std::collections::BTreeSet::new();
    let mut blocked=0u64;

    for target in targets {
        if !text(&target["document_id"]) || !revision(&target["revision"])
            || !ids.insert(target["document_id"].as_str().unwrap()) {return false;}
        if !target["blocked"].is_null() {
            if !target["blocked"].as_str().is_some_and(|v|!v.trim().is_empty()) {return false;}
            blocked+=1;continue;
        }
        let record=&target["people_transfer"]["collarbone_visual"];
        if !visual(record,target)
            || record["source_proof"]!=target["people_transfer"]["target_owner"]["source_proof"] {return false;}

    }
    value["blocked"].as_u64()==Some(blocked)
        && value["ok"].as_u64()==Some(targets.len() as u64-blocked)
}

pub(crate) fn compact_image(value:&Value,output:(u64,u64))->bool {
    if !fields(value,&["mime","width","height","sha256"]) || value["mime"]!="image/png"
        || !hex(&value["sha256"],64) {return false;}
    let edge=output.0.max(output.1);
    let scaled=|n:u64|->u64 {
        if edge<=1024 {return n;}
        let product=n*1024;let q=product/edge;let r=product%edge;
        (q+u64::from(r*2>edge || (r*2==edge && q%2==1))).max(1)
    };
    value["width"].as_u64()==Some(scaled(output.0)) && value["height"].as_u64()==Some(scaled(output.1))
}
fn image_request(value:&Value)->bool {
    fields(value,&["cmd","action","request_id","preflight_token","document_id","revision","side","sha256"])
        && value["cmd"]=="batch" && value["action"]=="collarbone_visual" && text(&value["request_id"])
        && hex(&value["preflight_token"],32) && text(&value["document_id"]) && revision(&value["revision"])
        && matches!(value["side"].as_str(),Some("before"|"after")) && hex(&value["sha256"],64)
}
pub(crate) fn read_only(value:&Value)->bool {
    if image_request(value) {return true;}
    let Some(map)=value.as_object() else{return false;};
    let names=["cmd","action","request_id","docs","module_scope","people_transfer"];
    let Some(docs)=value["docs"].as_array() else{return false;};
    value["cmd"]=="batch" && value["action"]=="preflight" && (selected(value) || persistent_request(value))
        && command(value).is_ok() && text(&value["request_id"])
        && names.iter().all(|key|map.contains_key(*key))
        && map.keys().all(|key|names.contains(&key.as_str()) || key=="conflict_policy")
        && value.get("conflict_policy").map_or(true,|p|if persistent_request(value){p=="recheck"}else{matches!(p.as_str(),Some("skip_and_report"|"recheck"))})
        && !docs.is_empty() && docs.len()<=(if persistent_request(value){15}else{MAX_TARGETS}) && docs.iter().all(text)
        && docs.iter().enumerate().all(|(i,v)|!docs[..i].contains(v))
}
pub(crate) fn image_receipt(value:&Value)->bool {
    if value["action"]!="collarbone_visual" || value["success"]!=true {return true;}
    let image_value=&value["image"];
    let (Some(w),Some(h))=(image_value["width"].as_u64(),image_value["height"].as_u64()) else{return false;};
    hex(&value["preflight_token"],32) && text(&value["document_id"]) && revision(&value["revision"])
        && matches!(value["side"].as_str(),Some("before"|"after")) && hex(&value["sha256"],64)
        && image_value["sha256"]==value["sha256"] && image(image_value,(w,h))
}


fn cohort_preflight(value:&Value)->bool {
    if value["people_transfer"]!=true || !value["persistent_association"].is_object()
        || value["policy"]!="recheck" || value["blocked"].as_u64()!=Some(0)
        || value["rejected_docs"].as_array().map_or(true,|rows|!rows.is_empty()) {return false;}
    let (Some(targets),Some(members))=(value["targets"].as_array(),value["persistent_association"]["members"].as_array()) else{return false;};
    if targets.is_empty() || targets.len()>15 || members.len()!=targets.len()+1
        || value["ok"].as_u64()!=Some(targets.len() as u64) || value.to_string().len()>7*1024*1024 {return false;}
    let source=&value["association_source"];
    if source["document_id"]!=value["source_snapshot"]["document_id"] {return false;}
    let mut seen=std::collections::BTreeSet::new();
    for target in std::iter::once(source).chain(targets.iter()) {
        let association=&target["association"];let owner=&association["owner"];
        if !text(&target["document_id"]) || !revision(&target["revision"]) || !target["blocked"].is_null()
            || !seen.insert(target["document_id"].as_str().unwrap())
            || owner["document"]["document_id"]!=target["document_id"]
            || owner["document"]["revision"].as_u64().map(|n|n.to_string())!=target["revision"].as_str().map(str::to_owned)
            || !members.iter().any(|m|m["document_id"]==target["document_id"] && m["ref"]==association["ref"])
            || !visual(&association["collarbone_visual"],target)
            || association["collarbone_visual"]["source_proof"]!=owner["source_proof"] {return false;}
        let coverage=&association["collarbone_coverage"];
        if !fields(coverage,&["version","support_transfer","targets"]) || coverage["version"].as_u64()!=Some(1)
            || coverage["support_transfer"]!="none"
            || !coverage["targets"].as_array().is_some_and(|rows|rows.len()==1 && rows[0]["face_ref"]==association["ref"]) {return false;}
    }
    seen.len()==members.len()
}

/// Internal receipt binding: retain exact arbitrary-order JSON intent by digest,
/// not the complete sixteen-member request in the compact receipt budget.
pub(crate) fn request_digest(value:&Value)->String {
    use sha2::{Digest,Sha256};
    fn sorted(value:&Value)->Value {
        match value {
            Value::Object(map)=>{
                let ordered:std::collections::BTreeMap<_,_>=map.iter().map(|(key,item)|(key.clone(),sorted(item))).collect();
                Value::Object(ordered.into_iter().collect())
            },
            Value::Array(items)=>Value::Array(items.iter().map(sorted).collect()),
            _=>value.clone(),
        }
    }
    format!("{:x}",Sha256::digest(sorted(value).to_string().as_bytes()))
}
