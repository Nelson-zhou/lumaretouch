// AUTHORED / UNRUN. Reopened-ledger recovery safety only; no mutation execution claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow} from '../batch/batchWorkflow';
import {observeEyeBagBatchHistory, registerEyeBagBatchReceipt, isEyeBagBatchHistory} from './batchHistoryRegistry';

test('reopened eye history is query-only even in a new controller with no local commit memory', async () => {
  const batch = {batch_id: 'reopened-eye', module_scope: ['lnx.people_graph.v1'], targets: 2, undone: false,
    eye_bag_batch_review: {version: 1, review_sha256: 'a'.repeat(64), member_count: 2}};
  observeEyeBagBatchHistory({workspace_generation: 'reopened-eye-workspace', batches: [batch]});
  assert.equal(isEyeBagBatchHistory(batch.batch_id), true);
  observeEyeBagBatchHistory({workspace_generation: 'reopened-eye-workspace', batches: []});
  assert.equal(isEyeBagBatchHistory(batch.batch_id), true);
  let corrected = false, sends = 0;
  const flow = createBatchWorkflow({request: async () => {sends++; return {requested: true};},
    read: async request_id => ({phase: 'done', request_id, result: {request_id, action: 'undo', success: corrected,
      outcome_unknown: !corrected, batch_id: batch.batch_id, module_scope: ['lnx.people_graph.v1'], restored: corrected ? [2, 3] : [], conflicts: []}})}, () => {});
  await flow.undo(batch.batch_id); assert.equal(flow.snapshot().phase, 'uncertain'); assert.equal(flow.snapshot().queryOnly, true);
  flow.acknowledgeInspection(); flow.close(); await flow.redo(batch.batch_id); assert.equal(sends, 1);
  corrected = true; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(sends, 1);
});
test('malformed markers tighten recovery while different workspaces and older observations cannot cross-contaminate', () => {
  const batch_id = 'malformed-eye';
  observeEyeBagBatchHistory({workspace_generation: 'newest-eye-workspace', batches: [{batch_id, eye_bag_batch_review: null}]}, 200);
  assert.equal(isEyeBagBatchHistory(batch_id), true);
  observeEyeBagBatchHistory({workspace_generation: 'older-eye-workspace', batches: []}, 199);
  assert.equal(isEyeBagBatchHistory(batch_id), true);
  observeEyeBagBatchHistory({workspace_generation: 'different-eye-workspace', batches: []}, 201);
  assert.equal(isEyeBagBatchHistory(batch_id), false);
  assert.equal(registerEyeBagBatchReceipt('newest-eye-workspace', 'foreign-receipt', 1), false);
  assert.equal(registerEyeBagBatchReceipt('different-eye-workspace', 'local-receipt', 1), true);
  assert.equal(isEyeBagBatchHistory('local-receipt'), true);
});

test('reopened partial restore or wrong scope never settles an atomic eye history write', async () => {
  const batch_id = 'partial-eye'; observeEyeBagBatchHistory({workspace_generation: 'partial-eye-workspace', batches: [{batch_id,
    module_scope: ['lnx.people_graph.v1'], targets: 2, eye_bag_batch_review: {version: 1, review_sha256: 'b'.repeat(64), member_count: 2}}]});
  let partial = true, sends = 0;
  const flow = createBatchWorkflow({request: async () => {sends++; return {requested: true};}, read: async request_id => ({phase: 'done', request_id,
    result: {request_id, action: 'redo', success: true, outcome_unknown: false, batch_id, module_scope: ['lnx.people_graph.v1'],
      restored: partial ? [2] : [2, 3], conflicts: []}})}, () => {});
  await flow.redo(batch_id); assert.equal(flow.snapshot().phase, 'uncertain'); flow.acknowledgeInspection();
  partial = false; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(sends, 1);
});
