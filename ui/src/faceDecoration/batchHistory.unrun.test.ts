// AUTHORED / UNRUN. Reopened-ledger recovery safety only; no mutation execution claim.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow} from '../batch/batchWorkflow';
import {observeDecorationBatchHistory, registerDecorationBatchReceipt, isDecorationBatchHistory, decorationBatchHistoryClass} from './batchHistoryRegistry';

test('reopened decoration history is query-only even in a new controller with no local commit memory', async () => {
  const batch = {batch_id: 'reopened-eye', module_scope: ['lnx.people_graph.v1'], targets: 2, undone: false,
    face_decoration_batch_review: {version: 1, review_sha256: 'a'.repeat(64), member_count: 2}};
  observeDecorationBatchHistory({workspace_generation: 'reopened-decoration-workspace', batches: [batch]});
  assert.equal(isDecorationBatchHistory(batch.batch_id), true);
  observeDecorationBatchHistory({workspace_generation: 'reopened-decoration-workspace', batches: []});
  assert.equal(isDecorationBatchHistory(batch.batch_id), true);
  let corrected = false, sends = 0;
  const flow = createBatchWorkflow({request: async () => {sends++; return {requested: true};},
    read: async request_id => ({phase: 'done', request_id, result: {request_id, action: 'undo', success: corrected,
      outcome_unknown: !corrected, batch_id: batch.batch_id, face_decoration_batch_review:batch.face_decoration_batch_review, module_scope: ['lnx.people_graph.v1'], restored: corrected ? [2, 3] : [], conflicts: []}})}, () => {});
  await flow.undo(batch.batch_id); assert.equal(flow.snapshot().phase, 'uncertain'); assert.equal(flow.snapshot().queryOnly, true);
  flow.acknowledgeInspection(); flow.close(); await flow.redo(batch.batch_id); assert.equal(sends, 1);
  corrected = true; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(sends, 1);
});
test('malformed markers tighten recovery while different workspaces and older observations cannot cross-contaminate', () => {
  const batch_id = 'malformed-eye';
  observeDecorationBatchHistory({workspace_generation: 'newest-decoration-workspace', batches: [{batch_id, face_decoration_batch_review: null}]}, 200);
  assert.equal(isDecorationBatchHistory(batch_id), true);
  observeDecorationBatchHistory({workspace_generation: 'older-decoration-workspace', batches: []}, 199);
  assert.equal(isDecorationBatchHistory(batch_id), true);
  observeDecorationBatchHistory({workspace_generation: 'different-decoration-workspace', batches: []}, 201);
  assert.equal(isDecorationBatchHistory(batch_id), false);
  assert.equal(registerDecorationBatchReceipt('newest-decoration-workspace', 'foreign-receipt', 1), false);
  assert.equal(registerDecorationBatchReceipt('different-decoration-workspace', 'local-receipt', 1), true);
  assert.equal(isDecorationBatchHistory('local-receipt'), true);
});

test('reopened partial restore or wrong scope never settles an atomic decoration history write', async () => {
  const batch_id = 'partial-eye'; observeDecorationBatchHistory({workspace_generation: 'partial-decoration-workspace', batches: [{batch_id,
    module_scope: ['lnx.people_graph.v1'], targets: 2, face_decoration_batch_review: {version: 1, review_sha256: 'b'.repeat(64), member_count: 2}}]});
  let partial = true, sends = 0;
  const flow = createBatchWorkflow({request: async () => {sends++; return {requested: true};}, read: async request_id => ({phase: 'done', request_id,
    result: {request_id, action: 'redo', success: true, outcome_unknown: false, batch_id, face_decoration_batch_review:{version:1,review_sha256:'b'.repeat(64),member_count:2}, module_scope: ['lnx.people_graph.v1'],
      restored: partial ? [2] : [2, 3], conflicts: []}})}, () => {});
  await flow.redo(batch_id); assert.equal(flow.snapshot().phase, 'uncertain'); flow.acknowledgeInspection();
  partial = false; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(sends, 1);
});

test('ordinary hexadecimal workspace/batch IDs remain eligible while control characters refuse',()=>{
 const epoch='a'.repeat(32),id='b'.repeat(32);observeDecorationBatchHistory({workspace_generation:epoch,batches:[]},1000);
 assert.equal(registerDecorationBatchReceipt(epoch,id,2,'c'.repeat(64)),true);
 assert.equal(registerDecorationBatchReceipt(epoch,'bad\u0000id',2),false);
});
test('mixed eye and decoration markers retain independent digests and compatible target membership',()=>{
 const marker={version:1,review_sha256:'a'.repeat(64),member_count:2};
 observeDecorationBatchHistory({workspace_generation:'mixed-workspace',batches:[{batch_id:'mixed',module_scope:['lnx.people_graph.v1'],targets:2,
 face_decoration_batch_review:marker,eye_bag_batch_review:{...marker,review_sha256:'b'.repeat(64)}}]},1001);
 assert.deepEqual(decorationBatchHistoryClass('mixed'),{memberCount:2,reviewSha256:'a'.repeat(64)});
});
