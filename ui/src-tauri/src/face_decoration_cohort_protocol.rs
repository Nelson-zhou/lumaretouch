// SPDX-License-Identifier: GPL-3.0-or-later
//! Automatic decoration evidence for an exact source-first persistent cohort.
use serde_json::{json,Value};
use crate::batch_api::{portrait_cohort as P,collarbone as C,eye_cohort as E};
use crate::original_shadow_transfer_protocol::{hex,revision};
use crate::preset_api::visual::{fields,text,visual};
pub(crate) const KEY:&str="face_decoration_cohort";
pub(crate) const ACK:&str="face_decoration_cohort_ack";
pub(crate) const IMAGE:&str="face_decoration_cohort_visual";
const UNSUPPORTED:&[&str]=&["lnx.torso_length.v1","lnx.waist_length.v1","lnx.head_size.v1","lnx.spill_removal.v1","lnx.original_shadow.v1","lnx.id_background.v1"];
const OP:&str="lnx.face_decoration.v1";
const FOREIGN:&[&str]=&["face_decoration_review_ack","face_decoration_preset_ack","face_decoration_visual_required","eye_bag_review_ack","face_style_review_ack","torso_review_ack","waist_review_ack","head_review_ack","spill_review_ack","shadow_review_ack"];
fn preflight(v:&Value)->bool{
    let required=["cmd","action","request_id","docs","module_scope","people_transfer"];
    let Some(m)=v.as_object() else{return false;};
    if !required.iter().all(|k|m.contains_key(*k))||!m.keys().all(|k|required.contains(&k.as_str())||k=="conflict_policy")
        ||v["cmd"]!="batch"||v["action"]!="preflight"||!text(&v["request_id"])||!v.get("conflict_policy").map_or(true,|p|p=="recheck")
        ||!P::request(&v["people_transfer"])||!P::request_scope(&v["module_scope"],&v["people_transfer"]){return false;}
    let Some(docs)=v["docs"].as_array() else{return false;};let targets=v["people_transfer"]["targets"].as_array().unwrap();
    docs.len()==targets.len()&&targets.iter().all(|row|docs.iter().filter(|id|*id==&row["target"]["document"]["document_id"]).count()==1)
}
fn image_request(v:&Value)->bool{
    fields(v,&["cmd","action","request_id","preflight_token","document_id","revision","side","sha256"])
        &&v["cmd"]=="batch"&&v["action"]==IMAGE&&text(&v["request_id"])&&hex(&v["preflight_token"],32)
        &&hex(&v["document_id"],32)&&revision(&v["revision"])&&matches!(v["side"].as_str(),Some("before"|"after"))&&hex(&v["sha256"],64)
}
pub(crate) fn acknowledgments(v:&Value)->bool{C::acknowledgments(v)&&v.as_array().is_some_and(|r|(2..=16).contains(&r.len()))}
fn paired(v:&Value)->bool{
    let Some(rows)=v[ACK].as_array() else{return false;};
    [(P::ACK,P::acknowledgments as fn(&Value)->bool),(C::ACK,C::acknowledgments),(E::ACK,E::acknowledgments)].iter().all(|(k,check)|{
        let Some(other)=v.get(*k) else{return true;};check(other)&&other.as_array().is_some_and(|r|r.len()==rows.len()
            &&r.iter().zip(rows).all(|(a,b)|["document_id","revision","before_sha256","after_sha256"].iter().all(|f|a[*f]==b[*f])))
    })
}
pub(crate) fn command(v:&Value)->Result<(),String>{
    if v["cmd"]!="batch"{return Ok(());}
    if v["action"]==IMAGE{return if image_request(v){Ok(())}else{Err("Decoration cohort image requires exact frozen member identity".into())};}
    if v.get(KEY).is_some()||v["people_transfer"].get(KEY).is_some(){return Err("Decoration cohort classification is produced from the actual frozen graph".into());}
    if let Some(ack)=v.get(ACK){
        let mut names=vec!["cmd","action","request_id","preflight_token","module_scope",ACK];
        for key in [P::ACK,C::ACK,E::ACK]{if v.get(key).is_some(){names.push(key);}}
        if !fields(v,&names)||v["action"]!="commit"||!text(&v["request_id"])||!hex(&v["preflight_token"],32)
            ||!P::scope(&v["module_scope"])||v["module_scope"].as_array().unwrap().iter().any(|op|UNSUPPORTED.iter().any(|bad|op==*bad))||!acknowledgments(ack)||!paired(v){return Err("Decoration cohort commit needs every source-first member image acknowledgment".into());}
    }
    Ok(())
}
pub(crate) fn read_only(v:&Value)->bool{image_request(v)||preflight(v)}
pub(crate) fn binding(v:&Value)->Result<Option<Value>,String>{
    command(v)?;if v["cmd"]!="batch"{return Ok(None);}
    if image_request(v){return Ok(Some(json!({"preflight_token":v["preflight_token"],"document_id":v["document_id"],"revision":v["revision"],"side":v["side"],"sha256":v["sha256"]})));}
    if let Some(ack)=v.get(ACK){let mut out=json!({"preflight_token":v["preflight_token"],"module_scope":v["module_scope"],(KEY):true,(ACK):ack});
        for (key,marker) in [(P::ACK,"portrait_cohort"),(C::ACK,"collarbone_cohort"),(E::ACK,"eye_bag_cohort")]{if let Some(a)=v.get(key){out[key]=a.clone();out[marker]=json!(true);}}
        return Ok(Some(out));}
    if preflight(v){return Ok(Some(json!({"module_scope":v["module_scope"],"policy":"recheck","face_decoration_cohort_applies_sha256":C::request_digest(&v["people_transfer"])})));}
    Ok(None)
}
pub(crate) fn evidence(v:&Value)->bool{
    v["action"]==IMAGE||v.get(KEY).is_some()||v.get(ACK).is_some()
        ||(v["applies"]["target_policy"]=="persistent_association"&&v["applies"]["selection"].get(OP).is_some())
        ||v["persistent_association"]["intent"].as_array().is_some_and(|r|r.iter().any(|x|x["op"]==OP))
        ||std::iter::once(&v["association_source"]).chain(v["targets"].as_array().into_iter().flatten()).any(|r|r["association"].get(KEY).is_some()||r["association"].get(IMAGE).is_some())
}
fn clean(v:&Value)->Value{
    let mut out=v.clone();if let Some(m)=out.as_object_mut(){m.remove(KEY);m.remove(ACK);}
    if let Some(m)=out["association_source"]["association"].as_object_mut(){m.remove(KEY);m.remove(IMAGE);}
    if let Some(rows)=out["targets"].as_array_mut(){for row in rows{if let Some(m)=row["association"].as_object_mut(){m.remove(KEY);m.remove(IMAGE);}}}
    out
}
fn failed(v:&Value)->bool{
    v["success"]==false&&v["outcome_unknown"].is_boolean()&&v["error"].as_str().is_some_and(|s|!s.trim().is_empty()&&s.chars().count()<=8000)
        &&(v["outcome_unknown"]==true||(v["batch_id"].is_null()&&v.get("doc_state").is_none()&&v["operation_committed"]!=true&&v["committed"]!=true
            &&v.get("applied").map_or(true,|r|r.as_array().is_some_and(Vec::is_empty))
            &&v.get("source_outcome").map_or(true,|r|r["result_revision"].is_null()&&matches!(r["outcome"].as_str(),Some("conflict"|"not_applied")))
            &&v.get("target_outcomes").map_or(true,|r|r.as_array().is_some_and(|r|r.iter().all(|x|x["result_revision"].is_null()&&matches!(x["outcome"].as_str(),Some("conflict"|"not_applied")))))))
}
fn intent(v:&Value)->bool{
    P::review(v)&&v["intent"].as_array().unwrap().iter().all(|leaf|!UNSUPPORTED.iter().any(|op|leaf["op"]==*op))&&v["intent"].as_array().unwrap().iter().all(|leaf|leaf["op"]!=OP||match leaf["path"].as_str(){
        Some("/strength")=>leaf["value"].as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n)),
        Some("/pattern")=>matches!(leaf["value"].as_str(),Some("freckle_dust"|"freckle_bridge"|"freckle_constellation"|"freckle_sunburst"|"freckle_scatter"|"mole_left_cheek"|"mole_right_cheek"|"mole_pair")),_=>false})
}
fn check_preflight(v:&Value)->bool{
    let applies=&v["applies"];let common=&v["persistent_association"];
    if !P::request(applies)||!P::request_scope(&v["module_scope"],applies)||!intent(common)||v["policy"]!="recheck"||v["people_transfer"]!=true
        ||common["operation"]!=applies["operation"]||common["association_id"]!=applies["association_id"]||!hex(&v["preflight_token"],32)
        ||v["blocked"].as_u64()!=Some(0)||v["rejected_docs"].as_array().map_or(true,|r|!r.is_empty())||v.to_string().len()>7*1024*1024{return false;}
    let Some(targets)=v["targets"].as_array() else{return false;};let wanted=applies["targets"].as_array().unwrap();let members=common["members"].as_array().unwrap();
    if targets.len()!=wanted.len()||members.len()!=targets.len()+1||v["ok"].as_u64()!=Some(targets.len() as u64){return false;}
    let source=&v["association_source"];if ["document_id","revision","path"].iter().any(|k|source[*k]!=v["source_snapshot"][*k]){return false;}
    let mut docs=std::collections::BTreeSet::new();let mut indices=std::collections::BTreeSet::new();
    for (i,row) in std::iter::once(source).chain(targets).enumerate(){
        let (owner,reference)=if i==0{(&applies["source"],&applies["source_ref"])}else{(&wanted[i-1]["target"],&wanted[i-1]["target_refs"][0])};
        let a=&row["association"];let proof=&a[IMAGE];let cov=&a[KEY];let mut names=vec!["owner","ref","candidate_sha256","person_id",KEY,IMAGE];
        if v["portrait_cohort"]==true{names.push("portrait_visual");}if v["collarbone_cohort"]==true{names.extend(["collarbone_coverage","collarbone_visual"]);}if v["eye_bag_cohort"]==true{names.extend(["eye_bag_cohort","eye_bag_cohort_visual"]);}
        if !fields(a,&names)||a["owner"]!=*owner||a["ref"]!=*reference||!hex(&a["candidate_sha256"],64)||!text(&a["person_id"])
            ||row["document_id"]!=owner["document"]["document_id"]||row["revision"].as_str()!=owner["document"]["revision"].as_u64().map(|n|n.to_string()).as_deref()
            ||!row["index"].is_u64()||!indices.insert(row["index"].as_u64().unwrap())||!row["blocked"].is_null()||!text(&row["document_id"])
            ||!docs.insert(row["document_id"].as_str().unwrap())||!row["path"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=4096)
            ||!members.iter().any(|m|m["document_id"]==row["document_id"]&&m["scope_id"]==owner["people_scope"]&&m["original_sha256"]==owner["source_proof"]["original_sha256"]&&m["ref"]==*reference)
            ||!crate::preset_api::face_decoration::coverage(cov,&owner["source_proof"],&json!([reference]))||!visual(proof,&row["document_id"],&row["revision"],&owner["source_proof"])
            ||proof["coverage_sha256"].as_str()!=Some(C::request_digest(cov).as_str()){return false;}
        for key in ["portrait_visual","collarbone_visual","eye_bag_cohort_visual"]{if let Some(other)=a.get(key){
            if !proof.as_object().unwrap().iter().all(|(k,value)|k=="coverage_sha256"||other.get(k)==Some(value)){return false;}
        }}
    }
    let leaves=common["intent"].as_array().unwrap();
    if applies["operation"]=="create"&&leaves.len()!=applies["selection"].as_object().unwrap().values().map(|p|p.as_array().unwrap().len()).sum::<usize>(){return false;}
    applies["operation"]=="unlink"||applies["selection"].as_object().unwrap().iter().all(|(op,paths)|paths.as_array().unwrap().iter().all(|path|leaves.iter().any(|leaf|leaf["op"].as_str()==Some(op.as_str())&&leaf["path"]==*path)))
}
fn commit(v:&Value)->bool{
    let (Some(targets),Some(acks),Some(applied),Some(skipped))=(v["target_outcomes"].as_array(),v[ACK].as_array(),v["applied"].as_array(),v["skipped"].as_array())else{return false;};
    let common=&v["persistent_association"];let source=&v["source_outcome"];
    if !crate::people_api::decoration_alias::summary(&v["face_decoration_cohort_review"])
        ||v["face_decoration_cohort_review"]["member_count"].as_u64()!=Some(acks.len() as u64)
        ||v["face_decoration_cohort_review"]["review_sha256"].as_str()!=Some(C::request_digest(&v[ACK]).as_str())
        ||!intent(common)||v["people_transfer"]!=true||targets.len()+1!=acks.len()||applied.len()!=acks.len()||!skipped.is_empty()||!text(&v["batch_id"])
        ||common["members"].as_array().unwrap().len()!=acks.len()||v["source_missing"]!=false||v["source_changed_since_preflight"]!=false
        ||source["document_id"]!=v["source_snapshot"]["document_id"]||source["expected_revision"]!=v["source_snapshot"]["revision"]||source["path"]!=v["source_snapshot"]["path"]
        ||(common["operation"]=="unlink"&&v["module_scope"]!=json!([])){return false;}
    let mut ids=std::collections::BTreeSet::new();let mut indices=std::collections::BTreeSet::new();
    std::iter::once(source).chain(targets).zip(acks).zip(applied).all(|((row,ack),idx)|fields(row,&["index","path","document_id","expected_revision","result_revision","outcome","blocked"])
        &&row["document_id"]==ack["document_id"]&&row["expected_revision"]==ack["revision"]&&revision(&row["result_revision"])
        &&row["result_revision"].as_str().unwrap().parse::<u64>().unwrap()>ack["revision"].as_str().unwrap().parse::<u64>().unwrap()
        &&row["outcome"]=="applied"&&row["blocked"].is_null()&&row["index"].is_u64()&&row["index"]==*idx&&indices.insert(row["index"].as_u64().unwrap())
        &&ids.insert(row["document_id"].as_str().unwrap())&&row["path"].as_str().is_some_and(|s|!s.is_empty()&&s.len()<=4096)
        &&common["members"].as_array().unwrap().iter().any(|m|m["document_id"]==row["document_id"]))
}
pub(crate) fn receipt(v:&Value)->bool{
    if v["action"]==IMAGE{let mut c=v.clone();c["action"]=json!("face_decoration_visual");return crate::batch_api::face_decoration::receipt(&c);}
    if !evidence(v){return true;}
    if FOREIGN.iter().any(|k|v.get(*k).is_some())||v.get(KEY).is_some_and(|x|x!=true){return false;}
    if v["success"]!=true{return failed(v)&&(v["action"]=="preflight"||v["action"]=="commit"&&v[KEY]==true&&acknowledgments(&v[ACK])&&paired(v));}
    if v[KEY]!=true||v.get("outcome_unknown").is_some_and(|x|x!=false){return false;}
    let valid=match v["action"].as_str(){Some("preflight")=>v.get(ACK).is_none()&&check_preflight(v),Some("commit")=>P::scope(&v["module_scope"])&&hex(&v["preflight_token"],32)&&acknowledgments(&v[ACK])&&paired(v)&&commit(v),_=>false};
    if !valid{return false;}
    let c=clean(v);
    E::receipt(&c)&&P::receipt(&c)&&C::receipt(&c)&&C::preflight(&c)
}
#[cfg(test)]
#[path="face_decoration_cohort_protocol_unrun.rs"]
mod tests;
