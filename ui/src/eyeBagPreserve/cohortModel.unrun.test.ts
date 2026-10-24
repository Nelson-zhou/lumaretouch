// AUTHORED / UNRUN. No tests, typecheck, build, runtime or photo acceptance executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sameAssociationRequest, validCapsule} from '../people/associationProof';
import {eyeBagCohortPolicy, validEyeBagCohortPolicy} from './cohortPolicy';
import {eyeBagCohortTargets, validEyeBagCohort, eyeBagCohortAck, validEyeBagCohortAck, verifyEyeBagCohortCoverage,
  eyeBagCohortImagesReady, eyeBagCohortReviewKey} from './cohortModel';
import {eyeCohortFixture} from './cohortFixture.unrun.test';
test('exact source-first member policies are explicit, non-portable and not capsule intent', () => {
  const f = eyeCohortFixture(), ids = [f.sourceId, f.targetId];
  assert.equal(eyeBagCohortPolicy(ids, {[f.targetId]: true}), undefined);
  assert.equal(validEyeBagCohortPolicy(f.people.eye_bag_cohort, ids), true);
  for (const mutate of [(p: any) => {p.members.reverse();}, (p: any) => {p.members[0].replace_legacy = 'false';},
    (p: any) => {p.source_masks = {};}, (p: any) => {p.members[0].analysis = {};}, (p: any) => {p.members.pop();}]) {
    const candidate = structuredClone(f.people); mutate(candidate.eye_bag_cohort);
    assert.equal(sameAssociationRequest(candidate, f.people), false);
  }
  const {operation: _, ...content} = f.plan.persistent_association;
  const capsule = {...content, local_document_id: f.sourceId};
  assert.equal(validCapsule(capsule), true);
  assert.equal(validCapsule({...capsule, eye_bag_cohort: f.people.eye_bag_cohort}), false);
});
test('create, generic patch, unlink and target-local retained active opt-in all cover source and every member', async () => {
  for (const operation of ['create', 'patch', 'unlink'] as const) {
    const f = eyeCohortFixture(operation, operation !== 'create');
    assert.equal(validEyeBagCohort(f.plan, f.people), true);
    const targets = eyeBagCohortTargets(f.plan); assert.equal(targets[0].source, true); assert.equal(targets.length, 2);
    for (const target of targets) assert.equal(await verifyEyeBagCohortCoverage(target.visual, target.coverage), true);
    assert.equal(validEyeBagCohortAck(eyeBagCohortAck(targets), targets), true);
    assert.equal(validEyeBagCohortAck(eyeBagCohortAck(targets).slice(1), targets), false);
    assert.equal(validEyeBagCohortAck(eyeBagCohortAck(targets).reverse(), targets), false);
  }
  const retained = eyeCohortFixture('patch', true, false, true);
  assert.equal(validEyeBagCohort(retained.plan, retained.people), true);
});
test('missing either side, borrowed support, extra data, image drift and missing source never grant review', () => {
  for (const mutate of [(f: any) => {delete f.plan.eye_bag_cohort;}, (f: any) => {delete f.people.eye_bag_cohort;},
    (f: any) => {delete f.plan.association_source.association.eye_bag_cohort;},
    (f: any) => {delete f.plan.targets[0].association.eye_bag_cohort.before;},
    (f: any) => {f.plan.targets[0].association.eye_bag_cohort.before.sides = [];},
    (f: any) => {f.plan.targets[0].association.eye_bag_cohort.after.recovery = {};},
    (f: any) => {f.plan.targets[0].association.eye_bag_cohort.face_ref.analysis_revision++;},
    (f: any) => {f.plan.targets[0].association.eye_bag_cohort_visual.before.sha256 = '0'.repeat(64);}]) {
    const f = eyeCohortFixture('patch', true, true); mutate(f); assert.equal(validEyeBagCohort(f.plan, f.people), false);
  }
});
test('review images and policy cannot revive across request or policy changes', () => {
  const f = eyeCohortFixture(), targets = eyeBagCohortTargets(f.plan), ready = Object.fromEntries(targets.map(t => [eyeBagCohortReviewKey('token:request', t), true]));
  assert.equal(eyeBagCohortImagesReady('token:request', targets, ready), true);
  assert.equal(eyeBagCohortImagesReady('token:new', targets, ready), false);
  const changed = structuredClone(targets); changed[0].coverage.replace_legacy = true;
  assert.equal(eyeBagCohortImagesReady('token:request', changed, ready), false);
});
