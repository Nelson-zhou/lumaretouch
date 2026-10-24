// AUTHORED / UNRUN: no imports, test execution, typecheck, build or photo acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {FACE_STYLES, FACE_STYLE_LABELS, faceStyleBinding, faceStyleLegacyWarning, faceStyleReceiptCurrent,
  faceStyleEchoMatches, faceStyleTargetReady, parseFaceStyleAmount, validFaceStyleReview,
  faceStyleAck, sameFaceStyleAck, type FaceStyleReview} from './model.ts';
function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2, faces: [{face_ref, enabled: true, box: [.1,.1,.6,.8], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref}, editing_overrides: {},
    resolved: {face_ref, state_revision: 5, association_revision: 2, conflicts: [], operations: {'lnx.deform.v1': Object.fromEntries(
      ['/slim_face','/small_chin','/big_eye','/smile'].map(path => [path,{value: 0, scope: 'default', target_id: null, overridden: false}]))}}};
}
function command(v = fixture()): PeopleAction {
  return {document_id: v.binding.document_id, document_epoch: v.binding.document_epoch, document_revision: v.binding.document_revision,
    state_revision: v.revision, association_revision: v.association_revision, request_id: 'request-a', target: v.editing_target!,
    action: 'face_style_preview', payload: {version: 1, style: 'classic', amount: .5}};
}
function result(c = command()): PeopleResult {
  const {request_id: _, ...echo} = c;
  return {protocol: 1, request_id: c.request_id, document_id: c.document_id, action: c.action, success: true,
    outcome_unknown: false, face_style_request: echo};
}
function review(v = fixture()): FaceStyleReview {
  const source_proof = {asset_sha256: v.binding.asset_sha256, original_sha256: v.binding.asset_sha256, creative_source: null};
  return {version: 1, token: 'f'.repeat(32), recipe: {version: 1, style: 'classic', amount: .5}, face_ref: v.editing_target!.face_ref!,
    patches_sha256: '1'.repeat(64), review_sha256: '2'.repeat(64), owner: {document: {document_id: v.binding.document_id,
      epoch: v.binding.document_epoch, revision: 7}, people_scope: v.binding.document_id, state_revision: 5, association_revision: 2,
      graph_sha256: '3'.repeat(64), source_proof}, visual: {version: 1, document_id: v.binding.document_id, revision: '7', source_proof,
      before_state_sha256: '4'.repeat(64), candidate_state_sha256: '5'.repeat(64), before_people_sha256: '6'.repeat(64), candidate_people_sha256: '7'.repeat(64),
      source_size: [400,300], before_output_size: [400,300], after_output_size: [400,300],
      before: {mime: 'image/png', width: 400, height: 300, sha256: '8'.repeat(64)}, after: {mime: 'image/png', width: 400, height: 300, sha256: '9'.repeat(64)}}};
}
test('seven new codes stay distinct from Chinese legacy recipe keys; display range is explicit', () => {
  assert.equal(FACE_STYLES.length, 7); assert.equal(FACE_STYLE_LABELS.classic, '经典');
  assert.equal(parseFaceStyleAmount('0'), 0); assert.equal(parseFaceStyleAmount('100'), 1); assert.equal(parseFaceStyleAmount('25'), .25);
  for (const value of ['', ' ', '-1', '101', 'NaN', 'Infinity', '0x10']) assert.equal(parseFaceStyleAmount(value), null);
});
test('current face only; active legacy is a disclosure, not a blanket preview veto', () => {
  const v = fixture(); assert.equal(faceStyleTargetReady(v), true); assert.equal(faceStyleLegacyWarning(v), null);
  const original = JSON.stringify(v); v.resolved!.operations['lnx.deform.v1']['/slim_face'].value = .2;
  const blocked = JSON.stringify(v); assert.ok(faceStyleLegacyWarning(v)); assert.equal(faceStyleTargetReady(v), true); assert.equal(JSON.stringify(v), blocked); assert.notEqual(blocked, original);
  v.resolved!.operations['lnx.deform.v1']['/slim_face'].value = 0;
  v.resolved!.operations['lnx.deform.v1']['/smile'].value = .1;
  assert.ok(faceStyleLegacyWarning(v)); assert.equal(faceStyleTargetReady(v), true);
  const zero = review(v); zero.recipe.amount = 0;
  assert.equal(validFaceStyleReview(zero, v, zero.recipe), true); // Backend, not a blanket UI rule, decides merged-recipe compatibility.
  assert.equal(faceStyleTargetReady({...v, editing_target: {...v.editing_target!, scope: 'person'}}), false);
  assert.notEqual(faceStyleBinding(v), faceStyleBinding({...v, revision: 6}));
});
test('read receipts bind exact echoed action payload target and revisions without fabricated doc_state', () => {
  const c = command(), r = result(c); assert.equal(faceStyleEchoMatches(c, r), true); assert.equal(faceStyleReceiptCurrent(c, r, fixture()), true);
  assert.equal(faceStyleEchoMatches(c, {...r, face_style_request: undefined}), false);
  assert.equal(faceStyleEchoMatches(c, {...r, face_style_request: {...r.face_style_request!, payload: {...c.payload, amount: .6}}}), false);
  assert.equal(faceStyleReceiptCurrent(c, r, {...fixture(), revision: 6}), false);
  assert.equal(faceStyleReceiptCurrent(c, {...r, outcome_unknown: true}, fixture()), false);
});
test('review binds real source owner face recipe and compact full-output extents', () => {
  const v = fixture(), r = review(v); assert.equal(validFaceStyleReview(r, v, r.recipe), true);
  assert.equal(validFaceStyleReview(r, v, {...r.recipe, amount: .6}), false);
  assert.equal(validFaceStyleReview({...r, face_ref: {...r.face_ref, analysis_revision: 4}}, v, r.recipe), false);
  assert.equal(validFaceStyleReview({...r, owner: {...r.owner, document: {...r.owner.document, epoch: 'old'}}}, v, r.recipe), false);
  assert.equal(validFaceStyleReview({...r, visual: {...r.visual, before: {...r.visual.before, width: 399}}}, v, r.recipe), false);
  assert.equal(validFaceStyleReview({...r, visual: {...r.visual, coverage_sha256: 'a'.repeat(64)}}, v, r.recipe), false);
  const ack = faceStyleAck(r); assert.equal(sameFaceStyleAck(ack, ack), true);
  assert.equal(sameFaceStyleAck({...ack, after_sha256: '0'.repeat(64)}, ack), false);
  assert.equal(sameFaceStyleAck({...ack, reviewed: true}, ack), false);
});
