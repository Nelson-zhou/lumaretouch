// SPDX-License-Identifier: GPL-3.0-or-later
//! Serializable execution ports. These are requests, never fabricated results.
//! Only the real import/preset/export owner may produce terminal receipts.
use serde::{Deserialize, Serialize};
use crate::schema::{bounded, digest, id, path_text, require, Result, MAX_FILE_BYTES};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InputOccurrence {
    pub occurrence_id: String,
    pub source_path: String,
    pub relative_path: String,
    pub source_sha256: String,
    pub size_bytes: u64,
    /// Full source stamp from polling (not an mtime-only id).
    pub source_stamp_sha256: String,
    /// Linux managed-import proof: dev, ino, size, mtime_ns, ctime_ns.
    /// Decimal strings avoid JavaScript integer precision loss.
    pub source_stat: [String; 5],
    pub completion: SourceCompletion,
}
impl InputOccurrence {
    pub fn validate(&self) -> Result<()> {
        require(digest(&self.occurrence_id) && digest(&self.source_sha256) && digest(&self.source_stamp_sha256), "invalid input occurrence/hash")?;
        require(self.source_stat[..3].iter().all(|s| !s.is_empty() && s.len() <= 20
            && s.bytes().all(|b| b.is_ascii_digit()) && s.parse::<u64>().is_ok())
            && self.source_stat[3..].iter().all(|s| s.len() <= 40 && s.parse::<i128>().is_ok()),
            "invalid stable source stat proof")?;
        require(crate::schema::fingerprint(&self.source_stat)? == self.source_stamp_sha256
            && self.source_stat[2] == self.size_bytes.to_string(), "source stat digest/size mismatch")?;
        require(path_text(&self.source_path) && bounded(&self.relative_path,4096)
            && !std::path::Path::new(&self.relative_path).is_absolute()
            && !std::path::Path::new(&self.relative_path).components().any(|p| !matches!(p,std::path::Component::Normal(_))),
            "input relative path must be safe, nonempty and within the source root")?;
        require(self.size_bytes > 0 && self.size_bytes <= MAX_FILE_BYTES, "source size exceeds the 2 GiB bound")?;
        require(self.occurrence_id == crate::schema::fingerprint(&(&self.source_path,&self.relative_path,
            &self.source_stat,&self.source_sha256))?, "input occurrence id is not bound to its path/stat/content proof")
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceCompletion { StableRead }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Identity {
    pub workflow_id: String,
    pub workflow_revision: u64,
    pub graph_sha256: String,
    pub run_id: String,
    pub input_occurrence_id: String,
    pub source_sha256: String,
    pub project_id: String,
    pub document_id: Option<String>,
    pub node_id: String,
    /// Content-derived operation key; queries carry the ORIGINAL key unchanged.
    pub operation_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SavedProjectGuard {
    pub project_id: String,
    pub project_path: String,
    pub project_revision: String,
    pub workspace_lease_id: String,
    pub saved_clean: bool,
    pub managed_import_receipt_count: u16,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ImportPreparation {
    pub preparation_id: String,
    pub source_sha256: String,
    pub guard: SavedProjectGuard,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DocumentState {
    pub project_id: String,
    pub document_id: String,
    pub document_revision: String,
    pub source_sha256: String,
    /// Owner readback/commit receipt for this exact retained document revision.
    pub receipt_id: String,
}
impl DocumentState {
    pub(crate) fn validate(&self) -> Result<()> {
        require(id(&self.project_id) && id(&self.document_id) && bounded(&self.document_revision,256)
            && digest(&self.source_sha256) && bounded(&self.receipt_id,256), "invalid document receipt identity")
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OwnerReviewReceipt {
    /// Opaque handle to a real retained review owned by the preset subsystem.
    /// An adapter MUST resolve this handle; a client-supplied ACK is insufficient.
    pub receipt_id: String,
    pub report_sha256: String,
    pub document_id: String,
    pub document_revision: String,
    pub preset_sha256: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PresetAssessment {
    pub report_id: String,
    pub report_sha256: String,
    pub document_revision: String,
    pub preset_sha256: String,
    pub requires_review: bool,
    pub review: Option<OwnerReviewReceipt>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FrozenExport {
    pub plan_id: String,
    pub plan_sha256: String,
    pub document_revision: String,
    pub output_root: String,
    pub recipe_sha256: String,
    /// Owner-frozen targets. Neither retry nor recovery may choose new names.
    pub targets: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutputReceipt { pub path: String, pub sha256: String, pub size_bytes: u64 }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum CommandKind {
    PrepareImport { input: InputOccurrence, project_path: String, managed_root: String },
    CommitImport { input: InputOccurrence, preparation: ImportPreparation },
    QueryImport { original_kind: String },
    PreflightPreset { document: DocumentState, preset_id: String, preset_sha256: String, labels: Vec<String> },
    ApplyPreset { document: DocumentState, preset_id: String, assessment: PresetAssessment },
    QueryPreset { original_kind: String },
    FreezeExport { document: DocumentState, output_root: String, recipe_sha256: String },
    StartExport { document: DocumentState, plan: FrozenExport },
    QueryExport { original_kind: String },
}
impl CommandKind {
    pub fn name(&self) -> &'static str {
        match self {
            Self::PrepareImport { .. } => "prepare_import", Self::CommitImport { .. } => "commit_import",
            Self::QueryImport { .. } => "query_import", Self::PreflightPreset { .. } => "preflight_preset",
            Self::ApplyPreset { .. } => "apply_preset", Self::QueryPreset { .. } => "query_preset",
            Self::FreezeExport { .. } => "freeze_export", Self::StartExport { .. } => "start_export",
            Self::QueryExport { .. } => "query_export",
        }
    }
    pub fn is_mutation(&self) -> bool {
        matches!(self, Self::CommitImport { .. } | Self::ApplyPreset { .. } | Self::StartExport { .. })
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Command { pub schema_version: u32, pub identity: Identity, pub operation: CommandKind }
impl Command {
    pub fn query(&self) -> Self {
        let original_kind = self.operation.name().to_string();
        let operation = match &self.operation {
            CommandKind::PrepareImport { .. } | CommandKind::CommitImport { .. } => CommandKind::QueryImport { original_kind },
            CommandKind::PreflightPreset { .. } | CommandKind::ApplyPreset { .. } => CommandKind::QueryPreset { original_kind },
            CommandKind::FreezeExport { .. } | CommandKind::StartExport { .. } => CommandKind::QueryExport { original_kind },
            _ => self.operation.clone(),
        };
        Self { schema_version: self.schema_version, identity: self.identity.clone(), operation }
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum ReceiptResult {
    Pending { owner_receipt_id: String },
    Unknown { reason: String },
    ImportPrepared { preparation: ImportPreparation },
    Imported { document: DocumentState, import_receipt_id: String },
    PresetPreflight { assessment: PresetAssessment },
    PresetApplied { document: DocumentState, preset_receipt_id: String },
    ExportFrozen { plan: FrozenExport },
    Exported { plan_id: String, export_receipt_id: String, outputs: Vec<OutputReceipt> },
    /// Only a definitive owner outcome belongs here. Lost transport/timeout,
    /// partial application without readback or unknown commit must use Unknown.
    Failed { code: String, message: String, retained_document: Option<DocumentState> },
    Cancelled { owner_receipt_id: String },
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    pub schema_version: u32,
    pub identity: Identity,
    pub result: ReceiptResult,
}
impl Receipt {
    /// Bound incoming transport bytes before deserialization. The scheduler
    /// still validates the phase, exact identity and result-specific proof.
    pub fn from_json(bytes: &[u8]) -> Result<Self> {
        require(bytes.len() <= 1024*1024, "owner receipt exceeds 1 MiB")?;
        Ok(serde_json::from_slice(bytes)?)
    }
}
