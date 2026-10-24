//! Bounded, epoch-bound terminal receipts. Acceptance is not completion.
use std::{collections::VecDeque, marker::PhantomData};
use serde_json::{json, Value};
pub(crate) const MAX_RECORDS: usize = 32;
const MAX_RESULT_BYTES: usize = 8 * 1024 * 1024;
const MAX_BYTES: usize = 16 * 1024 * 1024;
pub(crate) trait ReceiptKind {
    const NAME: &'static str;
    const ACTIONS: &'static [&'static str];
    fn valid(value: &Value, document: Option<&str>) -> bool;
    fn valid_request(_: &str, _: Option<&str>) -> bool { true }
    fn decorate_failure(_: &mut Value, _: Option<&str>) {}
}

// AUTHORED / UNRUN. Transport ledger specifications, not engine or product acceptance.
#[cfg(test)]
mod scalar_binding_tests {
    use super::*;
    struct FixtureKind;
    impl ReceiptKind for FixtureKind {
        const NAME: &'static str = "batch";
        const ACTIONS: &'static [&'static str] = &["preflight", "commit"];
        fn valid(value: &Value, _: Option<&str>) -> bool {
            value["success"].is_boolean() && value["outcome_unknown"].is_boolean()
        }
    }
    fn host() -> ReceiptHost<FixtureKind> {
        let mut host = ReceiptHost::default(); host.reset([1;16]); host.ready([1;16], true); host
    }
    fn command() -> Value {
        json!({"cmd":"batch","action":"commit","request_id":"waist","preflight_token":"f".repeat(32),
            "waist_review_ack":[
                {"document_id":"first","revision":"2","before_sha256":"a".repeat(64),"after_sha256":"b".repeat(64)},
                {"document_id":"second","revision":"3","before_sha256":"c".repeat(64),"after_sha256":"d".repeat(64)}]})
    }
    fn terminal(command: &Value) -> Value {
        json!({"action":"commit","request_id":command["request_id"],"success":true,"outcome_unknown":false,
            "module_scope":[crate::waist_transfer_protocol::WAIST_OP],"preflight_token":command["preflight_token"],
            "waist_review_ack":command["waist_review_ack"]})
    }
    #[test] fn immutable_exact_token_scope_and_ordered_ack_are_required() {
        let command = command(); let value = terminal(&command);
        for path in ["/preflight_token", "/module_scope", "/waist_review_ack/0/before_sha256", "/waist_review_ack/0/revision"] {
            let mut host = host(); host.begin_command([1;16], &command).unwrap();
            let mut changed = value.clone();
            *changed.pointer_mut(path).unwrap() = match path {
                "/preflight_token" => json!("e".repeat(32)), "/module_scope" => json!([crate::torso_transfer_protocol::TORSO_OP]),
                "/waist_review_ack/0/revision" => json!("3"), _ => json!("e".repeat(64)),
            };
            host.receive([1;16], &changed);
            let result = host.status("waist")["result"].clone();
            assert_eq!(result["outcome_unknown"], true, "{path}");
            assert_eq!(result["preflight_token"], command["preflight_token"]);
            assert_eq!(result["waist_review_ack"], command["waist_review_ack"]);
            assert_eq!(result["module_scope"], value["module_scope"]);
        }
        let mut host = host(); host.begin_command([1;16], &command).unwrap();
        let mut reordered = value; reordered["waist_review_ack"].as_array_mut().unwrap().reverse();
        host.receive([1;16], &reordered); assert_eq!(host.status("waist")["result"]["outcome_unknown"], true);
    }
    #[test] fn copied_binding_survives_sender_changes_send_failure_and_shutdown() {
        let original = command(); let mut changed = original.clone();
        let mut host = host(); host.begin_command([1;16], &changed).unwrap();
        changed["waist_review_ack"][0]["after_sha256"] = json!("e".repeat(64));
        host.failed("waist", "transport outcome is uncertain");
        assert_eq!(host.status("waist")["result"]["waist_review_ack"], original["waist_review_ack"]);
        assert_eq!(host.status("waist")["result"]["outcome_unknown"], true);
        let mut other = original.clone(); other["request_id"] = json!("shutdown");
        host.begin_command([1;16], &other).unwrap(); host.ended([1;16]);
        assert_eq!(host.status("shutdown")["result"]["preflight_token"], original["preflight_token"]);
        assert_eq!(host.status("shutdown")["result"]["waist_review_ack"], original["waist_review_ack"]);
        host.reset([2;16]); assert_eq!(host.status("shutdown")["phase"], "unavailable");
    }
    #[test] fn contradictory_unsettled_scalar_envelopes_cannot_look_terminal() {
        let command = command();
        for (key, replacement) in [("requires_reload", json!(true)), ("requires_readback", json!(true)),
            ("requires_reload", json!("yes")), ("status", json!("running")), ("phase", json!("accepted")),
            ("phase", json!(1))] {
            let mut host = host(); host.begin_command([1;16], &command).unwrap();
            let mut value = terminal(&command); value[key] = replacement; host.receive([1;16], &value);
            assert_eq!(host.status("waist")["result"]["outcome_unknown"], true, "{key}");
            assert!(host.guards_review([1;16], "waist"));
        }
    }
    #[test] fn only_explicit_unclaimed_no_write_rejections_can_omit_identity() {
        let command = command();
        let rejected = json!({"request_id":"waist","action":"commit","success":false,"outcome_unknown":false,
            "error":"Claim rejected before mutation"});
        let mut host = host(); host.begin_command([1;16], &command).unwrap(); host.receive([1;16], &rejected);
        assert_eq!(host.status("waist")["result"], rejected);
        let mut batch_rejected = rejected.clone(); batch_rejected["preflight_token"] = command["preflight_token"].clone();
        batch_rejected["target_outcomes"] = json!([{ "outcome":"conflict" }, { "outcome":"not_applied" }]);
        let mut batch_host = self::host(); batch_host.begin_command([1;16], &command).unwrap(); batch_host.receive([1;16], &batch_rejected);
        assert_eq!(batch_host.status("waist")["result"], batch_rejected);
        for (key, replacement) in [("success", json!(true)), ("outcome_unknown", json!(true)),
            ("outcome_unknown", Value::Null), ("module_scope", json!([crate::waist_transfer_protocol::WAIST_OP])),
            ("after", json!({})), ("target_outcomes", json!([{ "outcome":"applied" }])),
            ("preflight_token", json!("e".repeat(32))), ("operation_committed", json!(true)),
            ("requires_reload", json!(true)), ("error", json!(""))] {
            let mut host = self::host(); host.begin_command([1;16], &command).unwrap();
            let mut malformed = rejected.clone(); malformed[key] = replacement;
            host.receive([1;16], &malformed);
            assert_eq!(host.status("waist")["result"]["outcome_unknown"], true, "{key}");
            assert_eq!(host.status("waist")["result"]["waist_review_ack"], command["waist_review_ack"]);
        }
    }
    #[test] fn identity_checks_do_not_bypass_epoch_action_request_or_first_terminal() {
        let command = command(); let value = terminal(&command);
        let mut host = host(); host.begin_command([1;16], &command).unwrap();
        host.receive([2;16], &value); assert_eq!(host.status("waist")["phase"], "pending");
        let mut wrong = value.clone(); wrong["request_id"] = json!("other"); host.receive([1;16], &wrong);
        wrong = value.clone(); wrong["action"] = json!("preflight"); host.receive([1;16], &wrong);
        assert_eq!(host.status("waist")["phase"], "pending");
        host.receive([1;16], &value);
        wrong = value.clone(); wrong["waist_review_ack"][0]["after_sha256"] = json!("e".repeat(64)); host.receive([1;16], &wrong);
        host.failed("waist", "late transport failure");
        assert_eq!(host.status("waist")["result"], value);
        assert!(host.begin_command([1;16], &command).is_err());
    }
    #[test] fn preflight_scope_is_bound_without_inventing_an_ack_or_token() {
        let mut host = host();
        host.begin_command([1;16], &json!({"cmd":"batch","action":"preflight","request_id":"review",
            "module_scope":[crate::waist_transfer_protocol::WAIST_OP]})).unwrap();
        host.receive([1;16], &json!({"request_id":"review","action":"preflight","success":true,"outcome_unknown":false,
            "module_scope":[crate::torso_transfer_protocol::TORSO_OP]}));
        let result = host.status("review")["result"].clone();
        assert_eq!(result["outcome_unknown"], true);
        assert_eq!(result["module_scope"], json!([crate::waist_transfer_protocol::WAIST_OP]));
        assert!(result.get("preflight_token").is_none()); assert!(result.get("waist_review_ack").is_none());
    }
    #[test] fn ordinary_commands_and_legacy_registration_remain_unbound() {
        let value = json!({"request_id":"ordinary","action":"commit","success":true,"outcome_unknown":false});
        let mut host = host();
        host.begin_command([1;16], &json!({"cmd":"batch","action":"commit","request_id":"ordinary"})).unwrap();
        host.receive([1;16], &value); assert_eq!(host.status("ordinary")["result"], value);
        let mut host = self::host(); host.begin([1;16], "waist", "commit").unwrap();
        let value = terminal(&command()); host.receive([1;16], &value); assert_eq!(host.status("waist")["result"], value);
    }
    #[test] fn uncertain_scalar_rows_stay_guarded_and_capacity_bounded_until_reset() {
        let mut host = host();
        for index in 0..MAX_RECORDS {
            let mut request = command(); request["request_id"] = json!(format!("waist-{index}"));
            host.begin_command([1;16], &request).unwrap();
            let mut unknown = terminal(&request); unknown["success"] = json!(false); unknown["outcome_unknown"] = json!(true);
            unknown["untrusted_padding"] = json!("x".repeat(100_000)); unknown["error"] = json!("x".repeat(10_000));
            host.receive([1;16], &unknown);
            let id = request["request_id"].as_str().unwrap();
            assert!(host.guards_review([1;16], id)); assert!(!host.guards_review([2;16], id));
            let result = host.status(id)["result"].clone();
            assert_eq!(result["waist_review_ack"], request["waist_review_ack"]);
            assert!(result.get("untrusted_padding").is_none()); assert!(result.to_string().len() < 16 * 1024);
        }
        assert!(host.begin_command([1;16], &command()).is_err());
        host.reset([2;16]); host.ready([2;16], true);
        assert!(!host.guards_review([1;16], "waist-0")); assert!(host.begin_command([2;16], &command()).is_ok());
    }
    #[test] fn recovery_fence_observes_only_validated_scalar_outcomes() {
        let epoch = [187;16]; let command = command();
        let mut host = ReceiptHost::<FixtureKind>::default(); host.reset(epoch); host.ready(epoch, true);
        host.begin_command(epoch, &command).unwrap();
        crate::project_recovery_fence::issued(epoch, &command).unwrap();
        assert!(host.guards_review(epoch, "waist"));
        let mut substituted = terminal(&command); substituted["preflight_token"] = json!("e".repeat(32));
        host.receive(epoch, &substituted);
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        host.receive(epoch, &terminal(&command)); // No unverified replay replaces first unknown.
        assert!(crate::project_recovery_fence::proof(epoch).is_err());
        crate::project_recovery_fence::observed(epoch, &json!({"event":"project_opened"}));
        let epoch = [188;16];
        let mut host = ReceiptHost::<FixtureKind>::default(); host.reset(epoch); host.ready(epoch, true);
        host.begin_command(epoch, &command).unwrap(); crate::project_recovery_fence::issued(epoch, &command).unwrap();
        host.receive(epoch, &terminal(&command));
        assert!(crate::project_recovery_fence::proof(epoch).is_ok());
    }
}
/// Only immutable scalar review identities live beside the existing receipt.
/// This is not another plan, history, mutation owner, or replayable command.
struct ReviewBinding { fields: Value, bytes: usize }
impl ReviewBinding {
    fn from_command(value: &Value) -> Result<Option<Self>, String> {
        for (operation, ack_key) in [(crate::torso_transfer_protocol::TORSO_OP, "torso_review_ack"),
            (crate::waist_transfer_protocol::WAIST_OP, "waist_review_ack")] {
            let selected = value["module_scope"].as_array().is_some_and(|ops| ops.iter().any(|op| op == operation));
            if !selected && value.get(ack_key).is_none() { continue; }
            crate::torso_transfer_protocol::command(value)?;
            crate::waist_transfer_protocol::command(value)?;
            let terminal = (value["cmd"] == "preset" && value["action"] == "apply")
                || (value["cmd"] == "batch" && value["action"] == "commit");
            if !terminal && value["action"] != "preflight" { continue; }
            let mut fields = json!({"module_scope":[operation]});
            if terminal {
                let ack = value.get(ack_key).ok_or("scalar application requires a frozen image acknowledgment")?;
                fields["preflight_token"] = value["preflight_token"].clone();
                fields[ack_key] = ack.clone();
            }
            // The protocol already bounds each identifier, target count and hash.
            // Keep a second cap so this optional binding cannot expand the ledger.
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("scalar review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes }));
        }
        Ok(None)
    }
    fn matches(&self, value: &Value) -> bool {
        let unsettled = ["requires_reload", "requires_readback"].iter().any(|key| value[*key] == true)
            || ["status", "phase"].iter().any(|key| matches!(value[*key].as_str(),
                Some("pending" | "running" | "unknown" | "queued" | "writing" | "accepted")));
        if (unsettled && value["outcome_unknown"] != true)
            || ["requires_reload", "requires_readback"].iter().any(|key| !value[*key].is_null() && !value[*key].is_boolean())
            || ["status", "phase"].iter().any(|key| !value[*key].is_null() && !value[*key].is_string()) { return false; }
        // A failed claim may be safely corrected only when the engine explicitly
        // reports no write and has not echoed any accepted review identity.
        let no_write = value["success"] == false && value["outcome_unknown"] == false
            && value["error"].as_str().is_some_and(|error| !error.trim().is_empty())
            && ["module_scope", "torso_review_ack", "waist_review_ack",
                "before", "after", "doc_state", "batch_id", "applied", "committed", "operation_committed"]
                .iter().all(|key| value.get(*key).is_none())
            && (value["preflight_token"].is_null() || value.get("preflight_token") == self.fields.get("preflight_token"))
            && value.get("target_outcomes").map_or(true, |outcomes| outcomes.as_array().is_some_and(|rows|
                rows.iter().all(|row| row.is_object() && row["result_revision"].is_null()
                    && matches!(row["outcome"].as_str(), Some("conflict" | "not_applied")))))
            && value["requires_reload"] != true;
        no_write || self.fields.as_object().unwrap().iter().all(|(key, expected)| value.get(key) == Some(expected))
    }
    fn decorate(&self, value: &mut Value) {
        for (key, expected) in self.fields.as_object().unwrap() { value[key] = expected.clone(); }
    }
}
struct Receipt { id: String, action: String, document: Option<String>, review: Option<ReviewBinding>, result: Option<Value>, bytes: usize }
impl Receipt {
    fn evictable(&self) -> bool {
        self.result.as_ref().is_some_and(|result| self.review.is_none() || result["outcome_unknown"] != true)
    }
}
pub(crate) struct ReceiptHost<K: ReceiptKind> {
    epoch: [u8; 16], supported: bool, records: VecDeque<Receipt>, kind: PhantomData<K>,
}
impl<K: ReceiptKind> Default for ReceiptHost<K> {
    fn default() -> Self { Self { epoch: [0; 16], supported: false, records: VecDeque::new(), kind: PhantomData } }
}
impl<K: ReceiptKind> ReceiptHost<K> {
    pub fn reset(&mut self, epoch: [u8; 16]) { self.epoch = epoch; self.supported = false; self.records.clear(); }
    pub fn ready(&mut self, epoch: [u8; 16], supported: bool) { if self.epoch == epoch { self.supported = supported; } }
    /// Raw events for these requests cannot settle the recovery fence before the
    /// original review binding and receipt have been checked here.
    pub fn guards_review(&self, epoch: [u8; 16], id: &str) -> bool {
        epoch == self.epoch && self.records.iter().any(|record| record.id == id && record.review.is_some())
    }
    pub fn begin(&mut self, epoch: [u8; 16], id: &str, action: &str) -> Result<(), String> {
        self.begin_bound(epoch, id, action, None)
    }
    /// Opt-in command binding for the existing preset/batch scalar route. Legacy
    /// callers of begin/begin_bound retain their original receipt behavior.
    pub fn begin_command(&mut self, epoch: [u8; 16], command: &Value) -> Result<(), String> {
        if command["cmd"].as_str() != Some(K::NAME) { return Err("receipt command kind does not match its host".into()); }
        let id = command["request_id"].as_str().ok_or("missing receipt request ID")?;
        let action = command["action"].as_str().ok_or("missing receipt action")?;
        let review = ReviewBinding::from_command(command)?;
        self.begin_bound(epoch, id, action, command["document_id"].as_str())?;
        // begin_bound just appended this unique request, within the same lock.
        let record = self.records.back_mut().unwrap();
        record.bytes = review.as_ref().map_or(0, |binding| binding.bytes);
        record.review = review;
        self.trim_bytes();
        Ok(())
    }
    fn trim_bytes(&mut self) {
        while self.records.iter().map(|record| record.bytes).sum::<usize>() > MAX_BYTES {
            if let Some(index) = self.records.iter().position(Receipt::evictable) { self.records.remove(index); } else { break; }
        }
    }
    pub fn begin_bound(&mut self, epoch: [u8; 16], id: &str, action: &str, document: Option<&str>) -> Result<(), String> {
        if epoch == [0; 16] || epoch != self.epoch { return Err(format!("{} engine generation changed", K::NAME)); }
        if !self.supported { return Err(format!("engine has not advertised reviewed {} support", K::NAME)); }
        if id.is_empty() || id.len() > 128 || !K::ACTIONS.contains(&action) || !K::valid_request(action, document) {
            return Err(format!("invalid {} request", K::NAME));
        }
        if self.records.iter().any(|r| r.id == id) { return Err(format!("{} request ID already exists", K::NAME)); }
        while self.records.len() >= MAX_RECORDS {
            let index = self.records.iter().position(Receipt::evictable).ok_or_else(|| format!("too many pending or uncertain {} requests", K::NAME))?;
            self.records.remove(index);
        }
        self.records.push_back(Receipt { id: id.into(), action: action.into(), document: document.map(str::to_owned), review: None, result: None, bytes: 0 });
        Ok(())
    }
    fn unknown(record: &Receipt, error: &str) -> Value {
        let mut value = json!({"request_id": record.id, "action": record.action, "success": false, "outcome_unknown": true, "error": error});
        K::decorate_failure(&mut value, record.document.as_deref());
        if let Some(review) = &record.review { review.decorate(&mut value); }
        value
    }
    pub fn receive(&mut self, epoch: [u8; 16], value: &Value) {
        if epoch != self.epoch || epoch == [0; 16] { return; }
        let Some(id) = value["request_id"].as_str() else { return };
        let Some(record) = self.records.iter_mut().find(|r| r.id == id) else { return };
        if record.result.is_some() || value["action"].as_str() != Some(record.action.as_str()) { return; }
        let mut result = if !K::valid(value, record.document.as_deref())
            || record.review.as_ref().is_some_and(|review| !review.matches(value))
            || value.to_string().len() > MAX_RESULT_BYTES {
            Self::unknown(record, &format!("invalid or oversized {} receipt; inspect actual state", K::NAME))
        } else { value.clone() };
        if record.review.is_some() && result["outcome_unknown"] == true {
            // Unknown scalar identities cannot be evicted: retain a compact
            // diagnostic rather than pinning arbitrary multi-megabyte payloads.
            let error: String = result["error"].as_str().unwrap_or("Scalar outcome is unknown; inspect actual state")
                .chars().take(2000).collect();
            let mut compact = Self::unknown(record, &error);
            for key in ["requires_reload", "requires_readback", "publication_invalid", "rolled_back"] {
                if result[key].is_boolean() { compact[key] = result[key].clone(); }
            }
            if let Some(code) = result["error_code"].as_str() { compact["error_code"] = json!(code.chars().take(128).collect::<String>()); }
            result = compact;
        }
        record.bytes = result.to_string().len() + record.review.as_ref().map_or(0, |binding| binding.bytes);
        record.result = Some(result);
        if record.review.is_some() {
            // Use the retained, validated result, never the raw engine event.
            // A synthesized unknown carries the original identity and keeps the
            // recovery fence. The real receipt event name is not caller-owned.
            let mut observed = record.result.as_ref().unwrap().clone();
            observed["event"] = json!(format!("{}_result", K::NAME));
            crate::project_recovery_fence::observed(epoch, &observed);
        }
        self.trim_bytes();
    }
    pub fn failed(&mut self, id: &str, error: &str) {
        let value = self.records.iter().find(|r| r.id == id).map(|r| Self::unknown(r, error));
        if let Some(value) = value { self.receive(self.epoch, &value); }
    }
    pub fn ended(&mut self, epoch: [u8; 16]) {
        if self.epoch != epoch { return; }
        let ids: Vec<String> = self.records.iter().filter(|r| r.result.is_none()).map(|r| r.id.clone()).collect();
        for id in ids { self.failed(&id, &format!("engine ended before {} completion was confirmed", K::NAME)); }
        self.epoch = [0; 16]; self.supported = false;
    }
    pub fn status(&self, id: &str) -> Value {
        match self.records.iter().find(|r| r.id == id) {
            Some(r) => match &r.result {
                Some(result) => json!({"phase": "done", "request_id": id, "result": result}),
                None => json!({"phase": "pending", "request_id": id}),
            },
            None => json!({"phase": "unavailable", "request_id": id, "error": "receipt missing, evicted or engine restarted"}),
        }
    }
}
