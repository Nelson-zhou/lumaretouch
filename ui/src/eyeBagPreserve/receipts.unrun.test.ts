// AUTHORED / UNRUN. Frozen-contract fixtures, not executed proof.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createPeopleWorkflow} from '../people/workflow.ts';
import {peopleContext, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model.ts';
import {ack, echoMatches, validConfirmation, type EyeBagReview} from './model.ts';
const face = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face', analysis_revision: 2};
const source = {sha256: face.asset_sha256, width: 4000, height: 3000};
const recipe = {version: 2 as const, amount: .6, preserve: 1};
function view(): PeopleView {
  return {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: face.asset_sha256},
    revision: 11, association_revision: 3, faces: [{face_ref: face, enabled: true, box: [.2, .2, .6, .6], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: 'face', resolved: {face_ref: face, state_revision: 11, association_revision: 3, operations: {}, conflicts: []},
    editing_target: {scope: 'face', target_id: 'face', face_ref: face}, editing_overrides: {}};
}
function review(): EyeBagReview {
  const owner = {document: {document_id: 'd'.repeat(32), epoch: 'epoch', revision: 7}, people_scope: 'd'.repeat(32),
    state_revision: 11, association_revision: 3, graph_sha256: 'b'.repeat(64),
    source_proof: {asset_sha256: face.asset_sha256, original_sha256: face.asset_sha256, creative_source: null}};
  const png = (c: string) => ({mime: 'image/png' as const, width: 1024, height: 768, sha256: c.repeat(64)});
  return {version: 1, token: 'c'.repeat(32), recipe, owner, face_ref: face, support_sha256: 'e'.repeat(64), candidate_state_revision: 15,
    replace_legacy: true, review_sha256: 'f'.repeat(64), support_overlay: png('8'),
    support_source: {source_width: 4000, source_height: 3000, decoded_width: 4000, decoded_height: 3000},
    visual: {version: 1, document_id: owner.document.document_id, revision: '7', source_proof: owner.source_proof,
      before_state_sha256: '1'.repeat(64), candidate_state_sha256: '2'.repeat(64), before_people_sha256: '3'.repeat(64), candidate_people_sha256: '4'.repeat(64),
      source_size: [4000, 3000], before_output_size: [4000, 3000], after_output_size: [4000, 3000], before: png('6'), after: png('7')}};
}
function confirmed(): PeopleResult {
  const frozen = review(), next = view(); next.binding.document_revision = 8; next.revision = 15;
  next.resolved = {face_ref: face, state_revision: 15, association_revision: 3, conflicts: [], operations: {
    'lnx.eye_bags.v2': {'/amount': {value: .6, scope: 'face', target_id: 'face', overridden: true}, '/preserve': {value: 1, scope: 'face', target_id: 'face', overridden: true}},
    'lnx.enhance.v1': {'/eye_bags': {value: 0, scope: 'face', target_id: 'face', overridden: true}}}};
  next.eye_bag_preserve = {recipe, source, face_ref: face, legacy_amount: 0, reviewed: true, reviewed_eyes: ['left'],
    support_sha256: frozen.support_sha256, support_error: null, conflicts: [], changed_pixels: 40, suspended: null};
  return {protocol: 1, action: 'eye_bag_confirm', request_id: 'confirm', document_id: next.binding.document_id,
    success: true, outcome_unknown: false, doc_state: {people: next}, payload: {kind: 'eye_bag_confirm', token: frozen.token,
      review_sha256: frozen.review_sha256, recipe, support_sha256: frozen.support_sha256, replace_legacy: true,
      candidate_state_revision: 15, ack: ack(frozen)}};
}
test('confirmation proves one document transition and exact recipe/support graph', () => {
  assert.equal(validConfirmation(review(), confirmed()), true);
  const faults = [
    (r: PeopleResult) => {r.doc_state!.people!.binding.document_revision = 9;},
    (r: PeopleResult) => {r.doc_state!.people!.revision = 16;},
    (r: PeopleResult) => {r.doc_state!.people!.eye_bag_preserve!.support_sha256 = '0'.repeat(64);},
    (r: PeopleResult) => {r.doc_state!.people!.eye_bag_preserve!.legacy_amount = .4;},
    (r: PeopleResult) => {r.doc_state!.people!.eye_bag_preserve!.recipe = {...recipe, preserve: 0};},
  ];
  for (const change of faults) {const result = confirmed(); change(result); assert.equal(validConfirmation(review(), result), false);}
});
test('request echo binds exact source, revisions, target and payload', () => {
  const command: PeopleAction = {...peopleContext(view())!, request_id: 'read', action: 'eye_bag_reference', payload: {}};
  const {request_id: _id, ...echo} = command;
  const result = {...confirmed(), eye_bag_request: echo};
  assert.equal(echoMatches(command, result), true);
  assert.equal(echoMatches(command, {...result, eye_bag_request: {...echo, document_revision: 8}}), false);
});
test('unknown result remains query-only and is never auto-resubmitted', async () => {
  let sends = 0, reads = 0;
  const model = view(), command: PeopleAction = {...peopleContext(model)!, request_id: 'unknown', action: 'eye_bag_reference', payload: {}};
  const workflow = createPeopleWorkflow({send: async () => {sends++;}, refresh: async () => {}, read: async request_id => {
    reads++; return {phase: 'done', request_id, result: {protocol: 1, request_id, action: command.action,
      document_id: command.document_id, success: false, outcome_unknown: true, error: 'not established'}};
  }});
  workflow.update(model, true); await assert.rejects(workflow.submit(command));
  assert.equal(workflow.snapshot().uncertain, true); await assert.rejects(workflow.check());
  assert.equal(sends, 1); assert.equal(reads, 2);
});
