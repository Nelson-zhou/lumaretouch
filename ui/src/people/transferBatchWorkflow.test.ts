// UNRUN integration fixtures. Requires the project's local TypeScript/React-aware test setup.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow, type BatchTransport, type BatchReply, type BatchOptions, type BatchAction} from '../batch/batchWorkflow.ts';
import {request, review, sourceId, targetId} from './transferFixtureData.test.ts';
const token = 'f'.repeat(32), source = {document_id: sourceId, revision: '3', path: '/source.raw'};
const target = {document_id: targetId, revision: '20', index: 1, path: '/target.raw', blocked: null};
function fixture() {
  let count = 0, time = 0;
  const calls: {action: BatchAction; options: BatchOptions}[] = [], replies = new Map<string, BatchReply>();
  const people = request();
  const api: BatchTransport = {request: async (action, options) => {
    calls.push({action, options}); const id = options.requestId!;
    replies.set(id, action === 'preflight' ? {request_id: id, action, success: true, preflight_token: token,
      source_snapshot: source, module_scope: Object.keys(people.selection), applies: people, policy: 'recheck',
      targets: [{...target, people_transfer: review()}], rejected_docs: [], ok: 1, blocked: 0, people_transfer: true}
      : {request_id: id, action, success: true, preflight_token: token, source_snapshot: source,
        target_outcomes: [{...target, expected_revision: '20', current_revision: '20', result_revision: '21', outcome: 'applied'}]});
    return {requested: true};}, read: async id => ({phase: 'done', request_id: id, result: replies.get(id)})};
  const context = {docs: [targetId], moduleScope: Object.keys(people.selection), conflictPolicy: 'recheck', sourceDocumentId: sourceId,
    referencePath: source.path, enabled: true, label: 'one transfer only', peopleTransfer: people, peopleProof: people.source};
  const flow = createBatchWorkflow(api, () => {}, {uuid: () => `batch-${++count}`, now: () => time, pause: async () => {time += 10;}, timeoutMs: 15});
  flow.updateContext(context); return {flow, api, calls, replies, context};
}
test('explicit map preflight freezes all choices; only confirmation sends frozen token', async () => {
  const {flow, calls} = fixture(); await flow.start();
  assert.equal(flow.snapshot().phase, 'review'); assert.equal(calls.length, 1);
  await flow.commit(); assert.equal(flow.snapshot().phase, 'done');
  assert.deepEqual(calls[1], {action: 'commit', options: {preflightToken: token, requestId: 'batch-2'}});
});
test('dropped, extra and wrong-face targets cannot create a committable plan', async () => {
  for (const mutate of [
    (r: any) => {r.targets = []; r.ok = 0;},
    (r: any) => {r.targets[0].document_id = 'e'.repeat(32);},
    (r: any) => {r.targets[0].people_transfer.target_refs[0].analysis_revision++;},
  ]) {
    const {flow, api, calls} = fixture(), old = api.read;
    api.read = async id => {const reply = await old(id); mutate(reply.result); return reply;};
    await flow.start(); await flow.commit();
    assert.notEqual(flow.snapshot().phase, 'review'); assert.equal(flow.snapshot().plan, null); assert.equal(calls.length, 1);
  }
});
test('old uncertain preflight never authorizes changed choices after query', async () => {
  const {flow, api, calls, context} = fixture(), read = api.read;
  api.read = async id => ({phase: 'pending', request_id: id}); await flow.start();
  assert.equal(flow.snapshot().phase, 'uncertain');
  flow.updateContext({...context, peopleTransfer: {...request(), selection: {'lnx.deform.v1': ['/other']}}});
  api.read = read; await flow.query(); await flow.commit();
  assert.equal(flow.snapshot().phase, 'error'); assert.equal(flow.snapshot().plan, null); assert.equal(calls.length, 1);
});
test('uncertain commit remains queryable once after context changes without resubmission', async () => {
  const {flow, api, calls, context} = fixture(); await flow.start(); const read = api.read;
  api.read = async id => ({phase: 'pending', request_id: id}); await flow.commit();
  assert.equal(flow.snapshot().phase, 'uncertain'); flow.close();
  flow.updateContext({...context, enabled: false, docs: []}); api.read = read; await flow.query();
  assert.equal(flow.snapshot().phase, 'done'); assert.equal(calls.length, 2);
});
