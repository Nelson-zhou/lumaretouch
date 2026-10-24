// SPDX-License-Identifier: GPL-3.0-or-later
//! Exact ordinary target-local decoration review transport. AUTHORED / UNRUN.
use serde_json::{json,Value};
use crate::batch_api::{collarbone,face_style};
use crate::original_shadow_transfer_protocol::{hex,revision};
use crate::preset_api::visual::{fields,text,visual};
pub(crate) const OP:&str="lnx.face_decoration.v1";
pub(crate) const ACK:&str="face_decoration_review_ack";
const FOREIGN:&[&str]=&["portrait_cohort_ack","eye_bag_cohort_ack","face_style_review_ack",
    "torso_review_ack","waist_review_ack","head_review_ack","spill_review_ack","shadow_review_ack",
    "face_decoration_preset_ack","persistent_association","association_source","portrait_cohort","collarbone_cohort","eye_bag_cohort"];
fn token(v:&Value)->bool {text(v)&&v.as_str().unwrap().bytes().all(|b|b.is_ascii_alphanumeric()||b"_.:-".contains(&b))}
fn selected(v:&Value)->bool {v["module_scope"].as_array().is_some_and(|ops|ops.iter().any(|op|op==OP))}
fn request(v:&Value)->bool {
    if v.get("eye_bag").is_some(){return crate::batch_api::eye_bag::request(v);}
    if !fields(v,&["target_policy","source_ref","selection","source","targets"])
        ||v["target_policy"]!="explicit_face_map" || !face_style::endpoint(&v["source"])
        ||!face_style::face(&v["source_ref"],&v["source"]["source_proof"]["asset_sha256"]) {return false;}
    let (Some(selection),Some(targets))=(v["selection"].as_object(),v["targets"].as_array()) else{return false;};
    if selection.is_empty()||selection.len()>256||targets.is_empty()||targets.len()>16{return false;}
    let mut count=0;
    if !selection.iter().all(|(op,paths)|{
        let Some(paths)=paths.as_array() else{return false;}; count+=paths.len();
        text(&json!(op))&&!paths.is_empty()&&count<=256&&paths.iter().enumerate().all(|(i,p)|
            p.as_str().is_some_and(|s|s.starts_with('/')&&s.len()<=512&&!s.chars().any(char::is_control)
                &&(op!=OP||matches!(s,"/pattern"|"/strength")))&&!paths[..i].contains(p))
    }){return false;}
    let mut docs=std::collections::BTreeSet::new();
    targets.iter().all(|row|{
        let owner=&row["target"];
        let Some(refs)=row["target_refs"].as_array() else{return false;};
        let mut faces=std::collections::BTreeSet::new();
        fields(row,&["target","target_refs"])&&face_style::endpoint(owner)
            &&owner["document"]["document_id"]!=v["source"]["document"]["document_id"]
            &&owner["document"]["epoch"]==v["source"]["document"]["epoch"]
            &&docs.insert(owner["document"]["document_id"].as_str().unwrap())
            &&!refs.is_empty()&&refs.len()<=64&&refs.iter().all(|reference|
                face_style::face(reference,&owner["source_proof"]["asset_sha256"])
                    &&faces.insert(reference["face_instance_id"].as_str().unwrap()))
    })
}
fn scope(v:&Value,selection:&Value)->bool {
    let (Some(ops),Some(leaves))=(v.as_array(),selection.as_object()) else{return false;};
    !ops.is_empty()&&ops.len()==leaves.len()&&ops.iter().enumerate().all(|(i,op)|
        op.as_str().is_some_and(|name|leaves.contains_key(name))&&!ops[..i].contains(op))
}
fn preflight_request(v:&Value)->bool {
    let Some(map)=v.as_object() else{return false;};
    let names=["cmd","action","request_id","docs","module_scope","people_transfer"];
    if v["cmd"]!="batch"||v["action"]!="preflight"||!text(&v["request_id"])
        ||!names.iter().all(|k|map.contains_key(*k))||map.keys().any(|k|!names.contains(&k.as_str())&&k!="conflict_policy")
        ||!request(&v["people_transfer"])||!scope(&v["module_scope"],&v["people_transfer"]["selection"])
        ||!v.get("conflict_policy").map_or(true,|p|matches!(p.as_str(),Some("skip_and_report"|"recheck"))){return false;}
    let Some(docs)=v["docs"].as_array() else{return false;};
    let targets=v["people_transfer"]["targets"].as_array().unwrap();
    docs.len()==targets.len()&&targets.iter().all(|row|docs.iter().filter(|d|*d==&row["target"]["document"]["document_id"]).count()==1)
}
fn image_request(v:&Value)->bool {
    fields(v,&["cmd","action","request_id","preflight_token","document_id","revision","side","sha256"])
        &&v["cmd"]=="batch"&&v["action"]=="face_decoration_visual"&&text(&v["request_id"])
        &&hex(&v["preflight_token"],32)&&hex(&v["document_id"],32)&&revision(&v["revision"])
        &&matches!(v["side"].as_str(),Some("before"|"after"))&&hex(&v["sha256"],64)
}
pub(crate) fn paired(v:&Value)->bool {
    let Some(own)=v[ACK].as_array() else{return false;};
    [collarbone::ACK,crate::batch_api::eye_bag::ACK].iter().all(|key|{
        let Some(other)=v.get(*key) else{return true;};
        if !(if *key==collarbone::ACK {collarbone::acknowledgments(other)}else{crate::batch_api::eye_bag::acknowledgments(other)}){return false;}
        let rows=other.as_array().unwrap();own.len()==rows.len()&&own.iter().zip(rows).all(|(a,b)|
            ["document_id","revision","before_sha256","after_sha256"].iter().all(|k|a[*k]==b[*k]))
    })
}
pub(crate) fn command(v:&Value)->Result<(),String> {
    if v["cmd"]!="batch"{return Ok(());}
    if v["action"]=="face_decoration_visual" {return if image_request(v){Ok(())}else{Err("Decoration image read requires exact frozen target coordinates".into())};}
    if let Some(ack)=v.get(ACK){
        let mut names=vec!["cmd","action","request_id","preflight_token",ACK];
        for key in [collarbone::ACK,crate::batch_api::eye_bag::ACK]{if v.get(key).is_some(){names.push(key);}}
        if !fields(v,&names)||v["action"]!="commit"
            ||!text(&v["request_id"])||!hex(&v["preflight_token"],32)||!collarbone::acknowledgments(ack)
            ||ack.as_array().map_or(true,|rows|rows.is_empty())||!paired(v) {return Err("Decoration commit needs exact target image and coverage acknowledgments".into());}
    }
    if v.get("face_decoration_preset_ack").is_some(){return Err("Preset consent cannot authorize a decoration batch".into());}
    Ok(())
}
pub(crate) fn read_only(v:&Value)->bool {image_request(v)||preflight_request(v)}
pub(crate) fn binding(v:&Value)->Result<Option<Value>,String> {
    command(v)?;if v["cmd"]!="batch"{return Ok(None);}
    if image_request(v){return Ok(Some(json!({"preflight_token":v["preflight_token"],"document_id":v["document_id"],"revision":v["revision"],"side":v["side"],"sha256":v["sha256"]})));}
    if let Some(ack)=v.get(ACK){
        let mut out=json!({"preflight_token":v["preflight_token"],(ACK):ack});
        for key in [collarbone::ACK,crate::batch_api::eye_bag::ACK]{if let Some(value)=v.get(key){out[key]=value.clone();}}
        return Ok(Some(out));
    }
    if preflight_request(v){return Ok(Some(json!({"module_scope":v["module_scope"],"face_decoration_applies_sha256":collarbone::request_digest(&v["people_transfer"])})));}
    Ok(None)
}
fn target_review(v:&Value,row:&Value,wanted:&Value,applies:&Value)->bool {
    let owner=&wanted["target"];let evidence=&v["face_decoration_visual"];let coverage=&v["face_decoration_coverage"];
    let required=["version","source_document","target_document","source_ref","target_refs","parameters",
        "source_state_revision","target_state_revision","source_association_revision","target_association_revision",
        "transfer_policy","excluded","source_owner","target_owner","target_policy","face_decoration_coverage","face_decoration_visual"];
    let optional=["eye_bag","eye_bag_coverage","eye_bag_visual","collarbone_coverage","collarbone_visual","skin_colour_coverage","skin_finish_coverage","body_skin_evenness_coverage","body_face_match_coverage"];
    let Some(map)=v.as_object() else{return false;};
    if !required.iter().all(|k|map.contains_key(*k))||map.keys().any(|k|!required.contains(&k.as_str())&&!optional.contains(&k.as_str()))
        ||v["version"].as_u64()!=Some(1)||v["target_policy"]!="explicit_face_map"||v["transfer_policy"]!="selected_parameter_keys_replace"
        ||v["excluded"]!=json!(["local_assets","landmarks","masks","identity_links"])
        ||v["source_document"]!=applies["source"]["document"]||v["target_document"]!=owner["document"]
        ||v["source_ref"]!=applies["source_ref"]||v["target_refs"]!=wanted["target_refs"]
        ||v["source_owner"]!=applies["source"]||v["target_owner"]!=*owner
        ||v["source_state_revision"]!=applies["source"]["state_revision"]||v["target_state_revision"]!=owner["state_revision"]
        ||v["source_association_revision"]!=applies["source"]["association_revision"]||v["target_association_revision"]!=owner["association_revision"]
        ||!crate::preset_api::face_decoration::coverage(coverage,&owner["source_proof"],&v["target_refs"])
        ||!visual(evidence,&row["document_id"],&row["revision"],&owner["source_proof"])
        ||evidence["coverage_sha256"].as_str()!=Some(collarbone::request_digest(coverage).as_str()){return false;}
    for key in ["eye_bag_visual","collarbone_visual"] {
        if let Some(other)=v.get(key){let mut a=evidence.clone();let mut b=other.clone();
            if !b.is_object(){return false;}a.as_object_mut().unwrap().remove("coverage_sha256");b.as_object_mut().unwrap().remove("coverage_sha256");
            if a!=b{return false;}
        }
    }
    let Some(parameters)=v["parameters"].as_array() else{return false;};
    let mut wanted:std::collections::BTreeSet<(&str,&str)>=applies["selection"].as_object().unwrap().iter()
        .flat_map(|(op,paths)|paths.as_array().unwrap().iter().map(move|p|(op.as_str(),p.as_str().unwrap()))).collect();
    if parameters.len()!=wanted.len(){return false;}
    parameters.iter().all(|p|{
        let (Some(op),Some(path))=(p["operation_id"].as_str(),p["parameter_path"].as_str()) else{return false;};
        if !fields(p,&["operation_id","parameter_path","value"])||!wanted.remove(&(op,path)){return false;}
        if op==OP {return match path {
            "/strength"=>p["value"].as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n)),
            "/pattern"=>matches!(p["value"].as_str(),Some("freckle_dust"|"freckle_bridge"|"freckle_constellation"|"freckle_sunburst"|"freckle_scatter"|"mole_left_cheek"|"mole_right_cheek"|"mole_pair")),
            _=>false,
        };}
        p["value"].is_boolean()||p["value"].as_str().is_some_and(|s|s.len()<=4096)||p["value"].as_f64().is_some_and(f64::is_finite)
    })&&wanted.is_empty()
}
fn preflight(v:&Value)->bool {
    let applies=&v["applies"];
    if !request(applies)||!scope(&v["module_scope"],&applies["selection"])||v["people_transfer"]!=true
        ||!hex(&v["preflight_token"],32)||v.to_string().len()>7*1024*1024
        ||v["rejected_docs"].as_array().map_or(true,|rows|!rows.is_empty())
        ||v["source_snapshot"]["document_id"]!=applies["source"]["document"]["document_id"]
        ||v["source_snapshot"]["revision"].as_str()!=applies["source"]["document"]["revision"].as_u64().map(|n|n.to_string()).as_deref(){return false;}
    let Some(targets)=v["targets"].as_array() else{return false;};let requested=applies["targets"].as_array().unwrap();
    if targets.len()!=requested.len(){return false;}
    let mut seen=std::collections::BTreeSet::new();let mut blocked=0u64;let mut prior:Option<&Value>=None;
    for row in targets{
        if !hex(&row["document_id"],32)||!revision(&row["revision"])||!seen.insert(row["document_id"].as_str().unwrap()){return false;}
        let Some(wanted)=requested.iter().find(|r|r["target"]["document"]["document_id"]==row["document_id"]) else{return false;};
        if !row["blocked"].is_null(){
            if !row["blocked"].as_str().is_some_and(|s|!s.trim().is_empty())||!row["people_transfer"].is_null(){return false;}blocked+=1;continue;
        }
        if row["revision"].as_str()!=wanted["target"]["document"]["revision"].as_u64().map(|n|n.to_string()).as_deref()
            ||!target_review(&row["people_transfer"],row,wanted,applies){return false;}
        let parameters=&row["people_transfer"]["parameters"];if prior.is_some_and(|p|p!=parameters){return false;}prior=Some(parameters);
    }
    v["blocked"].as_u64()==Some(blocked)&&v["ok"].as_u64()==Some(targets.len() as u64-blocked)
}
fn failed(v:&Value)->bool {
    v["success"]==false&&v["outcome_unknown"].is_boolean()&&v["error"].as_str().is_some_and(|s|!s.trim().is_empty())
        &&(v["outcome_unknown"]==true||(v["batch_id"].is_null()&&v.get("doc_state").is_none()&&v["committed"]!=true&&v["operation_committed"]!=true
            &&v.get("applied").map_or(true,|rows|rows.as_array().is_some_and(|rows|rows.is_empty()))
            &&v.get("target_outcomes").map_or(true,|rows|rows.as_array().is_some_and(|rows|rows.iter().all(|r|r["result_revision"].is_null()&&matches!(r["outcome"].as_str(),Some("conflict"|"not_applied")))))))
}
fn image_receipt(v:&Value)->bool {
    if !hex(&v["preflight_token"],32)||!hex(&v["document_id"],32)||!revision(&v["revision"])
        ||!matches!(v["side"].as_str(),Some("before"|"after"))||!hex(&v["sha256"],64){return false;}
    if v["success"]!=true{return failed(v)&&v.get("image").is_none();}
    let names=["event","action","success","request_id","preflight_token","document_id","revision","side","sha256","compact","image","outcome_unknown"];
    if !v.as_object().is_some_and(|m|m.keys().all(|k|names.contains(&k.as_str())))||v.get("outcome_unknown").is_some_and(|v|v!=false){return false;}
    let image=&v["image"];let compact=&v["compact"];
    let (Some(w),Some(h))=(image["width"].as_u64(),image["height"].as_u64()) else{return false;};
    image["sha256"]==v["sha256"]&&collarbone::image(image,(w,h))&&collarbone::compact_image(compact,(w,h))
        &&["mime","width","height","sha256"].iter().all(|k|image[*k]==compact[*k])
}
fn index(v:&Value)->bool {v.as_u64().is_some_and(|n|n<=9_007_199_254_740_991)}
const MAX_TARGETS:usize=16;
fn commit(v: &Value) -> bool {
    if v["success"] != true { return failed(v); }
    let (Some(outcomes), Some(acks), Some(applied), Some(ops)) = (v["target_outcomes"].as_array(),
        v[ACK].as_array(), v["applied"].as_array(), v["module_scope"].as_array()) else { return false; };
    if v["outcome_unknown"] != false || v["people_transfer"] != true || outcomes.is_empty()
        || outcomes.len() > MAX_TARGETS || acks.is_empty()
        || (ops.contains(&json!(collarbone::OP)) != v.get(collarbone::ACK).is_some())
        || ops.len() > 256 || !ops.iter().all(token) || ops.iter().enumerate().any(|(i, op)| ops[..i].contains(op))
        || (!v["batch_id"].is_null() && !text(&v["batch_id"]))
        || !hex(&v["source_snapshot"]["document_id"], 32) || !revision(&v["source_snapshot"]["revision"])
        || !v["source_snapshot"]["path"].as_str().is_some_and(|p| !p.is_empty()) { return false; }
    let mut remaining: std::collections::BTreeMap<_, _> = acks.iter()
        .map(|ack| (ack["document_id"].as_str().unwrap(), &ack["revision"])).collect();
    let mut seen = std::collections::BTreeSet::new(); let mut indices = std::collections::BTreeSet::new();
    let mut actual = Vec::new(); let mut noops = 0;
    for row in outcomes {
        if !hex(&row["document_id"], 32) || !revision(&row["expected_revision"])
            || !seen.insert(row["document_id"].as_str().unwrap()) { return false; }
        let ack = remaining.remove(row["document_id"].as_str().unwrap());
        if ack.is_some_and(|r| r != &row["expected_revision"]) { return false; }
        match row["outcome"].as_str() {
            Some("applied") => {
                if ack.is_none() || !index(&row["index"]) || !indices.insert(row["index"].as_u64().unwrap())
                    || !row["blocked"].is_null() || row["current_revision"] != row["expected_revision"]
                    || !revision(&row["result_revision"])
                    || row["result_revision"].as_str().unwrap().parse::<u64>().unwrap() <= row["expected_revision"].as_str().unwrap().parse::<u64>().unwrap()
                    || v["batch_id"].is_null() { return false; }
                actual.push(row["index"].clone());
            }
            Some("noop") => {
                if ack.is_none() || !index(&row["index"]) || !indices.insert(row["index"].as_u64().unwrap())
                    || !row["blocked"].is_null() || row["current_revision"] != row["expected_revision"]
                    || row["result_revision"] != row["expected_revision"] { return false; }
                noops += 1;
            }
            Some("skipped") => {
                if !row["blocked"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 2000)
                    || (!row["index"].is_null() && !index(&row["index"]))
                    || (!row["current_revision"].is_null() && !revision(&row["current_revision"]))
                    || (!row["result_revision"].is_null() && !revision(&row["result_revision"])) { return false; }
            }
            _ => return false,
        }
    }
    let marker=&v["face_decoration_batch_review"];
    let history_ok=if actual.is_empty(){marker.is_null()}else{
        fields(marker,&["version","review_sha256","member_count"])&&marker["version"].as_u64()==Some(1)
            &&marker["review_sha256"].as_str()==Some(collarbone::request_digest(&v[ACK]).as_str())
            &&marker["member_count"].as_u64()==Some(actual.len() as u64)
    };
    history_ok && remaining.is_empty() && (!actual.is_empty() || noops > 0) && &actual == applied
        && (v["batch_id"].is_null() == actual.is_empty())
}
pub(crate) fn receipt(v:&Value)->bool {
    if v["action"]=="face_decoration_visual"{return image_receipt(v);}
    let evidence=v["targets"].as_array().is_some_and(|rows|rows.iter().any(|row|
        row["people_transfer"].get("face_decoration_visual").is_some()||row["people_transfer"].get("face_decoration_coverage").is_some()));
    let required=v["face_decoration_visual_required"]==true;
    if v.get("face_decoration_visual_required").is_some()&&!required{return false;}
    if evidence||required||v.get(ACK).is_some(){
        if FOREIGN.iter().any(|key|v.get(*key).is_some()){return false;}
        if v["action"]=="preflight" {
            return required&&v.get(ACK).is_none()&&(if v["success"]==true {preflight(v)}else{failed(v)});
        }
        if v["action"]=="commit" {
            return required&&hex(&v["preflight_token"],32)&&collarbone::acknowledgments(&v[ACK])&&paired(v)&&commit(v);
        }
        return false;
    }
    !(matches!(v["action"].as_str(),Some("preflight"|"commit"))&&selected(v)&&(v["success"]==true||v["outcome_unknown"]==true))
}
#[cfg(test)]
#[path="face_decoration_batch_protocol_unrun.rs"]
mod tests;
