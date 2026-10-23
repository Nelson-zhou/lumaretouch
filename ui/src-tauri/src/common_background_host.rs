//! Common replacement owns its output proof; studio cleanup has a separate host.
use std::collections::HashSet;
use serde_json::{json, Value};
use crate::color_capture_host::{id16, token};
use crate::receipt_host::{ReceiptHost, ReceiptKind};

pub(crate) struct CommonBackgroundKind;
pub(crate) type CommonBackgroundHost = ReceiptHost<CommonBackgroundKind>;

pub(crate) fn binding(document: &str, session: &str, preview: &str) -> Result<String, String> {
    token(document)?;
    id16(session)?;
    id16(preview)?;
    Ok(format!("{document}|{session}|{preview}"))
}

fn parts(bound: Option<&str>) -> Option<[&str; 3]> {
    let values: Vec<_> = bound?.split('|').collect();
    let values: [&str; 3] = values.try_into().ok()?;
    binding(values[0], values[1], values[2]).ok()?;
    Some(values)
}

impl ReceiptKind for CommonBackgroundKind {
    const NAME: &'static str = "common_background";
    const ACTIONS: &'static [&'static str] = &["apply"];

    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }

    fn valid(value: &Value, bound: Option<&str>) -> bool {
        let Some([document, session, preview]) = parts(bound) else { return false };
        let (Some(success), Some(unknown), Some(reload), Some(_)) = (
            value["success"].as_bool(), value["outcome_unknown"].as_bool(),
            value["requires_reload"].as_bool(), value["no_change"].as_bool(),
        ) else { return false };
        let history = ["undo_steps", "redo_steps"].iter()
            .all(|key| value["history"][*key].as_u64().is_some());
        value["protocol"] == 1 && value["action"] == "apply"
            && value["document_id"] == document && value["session_id"] == session
            && value["preview_id"] == preview && !(success && unknown)
            && (!unknown || reload)
            && if success { !reload && history }
                else { value.get("history").is_some_and(|v| v.is_null()) || history }
    }

    fn decorate_failure(value: &mut Value, bound: Option<&str>) {
        value["event"] = json!("common_background_result");
        value["protocol"] = json!(1);
        value["requires_reload"] = json!(true);
        value["no_change"] = json!(false);
        value["history"] = Value::Null;
        if let Some(values) = parts(bound) {
            for (key, item) in ["document_id", "session_id", "preview_id"].iter().zip(values) {
                value[*key] = json!(item);
            }
        }
    }
}

const MAX_PREVIEWS_PER_EPOCH: usize = 4096;
const MAX_PNG_URL_BYTES: usize = 4 * 1024 * 1024;

#[derive(Default)]
pub(crate) struct CommonBackgroundPreviewHost {
    epoch: [u8; 16],
    bound: Option<(String, String, String)>,
    value: Option<Value>,
    delivered: bool,
    presentation_requested: bool,
    shown: bool,
    redeemed: bool,
    cancelling: bool,
    // Never reuse a proof identity during an epoch, even after invalidation.
    // Fail closed at a fixed budget rather than evicting replay tombstones.
    used_previews: HashSet<String>,
}

impl CommonBackgroundPreviewHost {
    pub fn invalidate(&mut self) {
        self.bound = None;
        self.value = None;
        self.delivered = false;
        self.presentation_requested = false;
        self.shown = false;
        self.redeemed = false;
        self.cancelling = false;
    }

    pub fn reset(&mut self, epoch: [u8; 16]) {
        self.invalidate();
        self.used_previews.clear();
        self.epoch = epoch;
    }

    pub fn ended(&mut self, epoch: [u8; 16]) {
        if self.epoch == epoch { self.reset([0; 16]); }
    }

    pub fn begin(&mut self, epoch: [u8; 16], document: &str, session: &str, preview: &str) -> Result<(), String> {
        binding(document, session, preview)?;
        if epoch == [0; 16] || epoch != self.epoch {
            return Err("common background engine changed".into());
        }
        if self.used_previews.contains(preview) {
            return Err("use a fresh common background preview ID".into());
        }
        if self.used_previews.len() >= MAX_PREVIEWS_PER_EPOCH {
            return Err("common background preview budget exhausted; restart the engine".into());
        }
        self.invalidate();
        self.used_previews.insert(preview.into());
        self.bound = Some((document.into(), session.into(), preview.into()));
        self.value = Some(json!({"protocol": 1, "state": "running", "success": true,
            "document_id": document, "session_id": session, "preview_id": preview}));
        Ok(())
    }

    pub fn matches(&self, epoch: [u8; 16], document: &str, session: &str, preview: &str) -> bool {
        epoch != [0; 16] && epoch == self.epoch
            && self.bound.as_ref().is_some_and(|bound| bound.0 == document && bound.1 == session && bound.2 == preview)
    }

    pub fn receive(&mut self, epoch: [u8; 16], value: &Value) {
        let Some((document, session, preview)) = self.bound.as_ref() else { return };
        if epoch == [0; 16] || epoch != self.epoch || value["document_id"] != document.as_str()
            || value["session_id"] != session.as_str() || value["preview_id"] != preview.as_str()
            || self.redeemed { return; }
        let state = value["state"].as_str();
        if self.cancelling && !matches!(state, Some("cancelled" | "failed")) { return; }
        let current = self.value.as_ref().and_then(|v| v["state"].as_str());
        let valid = value["protocol"] == 1 && value.to_string().len() <= 2 * MAX_PNG_URL_BYTES + 16384
            && match state {
                Some("ready") => current == Some("running") && value["success"] == true && valid_image(value),
                Some("presented") => matches!(current, Some("ready" | "presented")) && value["success"] == true
                    && self.delivered && self.presentation_requested
                    && self.value.as_ref().is_some_and(|ready|
                        value["recipe_document_id"] == ready["recipe_document_id"]
                            && value["recipe_revision"] == ready["recipe_revision"]),
                Some("failed") => value["success"] == false,
                Some("cancelled") => value["success"] == true,
                _ => false,
            };
        if !valid {
            self.delivered = false;
            self.presentation_requested = false;
            self.shown = false;
            self.value = Some(json!({"protocol": 1, "state": "failed", "success": false,
                "document_id": document, "session_id": session, "preview_id": preview,
                "error": "invalid common background preview"}));
        } else if state == Some("presented") {
            self.shown = true;
            // Keep the exact delivered production images and recipe identities.
            if let Some(ready) = self.value.as_mut() { ready["state"] = json!("presented"); }
        } else {
            self.delivered = false;
            self.presentation_requested = false;
            self.shown = false;
            self.value = Some(value.clone());
        }
    }

    pub fn status(&mut self, epoch: [u8; 16], preview: &str) -> Value {
        if epoch == [0; 16] || epoch != self.epoch || self.redeemed
            || !self.bound.as_ref().is_some_and(|bound| bound.2 == preview) {
            return json!({"state": "stale", "preview_id": preview});
        }
        if self.value.as_ref().is_some_and(|value| value["state"] == "ready") { self.delivered = true; }
        self.value.clone().unwrap_or_else(|| json!({"state": "stale", "preview_id": preview}))
    }

    pub fn presentation_requested(&mut self) -> Result<(), String> {
        if !self.delivered || self.redeemed || self.cancelling
            || !self.value.as_ref().is_some_and(|value| value["state"] == "ready" || value["state"] == "presented") {
            return Err("common background output has not been delivered".into());
        }
        self.presentation_requested = true;
        Ok(())
    }

    pub fn cancel_requested(&mut self) {
        self.cancelling = true;
        self.delivered = false;
        self.presentation_requested = false;
        self.shown = false;
        if let Some(value) = self.value.as_mut() { value["state"] = json!("cancelling"); }
    }

    pub fn can_redeem(&self) -> Result<(), String> {
        if !self.shown || self.redeemed || self.cancelling {
            return Err("common background output was not presented or was already submitted".into());
        }
        Ok(())
    }

    pub fn redeem(&mut self) -> Result<(), String> {
        self.can_redeem()?;
        self.redeemed = true;
        Ok(())
    }
}

fn valid_image(value: &Value) -> bool {
    let image = &value["image"];
    image["domain"] == "production-output" && image["quality"] == "proxy-render-srgb8"
        && image["note"].as_str().is_some_and(|text| text.len() <= 4096)
        && ["width", "height"].iter().all(|key| image[*key].as_u64().is_some_and(|n| (1..=800).contains(&n)))
        && ["before", "after"].iter().all(|key| image[*key].as_str().is_some_and(|url|
            url.starts_with("data:image/png;base64,") && url.len() > 22 && url.len() <= MAX_PNG_URL_BYTES))
        && value["recipe_document_id"].as_str().is_some_and(|id| id16(id).is_ok())
        && value["recipe_revision"].as_str().is_some_and(|revision|
            !revision.is_empty() && revision.bytes().all(|byte| byte.is_ascii_digit())
                && revision.parse::<u64>().is_ok_and(|n| n.to_string() == revision))
}

// Source-authored fixtures only. Not executed as part of this implementation.
#[cfg(test)]
mod tests {
    use super::*;
    const EPOCH: [u8; 16] = [41; 16];
    const DOCUMENT: &str = "42";
    const SESSION: &str = "11111111111111111111111111111111";
    const PREVIEW: &str = "22222222222222222222222222222222";
    const RECIPE: &str = "33333333333333333333333333333333";
    const OTHER: &str = "44444444444444444444444444444444";
    const PNG: &str = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl1sAAAAASUVORK5CYII=";

    fn event(state: &str) -> Value {
        let mut value = json!({"event": "common_background_preview", "protocol": 1, "state": state,
            "success": state != "failed", "document_id": DOCUMENT, "session_id": SESSION, "preview_id": PREVIEW});
        if state == "presented" {
            value["recipe_document_id"] = json!(RECIPE);
            value["recipe_revision"] = json!("0");
        }
        value
    }

    fn ready() -> Value {
        let mut value = event("ready");
        value["recipe_document_id"] = json!(RECIPE);
        value["recipe_revision"] = json!("0");
        value["image"] = json!({"before": PNG, "after": PNG, "width": 1, "height": 1,
            "domain": "production-output", "quality": "proxy-render-srgb8", "note": "Proxy review"});
        value
    }

    fn host() -> CommonBackgroundPreviewHost {
        let mut host = CommonBackgroundPreviewHost::default();
        host.reset(EPOCH);
        host.begin(EPOCH, DOCUMENT, SESSION, PREVIEW).unwrap();
        host
    }

    fn show(host: &mut CommonBackgroundPreviewHost) {
        host.receive(EPOCH, &ready());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "ready");
        host.presentation_requested().unwrap();
        host.receive(EPOCH, &event("presented"));
    }

    #[test]
    fn delivery_and_matching_presentation_are_required_before_one_redemption() {
        let mut host = host();
        host.receive(EPOCH, &ready());
        assert!(host.presentation_requested().is_err());
        assert!(host.redeem().is_err());
        let delivered = host.status(EPOCH, PREVIEW);
        assert!(host.redeem().is_err());
        host.presentation_requested().unwrap();
        assert!(host.redeem().is_err());
        host.receive(EPOCH, &event("presented"));
        let presented = host.status(EPOCH, PREVIEW);
        assert_eq!(presented["state"], "presented");
        assert_eq!(presented["image"], delivered["image"]);
        assert_eq!(presented["recipe_document_id"], RECIPE);
        assert_eq!(presented["recipe_revision"], "0");
        host.redeem().unwrap();
        assert!(host.redeem().is_err());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "stale");
    }

    #[test]
    fn wrong_epoch_or_any_identity_cannot_deliver_or_acknowledge() {
        let mut host = host();
        host.receive([42; 16], &ready());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "running");
        for (key, wrong) in [("document_id", "43"), ("session_id", OTHER), ("preview_id", OTHER)] {
            let mut value = ready(); value[key] = json!(wrong);
            host.receive(EPOCH, &value);
            assert_eq!(host.status(EPOCH, PREVIEW)["state"], "running");
        }
        host.receive(EPOCH, &ready()); host.status(EPOCH, PREVIEW);
        host.presentation_requested().unwrap();
        let mut wrong = event("presented"); wrong["session_id"] = json!(OTHER);
        host.receive(EPOCH, &wrong);
        assert!(host.redeem().is_err());
    }

    #[test]
    fn presentation_ack_must_match_the_delivered_recipe_identity() {
        for (key, bad) in [("recipe_document_id", json!(OTHER)), ("recipe_revision", json!("1")),
            ("recipe_document_id", Value::Null), ("recipe_revision", Value::Null)] {
            let mut host = host();
            host.receive(EPOCH, &ready()); host.status(EPOCH, PREVIEW);
            host.presentation_requested().unwrap();
            let mut ack = event("presented"); ack[key] = bad;
            host.receive(EPOCH, &ack);
            assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
            assert!(host.redeem().is_err());
        }
    }

    #[test]
    fn cancel_or_document_invalidation_revokes_even_a_shown_proof() {
        let mut host = host(); show(&mut host);
        host.cancel_requested();
        host.receive(EPOCH, &event("presented"));
        assert!(host.redeem().is_err());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "cancelling");
        host.receive(EPOCH, &event("cancelled"));
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "cancelled");
        host.invalidate();
        host.receive(EPOCH, &ready());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "stale");
        assert!(host.begin(EPOCH, DOCUMENT, SESSION, PREVIEW).is_err());
        host.begin(EPOCH, DOCUMENT, SESSION, OTHER).unwrap();
        host.ended(EPOCH);
        assert!(host.begin(EPOCH, DOCUMENT, SESSION, PREVIEW).is_err());
    }

    #[test]
    fn invalid_output_envelopes_never_become_deliverable() {
        for (key, bad) in [("domain", json!("source-normalized")), ("quality", json!("source-rgb8")),
            ("width", json!(801)), ("height", json!(0)), ("note", Value::Null),
            ("before", json!("https://example.invalid/image.png")), ("after", json!("data:image/png;base64,"))] {
            let mut host = host(); let mut value = ready(); value["image"][key] = bad;
            host.receive(EPOCH, &value);
            assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
            assert!(host.presentation_requested().is_err());
        }
        for revision in ["", "-1", "1.0", "01", "18446744073709551616"] {
            let mut host = host(); let mut value = ready(); value["recipe_revision"] = json!(revision);
            host.receive(EPOCH, &value);
            assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
        }
        let mut host = host(); let mut value = ready();
        value["result"] = value["image"].clone(); value.as_object_mut().unwrap().remove("image");
        host.receive(EPOCH, &value);
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
    }

    #[test]
    fn unsolicited_ack_and_late_replacement_cannot_reuse_presentation() {
        let mut host = host(); host.receive(EPOCH, &event("presented"));
        assert!(host.redeem().is_err());
        let mut host = self::host(); show(&mut host);
        let mut replacement = ready(); replacement["recipe_revision"] = json!("1");
        host.receive(EPOCH, &replacement);
        assert!(host.redeem().is_err());
        assert_eq!(host.status(EPOCH, PREVIEW)["state"], "failed");
    }

    fn receipt(request: &str) -> Value {
        json!({"event": "common_background_result", "protocol": 1, "action": "apply",
            "request_id": request, "document_id": DOCUMENT, "session_id": SESSION, "preview_id": PREVIEW,
            "success": true, "outcome_unknown": false, "requires_reload": false,
            "no_change": false, "history": {"undo_steps": 1, "redo_steps": 0}})
    }

    #[test]
    fn receipt_requires_capability_and_retains_the_first_exact_result() {
        let mut host = CommonBackgroundHost::default(); host.reset(EPOCH);
        let bound = binding(DOCUMENT, SESSION, PREVIEW).unwrap();
        assert!(host.begin_bound(EPOCH, "one", "apply", Some(&bound)).is_err());
        host.ready(EPOCH, true); host.begin_bound(EPOCH, "one", "apply", Some(&bound)).unwrap();
        host.receive(EPOCH, &receipt("unrelated"));
        host.receive([42; 16], &receipt("one"));
        assert_eq!(host.status("one")["phase"], "pending");
        let original = receipt("one"); host.receive(EPOCH, &original);
        let mut late = original.clone(); late["history"]["undo_steps"] = json!(19);
        host.receive(EPOCH, &late); host.failed("one", "late send failure"); host.ended(EPOCH);
        assert_eq!(host.status("one")["result"], original);
    }

    #[test]
    fn malformed_receipt_and_engine_end_keep_bound_unknown_outcomes() {
        let bound = binding(DOCUMENT, SESSION, PREVIEW).unwrap();
        let mut host = CommonBackgroundHost::default(); host.reset(EPOCH); host.ready(EPOCH, true);
        host.begin_bound(EPOCH, "bad", "apply", Some(&bound)).unwrap();
        host.begin_bound(EPOCH, "pending", "apply", Some(&bound)).unwrap();
        let mut malformed = receipt("bad"); malformed["preview_id"] = json!(OTHER);
        host.receive(EPOCH, &malformed); host.ended(EPOCH);
        for request in ["bad", "pending"] {
            let result = host.status(request)["result"].clone();
            assert_eq!(result["protocol"], 1); assert_eq!(result["action"], "apply");
            assert_eq!(result["request_id"], request); assert_eq!(result["document_id"], DOCUMENT);
            assert_eq!(result["session_id"], SESSION); assert_eq!(result["preview_id"], PREVIEW);
            assert_eq!(result["success"], false); assert_eq!(result["outcome_unknown"], true);
            assert_eq!(result["requires_reload"], true); assert_eq!(result["no_change"], false);
            assert!(result["history"].is_null());
        }
    }
}
