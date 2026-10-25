//! Pure receipt boundary. The core reducer independently verifies the same
//! operation when recording it; raw events never release project fences.
use lrt_local_workflow::ports::{Command, CommandKind, DocumentState, Receipt, ReceiptResult};
use std::{collections::BTreeSet, path::{Component, Path}};

fn text(value: &str, maximum: usize) -> bool { !value.is_empty() && value.len() <= maximum && !value.chars().any(char::is_control) }
fn digest(value: &str) -> bool { value.len() == 64 && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) }
fn document(value: &DocumentState, command: &Command) -> bool {
    value.project_id == command.identity.project_id && value.source_sha256 == command.identity.source_sha256
        && command.identity.document_id.as_ref() == Some(&value.document_id) && super::wire::identity(&value.document_id)
        && text(&value.document_revision, 256) && text(&value.receipt_id, 256)
}
pub fn terminal(receipt: &Receipt) -> bool {
    !matches!(receipt.result, ReceiptResult::Pending { .. } | ReceiptResult::Unknown { .. }
        | ReceiptResult::PresetPreflight { assessment: lrt_local_workflow::ports::PresetAssessment { requires_review: true, review: None, .. } })
}
pub fn valid(command: &Command, receipt: &Receipt) -> bool {
    if receipt.schema_version != 1 || receipt.identity != command.identity { return false; }
    match &receipt.result {
        ReceiptResult::Pending { owner_receipt_id } => text(owner_receipt_id, 256),
        ReceiptResult::Unknown { reason } => text(reason, 2048),
        ReceiptResult::Failed { code, message, retained_document } => text(code, 128) && text(message, 2048)
            && retained_document.as_ref().map_or(true, |value| document(value, command)),
        ReceiptResult::Cancelled { owner_receipt_id } => text(owner_receipt_id, 256),
        ReceiptResult::ExportFrozen { plan } => {
            let CommandKind::FreezeExport { document, output_root, recipe_sha256 } = &command.operation else { return false; };
            let mut unique = BTreeSet::new();
            text(&plan.plan_id, 256) && digest(&plan.plan_sha256) && plan.document_revision == document.document_revision
                && &plan.output_root == output_root && &plan.recipe_sha256 == recipe_sha256
                && !plan.targets.is_empty() && plan.targets.len() <= 64 && plan.targets.iter().all(|target| {
                    let path = Path::new(target);
                    text(target, 4096) && path.is_absolute() && path.starts_with(output_root) && path != Path::new(output_root)
                        && !path.components().any(|part| matches!(part, Component::CurDir | Component::ParentDir)) && unique.insert(target)
                })
        }
        ReceiptResult::Exported { plan_id, export_receipt_id, outputs } => {
            let CommandKind::StartExport { plan, .. } = &command.operation else { return false; };
            let mut unique = BTreeSet::new();
            plan_id == &plan.plan_id && text(export_receipt_id, 256) && outputs.len() == plan.targets.len()
                && outputs.iter().all(|output| plan.targets.contains(&output.path) && unique.insert(&output.path)
                    && digest(&output.sha256) && output.size_bytes > 0)
        }
        ReceiptResult::PresetPreflight { assessment } => {
            let CommandKind::PreflightPreset { document, preset_sha256, .. } = &command.operation else { return false; };
            text(&assessment.report_id, 256) && digest(&assessment.report_sha256) && &assessment.preset_sha256 == preset_sha256
                && assessment.document_revision == document.document_revision && assessment.review.as_ref().map_or(true, |review|
                    text(&review.receipt_id, 256) && review.report_sha256 == assessment.report_sha256
                        && review.document_id == document.document_id && review.document_revision == document.document_revision
                        && review.preset_sha256 == assessment.preset_sha256)
        }
        ReceiptResult::PresetApplied { document: value, preset_receipt_id } => matches!(command.operation, CommandKind::ApplyPreset { .. })
            && document(value, command) && text(preset_receipt_id, 256),
        _ => false, // Import outcomes belong exclusively to ingest_session_api.
    }
}
