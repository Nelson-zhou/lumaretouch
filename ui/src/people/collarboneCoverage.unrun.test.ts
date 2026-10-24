// AUTHORED / UNRUN. No imports, tests, UI, typecheck or build executed while authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validPeopleReview, validCollarboneCoverage, type CollarboneCoverage} from './transferProof.ts';
import {request, review, targetId} from './transferFixtureData.test.ts';
function fixture(scope: CollarboneCoverage['targets'][number]['scope'] = 'reviewed-clavicle-only') {
  const req = request(), value = review();
  req.selection = {'lnx.collarbone.v1': ['/amount']};
  value.parameters = [{operation_id: 'lnx.collarbone.v1', parameter_path: '/amount', value: scope === 'neutral-no-effect' ? 0 : .4}];
  value.collarbone_coverage = {version: 1, support_transfer: 'none', targets: [{face_ref: {...value.target_refs[0]}, scope,
    body_review_sha256: scope === 'neutral-no-effect' ? null : 'f'.repeat(64),
    clavicle_category: scope === 'neutral-no-effect' ? null : 'female', clavicle_sides: scope === 'neutral-no-effect' ? [] : ['left']}]};
  return {req, value, target: {document_id: targetId, revision: '20'}};
}
test('own target evidence is required for active and exact no-effect disclosed for neutral', () => {
  for (const scope of ['neutral-no-effect', 'reviewed-clavicle-only'] as const) {
    const {req, value, target} = fixture(scope); assert.equal(validPeopleReview(value, req, req.source, target), true);
    delete value.collarbone_coverage; assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('only exact target-local clavicle evidence is admitted, no body-only or copied geometry fallback', () => {
  for (const mutate of [
    (v: any) => {v.version = 2;}, (v: any) => {v.support_transfer = 'copied';}, (v: any) => {v.targets = [];},
    (v: any) => {v.targets.push(structuredClone(v.targets[0]));}, (v: any) => {v.targets[0].face_ref.analysis_revision++;},
    (v: any) => {v.targets[0].face_ref.asset_sha256 = 'a'.repeat(64);}, (v: any) => {v.targets[0].scope = 'reviewed-body-only';},
    (v: any) => {v.targets[0].scope = 'face-only';}, (v: any) => {v.targets[0].body_review_sha256 = null;},
    (v: any) => {v.targets[0].body_review_sha256 = 'invalid';}, (v: any) => {v.targets[0].clavicle_category = null;},
    (v: any) => {v.targets[0].clavicle_category = 'male';}, (v: any) => {v.targets[0].clavicle_sides = [];},
    (v: any) => {v.targets[0].clavicle_sides = ['left', 'left'];}, (v: any) => {v.targets[0].clavicle_sides = ['anatomical-left'];},
    (v: any) => {v.targets[0].curves = [];}, (v: any) => {v.targets[0].mask = {};}, (v: any) => {v.body_ref = {};},
  ]) {const {req, value, target} = fixture(); mutate(value.collarbone_coverage); assert.equal(validPeopleReview(value, req, req.source, target), false);}
});
test('one or both sides, and either explicit eligible category, remain target-owned metadata', () => {
  for (const category of ['female', 'elder_female'] as const) for (const sides of [['left'], ['right'], ['left', 'right']] as ('left' | 'right')[][]) {
    const {req, value, target} = fixture(); Object.assign(value.collarbone_coverage!.targets[0], {clavicle_category: category, clavicle_sides: sides});
    assert.equal(validPeopleReview(value, req, req.source, target), true);
  }
});
test('scalar-only transfer rejects nonfinite, out-of-range, extra properties and geometry paths', () => {
  for (const amount of [true, '0.4', -1, 1.1, NaN, Infinity]) {
    const {req, value, target} = fixture(); value.parameters[0].value = amount; assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
  for (const path of ['/version', '/clavicle', '/curves', '/body_ref', '/mask', '/category']) {
    const {req, value, target} = fixture(); req.selection['lnx.collarbone.v1'] = [path]; value.parameters[0].parameter_path = path;
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('neutral metadata cannot retain anatomy/category identity or conceal a positive amount', () => {
  for (const mutate of [(v: any) => {v.body_review_sha256 = 'f'.repeat(64);}, (v: any) => {v.clavicle_category = 'female';},
    (v: any) => {v.clavicle_sides = ['left'];}]) {
    const {value} = fixture('neutral-no-effect'); mutate(value.collarbone_coverage!.targets[0]);
    assert.equal(validCollarboneCoverage(value.collarbone_coverage, value.target_refs), false);
  }
  const neutral = fixture('neutral-no-effect'); neutral.value.parameters[0].value = .5;
  assert.equal(validPeopleReview(neutral.value, neutral.req, neutral.req.source, neutral.target), false);
  const active = fixture(); active.value.parameters[0].value = 0;
  assert.equal(validPeopleReview(active.value, active.req, active.req.source, active.target), false);
});
test('each exact target requires a separate record and unrelated operations cannot smuggle a collarbone review', () => {
  const {value} = fixture(), other = {...value.target_refs[0], face_instance_id: 'other'}; value.target_refs.push(other);
  assert.equal(validCollarboneCoverage(value.collarbone_coverage, value.target_refs), false);
  value.collarbone_coverage!.targets.push({...value.collarbone_coverage!.targets[0], face_ref: other, body_review_sha256: 'e'.repeat(64)});
  assert.equal(validCollarboneCoverage(value.collarbone_coverage, value.target_refs), true);
  value.collarbone_coverage!.targets[1].face_ref = {...value.target_refs[0]};
  assert.equal(validCollarboneCoverage(value.collarbone_coverage, value.target_refs), false);
  const req = request(), unrelated = review(); unrelated.collarbone_coverage = fixture().value.collarbone_coverage;
  assert.equal(validPeopleReview(unrelated, req, req.source, {document_id: targetId, revision: '20'}), false);
});
test('visible transfer disclosure states category, image sides, scalar-only and missing batch visual comparison', () => {
  const text = readFileSync(new URL('./transferReview.tsx', import.meta.url), 'utf8');
  for (const expected of ['!!value.collarbone_coverage', '目标锁骨现有明暗增强覆盖范围', 'row.clavicle_category', 'row.clavicle_sides',
    '不复制身体蒙版、锁骨曲线、类别确认或人物关联', '不是新生成的批量逐图视觉前后对比', '不自动分类、检测锁骨、补全另一侧或进行 AI 3D 重建']) assert.ok(text.includes(expected));
});
