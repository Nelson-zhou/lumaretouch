// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. An isolated read protocol, not another people request owner.
import {peopleAssetContext, type FaceRef, type PeopleAction, type PeopleEnvelope, type PeopleResult, type PeopleView} from '../people/model';
import {digest, safeRevision, sameFace, validFaceRef, type EffectiveSourceProof} from '../people/transferProof';
import {canonical, object, skinReferenceBinding, validCatalog as validFaceCatalog,
  type SkinReferenceCatalog, type SkinReferenceSource} from '../skinReferenceMatch/model';
import {skinReferenceBodyBinding, validCatalog as validBodyCatalog,
  type SkinReferenceBodyCatalog} from '../skinReferenceBody/model';

export {canonical, object};
export const ACTION = 'skin_reference_choice' as const;
export const METHOD = 'rust-self-fit-robust-log-linear-srgb-y-v1' as const;
export const FACE_OPERATION = 'lnx.skin_reference_match.v1' as const;
export const BODY_OPERATION = 'lnx.skin_reference_body_match.v1' as const;
export const CONTROL_ID = 'control:PC-32465:19' as const;
export const MIN_LOG_GAP = Math.log(1.02);
export type ChoiceFamily = 'face' | 'body';
export type ChoiceCatalog = SkinReferenceCatalog | SkinReferenceBodyCatalog;
export type ChoiceRequest = {family: ChoiceFamily; source_review_sha256: string; manual_reference?: FaceRef | null};
/** Intentionally not cast to PeopleAction: shared routing must explicitly admit this action. */
export type ChoiceCommand = PeopleEnvelope & {action: typeof ACTION; payload: ChoiceRequest};
export type ChoiceResult = {protocol: 1; request_id: string; action: typeof ACTION; document_id: string;
  success: boolean; outcome_unknown: false; error?: string | null; payload?: unknown; payload_released?: boolean;
  event?: 'people_result'; created_id?: null; frame_emitted?: false;
  batch_id?: null; skin_reference_choice_request: Omit<ChoiceCommand, 'request_id'>};
export type SkinReferenceChoiceReceipt = {command: PeopleAction; result: PeopleResult};
export type ChoiceMeasurement = {log_luminance: number; linear_luminance: number; initial_log_luminance_mad: number;
  robust_sample_count: number; robust_weight: number; effective_samples: number; retained_weight_fraction: number};
export type ChoiceEvidence = {backend: 'mediapipe'; detector_model_sha256: string; semantic_model_sha256: string;
  landmark_digest: string; status: 'verified'; source_width: number; source_height: number; orientation: 'exif_normalized_once'};
export type ChoiceObservation = {contract: 'mediapipe-face-skin-edit-weight-v1'; source_sha256: string;
  semantic_model_sha256: string; producer_width: number; producer_height: number};
export type MeasuredCandidate = {face_ref: FaceRef; status: 'measured'; measurement: ChoiceMeasurement;
  /** Source row, column, height, width. Never display- or edited-canvas coordinates. */
  source_window: [number, number, number, number]; support_sha256: string; evidence: ChoiceEvidence;
  landmark_digest: string; face_skin_observation: ChoiceObservation; protected_face_boxes: number; protected_actual_face_ovals: number};
export type UnmeasuredCandidate = {face_ref: FaceRef; status: 'unavailable' | 'disabled';
  reason?: 'actual-face-analysis-unavailable' | 'actual-face-analysis-invalid' | 'source-measurement-refused'; detail?: string};
export type ChoiceCandidate = MeasuredCandidate | UnmeasuredCandidate;
export type ChoiceBlocker = 'fewer-than-two-enabled-retained-faces' | 'enabled-face-measurement-unavailable'
  | 'detector-limit-reached' | 'brightest-measurements-too-close';
export type ChoiceProposal = {version: 1; operation_id: typeof FACE_OPERATION; control_id: typeof CONTROL_ID; method: typeof METHOD;
  source: SkinReferenceSource; source_stage: 'immutable-source-before-repair-and-portrait-v1'; source_pixels_sha256: string;
  source_kind: 'original' | 'creative'; source_bits: 8 | 16 | 32; source_encoding: 'encoded-working-srgb-d65-sdr';
  state_revision: number; association_revision: number; candidate_scope: 'all-enabled-retained-same-source-faces';
  census_complete: false; detector_limit_reached: boolean | null; candidates: ChoiceCandidate[];
  read_only_proposal: true; review_required: true; reference_face_exclusion_required: true;
  body_extension_enabled: false; fit_retained: false; portable: false; memory_admission_bytes: number; limitations: string[];
  reference_face_ref: FaceRef | null; selection_mode: 'automatic-proposal' | 'manual-override-proposal' | 'none';
  automatic_status: 'proposed' | 'blocked'; automatic_reference_face_ref: FaceRef | null; automatic_blockers: ChoiceBlocker[];
  ranked_face_refs: FaceRef[]; top_log_luminance_gap: number | null; minimum_log_luminance_gap: number;
  ambiguous_face_refs: FaceRef[]; proposal_sha256: string};
export type ChoiceHostProof = {source_pixels_sha256: string; graph_sha256: string; analysis_sha256: string;
  body_bank_sha256: string; document_snapshot_sha256: string};
export type ChoiceReport = ChoiceHostProof & {kind: typeof ACTION; version: 1; operation_id: typeof FACE_OPERATION | typeof BODY_OPERATION;
  family: ChoiceFamily; target: ChoiceCommand['target']; document_id: string; revision: string; source: SkinReferenceSource;
  source_proof: EffectiveSourceProof; source_review_sha256: string; source_image_sha256: string;
  skin_reference_choice_request: ChoiceRequest; proposal: ChoiceProposal;
  memory: {resident_input_bytes: number; verification_workspace_bytes: number; total_byte_budget: number; capture_byte_budget: number;
    measurement_byte_budget: number; estimated_peak_bytes: number};
  read_only_proposal: true; source_image_load_required: true; review_required: true;
  grants_consent: false; render_committed: false; portable: false; report_sha256: string};
export type ChoiceContext = {family: ChoiceFamily; view: PeopleView; catalog: ChoiceCatalog};
export const exact = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).sort().join('|') === [...keys].sort().join('|');
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const positiveInteger = (v: unknown): v is number => safeRevision(v) && v > 0;
const same = (a: unknown, b: unknown) => canonical(a) === canonical(b);
const close = (a: number, b: number) => Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(a), Math.abs(b));
const dimensions = (v: unknown): v is number => positiveInteger(v) && v <= 1_000_000;
const LIMITATIONS = ['not-a-complete-photograph-face-census', 'observed-source-luminance-not-intrinsic-complexion',
  'confidence-is-not-brightness-and-no-demographic-inference', 'unknown-occlusion-and-model-errors-require-visual-review',
  'resampled-semantic-observation-is-not-fresh-full-resolution-inference',
  'not-proprietary-metric-parity-or-complete-ai-multi-person-feature'];
export const PROOF_KEYS = ['source_pixels_sha256', 'graph_sha256', 'analysis_sha256', 'body_bank_sha256', 'document_snapshot_sha256'] as const;
const REPORT_KEYS = ['kind', 'version', 'operation_id', 'family', 'target', 'document_id', 'revision', 'source', 'source_proof',
  'source_review_sha256', 'source_image_sha256', ...PROOF_KEYS, 'skin_reference_choice_request', 'proposal', 'memory',
  'read_only_proposal', 'source_image_load_required', 'review_required', 'grants_consent', 'render_committed', 'portable', 'report_sha256'];
const PROPOSAL_KEYS = ['version', 'operation_id', 'control_id', 'method', 'source', 'source_stage', 'source_pixels_sha256',
  'source_kind', 'source_bits', 'source_encoding', 'state_revision', 'association_revision', 'candidate_scope', 'census_complete',
  'detector_limit_reached', 'candidates', 'read_only_proposal', 'review_required', 'reference_face_exclusion_required',
  'body_extension_enabled', 'fit_retained', 'portable', 'memory_admission_bytes', 'limitations', 'reference_face_ref', 'selection_mode',
  'automatic_status', 'automatic_reference_face_ref', 'automatic_blockers', 'ranked_face_refs', 'top_log_luminance_gap',
  'minimum_log_luminance_gap', 'ambiguous_face_refs', 'proposal_sha256'];

/** Bound traversal before canonical comparisons. Reject cycles, non-JSON numbers and hidden payloads. */
function boundedJson(value: unknown): boolean {
  const seen = new Set<object>(); let nodes = 0, text = 0;
  function visit(v: unknown, depth: number): boolean {
    if (++nodes > 20_000 || depth > 16) return false;
    if (v === null || typeof v === 'boolean') return true;
    if (typeof v === 'number') return Number.isFinite(v);
    if (typeof v === 'string') {text += v.length; return text <= 512 * 1024;}
    if (!object(v) && !Array.isArray(v) || seen.has(v as object)) return false;
    seen.add(v as object);
    const result = Array.isArray(v) ? v.every(item => visit(item, depth + 1))
      : Object.entries(v as Record<string, unknown>).every(([key, item]) => visit(key, depth + 1) && visit(item, depth + 1));
    seen.delete(v as object); return result;
  }
  return visit(value, 0);
}
export function validChoiceCatalog(catalog: unknown, family: ChoiceFamily, view: PeopleView): catalog is ChoiceCatalog {
  return family === 'face' ? validFaceCatalog(catalog, view) : family === 'body' && validBodyCatalog(catalog, view);
}
export function validHostProof(v: unknown): v is ChoiceHostProof {
  return object(v) && exact(v, PROOF_KEYS) && PROOF_KEYS.every(key => digest(v[key]));
}
export function validContext(value: ChoiceContext | null): value is ChoiceContext {
  return !!value && validChoiceCatalog(value.catalog, value.family, value.view);
}
/** Catalog replacement, source repair/document revisions, associations and measured faces invalidate the whole proposal. */
export function choiceBinding(context: ChoiceContext | null): string {
  if (!context) return 'unavailable';
  const {family, view, catalog} = context;
  return canonical([family, skinReferenceBinding(view), skinReferenceBodyBinding(view), catalog.source, catalog.source_proof,
    catalog.source_review_sha256, catalog.source_image.sha256, catalog.source_image.width, catalog.source_image.height,
    catalog.faces, catalog.current, 'targets' in catalog ? catalog.targets : null]);
}
export function validRequest(value: unknown): value is ChoiceRequest {
  return object(value) && exact(value, ['family', 'source_review_sha256', ...(Object.hasOwn(value, 'manual_reference') ? ['manual_reference'] : [])])
    && (value.family === 'face' || value.family === 'body') && digest(value.source_review_sha256)
    && (!Object.hasOwn(value, 'manual_reference') || value.manual_reference === null || validFaceRef(value.manual_reference));
}
export function commandMatches(command: unknown, context: ChoiceContext): command is ChoiceCommand {
  if (!object(command) || !exact(command, ['request_id', 'action', 'payload', 'document_id', 'document_epoch', 'document_revision',
    'state_revision', 'association_revision', 'target']) || command.action !== ACTION || typeof command.request_id !== 'string'
    || !command.request_id || command.request_id.length > 128 || !validRequest(command.payload) || !validContext(context)) return false;
  const {request_id: _request, action: _action, payload, ...envelope} = command;
  return same(envelope, peopleAssetContext(context.view)) && payload.family === context.family
    && payload.source_review_sha256 === context.catalog.source_review_sha256 && (payload.manual_reference == null
      || context.catalog.faces.some(face => face.enabled && face.available && sameFace(face.face_ref, payload.manual_reference!)));
}
export function echoMatches(command: ChoiceCommand, value: unknown): boolean {
  const {request_id: _request, ...echo} = command;
  return object(value) && boundedJson(value.skin_reference_choice_request) && same(value.skin_reference_choice_request, echo);
}
export function validReceiptEnvelope(command: ChoiceCommand, value: unknown): value is ChoiceResult {
  if (!object(value) || !boundedJson(value) || !exact(value, ['protocol', 'request_id', 'action', 'document_id', 'success',
    'outcome_unknown', 'skin_reference_choice_request', ...['event', 'created_id', 'frame_emitted', 'payload', 'payload_released', 'error', 'batch_id'].filter(k => Object.hasOwn(value, k))])
    || value.protocol !== 1 || value.request_id !== command.request_id || value.action !== ACTION || value.document_id !== command.document_id
    || typeof value.success !== 'boolean' || value.outcome_unknown !== false || !echoMatches(command, value)
    || value.batch_id != null || value.created_id != null || value.event !== undefined && value.event !== 'people_result'
    || value.frame_emitted !== undefined && value.frame_emitted !== false
    || value.error != null && (typeof value.error !== 'string' || value.error.length > 8000)
    || value.payload_released !== undefined && typeof value.payload_released !== 'boolean') return false;
  return value.success ? value.event === 'people_result' && value.created_id === null && value.batch_id === null
    && value.frame_emitted === false && value.error === null
    && (value.payload_released === true ? !Object.hasOwn(value, 'payload') : Object.hasOwn(value, 'payload'))
    : typeof value.error === 'string' && value.error.length > 0 && !Object.hasOwn(value, 'payload') && value.payload_released !== true;
}
export function receiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!view || command.action !== ACTION || !validRequest(command.payload) || !validReceiptEnvelope(command as ChoiceCommand, result)
    || !result.success || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.document_revision !== view.binding.document_revision || command.state_revision !== view.revision
    || command.association_revision !== view.association_revision) return false;
  return same(command.target, peopleAssetContext(view)?.target);
}
export function validReleasedReceipt(command: PeopleAction, result: PeopleResult): boolean {
  return command.action === ACTION && validRequest(command.payload) && validReceiptEnvelope(command as ChoiceCommand, result)
    && result.success && result.payload_released === true;
}
function validMeasurement(value: unknown, pixels: number): value is ChoiceMeasurement {
  if (!object(value) || !exact(value, ['log_luminance', 'linear_luminance', 'initial_log_luminance_mad', 'robust_sample_count',
    'robust_weight', 'effective_samples', 'retained_weight_fraction']) || !Object.values(value).every(finite)) return false;
  const m = value as ChoiceMeasurement;
  const ceiling = m.robust_sample_count + Math.max(1e-7, m.robust_sample_count * 1e-6);
  return m.log_luminance > Math.log(.01) && m.log_luminance < Math.log(.90)
    && close(Math.exp(m.log_luminance), m.linear_luminance) && m.initial_log_luminance_mad >= 0 && m.initial_log_luminance_mad <= .50 + 1e-12
    && positiveInteger(m.robust_sample_count) && m.robust_sample_count >= 64 && m.robust_sample_count <= pixels
    && m.robust_weight >= 64 && m.robust_weight <= ceiling
    && m.effective_samples >= 64 && m.effective_samples <= ceiling
    && m.retained_weight_fraction >= .5 && m.retained_weight_fraction <= 1 + 1e-6;
}
function validCandidate(value: unknown, context: ChoiceContext): value is ChoiceCandidate {
  if (!object(value) || !validFaceRef(value.face_ref)) return false;
  const face = context.catalog.faces.find(row => sameFace(row.face_ref, value.face_ref as FaceRef));
  if (!face || !['measured', 'unavailable', 'disabled'].includes(String(value.status)) || (value.status === 'disabled') === face.enabled) return false;
  if (value.status !== 'measured') {
    const hasReason = Object.hasOwn(value, 'reason'), hasDetail = Object.hasOwn(value, 'detail');
    return exact(value, ['face_ref', 'status', ...(hasReason ? ['reason'] : []), ...(hasDetail ? ['detail'] : [])])
      && (value.status === 'disabled' || hasReason)
      && (!hasReason ? !hasDetail : value.reason === 'actual-face-analysis-unavailable' ? !hasDetail
        : ['actual-face-analysis-invalid', 'source-measurement-refused'].includes(String(value.reason))
          && hasDetail && typeof value.detail === 'string' && value.detail.length <= 8000);
  }
  if (!exact(value, ['face_ref', 'status', 'measurement', 'source_window', 'support_sha256', 'evidence', 'landmark_digest',
    'face_skin_observation', 'protected_face_boxes', 'protected_actual_face_ovals']) || !face.available
    || !Array.isArray(value.source_window) || value.source_window.length !== 4 || !value.source_window.every(safeRevision)
    || !digest(value.support_sha256) || !digest(value.landmark_digest)) return false;
  const [row, col, height, width] = value.source_window, source = context.catalog.source;
  if (!height || !width || height * width > 16_000_000 || row + height > source.height || col + width > source.width
    || !validMeasurement(value.measurement, height * width)) return false;
  const evidence = value.evidence, observation = value.face_skin_observation;
  return object(evidence) && exact(evidence, ['backend', 'detector_model_sha256', 'semantic_model_sha256', 'landmark_digest',
    'status', 'source_width', 'source_height', 'orientation']) && evidence.backend === 'mediapipe' && evidence.status === 'verified'
    && evidence.orientation === 'exif_normalized_once' && digest(evidence.detector_model_sha256) && digest(evidence.semantic_model_sha256)
    && evidence.landmark_digest === value.landmark_digest && evidence.source_width === source.width && evidence.source_height === source.height
    && object(observation) && exact(observation, ['contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'])
    && observation.contract === 'mediapipe-face-skin-edit-weight-v1' && observation.source_sha256 === source.sha256
    && observation.semantic_model_sha256 === evidence.semantic_model_sha256 && dimensions(observation.producer_width) && dimensions(observation.producer_height)
    && safeRevision(value.protected_face_boxes) && value.protected_face_boxes === context.catalog.faces.length - 1
    && safeRevision(value.protected_actual_face_ovals) && value.protected_actual_face_ovals <= value.protected_face_boxes;
}
function validSelection(value: ChoiceProposal, request: ChoiceRequest): boolean {
  if (!finite(value.minimum_log_luminance_gap) || !close(value.minimum_log_luminance_gap, MIN_LOG_GAP)) return false;
  const enabled = value.candidates.filter(row => row.status !== 'disabled');
  const ranked = enabled.filter((row): row is MeasuredCandidate => row.status === 'measured').sort((a, b) =>
    b.measurement.log_luminance - a.measurement.log_luminance || (a.face_ref.face_instance_id < b.face_ref.face_instance_id ? -1 : 1));
  const blockers: ChoiceBlocker[] = [];
  if (enabled.length < 2) blockers.push('fewer-than-two-enabled-retained-faces');
  if (enabled.some(row => row.status !== 'measured')) blockers.push('enabled-face-measurement-unavailable');
  if (value.detector_limit_reached === true) blockers.push('detector-limit-reached');
  let ambiguous: FaceRef[] = [], gap: number | null = null;
  if (ranked.length >= 2) {
    const top = ranked[0].measurement.log_luminance; gap = top - ranked[1].measurement.log_luminance;
    // Use the validated producer threshold to avoid a libm one-ulp difference
    // incorrectly changing a candidate exactly on the disclosed boundary.
    ambiguous = ranked.filter(row => top - row.measurement.log_luminance <= value.minimum_log_luminance_gap).map(row => row.face_ref);
    if (ambiguous.length > 1) blockers.push('brightest-measurements-too-close'); else ambiguous = [];
  }
  const automatic = ranked.length && !blockers.length ? ranked[0].face_ref : null;
  const manual = request.manual_reference;
  if (manual != null && !ranked.some(row => sameFace(row.face_ref, manual))) return false;
  return same(value.ranked_face_refs, ranked.map(row => row.face_ref)) && same(value.automatic_blockers, blockers)
    && same(value.ambiguous_face_refs, ambiguous) && same(value.automatic_reference_face_ref, automatic)
    && value.automatic_status === (automatic ? 'proposed' : 'blocked')
    && same(value.reference_face_ref, manual ?? automatic)
    && value.selection_mode === (manual ? 'manual-override-proposal' : automatic ? 'automatic-proposal' : 'none')
    && (gap === null ? value.top_log_luminance_gap === null : finite(value.top_log_luminance_gap) && close(value.top_log_luminance_gap, gap));
}
export function validProposal(value: unknown, context: ChoiceContext, request: ChoiceRequest, pixelsHash: string): value is ChoiceProposal {
  if (!object(value) || !exact(value, PROPOSAL_KEYS) || value.version !== 1 || value.operation_id !== FACE_OPERATION
    || value.control_id !== CONTROL_ID || value.method !== METHOD || !same(value.source, context.catalog.source)
    || value.source_stage !== 'immutable-source-before-repair-and-portrait-v1' || value.source_pixels_sha256 !== pixelsHash
    || value.source_encoding !== 'encoded-working-srgb-d65-sdr' || value.state_revision !== context.view.revision
    || value.association_revision !== context.view.association_revision || value.candidate_scope !== 'all-enabled-retained-same-source-faces'
    || value.census_complete !== false || value.detector_limit_reached !== null && typeof value.detector_limit_reached !== 'boolean'
    || value.read_only_proposal !== true || value.review_required !== true || value.reference_face_exclusion_required !== true
    || value.body_extension_enabled !== false || value.fit_retained !== false || value.portable !== false
    || !positiveInteger(value.memory_admission_bytes) || !same(value.limitations, LIMITATIONS) || !digest(value.proposal_sha256)
    || !Array.isArray(value.candidates) || value.candidates.length > 64 || value.candidates.length !== context.catalog.faces.length) return false;
  const creative = context.catalog.source_proof.creative_source !== null;
  if (creative ? value.source_kind !== 'creative' || value.source_bits !== 32
    : value.source_kind !== 'original' || value.source_bits !== 8 && value.source_bits !== 16) return false;
  const refs = [...context.catalog.faces].sort((a, b) => a.face_ref.face_instance_id < b.face_ref.face_instance_id ? -1 : 1).map(row => row.face_ref);
  if (!value.candidates.every(row => validCandidate(row, context)) || !same(value.candidates.map(row => row.face_ref), refs)) return false;
  return validSelection(value as ChoiceProposal, request);
}
export function parseReport(value: unknown, command: ChoiceCommand, context: ChoiceContext): ChoiceReport | null {
  if (!commandMatches(command, context) || !object(value) || !boundedJson(value) || !exact(value, REPORT_KEYS)
    || value.kind !== ACTION || value.version !== 1 || value.family !== context.family
    || value.operation_id !== (context.family === 'face' ? FACE_OPERATION : BODY_OPERATION)
    || !same(value.target, command.target) || value.document_id !== command.document_id || value.revision !== String(command.document_revision)
    || !same(value.source, context.catalog.source) || !same(value.source_proof, context.catalog.source_proof)
    || value.source_review_sha256 !== context.catalog.source_review_sha256 || value.source_image_sha256 !== context.catalog.source_image.sha256
    || !PROOF_KEYS.every(key => digest(value[key])) || !digest(value.report_sha256)
    || !same(value.skin_reference_choice_request, command.payload) || value.read_only_proposal !== true
    || value.source_image_load_required !== true || value.review_required !== true || value.grants_consent !== false
    || value.render_committed !== false || value.portable !== false
    || !validProposal(value.proposal, context, command.payload, value.source_pixels_sha256 as string)) return null;
  const memory = value.memory;
  if (!object(memory) || !exact(memory, ['resident_input_bytes', 'verification_workspace_bytes', 'total_byte_budget', 'capture_byte_budget', 'measurement_byte_budget', 'estimated_peak_bytes'])
    || !Object.values(memory).every(positiveInteger)) return null;
  const m = memory as ChoiceReport['memory'];
  if (m.capture_byte_budget > m.total_byte_budget || m.measurement_byte_budget > m.total_byte_budget
    || m.estimated_peak_bytes > m.total_byte_budget || m.resident_input_bytes >= m.total_byte_budget
    || value.proposal.memory_admission_bytes > m.measurement_byte_budget
    || m.estimated_peak_bytes < m.resident_input_bytes + m.verification_workspace_bytes + value.proposal.memory_admission_bytes) return null;
  // The engine authenticates Python content/fingerprint hashes. JS does not falsely
  // recompute them with JSON.stringify (different float/int encodings).
  return structuredClone(value) as ChoiceReport;
}
export function measuredReference(report: ChoiceReport, ref: FaceRef): boolean {
  return report.proposal.candidates.some(row => row.status === 'measured' && sameFace(row.face_ref, ref));
}
