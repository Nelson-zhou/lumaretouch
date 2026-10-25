//! Map only actual validated ingestion-owner evidence to core receipts.
//! No file copy, source timestamp reinterpretation, project switching or save.
use lrt_local_workflow::ports::{Command, CommandKind, DocumentState, ImportPreparation, Receipt, ReceiptResult, SavedProjectGuard};
use serde_json::{json, Value};
use super::{data::{Lease, Operation}, storage};

pub fn envelope(lease: &Lease, command: &Command) -> Result<Value, String> {
    let request_id = storage::uuid()?;
    match &command.operation {
        CommandKind::PrepareImport { .. } => Ok(json!({"cmd":"ingest_session","action":"state","request_id":request_id})),
        CommandKind::CommitImport { input, preparation } => {
            input.validate().map_err(|error| error.to_string())?;
            // Engine protocol one accepts canonical unsigned decimal stat
            // strings. An older/pre-epoch source is rejected, never rewritten.
            if !input.source_stat.iter().all(|part| !part.is_empty() && part.len() <= 20
                && part.bytes().all(|byte| byte.is_ascii_digit()) && (part == "0" || !part.starts_with('0')))
                || preparation.guard.workspace_lease_id != lease.lease_id
                || preparation.guard.project_id != command.identity.project_id
                || preparation.source_sha256 != input.source_sha256 {
                return Err("来源时间戳或原导入准备证据与真实接入协议不兼容；没有导入".into());
            }
            // Managed root comes from the journaled prepare operation in the
            // caller, not from an arbitrary renderer-supplied command here.
            Ok(json!({"cmd":"ingest_session","action":"import","request_id":request_id,"session_id":lease.lease_id,
                "paths":[input.source_path],"root":Value::Null,"completed_sources":[{
                    "path":input.source_path,"sha256":input.source_sha256,"size":input.size_bytes,
                    "stat":input.source_stat,"occurrence_id":input.occurrence_id,"completion":"stable_read"}]}))
        }
        _ => Err("不是导入 owner 命令".into()),
    }
}
pub fn query(lease: &Lease, original: &Value) -> Result<Value, String> {
    let original_id = original["request_id"].as_str().ok_or("原始导入请求丢失")?;
    let operation_id = crate::ingest_receipt_validation::operation_id(&lease.lease_id, original_id)?;
    Ok(json!({"cmd":"ingest_session","action":"query","request_id":storage::uuid()?,
        "session_id":lease.lease_id,"operation_id":operation_id}))
}
pub fn map(operation: &Operation, lease: &mut Lease, envelope: &Value) -> Result<Receipt, String> {
    let command = &operation.command;
    let unknown = |reason: String| ReceiptResult::Unknown { reason };
    let result = if envelope["phase"] == "unknown" {
        unknown("原引擎代际或回执已不可用；禁止重放导入".into())
    } else if envelope["result"].is_null() {
        ReceiptResult::Pending { owner_receipt_id: operation.request["request_id"].as_str().ok_or("缺少原请求身份")?.into() }
    } else {
        let event = &envelope["result"];
        let session = &event["session"];
        match &command.operation {
            CommandKind::PrepareImport { input, project_path, .. } => {
                if event["status"] != "readback" || event["request_id"] != operation.request["request_id"]
                    || event["action"] != "state" || session["session_id"] != lease.lease_id
                    || session["owner"] != "workflow" || session["requires_readback"] != false
                    || !session["operation_id"].is_null() || session["phase"] != "armed"
                    || session["binding"]["project_id"] != command.identity.project_id
                    || session["binding"]["path"] != *project_path
                    || session["binding"]["workspace"] != lease.binding["workspace"]
                    || !event["state"]["reason"].is_null() {
                    unknown("接入 owner 未确认同一已保存工程、空闲租约及剩余容量".into())
                } else {
                    let capacity = event["state"]["receipt_capacity"].as_u64().filter(|value| (1..=256).contains(value)).ok_or("接入容量缺失")?;
                    let revision = session["binding"]["disk_sha256"].as_str().ok_or("缺少已保存工程指纹")?.to_owned();
                    lease.binding = session["binding"].clone();
                    ReceiptResult::ImportPrepared { preparation: ImportPreparation {
                        preparation_id: operation.request["request_id"].as_str().unwrap().into(), source_sha256: input.source_sha256.clone(),
                        guard: SavedProjectGuard { project_id: command.identity.project_id.clone(), project_path: project_path.clone(),
                            project_revision: revision, workspace_lease_id: lease.lease_id.clone(), saved_clean: true,
                            managed_import_receipt_count: (256 - capacity) as u16 },
                    } }
                }
            }
            CommandKind::CommitImport { input, .. } => {
                let owner = &event["operation"];
                let request_id = operation.request["request_id"].as_str().ok_or("原始导入身份缺失")?;
                let operation_id = crate::ingest_receipt_validation::operation_id(&lease.lease_id, request_id)?;
                if owner["operation_id"] != operation_id || owner["request_id"] != request_id
                    || session["session_id"] != lease.lease_id || session["owner"] != "workflow"
                    || session["binding"]["project_id"] != command.identity.project_id
                    || session["binding"]["workspace"] != lease.binding["workspace"] {
                    unknown("接入回执与原请求、会话或工程不匹配；保持原操作待核对".into())
                } else { match owner["status"].as_str() {
                    Some("pending") => ReceiptResult::Pending { owner_receipt_id: operation_id },
                    Some("succeeded") => {
                        let documents = owner["documents"].as_array().filter(|rows| rows.len() == 1).ok_or("导入回执缺少唯一文档")?;
                        let doc = &documents[0];
                        if doc["occurrence_id"] != input.occurrence_id || doc["source_sha256"] != input.source_sha256
                            || doc["original_path"] != input.source_path || doc["size"] != input.size_bytes
                            || doc["stat"] != json!(input.source_stat) || doc["completion"] != "stable_read"
                            || doc["import_receipt_id"] != operation_id || session["requires_readback"] != false
                            || !session["operation_id"].is_null() {
                            return Err("成功回执缺少精确来源及已提交文档证据".into());
                        }
                        lease.binding = session["binding"].clone();
                        ReceiptResult::Imported { document: DocumentState {
                            project_id: command.identity.project_id.clone(),
                            document_id: doc["document_id"].as_str().ok_or("缺少已提交文档身份")?.into(),
                            document_revision: doc["revision"].as_str().ok_or("缺少已提交文档修订")?.into(),
                            source_sha256: input.source_sha256.clone(), receipt_id: operation_id.clone(),
                        }, import_receipt_id: operation_id }
                    }
                    Some("failed") if session["requires_readback"] == false && session["operation_id"].is_null() => ReceiptResult::Failed {
                        code: "managed_import_failed".into(), message: owner["receipt"]["error"].as_str().unwrap_or("导入 owner 已确认失败；未重试").chars().take(1024).collect(), retained_document: None },
                    Some("cancelled") if session["requires_readback"] == false && session["operation_id"].is_null() => ReceiptResult::Cancelled { owner_receipt_id: operation_id },
                    _ => unknown("原始导入结果未知，等待 owner 精确回读；不重发".into()),
                } }
            }
            _ => return Err("不是原始导入阶段".into()),
        }
    };
    Ok(Receipt { schema_version: 1, identity: command.identity.clone(), result })
}
