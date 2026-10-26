// SPDX-License-Identifier: GPL-3.0-or-later
use serde::{Deserialize, Serialize};
use std::path::Path;
use crate::{ports::*, schema::{bounded, digest, fingerprint, id, require, ErrorPolicy,
    NodeKind, Result, ValidatedGraph, MAX_JOBS, SCHEMA_VERSION}};

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Stage { PrepareImport, CommitImport, PreflightPreset, ApplyPreset, FreezeExport, StartExport, Done, Skipped, Failed }
impl Stage { pub fn terminal(&self) -> bool { matches!(self, Self::Done | Self::Skipped | Self::Failed) } }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "reason", rename_all = "snake_case", deny_unknown_fields)]
pub enum PauseReason {
    UncertainOutcome { operation_id: String, detail: String },
    ReviewRequired { operation_id: String, report_id: String, report_sha256: String },
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum RunStatus { Running, Paused { detail: PauseReason }, Stopped, Complete }

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Job {
    pub input: InputOccurrence,
    pub stage: Stage,
    pub labels: Vec<String>,
    pub document: Option<DocumentState>,
    pub import_preparation: Option<ImportPreparation>,
    pub preset_assessment: Option<PresetAssessment>,
    pub export_plan: Option<FrozenExport>,
    pub preset_condition_matched: bool,
    pub receipts: Vec<Receipt>,
    pub warning: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "event", rename_all = "snake_case", deny_unknown_fields)]
pub enum Event {
    Admit { input: InputOccurrence },
    Seal,
    Intent { command: Command },
    Receipt { receipt: Receipt },
    Stop,
    Resume,
    SourceCheckpoint { checkpoint: String },
}

/// Pure bounded state machine. Use DurableRunner for real dispatch, not reduce
/// followed by an unjournaled side effect. Neither this type nor deserialization
/// grants authorization to the adapters or certifies a review.
#[derive(Clone, Debug)]
pub struct Scheduler {
    pub(crate) graph: ValidatedGraph,
    pub(crate) run_id: String,
    pub(crate) jobs: Vec<Job>,
    pub(crate) pending: Option<Command>,
    pub(crate) last_reply: Option<Receipt>,
    pub(crate) pause: Option<PauseReason>,
    pub(crate) stopped: bool,
    pub(crate) sealed: bool,
    pub(crate) source_checkpoint: Option<String>,
}

impl Scheduler {
    pub fn new(graph: ValidatedGraph, run_id: String) -> Result<Self> {
        require(id(&run_id), "invalid run id")?;
        Ok(Self { graph, run_id, jobs: Vec::new(), pending: None, last_reply: None,
            pause: None, stopped: false, sealed: false, source_checkpoint: None })
    }
    pub fn graph(&self) -> &ValidatedGraph { &self.graph }
    pub fn run_id(&self) -> &str { &self.run_id }
    pub fn jobs(&self) -> &[Job] { &self.jobs }
    pub fn pending(&self) -> Option<&Command> { self.pending.as_ref() }
    pub fn is_sealed(&self) -> bool { self.sealed }
    /// Reporting only: count the durable frozen path list, not just admitted
    /// jobs. Missing capture evidence stays None rather than claiming zero.
    pub fn captured_input_count(&self) -> Option<usize> {
        if !self.graph.automatic() { return None; }
        let source: crate::poll::DirectoryPoller = serde_json::from_str(self.source_checkpoint.as_deref()?).ok()?;
        if source.graph_digest() != self.graph.digest() { return None; }
        source.captured_count()
    }
    pub fn status(&self) -> RunStatus {
        if self.stopped { RunStatus::Stopped }
        else if let Some(detail) = &self.pause { RunStatus::Paused { detail: detail.clone() } }
        else if self.sealed && self.pending.is_none() && self.jobs.iter().all(|j| j.stage.terminal()) { RunStatus::Complete }
        else { RunStatus::Running }
    }
    pub fn knows_occurrence(&self, input: &InputOccurrence) -> Result<bool> {
        match self.jobs.iter().find(|job| job.input.occurrence_id == input.occurrence_id) {
            Some(job) => { require(&job.input == input, "same occurrence id was reused for different source proof")?; Ok(true) }
            None => Ok(false),
        }
    }
    /// Pending intent means QUERY, including immediately after a restart. Never
    /// return the mutation a second time based on timeout, missing or unknown.
    pub fn next_command(&self) -> Result<Option<Command>> {
        if let Some(command) = &self.pending { return Ok(Some(command.query())); }
        if self.stopped || self.pause.is_some() { return Ok(None); }
        let Some(job) = self.jobs.iter().find(|j| !j.stage.terminal()) else { return Ok(None); };
        self.plan(job).map(Some)
    }
    fn plan(&self, job: &Job) -> Result<Command> {
        let (node, operation) = match job.stage {
            Stage::PrepareImport => {
                let NodeKind::ManagedImport { project_path, managed_root, .. } = &self.graph.import().operation else { unreachable!() };
                (self.graph.import(), CommandKind::PrepareImport { input: job.input.clone(), project_path: project_path.clone(), managed_root: managed_root.clone() })
            }
            Stage::CommitImport => (self.graph.import(), CommandKind::CommitImport {
                input: job.input.clone(), preparation: job.import_preparation.clone().expect("validated stage") }),
            Stage::PreflightPreset => {
                let node = self.graph.preset().expect("selected preset");
                let (NodeKind::CompatiblePreset { preset_id,preset_sha256,.. } | NodeKind::AutomaticPreset { preset_id,preset_sha256,.. }) = &node.operation else { unreachable!() };
                (node, CommandKind::PreflightPreset { document: job.document.clone().expect("imported document"),
                    preset_id: preset_id.clone(), preset_sha256: preset_sha256.clone(), labels: job.labels.clone() })
            }
            Stage::ApplyPreset => {
                let node = self.graph.preset().expect("selected preset");
                let (NodeKind::CompatiblePreset { preset_id,.. } | NodeKind::AutomaticPreset { preset_id,.. }) = &node.operation else { unreachable!() };
                (node, CommandKind::ApplyPreset { document: job.document.clone().expect("imported document"),
                    preset_id: preset_id.clone(), assessment: job.preset_assessment.clone().expect("preflight assessment") })
            }
            Stage::FreezeExport => {
                let NodeKind::Export { output_root,recipe_sha256 } = &self.graph.export().operation else { unreachable!() };
                (self.graph.export(), CommandKind::FreezeExport { document: job.document.clone().expect("imported document"),
                    output_root: output_root.clone(), recipe_sha256: recipe_sha256.clone() })
            }
            Stage::StartExport => (self.graph.export(), CommandKind::StartExport {
                document: job.document.clone().expect("imported document"), plan: job.export_plan.clone().expect("frozen plan") }),
            _ => unreachable!("only nonterminal jobs are planned"),
        };
        let mut identity = Identity { workflow_id: self.graph.graph.workflow_id.clone(),
            workflow_revision: self.graph.graph.revision, graph_sha256: self.graph.sha256.clone(),
            run_id: self.run_id.clone(), input_occurrence_id: job.input.occurrence_id.clone(),
            source_sha256: job.input.source_sha256.clone(), project_id: self.graph.project_id().into(),
            document_id: job.document.as_ref().map(|d| d.document_id.clone()), node_id: node.id.clone(), operation_id: String::new() };
        identity.operation_id = fingerprint(&(&identity, &operation))?;
        Ok(Command { schema_version: SCHEMA_VERSION, identity, operation })
    }
    /// Error-atomic: a rejected event leaves the state unchanged.
    pub fn reduce(&mut self, event: &Event) -> Result<()> {
        let mut staged = self.clone();
        staged.apply(event)?;
        *self = staged;
        Ok(())
    }
    fn apply(&mut self, event: &Event) -> Result<()> {
        match event {
            Event::Admit { input } => {
                input.validate()?;
                if self.knows_occurrence(input)? { return Ok(()); }
                require(!self.sealed && !self.stopped && self.pause.is_none(), "run is not accepting new photos")?;
                require(self.jobs.len() < MAX_JOBS, "job ledger is full; retained identities must not be evicted")?;
                let NodeKind::DirectorySource { root, .. } = &self.graph.source().operation else { unreachable!() };
                require(Path::new(root).join(&input.relative_path) == Path::new(&input.source_path), "source path is outside the pinned root/relative occurrence")?;
                let labels = self.graph.labels_for(&input.relative_path);
                let preset_condition_matched = self.graph.preset().map(|node| {
                    let (NodeKind::CompatiblePreset { when_all_labels, .. } | NodeKind::AutomaticPreset { when_all_labels, .. }) = &node.operation else { unreachable!() };
                    when_all_labels.iter().all(|label| labels.contains(label))
                }).unwrap_or(false);
                self.jobs.push(Job { input: input.clone(), stage: Stage::PrepareImport, labels, document: None,
                    import_preparation: None, preset_assessment: None, export_plan: None,
                    preset_condition_matched, receipts: Vec::new(), warning: None });
            }
            Event::Seal => self.sealed = true,
            Event::SourceCheckpoint { checkpoint } => {
                require(checkpoint.len() <= 1024*1024, "source checkpoint exceeds 1 MiB")?;
                self.source_checkpoint = Some(checkpoint.clone());
            }
            Event::Stop => self.stopped = true,
            Event::Resume => { require(self.stopped, "run is not stopped")?; self.stopped = false; }
            Event::Intent { command } => {
                require(self.pending.is_none(), "an unresolved intent already exists")?;
                require(self.next_command()?.as_ref() == Some(command), "intent differs from exact next operation")?;
                self.pending = Some(command.clone());
                self.last_reply = None;
            }
            Event::Receipt { receipt } => self.accept_receipt(receipt)?,
        }
        Ok(())
    }
    fn accept_receipt(&mut self, receipt: &Receipt) -> Result<()> {
        if self.last_reply.as_ref() == Some(receipt) { return Ok(()); }
        let command = self.pending.clone().ok_or_else(|| crate::schema::WorkflowError("no pending operation for this receipt".into()))?;
        require(receipt.schema_version == SCHEMA_VERSION && receipt.identity == command.identity,
            "receipt is stale or belongs to another workflow/input/project/document/node/operation")?;
        let index = self.jobs.iter().position(|j| j.input.occurrence_id == command.identity.input_occurrence_id).expect("pending job");
        match &receipt.result {
            ReceiptResult::Pending { owner_receipt_id } => {
                require(bounded(owner_receipt_id,256), "invalid pending owner receipt")?;
                self.last_reply = Some(receipt.clone());
                return Ok(());
            }
            ReceiptResult::Unknown { reason } => {
                require(bounded(reason,2048), "invalid uncertain-outcome reason")?;
                self.pause = Some(PauseReason::UncertainOutcome { operation_id: command.identity.operation_id.clone(), detail: reason.clone() });
                self.last_reply = Some(receipt.clone());
                return Ok(());
            }
            ReceiptResult::ImportPrepared { preparation } => {
                require(matches!(command.operation, CommandKind::PrepareImport { .. }), "wrong import preparation phase")?;
                let NodeKind::ManagedImport { project_path, .. } = &self.graph.import().operation else { unreachable!() };
                let guard = &preparation.guard;
                require(bounded(&preparation.preparation_id,256) && preparation.source_sha256 == command.identity.source_sha256
                    && guard.project_id == command.identity.project_id && &guard.project_path == project_path
                    && bounded(&guard.project_revision,256) && bounded(&guard.workspace_lease_id,256)
                    && guard.saved_clean && guard.managed_import_receipt_count < 256,
                    "managed import requires a clean saved project, exact source proof, owned lease and receipt capacity")?;
                self.jobs[index].import_preparation = Some(preparation.clone());
                self.jobs[index].stage = Stage::CommitImport;
            }
            ReceiptResult::Imported { document, import_receipt_id } => {
                require(matches!(command.operation, CommandKind::CommitImport { .. }), "wrong import commit phase")?;
                validate_document(document,&command.identity,None)?;
                require(bounded(import_receipt_id,256), "missing durable managed import receipt")?;
                self.jobs[index].document = Some(document.clone());
                self.jobs[index].stage = if self.jobs[index].preset_condition_matched { Stage::PreflightPreset } else { Stage::FreezeExport };
            }
            ReceiptResult::PresetPreflight { assessment } => {
                let CommandKind::PreflightPreset { document, preset_sha256, .. } = &command.operation else {
                    return Err(crate::schema::WorkflowError("wrong preset preflight phase".into()));
                };
                require(bounded(&assessment.report_id,256) && digest(&assessment.report_sha256)
                    && &assessment.preset_sha256 == preset_sha256 && assessment.document_revision == document.document_revision,
                    "preset preflight is not bound to the exact preset/document revision")?;
                require(if self.graph.automatic() { !assessment.requires_review && assessment.review.is_none() }
                    else { assessment.requires_review },
                    "preset assessment mode differs from frozen graph; automatic intent is not image review")?;
                if let Some(prior) = &self.jobs[index].preset_assessment {
                    require(prior.report_id == assessment.report_id && prior.report_sha256 == assessment.report_sha256
                        && prior.requires_review == assessment.requires_review, "review report changed while awaiting owner review")?;
                }
                if let Some(review) = &assessment.review {
                    require(bounded(&review.receipt_id,256) && review.report_sha256 == assessment.report_sha256
                        && review.document_id == document.document_id && review.document_revision == document.document_revision
                        && review.preset_sha256 == assessment.preset_sha256, "owner review receipt is stale or misbound")?;
                }
                self.jobs[index].preset_assessment = Some(assessment.clone());
                if assessment.requires_review && assessment.review.is_none() {
                    self.pause = Some(PauseReason::ReviewRequired { operation_id: command.identity.operation_id.clone(),
                        report_id: assessment.report_id.clone(), report_sha256: assessment.report_sha256.clone() });
                    self.last_reply = Some(receipt.clone());
                    return Ok(());
                }
                self.jobs[index].stage = Stage::ApplyPreset;
            }
            ReceiptResult::PresetApplied { document, preset_receipt_id } => {
                require(matches!(command.operation,CommandKind::ApplyPreset { .. }), "wrong preset application phase")?;
                validate_document(document,&command.identity,command.identity.document_id.as_deref())?;
                require(bounded(preset_receipt_id,256), "missing preset owner commit receipt")?;
                self.jobs[index].document = Some(document.clone());
                self.jobs[index].stage = Stage::FreezeExport;
            }
            ReceiptResult::ExportFrozen { plan } => {
                let CommandKind::FreezeExport { document, output_root, recipe_sha256 } = &command.operation else {
                    return Err(crate::schema::WorkflowError("wrong export freeze phase".into()));
                };
                require(bounded(&plan.plan_id,256) && digest(&plan.plan_sha256) && plan.document_revision == document.document_revision
                    && &plan.output_root == output_root && &plan.recipe_sha256 == recipe_sha256
                    && !plan.targets.is_empty() && plan.targets.len() <= 64, "invalid or stale frozen export plan")?;
                let mut unique = std::collections::BTreeSet::new();
                for target in &plan.targets {
                    require(crate::schema::path_text(target) && Path::new(target).starts_with(output_root)
                        && Path::new(target) != Path::new(output_root) && unique.insert(target), "frozen target is duplicated or outside output root")?;
                }
                self.jobs[index].export_plan = Some(plan.clone());
                self.jobs[index].stage = Stage::StartExport;
            }
            ReceiptResult::Exported { plan_id, export_receipt_id, outputs } => {
                let CommandKind::StartExport { plan, .. } = &command.operation else {
                    return Err(crate::schema::WorkflowError("wrong export start phase".into()));
                };
                require(plan_id == &plan.plan_id && bounded(export_receipt_id,256) && outputs.len() == plan.targets.len(), "export receipt does not match the frozen plan")?;
                let mut unique = std::collections::BTreeSet::new();
                for output in outputs {
                    require(plan.targets.contains(&output.path) && unique.insert(&output.path)
                        && digest(&output.sha256) && output.size_bytes > 0, "invalid output receipt")?;
                }
                self.jobs[index].stage = Stage::Done;
            }
            ReceiptResult::Failed { code, message, retained_document } => {
                require(bounded(code,128) && bounded(message,2048), "invalid definitive failure")?;
                let node = self.graph.ordered.iter().find(|node| node.id == command.identity.node_id).expect("pending node");
                match node.error_policy {
                    ErrorPolicy::Stop => { self.stopped = true; self.jobs[index].stage = Stage::Failed; }
                    ErrorPolicy::Skip => self.jobs[index].stage = Stage::Skipped,
                    ErrorPolicy::KeepContinue => {
                        let Some(document) = retained_document else {
                            self.pause = Some(PauseReason::UncertainOutcome { operation_id: command.identity.operation_id.clone(),
                                detail: "keep_continue requires an owner-readback retained document; query before advancing".into() });
                            self.last_reply = Some(receipt.clone());
                            return Ok(());
                        };
                        validate_document(document,&command.identity,command.identity.document_id.as_deref())?;
                        require(matches!(command.operation,CommandKind::PreflightPreset { .. } | CommandKind::ApplyPreset { .. }), "keep_continue unsupported for this node")?;
                        self.jobs[index].document = Some(document.clone());
                        self.jobs[index].stage = Stage::FreezeExport;
                    }
                }
                self.jobs[index].warning = Some(format!("{code}: {message}"));
            }
            ReceiptResult::Cancelled { owner_receipt_id } => {
                require(bounded(owner_receipt_id,256), "missing cancellation receipt")?;
                self.jobs[index].stage = Stage::Skipped;
                self.jobs[index].warning = Some("Owner confirmed cancellation; no later nodes run for this input.".into());
            }
        }
        require(self.jobs[index].receipts.len() < 8, "terminal receipt bound reached")?;
        self.jobs[index].receipts.push(receipt.clone());
        self.pending = None;
        self.last_reply = Some(receipt.clone());
        self.pause = None;
        Ok(())
    }
}

fn validate_document(document: &DocumentState, identity: &Identity, expected_document: Option<&str>) -> Result<()> {
    document.validate()?;
    require(document.project_id == identity.project_id && document.source_sha256 == identity.source_sha256
        && expected_document.map(|expected| expected == document.document_id).unwrap_or(true),
        "document proof belongs to another project/source/document")
}
