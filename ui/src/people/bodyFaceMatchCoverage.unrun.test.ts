// AUTHORED / UNRUN. No imports, tests, UI, typecheck or build executed while authoring.
import {test} from 'node:test';
import {ownFaceReferenceFixture} from '../bodyFaceMatch/fixtures.unrun.ts';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validPeopleReview, validBodyFaceMatchCoverage, type BodyFaceMatchCoverage} from './transferProof.ts';
import {request, review, targetId} from './transferFixtureData.test.ts';

function fixture(scope: BodyFaceMatchCoverage['targets'][number]['scope'] = 'reviewed-body-own-face') {
  const req = request(), value = review();
  req.selection = {'lnx.body_face_match.v1': ['/amount']};
  value.parameters = [{operation_id: 'lnx.body_face_match.v1', parameter_path: '/amount', value: scope === 'neutral-no-effect' ? 0 : .4}];
  value.body_face_match_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]}, scope,
    body_review_sha256: scope === 'reviewed-body-own-face' ? 'f'.repeat(64) : null,
    own_face_reference: scope === 'reviewed-body-own-face' ? ownFaceReferenceFixture(value.target_refs[0]) : null}]};
  return {req, value, target: {document_id: targetId, revision: '20'}};
}

test('active body-only and neutral transfer receipts carry exact independent target coverage', () => {
  for (const scope of ['reviewed-body-own-face', 'neutral-no-effect'] as const) {
    const {req, value, target} = fixture(scope);
    assert.equal(validPeopleReview(value, req, req.source, target), true);
    delete value.body_face_match_coverage;
    value.skin_colour_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]},
      scope: 'face-and-reviewed-body', body_review_sha256: 'e'.repeat(64)}]};
    value.skin_finish_coverage = structuredClone(value.skin_colour_coverage);
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});

test('body coverage rejects face-only fallback, copied supports and foreign or omitted target identity', () => {
  for (const mutate of [
    (v: any) => {v.support_transfer = 'copied';}, (v: any) => {v.version = 2;},
    (v: any) => {v.targets = [];}, (v: any) => {v.targets.push(structuredClone(v.targets[0]));},
    (v: any) => {v.targets[0].face_ref.analysis_revision++;},
    (v: any) => {v.targets[0].face_ref.asset_sha256 = 'a'.repeat(64);},
    (v: any) => {v.targets[0].scope = 'face-only';}, (v: any) => {v.targets[0].scope = 'face-and-reviewed-body';},
    (v: any) => {v.targets[0].body_review_sha256 = null;}, (v: any) => {v.targets[0].body_review_sha256 = 'bad';},
    (v: any) => {v.targets[0].body_ref = {};}, (v: any) => {v.targets[0].mask = [1, 1];},
    (v: any) => {v.source_support = {};}, (v: any) => {v.reference_colour = [.5, .4, .3];},
    (v: any) => {delete v.targets[0].own_face_reference;}, (v: any) => {v.targets[0].own_face_reference = null;},
    (v: any) => {v.targets[0].own_face_reference.face_ref.face_instance_id = 'donor';},
    (v: any) => {v.targets[0].own_face_reference.face_ref.analysis_revision++;},
    (v: any) => {v.targets[0].own_face_reference.face_skin_observation.source_sha256 = 'a'.repeat(64);},
    (v: any) => {v.targets[0].own_face_reference.landmark_digest = 'bad';},
    (v: any) => {v.targets[0].own_face_reference.reference_method = 'later-edited-face';},
    (v: any) => {v.targets[0].own_face_reference.reference_colour = [.2, .3, .4];},
    (v: any) => {v.targets[0].scope = 'reviewed-body-only';},
  ]) {
    const {req, value, target} = fixture(); mutate(value.body_face_match_coverage);
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});

test('body transfer accepts only one finite unsigned /amount and enforces exact zero disclosure', () => {
  for (const amount of ['0.4', true, -1, -.01, 1.01, NaN, Infinity]) {
    const {req, value, target} = fixture(); value.parameters[0].value = amount;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
  for (const path of ['/temperature', '/whitening', '/version', '/body_ref', '/mask']) {
    const {req, value, target} = fixture();
    req.selection['lnx.body_face_match.v1'] = [path]; value.parameters[0].parameter_path = path;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
  for (const amount of [.01, .5, 1]) {
    const {req, value, target} = fixture(); value.parameters[0].value = amount;
    assert.equal(validPeopleReview(value, req, req.source, target), true);
  }
  const neutral = fixture('neutral-no-effect'); neutral.value.parameters[0].value = .3;
  assert.equal(validPeopleReview(neutral.value, neutral.req, neutral.req.source, neutral.target), false);
  const active = fixture(); active.value.parameters[0].value = 0;
  assert.equal(validPeopleReview(active.value, active.req, active.req.source, active.target), false);
  neutral.value.parameters[0].value = 0; neutral.value.body_face_match_coverage!.targets[0].body_review_sha256 = 'f'.repeat(64);
  assert.equal(validBodyFaceMatchCoverage(neutral.value.body_face_match_coverage, neutral.value.target_refs), false);
  const neutralReference = fixture('neutral-no-effect');
  neutralReference.value.body_face_match_coverage!.targets[0].own_face_reference = ownFaceReferenceFixture(neutralReference.value.target_refs[0]);
  assert.equal(validBodyFaceMatchCoverage(neutralReference.value.body_face_match_coverage, neutralReference.value.target_refs), false);
});

test('each target independently declares its own reviewed body, never selected-person evidence for all', () => {
  const {value} = fixture(), other = {...review().target_refs[0], face_instance_id: 'another-target'};
  value.target_refs.push(other);
  assert.equal(validBodyFaceMatchCoverage(value.body_face_match_coverage, value.target_refs), false);
  value.body_face_match_coverage!.targets.push({face_ref: other, scope: 'reviewed-body-own-face', body_review_sha256: 'e'.repeat(64), own_face_reference: ownFaceReferenceFixture(other)});
  assert.equal(validBodyFaceMatchCoverage(value.body_face_match_coverage, value.target_refs), true);
  value.body_face_match_coverage!.targets[1].face_ref = {...value.target_refs[0]};
  assert.equal(validBodyFaceMatchCoverage(value.body_face_match_coverage, value.target_refs), false);
});

test('mixed skin families keep separate disclosures and unrelated transfers reject unexplained body coverage', () => {
  const {req, value, target} = fixture();
  req.selection['lnx.skin_colour.v1'] = ['/temperature'];
  req.selection['lnx.skin_finish.v1'] = ['/whitening'];
  value.parameters.push({operation_id: 'lnx.skin_colour.v1', parameter_path: '/temperature', value: -.4},
    {operation_id: 'lnx.skin_finish.v1', parameter_path: '/whitening', value: .2});
  value.skin_colour_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]}, scope: 'face-only', body_review_sha256: null}]};
  value.skin_finish_coverage = structuredClone(value.skin_colour_coverage);
  req.selection['lnx.body_skin_evenness.v1'] = ['/amount'];
  value.parameters.push({operation_id: 'lnx.body_skin_evenness.v1', parameter_path: '/amount', value: .6});
  value.body_skin_evenness_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]},
    scope: 'reviewed-body-only', body_review_sha256: 'd'.repeat(64)}]};
  assert.equal(validPeopleReview(value, req, req.source, target), true);
  delete value.body_face_match_coverage;
  assert.equal(validPeopleReview(value, req, req.source, target), false);
  const unrelated = request(), other = review();
  other.body_face_match_coverage = fixture().value.body_face_match_coverage;
  assert.equal(validPeopleReview(other, unrelated, unrelated.source, target), false);
});

test('matching coverage visibly exposes independent target reference identity, source stage and refusals', () => {
  const source = readFileSync(new URL('./transferReview.tsx', import.meta.url), 'utf8');
  for (const text of ['!!value.body_face_match_coverage', 'aria-label="目标身体向本人脸部色度匹配覆盖范围"',
    '只同步匹配强度，不复制身体蒙版、参考色、脸部观察或人物关联', '本人的实测来源脸部',
    'row.own_face_reference!.face_ref.face_instance_id', 'row.own_face_reference!.face_ref.analysis_revision',
    '肖像效果之前的冻结阶段', '含已验证修复', '不匹配亮度，不复制 RGB',
    '不据此声明已有身体审核或可用脸部参考', '元数据也不等于照片质量验收',
    '预检中被拒绝的目标不会因其他人物已有审核而变为可用', '处理原始拒绝原因']) assert.ok(source.includes(text));
});
