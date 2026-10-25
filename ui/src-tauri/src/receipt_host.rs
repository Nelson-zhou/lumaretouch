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
struct ReviewBinding { fields: Value, bytes: usize, read_only: bool, strict_failure_identity: bool }
impl ReviewBinding {
    fn from_command(epoch: [u8;16], value: &Value) -> Result<Option<Self>, String> {
        if let Some(fields) = crate::people_api::skin_reference_choice::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("reference-choice identity exceeds people receipt budget".into()); }
            return Ok(Some(Self { fields, bytes,
                read_only: crate::people_api::skin_reference_choice::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::neck_wrinkle::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("neck review identity exceeds people receipt budget".into()); }
            return Ok(Some(Self { fields, bytes,
                read_only: crate::people_api::neck_wrinkle::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::skin_reference_body::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("body-reference identity exceeds people receipt budget".into()); }
            return Ok(Some(Self { fields, bytes,
                read_only: crate::people_api::skin_reference_body::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::skin_reference_match::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("skin-reference identity exceeds people receipt budget".into()); }
            return Ok(Some(Self { fields, bytes,
                read_only: crate::people_api::skin_reference_match::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::effect_recovery_host::alias::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("shared recovery receipt identity exceeds budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: false, strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::eye_bag::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 192 * 1024 { return Err("eye bag source review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::people_api::eye_bag::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::decoration_support_alias::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("Decoration support identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::people_api::decoration_support_alias::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields)=crate::people_api::decoration_alias::binding(value)? {
            let bytes=fields.to_string().len(); if bytes>16*1024{return Err("Decoration alias identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::people_api::decoration_alias::read_only(value),strict_failure_identity:true}));
        }
        if let Some(fields) = crate::people_api::facial_sculpt::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>256*1024 { return Err("Facial structure review identity exceeds receipt budget".into()); }
            return Ok(Some(Self{fields,bytes,read_only:crate::people_api::facial_sculpt::read_only(value),strict_failure_identity:true}));
        }
        if let Some(fields) = crate::people_api::eye_makeup_enhance::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>256*1024 { return Err("Periocular makeup review identity exceeds receipt budget".into()); }
            return Ok(Some(Self{fields,bytes,read_only:crate::people_api::eye_makeup_enhance::read_only(value),strict_failure_identity:true}));
        }
        if let Some(fields) = crate::people_api::face_decoration::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 256 * 1024 { return Err("face decoration source review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::people_api::face_decoration::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::people_api::face_style::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("face style review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::people_api::face_style::read_only(value), strict_failure_identity: false }));
        }
        if let Some(fields)=crate::batch_api::decoration_cohort::binding(value)? {
            let bytes=fields.to_string().len(); if bytes>32*1024{return Err("Decoration cohort identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::batch_api::decoration_cohort::read_only(value),strict_failure_identity:value["action"]!="preflight"}));
        }
        if let Some(fields) = crate::batch_api::eye_cohort::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 32 * 1024 { return Err("eye-bag cohort review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::batch_api::eye_cohort::read_only(value), strict_failure_identity: true }));
        }
        if let Some(fields) = crate::batch_api::eye_bag::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("eye-bag batch review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::batch_api::eye_bag::read_only(value), strict_failure_identity: true }));
        }
        if let Some(mut fields) = crate::batch_api::history::binding(value)? {
            if let Some(markers) = crate::project_recovery_fence::shared_history_markers(epoch, value)? {
                for (key, marker) in markers.as_object().unwrap() { fields[key] = marker.clone(); }
                if markers.get("eye_bag_recovery_alias_review").is_some() || markers.get(crate::people_api::decoration_support_alias::MARKER).is_some()
                    || markers.get(crate::preset_api::face_decoration::ALIAS_MARKER).is_some() { fields["module_scope"] = json!(["lnx.people_graph.v1"]); }
            }
            let bytes = fields.to_string().len();
            return Ok(Some(Self { fields, bytes, read_only: false, strict_failure_identity: true }));
        }
        if let Some(fields) = crate::batch_api::portrait_cohort::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("portrait cohort review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::batch_api::portrait_cohort::read_only(value),
                strict_failure_identity: value["action"] == "portrait_cohort_visual" }));
        }
        if let Some(fields) = crate::batch_api::face_style::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("face style batch review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::batch_api::face_style::read_only(value),
                strict_failure_identity: value["action"] == "face_style_visual" }));
        }
        if let Some(fields) = crate::preset_api::eye_bag::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>16*1024{return Err("preset eye-bag review identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::preset_api::eye_bag::read_only(value),
                strict_failure_identity:crate::preset_api::eye_bag::strict_failure_identity(value)}));
        }
        if let Some(fields) = crate::preset_api::face_decoration::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>16*1024 {return Err("decoration review identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::preset_api::face_decoration::read_only(value),
                strict_failure_identity:value["action"]!="preflight"}));
        }
        if let Some(fields) = crate::batch_api::face_decoration::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>16*1024 {return Err("decoration review identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::batch_api::face_decoration::read_only(value),
                strict_failure_identity:value["action"]!="preflight"}));
        }
        if let Some(fields) = crate::preset_api::collarbone::binding(value)? {
            let bytes=fields.to_string().len();
            if bytes>16*1024{return Err("preset collarbone review identity exceeds receipt budget".into());}
            return Ok(Some(Self{fields,bytes,read_only:crate::preset_api::collarbone::read_only(value),strict_failure_identity:false}));
        }
        if let Some(fields) = crate::batch_api::collarbone::binding(value)? {
            let bytes = fields.to_string().len();
            if bytes > 16 * 1024 { return Err("collarbone review identity exceeds receipt budget".into()); }
            return Ok(Some(Self { fields, bytes, read_only: crate::batch_api::collarbone::read_only(value), strict_failure_identity: false }));
        }
        for family in crate::preset_host::BODY_REVIEW_FAMILIES {
            let operation = family.op();
            let ack_key = family.ack_key();
            let selected = family.selected(value);
            if !selected && value.get(ack_key).is_none() { continue; }
            for policy in crate::preset_host::BODY_REVIEW_FAMILIES { policy.command(value)?; }
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
            return Ok(Some(Self { fields, bytes, read_only: crate::torso_transfer_protocol::read_only_head_preflight(value), strict_failure_identity: false }));
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
            && ["face_decoration_cohort", "face_decoration_cohort_ack", "face_decoration_cohort_visual", "module_scope", "face_decoration_review_ack", "face_decoration_preset_ack", "face_decoration_preset", "face_decoration_visual_required", "torso_review_ack", "waist_review_ack", "head_review_ack", "collarbone_review_ack", "collarbone_preset_ack", "collarbone_preset", "face_style_review_ack", "face_style", "face_style_visual",
                "eye_bag_cohort", "eye_bag_cohort_ack", "eye_bag_cohort_visual", "eye_bag_preset", "eye_bag_preset_ack", "eye_bag_review_ack", "eye_bag", "eye_bag_coverage", "eye_bag_visual", "portrait_cohort_ack", "portrait_cohort", "portrait_visual", "persistent_association", "association_source", "source_outcome", "collarbone_cohort",
                "torso_transfer", "waist_transfer", "head_transfer",
                "face_decoration_preset_alias_review", "alias_members", "member_document_id", "member_revision", "before", "after", "doc_state", "batch_id", "applied", "committed", "operation_committed"]
                .iter().all(|key| value.get(*key).is_none())
            && (value["preflight_token"].is_null() || value.get("preflight_token") == self.fields.get("preflight_token"))
            && value.get("target_outcomes").map_or(true, |outcomes| outcomes.as_array().is_some_and(|rows|
                rows.iter().all(|row| row.is_object() && row["result_revision"].is_null()
                    && matches!(row["outcome"].as_str(), Some("conflict" | "not_applied")))))
            && value["requires_reload"] != true;
        // A second family cannot be added to a portrait acknowledgment after
        // dispatch. Both presence and the exact ordered arrays were authorized.
        let same_families = (self.fields.get("face_decoration_cohort_ack").is_none() || ["eye_bag_cohort_ack","eye_bag_cohort","portrait_cohort_ack","portrait_cohort","collarbone_review_ack","collarbone_cohort"].iter().all(|key|value.get(*key)==self.fields.get(*key))) && (self.fields.get("face_decoration_review_ack").is_none()
            || ["eye_bag_review_ack","collarbone_review_ack"].iter().all(|k|value.get(*k)==self.fields.get(*k))) && (!(self.fields.get("side").is_some() && self.fields.get("sha256").is_some()
            && self.fields.get("preflight_token").is_some())
            || ["member_document_id", "member_revision"].iter().all(|key| value.get(*key) == self.fields.get(*key)))
            && (self.fields.get("eye_bag_cohort_ack").is_none()
            || ["portrait_cohort_ack", "portrait_cohort", "collarbone_review_ack", "collarbone_cohort"]
                .iter().all(|key| value.get(*key) == self.fields.get(*key)))
            && (self.fields.get("eye_bag_review_ack").is_none()
            || (value.get("collarbone_review_ack") == self.fields.get("collarbone_review_ack")
                && value.get("face_decoration_review_ack")==self.fields.get("face_decoration_review_ack")))
            && (self.fields.get("portrait_cohort_ack").is_none()
            || (value.get("collarbone_review_ack") == self.fields.get("collarbone_review_ack")
                && value.get("collarbone_cohort") == self.fields.get("collarbone_cohort")));
        (no_write && !self.strict_failure_identity && self.fields.get("face_style_request").is_none()) || (same_families && self.fields.as_object().unwrap().iter().all(|(key, expected)| {
            if key=="face_decoration_cohort_applies_sha256" || key=="face_decoration_applies_sha256" || key=="eye_bag_cohort_applies_sha256" || key=="eye_bag_applies_sha256" {
                value["applies"].is_object() && expected.as_str()==Some(crate::batch_api::collarbone::request_digest(&value["applies"]).as_str())
            } else if key=="collarbone_applies_sha256" {
                value["applies"].is_object() && expected.as_str()==Some(crate::batch_api::collarbone::request_digest(&value["applies"]).as_str())
            } else if key=="face_style_applies_sha256" {
                value["applies"].is_object() && expected.as_str()==Some(crate::batch_api::face_style::request_digest(&value["applies"]).as_str())
            } else if key=="portrait_applies_sha256" {
                value["applies"].is_object() && expected.as_str()==Some(crate::batch_api::face_style::request_digest(&value["applies"]).as_str())
            } else {value.get(key)==Some(expected)}
        }))
    }
    fn decorate(&self, value: &mut Value) {
        if self.fields[crate::preset_api::face_decoration::ACK].get("members").is_some() {
            value["face_decoration_visual_required"] = json!(true);
        }
        if (self.fields["protocol"] == 2 && self.fields.get("ack").is_some())
            || self.fields.get("eye_bag_recovery_alias_review").is_some()
            || self.fields.get(crate::people_api::decoration_support_alias::MARKER).is_some()
            || self.fields.get(crate::preset_api::face_decoration::ALIAS_MARKER).is_some()
            || self.fields["face_decoration_support_alias_request"]["action"] == "face_decoration_support_alias_confirm" { value["no_write"] = json!(false); }
        for (key, expected) in self.fields.as_object().unwrap() {
            if !["face_decoration_cohort_applies_sha256", "face_decoration_applies_sha256", "eye_bag_cohort_applies_sha256", "eye_bag_applies_sha256", "collarbone_applies_sha256", "face_style_applies_sha256", "portrait_applies_sha256"].contains(&key.as_str()) {value[key] = expected.clone();}
        }
    }
}
struct Receipt { id: String, action: String, document: Option<String>, review: Option<ReviewBinding>, result: Option<Value>, bytes: usize, native_unknown: bool, late_terminal_workspace: Option<String>, body_review_digest: Option<String>, choice_source_catalog: Option<Value> }
impl Receipt {
    fn evictable(&self) -> bool {
        self.result.as_ref().is_some_and(|result| self.review.is_none() || result["outcome_unknown"] != true
            // Only explicitly classified head/collarbone preflight or paged
            // image reads may expire; an unknown commit remains guarded.
            || (matches!(self.action.as_str(), "skin_reference_choice" | "skin_reference_body_catalog" | "skin_reference_body_preview" | "skin_reference_body_image" | "skin_reference_match_catalog" | "skin_reference_match_preview" | "skin_reference_match_image" | "face_decoration_support_alias_preview" | "face_decoration_support_alias_image" | "face_decoration_alias_preview" | "face_decoration_alias_image" | "face_decoration_cohort_visual" | "preflight" | "face_decoration_visual" | "collarbone_visual" | "eye_bag_visual" | "eye_bag_cohort_visual" | "face_style_visual" | "portrait_cohort_visual" | "face_style_catalog" | "face_style_preview" | "face_style_image" | "eye_bag_source_image" | "eye_bag_reference" | "eye_bag_preview" | "eye_bag_image" | "face_decoration_reference" | "facial_sculpt_reference" | "eye_makeup_enhance_reference") && self.review.as_ref().is_some_and(|review| review.read_only)))
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
        self.begin_bound_command(epoch, command, command["document_id"].as_str())
    }
    /// Preserve a family-specific compound owner while retaining immutable
    /// command evidence through the same terminal ledger, not a second owner.
    pub fn begin_bound_command(&mut self, epoch: [u8; 16], command: &Value, bound: Option<&str>) -> Result<(), String> {
        if command["cmd"].as_str() != Some(K::NAME) { return Err("receipt command kind does not match its host".into()); }
        let id = command["request_id"].as_str().ok_or("missing receipt request ID")?;
        let action = command["action"].as_str().ok_or("missing receipt action")?;
        let review = ReviewBinding::from_command(epoch, command)?;
        // This operation requires its original accepted preview and both actual
        // image receipts. Reuse this ledger; no second token/plan store exists.
        let body_review_digest = self.capture_body_confirmation(command)?;
        let choice_source_catalog = self.capture_choice_source_catalog(command)?;
        let late_terminal_workspace = review.as_ref().and_then(|review|
            crate::project_recovery_fence::support_history_workspace(epoch, &review.fields)
                .or_else(|| crate::project_recovery_fence::decoration_preset_workspace(epoch, &review.fields)));
        self.begin_bound(epoch, id, action, bound)?;
        // begin_bound just appended this unique request, within the same lock.
        let record = self.records.back_mut().unwrap();
        record.bytes = review.as_ref().map_or(0, |binding| binding.bytes) + late_terminal_workspace.as_ref().map_or(0, |workspace| workspace.len())
            + body_review_digest.as_ref().map_or(0, String::len)
            + choice_source_catalog.as_ref().map_or(0, |value| value.to_string().len());
        record.review = review;
        record.late_terminal_workspace = late_terminal_workspace;
        record.body_review_digest = body_review_digest;
        record.choice_source_catalog = choice_source_catalog;
        self.trim_bytes();
        Ok(())
    }
    fn capture_body_confirmation(&self, command: &Value) -> Result<Option<String>, String> {
        if K::NAME != "people" || command["action"] != "skin_reference_body_confirm" { return Ok(None); }
        let previews: Vec<&Value> = self.records.iter().filter_map(|record| record.result.as_ref())
            .filter(|value| crate::people_api::skin_reference_body::confirmation_preview(command, value)).collect();
        if previews.len() != 1 { return Err("身体肤色审核已失效或已释放，请重新预览；未重发确认".into()); }
        let frozen = &previews[0]["payload"]["review"];
        if !["before", "after"].iter().all(|side| self.records.iter().filter_map(|record| record.result.as_ref())
            .any(|value| crate::people_api::skin_reference_body::confirmation_image(command, frozen, value, side))) {
            return Err("身体肤色审核需要保留同一预览的完整前后图像回执，请重新加载审核；未提交修改".into());
        }
        Ok(Some(crate::people_api::skin_reference_body::frozen_digest(frozen)))
    }
    /// The original family catalog remains the only source-image owner. Retain
    /// its bounded metadata here so ordinary ledger eviction cannot rebind a
    /// late suggestion to another family, generation or partial face census.
    fn capture_choice_source_catalog(&self, command: &Value) -> Result<Option<Value>, String> {
        if K::NAME != "people" || !crate::people_api::skin_reference_choice::action(command) { return Ok(None); }
        let mut captured: Option<Value> = None;
        for result in self.records.iter().filter_map(|record| record.result.as_ref()) {
            let Some(binding) = crate::people_api::skin_reference_choice::source_catalog_binding(command, result) else { continue; };
            if captured.as_ref().is_some_and(|previous| previous != &binding) {
                return Err("参照建议的原有照片审核来源不一致，请重新加载；未生成替代参照".into());
            }
            captured = Some(binding);
        }
        if captured.is_none() { return Err("请先加载并保留同一操作的当前照片审核来源，再请求只读参照建议".into()); }
        Ok(captured)
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
        self.records.push_back(Receipt { id: id.into(), action: action.into(), document: document.map(str::to_owned), review: None, result: None, bytes: 0, native_unknown: false, late_terminal_workspace: None, body_review_digest: None, choice_source_catalog: None });
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
        if value["action"].as_str() != Some(record.action.as_str()) { return; }
        if let Some(previous) = &record.result {
            // A read can outlive a transport failure. Reconcile only this exact
            // retained eye-bag read after its actual terminal arrives. Never
            // replace a known terminal or reopen confirmation/write authority.
            let read_reconciliation = K::NAME == "people" && previous["outcome_unknown"] == true
                && matches!(record.action.as_str(), "eye_bag_reference" | "eye_bag_preview" | "eye_bag_image" | "eye_bag_source_image")
                && record.review.as_ref().is_some_and(|review| review.read_only
                    && review.fields.get("eye_bag_request").is_some() && review.matches(value))
                && value["outcome_unknown"] == false && K::valid(value, record.document.as_deref())
                && value.to_string().len() <= MAX_RESULT_BYTES;
            // Only this family's exact captured reads may settle after a lost
            // read response. Confirm and clear never acquire replay authority.
            let skin_read_reconciliation = K::NAME == "people" && previous["outcome_unknown"] == true
                && matches!(record.action.as_str(), "skin_reference_match_catalog" | "skin_reference_match_preview" | "skin_reference_match_image")
                && record.review.as_ref().is_some_and(|review| review.read_only
                    && review.fields.get(crate::people_api::skin_reference_match::MARKER).is_some() && review.matches(value))
                && value["event"] == "people_result" && value["outcome_unknown"] == false
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            // Body reads share transport reconciliation, never face/body write authority.
            let body_read_reconciliation = K::NAME == "people" && previous["outcome_unknown"] == true
                && matches!(record.action.as_str(), "skin_reference_body_catalog" | "skin_reference_body_preview" | "skin_reference_body_image")
                && record.review.as_ref().is_some_and(|review| review.read_only
                    && review.fields.get(crate::people_api::skin_reference_body::MARKER).is_some() && review.matches(value))
                && value["event"] == "people_result" && value["outcome_unknown"] == false
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            let choice_read_reconciliation = K::NAME == "people" && previous["outcome_unknown"] == true
                && record.action == crate::people_api::skin_reference_choice::ACTION
                && record.review.as_ref().is_some_and(|review| review.read_only
                    && review.fields.get(crate::people_api::skin_reference_choice::MARKER).is_some() && review.matches(value))
                && value["event"] == "people_result" && value["outcome_unknown"] == false
                && record.choice_source_catalog.as_ref().is_some_and(|binding|
                    crate::people_api::skin_reference_choice::matches_source_catalog(binding, value))
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            // The dedicated support protocol may reconcile a locally synthesized
            // transport unknown with the original exact engine terminal.
            // An engine-issued unknown or any known terminal stays immutable.
            let bound_support_event = K::NAME == "people" && record.native_unknown && previous["outcome_unknown"] == true
                && value["event"] == "people_result"
                && matches!(record.action.as_str(), "face_decoration_support_alias_preview" | "face_decoration_support_alias_image" | "face_decoration_support_alias_confirm")
                && record.review.as_ref().is_some_and(|review| review.fields.get("face_decoration_support_alias_request").is_some() && review.matches(value))
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            // The support-bank history route uses its existing batch protocol,
            // but only a native-observed exact workspace + marker may reconcile.
            // Generic/scalar history, changed workspaces and rejected summaries
            // retain their existing immutable-unknown/reopen behavior.
            let bound_support_history_event = K::NAME == "batch" && record.native_unknown && previous["outcome_unknown"] == true
                && value["event"] == "batch_result" && matches!(record.action.as_str(), "undo" | "redo")
                && record.review.as_ref().is_some_and(|review|
                    review.fields.get(crate::people_api::decoration_support_alias::MARKER).is_some() && review.matches(value)
                    && record.late_terminal_workspace.as_ref().is_some_and(|workspace|
                        crate::project_recovery_fence::support_history_workspace(epoch, &review.fields).as_ref() == Some(workspace)))
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            // Only a transport-generated unknown may reconcile for decoration
            // mixed-preset apply/history. Capture and compare workspace without
            // changing ordinary preset/scalar/eye-bag terminal semantics.
            let bound_decoration_preset_event = record.native_unknown && previous["outcome_unknown"] == true
                && ((K::NAME == "preset" && record.action == "apply" && value["event"] == "preset_result")
                    || (K::NAME == "batch" && matches!(record.action.as_str(), "undo" | "redo") && value["event"] == "batch_result"))
                && record.review.as_ref().is_some_and(|review| review.matches(value)
                    && ((K::NAME == "preset" && review.fields[crate::preset_api::face_decoration::ACK].get("members").is_some())
                        || (K::NAME == "batch" && review.fields.get(crate::preset_api::face_decoration::ALIAS_MARKER).is_some()))
                    && record.late_terminal_workspace.as_ref().is_some_and(|workspace|
                        crate::project_recovery_fence::decoration_preset_workspace(epoch, &review.fields).as_ref() == Some(workspace)))
                && K::valid(value, record.document.as_deref()) && value.to_string().len() <= MAX_RESULT_BYTES;
            let support_reconciliation = (bound_support_event || bound_support_history_event || bound_decoration_preset_event) && value["outcome_unknown"] == false;
            let support_engine_unknown = (bound_support_event || bound_support_history_event || bound_decoration_preset_event) && value["outcome_unknown"] == true;
            if !read_reconciliation && !skin_read_reconciliation && !body_read_reconciliation && !choice_read_reconciliation && !support_reconciliation && !support_engine_unknown { return; }
            // An exact engine unknown replaces the transport diagnostic, not
            // its authority: it closes late-terminal reconciliation and stays fenced.
            if support_engine_unknown { record.native_unknown = false; }
        }
        let invalid = !K::valid(value, record.document.as_deref())
            || record.review.as_ref().is_some_and(|review| !review.matches(value))
            || record.choice_source_catalog.as_ref().is_some_and(|binding|
                !crate::people_api::skin_reference_choice::matches_source_catalog(binding, value))
            || (value["success"] == true && record.body_review_digest.as_ref().is_some_and(|expected|
                crate::people_api::skin_reference_body::frozen_digest(&value["payload"]["review"]) != *expected))
            || value.to_string().len() > MAX_RESULT_BYTES;
        let mut result = if invalid {
            Self::unknown(record, &format!("invalid or oversized {} receipt; inspect actual state", K::NAME))
        } else { value.clone() };
        if record.review.is_some() && result["outcome_unknown"] == true {
            // Unknown scalar mutation identities cannot be evicted. Keep read
            // diagnostics compact too, without pinning arbitrary large payloads.
            let error: String = result["error"].as_str().unwrap_or("Scalar outcome is unknown; inspect actual state")
                .chars().take(2000).collect();
            let mut compact = Self::unknown(record, &error);
            // `result` is either fully validated and request-bound above, or a
            // synthesized unknown with no engine publication claims. Preserve
            // only the dedicated bounded composite diagnostics in that result.
            if K::NAME == "preset" {
                if let Some(publication) = crate::preset_api::eye_bag::retained_alias_publication(&result) {
                    for (key, value) in publication.as_object().unwrap() { compact[key] = value.clone(); }
                }
                if let Some(publication) = crate::preset_api::face_decoration::retained_alias_publication(&result) {
                    for (key, value) in publication.as_object().unwrap() { compact[key] = value.clone(); }
                }
            }
            if K::NAME == "people" {
                if let Some(publication) = crate::people_api::decoration_support_alias::retained_publication(&result) {
                    for (key, value) in publication.as_object().unwrap() { compact[key] = value.clone(); }
                }
            }
            if K::NAME == "effect_recovery" {
                if let Some(publication) = crate::effect_recovery_host::alias::retained_publication(&result) {
                    for (key, value) in publication.as_object().unwrap() { compact[key] = value.clone(); }
                }
            }
            for key in ["requires_reload", "requires_readback", "publication_invalid", "rolled_back"] {
                if result[key].is_boolean() { compact[key] = result[key].clone(); }
            }
            if let Some(code) = result["error_code"].as_str() { compact["error_code"] = json!(code.chars().take(128).collect::<String>()); }
            result = compact;
        }
        record.native_unknown = result["outcome_unknown"] == true && record.native_unknown;
        record.bytes = result.to_string().len() + record.review.as_ref().map_or(0, |binding| binding.bytes)
            + record.late_terminal_workspace.as_ref().map_or(0, |workspace| workspace.len())
            + record.body_review_digest.as_ref().map_or(0, String::len)
            + record.choice_source_catalog.as_ref().map_or(0, |value| value.to_string().len());
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
        let value = self.records.iter_mut().find(|r| r.id == id).and_then(|record| {
            if record.result.is_some() { return None; }
            record.native_unknown = true;
            Some(Self::unknown(record, error))
        });
        if let Some(value) = value { self.receive(self.epoch, &value); }
    }
    pub fn ended(&mut self, epoch: [u8; 16]) {
        if self.epoch != epoch { return; }
        let ids: Vec<String> = self.records.iter().filter(|r| r.result.is_none()).map(|r| r.id.clone()).collect();
        for id in ids { self.failed(&id, &format!("engine ended before {} completion was confirmed", K::NAME)); }
        self.epoch = [0; 16]; self.supported = false;
    }
    /// Query retained read-only proof without changing or settling its receipt.
    /// The caller owns engine-epoch comparison, including an ended engine.
    pub fn read_review_binding(&self, id: &str) -> Option<Value> {
        self.records.iter().find(|r| r.id == id).and_then(|r| r.review.as_ref())
            .filter(|review| review.read_only).map(|review| review.fields.clone())
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

// AUTHORED / UNRUN: head inherits the bounded immutable receipt ledger.
#[cfg(test)]
#[path = "head_receipt_host_tests.rs"]
mod head_tests;
