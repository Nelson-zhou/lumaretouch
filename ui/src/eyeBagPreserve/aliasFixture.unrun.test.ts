// AUTHORED / UNRUN. Tiny synthetic contract fixtures, never photographic quality evidence.
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model';
import type {SpillImage} from '../spillRemoval/model';
import {ack, OPERATION_ID, type EyeBagAliasCommit, type EyeBagCandidate, type EyeBagReviewV1, type EyeBagReviewV2} from './model';
import {emptyMask} from './support';
export function aliasFixture() {
  const pngs = [
    ['iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAADklEQVR4nGMIAAMGCAUAGk4DwSPol3sAAAAASUVORK5CYII=', '914920843d89e4d18390520ffc904d266204e4a8811b434e2bd6b1a1998782b4'],
    ['iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGMICQoAIgYIBQAbBgPZYhAyRwAAAABJRU5ErkJggg==', 'effd308e0df2d30945f0b283fa4e178901d0d4b21bf1af7d657a8d8bb9cadc2c'],
    ['iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGPw8QsAIgYIBQAZlgOppp3+1AAAAABJRU5ErkJggg==', '1032463dd902bc9d5c689329f63dccf2e377ca205e2b5d0518112c9836aea142'],
    ['iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR4nGMICgwAIgYIBQAaqgPNjz896AAAAABJRU5ErkJggg==', '8a942fd6565b36209f6be6fe1d1bb76d81db0dac71a940797ff88516c84021b3'],
  ].map(([base64, sha256]): SpillImage => ({mime: 'image/png', width: 2, height: 2, base64, sha256}));
  const compact = (index: number) => {const {base64: _, ...value} = pngs[index]; return value;};
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face', analysis_revision: 2};
  const source = {sha256: face_ref.asset_sha256, width: 2, height: 2};
  const view: PeopleView = {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 11, association_revision: 3, faces: [{face_ref, enabled: true, box: [.1, .1, .8, .8], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: 'face', resolved: {face_ref, state_revision: 11, association_revision: 3, operations: {}, conflicts: []},
    editing_target: {scope: 'face', target_id: 'face', face_ref}, editing_overrides: {}};
  const source_proof = {asset_sha256: face_ref.asset_sha256, original_sha256: face_ref.asset_sha256, creative_source: null};
  const recipe = {version: 2 as const, amount: .6, preserve: 1};
  const single: EyeBagReviewV1 = {version: 1, token: 'c'.repeat(32), recipe, owner: {
    document: {document_id: view.binding.document_id, epoch: 'epoch', revision: 7}, people_scope: 'project', state_revision: 11,
    association_revision: 3, graph_sha256: 'b'.repeat(64), source_proof}, face_ref, support_sha256: 'e'.repeat(64), candidate_state_revision: 15,
    replace_legacy: true, review_sha256: 'f'.repeat(64), support_overlay: compact(0),
    support_source: {source_width: 2, source_height: 2, decoded_width: 2, decoded_height: 2},
    visual: {version: 1, document_id: view.binding.document_id, revision: '7', source_proof,
      before_state_sha256: '1'.repeat(64), candidate_state_sha256: '2'.repeat(64), before_people_sha256: '3'.repeat(64), candidate_people_sha256: '4'.repeat(64),
      source_size: [2, 2], before_output_size: [2, 2], after_output_size: [2, 2], before: compact(0), after: compact(1)}};
  const review: EyeBagReviewV2 = {...single, version: 2, members: [{path: '/photos/current.png', visual: structuredClone(single.visual)},
    {path: '/photos/alias.png', visual: {...structuredClone(single.visual), document_id: 'e'.repeat(32), revision: '9',
      source_proof: {asset_sha256: face_ref.asset_sha256, original_sha256: 'b'.repeat(64), creative_source: {sha256: face_ref.asset_sha256, width: 2, height: 2}},
      before_state_sha256: '8'.repeat(64), candidate_state_sha256: '9'.repeat(64), before: compact(2), after: compact(3)}}]};
  const mask = emptyMask(); mask.objects.push({id: 'left', name: 'left', enabled: true, kind: 'brush', operation: 'add', opacity: 1,
    feather: 0, points: [[.5, .5]], axes: [[.01, 0], [0, .01]]});
  const candidate: EyeBagCandidate = {recipe, replace_legacy: true, eyes: {left: {recipe: mask, visible: true, unoccluded: true, ownership_confirmed: true}}};
  const context = {document_id: view.binding.document_id, document_epoch: 'epoch', document_revision: 7, state_revision: 11,
    association_revision: 3, target: view.editing_target!};
  const command: PeopleAction = {...context, request_id: 'confirm', action: 'eye_bag_confirm', payload: {token: review.token, ack: ack(review)}};
  const next = structuredClone(view); next.binding.document_revision = 8; next.revision = 15; next.resolved!.state_revision = 15;
  const parameter = (value: number) => ({value, scope: 'face' as const, target_id: 'face', overridden: true});
  next.resolved!.operations = {[OPERATION_ID]: {'/amount': parameter(.6), '/preserve': parameter(1)}, 'lnx.enhance.v1': {'/eye_bags': parameter(0)}};
  next.eye_bag_preserve = {recipe, source, face_ref, legacy_amount: 0, reviewed: true, reviewed_eyes: ['left'], support_sha256: review.support_sha256,
    support_error: null, conflicts: [], changed_pixels: 1, suspended: null};
  const {request_id: requestId, ...eye_bag_request} = command;
  const result: PeopleResult = {protocol: 1, request_id: requestId, action: command.action, document_id: command.document_id, success: true,
    outcome_unknown: false, batch_id: 'eye-alias-batch', doc_state: {people: next}, eye_bag_request,
    payload: {kind: 'eye_bag_confirm', token: review.token, review_sha256: review.review_sha256, ack: ack(review), recipe,
      support_sha256: review.support_sha256, replace_legacy: true, candidate_state_revision: 15,
      alias_members: review.members.map(({visual}) => ({document_id: visual.document_id, expected_revision: visual.revision,
        result_revision: String(BigInt(visual.revision) + 1n)}))}};
  const commit: EyeBagAliasCommit = {batchId: result.batch_id!, documentEpoch: 'epoch', requestId, review, command, result};
  return {view, next, single, review, candidate, command, context, result, commit, pngs};
}
