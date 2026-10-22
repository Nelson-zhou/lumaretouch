//! Single bounded, epoch-bound preview mailbox. Pixels never enter edit history here.
use serde_json::{json, Value};
#[derive(Default)]
pub(crate) struct PromptedMaskHost {
    epoch: [u8;16],
    pub binding: Option<(String, String, String, String)>, // preview, capture, ticket, document
    value: Option<Value>,
}
impl PromptedMaskHost {
    pub fn reset(&mut self, epoch: [u8;16]) { self.epoch = epoch; self.binding = None; self.value = None; }
    pub fn ended(&mut self, epoch: [u8;16]) { if self.epoch == epoch { self.reset([0;16]); } }
    pub fn begin(&mut self, epoch: [u8;16], preview: &str, capture: &str, ticket: &str, document: &str) -> Result<(), String> {
        if self.epoch != epoch || epoch == [0;16] { return Err("prompted preview engine changed".into()); }
        self.binding = Some((preview.into(), capture.into(), ticket.into(), document.into()));
        self.value = Some(json!({"protocol":1,"preview_id":preview,"document_id":document,"state":"running","success":true}));
        Ok(())
    }
    pub fn receive(&mut self, epoch: [u8;16], value: &Value) {
        let Some((preview, _, _, document)) = &self.binding else { return };
        if epoch != self.epoch || value["preview_id"].as_str() != Some(preview.as_str())
            || value["document_id"].as_str() != Some(document.as_str()) { return; }
        let ready_invalid = value["state"] == "ready" && (
            !value["result"]["source_image"].as_str().is_some_and(|s| s.starts_with("data:image/png;base64,"))
            || value["result"].get("candidates").is_some_and(|v| !v.as_array().is_some_and(|items|
                items.len() == 3 && items.iter().all(|s| s.as_str().is_some_and(|s| s.starts_with("data:image/png;base64,"))))));
        if ready_invalid || value.to_string().len() > 8*1024*1024 || value["protocol"] != 1 || !value["success"].is_boolean()
            || !matches!(value["state"].as_str(), Some("running"|"ready"|"failed"|"cancelled")) {
            self.value = Some(json!({"state":"failed","success":false,"error":"Invalid or oversized prompted preview"}));
        } else { self.value = Some(value.clone()); }
    }
    pub fn status(&self, epoch: [u8;16], preview: &str) -> Value {
        if epoch == self.epoch && self.binding.as_ref().is_some_and(|b| b.0 == preview) {
            self.value.clone().unwrap_or_else(|| json!({"state":"stale"}))
        } else { json!({"state":"stale"}) }
    }
}
