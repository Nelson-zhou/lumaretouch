// AUTHORED / UNRUN: no imports, tests, typecheck, build or product execution performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {batchCompletionRequest} from './completion';
import type {BatchUi} from './batchWorkflow';

const state = (phase: BatchUi['phase'], success: boolean, unknown = false): BatchUi => ({phase, operation: 'undo',
  plan: null, message: '', scopeLabel: '', result: {request_id: 'same-original-request', action: 'undo', success,
    outcome_unknown: unknown, batch_id: 'real-batch', restored: [], conflicts: []}});
test('unknown then query-known same request notifies only at actual completion', () => {
  let reported = '', notifications = 0;
  for (const value of [state('uncertain', false, true), state('committing', false, true),
    state('done', true), state('done', true)]) {
    const next = batchCompletionRequest(value, reported);
    if (next) {reported = next; notifications++;}
  }
  assert.equal(notifications, 1); assert.equal(reported, 'same-original-request');
});
test('normal done and known error each notify once; preflight never does', () => {
  for (const value of [state('done', true), state('error', false)]) {
    const id = batchCompletionRequest(value, ''); assert.equal(id, 'same-original-request');
    assert.equal(batchCompletionRequest(value, id!), null);
  }
  assert.equal(batchCompletionRequest({...state('done', true), operation: 'preflight'}, ''), null);
  assert.equal(batchCompletionRequest(state('done', true, true), ''), null);
});
