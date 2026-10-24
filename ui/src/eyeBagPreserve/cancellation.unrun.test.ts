// AUTHORED / UNRUN. No tests, product imports or typechecks executed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createPeopleWorkflow} from '../people/workflow.ts';
import {peopleContext, type PeopleView, type PeopleAction, type PeopleMailbox} from '../people/model.ts';
import {eyeBagBinding} from './model.ts';
import {emptyMask} from './support.ts';
const face = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face', analysis_revision: 1};
function view(): PeopleView {
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 1, asset_sha256: face.asset_sha256}, revision: 1,
    association_revision: 0, faces: [{face_ref: face, enabled: true, box: [.1,.1,.8,.8], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: 'face', resolved: null, editing_target: {scope: 'face', target_id: 'face', face_ref: face}, editing_overrides: {}};
}
function request(v: PeopleView): PeopleAction {return {...peopleContext(v)!, request_id: 'read', action: 'eye_bag_reference', payload: {}};}
function echo(c: PeopleAction) {const {request_id: _, ...value} = c; return value;}
function deferred<T>() {let resolve!: (v: T) => void; const promise = new Promise<T>(r => {resolve = r;}); return {promise, resolve};}
test('cancel request keeps pending until exact original stopped receipt, no retry', async () => {
  const v = view(), c = request(v), read = deferred<PeopleMailbox>(); let sends = 0;
  const w = createPeopleWorkflow({send: async () => {sends++;}, read: async () => read.promise, refresh: async () => {},
    cancelEyeBagRead: async request_id => ({request_id, cancel_requested: true, stopped: false, eye_bag_request: echo(c)})});
  w.update(v, true); const submitted = w.submit(c); const cancel = w.cancelEyeBagRead();
  assert.equal(w.snapshot().pending, true); assert.equal(w.snapshot().eyeBagCancel, 'requested');
  read.resolve({phase: 'done', request_id: c.request_id, result: {protocol: 1, request_id: c.request_id, action: c.action,
    document_id: c.document_id, success: false, outcome_unknown: false, error: 'stopped', eye_bag_cancelled: true, eye_bag_request: echo(c)}});
  await Promise.all([submitted, cancel]); assert.equal(sends, 1); assert.equal(w.snapshot().pending, false);
  assert.equal(w.snapshot().eyeBagCancel, 'stopped'); assert.equal(w.snapshot().lastEyeBagResult, null);
});
test('completed read race is discarded but never labeled stopped', async () => {
  const v = view(), c = request(v), read = deferred<PeopleMailbox>();
  const w = createPeopleWorkflow({send: async () => {}, read: async () => read.promise, refresh: async () => {},
    cancelEyeBagRead: async request_id => ({request_id, cancel_requested: false, stopped: false, eye_bag_request: echo(c)})});
  w.update(v, true); const submitted = w.submit(c), cancel = w.cancelEyeBagRead();
  read.resolve({phase: 'done', request_id: c.request_id, result: {protocol: 1, request_id: c.request_id, action: c.action,
    document_id: c.document_id, success: true, outcome_unknown: false, payload: {}, eye_bag_request: echo(c)}});
  await Promise.all([submitted, cancel]); assert.equal(w.snapshot().eyeBagCancel, 'completed'); assert.equal(w.snapshot().lastEyeBagResult, null);
});
test('native read-only recovery cannot be undone by a late old mailbox callback', async () => {
  const v = view(), c = request(v), read = deferred<PeopleMailbox>();
  const w = createPeopleWorkflow({send: async () => {}, read: async () => read.promise, refresh: async () => {},
    recoverEyeBagRead: async request_id => ({request_id, read_only: true, released: true, reason: 'engine_ended', stopped: true, eye_bag_request: echo(c)})});
  w.update(v, true); const submitted = w.submit(c); await w.recoverEyeBagRead();
  read.resolve({phase: 'unavailable', request_id: c.request_id}); await submitted;
  assert.equal(w.snapshot().pending, false); assert.equal(w.snapshot().uncertain, false); assert.equal(w.snapshot().eyeBagCancel, 'released');
});
test('session drafts clone only recipe/vectors and expire with source revision', () => {
  const v = view(), w = createPeopleWorkflow({send: async () => {}, read: async id => ({phase: 'unavailable', request_id: id}), refresh: async () => {}});
  w.update(v, true); const key = eyeBagBinding(v), draft = {recipe: {version: 2 as const, amount: .4, preserve: 1}, masks: {left: emptyMask(), right: emptyMask()}, replaceLegacy: false};
  w.saveEyeBagDraft(key, draft); draft.recipe.amount = .9;
  assert.equal(w.eyeBagDraft(key)?.recipe.amount, .4);
  const next = structuredClone(v); next.binding.document_revision++;
  w.update(next, true); assert.equal(w.eyeBagDraft(key), null);
});
test('incomplete erase-only draft remains storable but is not an active reviewed mask', async () => {
  const {validDraft} = await import('./draft.ts'); const {validEyes} = await import('./support.ts');
  const mask = emptyMask(); mask.objects.push({id: 'erase', name: 'erase', enabled: true, kind: 'brush', operation: 'subtract', opacity: 1,
    feather: 0, points: [[.5,.5]], axes: [[.01,0],[0,.01]]});
  assert.equal(validDraft({recipe: {version: 2, amount: .4, preserve: 1}, masks: {left: mask, right: emptyMask()}, replaceLegacy: false}), true);
  assert.equal(validEyes({left: {recipe: mask, visible: true, unoccluded: true, ownership_confirmed: true}}, false), false);
});
test('a mutating request never gains cancel or recovery authority', async () => {
  const v = view(), c: PeopleAction = {...request(v), action: 'patch', payload: {patches: []}}, read = deferred<PeopleMailbox>(); let controls = 0;
  const w = createPeopleWorkflow({send: async () => {}, read: async () => read.promise, refresh: async () => {},
    cancelEyeBagRead: async () => {controls++;}, recoverEyeBagRead: async () => {controls++;}});
  w.update(v, true); const submitted = w.submit(c);
  await assert.rejects(w.cancelEyeBagRead()); await assert.rejects(w.recoverEyeBagRead()); assert.equal(controls, 0);
  read.resolve({phase: 'done', request_id: c.request_id, result: {protocol: 1, request_id: c.request_id, action: c.action,
    document_id: c.document_id, success: false, outcome_unknown: false, error: 'declined'}});
  await assert.rejects(submitted);
});
test('a new request gets its own poll after read recovery while old poll is late', async () => {
  const v = view(), c = request(v), old = deferred<PeopleMailbox>(), started = deferred<void>(); let reads = 0;
  const w = createPeopleWorkflow({send: async () => {}, read: async request_id => {
    reads++; if (request_id === c.request_id) {started.resolve(); return old.promise;}
    return {phase: 'done', request_id, result: {protocol: 1, request_id, action: 'eye_bag_reference', document_id: c.document_id,
      success: false, outcome_unknown: false, error: 'declined', eye_bag_request: echo(c)}};
  }, refresh: async () => {}, recoverEyeBagRead: async request_id => ({request_id, read_only: true, released: true,
    reason: 'engine_ended', stopped: true, eye_bag_request: echo(c)})});
  w.update(v, true); const original = w.submit(c); await started.promise;
  await w.recoverEyeBagRead();
  await assert.rejects(w.submit({...c, request_id: 'new-read'}));
  assert.ok(reads >= 2); assert.equal(w.snapshot().pending, false);
  old.resolve({phase: 'unavailable', request_id: c.request_id}); await original;
  assert.equal(w.snapshot().pending, false); assert.equal(w.snapshot().uncertain, false);
});
