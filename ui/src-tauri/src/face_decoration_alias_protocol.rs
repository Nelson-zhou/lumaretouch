// SPDX-License-Identifier: GPL-3.0-or-later
//! Direct shared-source scalar review. No donor support or sibling local-state writes.
use serde_json::{json,Value};
use crate::original_shadow_transfer_protocol::{hex,revision};
use crate::preset_api::visual::{fields,text,visual};
const CONTEXT:&[&str]=&["document_id","document_epoch","document_revision","state_revision","association_revision","target"];
const REQUEST:&str="face_decoration_alias_request";
const MAX_MEMBERS:usize=16;
fn number(v:&Value)->bool {v.as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n))}
fn recipe(v:&Value)->bool {
    fields(v,&["version","pattern","strength"])&&v["version"].as_u64()==Some(1)&&number(&v["strength"])
        &&matches!(v["pattern"].as_str(),Some("freckle_dust"|"freckle_bridge"|"freckle_constellation"|"freckle_sunburst"|"freckle_scatter"|"mole_left_cheek"|"mole_right_cheek"|"mole_pair"))
}
pub(crate) fn action(v:&Value)->bool {matches!(v["action"].as_str(),Some("face_decoration_alias_preview"|"face_decoration_alias_image"|"face_decoration_alias_confirm"))}
fn ack(v:&Value)->bool {
    let Some(rows)=v["members"].as_array() else{return false;};let mut ids=std::collections::BTreeSet::new();
    fields(v,&["review_sha256","members"])&&hex(&v["review_sha256"],64)&&(2..=MAX_MEMBERS).contains(&rows.len())
        &&rows.iter().all(|row|fields(row,&["document_id","revision","before_sha256","after_sha256"])
            &&text(&row["document_id"])&&revision(&row["revision"])&&hex(&row["before_sha256"],64)&&hex(&row["after_sha256"],64)
            &&ids.insert(row["document_id"].as_str().unwrap()))
}
pub(crate) fn command(v:&Value)->Result<(),String>{
    if !action(v){return Ok(());}let mut context=json!({});for k in CONTEXT{context[*k]=v[*k].clone();}let p=&v["payload"];
    let valid=super::valid_context(&context)&&v["target"]["scope"]=="face"&&match v["action"].as_str(){
        Some("face_decoration_alias_preview")=>fields(p,&["recipe"])&&recipe(&p["recipe"]),
        Some("face_decoration_alias_image")=>fields(p,&["token","document_id","side","sha256"])&&hex(&p["token"],32)
            &&text(&p["document_id"])&&matches!(p["side"].as_str(),Some("before"|"after"))&&hex(&p["sha256"],64),
        Some("face_decoration_alias_confirm")=>fields(p,&["token","ack"])&&hex(&p["token"],32)&&ack(&p["ack"])
            &&p["ack"]["members"][0]["document_id"]==v["document_id"]
            &&p["ack"]["members"][0]["revision"].as_str()==v["document_revision"].as_u64().map(|n|n.to_string()).as_deref(),
        _=>false,
    };
    if valid{Ok(())}else{Err("Decoration alias editing requires exact target and every affected document image".into())}
}
pub(crate) fn read_only(v:&Value)->bool{
    let names=["cmd","request_id","action","payload","document_id","document_epoch","document_revision","state_revision","association_revision","target"];
    v["cmd"]=="people"&&matches!(v["action"].as_str(),Some("face_decoration_alias_preview"|"face_decoration_alias_image"))&&command(v).is_ok()
        &&text(&v["request_id"])&&v.as_object().is_some_and(|m|names.iter().all(|k|m.contains_key(*k))&&m.keys().all(|k|names.contains(&k.as_str())||k=="host_epoch"))
        &&v.get("host_epoch").map_or(true,|epoch|hex(epoch,32))
}
pub(crate) fn binding(v:&Value)->Result<Option<Value>,String>{
    if v["cmd"]!="people"||!action(v){return Ok(None);}command(v)?;
    let mut r=json!({"action":v["action"],"payload":v["payload"]});for k in CONTEXT{r[*k]=v[*k].clone();}
    Ok(Some(json!({(REQUEST):r})))
}
fn review(v:&Value,request:&Value)->bool{
    if !fields(v,&["version","token","recipe","owner","face_ref","members","review_sha256","candidate_state_revision"])
        ||v["version"].as_u64()!=Some(1)||!hex(&v["token"],32)||!recipe(&v["recipe"])||v["recipe"]!=request["payload"]["recipe"]
        ||!crate::batch_api::face_style::endpoint(&v["owner"])||v["face_ref"]!=request["target"]["face_ref"]||!hex(&v["review_sha256"],64)
        ||v["owner"]["document"]["document_id"]!=request["document_id"]||v["owner"]["document"]["epoch"]!=request["document_epoch"]
        ||v["owner"]["document"]["revision"]!=request["document_revision"]||v["owner"]["state_revision"]!=request["state_revision"]
        ||v["owner"]["association_revision"]!=request["association_revision"]||v["face_ref"]["asset_sha256"]!=v["owner"]["source_proof"]["asset_sha256"]
        ||!v["candidate_state_revision"].as_u64().is_some_and(|n|n<=9_007_199_254_740_991&&request["state_revision"].as_u64().is_some_and(|old|n>=old)){return false;}
    let Some(rows)=v["members"].as_array() else{return false;};let mut ids=std::collections::BTreeSet::new();
    (2..=MAX_MEMBERS).contains(&rows.len())&&rows[0]["visual"]["document_id"]==request["document_id"]
        &&rows[0]["visual"]["source_proof"]==v["owner"]["source_proof"]
        &&rows[0]["visual"]["revision"].as_str()==request["document_revision"].as_u64().map(|n|n.to_string()).as_deref()
        &&rows.iter().all(|row|{let image=&row["visual"];
            fields(row,&["path","coverage","visual"])&&row["path"].as_str().is_some_and(|p|!p.is_empty()&&p.len()<=4096)
                &&text(&image["document_id"])&&revision(&image["revision"])&&ids.insert(image["document_id"].as_str().unwrap())
                &&image["source_proof"]["asset_sha256"]==v["owner"]["source_proof"]["asset_sha256"]
                &&image["before_state_sha256"]==image["candidate_state_sha256"]&&image["before_output_size"]==image["after_output_size"]
                &&visual(image,&image["document_id"],&image["revision"],&image["source_proof"])
                &&crate::preset_api::face_decoration::coverage(&row["coverage"],&image["source_proof"],&json!([v["face_ref"]]))
                &&image["coverage_sha256"].as_str()==Some(crate::batch_api::collarbone::request_digest(&row["coverage"]).as_str())})
}
fn confirmed(value:&Value,request:&Value)->bool{
    let p=&value["payload"];let a=&request["payload"]["ack"];
    if !fields(p,&["kind","token","review_sha256","recipe","ack","alias_members","candidate_state_revision","history_review_sha256"])
        ||p["kind"]!="face_decoration_alias_confirm"||p["token"]!=request["payload"]["token"]||p["ack"]!=*a
        ||p["history_review_sha256"].as_str()!=Some(crate::batch_api::collarbone::request_digest(a).as_str())||p["review_sha256"]!=a["review_sha256"]||!recipe(&p["recipe"])||!text(&value["batch_id"]){return false;}
    let (Some(rows),Some(acks))=(p["alias_members"].as_array(),a["members"].as_array()) else{return false;};
    if rows.len()!=acks.len()||!rows.iter().zip(acks).all(|(row,ack)|fields(row,&["document_id","expected_revision","result_revision"])
        &&row["document_id"]==ack["document_id"]&&row["expected_revision"]==ack["revision"]&&revision(&row["result_revision"])
        &&row["result_revision"].as_str().and_then(|s|s.parse::<u64>().ok())==ack["revision"].as_str().and_then(|s|s.parse::<u64>().ok()).and_then(|n|n.checked_add(1))){return false;}
    let people=&value["doc_state"]["people"];let binding=&people["binding"];let report=&people["face_decoration"];
    binding["document_epoch"]==request["document_epoch"]&&binding["asset_sha256"]==request["target"]["face_ref"]["asset_sha256"]
        &&binding["document_revision"].as_u64()==request["document_revision"].as_u64().and_then(|n|n.checked_add(1))
        &&p["candidate_state_revision"].as_u64().is_some_and(|n|n<=9_007_199_254_740_991&&request["state_revision"].as_u64().is_some_and(|old|n>old))&&people["revision"]==p["candidate_state_revision"]&&people["association_revision"]==request["association_revision"]
        &&report["recipe"]==p["recipe"]&&report["face_ref"]==request["target"]["face_ref"]
        &&people["resolved"]["face_ref"]==request["target"]["face_ref"]&&people["resolved"]["state_revision"]==people["revision"]
        &&people["resolved"]["association_revision"]==people["association_revision"]
        &&people["resolved"]["operations"]["lnx.face_decoration.v1"]["/pattern"]["value"]==p["recipe"]["pattern"]
        &&people["resolved"]["operations"]["lnx.face_decoration.v1"]["/strength"]["value"].as_f64()==p["recipe"]["strength"].as_f64()
}
pub(crate) fn receipt(v:&Value)->bool{
    if !action(v){return v.get(REQUEST).is_none();}
    let required=["protocol","request_id","action","document_id","success","outcome_unknown",REQUEST];
    let optional=["event","error","created_id","batch_id","frame_emitted","payload","doc_state","payload_released"];
    if !v.as_object().is_some_and(|m|required.iter().all(|k|m.contains_key(*k))&&m.keys().all(|k|required.contains(&k.as_str())||optional.contains(&k.as_str())))
        ||v["protocol"]!=1||!text(&v["request_id"])||v.get("event").is_some_and(|e|e!="people_result")
        ||!v["created_id"].is_null()||v.get("frame_emitted").is_some_and(|b|!b.is_boolean()){return false;}
    let request=&v[REQUEST];let mut wire=request.clone();wire["cmd"]=json!("people");
    if !fields(request,&["action","payload","document_id","document_epoch","document_revision","state_revision","association_revision","target"])||command(&wire).is_err()||request["action"]!=v["action"]||request["document_id"]!=v["document_id"]{return false;}
    if v["success"]!=true{return v["success"]==false&&v["outcome_unknown"].is_boolean()&&v["error"].as_str().is_some_and(|s|!s.trim().is_empty())&&(v["outcome_unknown"]==true||(v.get("doc_state").map_or(true,Value::is_null)&&v.get("batch_id").map_or(true,Value::is_null)));}
    if v["outcome_unknown"]!=false{return false;}
    if v.get("payload_released").is_some() {
        return v["action"]=="face_decoration_alias_image"&&v["payload_released"]==true
            &&v.get("payload").map_or(true,Value::is_null)&&v.get("doc_state").is_none()
            &&v["batch_id"].is_null()&&v["created_id"].is_null()&&v["frame_emitted"]==false&&v["error"].is_null();
    }
    let p=&v["payload"];
    match v["action"].as_str(){
        Some("face_decoration_alias_preview")=>fields(p,&["kind","review"])&&p["kind"]==v["action"]&&review(&p["review"],request)&&v["doc_state"]["people"]["face_decoration"]["alias_review"]==p["review"],
        Some("face_decoration_alias_image")=>fields(p,&["kind","token","document_id","side","sha256","review_sha256","image"])
            &&p["kind"]==v["action"]&&v.get("doc_state").is_none()&&hex(&p["review_sha256"],64)
            &&["token","document_id","side","sha256"].iter().all(|k|p[*k]==request["payload"][*k])
            &&p["image"]["sha256"]==p["sha256"]&&crate::people_api::face_style::image(&p["image"]),
        Some("face_decoration_alias_confirm")=>confirmed(v,request),_=>false,
    }
}

/// Optional new metadata is complete and never mutating authority.
pub(crate) fn report_metadata(v:&Value)->bool {
    let keys=["alias_required","alias_member_count","alias_reason","alias_review"];
    if keys.iter().all(|k|v.get(*k).is_none()){return true;}
    if keys.iter().any(|k|v.get(*k).is_none())||!v["alias_required"].is_boolean()
        ||!v["alias_member_count"].as_u64().is_some_and(|n|n<=1_000_000)
        ||!(v["alias_reason"].is_null()||v["alias_reason"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=4096)){return false;}
    if v["alias_review"].is_null(){return true;}
    let r=&v["alias_review"];let owner=&r["owner"];
    let request=json!({"document_id":owner["document"]["document_id"],"document_epoch":owner["document"]["epoch"],
        "document_revision":owner["document"]["revision"],"state_revision":owner["state_revision"],"association_revision":owner["association_revision"],
        "target":{"scope":"face","target_id":r["face_ref"]["face_instance_id"],"face_ref":r["face_ref"]},"payload":{"recipe":r["recipe"]}});
    v["alias_required"]==true&&r["face_ref"]==v["face_ref"]&&r["owner"]["source_proof"]["asset_sha256"]==v["source"]["sha256"]
        &&r["members"].as_array().map(|rows|rows.len() as u64)==v["alias_member_count"].as_u64()&&review(r,&request)
}

pub(crate) fn applies(v:&Value)->bool {v["cmd"]=="people"&&v["action"]=="face_decoration_alias_confirm"&&command(v).is_ok()}
pub(crate) fn matches_request(command:&Value,value:&Value)->bool {
    let Ok(Some(bound))=binding(command) else{return false;};
    value["event"]=="people_result"&&receipt(value)&&bound.as_object().is_some_and(|m|m.iter().all(|(k,v)|value.get(k)==Some(v)))
}
pub(crate) fn summary(v:&Value)->bool {fields(v,&["version","review_sha256","member_count"])&&v["version"]==1&&hex(&v["review_sha256"],64)&&v["member_count"].as_u64().is_some_and(|n|(2..=16).contains(&n))}
#[cfg(test)]
#[path="face_decoration_alias_protocol_unrun.rs"]
mod tests;
