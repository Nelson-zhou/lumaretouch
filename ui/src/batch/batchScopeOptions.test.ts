import test from 'node:test';
import assert from 'node:assert/strict';
import {batchScopeOptions, resolveBatchScope} from './batchScopeOptions.ts';

test('HSL is independently selectable and included in global recipe', () => {
  const choices = batchScopeOptions(['lnx.hsl.v1', 'lnx.exposure.v1'].map(operation_id => ({operation_id, transferable: true})));
  assert.deepEqual(choices[0], {label: '全图配方（曝光·HSL）', ops: ['lnx.exposure.v1', 'lnx.hsl.v1']});
  assert.deepEqual(choices.find(c => c.label === '仅HSL')?.ops, ['lnx.hsl.v1']);
});
test('older engines do not advertise missing or untransferable modules', () => {
  const choices = batchScopeOptions([{operation_id: 'lnx.exposure.v1', transferable: true}, {operation_id: 'lnx.hsl.v1', transferable: false}]);
  assert.equal(choices[0].label, '全图配方（曝光）');
  assert.ok(choices.every(c => !c.label.includes('HSL') && !c.ops.includes('lnx.hsl.v1')));
  assert.deepEqual(batchScopeOptions([]), []);
});
test('shared skin aliases remain together and retain the single-face warning', () => {
  const choices = batchScopeOptions(['lnx.skin.v1', 'lnx.blemish.v1'].map(operation_id => ({operation_id, transferable: true})));
  assert.deepEqual(choices, [{label: '仅磨皮（逐张须单脸）', ops: ['lnx.skin.v1', 'lnx.blemish.v1']}]);
});
test('lost HSL selection cannot silently broaden to a global recipe', () => {
  const choices = batchScopeOptions([{operation_id: 'lnx.exposure.v1', transferable: true}]);
  const resolved = resolveBatchScope(choices, '仅HSL');
  assert.deepEqual(resolved, {label: '原模块不可用，请重新选择', ops: []});
  assert.deepEqual(resolveBatchScope(choices, ''), choices[0]);
  assert.deepEqual(resolveBatchScope(choices, '仅曝光'), {label: '仅曝光', ops: ['lnx.exposure.v1']});
});
