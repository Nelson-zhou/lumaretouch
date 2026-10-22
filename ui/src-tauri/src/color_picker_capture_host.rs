//! Frozen targeted color input capture. The sampled scalar values stay in the engine. Invalidating a ticket never releases
//! the one in-flight read: only completion of that exact read releases its lease.
use serde_json::{json, Value};
use crate::{capture_wire::Identity, color_capture_host::{id16, token}, frame_identity::hex};

#[derive(Clone, Debug)]
pub(crate) struct Proof {
    pub identity: Identity,
    pub recipe_document_id: String,
    pub recipe_revision: String,
    pub descriptor: Value,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase { Arming, Ready, Copying, Copied, Eligible, Redeemed }
struct Record {
    capture: String, document: String, ticket: u64, revision: usize,
    phase: Phase, proof: Option<Proof>, action: String, channel: String,
}
#[derive(Default)]
pub(crate) struct ColorPickerCaptureHost {
    epoch: [u8;16], supported: bool, counter: u64, record: Option<Record>,
    copying: Option<Identity>, error: Option<(String, String, String)>,
}
fn revision(value: &str) -> Result<u64, String> {
    let n = value.parse::<u64>().map_err(|_| "invalid recipe revision")?;
    if n.to_string() != value { return Err("noncanonical recipe revision".into()); }
    Ok(n)
}
fn dimension_pair(value: &Value) -> bool {
    value.as_array().is_some_and(|a| a.len() == 2 && a.iter().all(|v| v.as_u64().is_some_and(|n| n > 0 && n <= u32::MAX as u64)))
}
fn projection(value: &Value, identity: &Identity) -> bool {
    // Bounded, explicit metadata only. The engine retains the authoritative
    // geometry and performs stage-domain projection; none of this comes from IPC.
    let keys = ["version", "source_proxy", "rect", "integer_crop", "rotation", "quarter_turn", "rotated", "target", "resize", "align_corners", "antialias"];
    if !value.as_object().is_some_and(|o| o.len() == keys.len() && keys.iter().all(|key| o.contains_key(*key)))
        || value["version"] != "crop-rotate-fixed-proxy-v1" || value["resize"] != "bilinear"
        || value["align_corners"] != false || value["antialias"] != false
        || value["source_proxy"] != json!([identity.width,identity.height])
        || value["target"] != json!([identity.width,identity.height]) || !dimension_pair(&value["rotated"])
        || !value["rotation"].as_f64().is_some_and(|n| n.is_finite() && (-180.0..=180.0).contains(&n))
        || !(value["quarter_turn"].is_null() || value["quarter_turn"].as_u64().is_some_and(|n| n <= 3)) { return false; }
    let Some(rect) = value["rect"].as_array() else { return false };
    if rect.len() != 4 || !rect.iter().all(|v| v.as_f64().is_some_and(|n| n.is_finite() && (0.0..=1.0).contains(&n)))
        || rect[0].as_f64() >= rect[2].as_f64() || rect[1].as_f64() >= rect[3].as_f64() { return false; }
    let Some(crop) = value["integer_crop"].as_array() else { return false };
    crop.len() == 4 && crop.iter().all(|v| v.as_u64().is_some_and(|n| n <= u32::MAX as u64))
        && crop[0].as_u64() < crop[2].as_u64() && crop[1].as_u64() < crop[3].as_u64()
        && crop[2].as_u64() <= Some(identity.width as u64) && crop[3].as_u64() <= Some(identity.height as u64)
}
impl ColorPickerCaptureHost {
    pub fn reset(&mut self, epoch: [u8;16]) { self.invalidate(); self.epoch = epoch; self.supported = false; }
    pub fn ready(&mut self, epoch: [u8;16], supported: bool) { if self.epoch == epoch { self.supported = supported; } }
    pub fn invalidate(&mut self) { self.record = None; self.error = None; }
    pub fn engine_ended(&mut self, epoch: [u8;16]) {
        if self.epoch == epoch { self.invalidate(); self.epoch = [0;16]; self.supported = false; }
    }
    pub fn begin(&mut self, epoch: [u8;16], capture: String, document: String, host_revision: usize, action: String, channel: String) -> Result<String, String> {
        crate::color_picker_host::selection(&action, &channel)?;
        id16(&capture)?; token(&document)?;
        if epoch == [0;16] || self.epoch != epoch || !self.supported { return Err("color-action-input capture is unavailable".into()); }
        self.counter = self.counter.checked_add(1).ok_or("targeted color capture ticket exhausted")?;
        let ticket = self.counter;
        self.invalidate();
        self.record = Some(Record { capture, document, ticket, revision: host_revision, phase: Phase::Arming, proof: None, action, channel });
        Ok(ticket.to_string())
    }
    pub fn armed_event(&mut self, epoch: [u8;16], event: &Value, host_revision: usize) {
        if epoch == [0;16] || epoch != self.epoch || event["event"] != "color_picker_capture" || event["action"] != "arm" { return; }
        let Some(record) = self.record.as_ref() else { return };
        if record.phase != Phase::Arming || event["capture_id"] != record.capture || event["ticket"] != record.ticket.to_string() { return; }
        let result = (|| -> Result<Proof, String> {
            if event["success"] != true { return Err(event["error"].as_str().unwrap_or("color-action-input capture failed").chars().take(2000).collect()); }
            if host_revision != record.revision { return Err("document changed while arming targeted color input; retry".into()); }
            let d = &event["descriptor"];
            if d["version"] != 1 || d["domain"] != "color-action-input" || d["quality"] != "proxy-float-input"
                || d["picker_action"] != record.action || d["picker_channel"] != record.channel
                || d["source_stage"] != crate::color_picker_host::stage(&record.action, &record.channel)
                || d["profile"] != "working-srgb" || d["document_id"] != record.document
                || d["epoch"] != hex(epoch) || d["seq"] != "1" || !dimension_pair(&d["full_source"]) {
                return Err("color-action-input descriptor contract mismatch".into());
            }
            // Older capture consumers expect these aliases in the descriptor.
            // If supplied, they must agree; the registered record is authoritative.
            let ticket_text = record.ticket.to_string();
            for (key, value) in [("capture_id", record.capture.as_str()), ("ticket", ticket_text.as_str())] {
                if d.get(key).is_some() && d[key].as_str() != Some(value) { return Err("color-action-input descriptor identity mismatch".into()); }
            }
            let scalar = |key: &str| token(d[key].as_str().ok_or("missing capture integer")?);
            let dimension = |key: &str| -> Result<u32, String> {
                u32::try_from(d[key].as_u64().ok_or("missing capture dimension")?).map_err(|_| "capture dimension overflow".into())
            };
            let identity = Identity { epoch, instance: id16(d["shm_instance"].as_str().ok_or("missing capture artifact identity")?)?,
                capture: id16(&record.capture)?, seq: 1, generation: scalar("generation")?, document: token(&record.document)?, ticket: record.ticket,
                width: dimension("width")?, height: dimension("height")?, presentation_width: dimension("presentation_width")?, presentation_height: dimension("presentation_height")? };
            identity.header().map_err(str::to_owned)?;
            if !projection(&d["projection"], &identity) { return Err("color-action-input projection descriptor is invalid".into()); }
            let recipe_document_id = d["recipe_document_id"].as_str().ok_or("missing recipe document identity")?;
            id16(recipe_document_id)?;
            let recipe_revision = d["recipe_revision"].as_str().ok_or("missing recipe revision")?;
            revision(recipe_revision)?;
            // Do not retain arbitrary, potentially large event extension fields.
            let mut descriptor = json!({});
            for key in ["version","domain","quality","profile","epoch","shm_instance","seq","generation","document_id",
                "recipe_document_id","recipe_revision","width","height","presentation_width","presentation_height","projection","full_source","picker_action","picker_channel","source_stage"] {
                descriptor[key] = d[key].clone();
            }
            descriptor["capture_id"] = json!(record.capture); descriptor["ticket"] = json!(record.ticket.to_string());
            Ok(Proof { identity, recipe_document_id: recipe_document_id.to_owned(), recipe_revision: recipe_revision.to_owned(), descriptor })
        })();
        match result {
            Ok(proof) => { let r = self.record.as_mut().unwrap(); r.phase = Phase::Ready; r.proof = Some(proof); self.error = None; }
            Err(error) => { let r = self.record.take().unwrap(); self.error = Some((r.capture, r.ticket.to_string(), error)); }
        }
    }
    fn matching(&self, capture: &str, ticket: &str) -> Result<&Record, String> {
        id16(capture)?; token(ticket)?;
        let r = self.record.as_ref().ok_or("color-action-input capture is unavailable")?;
        if r.capture != capture || r.ticket.to_string() != ticket { return Err("color-action-input capture identity changed".into()); }
        Ok(r)
    }
    pub fn begin_copy(&mut self, capture: &str, ticket: &str) -> Result<Identity, String> {
        if self.copying.is_some() { return Err("a color-action-input copy is still in flight".into()); }
        let r = self.matching(capture, ticket)?;
        if r.phase != Phase::Ready { return Err("color-action-input frame is not available for copying".into()); }
        let identity = r.proof.as_ref().ok_or("color-action-input proof unavailable")?.identity.clone();
        self.record.as_mut().unwrap().phase = Phase::Copying;
        self.copying = Some(identity.clone());
        Ok(identity)
    }
    pub fn finish_copy(&mut self, identity: &Identity, error: Option<&str>) -> Result<(), String> {
        if self.copying.as_ref() != Some(identity) { return Err("color-action-input copy lease changed".into()); }
        self.copying = None;
        let current = self.record.as_ref().is_some_and(|r| r.phase == Phase::Copying && r.proof.as_ref().is_some_and(|p| &p.identity == identity));
        if !current || self.epoch != identity.epoch { return Err("color-action-input capture invalidated during copy".into()); }
        if let Some(error) = error {
            let r = self.record.take().unwrap();
            self.error = Some((r.capture, r.ticket.to_string(), error.chars().take(2000).collect()));
            return Err(error.into());
        }
        self.record.as_mut().unwrap().phase = Phase::Copied;
        Ok(())
    }
    pub fn confirm_copied(&self, identity: &Identity) -> Result<(), String> {
        if self.record.as_ref().is_some_and(|r| r.phase == Phase::Copied && r.proof.as_ref().is_some_and(|p| &p.identity == identity)) {
            Ok(())
        } else { Err("color-action-input capture invalidated before delivery".into()) }
    }
    pub fn presented(&mut self, capture: &str, ticket: &str, document: &str) -> Result<Proof, String> {
        let r = self.matching(capture, ticket)?;
        if r.document != document || ![Phase::Copied, Phase::Eligible].contains(&r.phase) { return Err("color-action-input pixels have not been delivered for this document".into()); }
        let proof = r.proof.as_ref().ok_or("color-action-input proof unavailable")?.clone();
        self.record.as_mut().unwrap().phase = Phase::Eligible;
        Ok(proof)
    }
    pub fn eligible_proof(&self, epoch: [u8;16], capture: &str, ticket: &str) -> Result<Proof, String> {
        let r = self.matching(capture, ticket)?;
        if epoch != self.epoch || epoch == [0;16] || r.phase != Phase::Eligible { return Err("targeted color capture is not eligible".into()); }
        r.proof.clone().ok_or("targeted color capture proof unavailable".into())
    }
    pub fn redeem(&mut self, epoch: [u8;16], capture: &str, ticket: &str) -> Result<Proof, String> {
        let r = self.matching(capture, ticket)?;
        if epoch != self.epoch || epoch == [0;16] || r.phase != Phase::Eligible { return Err("color-action-input capture is not eligible for apply".into()); }
        let proof = r.proof.as_ref().ok_or("color-action-input proof unavailable")?.clone();
        self.record.as_mut().unwrap().phase = Phase::Redeemed;
        Ok(proof)
    }
    pub fn cancel(&mut self, capture: &str, ticket: Option<&str>, document: &str) -> Option<Proof> {
        let matches = self.record.as_ref().is_some_and(|r| r.capture == capture && r.document == document
            && ticket.map(|t| r.ticket.to_string() == t).unwrap_or(true));
        if !matches { return None; }
        let proof = self.record.as_ref().and_then(|r| r.proof.clone());
        self.invalidate(); proof
    }
    pub fn status_for(&self, capture: &str, ticket: &str) -> Value {
        if let Some((id, t, error)) = &self.error {
            if id == capture && t == ticket { return json!({"phase":"error","capture_id":id,"ticket":t,"error":error}); }
        }
        let Ok(r) = self.matching(capture, ticket) else { return json!({"phase":"stale","error":"color-action-input capture identity changed"}); };
        let phase = match r.phase { Phase::Arming=>"arming",Phase::Ready=>"ready",Phase::Copying=>"copying",Phase::Copied=>"copied",Phase::Eligible=>"eligible",Phase::Redeemed=>"redeemed" };
        json!({"phase":phase,"capture_id":r.capture,"ticket":r.ticket.to_string(),"descriptor":r.proof.as_ref().map(|p| &p.descriptor)})
    }
}

#[cfg(test)]
#[path = "color_picker_capture_tests.rs"]
mod tests;
