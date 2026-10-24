// AUTHORED / UNRUN. Receipt, cancellation and all-member history fixtures; not runtime evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createPeopleWorkflow} from '../people/workflow';
import type {PeopleAction, PeopleMailbox, PeopleResult} from '../people/model';
import {createBatchWorkflow} from '../batch/batchWorkflow';
import {aliasFixture} from './aliasFixture.unrun.test';
import {observeEyeBagAliasHistory, eyeBagAliasHistoryClass, registerEyeBagAliasReceipt} from './aliasHistoryRegistry';
const echo = (command: PeopleAction) => {const {request_id: _, ...value} = command; return value;};
const preview = (f: ReturnType<typeof aliasFixture>): PeopleAction => ({...f.context, request_id: 'preview', action: 'eye_bag_preview', payload: f.candidate});
function readResult(command: PeopleAction, payload: unknown): PeopleResult {
  return {protocol: 1, request_id: command.request_id, document_id: command.document_id, action: command.action,
    success: true, outcome_unknown: false, eye_bag_request: echo(command), payload};
}
function deferred<T>() {let resolve!: (value: T) => void; const promise = new Promise<T>(r => {resolve = r;}); return {promise, resolve};}

test('captured v2 confirms once; unknown/partial receipt stays query-only until exact complete original receipt', async () => {
  const f = aliasFixture(), p = preview(f); let sends = 0, complete = false;
  const w = createPeopleWorkflow({send: async () => {sends++;}, refresh: async () => {}, read: async request_id => ({phase: 'done', request_id,
    result: request_id === p.request_id ? readResult(p, {kind: 'eye_bag_preview', review: f.review})
      : complete ? f.result : {...f.result, outcome_unknown: true}})});
  w.update(f.view, true); await w.submit(p); await assert.rejects(w.submit(f.command));
  assert.equal(w.snapshot().uncertain, true); assert.equal(w.snapshot().lastEyeBagAliasCommit, null);
  await assert.rejects(w.submit({...f.command, request_id: 'duplicate'})); assert.equal(sends, 2);
  await assert.rejects(w.cancelEyeBagRead()); await assert.rejects(w.recoverEyeBagRead());
  complete = true; await w.check(); assert.equal(sends, 2); assert.equal(w.snapshot().uncertain, false);
  assert.deepEqual(w.snapshot().lastEyeBagAliasCommit, f.commit);
});

test('late confirmed alias outcome retained without applying old face receipt to newly navigated document', async () => {
  const f = aliasFixture(), p = preview(f), result = deferred<PeopleMailbox>(), begun = deferred<void>();
  const w = createPeopleWorkflow({send: async () => {}, refresh: async () => {}, read: async request_id => {
    if (request_id === p.request_id) return {phase: 'done', request_id, result: readResult(p, {kind: 'eye_bag_preview', review: f.review})};
    begun.resolve(); return result.promise;
  }});
  w.update(f.view, true); await w.submit(p); const pending = w.submit(f.command); await begun.promise;
  const elsewhere = structuredClone(f.view); elsewhere.binding.document_id = '9'.repeat(32); w.update(elsewhere, true);
  result.resolve({phase: 'done', request_id: f.command.request_id, result: f.result}); await pending;
  assert.equal(w.snapshot().lastEyeBagResult, null); assert.deepEqual(w.snapshot().lastEyeBagAliasCommit, f.commit);
});

test('cancelled v2 preview discards completed candidate and never authorizes later confirm', async () => {
  const f = aliasFixture(), p = preview(f), pending = deferred<PeopleMailbox>(); let sends = 0;
  const w = createPeopleWorkflow({send: async () => {sends++;}, refresh: async () => {}, read: async () => pending.promise,
    cancelEyeBagRead: async request_id => ({request_id, cancel_requested: false, stopped: false, eye_bag_request: echo(p)})});
  w.update(f.view, true); const submitted = w.submit(p), cancelled = w.cancelEyeBagRead();
  pending.resolve({phase: 'done', request_id: p.request_id, result: readResult(p, {kind: 'eye_bag_preview', review: f.review})});
  await Promise.all([submitted, cancelled]); assert.equal(w.snapshot().eyeBagCancel, 'completed');
  assert.equal(w.snapshot().lastEyeBagResult, null); await assert.rejects(w.submit(f.command)); assert.equal(sends, 1);
});

test('reopened alias marker protects every batch controller; partial restore cannot become success or replay', async () => {
  const batch_id = 'reopened-eye-alias', workspace_generation = 'reopened-eye-alias-workspace';
  const batch = {batch_id, targets: 2, module_scope: ['lnx.people_graph.v1'], undone: false,
    eye_bag_alias_review: {version: 1, review_sha256: 'a'.repeat(64), member_count: 2}};
  observeEyeBagAliasHistory({workspace_generation, batches: [batch]}, 100);
  observeEyeBagAliasHistory({workspace_generation, batches: []}, 101);
  assert.equal(eyeBagAliasHistoryClass(batch_id)?.memberCount, 2);
  let sends = 0, complete = false;
  const flow = createBatchWorkflow({request: async () => {sends++; return {requested: true};}, read: async request_id => ({phase: 'done', request_id,
    result: {request_id, action: 'undo', success: true, outcome_unknown: false, batch_id, module_scope: ['lnx.people_graph.v1'],
      restored: complete ? [2, 7] : [2], conflicts: []}})}, () => {});
  await flow.undo(batch_id); assert.equal(flow.snapshot().phase, 'uncertain'); assert.equal(flow.snapshot().queryOnly, true);
  flow.acknowledgeInspection(); flow.close(); await flow.redo(batch_id); assert.equal(sends, 1);
  complete = true; await flow.query(); assert.equal(flow.snapshot().phase, 'done'); assert.equal(sends, 1);
  observeEyeBagAliasHistory({workspace_generation: 'older-workspace', batches: []}, 99);
  assert.equal(eyeBagAliasHistoryClass(batch_id)?.memberCount, 2);
  observeEyeBagAliasHistory({workspace_generation: 'other-workspace', batches: []}, 102);
  assert.equal(eyeBagAliasHistoryClass(batch_id), undefined);
});

test('receipt registration cannot invent a batch; malformed/contradictory markers cannot downgrade safety', () => {
  const f = aliasFixture(); observeEyeBagAliasHistory({workspace_generation: 'epoch', batches: []});
  assert.equal(registerEyeBagAliasReceipt({...f.commit, batchId: 'invented'}), false);
  assert.equal(registerEyeBagAliasReceipt(f.commit), true); assert.equal(eyeBagAliasHistoryClass(f.commit.batchId)?.memberCount, 2);
  observeEyeBagAliasHistory({workspace_generation: 'epoch', batches: [{batch_id: f.commit.batchId, eye_bag_alias_review: null}]});
  assert.equal(eyeBagAliasHistoryClass(f.commit.batchId)?.memberCount, null);
  assert.equal(registerEyeBagAliasReceipt(f.commit), false);
  observeEyeBagAliasHistory({workspace_generation: 'epoch', batches: [{batch_id: 'mixed-marker', targets: 2,
    module_scope: ['lnx.people_graph.v1'], eye_bag_batch_review: {}, eye_bag_alias_review: {version: 1, review_sha256: 'a'.repeat(64), member_count: 2}}]});
  assert.equal(eyeBagAliasHistoryClass('mixed-marker')?.memberCount, null);
});
