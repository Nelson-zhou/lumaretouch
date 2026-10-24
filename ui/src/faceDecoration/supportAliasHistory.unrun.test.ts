// AUTHORED / UNRUN. These envelopes are static contracts, not executed history acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow, type BatchReply} from '../batch/batchWorkflow';
import {checkSupportAliasHistoryReceipt} from './supportAliasBatchReceipt';
import {observeSupportAliasHistory, supportAliasHistoryClass, supportAliasWritePending, type SupportAliasMarker} from './supportAliasHistoryRegistry';
import {observeDecorationMultiHistory, decorationMultiHistory} from './multiHistory';
const marker: SupportAliasMarker = {version: 1, review_sha256: 'a'.repeat(64), member_count: 2};
const request = {action: 'undo', batchId: 'support-batch', supportAliasWrite: true, supportAliasMarker: marker, supportAliasMemberCount: 2};
function refusal(): BatchReply {return {request_id: 'support-history', action: 'undo', batch_id: 'support-batch', success: false, outcome_unknown: false,
  no_write: true, rolled_back: false, restored: [], error: 'source member unavailable', module_scope: ['lnx.people_graph.v1'], face_decoration_support_alias_review: marker};}
test('known no-write and compensated rollback failures match exact engine rejection without conflicts', () => {
  assert.doesNotThrow(() => checkSupportAliasHistoryReceipt(refusal(), request));
  assert.doesNotThrow(() => checkSupportAliasHistoryReceipt({...refusal(), no_write: false, rolled_back: true}, request));
  assert.throws(() => checkSupportAliasHistoryReceipt({...refusal(), conflicts: [{path: '/missing', reason: 'partial restore'}]}, request));
  assert.throws(() => checkSupportAliasHistoryReceipt({...refusal(), no_write: false, rolled_back: false}, request));
  assert.throws(() => checkSupportAliasHistoryReceipt({...refusal(), face_decoration_support_alias_review: undefined}, request));
  assert.throws(() => checkSupportAliasHistoryReceipt({...refusal(), success: true, no_write: false, restored: [0, 1]}, request));
  assert.doesNotThrow(() => checkSupportAliasHistoryReceipt({...refusal(), success: true, no_write: false, restored: [0, 1], conflicts: []}, request));
});
test('reopened support marker never co-classifies as scalar or falls back from malformed support', () => {
  const sync = {workspace_generation: 'support-marker-fixture', batches: [
    {batch_id: 'support-only', targets: 2, module_scope: ['lnx.people_graph.v1'], face_decoration_support_alias_review: marker},
    {batch_id: 'support-mixed', targets: 2, module_scope: ['lnx.people_graph.v1'], face_decoration_support_alias_review: marker, face_decoration_alias_review: marker},
    {batch_id: 'support-invalid', targets: 1, module_scope: ['lnx.people_graph.v1'], face_decoration_support_alias_review: marker},
  ]};
  observeSupportAliasHistory(sync); observeDecorationMultiHistory(sync);
  assert.equal(supportAliasHistoryClass('support-only')?.memberCount, 2);
  assert.equal(decorationMultiHistory('support-only'), undefined);
  assert.equal(supportAliasHistoryClass('support-mixed')?.marker, null);
  assert.equal(decorationMultiHistory('support-mixed')?.marker, null);
  assert.equal(supportAliasHistoryClass('support-invalid')?.marker, null);
});
test('unknown undo cannot release or resend; exact terminal query clears original global fence', async () => {
  observeSupportAliasHistory({workspace_generation: 'support-query-fixture', batches: [{batch_id: 'support-batch', targets: 2,
    module_scope: ['lnx.people_graph.v1'], face_decoration_support_alias_review: marker}]});
  let sent = 0, terminal = false;
  const flow = createBatchWorkflow({request: async () => {sent++; return {requested: true};}, read: async id => {
    if (!terminal) throw Error('mailbox unavailable');
    return {phase: 'done', request_id: id, result: {...refusal(), request_id: id}};
  }}, () => {}, {uuid: () => 'support-history'});
  await flow.undo('support-batch'); assert.equal(flow.snapshot().phase, 'uncertain'); assert.ok(supportAliasWritePending());
  flow.acknowledgeInspection(); flow.close(); await flow.undo('support-batch');
  assert.equal(sent, 1); assert.equal(flow.snapshot().phase, 'uncertain'); assert.ok(supportAliasWritePending());
  terminal = true; await flow.query(); assert.equal(flow.snapshot().phase, 'error'); assert.equal(supportAliasWritePending(), false);
  flow.dispose();
});
