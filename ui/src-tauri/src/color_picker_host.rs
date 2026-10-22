//! Targeted color completion is an identity-bound post-history receipt, not a sample.
use serde_json::{json, Value};
use crate::{color_capture_host::{id16, token}, receipt_host::{ReceiptHost, ReceiptKind}};

pub(crate) const ACTIONS: &[&str] = &["levels_black", "levels_white", "curve", "hsl"];
const IDENTITY_KEYS: &[&str] = &[
    "document_id", "capture_id", "ticket", "generation", "recipe_document_id",
    "recipe_revision", "action", "channel",
];

pub(crate) fn selection(action: &str, channel: &str) -> Result<(), String> {
    if !ACTIONS.contains(&action)
        || !["master", "red", "green", "blue", "luminance"].contains(&channel)
        || (action != "curve" && channel != "master") {
        return Err("invalid targeted color action/channel".into());
    }
    Ok(())
}
pub(crate) fn stage(action: &str, channel: &str) -> String {
    if action.starts_with("levels_") { "levels-input".into() }
    else if action == "hsl" { "hsl-input".into() }
    else { format!("curve-{channel}-input") }
}
fn canonical_revision(value: &Value) -> bool {
    value.as_str().is_some_and(|s| s.parse::<u64>().is_ok_and(|n| n.to_string() == s))
}
fn valid_binding(value: &Value) -> bool {
    let Some(action) = value["action"].as_str() else { return false };
    let Some(channel) = value["channel"].as_str() else { return false };
    let Some(delta) = value["delta"].as_f64() else { return false };
    let limit = if action == "hsl" { 60. } else if action == "curve" { 1. } else { 0. };
    selection(action, channel).is_ok() && delta.is_finite() && delta.abs() <= limit
        && ["document_id", "ticket", "generation"].iter()
            .all(|k| value[*k].as_str().is_some_and(|s| token(s).is_ok()))
        && ["capture_id", "recipe_document_id"].iter()
            .all(|k| value[*k].as_str().is_some_and(|s| id16(s).is_ok()))
        && canonical_revision(&value["recipe_revision"])
        && serde_json::from_value::<crate::color_picker_capture_api::Region>(value["region"].clone())
            .is_ok_and(|region| region.validate().is_ok())
}
/// Only producer-proved identity and native-validated scalar/region input enter
/// the mailbox context. A later capture cancellation cannot erase this binding.
pub(crate) fn binding(command: &Value) -> Result<String, String> {
    let mut value = json!({"region": command["region"], "delta": command["delta"]});
    for key in IDENTITY_KEYS { value[*key] = command[*key].clone(); }
    if !valid_binding(&value) { return Err("invalid targeted color receipt binding".into()); }
    Ok(value.to_string())
}
fn parts(bound: Option<&str>) -> Option<Value> {
    let text = bound?;
    if text.len() > 2048 { return None; }
    let value: Value = serde_json::from_str(text).ok()?;
    valid_binding(&value).then_some(value)
}
fn common(value: &Value, bound: &Value) -> bool {
    value["protocol"] == 1 && IDENTITY_KEYS.iter().all(|k| value[*k] == bound[*k])
        && value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
        && !(value["success"] == true && value["outcome_unknown"] == true)
        && value.to_string().len() <= 3 * 1024 * 1024
}
fn vector(value: &Value, size: usize, min: f64, max: f64) -> bool {
    value.as_array().is_some_and(|a| a.len() == size && a.iter()
        .all(|v| v.as_f64().is_some_and(|n| n.is_finite() && (min..=max).contains(&n))))
}
fn sample(value: &Value, bound: &Value) -> bool {
    let action = bound["action"].as_str().unwrap_or("");
    let channel = bound["channel"].as_str().unwrap_or("");
    let region = &bound["region"];
    let count = region["width"].as_u64().zip(region["height"].as_u64())
        .and_then(|(w, h)| w.checked_mul(h));
    let hsl = &value["hsl"];
    if value["version"] != 1 || value["policy"] != "stage-targeted-srgb-v1"
        || value["action"] != action || value["channel"] != channel
        || value["source_stage"] != stage(action, channel) || value["region"] != *region
        || value["samples"].as_u64() != count || !count.is_some_and(|n| (1..=121).contains(&n))
        || !vector(&value["mean_srgb"], 3, 0., 1.) || !vector(hsl, 3, 0., 360.)
        || !hsl[0].as_f64().is_some_and(|n| n < 360.)
        || ![1, 2].iter().all(|i| hsl[*i].as_f64().is_some_and(|n| n <= 1.)) {
        return false;
    }
    if action == "curve" {
        vector(&value["point"], 2, 0., 1.)
            && value["point_index"].as_u64().is_some_and(|n| n < crate::point_curve::MAX_POINTS as u64)
            && value["sample_x"].as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n))
            && value["achieved_delta"].as_f64().is_some_and(|n| n.is_finite() && n.abs() <= 1.)
    } else if action == "hsl" {
        vector(&value["weights"], 8, 0., 1.)
            && value["achieved_delta"].as_f64().is_some_and(|n| n.is_finite() && n.abs() <= 120.)
    } else { true }
}
fn exact_keys(value: &Value, names: &[&str]) -> bool {
    value.as_object().is_some_and(|o| o.len() == names.len() && names.iter().all(|k| o.contains_key(*k)))
}
fn recipe(value: &Value, action: &str) -> bool {
    if action == "curve" { return crate::curve_api::preview(value).is_ok(); }
    if action == "hsl" {
        return value.as_array().is_some_and(|a| a.len() == 24 && a.iter().enumerate()
            .all(|(i, v)| v.as_f64().is_some_and(|n| n.is_finite() && n.abs() <= if i % 3 == 0 { 60. } else { 100. })));
    }
    let fields = ["input_black", "input_white", "gamma", "output_black", "output_white"];
    exact_keys(value, &["version", "space", "enabled", "master", "red", "green", "blue"])
        && value["version"] == 1 && value["space"] == "srgb-display" && value["enabled"] == true
        && ["master", "red", "green", "blue"].iter().all(|channel| {
            let row = &value[*channel];
            let values = fields.map(|key| row[key].as_f64());
            exact_keys(row, &fields) && values.iter().all(Option::is_some)
                && crate::levels_core::Channel::new(values.map(Option::unwrap)).is_ok()
        })
}
fn unchanged_unrelated(before: &Value, after: &Value, action: &str, channel: &str) -> bool {
    if action == "hsl" {
        return (0..24).filter(|i| i % 3 != 0).all(|i| before[i] == after[i]);
    }
    let (mut left, mut right) = (before.clone(), after.clone());
    if action == "curve" {
        if before["enabled"] != true || after["enabled"] != true { return false; }
        left.as_object_mut().unwrap().remove(channel);
        right.as_object_mut().unwrap().remove(channel);
        // Adding the first luminance point to a legacy v1 recipe requires the
        // existing v2 schema, but must not migrate any other curve channel.
        if channel == "luminance" && before["version"] == 1 && after["version"] == 2 {
            right["version"] = json!(1);
            right.as_object_mut().unwrap().remove("luminance_space");
        }
    } else {
        let key = if action == "levels_black" { "input_black" } else { "input_white" };
        for channel in ["red", "green", "blue"] {
            left[channel].as_object_mut().unwrap().remove(key);
            right[channel].as_object_mut().unwrap().remove(key);
        }
    }
    left == right
}
fn decorate(value: &mut Value, bound: Option<&str>, reload: bool) {
    value["protocol"] = json!(1);
    value["requires_reload"] = json!(reload);
    if let Some(bound) = parts(bound) {
        for key in IDENTITY_KEYS { value[*key] = bound[*key].clone(); }
    }
}
pub(crate) struct ColorPickerKind;
impl ReceiptKind for ColorPickerKind {
    const NAME: &'static str = "color_picker";
    const ACTIONS: &'static [&'static str] = ACTIONS;
    fn valid_request(action: &str, bound: Option<&str>) -> bool {
        parts(bound).is_some_and(|v| v["action"] == action)
    }
    fn valid(value: &Value, bound: Option<&str>) -> bool {
        let Some(bound) = parts(bound) else { return false };
        if !common(value, &bound) || !value["requires_reload"].is_boolean() { return false; }
        if value["success"] != true { return true; }
        let action = bound["action"].as_str().unwrap();
        let channel = bound["channel"].as_str().unwrap();
        let (before, after) = (&value["before"], &value["after"]);
        value["requires_reload"] == false && sample(&value["sample"], &bound)
            && recipe(before, action) && recipe(after, action)
            && value["no_change"].as_bool() == Some(before == after)
            && ["undo_steps", "redo_steps"].iter().all(|k| value["history"][*k].as_u64().is_some())
            && unchanged_unrelated(before, after, action, channel)
    }
    fn decorate_failure(value: &mut Value, bound: Option<&str>) { decorate(value, bound, true); }
}
pub(crate) struct ColorPickerProbeKind;
impl ReceiptKind for ColorPickerProbeKind {
    const NAME: &'static str = "color_picker_probe";
    const ACTIONS: &'static [&'static str] = ACTIONS;
    fn valid_request(action: &str, bound: Option<&str>) -> bool {
        parts(bound).is_some_and(|v| v["action"] == action)
    }
    fn valid(value: &Value, bound: Option<&str>) -> bool {
        let Some(bound) = parts(bound) else { return false };
        if !common(value, &bound) { return false; }
        value["success"] != true || (sample(&value["sample"], &bound)
            && crate::color_picker_preview_wire::valid(&value["preview"]))
    }
    fn decorate_failure(value: &mut Value, bound: Option<&str>) { decorate(value, bound, false); }
}
pub(crate) type ColorPickerHost = ReceiptHost<ColorPickerKind>;

/// One actual engine probe at a time, independent of whether its capture was
/// cancelled. UI coalescing is a convenience, not the native admission limit.
#[derive(Default)]
pub(crate) struct ColorPickerProbeHost {
    receipts: ReceiptHost<ColorPickerProbeKind>,
    active: Option<([u8; 16], String, String)>,
}
impl ColorPickerProbeHost {
    pub fn reset(&mut self, epoch: [u8; 16]) { self.receipts.reset(epoch); self.active = None; }
    pub fn ready(&mut self, epoch: [u8; 16], supported: bool) { self.receipts.ready(epoch, supported); }
    pub fn begin_bound(&mut self, epoch: [u8; 16], id: &str, action: &str, bound: Option<&str>) -> Result<(), String> {
        if self.active.is_some() { return Err("a targeted color probe is still in flight".into()); }
        self.receipts.begin_bound(epoch, id, action, bound)?;
        self.active = Some((epoch, id.into(), action.into()));
        Ok(())
    }
    pub fn receive(&mut self, epoch: [u8; 16], value: &Value) {
        let current = self.active.as_ref().filter(|(e, id, _)| *e == epoch
            && value["request_id"].as_str() == Some(id.as_str()));
        if let Some((_, id, action)) = current {
            if value["action"].as_str() != Some(action.as_str()) {
                self.receipts.failed(id, &format!("color probe action changed from {action}"));
            } else { self.receipts.receive(epoch, value); }
            // ReceiptHost terminalizes this receipt even for malformed payloads.
            // Do not clone its PNG merely to read the completion phase.
            self.active = None;
        } else { self.receipts.receive(epoch, value); }
    }
    pub fn failed(&mut self, id: &str, error: &str) {
        self.receipts.failed(id, error);
        if self.active.as_ref().is_some_and(|(_, active, _)| active == id) { self.active = None; }
    }
    pub fn ended(&mut self, epoch: [u8; 16]) {
        self.receipts.ended(epoch);
        if self.active.as_ref().is_some_and(|(e, _, _)| *e == epoch) { self.active = None; }
    }
    pub fn status(&self, id: &str) -> Value { self.receipts.status(id) }
}

#[cfg(test)]
#[path = "color_picker_host_tests.rs"]
mod tests;
