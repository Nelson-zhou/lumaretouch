// AUTHORED / UNRUN. These synthetic source fixtures have not been executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {samePeopleRequest, validPeopleReview} from '../people/transferProof';
import {eyeBatchFixture} from './batchFixture.unrun.test';
import {eyeBagBatchPolicy, sameEyeBagBatchPolicy, validEyeBagBatchPolicy, validEyeBagBatchCoverage,
  validEyeBagBatchReview, eyeBagBatchReviewKey, eyeBagBatchImagesReady, validEyeBagBatchAck, sameEyeBagBatchAck,
  verifyEyeBagBatchCoverage} from './batchModel';

test('each target requires an explicit boolean; missing, duplicate, extra, donor-support and nonboolean policies refuse', () => {
  const f = eyeBatchFixture({count: 2}), policy = f.people.eye_bag!;
  assert.equal(eyeBagBatchPolicy(f.ids, {[f.ids[0]]: false}), undefined);
  assert.deepEqual(eyeBagBatchPolicy(f.ids, {[f.ids[0]]: false, [f.ids[1]]: true})?.targets.map(row => row.replace_legacy), [false, true]);
  assert.equal(validEyeBagBatchPolicy(policy, f.ids), true);
  for (const mutate of [(p: any) => p.targets.pop(), (p: any) => p.targets.push(p.targets[0]),
    (p: any) => {p.targets[0].replace_legacy = 0;}, (p: any) => {p.targets[0].document_id = 'd'.repeat(32);},
    (p: any) => {p.targets[0].support = {};}, (p: any) => {p.version = 2;}]) {
    const bad = structuredClone(policy); mutate(bad); assert.equal(validEyeBagBatchPolicy(bad, f.ids), false);
  }
  assert.equal(sameEyeBagBatchPolicy({...policy, targets: [...policy.targets].reverse()}, policy, f.ids), true);
  assert.equal(samePeopleRequest(f.people, f.people), true);
  assert.equal(samePeopleRequest({...f.people, eye_bag: {...policy, targets: policy.targets.map(row => ({...row, replace_legacy: true}))}}, f.people), false);
});
test('exact target refs, existing own protection, sorted sides and neutral disclosure are mandatory', () => {
  const f = eyeBatchFixture(), r = f.evidence[0], coverage = r.eye_bag_coverage!;
  assert.equal(validPeopleReview(r, f.people, f.people.source, {document_id: f.ids[0], revision: '20'}), true);
  assert.equal(validEyeBagBatchCoverage(coverage, r.target_refs), true);
  for (const mutate of [(c: any) => {c.support_transfer = 'source';}, (c: any) => c.targets.push(c.targets[0]),
    (c: any) => {c.targets[0].face_ref.analysis_revision++;}, (c: any) => {c.targets[0].ridge_sha256 = null;},
    (c: any) => {c.targets[0].sides = ['right', 'left'];}, (c: any) => {c.targets[0].sides = ['left', 'left'];},
    (c: any) => {c.targets[0].scope = 'face-only';}, (c: any) => {c.targets[0].recovery = {};},
    (c: any) => {c.targets[0].scope = 'neutral-no-effect';}]) {
    const bad = structuredClone(coverage); mutate(bad); assert.equal(validEyeBagBatchCoverage(bad, r.target_refs), false);
  }
  const neutral = eyeBatchFixture({amount: 0, replaceLegacy: true});
  assert.equal(validEyeBagBatchReview(neutral.evidence[0], true), true);
  assert.equal(validEyeBagBatchReview(r, true), false);
  assert.equal(validEyeBagBatchReview(eyeBatchFixture({preserveOnly: true}).evidence[0], false), true);
});
test('no selected effect is silently dropped; active selected legacy conflicts even when replacement authorized', () => {
  const f = eyeBatchFixture({mixed: true, replaceLegacy: true}), r = f.evidence[0];
  assert.equal(validPeopleReview(r, f.people, f.people.source, {document_id: f.ids[0], revision: '20'}), true);
  r.parameters.push({operation_id: 'lnx.enhance.v1', parameter_path: '/eye_bags', value: .4});
  assert.equal(validEyeBagBatchReview(r, true), false);
  r.parameters.pop(); r.collarbone_visual!.after.sha256 = '9'.repeat(64);
  assert.equal(validEyeBagBatchReview(r, true), false);
});
test('eye evidence is forbidden without envelope; only explicit neutral reset can use compatibility shape', () => {
  const f = eyeBatchFixture({amount: 0}), r = f.evidence[0]; delete f.people.eye_bag;
  assert.equal(validPeopleReview(r, f.people, f.people.source, {document_id: f.ids[0], revision: '20'}), false);
  delete r.eye_bag; delete r.eye_bag_coverage; delete r.eye_bag_visual;
  assert.equal(validPeopleReview(r, f.people, f.people.source, {document_id: f.ids[0], revision: '20'}), true);
  r.parameters.find(leaf => leaf.parameter_path === '/amount')!.value = .5;
  assert.equal(validPeopleReview(r, f.people, f.people.source, {document_id: f.ids[0], revision: '20'}), false);
});
test('coverage digest binds actual disclosure and ordered ACK binds policy and all PNG pairs', async () => {
  const f = eyeBatchFixture({count: 2}), r = f.evidence[0];
  assert.equal(await verifyEyeBagBatchCoverage(r.eye_bag_visual!, r.eye_bag_coverage!), true);
  assert.equal(validEyeBagBatchAck(f.ack, f.evidence), true);
  assert.equal(validEyeBagBatchAck([...f.ack].reverse(), f.evidence), false);
  assert.equal(validEyeBagBatchAck([f.ack[0], f.ack[0]], f.evidence), false);
  assert.equal(sameEyeBagBatchAck([], []), false);
  for (const field of ['document_id', 'revision', 'before_sha256', 'after_sha256', 'coverage_sha256', 'replace_legacy']) {
    assert.equal(validEyeBagBatchAck([{...f.ack[0], [field]: 'wrong'}, f.ack[1]], f.evidence), false);
  }
  const key = eyeBagBatchReviewKey('token:request', r.eye_bag_visual!, r.eye_bag!), ready = {[key]: true};
  assert.equal(eyeBagBatchImagesReady('token:request', [r], ready), true);
  assert.equal(eyeBagBatchImagesReady('token:other', [r], ready), false);
  assert.equal(eyeBagBatchImagesReady('token:request', [{...r, eye_bag: {version: 1, replace_legacy: true}}], ready), false);
});
