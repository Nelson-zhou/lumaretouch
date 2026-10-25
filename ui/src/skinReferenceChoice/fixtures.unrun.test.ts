// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN fixture builders only. Synthetic metadata, never photographic evidence.
import {peopleAssetContext, type FaceRef, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model.ts';
import type {SkinReferenceCatalog} from '../skinReferenceMatch/model.ts';
import type {SkinReferenceBodyCatalog} from '../skinReferenceBody/model.ts';
import {ACTION, BODY_OPERATION, CONTROL_ID, FACE_OPERATION, METHOD, MIN_LOG_GAP,
  type ChoiceCommand, type ChoiceContext, type ChoiceFamily, type ChoiceProposal, type ChoiceReport,
  type ChoiceResult, type MeasuredCandidate} from './model.ts';

export const hash = (digit: string) => digit.repeat(64);
export const face = (id: string): FaceRef => ({asset_sha256: hash('a'), face_instance_id: `face-${id}`, analysis_revision: 3});
const image = () => ({mime: 'image/png' as const, width: 16, height: 16,
  // Flat 16x16 synthetic PNG; only PNG/transport identity is under specification.
  base64: 'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAFElEQVR4nGNoIBEwjGoY1TB8NQAAJYSAEGy7FvQAAAAASUVORK5CYII=',
  sha256: '01d2331ff50b971d55e18aaa7ccc1917c3c319d640d0d9c7fa68cf82bc4460eb'});
export function fixture(family: ChoiceFamily = 'face') {
  const source = {sha256: hash('a'), width: 16, height: 16};
  const source_proof = {asset_sha256: hash('a'), original_sha256: hash('a'), creative_source: null};
  const neutralFace = {version: 1 as const, operation_id: FACE_OPERATION, bank_sha256: hash('b'), reference_face_ref: null,
    target_face_refs: [], amounts: []};
  const neutralBody = {...neutralFace, operation_id: BODY_OPERATION};
  const view: PeopleView = {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: hash('a')},
    revision: 5, association_revision: 2, faces: ['a', 'b'].map((id, i) => ({face_ref: face(id), enabled: true,
      box: [i * .5, 0, (i + 1) * .5, 1], manual: false, analysis_status: 'verified'})),
    groups: {}, persons: {}, links: [], selected_face_id: null, editing_target: null, editing_overrides: {}, resolved: null,
    skin_reference_match: neutralFace, skin_reference_body_match: neutralBody};
  const common = {version: 1 as const, source, source_proof, document_id: view.binding.document_id, revision: '7',
    source_image: image(), source_review_sha256: hash(family === 'face' ? 'c' : 'd'),
    faces: view.faces.map(row => ({face_ref: row.face_ref, box: row.box, enabled: true, available: true, reason: null, amount: 0})),
    automatic_reference: false as const};
  const catalog: SkinReferenceCatalog | SkinReferenceBodyCatalog = family === 'face'
    ? {...common, kind: 'skin_reference_match_catalog', operation_id: FACE_OPERATION, scope: 'current-photo-face-only',
      current: neutralFace, body_matching: false, skin_reference_match_available: true, skin_reference_match_reason: null}
    : {...common, kind: 'skin_reference_body_catalog', operation_id: BODY_OPERATION, scope: 'current-photo-body-only',
      current: neutralBody, body_matching: true, targets: [], skin_reference_body_available: true, skin_reference_body_reason: null};
  const context: ChoiceContext = {family, view, catalog};
  const command: ChoiceCommand = {...peopleAssetContext(view)!, request_id: 'choice-request', action: ACTION,
    payload: {family, source_review_sha256: catalog.source_review_sha256}};
  const candidates: MeasuredCandidate[] = ['a', 'b'].map((id, i) => ({face_ref: face(id), status: 'measured',
    measurement: {log_luminance: Math.log(i ? .2 : .4), linear_luminance: i ? .2 : .4, initial_log_luminance_mad: .1,
      robust_sample_count: 100, robust_weight: 80, effective_samples: 90, retained_weight_fraction: .8},
    source_window: [0, i * 8, 16, 8], support_sha256: hash(i ? '2' : '1'),
    evidence: {backend: 'mediapipe', detector_model_sha256: hash('3'), semantic_model_sha256: hash('4'), landmark_digest: hash(i ? '6' : '5'),
      status: 'verified', source_width: 16, source_height: 16, orientation: 'exif_normalized_once'},
    landmark_digest: hash(i ? '6' : '5'), face_skin_observation: {contract: 'mediapipe-face-skin-edit-weight-v1',
      source_sha256: source.sha256, semantic_model_sha256: hash('4'), producer_width: 16, producer_height: 16},
    protected_face_boxes: 1, protected_actual_face_ovals: 1}));
  const proposal: ChoiceProposal = {version: 1, operation_id: FACE_OPERATION, control_id: CONTROL_ID, method: METHOD, source,
    source_stage: 'immutable-source-before-repair-and-portrait-v1', source_pixels_sha256: hash('7'), source_kind: 'original', source_bits: 16,
    source_encoding: 'encoded-working-srgb-d65-sdr', state_revision: 5, association_revision: 2,
    candidate_scope: 'all-enabled-retained-same-source-faces', census_complete: false, detector_limit_reached: false,
    candidates, read_only_proposal: true, review_required: true, reference_face_exclusion_required: true,
    body_extension_enabled: false, fit_retained: false, portable: false, memory_admission_bytes: 4 * 1024 ** 2,
    limitations: ['not-a-complete-photograph-face-census', 'observed-source-luminance-not-intrinsic-complexion',
      'confidence-is-not-brightness-and-no-demographic-inference', 'unknown-occlusion-and-model-errors-require-visual-review',
      'resampled-semantic-observation-is-not-fresh-full-resolution-inference', 'not-proprietary-metric-parity-or-complete-ai-multi-person-feature'],
    reference_face_ref: face('a'), selection_mode: 'automatic-proposal', automatic_status: 'proposed', automatic_reference_face_ref: face('a'),
    automatic_blockers: [], ranked_face_refs: [face('a'), face('b')], top_log_luminance_gap: Math.log(.4) - Math.log(.2),
    minimum_log_luminance_gap: MIN_LOG_GAP, ambiguous_face_refs: [], proposal_sha256: hash('8')};
  const report: ChoiceReport = {kind: ACTION, version: 1, operation_id: family === 'face' ? FACE_OPERATION : BODY_OPERATION,
    family, target: command.target, document_id: command.document_id, revision: '7', source, source_proof,
    source_review_sha256: catalog.source_review_sha256, source_image_sha256: catalog.source_image.sha256,
    source_pixels_sha256: hash('7'), graph_sha256: hash('9'), analysis_sha256: hash('a'), body_bank_sha256: hash('b'),
    document_snapshot_sha256: hash('c'), skin_reference_choice_request: structuredClone(command.payload), proposal,
    memory: {resident_input_bytes: 1024 ** 2, verification_workspace_bytes: 2 * 1024 ** 2, total_byte_budget: 16 * 1024 ** 2,
      capture_byte_budget: 13 * 1024 ** 2, measurement_byte_budget: 13 * 1024 ** 2, estimated_peak_bytes: 7 * 1024 ** 2},
    read_only_proposal: true, source_image_load_required: true, review_required: true, grants_consent: false,
    render_committed: false, portable: false, report_sha256: hash('e')};
  return {context, command, report, result: result(command, report)};
}
/** Mirrors people_host_commands.finish, not an idealized payload-only result. */
export function result(command: ChoiceCommand, payload?: unknown): ChoiceResult {
  const {request_id: _id, ...echo} = command;
  return {event: 'people_result', protocol: 1, request_id: command.request_id, action: ACTION, document_id: command.document_id,
    success: true, outcome_unknown: false, error: null, created_id: null, batch_id: null, frame_emitted: false,
    skin_reference_choice_request: structuredClone(echo), ...(payload === undefined ? {} : {payload})};
}
export function catalogReceipt(context: ChoiceContext) {
  const command: PeopleAction = {...peopleAssetContext(context.view)!, request_id: `catalog-${context.family}`,
    action: context.family === 'face' ? 'skin_reference_match_catalog' : 'skin_reference_body_catalog', payload: {}};
  const {request_id: _id, ...echo} = command;
  const value = {event: 'people_result', protocol: 1, request_id: command.request_id, action: command.action, document_id: command.document_id,
    success: true, outcome_unknown: false, error: null, created_id: null, batch_id: null, frame_emitted: false,
    [context.family === 'face' ? 'skin_reference_match_request' : 'skin_reference_body_request']: echo, payload: context.catalog};
  // Existing PeopleResult omits canonical transport fields and types error as string;
  // the fixture deliberately preserves the real null-success wire for guards.
  return {command, result: value as unknown as PeopleResult};
}
