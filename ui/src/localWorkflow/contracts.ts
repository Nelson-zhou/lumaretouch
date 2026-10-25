// SPDX-License-Identifier: GPL-3.0-or-later
/** Local-only v1 contract. The application supplies the port; this module never invokes native APIs. */
export const WORKFLOW_PORT_VERSION = 1 as const;
export type ErrorPolicy = 'stop' | 'skip' | 'keep_continue';
export type WorkflowOperation =
  | {kind: 'directory_source'; root: string; recursive: boolean; include_existing: boolean; extensions: string[]; settle_ms: number}
  | {kind: 'managed_import'; project_id: string; project_path: string; managed_root: string}
  | {kind: 'path_labels'; rules: {target: 'filename' | 'relative_path'; contains: string; label: string}[]}
  | {kind: 'compatible_preset'; preset_id: string; preset_sha256: string; when_all_labels: string[]}
  | {kind: 'export'; output_root: string; recipe_sha256: string};
export type NodeKind = WorkflowOperation['kind'];
export interface WorkflowNode {id: string; error_policy: ErrorPolicy; operation: WorkflowOperation}
export interface WorkflowEdge {from: string; to: string}
export interface WorkflowGraph {
  schema_version: 1;
  workflow_id: string;
  revision: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}
export interface WorkflowDefinition {
  name: string;
  description: string;
  /** null means this is an unsaved definition. Graph revision is independent. */
  storage_revision: string | null;
  graph: WorkflowGraph;
}
export interface DefinitionSummary {workflow_id: string; name: string; storage_revision: string; updated_at: string}
export interface WorkflowDiagnostic {severity: 'error' | 'warning' | 'info'; code: string; message: string; node_id?: string}
export interface WorkflowCapabilities {
  available: boolean;
  reason?: string;
  can_save: boolean;
  can_run: boolean;
  can_open_review: boolean;
  /** Missing entries grant no policy. keep_continue is only meaningful for compatible_preset. */
  error_policies: Partial<Record<NodeKind, ErrorPolicy[]>>;
}
export interface ProjectLease {
  lease_id: string;
  project_id: string;
  project_path: string;
  saved: true;
  /** Exclusive workflow ownership of the exact currently loaded clean saved project, not another project. */
  dedicated: true;
  expires_at: string;
}
/** Exact bounded v1 shape from workflow_owner_protocol.RECIPE_PROFILE, not editable settings. */
export interface WorkflowExportProfile {
  profile: 'lrt.workflow-export.jpeg-srgb.v1';
  export_options: {
    format: 'jpg'; quality: 95; tile: 1024; bit_depth: 8; scale: 1; upscale_backend: 'lanczos3';
    sharpen: 0; output_profile: 'srgb'; metadata_include_gps: false;
    conflict_policy: 'skip_and_report'; tiff_compression: 'deflate';
  };
  destination: {mode: 'chosen_root'; retain_hierarchy: false; conflict: 'ask'; create_missing: false};
  watermark: null;
  layout: null;
}
export interface ReturnedExportProfile {recipe_sha256: string; recipe_profile: WorkflowExportProfile}
export interface PreflightReport {
  workflow_id: string;
  graph_revision: number;
  lease_id: string;
  /** Host-issued binding of the canonical graph, filesystem checks and immutable recipe/preset hashes. */
  preflight_token: string;
  valid_until: string;
  can_start: boolean;
  diagnostics: WorkflowDiagnostic[];
  recipe_sha256?: string;
  recipe_profile?: WorkflowExportProfile;
}
export type RunStatus = 'running' | 'paused' | 'stopping' | 'stopped' | 'complete' | 'failed';
export type StepStatus = 'waiting' | 'running' | 'pending' | 'unknown' | 'review_required' | 'succeeded' | 'failed' | 'skipped' | 'stopped';
export interface WorkflowNodeRecord {node_id: string; status: StepStatus; message?: string; receipt_id?: string}
export interface WorkflowFileRecord {
  file_id: string;
  relative_path: string;
  status: StepStatus;
  stage: string;
  labels: string[];
  nodes: WorkflowNodeRecord[];
  message?: string;
  output_path?: string;
}
export interface ReviewRequirement {
  review_id: string;
  file_id: string;
  node_id: string;
  family: string;
  reason: string;
}
export interface RunSummary {
  run_id: string;
  workflow_id: string;
  graph_revision: number;
  status: RunStatus;
  started_at: string;
  completed_files: number;
  total_files: number;
}
export interface WorkflowRun extends RunSummary {
  sequence: number;
  lease_id: string;
  /** Stop is only a dispatch fence. False keeps readback/ownership active until all owner effects settle. */
  effects_settled: boolean;
  files: WorkflowFileRecord[];
  /** Records are bounded by the host; total_files is not inferred from the visible page. */
  records_truncated: boolean;
  diagnostics: WorkflowDiagnostic[];
  review: ReviewRequirement | null;
}
export type WorkflowCommand =
  | {kind: 'save_definition'; definition: WorkflowDefinition; expected_storage_revision: string | null}
  | {kind: 'acquire_project_lease'; project_id: string; project_path: string}
  | {kind: 'release_project_lease'; lease_id: string}
  | {kind: 'start'; graph: WorkflowGraph; lease_id: string; preflight_token: string}
  | {kind: 'stop'; run_id: string}
  | {kind: 'open_review'; run_id: string; review_id: string};
export type WorkflowOutcome =
  | {kind: 'save_definition'; definition: WorkflowDefinition}
  | {kind: 'acquire_project_lease'; lease: ProjectLease}
  | {kind: 'release_project_lease'; released: true; lease_id: string}
  | {kind: 'start'; run: WorkflowRun}
  | {kind: 'stop'; run: WorkflowRun}
  | {kind: 'open_review'; opened: boolean; message: string};
export interface PendingWorkflowRequest {request_id: string; command_kind: WorkflowCommand['kind']}
export type WorkflowReceipt = PendingWorkflowRequest & (
  | {status: 'pending' | 'unknown'; message?: string}
  | {status: 'failed' | 'cancelled'; message: string}
  | {status: 'succeeded'; outcome: WorkflowOutcome}
);
export interface WorkflowWorkspace {
  port_version: 1;
  /** When supplied, must match the port's persistent scope_id. */
  host_scope_id?: string;
  workspace_revision: number;
  capabilities: WorkflowCapabilities;
  definitions: DefinitionSummary[];
  runs: RunSummary[];
  active_run: WorkflowRun | null;
  /** New native adapters populate this even when null, allowing acquired-but-unused lease recovery. */
  lease?: ProjectLease | null;
  recipe_sha256?: string;
  recipe_profile?: WorkflowExportProfile;
  /** True only while the host's real read-only engine profile request is outstanding. */
  recipe_profile_pending?: boolean;
  /** Includes indeterminate writes from earlier UI lifetimes. An unknown receipt must remain here. */
  unresolved_requests: PendingWorkflowRequest[];
}
export interface WorkflowHostPort {
  readonly version: 1;
  /** Stable identity of the host recovery journal. Do not change it on rerender. */
  readonly scope_id: string;
  readWorkspace(): Promise<WorkflowWorkspace>;
  readDefinition(workflow_id: string): Promise<WorkflowDefinition>;
  preflight(input: {port_version: 1; graph: WorkflowGraph; lease_id: string}): Promise<PreflightReport>;
  /** Persist request identity before effects; deduplicate by identity. Never acknowledge a review here. */
  submit(input: {port_version: 1; request_id: string; command: WorkflowCommand}): Promise<WorkflowReceipt>;
  queryRequest(request_id: string): Promise<WorkflowReceipt>;
  readRun(run_id: string): Promise<WorkflowRun>;
}
