//! Reviewed fringe correction: epoch-bound image proof and one-shot receipts.
use std::collections::HashSet;
use serde_json::{json, Value};
use crate::color_capture_host::{id16, token};
use crate::receipt_host::{ReceiptHost, ReceiptKind};

pub(crate) struct FringeRepairKind;
pub(crate) type FringeRepairHost = ReceiptHost<FringeRepairKind>;

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

impl ReceiptKind for FringeRepairKind {
    const NAME: &'static str = "fringe_repair";
    const ACTIONS: &'static [&'static str] = &["apply"];

    fn valid_request(_: &str, bound: Option<&str>) -> bool { parts(bound).is_some() }

    fn valid(value: &Value, bound: Option<&str>) -> bool {
        let Some([document, session, preview]) = parts(bound) else { return false };
        let (Some(success), Some(unknown), Some(reload), Some(no_change)) = (
            value["success"].as_bool(), value["outcome_unknown"].as_bool(),
            value["requires_reload"].as_bool(), value["no_change"].as_bool(),
        ) else { return false };
        let history = ["undo_steps", "redo_steps"].iter()
            .all(|key| value["history"][*key].as_u64().is_some());
        value["event"] == "fringe_repair_result" && value["protocol"] == 1 && value["action"] == "apply"
            && value["document_id"] == document && value["session_id"] == session
            && value["preview_id"] == preview && !(success && unknown)
            && (!unknown || (reload && !no_change))
            && if success { !reload && history }
                else { value.get("history").is_some_and(Value::is_null) || history }
    }

    fn decorate_failure(value: &mut Value, bound: Option<&str>) {
        value["event"] = json!("fringe_repair_result");
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
const MAX_PREVIEW_METADATA_BYTES: usize = 512 * 1024;

#[derive(Default)]
pub(crate) struct FringeRepairPreviewHost {
    epoch: [u8; 16],
    bound: Option<(String, String, String)>,
    value: Option<Value>,
    delivered: bool,
    presentation_requested: bool,
    shown: bool,
    redeemed: bool,
    cancelling: bool,
    // Keep replay tombstones through invalidation; never recycle a shown ID.
    used_previews: HashSet<String>,
}

impl FringeRepairPreviewHost {
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
        if epoch == [0; 16] || epoch != self.epoch { return Err("fringe repair engine changed".into()); }
        if self.used_previews.contains(preview) { return Err("use a fresh fringe repair preview ID".into()); }
        if self.used_previews.len() >= MAX_PREVIEWS_PER_EPOCH {
            return Err("fringe repair preview budget exhausted; restart the engine".into());
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
        let valid = value["event"] == "fringe_repair_preview" && value["protocol"] == 1
            && value.to_string().len() <= 3 * MAX_PNG_URL_BYTES + MAX_PREVIEW_METADATA_BYTES
            && match state {
                Some("ready") => current == Some("running") && value["success"] == true && valid_image(value),
                Some("presented") => matches!(current, Some("ready" | "presented")) && value["success"] == true
                    && self.delivered && self.presentation_requested
                    && self.value.as_ref().is_some_and(|ready|
                        value["recipe_document_id"] == ready["recipe_document_id"]
                            && value["recipe_revision"] == ready["recipe_revision"]),
                Some("failed") => value["success"] == false,
                Some("cancelled") => self.cancelling && value["success"] == true,
                _ => false,
            };
        if !valid {
            self.delivered = false;
            self.presentation_requested = false;
            self.shown = false;
            self.value = Some(json!({"protocol": 1, "state": "failed", "success": false,
                "document_id": document, "session_id": session, "preview_id": preview,
                "error": "invalid fringe repair preview"}));
        } else if state == Some("presented") {
            self.shown = true;
            // The ACK may not replace the exact image/recipe shown to the user.
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
            return Err("fringe repair output has not been delivered".into());
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
            return Err("fringe repair output was not presented or was already submitted".into());
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
    image["domain"] == "production-output" && image["quality"] == "full-source-render-downsampled-srgb8"
        && image["note"].as_str().is_some_and(|text| text.len() <= 4096)
        && ["width", "height"].iter().all(|key| image[*key].as_u64().is_some_and(|n| (1..=800).contains(&n)))
        && ["before", "after", "coverage"].iter().all(|key| image[*key].as_str().is_some_and(|url|
            url.starts_with("data:image/png;base64,") && url.len() > 22 && url.len() <= MAX_PNG_URL_BYTES))
        && value["recipe_document_id"].as_str().is_some_and(|id| id16(id).is_ok())
        && value["recipe_revision"].as_str().is_some_and(|revision|
            !revision.is_empty() && revision.bytes().all(|byte| byte.is_ascii_digit())
                && revision.parse::<u64>().is_ok_and(|n| n.to_string() == revision))
        && valid_recipe(value)
}

fn bounded(value: &Value, minimum: f64, maximum: f64) -> bool {
    value.as_f64().is_some_and(|n| n.is_finite() && (minimum..=maximum).contains(&n))
}

fn valid_source(source: &Value) -> bool {
    source.as_object().is_some_and(|object| object.len() == 3)
        && source["sha256"].as_str().is_some_and(|digest| digest.len() == 64
            && digest.bytes().all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)))
        && ["width", "height"].iter().all(|key| source[*key].as_u64().is_some_and(|n| (1..=1_000_000).contains(&n)))
}

fn valid_axes(value: &Value) -> bool {
    let Some(axes) = value.as_array() else { return false };
    if axes.len() != 2 || !axes.iter().all(|axis| axis.as_array().is_some_and(|values|
        values.len() == 2 && values.iter().all(|v| bounded(v, -2.0, 2.0)))) { return false; }
    let a = axes[0][0].as_f64().unwrap_or(0.0);
    let b = axes[0][1].as_f64().unwrap_or(0.0);
    let c = axes[1][0].as_f64().unwrap_or(0.0);
    let d = axes[1][1].as_f64().unwrap_or(0.0);
    let lengths = (a.hypot(b), c.hypot(d));
    let determinant = (a * d - b * c).abs();
    lengths.0 >= 1e-9 && lengths.1 >= 1e-9 && determinant >= 1e-12
        && determinant / (lengths.0 * lengths.1) >= 1e-6
}

fn valid_recipe(value: &Value) -> bool {
    let recipe = &value["recipe"];
    if !valid_source(&value["source"]) || !recipe.as_object().is_some_and(|object| object.len() == 6)
        || recipe["version"] != 1 || recipe["algorithm"] != "lrt-fringe-repair-v1"
        || !recipe["enabled"].is_boolean() || !bounded(&recipe["strength"], 0.0, 100.0)
        || !recipe["coverage"].as_object().is_some_and(|object| object.len() == 2)
        || recipe["coverage"]["domain"] != "post-optics-pre-crop-normalized-v1"
        || !value["defaults"].as_object().is_some_and(|object| object.len() == 3)
        || value["defaults"]["strength"] != 50 || value["defaults"]["min_strength"] != 0
        || value["defaults"]["max_strength"] != 100 { return false; }
    let Some(strokes) = recipe["coverage"]["strokes"].as_array() else { return false };
    let Some(source) = recipe.get("source") else { return false };
    if strokes.len() > 128 || if strokes.is_empty() { !source.is_null() } else { source != &value["source"] } {
        return false;
    }
    let mut ids = HashSet::new();
    let mut point_count = 0usize;
    for stroke in strokes {
        let Some(id) = stroke["id"].as_str() else { return false };
        if !stroke.as_object().is_some_and(|object| object.len() == 6) || id.is_empty()
            || id.chars().count() > 96 || id.trim() != id || id.chars().any(char::is_control) || !ids.insert(id)
            || !matches!(stroke["mode"].as_str(), Some("add" | "subtract")) || !valid_axes(&stroke["axes"])
            || !bounded(&stroke["opacity"], 0.0, 1.0) || !bounded(&stroke["feather"], 0.0, 1.0) { return false; }
        let Some(points) = stroke["points"].as_array() else { return false };
        point_count += points.len();
        if points.is_empty() || points.len() > 1024 || point_count > 8192 || !points.iter().all(|point|
            point.as_array().is_some_and(|xy| xy.len() == 2 && xy.iter().all(|v| bounded(v, 0.0, 1.0)))) {
            return false;
        }
    }
    true
}

// Source-authored adversarial fixtures only; intentionally UNRUN.
#[cfg(test)]
#[path = "fringe_repair_host_tests.rs"]
mod tests;
