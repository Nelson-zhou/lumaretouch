// SPDX-License-Identifier: GPL-3.0-or-later
//! HairSmoothing review transport only. Existing people mailbox remains sole receipt owner.
//! Authored / UNRUN: not numerical, browser, renderer or photographic acceptance.
use serde_json::{json, Value};
use std::collections::BTreeSet;
use crate::original_shadow_transfer_protocol::hex;
use super::skin_reference_match::{fields, allowed, identifier, revision, amount, face_ref};

pub(crate) const MARKER: &str = "hair_smoothing_request";
pub(crate) const ACTIONS: &[&str] = &["hair_smoothing_reference", "hair_smoothing_preview", "hair_smoothing_crop", "hair_smoothing_confirm", "hair_smoothing_detach"];
const OP: &str = "lnx.hair_smoothing.v1";
const REQUEST: &[&str] = &["action", "payload", "document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const CONTEXT: &[&str] = &["document_id", "document_epoch", "document_revision", "state_revision", "association_revision", "target"];
const MAX_RESULT: usize = 18 * 1024 * 1024;

pub(crate) fn neutral_patch(v: &Value) -> bool {
    if v["action"] != "patch" || !fields(&v["payload"], &["patches"]) { return false; }
    v["payload"]["patches"].as_array().is_some_and(|rows| rows.len() == 1 && {
        let row = &rows[0];
        fields(row, &["operation_id","parameter_path","unset","value"])
            && row["operation_id"] == OP && row["parameter_path"] == "/amount"
            && row["unset"] == false && row["value"].as_f64() == Some(0.0)
    })
}
pub(crate) fn action(v: &Value) -> bool {
    v["action"].as_str().is_some_and(|name| ACTIONS.contains(&name)) || neutral_patch(v)
        || (v["action"] == "patch" && neutral_patch(&v[MARKER]))
}
pub(crate) fn mutation(v: &Value) -> bool {
    matches!(v["action"].as_str(), Some("hair_smoothing_confirm" | "hair_smoothing_detach")) || neutral_patch(v)
}
fn coordinate(v: &Value, low: f64, high: f64) -> bool {
    v.as_array().is_some_and(|a| a.len() == 2 && a.iter().all(|n| n.as_f64().is_some_and(|n| n.is_finite() && (low..=high).contains(&n))))
}
fn mask(v: &Value, protect: bool) -> Option<usize> {
    if !fields(v, &["version","domain","objects"]) || v["version"] != 1 || v["domain"] != "source-normalized" { return None; }
    let objects = v["objects"].as_array()?;
    if objects.len() > 64 { return None; }
    let mut ids = BTreeSet::new(); let mut points = 0; let mut positive = false;
    for row in objects {
        if !fields(row, &["id","name","enabled","operation","kind","opacity","feather","points","axes"])
            || !row["id"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 64 && s.bytes().all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b)) && ids.insert(s))
            || !row["name"].as_str().is_some_and(|s| !s.trim().is_empty() && s.chars().count() <= 80 && s.chars().all(|c| c >= ' '))
            || !row["enabled"].is_boolean() || row["kind"] != "brush" || !matches!(row["operation"].as_str(), Some("add" | "subtract"))
            || !amount(&row["opacity"],false) || !row["feather"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=100.0).contains(&n)) { return None; }
        let stroke = row["points"].as_array()?; let axes = row["axes"].as_array()?;
        if !(1..=1024).contains(&stroke.len()) || !stroke.iter().all(|p| coordinate(p,0.0,1.0)) || axes.len() != 2
            || !axes.iter().all(|p| coordinate(p,-4.0,4.0)) { return None; }
        let det = axes[0][0].as_f64()? * axes[1][1].as_f64()? - axes[0][1].as_f64()? * axes[1][0].as_f64()?;
        if det.abs() < 1e-12 || (protect && (row["enabled"] != true || row["operation"] != "add" || row["opacity"].as_f64() != Some(1.0) || row["feather"].as_f64() != Some(0.0))) { return None; }
        points += stroke.len(); positive |= row["enabled"] == true && row["operation"] == "add" && amount(&row["opacity"],true);
    }
    if points <= 4096 && (protect || positive) { Some(points) } else { None }
}
fn review(v: &Value) -> bool {
    if !fields(v, &["version","domain","target_recipe","context_recipe","protect_recipe","texture_scale",
        "visible_hair_reviewed","protections_reviewed","ownership_confirmed"])
        || v["version"] != 1 || v["domain"] != "source-normalized" || !amount(&v["texture_scale"],true)
        || !["visible_hair_reviewed","protections_reviewed","ownership_confirmed"].iter().all(|k| v[*k] == true) {return false;}
    let (Some(target),Some(context),Some(protect)) = (mask(&v["target_recipe"],false),mask(&v["context_recipe"],false),mask(&v["protect_recipe"],true)) else {return false;};
    target + context + protect <= 4096 && v.to_string().len() <= 192 * 1024
}
fn rect(v: &Value) -> bool {
    v.as_array().is_some_and(|a| a.len() == 4 && a[0].as_u64().is_some_and(|n| n <= 1_000_000)
        && a[1].as_u64().is_some_and(|n| n <= 1_000_000) && a[2..].iter().all(|n| n.as_u64().is_some_and(|n| (1..=1024).contains(&n))))
}
fn inspection(v: &Value) -> bool {
    fields(v, &["rect","before_sha256","after_sha256"]) && rect(&v["rect"]) && hex(&v["before_sha256"],64) && hex(&v["after_sha256"],64)
}
pub(crate) fn command(v: &Value) -> Result<(), String> {
    if !action(v) { return Ok(()); }
    let mut context=json!({}); for key in CONTEXT { context[*key]=v[*key].clone(); }
    let p=&v["payload"]; let asset=&v["target"]["face_ref"]["asset_sha256"];
    let valid=allowed(v,REQUEST,&["cmd","request_id","host_epoch"]) && v.to_string().len() <= 256*1024
        && v.get("cmd").map_or(true, |c| c == "people" && identifier(&v["request_id"]))
        && v.get("request_id").map_or(true,identifier) && v.get("host_epoch").map_or(true, |e| hex(e,32) && v["cmd"] == "people")
        && super::valid_context(&context) && v["target"]["scope"] == "face" && face_ref(&v["target"]["face_ref"],asset)
        && v["target"]["target_id"] == v["target"]["face_ref"]["face_instance_id"]
        && match v["action"].as_str() {
            Some("hair_smoothing_reference" | "hair_smoothing_detach") => fields(p,&[]),
            Some("hair_smoothing_preview") => fields(p,&["review","amount"]) && amount(&p["amount"],true) && review(&p["review"]),
            Some("hair_smoothing_crop") => {
                let id=if p["plane"] == "source" {"reference_id"} else {"preview_id"};
                fields(p,&[id,"plane","rect"]) && identifier(&p[id]) && rect(&p["rect"]) && matches!(p["plane"].as_str(),Some("source"|"before"|"after"))
            },
            Some("hair_smoothing_confirm") => fields(p,&["preview_id","reviewed","before_sha256","after_sha256","support_sha256","inspection"])
                && identifier(&p["preview_id"]) && p["reviewed"] == true && ["before_sha256","after_sha256","support_sha256"].iter().all(|k| hex(&p[*k],64)) && inspection(&p["inspection"]),
            Some("patch") => neutral_patch(v),
            _ => false,
        };
    if valid { Ok(()) } else { Err("头发柔顺审核需要准确本人头发归属、独立保护笔迹与完整图像及原像素检查凭据".into()) }
}
pub(crate) fn binding(v: &Value) -> Result<Option<Value>,String> {
    if v["cmd"] != "people" || !action(v) { return Ok(None); }
    command(v)?; let mut r=json!({}); for k in REQUEST { r[*k]=v[*k].clone(); }
    Ok(Some(json!({"hair_smoothing_request":r})))
}
pub(crate) fn read_only(v: &Value) -> bool {
    v["cmd"] == "people" && matches!(v["action"].as_str(),Some("hair_smoothing_reference"|"hair_smoothing_preview"|"hair_smoothing_crop")) && command(v).is_ok()
}
/// An unrelated, malformed or merely same-ID terminal cannot release the
/// cross-domain pending-write fence. The original request owns this receipt.
pub(crate) fn matches_request(command: &Value, value: &Value) -> bool {
    if command["cmd"] != "people" || !action(command) || !receipt(value)
        || value["event"] != "people_result" || command["request_id"] != value["request_id"]
        || command["action"] != value["action"] || value["outcome_unknown"] != false { return false; }
    let Ok(Some(identity)) = binding(command) else { return false; };
    identity[MARKER] == value[MARKER]
}
fn source(v: &Value, asset: &Value) -> bool {
    fields(v,&["sha256","width","height"]) && v["sha256"] == *asset && hex(asset,64)
        && ["width","height"].iter().all(|k| v[*k].as_u64().is_some_and(|n| (2..=1_000_000).contains(&n)))
}
fn source_binding(p: &Value, r: &Value) -> bool {
    let s=&p["source"]; let proof=&p["source_proof"]; let asset=&r["target"]["face_ref"]["asset_sha256"];
    source(s,asset)
        && s["width"].as_u64().zip(s["height"].as_u64()).is_some_and(|(w,h)| w<=65536 && h<=65536 && w.checked_mul(h).is_some_and(|n| n<=32_000_000))
        && fields(proof,&["asset_sha256","original_sha256","creative_source"]) && proof["asset_sha256"] == *asset
        && hex(&proof["original_sha256"],64) && proof["creative_source"].is_null() && proof["original_sha256"] == *asset
        && hex(&p["input_sha256"],64) && hex(&p["repair_sha256"],64)
}
fn image(v: &Value, edge: u64) -> bool {
    use base64::{engine::general_purpose::STANDARD, Engine as _}; use sha2::{Digest,Sha256};
    if !fields(v,&["mime","base64","width","height","sha256"]) || v["mime"] != "image/png" || !hex(&v["sha256"],64) { return false; }
    let (Some(w),Some(h),Some(s))=(v["width"].as_u64(),v["height"].as_u64(),v["base64"].as_str()) else {return false;};
    if !(1..=edge).contains(&w) || !(1..=edge).contains(&h) || s.is_empty() || s.len() > 5_592_408 || s.len()%4 != 0 {return false;}
    let Ok(bytes)=STANDARD.decode(s) else {return false;};
    bytes.len() <= 4*1024*1024 && STANDARD.encode(&bytes) == s && bytes.get(25) == Some(&2)
        && crate::torso_transfer_protocol::png(&bytes,w as u32,h as u32) && format!("{:x}",Sha256::digest(&bytes)) == v["sha256"].as_str().unwrap()
}
fn size(v: &Value) -> Option<(u64,u64)> {
    let a=v.as_array()?; if a.len()!=2 {return None;} let w=a[0].as_u64()?; let h=a[1].as_u64()?;
    if (2..=1_000_000).contains(&w) && (2..=1_000_000).contains(&h) {Some((w,h))} else {None}
}
fn full_frame(i: &Value, w: u64, h: u64) -> bool {
    let (Some(iw),Some(ih))=(i["width"].as_u64(),i["height"].as_u64()) else {return false;};
    iw<=w && ih<=h && (iw*h).abs_diff(ih*w)<=w.max(h)
}
fn family(v: &Value) -> bool {v["family"] == "hair_smoothing" && v["operation_id"] == OP}
fn diagnostics(v: &Value, w: u64, h: u64, review: &Value) -> bool {
    if !fields(v,&["supported_pixels","context_rejected_pixels","directional_pixels","changed_pixels",
        "no_signal_reason","texture_scale_px","runtime_quality_accepted"]) || v["runtime_quality_accepted"] != false {return false;}
    let Some(total)=w.checked_mul(h) else {return false;};
    let (Some(supported),Some(rejected),Some(directional),Some(changed))=(v["supported_pixels"].as_u64(),v["context_rejected_pixels"].as_u64(),
        v["directional_pixels"].as_u64(),v["changed_pixels"].as_u64()) else {return false;};
    let (Some(scale),Some(requested))=(v["texture_scale_px"].as_f64(),review["texture_scale"].as_f64()) else {return false;};
    supported<=total && rejected<=total && changed<=directional && directional<=supported
        && scale.is_finite() && (1.0..=8.0).contains(&scale) && (scale-requested*w.min(h) as f64).abs()<=1e-9
        && (v["no_signal_reason"].is_null() || v["no_signal_reason"].as_str().is_some_and(|s| !s.is_empty() && s.chars().count()<=256))
}
fn payload(p: &Value, r: &Value) -> bool {
    if !family(p) || !source_binding(p,r) {return false;}
    let w=p["source"]["width"].as_u64().unwrap(); let h=p["source"]["height"].as_u64().unwrap();
    match r["action"].as_str() {
        Some("hair_smoothing_reference") => {
            fields(p,&["kind","family","operation_id","reference_id","source","source_proof","input_sha256","repair_sha256","face_ref",
                "hair_colour_asset_sha256","ownership_review_key","semantic_evidence_sha256","retained_faces_sha256","source_image","attached"])
                && p["kind"] == "reference" && identifier(&p["reference_id"]) && p["face_ref"] == r["target"]["face_ref"] && p["attached"].is_boolean()
                && image(&p["source_image"],1152) && full_frame(&p["source_image"],w,h)
                && ["hair_colour_asset_sha256","ownership_review_key","semantic_evidence_sha256","retained_faces_sha256"].iter().all(|k| hex(&p[*k],64))
        },
        Some("hair_smoothing_preview") => {
            let Some((ow,oh))=size(&p["before_output_size"]) else {return false;};
            fields(p,&["kind","family","operation_id","preview_id","source","source_proof","input_sha256","repair_sha256","face_ref","review","amount","before","after","support","before_output_size","after_output_size","diagnostics","runtime_quality_accepted"])
                && p["kind"] == "preview" && identifier(&p["preview_id"]) && p["face_ref"] == r["target"]["face_ref"]
                && p["review"] == r["payload"]["review"] && p["amount"] == r["payload"]["amount"] && p["runtime_quality_accepted"] == false
                && p["after_output_size"] == p["before_output_size"] && ["before","after","support"].iter().all(|k| image(&p[*k],1152))
                && p["before"]["width"] == p["after"]["width"] && p["before"]["height"] == p["after"]["height"]
                && full_frame(&p["before"],ow,oh) && full_frame(&p["after"],ow,oh) && full_frame(&p["support"],w,h)
                && ow == w && oh == h && review(&p["review"]) && diagnostics(&p["diagnostics"],w,h,&p["review"])
                && p["review"]["texture_scale"].as_f64().is_some_and(|n| (1.0..=8.0).contains(&(n*w.min(h) as f64)))
        },
        Some("hair_smoothing_crop") => {
            let id=if r["payload"]["plane"] == "source" {"reference_id"} else {"preview_id"};
            let rect=&r["payload"]["rect"];
            fields(p,&["kind","family","operation_id",id,"plane","rect","domain","source","source_proof","input_sha256","repair_sha256","image"])
                && p["kind"] == "crop" && p[id] == r["payload"][id] && p["plane"] == r["payload"]["plane"] && p["rect"] == *rect
                && p["domain"] == (if id=="reference_id" {"source"} else {"rendered_result"})
                && image(&p["image"],1024) && p["image"]["width"] == rect[2] && p["image"]["height"] == rect[3]
                && rect[0].as_u64().unwrap()+rect[2].as_u64().unwrap()<=w && rect[1].as_u64().unwrap()+rect[3].as_u64().unwrap()<=h
        },
        _ => false,
    }
}
/// Checks publication against the exact retained request. The application owner
/// additionally binds confirmation amount/images to its retained preview, not
/// to newly selected UI state. No support replacement is inferred from a label.
pub(crate) fn post_state(v: &Value, r: &Value) -> bool {
    let people=&v["doc_state"]["people"]; let b=&people["binding"]; let report=&people["hair_smoothing"];
    let face=&r["target"]["face_ref"]; let resolved=&people["resolved"];
    let confirm=r["action"] == "hair_smoothing_confirm";
    let expected=if confirm {v["payload"]["amount"].as_f64()} else {Some(0.0)};
    let Some(expected)=expected else {return false;};
    if !expected.is_finite() || !(0.0..=1.0).contains(&expected) || (confirm && expected<=0.0)
        || b["document_id"] != r["document_id"] || b["document_epoch"] != r["document_epoch"] || b["asset_sha256"] != face["asset_sha256"]
        || !b["document_revision"].as_u64().zip(r["document_revision"].as_u64()).is_some_and(|(a,b)| a>=b && a<=9_007_199_254_740_991)
        || !people["revision"].as_u64().zip(r["state_revision"].as_u64()).is_some_and(|(a,b)| a>=b && a<=9_007_199_254_740_991)
        || people["association_revision"] != r["association_revision"] || people["editing_target"] != r["target"]
        || people["selected_face_id"] != face["face_instance_id"] || resolved["face_ref"] != *face
        || resolved["state_revision"] != people["revision"] || resolved["association_revision"] != people["association_revision"] {return false;}
    let leaf=&resolved["operations"][OP]["/amount"];
    if leaf["value"].as_f64()!=Some(expected) || leaf["scope"]!="face" || leaf["target_id"]!=face["face_instance_id"]
        || people["editing_overrides"][OP]["/amount"].as_f64()!=Some(expected) {return false;}
    let Some(conflicts)=resolved["conflicts"].as_array() else {return false;};
    if conflicts.iter().any(|c| c["operation_id"] == OP) {return false;}
    if !allowed(report,&["family","operation_id","attached","face_ref","source"],&["needs_review","reason"])
        || !family(report) || report["face_ref"] != *face || !source(&report["source"],&face["asset_sha256"]) || !report["attached"].is_boolean()
        || report.get("needs_review").is_some_and(|n| !n.is_boolean())
        || report.get("reason").is_some_and(|s| !s.is_null() && !s.is_string()) {return false;}
    if confirm {report["attached"] == true && report["needs_review"] == false}
    else if r["action"] == "hair_smoothing_detach" {report["attached"] == false}
    else {true} // Reset leaves owned support untouched; UI compares captured report.
}
pub(crate) fn receipt(v: &Value) -> bool {
    if !action(v) && v.get(MARKER).is_none() {return true;}
    let r=&v[MARKER];
    if !allowed(v,&["protocol","request_id","action","document_id","success","outcome_unknown",MARKER],
        &["event","error","created_id","batch_id","frame_emitted","payload","doc_state","payload_released"])
        || !fields(r,REQUEST) || !action(r) || command(r).is_err() || r["action"]!=v["action"] || r["document_id"]!=v["document_id"]
        || v["protocol"]!=1 || !identifier(&v["request_id"]) || !v["success"].is_boolean() || !v["outcome_unknown"].is_boolean()
        || v.to_string().len()>MAX_RESULT || !v["batch_id"].is_null() || !v["created_id"].is_null()
        || v.get("event").is_some_and(|e| e!="people_result") {return false;}
    let read=matches!(r["action"].as_str(),Some("hair_smoothing_reference"|"hair_smoothing_preview"|"hair_smoothing_crop"));
    if v.get("payload_released").is_some() {
        return read && v["payload_released"]==true && v["success"]==true && v["outcome_unknown"]==false
            && v.get("payload").is_none() && v.get("doc_state").is_none() && v["frame_emitted"]!=true;
    }
    if v["success"]!=true {
        return v["error"].as_str().is_some_and(|s| !s.trim().is_empty()) && v.get("payload").is_none() && v.get("doc_state").is_none()
            && v["frame_emitted"] != true;
    }
    if v["outcome_unknown"]!=false || !v["error"].is_null() {return false;}
    if read {return v.get("doc_state").is_none() && v["frame_emitted"]!=true && payload(&v["payload"],r);}
    if r["action"]=="patch" {return neutral_patch(r) && post_state(v,r);}
    let p=&v["payload"]; let confirm=r["action"]=="hair_smoothing_confirm";
    fields(p,&["kind","family","operation_id","attached","amount"]) && family(p)
        && p["kind"]==(if confirm {"confirmed"} else {"detached"}) && p["attached"]==confirm
        && amount(&p["amount"],confirm) && (confirm || p["amount"].as_f64()==Some(0.0)) && post_state(v,r)
}

#[cfg(test)]
mod tests {
    // AUTHORED / UNRUN. Pure validation fixtures, never proof of native execution.
    use super::*;
    fn request(action: &str, payload: Value) -> Value {
        json!({"action":action,"payload":payload,"document_id":"doc","document_epoch":"epoch",
            "document_revision":1,"state_revision":1,"association_revision":0,
            "target":{"scope":"face","target_id":"face","face_ref":{"asset_sha256":"a".repeat(64),"face_instance_id":"face","analysis_revision":1}}})
    }
    #[test] fn admits_reference_not_source_injection() {
        assert!(command(&request("hair_smoothing_reference",json!({}))).is_ok());
        assert!(command(&request("hair_smoothing_reference",json!({"source":"donor"}))).is_err());
    }
    #[test] fn confirms_all_images_and_native_pair() {
        let p=json!({"preview_id":"preview","reviewed":true,"before_sha256":"a".repeat(64),"after_sha256":"b".repeat(64),
            "support_sha256":"c".repeat(64),"inspection":{"rect":[0,0,512,512],"before_sha256":"d".repeat(64),"after_sha256":"e".repeat(64)}});
        assert!(command(&request("hair_smoothing_confirm",p.clone())).is_ok());
        let mut missing=p; missing.as_object_mut().unwrap().remove("inspection");
        assert!(command(&request("hair_smoothing_confirm",missing)).is_err());
    }
    #[test] fn crop_identity_cannot_mix_domains() {
        assert!(command(&request("hair_smoothing_crop",json!({"reference_id":"ref","plane":"source","rect":[0,0,1024,1]}))).is_ok());
        assert!(command(&request("hair_smoothing_crop",json!({"reference_id":"ref","plane":"after","rect":[0,0,16,16]}))).is_err());
        assert!(!rect(&json!([0,0,1025,1]))); assert!(!rect(&json!([0.5,0,1,1])));
    }
    #[test] fn neutral_patch_is_exact_not_general_bypass() {
        let p=json!({"patches":[{"operation_id":OP,"parameter_path":"/amount","unset":false,"value":0}]});
        assert!(neutral_patch(&request("patch",p.clone())));
        let mut active=request("patch",p); active["payload"]["patches"][0]["value"]=json!(0.4);
        assert!(!neutral_patch(&active));
    }
    #[test] fn alias_and_fake_success_refused() {
        let mut r=request("hair_smoothing_reference",json!({})); r["target"]["scope"]=json!("all_people");
        assert!(command(&r).is_err());
        let v=json!({"protocol":1,"request_id":"r","action":"hair_smoothing_detach","document_id":"doc","success":true,"outcome_unknown":false,
            "hair_smoothing_request":request("hair_smoothing_detach",json!({})),"payload":{"kind":"detached","family":"hair_smoothing","operation_id":OP,"attached":false,"amount":0}});
        assert!(!receipt(&v));
    }
    #[test] fn no_image_hash_is_no_image_proof() {
        assert!(!image(&json!({"mime":"image/png","width":1,"height":1,"sha256":"a".repeat(64),"base64":"iVBORw=="}),1152));
    }
    #[test] fn original_only_rejects_same_size_derived_proof() {
        let r=request("hair_smoothing_reference",json!({}));
        let source=json!({"sha256":"a".repeat(64),"width":200,"height":100});
        let mut p=json!({"source":source,"source_proof":{"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null},
            "input_sha256":"b".repeat(64),"repair_sha256":"c".repeat(64)});
        assert!(source_binding(&p,&r));
        p["source_proof"]["creative_source"]=p["source"].clone();
        assert!(!source_binding(&p,&r));
    }
    #[test] fn unknown_failure_cannot_release_original_write_fence() {
        let mut command=request("hair_smoothing_detach",json!({}));
        command["cmd"]=json!("people"); command["request_id"]=json!("pending");
        let request=binding(&command).unwrap().unwrap()[MARKER].clone();
        let mut result=json!({"event":"people_result","protocol":1,"request_id":"pending","action":"hair_smoothing_detach",
            "document_id":"doc","success":false,"outcome_unknown":true,"error":"Uncertain","hair_smoothing_request":request});
        assert!(receipt(&result)); assert!(!matches_request(&command,&result));
        result["outcome_unknown"]=json!(false); assert!(matches_request(&command,&result));
        result["hair_smoothing_request"]["document_epoch"]=json!("old"); assert!(!matches_request(&command,&result));
    }
    #[test] fn failed_read_cannot_claim_frame_publication() {
        let mut result=json!({"event":"people_result","protocol":1,"request_id":"r","action":"hair_smoothing_reference",
            "document_id":"doc","success":false,"outcome_unknown":false,"error":"Refused","frame_emitted":true,
            "hair_smoothing_request":request("hair_smoothing_reference",json!({}))});
        assert!(!receipt(&result)); result["frame_emitted"]=json!(false); assert!(receipt(&result));
    }

    #[test] fn diagnostics_preserve_distinct_bounded_counts_and_actual_source_scale() {
        let r=json!({"texture_scale":0.03});
        let mut d=json!({"supported_pixels":1000,"context_rejected_pixels":500,"directional_pixels":700,"changed_pixels":300,
            "no_signal_reason":null,"texture_scale_px":3.0,"runtime_quality_accepted":false});
        assert!(diagnostics(&d,200,100,&r));
        d["changed_pixels"]=json!(701); assert!(!diagnostics(&d,200,100,&r));
        d["directional_pixels"]=json!(0); d["changed_pixels"]=json!(0); d["no_signal_reason"]=json!("no-direction");
        assert!(diagnostics(&d,200,100,&r)); d["texture_scale_px"]=json!(4.0); assert!(!diagnostics(&d,200,100,&r));
    }

}
