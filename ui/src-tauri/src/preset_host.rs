//! Preset-specific protocol and document binding atop the shared mailbox.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
pub(crate) struct PresetKind;
fn text(value: &Value) -> bool { value.as_str().is_some_and(|s| !s.trim().is_empty()) }
fn scope(value: &Value) -> bool {
    value.as_array().is_some_and(|a| !a.is_empty() && a.iter().all(text)
        && a.iter().filter_map(Value::as_str).collect::<std::collections::BTreeSet<_>>().len() == a.len())
}
fn modules(value: &Value, ops: &Value) -> bool {
    let (Some(map), Some(ops)) = (value.as_object(), ops.as_array()) else { return false };
    map.len() == ops.len() && ops.iter().all(|op| op.as_str().is_some_and(|op| map.get(op).is_some_and(Value::is_object)))
}
fn preset(value: &Value) -> bool {
    value["schema"] == "lrt.preset.v1" && text(&value["id"]) && text(&value["name"])
        && text(&value["kind"]) && value["builtin"].is_boolean() && value["modules"].as_object().is_some_and(|m| !m.is_empty() && m.values().all(Value::is_object))
}
fn optical_review(value: &Value, document: &Value, revision: &Value, params: &Value) -> bool {
    let hash = |v: &Value| v.as_str().is_some_and(|s| s.len()==64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)));
    let number = |v: &Value, lo: f64, hi: f64| v.as_f64().is_some_and(|n| n.is_finite() && n>=lo && n<=hi);
    let mode=value["auto_mode"].as_str();
    if value["version"]!=1 || value["success"]!=true || &value["document_id"]!=document || &value["revision"]!=revision
        || !hash(&value["proof"]) || !hash(&value["candidate_key"]) || !number(&value["crop_zoom"],1.,32.)
        || !matches!(mode,Some("off"|"smart"|"horizontal"|"vertical")) || !value["lens_auto"].is_boolean()
        || value["auto_mode"]!=params["request"]["auto_mode"] || value["lens_auto"]!=params["request"]["lens_auto"] { return false; }
    let a=&value["analysis"];
    if mode==Some("off") { if !a.is_null(){return false;} }
    else if !text(&a["method"]) || !number(&a["confidence"],0.45,1.) || !a["lines"].as_u64().is_some_and(|n| (4..=512).contains(&n))
        || !number(&a["residual_degrees"],0.,90.) || !a["message"].is_string() {return false;}
    let p=&value["lens"];
    if value["lens_auto"]==true {
        if !hash(&p["database_sha256"]) || !text(&p["library_version"]) || !text(&p["camera_model"]) || !text(&p["lens_model"])
            || !number(&p["focal"],0.1,10000.) || !p["flags"].as_array().is_some_and(|a| !a.is_empty() && a.iter().all(|f| matches!(f.as_str(),Some("distortion"|"tca"|"vignette")))) {return false;}
    } else if !p.is_null(){return false;}
    if let Some(c)=value.get("comparison") {
        let (Some(before),Some(after))=(c["before"].as_str(),c["after"].as_str()) else{return false;};
        if c["domain"]!="post-manual-liquify-pre-crop-normalized" || !["width","height"].iter().all(|k|c[*k].as_u64().is_some_and(|n|(1..=320).contains(&n)))
            || before.len()+after.len()>1024*1024 || ![before,after].iter().all(|s|s.starts_with("data:image/png;base64,iVBOR") && s[22..].bytes().all(|b|b.is_ascii_alphanumeric()||b"+/=".contains(&b))) {return false;}
    }
    true
}
fn crop_review(value:&Value,document:&Value,revision:&Value,params:&Value)->bool {
    let hash=|v:&Value|v.as_str().is_some_and(|s|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)));
    let size=|v:&Value|v.as_array().is_some_and(|a|a.len()==2&&a.iter().all(|n|n.as_u64().is_some_and(|n|n>0)));
    if value.as_object().map_or(true,|m|m.len()!=10)||value["version"]!=1||&value["document_id"]!=document||&value["revision"]!=revision
        ||!hash(&value["candidate_sha256"])||!hash(&value["people_sha256"])||&value["crop"]!=params
        ||!size(&value["source_size"])||!size(&value["output_size"]){return false;}
    let crop=&value["crop"];
    let Some(rect)=crop["rect_normalized"].as_array() else{return false;};
    if crop.as_object().map_or(true,|m|m.len()!=2)||rect.len()!=4
        ||!rect.iter().all(|n|n.as_f64().is_some_and(|n|n.is_finite()&&(0.0..=1.0).contains(&n)))
        ||rect[0].as_f64()>=rect[2].as_f64()||rect[1].as_f64()>=rect[3].as_f64()
        ||!crop["rotation_degrees"].as_f64().is_some_and(|n|n.is_finite()&&(-180.0..=180.0).contains(&n)){return false;}
    let source=&value["source_proof"];let creative=&source["creative_source"];
    if source.as_object().map_or(true,|m|m.len()!=3||!m.contains_key("creative_source"))||!hash(&source["asset_sha256"])||!hash(&source["original_sha256"]){return false;}
    if creative.is_null(){if source["asset_sha256"]!=source["original_sha256"]{return false;}}
    else if creative.as_object().map_or(true,|m|m.len()!=3)||creative["sha256"]!=source["asset_sha256"]
        ||creative["width"]!=value["source_size"][0]||creative["height"]!=value["source_size"][1]{return false;}
    let preview=&value["preview"];
    let Some(bytes)=preview["base64"].as_str() else{return false;};
    preview.as_object().is_some_and(|m|m.len()==5)&&preview["mime"]=="image/png"&&hash(&preview["sha256"])
        &&["width","height"].iter().all(|k|preview[*k].as_u64().is_some_and(|n|(1..=320).contains(&n)))
        &&bytes.len()<=400000&&bytes.len()%4==0&&bytes.starts_with("iVBOR")
        &&bytes.bytes().all(|b|b.is_ascii_alphanumeric()||b"+/=".contains(&b))
}
fn reviewed_types(value: &Value) -> bool {
    let Some(ops)=value["module_scope"].as_array() else{return false;};
    let local=ops.iter().any(|op|op=="lnx.local_grade.v1");
    let optics=ops.iter().any(|op|op=="lnx.optics_auto.v1");
    let crop=ops.iter().any(|op|op=="lnx.crop.v1");
    (local||optics||crop) && (!local||value["local_mask_transfer"].is_object())
        && (!optics||optical_review(&value["optical_transfer"],&value["document_id"],&value["revision"],&value["applies"]["lnx.optics_auto.v1"]))
        && (!crop||crop_review(&value["crop_transfer"],&value["document_id"],&value["revision"],&value["applies"]["lnx.crop.v1"]))
}
impl ReceiptKind for PresetKind {
    const NAME: &'static str = "preset";
    const ACTIONS: &'static [&'static str] = &["list", "preflight", "apply", "save", "import", "delete"];
    fn valid_request(action: &str, document: Option<&str>) -> bool {
        if ["apply", "preflight", "save"].contains(&action) {
            document.is_some_and(|d| !d.is_empty() && d.len() <= 128 && d.chars().count() <= 64)
        } else { document.is_none() }
    }
    fn valid(value: &Value, document: Option<&str>) -> bool {
        let Some(success) = value["success"].as_bool() else { return false };
        let Some(unknown) = value["outcome_unknown"].as_bool() else { return false };
        if value["protocol"].as_u64() != Some(1) || (success && unknown) { return false; }
        if document.is_some() && value["document_id"].as_str() != document { return false; }
        if !success { return true; }
        match value["action"].as_str() {
            Some("preflight") => text(&value["id"]) && scope(&value["module_scope"])
                && modules(&value["applies"], &value["module_scope"])
                && value["preflight_token"].as_str().is_some_and(|s| s.len() == 32 && s.bytes().all(|b| b.is_ascii_hexdigit()))
                && reviewed_types(value) && text(&value["revision"]),
            Some("list") => value["catalog"]["available"] == true && value["catalog"]["list"].as_array().is_some_and(|items| items.iter().all(preset))
                && value["catalog"]["errors"].is_array() && value["catalog"]["modules"].is_array(),
            Some("apply") => text(&value["id"]) && scope(&value["module_scope"]) && modules(&value["before"], &value["module_scope"])
                && modules(&value["after"], &value["module_scope"]) && value["doc_state"].is_object()
                && value["doc_state"]["document_id"].as_str() == document,
            Some("save" | "import") => text(&value["id"]) && text(&value["path"]) && scope(&value["module_scope"])
                && preset(&value["preset"]) && value["preset"]["id"] == value["id"] && modules(&value["preset"]["modules"], &value["module_scope"]),
            Some("delete") => text(&value["id"]) && text(&value["path"]),
            _ => false,
        }
    }
    fn decorate_failure(value: &mut Value, document: Option<&str>) {
        value["protocol"] = json!(1);
        if let Some(document) = document { value["document_id"] = json!(document); }
    }
}
pub(crate) type PresetHost = ReceiptHost<PresetKind>;
#[cfg(test)]
mod tests {
    use super::*;
    // AUTHORED / UNRUN. Synthetic receipt schema, not actual rendered PNG evidence.
    #[test] fn crop_only_preflight_requires_bound_preview_evidence() {
        let crop=json!({"rect_normalized":[0.0,0.0,1.0,1.0],"rotation_degrees":0.0});
        let report=json!({"version":1,"document_id":"doc","revision":"3",
            "source_proof":{"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null},
            "candidate_sha256":"b".repeat(64),"people_sha256":"c".repeat(64),"crop":crop,
            "source_size":[640,480],"output_size":[640,480],
            "preview":{"mime":"image/png","base64":"iVBORw==","width":320,"height":240,"sha256":"d".repeat(64)}});
        let value=json!({"protocol":1,"action":"preflight","success":true,"outcome_unknown":false,"id":"crop",
            "document_id":"doc","revision":"3","module_scope":["lnx.crop.v1"],"applies":{"lnx.crop.v1":crop},
            "preflight_token":"f".repeat(32),"crop_transfer":report});
        assert!(PresetKind::valid(&value,Some("doc")));
        for key in ["crop_transfer","revision"] {let mut changed=value.clone();changed.as_object_mut().unwrap().remove(key);assert!(!PresetKind::valid(&changed,Some("doc")));}
        let mut changed=value.clone();changed["crop_transfer"]["document_id"]=json!("other");assert!(!PresetKind::valid(&changed,Some("doc")));
        changed=value.clone();changed["crop_transfer"]["crop"]["rotation_degrees"]=json!(45);assert!(!PresetKind::valid(&changed,Some("doc")));
        changed=value.clone();changed["crop_transfer"]["preview"]["width"]=json!(321);assert!(!PresetKind::valid(&changed,Some("doc")));
    }
    fn host() -> PresetHost { let mut h = PresetHost::default(); h.reset([1; 16]); h.ready([1; 16], true); h }
    #[test] fn editing_actions_require_document_identity_but_catalog_does_not() {
        let mut h = host(); assert!(h.begin([1; 16], "a", "apply").is_err());
        assert!(h.begin_bound([1; 16], "a", "save", Some("doc")).is_ok());
        assert!(h.begin([1; 16], "b", "list").is_ok());
        assert!(h.begin_bound([1; 16], "c", "import", Some("doc")).is_err());
    }
    #[test] fn mismatched_document_and_missing_evidence_never_become_success() {
        let mut h = host(); h.begin_bound([1; 16], "a", "apply", Some("doc")).unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"a","action":"apply","success":true,"outcome_unknown":false,"document_id":"other"}));
        assert_eq!(h.status("a")["result"]["outcome_unknown"], true);
        assert_eq!(h.status("a")["result"]["document_id"], "doc");
        h.begin_bound([1; 16], "b", "save", Some("doc")).unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"b","action":"save","success":true,"outcome_unknown":false,"document_id":"doc"}));
        assert_eq!(h.status("b")["result"]["success"], false);
    }
    #[test] fn shutdown_and_send_failure_keep_protocol_identity_and_first_terminal() {
        let mut h = host(); h.begin_bound([1; 16], "a", "save", Some("doc")).unwrap(); h.failed("a", "send failed");
        assert_eq!(h.status("a")["result"]["protocol"], 1);
        assert_eq!(h.status("a")["result"]["document_id"], "doc");
        h.begin([1; 16], "b", "delete").unwrap();
        h.receive([1; 16], &json!({"protocol":1,"request_id":"b","action":"delete","success":true,"outcome_unknown":false,"id":"p","path":"/p.json"}));
        h.ended([1; 16]); assert_eq!(h.status("b")["result"]["success"], true);
        h.reset([2; 16]); assert_eq!(h.status("a")["phase"], "unavailable");
    }
    #[test] fn complete_receipts_are_accepted_for_all_actions() {
        let p = json!({"schema":"lrt.preset.v1","id":"p","name":"name","kind":"custom","builtin":false,"modules":{"hsl":{"recipe":{}}}});
        for action in ["list", "apply", "save", "import", "delete"] {
            let document = if ["apply", "save"].contains(&action) { Some("doc") } else { None };
            let value = json!({"protocol":1,"request_id":"r","action":action,"success":true,"outcome_unknown":false,
                "document_id":"doc","id":"p","path":"/p.json","module_scope":["hsl"],"preset":p,
                "before":{"hsl":{}},"after":{"hsl":{}},"doc_state":{"document_id":"doc"},
                "catalog":{"available":true,"list":[p],"errors":[],"modules":[]}});
            assert!(PresetKind::valid(&value, document), "{action}");
        }
    }
    #[test] fn duplicate_scope_and_incomplete_module_evidence_are_rejected() {
        let mut v = json!({"protocol":1,"request_id":"r","action":"save","success":true,"outcome_unknown":false,
            "document_id":"doc","id":"p","path":"/p.json","module_scope":["hsl"],
            "preset":{"schema":"lrt.preset.v1","id":"p","name":"name","kind":"custom","builtin":false,"modules":{"hsl":{}}}});
        assert!(PresetKind::valid(&v, Some("doc")));
        v["module_scope"] = json!(["hsl","hsl"]); assert!(!PresetKind::valid(&v, Some("doc")));
        v["module_scope"] = json!(["hsl"]); v["preset"]["modules"] = json!({}); assert!(!PresetKind::valid(&v, Some("doc")));
        v["action"] = json!("apply"); v["before"] = json!({}); v["after"] = json!({});
        v["doc_state"] = json!({"document_id":"doc"}); assert!(!PresetKind::valid(&v, Some("doc")));
    }

}
