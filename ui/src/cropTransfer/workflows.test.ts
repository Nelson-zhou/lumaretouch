// AUTHORED / UNRUN. Requires the local TypeScript/React-aware fixture setup.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CROP_OP} from './model.ts';
import {crop, review, targetId, sourceId, token} from './model.test.ts';
import {createPresetWorkflow, validatePresetReply, type PresetReply, type PresetTransport} from '../presets/presetWorkflow.ts';
import {createBatchWorkflow, type BatchReply, type BatchTransport} from '../batch/batchWorkflow.ts';
function presetResult(id: string): PresetReply {
  return {protocol: 1, request_id: id, action: 'preflight', success: true, outcome_unknown: false,
    document_id: targetId, id: 'crop', revision: '7', preflight_token: token,
    module_scope: [CROP_OP], applies: {[CROP_OP]: crop}, crop_transfer: review()};
}
test('preset requires genuine target preview, not normalized numbers alone', () => {
  const r = presetResult('request'), options = {id: 'crop', documentId: targetId};
  assert.doesNotThrow(() => validatePresetReply(r, 'preflight', options, 'request', [CROP_OP]));
  delete r.crop_transfer;
  assert.throws(() => validatePresetReply(r, 'preflight', options, 'request', [CROP_OP]));
});
function presetFixture() {
  let time = 0, pending = true, requests = 0;
  const api: PresetTransport = {request: async () => {requests++; return {requested: true};},
    read: async id => pending ? {phase: 'pending', request_id: id} : {phase: 'done', request_id: id, result: presetResult(id)}};
  const flow = createPresetWorkflow(api, () => {}, {uuid: () => 'request', now: () => time,
    pause: async () => {time += 20;}, timeoutMs: 10});
  const context = {enabled: true, editable: true, documentId: targetId, reviewContextKey: 'frame-1'};
  flow.updateContext(context);
  return {flow, context, api, release: () => {pending = false;}, count: () => requests};
}
test('queued preflight cannot revive after a real document edit', async () => {
  const f = presetFixture(); await f.flow.submit('preflight', {id: 'crop'}, [CROP_OP]);
  assert.equal(f.flow.snapshot().phase, 'uncertain');
  f.flow.updateContext({...f.context, reviewContextKey: 'frame-2'}); f.release(); await f.flow.query();
  assert.equal(f.flow.snapshot().phase, 'error'); assert.equal(f.flow.snapshot().result, null); assert.equal(f.count(), 1);
});
test('queue-only editability flip does not invalidate read-only preflight', async () => {
  const f = presetFixture(); await f.flow.submit('preflight', {id: 'crop'}, [CROP_OP]);
  f.flow.updateContext({...f.context, editable: false}); f.flow.updateContext(f.context);
  f.release(); await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done');
  f.flow.updateContext({...f.context, reviewContextKey: 'frame-2'}); assert.equal(f.flow.snapshot().result, null);
});
test('uncertain applied mutation stays queryable after document changes', async () => {
  const f = presetFixture(); await f.flow.submit('apply', {id: 'crop', preflightToken: token}, [CROP_OP]);
  f.flow.updateContext({...f.context, documentId: sourceId, reviewContextKey: 'other'});
  f.api.read = async id => ({phase: 'done', request_id: id, result: {...presetResult(id), action: 'apply',
    before: {[CROP_OP]: crop}, after: {[CROP_OP]: crop}, doc_state: {document_id: targetId}}});
  await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.count(), 1);
});
test('batch rejects missing target crop evidence before any commit', async () => {
  for (const include of [false, true]) {
    let requests = 0;
    const api: BatchTransport = {request: async () => {requests++; return {requested: true};}, read: async id => ({phase: 'done', request_id: id,
      result: {request_id: id, action: 'preflight', success: true, preflight_token: token,
        source_snapshot: {document_id: sourceId, revision: '1', path: '/source'}, module_scope: [CROP_OP], applies: {[CROP_OP]: crop}, policy: 'recheck',
        targets: [{index: 1, document_id: targetId, revision: '7', path: '/target', blocked: null, ...(include ? {crop_transfer: review()} : {})}],
        rejected_docs: [], ok: 1, blocked: 0} as BatchReply})};
    const flow = createBatchWorkflow(api, () => {}, {uuid: () => 'request'});
    flow.updateContext({docs: [targetId], moduleScope: [CROP_OP], conflictPolicy: 'recheck', sourceDocumentId: sourceId, enabled: true, label: 'crop'});
    await flow.start(); assert.equal(flow.snapshot().phase === 'review', include); assert.equal(requests, 1); flow.dispose();
  }
});
