// AUTHORED / UNRUN. No imports, tests, typecheck or build executed while authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validPeopleReview, validSkinColourCoverage, type SkinColourCoverage} from './transferProof.ts';
import {request, review, targetId} from './transferFixtureData.test.ts';

function fixture(scope: SkinColourCoverage['targets'][number]['scope'] = 'face-only') {
  const req = request(), value = review();
  req.selection = {'lnx.skin_colour.v1': ['/temperature']};
  value.parameters = [{operation_id: 'lnx.skin_colour.v1', parameter_path: '/temperature', value: scope === 'neutral-no-effect' ? 0 : .4}];
  value.skin_colour_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]}, scope,
    body_review_sha256: scope === 'face-and-reviewed-body' ? 'f'.repeat(64) : null}]};
  return {req, value, target: {document_id: targetId, revision: '20'}};
}

test('skin-colour review requires exact target coverage before it becomes committable', () => {
  for (const scope of ['face-only', 'face-and-reviewed-body', 'neutral-no-effect'] as const) {
    const {req, value, target} = fixture(scope);
    assert.equal(validPeopleReview(value, req, req.source, target), true);
    delete value.skin_colour_coverage;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('coverage cannot invent transferred supports, another face or an omitted target', () => {
  for (const mutate of [
    (v: any) => {v.support_transfer = 'copied';},
    (v: any) => {v.targets = [];},
    (v: any) => {v.targets.push(structuredClone(v.targets[0]));},
    (v: any) => {v.targets[0].face_ref.analysis_revision++;},
    (v: any) => {v.targets[0].face_ref.asset_sha256 = 'a'.repeat(64);},
    (v: any) => {v.targets[0].scope = 'whole-body';},
    (v: any) => {v.targets[0].body_review_sha256 = null;},
    (v: any) => {v.targets[0].body_review_sha256 = 'bad';},
    (v: any) => {v.targets[0].mask = [1, 1];},
    (v: any) => {v.targets[0].body_ref = {};},
    (v: any) => {v.source_support = {};},
  ]) {
    const {req, value, target} = fixture('face-and-reviewed-body'); mutate(value.skin_colour_coverage);
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('face-only and neutral entries cannot claim a body-support hash', () => {
  for (const scope of ['face-only', 'neutral-no-effect'] as const) {
    const {value} = fixture(scope); value.skin_colour_coverage!.targets[0].body_review_sha256 = 'f'.repeat(64);
    assert.equal(validSkinColourCoverage(value.skin_colour_coverage, value.target_refs), false);
  }
});
test('a nonzero transferred scalar cannot be disclosed as no effect', () => {
  const {req, value, target} = fixture('neutral-no-effect'); value.parameters[0].value = -.4;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
  for (const amount of ['0.4', true, 1.1, -1.1]) {
    value.skin_colour_coverage!.targets[0].scope = 'face-only'; value.parameters[0].value = amount;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('mixed target extents must independently match every selected face', () => {
  const {value} = fixture();
  const other = {...value.target_refs[0], face_instance_id: 'another-target-face'};
  value.target_refs.push(other);
  value.skin_colour_coverage!.targets.push({face_ref: other, scope: 'face-and-reviewed-body', body_review_sha256: 'e'.repeat(64)});
  assert.equal(validSkinColourCoverage(value.skin_colour_coverage, value.target_refs), true);
  value.skin_colour_coverage!.targets[1].face_ref = {...value.target_refs[0]};
  assert.equal(validSkinColourCoverage(value.skin_colour_coverage, value.target_refs), false);
});
test('unrelated transfers retain compatibility but reject unexplained coverage claims', () => {
  const req = request(), value = review(), target = {document_id: targetId, revision: '20'};
  assert.equal(validPeopleReview(value, req, req.source, target), true);
  value.skin_colour_coverage = fixture().value.skin_colour_coverage;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
});
test('coverage disclosure is open for both transfer policies and denies automatic whole-body claims', () => {
  const source = readFileSync(new URL('./transferReview.tsx', import.meta.url), 'utf8');
  assert.ok(source.includes('open={explicit || !!value.skin_colour_coverage || !!value.skin_finish_coverage || !!value.body_skin_evenness_coverage}'));
  assert.ok(source.includes('身体审核不随源图或预设复制'));
  assert.ok(source.includes('不会继承源图的身体范围'));
  assert.ok(source.includes('不是自动全身分割'));
  assert.ok(source.includes('不据此声明身体审核有效'));
});
