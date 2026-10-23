//! Independent source/review proof and post-history receipt ownership.
use serde_json::{json, Value};
use crate::receipt_host::{ReceiptHost, ReceiptKind};
use crate::color_capture_host::{id16, token};

pub(crate) struct RecoveryKind;
pub(crate) type RecoveryHost = ReceiptHost<RecoveryKind>;

/// Exact existing operator family contract shared by request and review paths.
/// Face ownership is still checked by the engine; this grants no source bypass.
pub(crate) fn supported_target(value: &Value) -> bool {
    matches!(value.as_str(), Some(
        "skin_smoothing" | "fabric_fine" | "background_replace" | "id_background"
        | "facial_wrinkles" | "lip_makeup" | "eye_light" | "blush_makeup"
        | "lipstick" | "eyeliner" | "eyelash" | "brow_makeup" | "iris_makeup"
    ))
}


pub(crate) fn binding(document: &str, capture: &str, ticket: &str, preview: &str) -> Result<String, String> {
    token(document)?; id16(capture)?; token(ticket)?; id16(preview)?;
    Ok(format!("{document}|{capture}|{ticket}|{preview}"))
}
fn parts(bound: Option<&str>) -> Option<[&str; 4]> {
    let values: Vec<_> = bound?.split('|').collect();
    let values: [&str; 4] = values.try_into().ok()?;
    binding(values[0], values[1], values[2], values[3]).ok()?;
    Some(values)
}
impl ReceiptKind for RecoveryKind {
    const NAME: &'static str = "effect_recovery";
    const ACTIONS: &'static [&'static str] = &["apply"];
    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }
    fn valid(v: &Value, bound: Option<&str>) -> bool {
        let Some([document, capture, ticket, preview]) = parts(bound) else { return false };
        let (Some(success), Some(unknown), Some(reload)) =
            (v["success"].as_bool(), v["outcome_unknown"].as_bool(), v["requires_reload"].as_bool()) else { return false };
        if v["protocol"] != 1 || v["action"] != "apply" || (success && unknown)
            || v["document_id"] != document || v["capture_id"] != capture
            || v["ticket"] != ticket || v["preview_id"] != preview { return false; }
        !success || (!reload && v["no_change"].is_boolean()
            && ["undo_steps", "redo_steps"].iter().all(|k| v["history"][*k].as_u64().is_some()))
    }
    fn decorate_failure(v: &mut Value, bound: Option<&str>) {
        v["protocol"] = json!(1); v["requires_reload"] = json!(true);
        if let Some(values) = parts(bound) {
            for (key, value) in ["document_id", "capture_id", "ticket", "preview_id"].iter().zip(values) {
                v[*key] = json!(value);
            }
        }
    }
}

#[derive(Default)]
pub(crate) struct RecoveryPreviewHost {
    epoch: [u8; 16],
    pub bound: Option<(String, String, String, String)>, // preview, capture, ticket, document
    value: Option<Value>,
    target: Option<String>,
    delivered: bool,
    presentation_requested: bool,
    shown: bool,
    redeemed: bool,
}
impl RecoveryPreviewHost {
    pub fn invalidate(&mut self) {
        self.bound = None; self.value = None; self.target = None; self.delivered = false; self.presentation_requested = false;
        self.shown = false; self.redeemed = false;
    }
    pub fn reset(&mut self, epoch: [u8; 16]) { self.invalidate(); self.epoch = epoch; }
    pub fn ended(&mut self, epoch: [u8; 16]) { if self.epoch == epoch { self.reset([0; 16]); } }
    pub fn begin(&mut self, epoch: [u8; 16], preview: &str, capture: &str, ticket: &str, document: &str, target: &Value) -> Result<(), String> {
        binding(document, capture, ticket, preview)?;
        if !supported_target(target) { return Err("unsupported recovery target".into()); }
        if self.epoch != epoch || epoch == [0; 16] { return Err("recovery preview engine changed".into()); }
        if self.bound.as_ref().is_some_and(|b| b.0 == preview) { return Err("use a fresh recovery preview ID".into()); }
        self.invalidate();
        self.bound = Some((preview.into(), capture.into(), ticket.into(), document.into()));
        self.target = target.as_str().map(str::to_owned);
        self.value = Some(json!({"protocol":1,"state":"running","preview_id":preview,
            "capture_id":capture,"ticket":ticket,"document_id":document,"success":true}));
        Ok(())
    }
    pub fn matches(&self, epoch: [u8; 16], preview: &str, capture: &str, ticket: &str, document: &str) -> bool {
        epoch != [0;16] && epoch == self.epoch && self.bound.as_ref().is_some_and(|b|
            b.0 == preview && b.1 == capture && b.2 == ticket && b.3 == document)
    }
    pub fn receive(&mut self, epoch: [u8; 16], v: &Value) {
        let Some((preview, capture, ticket, document)) = self.bound.as_ref() else { return };
        if epoch != self.epoch || v["preview_id"] != preview.as_str() || v["document_id"] != document.as_str()
            || v["capture_id"] != capture.as_str() || v["ticket"] != ticket.as_str() || self.redeemed { return; }
        let valid_images = || {
            let r = &v["result"];
            r["domain"] == "production-output" && r["quality"] == "proxy-render-srgb8"
                && ["width", "height"].iter().all(|k| r[*k].as_u64().is_some_and(|n| (1..=800).contains(&n)))
                && ["before", "after"].iter().all(|k| r[*k].as_str().is_some_and(|s|
                    s.len() <= 4*1024*1024 && s.starts_with("data:image/png;base64,")))
                && supported_target(&v["target"]) && v["target"].as_str() == self.target.as_deref()
        };
        let valid = v["protocol"] == 1 && v["success"].is_boolean() && v.to_string().len() <= 6*1024*1024+16384
            && match v["state"].as_str() {
                Some("ready") => v["success"] == true && valid_images(),
                Some("presented") => v["success"] == true && self.delivered && self.presentation_requested,
                Some("failed") => v["success"] == false,
                Some("cancelled") => v["success"] == true,
                _ => false,
            };
        if !valid {
            self.delivered = false; self.shown = false; self.presentation_requested = false;
            self.value = Some(json!({"protocol":1,"state":"failed","success":false,
                "preview_id":preview,"capture_id":capture,"ticket":ticket,"document_id":document,
                "error":"Invalid or oversized recovery preview"}));
        } else if v["state"] == "presented" {
            self.shown = true;
            if let Some(value) = self.value.as_mut() { value["state"] = json!("presented"); }
        } else {
            self.delivered = false; self.shown = false; self.presentation_requested = false;
            self.value = Some(v.clone());
        }
    }
    pub fn status(&mut self, epoch: [u8; 16], preview: &str) -> Value {
        if epoch != self.epoch || !self.bound.as_ref().is_some_and(|b| b.0 == preview) || self.redeemed {
            return json!({"state":"stale"});
        }
        if self.value.as_ref().is_some_and(|v| v["state"] == "ready") { self.delivered = true; }
        self.value.clone().unwrap_or_else(|| json!({"state":"stale"}))
    }
    pub fn allow_presented(&mut self) -> Result<(), String> {
        if !self.delivered || self.redeemed || !self.value.as_ref().is_some_and(|v| v["state"] == "ready" || v["state"] == "presented") {
            return Err("rendered recovery comparison has not been delivered".into());
        }
        self.presentation_requested = true;
        Ok(())
    }
    pub fn redeem(&mut self) -> Result<(), String> {
        if !self.shown || self.redeemed { return Err("rendered recovery comparison was not acknowledged or was already consumed".into()); }
        self.redeemed = true;
        Ok(())
    }
}

// Source fixtures only; runtime/native acceptance remains UNRUN.
#[cfg(test)]
mod tests {
    use super::*;
    const FACES: [&str; 9] = ["facial_wrinkles", "lip_makeup", "eye_light", "blush_makeup",
        "lipstick", "eyeliner", "eyelash", "brow_makeup", "iris_makeup"];
    const PREVIEW: &str = "11111111111111111111111111111111";
    const CAPTURE: &str = "22222222222222222222222222222222";

    fn ready(target: &str) -> Value {
        json!({"protocol":1,"state":"ready","success":true,"preview_id":PREVIEW,
            "capture_id":CAPTURE,"ticket":"3","document_id":"4","target":target,
            "result":{"domain":"production-output","quality":"proxy-render-srgb8",
                "width":8,"height":8,"before":"data:image/png;base64,fixture",
                "after":"data:image/png;base64,fixture"}})
    }

    #[test]
    fn exact_face_targets_keep_delivery_presentation_and_single_use_fences() {
        for target in FACES.into_iter().chain(["id_background", "background_replace"]) {
            let epoch = [1; 16];
            let mut host = RecoveryPreviewHost::default();
            host.reset(epoch);
            host.begin(epoch, PREVIEW, CAPTURE, "3", "4", &json!(target)).unwrap();
            host.receive(epoch, &ready(target));
            assert!(host.redeem().is_err());
            assert!(host.allow_presented().is_err());
            assert_eq!(host.status(epoch, PREVIEW)["state"], "ready");
            assert!(host.redeem().is_err());
            host.allow_presented().unwrap();
            let mut presented = ready(target);
            presented["state"] = json!("presented");
            host.receive(epoch, &presented);
            host.redeem().unwrap();
            assert!(host.redeem().is_err());
        }
    }

    #[test]
    fn unknown_targets_and_wrong_source_review_cannot_be_redeemed() {
        let epoch = [1; 16];
        for target in ["sky", "skin", "hair", "all", "fabric_coarse", "eye_light_extra"] {
            assert!(!supported_target(&json!(target)));
            let mut host = RecoveryPreviewHost::default();
            host.reset(epoch);
            host.begin(epoch, PREVIEW, CAPTURE, "3", "4", &json!("eye_light")).unwrap();
            host.receive(epoch, &ready(target));
            assert_eq!(host.status(epoch, PREVIEW)["state"], "failed");
            assert!(host.allow_presented().is_err());
            assert!(host.redeem().is_err());
        }
        let mut host = RecoveryPreviewHost::default();
        host.reset(epoch);
        host.begin(epoch, PREVIEW, CAPTURE, "3", "4", &json!("eye_light")).unwrap();
        let mut wrong = ready("eye_light");
        wrong["document_id"] = json!("5");
        host.receive(epoch, &wrong);
        assert_eq!(host.status(epoch, PREVIEW)["state"], "running");
        assert!(host.allow_presented().is_err());
        host.receive([2; 16], &ready("eye_light"));
        assert!(host.redeem().is_err());
    }

    #[test]
    fn legacy_preview_cannot_authorize_dedicated_id_recovery() {
        let epoch = [1; 16];
        let mut host = RecoveryPreviewHost::default();
        host.reset(epoch);
        host.begin(epoch, PREVIEW, CAPTURE, "3", "4", &json!("id_background")).unwrap();
        host.receive(epoch, &ready("background_replace"));
        assert_eq!(host.status(epoch, PREVIEW)["state"], "failed");
        assert!(host.allow_presented().is_err());
        assert!(host.redeem().is_err());
        host.reset(epoch);
        assert!(host.begin(epoch, PREVIEW, CAPTURE, "3", "4", &json!("id_background_other")).is_err());
    }
}
