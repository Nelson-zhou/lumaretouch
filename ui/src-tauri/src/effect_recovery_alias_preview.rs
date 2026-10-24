// SPDX-License-Identifier: GPL-3.0-or-later
//! Bounded immutable alias image delivery ledger. AUTHORED / UNRUN.
//! PNG bytes are verified, then explicit presentation is required separately.
use std::collections::{BTreeSet, VecDeque};
use serde_json::{json, Value};
use crate::source_patch_capture_host::Proof;
use super::alias;
const MAX_RECORDS: usize = 32;
const MAX_BYTES: usize = 16 * 1024 * 1024;
struct Page { request: Value, result: Option<Value>, delivered: bool, terminal: bool }
pub(super) struct AliasPreview {
    review: Value,
    pages: VecDeque<Page>,
    delivered: BTreeSet<(String, String)>,
}
impl AliasPreview {
    pub fn new(review: &Value, proof: &Proof) -> Result<Self, String> {
        if review.to_string().len() > 192 * 1024 || !alias::review(review, proof) {
            return Err("Invalid shared effect-recovery full-render review".into());
        }
        Ok(Self { review: review.clone(), pages: VecDeque::new(), delivered: BTreeSet::new() })
    }
    fn metadata(&self, request: &Value) -> Option<&Value> {
        if request["protocol"] != 2 || request["review_sha256"] != self.review["review_sha256"]
            || !matches!(request["side"].as_str(), Some("before" | "after")) { return None; }
        let own = self.review["members"].as_array()?.iter().find(|row|
            row["visual"]["document_id"] == request["member_document_id"]
                && row["visual"]["revision"] == request["member_revision"])?;
        let image = &own["visual"][request["side"].as_str()?];
        (image["sha256"] == request["sha256"]).then_some(image)
    }
    pub fn begin_image(&mut self, request: &Value) -> Result<(), String> {
        if !crate::preset_api::visual::text(&request["request_id"]) || self.metadata(request).is_none() {
            return Err("Image request differs from its frozen alias, revision, side or content digest".into());
        }
        if self.pages.iter().any(|page| page.request["request_id"] == request["request_id"]) {
            return Err("Use a fresh shared recovery image request ID".into());
        }
        while self.pages.len() >= MAX_RECORDS {
            let index = self.pages.iter().position(|page| page.delivered).ok_or("Too many pending alias image requests")?;
            self.pages.remove(index);
        }
        self.pages.push_back(Page { request: request.clone(), result: None, delivered: false, terminal: false });
        Ok(())
    }
    pub fn receive(&mut self, value: &Value) {
        let Some(index) = self.pages.iter().position(|page| page.request["request_id"] == value["request_id"]) else { return; };
        if self.pages[index].terminal { return; }
        let request = self.pages[index].request.clone();
        let same = ["protocol", "preview_id", "request_id", "review_sha256", "member_document_id", "member_revision", "side", "sha256"]
            .iter().chain(alias::PROOF.iter()).all(|key| value.get(*key) == request.get(*key));
        let valid = same && value.to_string().len() <= 6 * 1024 * 1024 && value["success"].is_boolean()
            && ((value["state"] == "image" && value["success"] == true
                && crate::people_api::face_style::image(&value["image"])
                && self.metadata(&request).is_some_and(|metadata| ["mime", "width", "height", "sha256"]
                    .iter().all(|key| value["image"][*key] == metadata[*key])))
                || (value["state"] == "failed" && value["success"] == false
                    && value["error"].as_str().is_some_and(|s| !s.trim().is_empty() && s.len() <= 8000)));
        let mut result = if valid { value.clone() } else { request.clone() };
        if !valid {
            result["state"] = json!("failed"); result["success"] = json!(false);
            result["error"] = json!("Alias image identity, dimensions, PNG framing or content digest changed");
            result.as_object_mut().unwrap().remove("cmd"); result.as_object_mut().unwrap().remove("action");
        }
        // Evict delivered byte payloads only. Compact delivery evidence remains
        // independently owned, and a pending/undelivered page is never replaced.
        let bytes = result.to_string().len();
        while self.pages.iter().map(|page| page.result.as_ref().map_or(0, |v| v.to_string().len())).sum::<usize>() + bytes > MAX_BYTES {
            let Some(old) = self.pages.iter().position(|page| page.delivered && page.result.is_some()) else { break; };
            self.pages[old].result = None;
        }
        if self.pages.iter().map(|page| page.result.as_ref().map_or(0, |v| v.to_string().len())).sum::<usize>() + bytes > MAX_BYTES {
            result = request.clone(); result["state"] = json!("failed"); result["success"] = json!(false);
            result["error"] = json!("Alias image delivery budget exceeded; retrieve fewer pending pages");
        }
        self.pages[index].terminal = true;
        self.pages[index].result = Some(result);
    }
    pub fn has_failed(&self) -> bool {
        self.pages.iter().any(|page| page.result.as_ref().is_some_and(|value| value["state"] == "failed"))
    }
    pub fn status(&mut self, request_id: &str) -> Value {
        let Some(page) = self.pages.iter_mut().find(|page| page.request["request_id"] == request_id) else {
            return json!({"state":"stale", "request_id":request_id});
        };
        if let Some(value) = &page.result {
            page.delivered = true;
            if value["state"] == "image" && value["success"] == true {
                self.delivered.insert((page.request["member_document_id"].as_str().unwrap().to_owned(),
                    page.request["side"].as_str().unwrap().to_owned()));
            }
            return value.clone();
        }
        let mut status = page.request.clone();
        status["state"] = json!(if page.delivered { "stale" } else { "pending" });
        status.as_object_mut().unwrap().remove("cmd"); status.as_object_mut().unwrap().remove("action");
        status
    }
    pub fn allow_presented(&self, acknowledgment: &Value) -> Result<(), String> {
        if !alias::acknowledgment(acknowledgment) || *acknowledgment != alias::expected_ack(&self.review)
            || !self.review["members"].as_array().unwrap().iter().all(|row| ["before", "after"].iter().all(|side|
                self.delivered.contains(&(row["visual"]["document_id"].as_str().unwrap().to_owned(), (*side).to_owned())))) {
            return Err("Every exact alias image pair must be delivered and explicitly acknowledged".into());
        }
        Ok(())
    }
    pub fn acknowledgment(&self) -> Value { alias::expected_ack(&self.review) }
    pub fn presented(&self, value: &Value) -> bool { value["review_sha256"] == self.review["review_sha256"] }
}
