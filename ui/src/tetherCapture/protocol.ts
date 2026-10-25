// SPDX-License-Identifier: GPL-3.0-or-later
/** UI-only ABI. The application supplies a real host; this module never loads a
 * camera driver, invents a device, imports a file, or acknowledges pixel review. */
export const TETHER_HOST_PROTOCOL = 1 as const;
export type TetherRecordingFormat = 'raw' | 'jpeg' | 'raw_jpeg' | 'unknown';
export type TetherImportFormat = Exclude<TetherRecordingFormat, 'unknown'>;
// raw_jpeg means keep all actual supported files when recording_format is
// unknown. It does not assert the camera records both, or create a missing mate.
export type TetherPreviewMode = 'follow_latest' | 'keep_current';
export type TetherNamingMode = 'custom_counter' | 'custom_filename' | 'date_counter' | 'date_filename' | 'original';
export interface TetherNaming {
  mode: TetherNamingMode;
  custom_name: string;
  counter_start: number;
}
export interface TetherCapability {
  state: 'unknown' | 'driver_advertised' | 'verified' | 'unsupported';
  /** Human-readable, operation-specific evidence or reason, not certification. */
  reason: string;
}
export interface TetherDevice {
  device_id: string;
  label: string;
  connected: boolean;
  /** True only after fresh enumeration/probe by the current runtime. */
  detected_by_runtime: boolean;
  recording_format: TetherRecordingFormat;
  recording_format_reason: string;
  capabilities: {
    event_polling: TetherCapability;
    original_download: TetherCapability;
    remote_shutter: TetherCapability;
    live_view: TetherCapability;
  };
  /** Read-only camera values. No UI camera-setting write API exists. */
  settings: ReadonlyArray<{label: string; value: string}>;
}
export interface TetherDestination {
  /** Host-owned authorization/validation token from the real folder picker. */
  destination_id: string;
  display_path: string;
}
export interface TetherIngestionTarget {
  project_id: string;
  path: string;
  name: string;
  available: boolean;
  reason: string;
  /** Actual engine admission budget, not an estimate of available disk space. */
  remaining_operations: number;
}
export interface TetherSession {
  session_id: string;
  /** Strictly increasing across replacement sessions, even for one device. */
  generation: number;
  device_id: string;
  /** Frozen project target; changing the editor's project cannot redirect it. */
  ingestion_target: Pick<TetherIngestionTarget, 'project_id' | 'path' | 'name'>;
  phase: 'starting' | 'active' | 'stopping' | 'stopped' | 'error';
  destination: TetherDestination;
  naming: TetherNaming;
  import_format: TetherImportFormat;
  preview_mode: TetherPreviewMode;
  live_view: 'off' | 'starting' | 'on' | 'stopping' | 'error';
  error?: string;
}
export interface TetherImportedDocument {
  /** Host-issued import receipt, never a request ID or camera object path. */
  import_receipt_id: string;
  transfer_id: string;
  session_id: string;
  session_generation: number;
  document_id: string;
  project_id: string;
  project_path: string;
  managed_path: string;
  sha256: string;
  bytes: number;
}
export interface TetherTransfer {
  transfer_id: string;
  session_id: string;
  session_generation: number;
  camera_filename: string;
  local_filename?: string;
  format: 'raw' | 'jpeg' | 'other' | 'unknown';
  phase: 'queued' | 'downloading' | 'validating' | 'importing' | 'imported' | 'skipped' | 'failed' | 'outcome_unknown' | 'cancelled';
  /** Omit absent byte measurements; the UI never synthesizes progress. */
  bytes_received?: number;
  bytes_total?: number;
  error?: string;
  /** Host asserts a known failed/retry-safe outcome; unknown is not retryable. */
  retryable: boolean;
  imported_document?: TetherImportedDocument;
}
export type TetherAction = 'probe_device' | 'start' | 'stop' | 'retry_transfer' | 'set_preview_mode' | 'start_live_view' | 'stop_live_view' | 'capture';
export interface TetherPendingRequest {
  request_id: string;
  action: TetherAction;
  expected_session_id: string | null;
  expected_generation: number | null;
}
export interface TetherSnapshot {
  protocol_version: typeof TETHER_HOST_PROTOCOL;
  host_id: string;
  /** Monotonic for the entire host lifetime, not reset at each session. */
  revision: number;
  availability: {available: boolean; reason: string};
  /** Actual saved project and engine admission. null is not an implicit target. */
  ingestion_target: TetherIngestionTarget | null;
  devices: ReadonlyArray<TetherDevice>;
  session: TetherSession | null;
  transfers: ReadonlyArray<TetherTransfer>;
  /** Durable host mailbox: reappears after UI remount until terminal receipt. */
  pending_requests: ReadonlyArray<TetherPendingRequest>;
}
interface TetherRequestIdentity extends TetherPendingRequest {
  protocol_version: typeof TETHER_HOST_PROTOCOL;
  host_id: string;
  expected_revision: number;
}
export type TetherCommand =
  | {action: 'probe_device'; device_id: string}
  | {action: 'start'; device_id: string; ingestion_target: Pick<TetherIngestionTarget, 'project_id' | 'path'>; destination: TetherDestination; naming: TetherNaming; import_format: TetherImportFormat; preview_mode: TetherPreviewMode}
  | {action: 'stop'}
  | {action: 'retry_transfer'; transfer_id: string}
  | {action: 'set_preview_mode'; preview_mode: TetherPreviewMode}
  | {action: 'start_live_view'}
  | {action: 'stop_live_view'}
  | {action: 'capture'};
export type TetherRequest = TetherRequestIdentity & TetherCommand;
export type TetherReceipt = {
  protocol_version: typeof TETHER_HOST_PROTOCOL;
  host_id: string;
  request_id: string;
  action: TetherAction;
  expected_session_id: string | null;
  expected_generation: number | null;
  snapshot?: TetherSnapshot;
} & (
  | {phase: 'pending'; outcome_unknown: boolean; error?: string}
  | {phase: 'done'; outcome_unknown: true; success?: boolean; error?: string}
  | {phase: 'done'; outcome_unknown: false; success: boolean; error?: string}
);
export interface TetherLiveFrame {
  host_id: string;
  session_id: string;
  session_generation: number;
  sequence: number;
  /** Actual host-supplied frame only: blob/data image URI, not arbitrary URL. */
  image_url: string;
  width: number;
  height: number;
}
export type TetherHostEvent =
  | {type: 'snapshot'; snapshot: TetherSnapshot}
  | {type: 'imported_document'; snapshot: TetherSnapshot; receipt: TetherImportedDocument}
  | {type: 'live_frame'; frame: TetherLiveFrame};
export interface TetherHostPort {
  /** Transport capability, never inferred from a camera advertised feature. */
  supported_preview_modes?: ReadonlyArray<TetherPreviewMode>;
  protocol_version: typeof TETHER_HOST_PROTOCOL;
  /** Stable for one host runtime. Replace the port when this identity changes. */
  host_id: string;
  readSnapshot(): Promise<TetherSnapshot>;
  subscribe(listener: (event: TetherHostEvent) => void): () => void;
  /** Host must record request identity before any mutation; replay is forbidden. */
  send(request: TetherRequest): Promise<TetherReceipt>;
  /** Read-only. null means not yet found, NEVER proof that it did not execute. */
  queryReceipt(requestId: string): Promise<TetherReceipt | null>;
  /** Real system folder picker. null means the user cancelled. */
  pickDestination(): Promise<TetherDestination | null>;
}
export interface TetherImportNotice {
  receipt: TetherImportedDocument;
  /** Advisory navigation only; the host has already completed managed import. */
  make_current: boolean;
}
