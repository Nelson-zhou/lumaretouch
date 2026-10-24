// AUTHORED / UNRUN. Synthetic 2×2 receipt fixture, never photographic acceptance.
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {command, OP, type ReferenceProof} from './model.ts';
export const png = 'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGMIAAMGCAUAGk4DwSPol3sAAAAASUVORK5CYII=';
export const pngSha = '914920843d89e4d18390520ffc904d266204e4a8811b434e2bd6b1a1998782b4';
export function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  const source = {sha256: face_ref.asset_sha256, width: 2, height: 2};
  const proof: ReferenceProof = {source, face_ref, landmark_digest: 'b'.repeat(64), preview_sha256: pngSha, reference_request_id: 'reference-request'};
  return {binding: {document_id: 'doc-a', document_epoch: 'epoch-a', document_revision: 7, asset_sha256: source.sha256},
    revision: 4, association_revision: 2, faces: [{face_ref, enabled: true, manual: false, box: [.1,.1,.9,.9], analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref},
    editing_overrides: {[OP]: {'/pattern': 'freckle_dust', '/strength': .3}},
    resolved: {face_ref, state_revision: 4, association_revision: 2, conflicts: [], operations: {
      [OP]: {'/pattern': {value: 'freckle_dust', scope: 'face', target_id: 'face-a', overridden: true},
        '/strength': {value: .3, scope: 'face', target_id: 'face-a', overridden: true}}}},
    face_decoration: {recipe: {version: 1, pattern: 'freckle_dust', strength: .3}, source, face_ref,
      native_available: true, support_available: true, support_reason: null, suspended: null, reviewed: true,
      landmark_digest: proof.landmark_digest, support_sha256: 'c'.repeat(64), reference_proof: proof, facts: {},
      source_preview: {mime: 'image/png', base64: png, sha256: pngSha, source_sha256: source.sha256,
        source_width: 2, source_height: 2, decoded_width: 2, decoded_height: 2, width: 2, height: 2,
        mapping: 'normalized_full_frame', orientation: 'exif_normalized_once'}}};
}
export function reference(view = fixture()): PeopleAction {return command(view, 'face_decoration_reference', 'reference-request', {});}
export function receipt(request = reference(), view = fixture()): PeopleResult {
  const {request_id: _id, ...echo} = request;
  return {protocol: 1, request_id: request.request_id, action: request.action, document_id: request.document_id,
    success: true, outcome_unknown: false, face_decoration_request: echo, doc_state: {people: view},
    payload: {kind: 'face_decoration_reference', reference_proof: view.face_decoration!.reference_proof}};
}
