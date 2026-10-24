//! Preset-specific protocol and document binding atop the shared mailbox.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use crate::spill_transfer_protocol as spill;
use crate::original_shadow_transfer_protocol as shadow;
use crate::torso_transfer_protocol as torso;
use crate::waist_transfer_protocol as waist;
#[path = "xmp_preset_protocol.rs"]
pub(crate) mod xmp_protocol;
pub(crate) struct PresetKind;
/// The transport envelope is shared; each operation still selects its own proof
/// validator and cannot borrow another family's transfer or acknowledgment.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum BodyReviewFamily { Torso, Waist, Head }
pub(crate) const BODY_REVIEW_FAMILIES: [BodyReviewFamily; 3] = [BodyReviewFamily::Torso, BodyReviewFamily::Waist, BodyReviewFamily::Head];
impl BodyReviewFamily {
    pub(crate) fn op(self) -> &'static str { match self { Self::Torso => torso::TORSO_OP, Self::Waist => waist::WAIST_OP, Self::Head => torso::HEAD_OP } }
    pub(crate) fn transfer_key(self) -> &'static str { match self { Self::Torso => "torso_transfer", Self::Waist => "waist_transfer", Self::Head => "head_transfer" } }
    pub(crate) fn ack_key(self) -> &'static str { match self { Self::Torso => "torso_review_ack", Self::Waist => "waist_review_ack", Self::Head => "head_review_ack" } }
    pub(crate) fn selected(self, value: &Value) -> bool {
        value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == self.op()))
    }
    pub(crate) fn parameters(self, value: &Value) -> bool { match self { Self::Torso => torso::parameters(value), Self::Waist => waist::parameters(value), Self::Head => torso::head_parameters(value) } }
    pub(crate) fn transfer(self, value: &Value, document: &Value, revision: &Value, params: &Value, source: &Value) -> bool {
        match self { Self::Torso => torso::transfer(value, document, revision, params, source), Self::Waist => waist::transfer(value, document, revision, params, source), Self::Head => torso::head_transfer(value, document, revision, params, source) }
    }
    pub(crate) fn max_targets(self) -> usize { match self { Self::Torso => torso::MAX_TARGETS, Self::Waist => waist::MAX_TARGETS, Self::Head => torso::MAX_TARGETS } }
    pub(crate) fn command(self, value: &Value) -> Result<(), String> {
        match self { Self::Torso => torso::command(value), Self::Waist => waist::command(value), Self::Head => torso::head_command(value) }
    }
    pub(crate) fn no_foreign_evidence(self, value: &Value) -> bool {
        ["spill_transfer", "shadow_transfer", "crop_transfer", "local_mask_transfer", "optical_transfer", "reference_color",
            "people_transfer", "persistent_association", "xmp_report", "xmp_transfer"]
            .iter().all(|key| value[*key].is_null())
            && ["spill_review_ack", "shadow_review_ack", "xmp_review_ack", "xmp_ack"]
                .iter().all(|key| value.get(*key).is_none())
            && BODY_REVIEW_FAMILIES.iter().filter(|other| **other != self)
                .all(|other| value[other.transfer_key()].is_null() && value.get(other.ack_key()).is_none())
    }
    pub(crate) fn receipt(self, value: &Value, command_kind: &str, terminal: &str) -> bool {
        let selected = self.selected(value);
        if !value[self.transfer_key()].is_null()
            && (command_kind != "preset" || !selected || value["success"] != true || value["action"] != "preflight") { return false; }
        if selected && (value["module_scope"].as_array().map_or(true, |ops| ops.len() != 1)
            || !self.no_foreign_evidence(value)
            || (value["success"] == true && value["outcome_unknown"] == true)
            || ((self == Self::Head || (self == Self::Waist && value["action"] == terminal)) && !value["outcome_unknown"].is_boolean())
            || value.get("outcome_unknown").is_some_and(|unknown| !unknown.is_boolean())) { return false; }
        if let Some(ack) = value.get(self.ack_key()) {
            if !selected || value["action"] != terminal || !self.no_foreign_evidence(value) { return false; }
            let mut command = json!({"cmd":command_kind, "action":terminal, "request_id":value["request_id"],
                "module_scope":value["module_scope"], "preflight_token":value["preflight_token"]});
            command[self.ack_key()] = ack.clone();
            if command_kind == "preset" { command["document_id"] = value["document_id"].clone(); }
            let valid = self.command(&command);
            if valid.is_err() { return false; }
        } else if selected && value["action"] == terminal && (self != Self::Torso || value["success"] == true) { return false; }
        true
    }
}
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
        && BODY_REVIEW_FAMILIES.iter().all(|family| value["modules"].get(family.op()).map_or(true, |params| {
            value["modules"].as_object().is_some_and(|modules| modules.len() == 1) && family.parameters(params)
        }))
        && value.get("xmp_import").map_or(true, |xmp| xmp_protocol::summary(xmp, &value["modules"]))
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
    let has_spill=ops.iter().any(|op|op==spill::SPILL_OP);
    let has_shadow=ops.iter().any(|op|op==shadow::SHADOW_OP);
    let collarbone=crate::preset_api::collarbone::selected(value);
    let has_body=BODY_REVIEW_FAMILIES.iter().any(|family| family.selected(value));
    let xmp=!value["xmp_report"].is_null()||!value["xmp_transfer"].is_null();
    (local||optics||crop||xmp||has_spill||has_shadow||has_body||collarbone)
        && BODY_REVIEW_FAMILIES.iter().all(|family| {
            if !family.selected(value) { return value[family.transfer_key()].is_null(); }
            ops.len() == 1 && !xmp && value.get(family.ack_key()).is_none() && family.no_foreign_evidence(value)
                && torso::hex(&value["preflight_token"],32)
                && family.transfer(&value[family.transfer_key()],&value["document_id"],&value["revision"],&value["applies"][family.op()],&value["source_proof"])
        })
        && (!has_shadow || (!has_spill && !ops.iter().any(|op|op=="lnx.id_background.v1")
            && shadow::hex(&value["preflight_token"],32)
            && shadow::transfer(&value["shadow_transfer"],&value["document_id"],&value["revision"],&value["applies"][shadow::SHADOW_OP],&value["source_proof"])))
        && (!has_spill || (spill::hex(&value["preflight_token"], 32)
            && !ops.iter().any(|op|op=="lnx.id_background.v1")
            && spill::transfer(&value["spill_transfer"], &value["document_id"], &value["revision"], &value["applies"][spill::SPILL_OP], &value["source_proof"])))
        && (!local||value["local_mask_transfer"].is_object())
        && (!optics||optical_review(&value["optical_transfer"],&value["document_id"],&value["revision"],&value["applies"]["lnx.optics_auto.v1"]))
        && (!crop||crop_review(&value["crop_transfer"],&value["document_id"],&value["revision"],&value["applies"]["lnx.crop.v1"]))
        && (!xmp||(xmp_protocol::transfer(&value["xmp_transfer"],&value["document_id"],&value["revision"],&value["xmp_report"])
            &&xmp_protocol::adapted_modules(&value["applies"],&value["xmp_report"])))
}
impl ReceiptKind for PresetKind {
    const NAME: &'static str = "preset";
    const ACTIONS: &'static [&'static str] = &["list", "preflight", "apply", "save", "import", "delete", "xmp_inspect", "collarbone_visual"];
    fn valid_request(action: &str, document: Option<&str>) -> bool {
        if ["apply", "preflight", "save", "collarbone_visual"].contains(&action) {
            document.is_some_and(|d| !d.is_empty() && d.len() <= 128 && d.chars().count() <= 64)
        } else { document.is_none() }
    }
    fn valid(value: &Value, document: Option<&str>) -> bool {
        let Some(success) = value["success"].as_bool() else { return false };
        let Some(unknown) = value["outcome_unknown"].as_bool() else { return false };
        if value["protocol"].as_u64() != Some(1) || (success && unknown) { return false; }
        if document.is_some() && value["document_id"].as_str() != document { return false; }
        if !crate::preset_api::collarbone::receipt(value) {return false;}
        if !BODY_REVIEW_FAMILIES.iter().all(|family| family.receipt(value, "preset", "apply")) { return false; }
        if !success { return true; }
        match value["action"].as_str() {
            Some("collarbone_visual") => crate::preset_api::collarbone::receipt(value),
            Some("xmp_inspect") => text(&value["path"]) && xmp_protocol::report(&value["xmp_report"]),
            Some("preflight") => text(&value["id"]) && scope(&value["module_scope"])
                && modules(&value["applies"], &value["module_scope"])
                && value["preflight_token"].as_str().is_some_and(|s| s.len() == 32 && s.bytes().all(|b| b.is_ascii_hexdigit()))
                && reviewed_types(value) && text(&value["revision"]),
            Some("list") => value["catalog"]["available"] == true && value["catalog"]["list"].as_array().is_some_and(|items| items.iter().all(preset))
                && value["catalog"]["errors"].is_array() && value["catalog"]["modules"].is_array(),
            Some("apply") => text(&value["id"]) && scope(&value["module_scope"]) && modules(&value["before"], &value["module_scope"])
                && modules(&value["after"], &value["module_scope"]) && value["doc_state"].is_object()
                && BODY_REVIEW_FAMILIES.iter().all(|family| !family.selected(value) || ["before", "after"].iter().all(|side| {
                    let dependency = &value[*side][family.op()];
                    dependency.as_object().is_some_and(|fields| fields.len() == 1)
                        && torso::hex(&dependency["target_recipe_key"], 64)
                }))
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
    // AUTHORED / UNRUN. Complete small PNG fixtures, not product-render evidence.
    fn spill_review() -> Value {
        let source=json!({"asset_sha256":"a".repeat(64),"original_sha256":"a".repeat(64),"creative_source":null});
        let params=json!({"enabled":true,"strength":61});
        let report=spill::tests::sample_transfer(&json!("loaded-photo"), &json!("3"), &params, &source);
        json!({"protocol":1,"action":"preflight","success":true,"outcome_unknown":false,"request_id":"spill",
            "id":"spill-preset","document_id":"loaded-photo","revision":"3","module_scope":[spill::SPILL_OP],
            "applies":{(spill::SPILL_OP):params},"preflight_token":"f".repeat(32),"source_proof":source,"spill_transfer":report})
    }
    #[test] fn spill_preflight_requires_one_exact_bound_image_pair() {
        let value=spill_review();assert!(PresetKind::valid(&value,Some("loaded-photo")));
        for key in ["spill_transfer","source_proof","revision"] {
            let mut changed=value.clone();changed.as_object_mut().unwrap().remove(key);
            assert!(!PresetKind::valid(&changed,Some("loaded-photo")),"{key}");
        }
        for (key,replacement) in [("document_id",json!("other-photo")),("revision",json!("4")),
            ("source_proof",Value::Null),("parameters",json!({"enabled":true,"strength":60}))] {
            let mut changed=value.clone();changed["spill_transfer"][key]=replacement;
            assert!(!PresetKind::valid(&changed,Some("loaded-photo")),"{key}");
        }
        let mut changed=value.clone();changed["revision"]=json!("03");changed["spill_transfer"]["revision"]=json!("03");
        assert!(!PresetKind::valid(&changed,Some("loaded-photo")));
        changed=value.clone();changed["spill_transfer"]["after"]["sha256"]=json!("e".repeat(64));
        assert!(!PresetKind::valid(&changed,Some("loaded-photo")));
        changed=value.clone();changed["module_scope"]=json!([spill::SPILL_OP,"lnx.id_background.v1"]);
        changed["applies"]["lnx.id_background.v1"]=json!({"recipe":{}});
        assert!(!PresetKind::valid(&changed,Some("loaded-photo")));
        changed=value;changed["success"]=json!(false);changed["spill_transfer"]=Value::Null;
        assert!(PresetKind::valid(&changed,Some("loaded-photo")));
    }
    #[test] fn corrupt_spill_png_receipt_is_unknown_and_keeps_document_binding() {
        let mut h=host();h.begin_bound([1;16],"spill","preflight",Some("loaded-photo")).unwrap();
        let mut value=spill_review();value["spill_transfer"]["before"]["base64"]=json!("iVBORw==");
        h.receive([1;16],&value);
        assert_eq!(h.status("spill")["result"]["success"],false);
        assert_eq!(h.status("spill")["result"]["outcome_unknown"],true);
        assert_eq!(h.status("spill")["result"]["document_id"],"loaded-photo");
    }
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
        let mut legacy_null=value.clone();legacy_null["xmp_report"]=Value::Null;legacy_null["xmp_transfer"]=Value::Null;
        assert!(PresetKind::valid(&legacy_null,Some("doc")));
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

    #[test] fn shadow_preset_requires_its_own_pair_and_refuses_combined_scopes() {
        let mut value=spill_review();let params=json!({"enabled":true,"strength":45,"blend":"softlight"});
        value["module_scope"]=json!([shadow::SHADOW_OP]);value["applies"]=json!({(shadow::SHADOW_OP):params});
        value.as_object_mut().unwrap().remove("spill_transfer");
        value["shadow_transfer"]=shadow::tests::sample_transfer(&value["document_id"],&value["revision"],&params,&value["source_proof"]);
        assert!(PresetKind::valid(&value,Some("loaded-photo")));
        for key in ["shadow_transfer","source_proof","revision"] {
            let mut bad=value.clone();bad.as_object_mut().unwrap().remove(key);assert!(!PresetKind::valid(&bad,Some("loaded-photo")));
        }
        for op in [spill::SPILL_OP,"lnx.id_background.v1"] {
            let mut bad=value.clone();bad["module_scope"].as_array_mut().unwrap().push(json!(op));bad["applies"][op]=json!({});
            assert!(!PresetKind::valid(&bad,Some("loaded-photo")));
        }
        let mut bad=value;bad["shadow_transfer"]["parameters"]["retention"]=json!({});assert!(!PresetKind::valid(&bad,Some("loaded-photo")));
    }

    // AUTHORED / UNRUN. Complete transport fixtures, not actual target rendering.
    fn torso_review() -> Value {
        let mut value = spill_review(); let params = json!({"version":1,"amount":-0.4});
        value["request_id"] = json!("torso"); value["id"] = json!("torso-preset");
        value["module_scope"] = json!([torso::TORSO_OP]); value["applies"] = json!({(torso::TORSO_OP):params});
        value.as_object_mut().unwrap().remove("spill_transfer");
        value["torso_transfer"] = torso::tests::sample_transfer(&value["document_id"], &value["revision"], &params, &value["source_proof"]);
        value
    }
    #[test] fn torso_preset_requires_owned_body_face_and_both_verified_images() {
        let value = torso_review(); assert!(PresetKind::valid(&value, Some("loaded-photo")));
        for path in ["/torso_transfer", "/source_proof", "/torso_transfer/body_ref", "/torso_transfer/associated_face",
            "/torso_transfer/body_review_sha256", "/torso_transfer/before_bank_sha256", "/torso_transfer/candidate_bank_sha256"] {
            let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null;
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{path}");
        }
        for op in [spill::SPILL_OP, shadow::SHADOW_OP, "lnx.crop.v1", "lnx.exposure.v1"] {
            let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op));
            bad["applies"][op] = json!({}); assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        }
        let mut bad = value.clone(); bad["torso_transfer"]["body_ref"]["asset_sha256"] = json!("e".repeat(64));
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        bad = value.clone(); bad["torso_transfer"]["parameters"]["amount"] = json!(0.0);
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        let mut h = host(); h.begin_bound([1;16],"torso","preflight",Some("loaded-photo")).unwrap();
        bad = value; bad["torso_transfer"]["after"]["sha256"] = json!("e".repeat(64)); h.receive([1;16], &bad);
        assert_eq!(h.status("torso")["result"]["outcome_unknown"],true);
    }
    #[test] fn torso_apply_retains_reviewed_ack_and_dependency_keys_not_display_pixels() {
        let review = torso_review(); let pair = &review["torso_transfer"];
        let ack = json!([{"document_id":review["document_id"],"revision":review["revision"],
            "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}]);
        let value = json!({"protocol":1,"action":"apply","request_id":"torso-apply","success":true,"outcome_unknown":false,
            "id":"torso-preset","document_id":"loaded-photo","module_scope":[torso::TORSO_OP],
            "preflight_token":review["preflight_token"],"torso_review_ack":ack,
            "before":{(torso::TORSO_OP):{"target_recipe_key":"a".repeat(64)}},
            "after":{(torso::TORSO_OP):{"target_recipe_key":"b".repeat(64)}},"doc_state":{"document_id":"loaded-photo"}});
        assert!(PresetKind::valid(&value, Some("loaded-photo")));
        for key in ["torso_review_ack", "preflight_token"] {
            let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key);
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
        }
        let mut bad = value.clone(); bad["torso_review_ack"][0]["document_id"] = json!("other-photo");
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        bad = value.clone(); bad["after"][torso::TORSO_OP] = json!({"version":1,"amount":-0.4});
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        bad = value.clone(); bad["torso_transfer"] = pair.clone(); assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        let mut pending = value; pending["success"] = json!(false); pending["outcome_unknown"] = json!(true);
        assert!(PresetKind::valid(&pending, Some("loaded-photo")));
    }

    // AUTHORED / UNRUN. Reuses only a synthetic common proof schema; this is not
    // evidence that torso target geometry is valid for an actual waist render.
    fn waist_review() -> Value {
        let mut value = torso_review();
        value["request_id"] = json!("waist"); value["id"] = json!("waist-preset");
        value["module_scope"] = json!([waist::WAIST_OP]);
        value["applies"] = json!({(waist::WAIST_OP):{"version":1,"amount":0.0}});
        let mut proof = value.as_object_mut().unwrap().remove("torso_transfer").unwrap();
        proof["parameters"] = value["applies"][waist::WAIST_OP].clone();
        value["waist_transfer"] = proof;
        value
    }
    fn waist_apply() -> Value {
        let review = waist_review(); let pair = &review["waist_transfer"];
        json!({"protocol":1,"action":"apply","request_id":"waist-apply","success":true,"outcome_unknown":false,
            "id":"waist-preset","document_id":"loaded-photo","module_scope":[waist::WAIST_OP],
            "preflight_token":review["preflight_token"],
            "waist_review_ack":[{"document_id":review["document_id"],"revision":review["revision"],
                "before_sha256":pair["before"]["sha256"],"after_sha256":pair["after"]["sha256"]}],
            "before":{(waist::WAIST_OP):{"target_recipe_key":"a".repeat(64)}},
            "after":{(waist::WAIST_OP):{"target_recipe_key":"b".repeat(64)}},"doc_state":{"document_id":"loaded-photo"}})
    }
    #[test] fn waist_zero_preflight_still_requires_all_owned_evidence_and_both_pngs() {
        let value = waist_review(); assert!(PresetKind::valid(&value, Some("loaded-photo")));
        for key in value["waist_transfer"].as_object().unwrap().keys() {
            let mut bad = value.clone(); bad["waist_transfer"].as_object_mut().unwrap().remove(key);
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
        }
        for path in ["/source_proof", "/waist_transfer/body_ref/asset_sha256",
            "/waist_transfer/associated_face/associated_face_ref/asset_sha256",
            "/waist_transfer/body_support_sha256", "/waist_transfer/body_review_sha256",
            "/waist_transfer/before/base64", "/waist_transfer/after/base64"] {
            let mut bad = value.clone(); *bad.pointer_mut(path).unwrap() = Value::Null;
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{path}");
        }
        for (key, replacement) in [("source_proof", json!({"asset_sha256":"e".repeat(64),"original_sha256":"e".repeat(64),"creative_source":null})),
            ("revision", json!("4")), ("parameters", json!({"version":1,"amount":0.1})),
            ("body_ref", json!([value["waist_transfer"]["body_ref"].clone()])), ("body_refs", json!([]))] {
            let mut bad = value.clone(); bad["waist_transfer"][key] = replacement;
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
        }
        let mut bad = value.clone(); bad["waist_transfer"]["after"]["sha256"] = json!("e".repeat(64));
        let mut h = host(); h.begin_bound([1;16], "waist", "preflight", Some("loaded-photo")).unwrap(); h.receive([1;16], &bad);
        assert_eq!(h.status("waist")["result"]["outcome_unknown"], true);
    }
    #[test] fn waist_scope_is_exclusive_and_never_borrows_another_review_family() {
        let value = waist_review();
        for op in [torso::TORSO_OP, waist::WAIST_OP, spill::SPILL_OP, shadow::SHADOW_OP, "lnx.crop.v1", "lnx.exposure.v1"] {
            let mut bad = value.clone(); bad["module_scope"].as_array_mut().unwrap().push(json!(op));
            bad["applies"][op] = json!({}); assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{op}");
        }
        for key in ["torso_transfer", "spill_transfer", "shadow_transfer", "people_transfer", "persistent_association", "xmp_transfer"] {
            let mut bad = value.clone(); bad[key] = json!({}); assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
        }
        for key in ["torso_review_ack", "waist_review_ack", "spill_review_ack", "shadow_review_ack", "xmp_review_ack"] {
            let mut bad = value.clone(); bad[key] = Value::Null; assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
        }
        let mut bad = value.clone(); bad["module_scope"] = json!([torso::TORSO_OP]);
        bad["applies"] = json!({(torso::TORSO_OP):{"version":1,"amount":0.0}});
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        bad = torso_review(); bad["waist_transfer"] = value["waist_transfer"].clone();
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
    }
    #[test] fn waist_terminal_claims_keep_exact_ack_shape_even_when_unknown_or_rejected() {
        let original = waist_apply();
        for (success, unknown) in [(true,false), (false,true), (false,false)] {
            let mut value = original.clone(); value["success"] = json!(success); value["outcome_unknown"] = json!(unknown);
            assert!(PresetKind::valid(&value, Some("loaded-photo")));
            for key in ["waist_review_ack", "preflight_token", "module_scope"] {
                let mut bad = value.clone(); bad.as_object_mut().unwrap().remove(key);
                assert!(!PresetKind::valid(&bad, Some("loaded-photo")), "{key}");
            }
            let mut bad = value.clone(); bad["torso_review_ack"] = value["waist_review_ack"].clone();
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
            bad = value.clone(); bad["waist_review_ack"][0]["document_id"] = json!("other");
            assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        }
        let mut bad = original.clone(); bad["after"][waist::WAIST_OP] = json!({"version":1,"amount":0});
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
        bad = original; bad["waist_transfer"] = waist_review()["waist_transfer"].clone();
        assert!(!PresetKind::valid(&bad, Some("loaded-photo")));
    }
    #[test] fn waist_portable_catalog_accepts_only_one_exact_scalar_module() {
        let value = json!({"schema":"lrt.preset.v1","id":"waist","name":"Waist","kind":"custom","builtin":false,
            "modules":{(waist::WAIST_OP):{"version":1,"amount":0.0}}});
        assert!(preset(&value));
        for key in ["body_ref", "associated_face", "support", "review"] {
            let mut bad = value.clone(); bad["modules"][waist::WAIST_OP][key] = Value::Null; assert!(!preset(&bad));
        }
        let mut bad = value.clone(); bad["modules"][torso::TORSO_OP] = json!({"version":1,"amount":0.0}); assert!(!preset(&bad));
        bad = value; bad["modules"][waist::WAIST_OP]["amount"] = json!(1.1); assert!(!preset(&bad));
    }
    #[test] fn native_waist_apply_binding_preserves_document_and_original_ack_on_unknown() {
        let value = waist_apply();
        let command = json!({"cmd":"preset","action":"apply","request_id":value["request_id"],"document_id":value["document_id"],
            "preflight_token":value["preflight_token"],"waist_review_ack":value["waist_review_ack"]});
        let mut h = host(); h.begin_command([1;16], &command).unwrap();
        let mut bad = value.clone(); bad["document_id"] = json!("other"); h.receive([1;16], &bad);
        let result = h.status("waist-apply")["result"].clone();
        assert_eq!(result["success"], false); assert_eq!(result["outcome_unknown"], true);
        assert_eq!(result["document_id"], "loaded-photo"); assert_eq!(result["waist_review_ack"], value["waist_review_ack"]);
        assert_eq!(result["preflight_token"], value["preflight_token"]);
    }

}

// AUTHORED / UNRUN: independent head-family protocol specifications.
#[cfg(test)]
#[path = "head_preset_host_tests.rs"]
mod head_tests;
