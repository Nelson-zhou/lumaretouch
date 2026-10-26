//! AUTHORED / UNRUN. Static acceptance fixtures only; no command in this change
//! compiles or executes these tests, invokes product imports, or touches photos.
use super::{validation, wire};
use lrt_local_workflow::ports::{Command, CommandKind, DocumentState, FrozenExport, Identity, OutputReceipt, Receipt, ReceiptResult};
use serde_json::json;

fn identity() -> Identity {
    Identity { workflow_id: "workflow-fixture".into(), workflow_revision: 1, graph_sha256: "a".repeat(64),
        run_id: "run-fixture".into(), input_occurrence_id: "b".repeat(64), source_sha256: "c".repeat(64),
        project_id: "project-fixture".into(), document_id: Some("document-fixture".into()),
        node_id: "export".into(), operation_id: "d".repeat(64) }
}
fn document() -> DocumentState {
    DocumentState { project_id: "project-fixture".into(), document_id: "document-fixture".into(),
        document_revision: "1".into(), source_sha256: "c".repeat(64),
        receipt_id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8".into() }
}
fn plan() -> FrozenExport {
    FrozenExport { plan_id: "plan-fixture".into(), plan_sha256: "e".repeat(64),
        document_revision: "1".into(), output_root: "/fixture/output".into(),
        recipe_sha256: "f".repeat(64), targets: vec!["/fixture/output/photo.jpg".into()] }
}
fn exported() -> (Command, Receipt) {
    let command = Command { schema_version: 1, identity: identity(), operation: CommandKind::StartExport { document: document(), plan: plan() } };
    let receipt = Receipt { schema_version: 1, identity: command.identity.clone(), result: ReceiptResult::Exported {
        plan_id: "plan-fixture".into(), export_receipt_id: "actual-owner-task".into(), outputs: vec![OutputReceipt {
            path: "/fixture/output/photo.jpg".into(), sha256: "1".repeat(64), size_bytes: 1024 }] } };
    (command, receipt)
}
#[test]
fn request_schema_rejects_extra_authority_and_versions() {
    assert!(wire::Request::parse(json!({"port_version":2,"request_id":"r","command":{"kind":"stop","run_id":"run"}})).is_err());
    assert!(wire::Request::parse(json!({"port_version":1,"request_id":"r","command":{"kind":"stop","run_id":"run"},"approved":true})).is_err());
    assert!(wire::Request::parse(json!({"port_version":1,"request_id":"r","command":{"kind":"open_review","run_id":"run","review_id":"review","ack":true}})).is_err());
}
#[test]
fn explicit_release_is_a_distinct_identity_bound_action() {
    let request = wire::Request::parse(json!({"port_version":1,"request_id":"release-one","command":{"kind":"release_project_lease","lease_id":"lease-one"}})).unwrap();
    assert_eq!(request.command.name(), "release_project_lease");
    assert_eq!(request.receipt("pending", "owner pending")["command_kind"], "release_project_lease");
}
#[test]
fn unknown_and_pending_are_not_effect_settlement() {
    let (command, mut receipt) = exported();
    receipt.result = ReceiptResult::Unknown { reason: "engine restarted".into() };
    assert!(validation::valid(&command, &receipt)); assert!(!validation::terminal(&receipt));
    receipt.result = ReceiptResult::Pending { owner_receipt_id: "original-task".into() };
    assert!(validation::valid(&command, &receipt)); assert!(!validation::terminal(&receipt));
}
#[test]
fn full_original_identity_is_required_not_only_operation_hash() {
    let (command, mut receipt) = exported();
    assert!(validation::valid(&command, &receipt));
    receipt.identity.run_id = "another-run".into();
    assert!(!validation::valid(&command, &receipt));
}
#[test]
fn successful_export_requires_exact_targets_bytes_hashes_and_plan() {
    let (command, mut receipt) = exported();
    if let ReceiptResult::Exported { outputs, .. } = &mut receipt.result { outputs[0].path = "/fixture/output/renamed.jpg".into(); }
    assert!(!validation::valid(&command, &receipt));
    let (_, mut receipt) = exported();
    if let ReceiptResult::Exported { outputs, .. } = &mut receipt.result { outputs[0].size_bytes = 0; }
    assert!(!validation::valid(&command, &receipt));
    let (_, mut receipt) = exported();
    if let ReceiptResult::Exported { plan_id, .. } = &mut receipt.result { *plan_id = "different-plan".into(); }
    assert!(!validation::valid(&command, &receipt));
}
#[test]
fn freeze_cannot_escape_pinned_root_or_repeat_target() {
    let command = Command { schema_version: 1, identity: identity(), operation: CommandKind::FreezeExport {
        document: document(), output_root: "/fixture/output".into(), recipe_sha256: "f".repeat(64) } };
    let mut receipt = Receipt { schema_version: 1, identity: command.identity.clone(), result: ReceiptResult::ExportFrozen { plan: plan() } };
    assert!(validation::valid(&command, &receipt));
    if let ReceiptResult::ExportFrozen { plan } = &mut receipt.result { plan.targets.push(plan.targets[0].clone()); }
    assert!(!validation::valid(&command, &receipt));
    if let ReceiptResult::ExportFrozen { plan } = &mut receipt.result { plan.targets = vec!["/fixture/output/../original.jpg".into()]; }
    assert!(!validation::valid(&command, &receipt));
}
#[test]
fn owner_receipt_from_wrong_phase_does_not_settle_export() {
    let (command, mut receipt) = exported();
    receipt.result = ReceiptResult::PresetApplied { document: document(), preset_receipt_id: "not-an-export".into() };
    assert!(!validation::valid(&command, &receipt));
}

#[test]
fn review_steps_are_distinct_durable_requests_and_never_read_only() {
    let request = wire::Request::parse(json!({"port_version":1,"request_id":"open-one","command":{
        "kind":"review_step","run_id":"run-fixture","operation_id":"d".repeat(64),"step":"open_target","payload":{}}})).unwrap();
    assert_eq!(request.command.name(), "review_step");
    assert!(!super::transport::read_only(&json!({"cmd":"workflow_owner","action":"review_step"})));
    assert!(super::transport::read_only(&json!({"cmd":"workflow_owner","action":"review_image"})));
    assert!(super::transport::read_only(&json!({"cmd":"workflow_owner","action":"open_review"})));
}
#[test]
fn exact_handoff_binds_command_and_stops_unknown_actions() {
    let command = Command {schema_version:1, identity:identity(), operation:CommandKind::PreflightPreset {
        document:document(), preset_id:"warm".into(), preset_sha256:"f".repeat(64), labels:vec![]}};
    let mut handoff = json!({"version":1,"operation_id":"d".repeat(64),"document_id":"document-fixture",
        "preset_id":"warm","preset_sha256":"f".repeat(64),"phase":"awaiting_open","review":null,"message":"Open the exact target explicitly"});
    assert!(super::review::handoff(&handoff, &command));
    assert!(super::review::step_allowed(&handoff, "open_target", &json!({})));
    assert!(super::review::step_allowed(&handoff, "return_target", &json!({})));
    assert!(!super::review::step_allowed(&handoff, "approve", &json!({"accepted":true})));
    assert!(!super::review::step_allowed(&handoff, "open_target", &json!({"auto_ack":true})));
    handoff["phase"] = json!("awaiting_preparation");
    assert!(super::review::handoff(&handoff, &command));
    assert!(super::review::step_allowed(&handoff, "prepare_skin", &json!({})));
    assert!(super::review::step_allowed(&handoff, "return_target", &json!({})));
    assert!(!super::review::step_allowed(&handoff, "prepare_skin", &json!({"backend":"auto"})));
    assert!(!super::review::step_allowed(&handoff, "approve", &json!({"accepted":true})));
    handoff["phase"] = json!("unknown");
    for step in ["open_target", "prepare_skin", "approve", "save_project", "return_target"] {
        assert!(!super::review::step_allowed(&handoff, step, &json!({})));
    }
    handoff["document_id"] = json!("different-document");
    assert!(!super::review::handoff(&handoff, &command));
}
#[test]
fn preset_review_required_receipt_remains_nonterminal_until_owner_approval() {
    use lrt_local_workflow::ports::PresetAssessment;
    let receipt = Receipt {schema_version:1, identity:identity(), result:ReceiptResult::PresetPreflight {assessment:PresetAssessment {
        report_id:"review".into(), report_sha256:"a".repeat(64), document_revision:"1".into(), preset_sha256:"b".repeat(64), requires_review:true, review:None}}};
    assert!(!validation::terminal(&receipt));
}

// Authored UNRUN: wire admission only, not evidence of inference/render/quality.
fn scalar_review_fixture() -> serde_json::Value {
    let hash = "a".repeat(64);
    let image = json!({"mime":"image/png","width":1,"height":1,"sha256":hash,
        "byte_length":33,"page_count":1});
    json!({"schema":"lrt.workflow-preset-review.v1","review_id":"review-fixture",
        "target":{"document_id":"target","load_id":"load","revision":"1"},
        "preset_id":"skin-color","preset_sha256":hash,
        "module_ids":["lnx.skin.v1","lnx.exposure.v1","lnx.white_balance.v1"],
        "before":image,"after":image,"source_proof":{},"source_size":[1,1],"output_size":[1,1],
        "before_state_sha256":hash,"candidate_state_sha256":hash,"people_sha256":hash,
        "repair_sha256":hash,"before_render_sha256":hash,"candidate_render_sha256":hash,
        "page_bytes":65536,"ttl_seconds":900,"approval_only":true,"runtime_verified":false,
        "review_sha256":hash})
}

#[test]
fn native_review_accepts_exact_skin_color_scope_but_no_duplicates_or_extra_modules() {
    let mut review = scalar_review_fixture();
    assert!(super::review::report(&review));
    review["module_ids"] = json!(["lnx.skin.v1"]);
    assert!(super::review::report(&review));
    for ids in [json!([]), json!(["lnx.skin.v1", "lnx.skin.v1"]),
        json!(["lnx.skin.v1", "lnx.exposure.v1", "lnx.skin.v1"]),
        json!(["lnx.skin.v1", "lnx.blemish.v1"]),
        json!(["lnx.skin.v1", "lnx.exposure.v1", "lnx.white_balance.v1", "lnx.unknown.v1"])] {
        review["module_ids"] = ids;
        assert!(!super::review::report(&review));
    }
    review = scalar_review_fixture();
    review["runtime_verified"] = json!(true);
    assert!(!super::review::report(&review));
}

#[test]
fn automatic_start_ack_is_not_reusable_definition_authority() {
    let digest = "a".repeat(64);
    let mut ack = wire::AutomaticStartAck { schema: "lrt.automatic-batch-start.v1".into(), graph_sha256: digest.clone(), accepted: true };
    assert!(ack.matches(&digest));
    assert!(!ack.matches(&"b".repeat(64)));
    ack.accepted = false; assert!(!ack.matches(&digest));
    assert!(serde_json::from_value::<wire::AutomaticStartAck>(json!({"schema":"lrt.automatic-batch-start.v1",
        "graph_sha256":digest,"accepted":true,"viewed_images":true})).is_err());
}
#[test]
fn automatic_handoff_never_accepts_review_steps_or_image_ack() {
    let command = Command { schema_version:1, identity:identity(), operation:CommandKind::PreflightPreset {
        document:document(), preset_id:"preset-one".into(), preset_sha256:"a".repeat(64), labels:vec![] } };
    let mut handoff = json!({"version":1,"mode":"automatic","operation_id":command.identity.operation_id,
        "document_id":"document-fixture","preset_id":"preset-one","preset_sha256":"a".repeat(64),
        "phase":"authorized","review":null,"message":"Frozen automatic intent, no human review"});
    assert!(super::review::handoff(&handoff, &command));
    for step in ["open_target","prepare_skin","approve","save_project","return_target"] {
        assert!(!super::review::step_allowed(&handoff, step, &json!({})));
    }
    handoff["review"] = json!({"accepted":true});
    assert!(!super::review::handoff(&handoff, &command));
}

// AUTHORED / UNRUN: archive selection cannot dispatch edits or mint Start consent.
#[test]
fn semantic_archive_readback_is_exact_and_read_only() {
    use sha2::{Digest, Sha256};
    let intent = json!({"reference":{"asset_id":"b".repeat(64),"render_sha256":"c".repeat(64),
        "source":{"sha256":"d".repeat(64)}}}).to_string();
    let hash: String = Sha256::digest(intent.as_bytes()).iter().map(|byte| format!("{byte:02x}")).collect();
    let value = json!({"path":"/fixture/reference.lrtcolour","file_bytes":8192,"file_sha256":"e".repeat(64),
        "intent_sha256":hash,"portable_intent_json":intent});
    assert!(super::archive::checked(&value, "/fixture/reference.lrtcolour").is_ok());
    assert!(super::archive::checked(&value, "/fixture/other.lrtcolour").is_err());
    let mut changed = value; changed["reviewed"] = json!(true);
    assert!(super::archive::checked(&changed, "/fixture/reference.lrtcolour").is_err());
    assert!(super::transport::read_only(&json!({"cmd":"workflow_owner","action":"semantic_archive"})));
    assert!(!super::transport::read_only(&json!({"cmd":"workflow_owner","action":"execute"})));
}
