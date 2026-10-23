// UNRUN: authored without executing tests, imports, inference, builds or typechecks.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createInventoryWorkflow, type InventoryTransport, type InventoryMailbox} from './transferInventoryWorkflow.ts';
import {inventory, sourceContext, targetId} from './transferFixtureData.test.ts';
const context = {key: 'source-and-targets-v1', enabled: true, docs: [targetId], source: sourceContext()};
const deferred = <T>() => {let resolve!: (value: T) => void; const promise = new Promise<T>(r => {resolve = r;}); return {promise, resolve};};
function fixture() {
  let n = 0, time = 0;
  const sends: string[] = [];
  const api: InventoryTransport = {request: async (_docs, id) => {sends.push(id); return {requested: true};},
    read: async id => ({request_id: id, phase: 'done', result: inventory(id)})};
  const flow = createInventoryWorkflow(api, () => {}, {uuid: () => `read-${++n}`, now: () => time,
    pause: async () => {time += 10;}, timeoutMs: 15});
  flow.updateContext(context); return {api, flow, sends};
}
test('inventory completes read-only, exact request correlation is required', async () => {
  const {flow, sends} = fixture(); await flow.start(); assert.equal(flow.snapshot().phase, 'ready');
  assert.deepEqual(sends, ['read-1']);
  const bad = fixture(); bad.api.read = async () => ({phase: 'done', request_id: 'wrong', result: inventory('wrong')});
  await bad.flow.start(); assert.equal(bad.flow.snapshot().phase, 'uncertain'); assert.equal(bad.flow.snapshot().result, null);
});
test('uncertain inventory keeps request ID and querying does not submit a new command', async () => {
  const {flow, api, sends} = fixture(), read = api.read;
  api.read = async id => ({phase: 'pending', request_id: id}); await flow.start();
  assert.equal(flow.snapshot().phase, 'uncertain'); await flow.start(); assert.equal(sends.length, 1);
  api.read = read; await flow.query(); assert.equal(flow.snapshot().phase, 'ready'); assert.equal(sends.length, 1);
});
test('cancel and changed source, target selection or availability discard late responses', async () => {
  for (const change of ['cancel', 'context', 'disabled']) {
    const {flow, api} = fixture(), wait = deferred<InventoryMailbox>(); api.read = () => wait.promise;
    const started = flow.start(); await Promise.resolve(); await Promise.resolve();
    if (change === 'cancel') flow.cancel();
    else flow.updateContext({...context, key: change === 'context' ? 'changed' : context.key, enabled: change !== 'disabled'});
    wait.resolve({phase: 'done', request_id: 'read-1', result: inventory()}); await started;
    assert.equal(flow.snapshot().phase, 'idle'); assert.equal(flow.snapshot().result, null);
  }
});
test('repeated clicks and too many targets cannot enqueue unreviewable work', async () => {
  const {flow, api, sends} = fixture(), wait = deferred<{requested: boolean}>(); api.request = async (_docs, id) => {sends.push(id); return wait.promise;};
  const started = flow.start(); await flow.start(); assert.equal(sends.length, 1);
  wait.resolve({requested: true}); await started;
  flow.updateContext({...context, key: 'oversize', docs: Array.from({length: 17}, (_, n) => n.toString(16).padStart(32, '0'))});
  await flow.start(); assert.equal(flow.snapshot().phase, 'error'); assert.equal(sends.length, 1);
});
