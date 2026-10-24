// AUTHORED / UNRUN. No imports, tests, typecheck or build executed while authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validPeopleReview, validSkinFinishCoverage, type SkinFinishCoverage} from './transferProof.ts';
import {request, review, targetId} from './transferFixtureData.test.ts';

function fixture(scope: SkinFinishCoverage['targets'][number]['scope'] = 'face-only') {
  const req = request(), value = review();
  req.selection = {'lnx.skin_finish.v1': ['/whitening']};
  value.parameters = [{operation_id: 'lnx.skin_finish.v1', parameter_path: '/whitening', value: scope === 'neutral-no-effect' ? 0 : .4}];
  value.skin_finish_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]}, scope,
    body_review_sha256: scope === 'face-and-reviewed-body' ? 'f'.repeat(64) : null}]};
  return {req, value, target: {document_id: targetId, revision: '20'}};
}

test('finish review requires independently keyed exact target coverage', () => {
  for (const scope of ['face-only', 'face-and-reviewed-body', 'neutral-no-effect'] as const) {
    const {req, value, target} = fixture(scope);
    assert.equal(validPeopleReview(value, req, req.source, target), true);
    value.skin_colour_coverage = value.skin_finish_coverage;
    delete value.skin_finish_coverage;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
    delete value.skin_colour_coverage;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('finish coverage cannot transport supports or change or omit exact target identity', () => {
  for (const mutate of [
    (v: any) => {v.support_transfer = 'copied';},
    (v: any) => {v.targets = [];},
    (v: any) => {v.targets.push(structuredClone(v.targets[0]));},
    (v: any) => {v.targets[0].face_ref.analysis_revision++;},
    (v: any) => {v.targets[0].face_ref.asset_sha256 = 'a'.repeat(64);},
    (v: any) => {v.targets[0].scope = 'whole-body';},
    (v: any) => {v.targets[0].body_review_sha256 = null;},
    (v: any) => {v.targets[0].body_review_sha256 = 'bad';},
    (v: any) => {v.targets[0].body_ref = {};},
    (v: any) => {v.targets[0].mask = [1, 1];},
    (v: any) => {v.source_support = {};},
  ]) {
    const {req, value, target} = fixture('face-and-reviewed-body'); mutate(value.skin_finish_coverage);
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('finish scalars are finite unsigned amounts, not signed temperature or tint aliases', () => {
  for (const amount of ['0.4', true, -1, -.01, 1.01, NaN, Infinity]) {
    const {req, value, target} = fixture(); value.parameters[0].value = amount;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
  for (const path of ['/temperature', '/tint', '/version', '/body_ref', '/mask']) {
    const {req, value, target} = fixture();
    req.selection['lnx.skin_finish.v1'] = [path]; value.parameters[0].parameter_path = path;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
  for (const amount of [0, .5, 1]) {
    const {req, value, target} = fixture(); value.parameters[0].value = amount;
    assert.equal(validPeopleReview(value, req, req.source, target), true);
  }
});
test('nonzero finish cannot claim no effect, but a partial zero leaf need not mean neutral', () => {
  const {req, value, target} = fixture('neutral-no-effect'); value.parameters[0].value = .3;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
  value.parameters[0].value = 0; value.skin_finish_coverage!.targets[0].scope = 'face-only';
  assert.equal(validPeopleReview(value, req, req.source, target), true);
});
test('face-only and neutral finish cannot claim a body support hash', () => {
  for (const scope of ['face-only', 'neutral-no-effect'] as const) {
    const {value} = fixture(scope); value.skin_finish_coverage!.targets[0].body_review_sha256 = 'f'.repeat(64);
    assert.equal(validSkinFinishCoverage(value.skin_finish_coverage, value.target_refs), false);
  }
});
test('each selected finish target independently discloses its extent', () => {
  const {value} = fixture(), other = {...review().target_refs[0], face_instance_id: 'another-target'};
  value.target_refs.push(other);
  value.skin_finish_coverage!.targets.push({face_ref: other, scope: 'face-and-reviewed-body', body_review_sha256: 'e'.repeat(64)});
  assert.equal(validSkinFinishCoverage(value.skin_finish_coverage, value.target_refs), true);
  value.skin_finish_coverage!.targets[1].face_ref = {...value.target_refs[0]};
  assert.equal(validSkinFinishCoverage(value.skin_finish_coverage, value.target_refs), false);
});
test('mixed finish and signed colour retain separate disclosures and scalar domains', () => {
  const {req, value, target} = fixture('face-and-reviewed-body');
  req.selection['lnx.skin_colour.v1'] = ['/temperature'];
  value.parameters.push({operation_id: 'lnx.skin_colour.v1', parameter_path: '/temperature', value: -.4});
  value.skin_colour_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]},
    scope: 'face-only', body_review_sha256: null}]};
  assert.equal(validPeopleReview(value, req, req.source, target), true);
  delete value.skin_finish_coverage;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
});
test('unrelated transfers do not acquire unexplained finish coverage', () => {
  const req = request(), value = review(), target = {document_id: targetId, revision: '20'};
  assert.equal(validPeopleReview(value, req, req.source, target), true);
  value.skin_finish_coverage = fixture().value.skin_finish_coverage;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
});
test('finish disclosure is visible and explicitly separates body authorization from colour', () => {
  // Source contract only, not a rendered UI/screenshot acceptance claim.
  const source = readFileSync(new URL('./transferReview.tsx', import.meta.url), 'utf8');
  assert.ok(source.includes('open={explicit || !!value.skin_colour_coverage || !!value.skin_finish_coverage || !!value.body_skin_evenness_coverage || !!value.body_face_match_coverage}'));
  assert.ok(source.includes('aria-label="目标美白红润覆盖范围"'));
  assert.ok(source.includes('不改色温或色调'));
  assert.ok(source.includes('旧肤色色温/色调审核不能授权美白红润'));
  assert.ok(source.includes('不会继承源图或色温/色调的身体范围'));
  assert.ok(source.includes('不是自动全身分割'));
});
