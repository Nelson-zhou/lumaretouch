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
