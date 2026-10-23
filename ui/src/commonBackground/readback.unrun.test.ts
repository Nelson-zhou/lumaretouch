/** AUTHORED ONLY. UNRUN: no imports, test execution, typecheck, build or product launch performed. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflow, type Context, type Transport} from './workflow.ts';
import {defaultDraft, type Request} from './model.ts';
import {auditInventory, type ReadbackRequest} from './readback.ts';

const image = {before: 'data:image/png;base64,iVBORw0KGgo=', after: 'data:image/png;base64,iVBORw0KGgo=', width: 2, height: 2,
  domain: 'production-output', quality: 'proxy-render-srgb8', note: 'Transport placeholder only; image decoding is not tested here.'};
const context: Context = {enabled: true, canStart: true, documentId: '42', contextKey: 'epoch-1:revision-1', engineKey: 'engine-1', readbackEnabled: true};
const request = (n = 1): Request => ({request_id: `original-${n}`, document_id: '42', session_id: '1'.repeat(32), preview_id: n.toString(16).padStart(32, '0')});
const receipt = (r: Request, patch: Record<string, unknown> = {}) => ({protocol: 1, action: 'apply', request_id: r.request_id, document_id: r.document_id, session_id: r.session_id, preview_id: r.preview_id,
  success: true, outcome_unknown: false, requires_reload: false, no_change: false, history: {undo_steps: 1, redo_steps: 0}, ...patch});
const unknown = (r: Request) => receipt(r, {success: false, outcome_unknown: true, requires_reload: true, history: null, error: 'transport or rollback uncertain'});
const item = (r: Request, patch: Record<string, unknown> = {}) => ({original_request: r, original_receipt: unknown(r), readback_result: null,
  readback_id: null, engine_state: 'same_live_engine', unresolved: true, ...patch});
const inventory = (items: unknown[] = [], client_generation = '1') => ({protocol: 1, audit_scope: 'application-process', client_generation, count: items.length, items});
const response = (r: ReadbackRequest, result: unknown = receipt(r), phase = 'found') => ({protocol: 1, action: 'query', audit_scope: 'application-process',
  ...r, phase, result, original_receipt: unknown(r)});
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
function fixture(items: ReturnType<typeof item>[] = [], timeoutMs = 1000, beforeSubmit?: () => Promise<void>) {
  let serial = 10, preview: Record<string, unknown> = {}, refreshes = 0, inventories = 0;
  const sent: Request[] = [], clientGenerations: string[] = [], queries: ReadbackRequest[] = [], statusIds: string[] = [], known = new Map(items.map(value => [value.original_request.request_id, value.original_request]));
  const api: Transport = {
    audit: async () => {inventories++; return inventory(items, String(inventories));},
    preview: async (action, preview_id, session_id, document_id) => {
      if (action === 'preview') preview = {protocol: 1, preview_id, session_id, document_id, state: 'ready', success: true,
        recipe_document_id: '2'.repeat(32), recipe_revision: '2', image};
      if (action === 'presented') preview = {...preview, state: 'presented'};
      return {requested: true};
    },
    status: async () => preview,
    submit: async (r, generation) => {sent.push(r); clientGenerations.push(generation); known.set(r.request_id, r); return {requested: true};},
    result: async request_id => ({phase: 'done', request_id, result: unknown(known.get(request_id)!)}),
    readback: async r => {queries.push(r); return {requested: true};},
    readbackStatus: async readback_id => {statusIds.push(readback_id); return response(queries.find(r => r.readback_id === readback_id)!);},
  };
  const make = () => createWorkflow(api, async () => {refreshes++;}, {beforeSubmit, id: () => (++serial).toString(16).padStart(32, '0'), timeoutMs, sleep: async () => {await tick();}});
  const flow = make(); flow.context(context);
  async function uncertain() {await flow.initialize(); await flow.start(defaultDraft()); await flow.presented(flow.snapshot().previewId!); await flow.confirm(); assert.equal(flow.snapshot().phase, 'uncertain');}
  return {flow, make, api, sent, clientGenerations, queries, statusIds, uncertain, refreshes: () => refreshes, inventories: () => inventories};
}

test('UNRUN: initial editing stays blocked until authoritative native inventory, independent of engine capability', async () => {
  const f = fixture(); f.flow.context({...context, enabled: false, readbackEnabled: false, engineKey: undefined});
  assert.equal(f.flow.busy(), true); await f.flow.start(defaultDraft()); assert.equal(f.sent.length, 0);
  await f.flow.initialize(); assert.equal(f.inventories(), 1); assert.equal(f.flow.snapshot().inventoryPhase, 'ready'); assert.equal(f.flow.busy(), false);
});
test('UNRUN: malformed or failed inventory never silently releases editing', async () => {
  const f = fixture(); f.api.audit = async () => ({...inventory(), count: 5});
  await f.flow.initialize(); assert.equal(f.flow.snapshot().inventoryPhase, 'failed'); assert.equal(f.flow.busy(), true);
  f.api.audit = async () => inventory(); await f.flow.initialize(); assert.equal(f.flow.busy(), false);
});
test('UNRUN: inventory independently rejects unknown marked settled, identity mismatch and duplicate originals', () => {
  assert.throws(() => auditInventory(inventory([item(request(), {unresolved: false})])));
  assert.throws(() => auditInventory(inventory([item(request(), {original_receipt: unknown(request(2))})])));
  assert.throws(() => auditInventory(inventory([item(request()), item(request())])));
});
test('UNRUN: bootstrap requires a canonical positive u64 client generation before admission', async () => {
  for (const value of [undefined, null, 1, '', '0', '01', '-1', '18446744073709551616']) {
    const f = fixture(); f.api.audit = async () => ({...inventory(), client_generation: value});
    await f.flow.initialize(); await f.flow.start(defaultDraft()); await f.flow.confirm();
    assert.equal(f.flow.busy(), true); assert.equal(f.sent.length, 0);
  }
  assert.equal(auditInventory(inventory([], '18446744073709551615')).clientGeneration, '18446744073709551615');
  const f = fixture(); await f.uncertain(); assert.deepEqual(f.clientGenerations, ['1']);
});
test('UNRUN: explicit same-engine readback settles clean success without sending another apply and preserves original audit', async () => {
  const f = fixture(); await f.uncertain(); const original = structuredClone(f.flow.snapshot().audit[0].original_receipt);
  assert.equal(f.queries.length, 0); await f.flow.readback();
  assert.equal(f.sent.length, 1); assert.equal(f.queries.length, 1); assert.equal(f.flow.snapshot().phase, 'success');
  assert.equal(f.flow.snapshot().request, null); assert.equal(f.flow.busy(), false); assert.equal(f.refreshes(), 1);
  assert.deepEqual(f.flow.snapshot().audit[0].original_receipt, original); assert.equal(f.flow.snapshot().audit[0].settled_by, 'readback');
  assert.ok(f.flow.snapshot().audit[0].readbacks[0].status?.original_receipt);
  f.flow.cancel(); assert.equal(f.flow.snapshot().audit.length, 1);
});
test('UNRUN: clean cached rejection settles as failure, never as saved', async () => {
  const f = fixture(); await f.uncertain(); f.api.readbackStatus = async () => response(f.queries[0], receipt(f.sent[0], {success: false, history: null, error: 'not applied'}));
  await f.flow.readback(); assert.equal(f.flow.snapshot().phase, 'failure'); assert.equal(f.flow.busy(), false); assert.equal(f.refreshes(), 0); assert.equal(f.sent.length, 1);
});
test('UNRUN: genuine rollback uncertainty remains locked and identifies checkpoint recovery as distinct', async () => {
  const f = fixture(); await f.uncertain(); f.api.readbackStatus = async () => response(f.queries[0], unknown(f.sent[0]));
  await f.flow.readback(); assert.equal(f.flow.snapshot().phase, 'uncertain'); assert.equal(f.flow.busy(), true);
  assert.match(f.flow.snapshot().message, /检查点/); assert.equal(f.flow.snapshot().audit[0].settled_by, null); assert.equal(f.sent.length, 1);
});
test('UNRUN: missing, epoch-changed, unavailable and failed readbacks are never evidence of noncommit', async () => {
  for (const phase of ['missing', 'epoch_changed', 'engine_unavailable', 'failed', 'unavailable']) {
    const f = fixture(); await f.uncertain(); f.api.readbackStatus = async () => response(f.queries[0], null, phase);
    await f.flow.readback(); assert.equal(f.flow.busy(), true); assert.ok(f.flow.snapshot().request); assert.equal(f.sent.length, 1); assert.equal(f.refreshes(), 0);
  }
});
test('UNRUN: wrong protocol, query identity, original binding or terminal proof cannot settle', async () => {
  for (const patch of [{protocol: 2}, {action: 'apply'}, {readback_id: 'f'.repeat(32)}, {document_id: '99'}, {request_id: 'other'},
    {result: receipt(request(999))}, {result: null}, {original_receipt: undefined}, {original_receipt: unknown(request(999))}, {audit_scope: 'disk'}]) {
    const f = fixture(); await f.uncertain(); f.api.readbackStatus = async () => ({...response(f.queries[0]), ...patch});
    await f.flow.readback(); assert.equal(f.flow.busy(), true); assert.equal(f.sent.length, 1); assert.equal(f.refreshes(), 0);
  }
});
test('UNRUN: minimal unavailable readback is non-evidence, not an invented original identity or noncommit', async () => {
  const f = fixture(); await f.uncertain(); f.api.readbackStatus = async id => ({phase: 'unavailable', readback_id: id, result: null});
  await f.flow.readback(); assert.equal(f.flow.busy(), true); assert.equal(f.flow.snapshot().readbackPhase, 'unavailable');
  assert.equal(f.flow.snapshot().audit[0].readbacks[0].status, null); assert.equal(f.sent.length, 1);
});
test('UNRUN: lost readback send response queries its same ID and never repeats apply', async () => {
  const f = fixture(); await f.uncertain(); f.api.readback = async r => {f.queries.push(r); throw Error('read response lost');};
  await f.flow.readback(); assert.equal(f.flow.snapshot().phase, 'success'); assert.equal(f.queries.length, 1); assert.equal(f.sent.length, 1);
  assert.ok(f.statusIds.every(value => value === f.queries[0].readback_id));
});
test('UNRUN: readback timeout can resume the existing readback ID without a new query send', async () => {
  const f = fixture([], 10); await f.uncertain(); f.api.readbackStatus = () => new Promise(() => {});
  await f.flow.readback(); assert.equal(f.flow.snapshot().readbackPending, false); assert.equal(f.flow.busy(), true);
  f.api.readbackStatus = async () => response(f.queries[0]); await f.flow.readback();
  assert.equal(f.queries.length, 1); assert.equal(f.sent.length, 1); assert.equal(f.flow.snapshot().phase, 'success');
});
test('UNRUN: repeated clicks and ordinary receipt checks do not race an in-flight readback', async () => {
  const f = fixture(); await f.uncertain(); let resolve!: (value: unknown) => void;
  f.api.readbackStatus = () => new Promise(done => {resolve = done;}); const reading = f.flow.readback(); await tick();
  await f.flow.readback(); await f.flow.check(); assert.equal(f.queries.length, 1);
  resolve(response(f.queries[0])); await reading; assert.equal(f.sent.length, 1);
});
test('UNRUN: closing and changing the viewed photo does not attribute the old receipt to the new photo', async () => {
  const f = fixture(); await f.uncertain(); let resolve!: (value: unknown) => void;
  f.api.readbackStatus = () => new Promise(done => {resolve = done;}); const reading = f.flow.readback(); await tick();
  f.flow.cancel(); f.flow.context({...context, documentId: '99', contextKey: 'other-photo'});
  resolve(response(f.queries[0])); await reading; assert.equal(f.flow.snapshot().phase, 'success'); assert.match(f.flow.snapshot().message, /上一张照片/);
  assert.equal(f.flow.snapshot().audit[0].original_request.document_id, '42'); assert.equal(f.sent.length, 1);
});
test('UNRUN: stop/reactivate ignores old asynchronous readback and keeps original request', async () => {
  const f = fixture(); await f.uncertain(); let resolve!: (value: unknown) => void;
  f.api.readbackStatus = () => new Promise(done => {resolve = done;}); const reading = f.flow.readback(); await tick();
  f.flow.stop(); f.flow.activate(); resolve(response(f.queries[0])); await reading;
  assert.equal(f.flow.busy(), true); assert.equal(f.refreshes(), 0); assert.ok(f.flow.snapshot().request);
  f.api.readbackStatus = async () => response(f.queries[0]); await f.flow.readback(); assert.equal(f.flow.snapshot().phase, 'success'); assert.equal(f.queries.length, 1);
});
test('UNRUN: engine epoch changes invalidate an in-flight readback without unlocking', async () => {
  const f = fixture(); await f.uncertain(); let resolve!: (value: unknown) => void;
  f.api.readbackStatus = () => new Promise(done => {resolve = done;}); const reading = f.flow.readback(); await tick();
  f.flow.context({...context, engineKey: 'engine-2', contextKey: 'epoch-2'}); resolve(response(f.queries[0])); await reading;
  assert.equal(f.flow.busy(), true); assert.equal(f.flow.snapshot().readbackPhase, 'epoch_changed'); assert.equal(f.refreshes(), 0);
});
test('UNRUN: initial PID arrival cannot strand or duplicate the process-owned inventory bootstrap', async () => {
  const f = fixture(); const pending: ((value: unknown) => void)[] = [];
  f.api.audit = () => new Promise(resolve => pending.push(resolve)); f.flow.context({...context, engineKey: undefined});
  const first = f.flow.initialize(); assert.equal(pending.length, 1); f.flow.context(context); assert.equal(pending.length, 1);
  pending[0](inventory([item(request())])); await first;
  assert.equal(f.flow.snapshot().inventoryPhase, 'ready'); assert.equal(f.flow.busy(), true); assert.equal(f.flow.snapshot().request?.request_id, 'original-1');
});
test('UNRUN: full new workflow instance restores native unresolved records even without a live engine or capability', async () => {
  const f = fixture([item(request(), {engine_state: 'epoch_changed'})]); const remounted = f.make();
  remounted.context({...context, enabled: false, readbackEnabled: false, engineKey: 'engine-2'});
  assert.equal(remounted.busy(), true); await remounted.initialize(); assert.equal(remounted.busy(), true);
  assert.equal(remounted.snapshot().audit.length, 1); assert.equal(remounted.snapshot().request?.request_id, 'original-1'); assert.equal(f.sent.length, 0);
});
test('UNRUN: multiple native originals reconcile sequentially and every original audit remains', async () => {
  const f = fixture([item(request(1)), item(request(2))]); await f.flow.initialize();
  assert.equal(f.flow.snapshot().unresolved.length, 2); await f.flow.readback();
  assert.equal(f.flow.snapshot().request?.request_id, 'original-2'); assert.equal(f.flow.busy(), true); assert.equal(f.flow.snapshot().audit[0].settled_by, 'readback');
  await f.flow.readback(); assert.equal(f.flow.busy(), false); assert.equal(f.flow.snapshot().unresolved.length, 0);
  assert.equal(f.flow.snapshot().audit.length, 2); assert.ok(f.flow.snapshot().audit.every(entry => entry.original_receipt && entry.settled_by === 'readback')); assert.equal(f.sent.length, 0);
});
test('UNRUN: authoritative pre-admission not_sent receipt settles without fabricated history', async () => {
  const f = fixture(); f.api.result = async request_id => ({phase: 'done', request_id,
    result: receipt(f.sent[0], {success: false, history: null, submission: 'not_sent', error: 'proof changed before admission'})});
  await f.flow.initialize(); await f.flow.start(defaultDraft()); await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm();
  assert.equal(f.flow.snapshot().phase, 'failure'); assert.equal(f.flow.busy(), false); assert.equal(f.flow.snapshot().audit[0].settled_by, 'original-receipt');
});
test('UNRUN: rejected edit-settlement preflight is definitely unsent, not a permanent unknown', async () => {
  const f = fixture([], 1000, async () => {throw Error('curve edit failed');});
  await f.flow.initialize(); await f.flow.start(defaultDraft()); await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm();
  assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().audit.length, 0); assert.equal(f.flow.snapshot().request, null);
  assert.equal(f.flow.snapshot().phase, 'failure'); assert.equal(f.flow.busy(), false); assert.match(f.flow.snapshot().message, /未发送/);
});
test('UNRUN: canceled, changed, dirtied or unmounted confirmation preflight never later submits', async () => {
  for (const invalidation of ['cancel', 'context', 'dirty', 'stop']) {
    let resume!: () => void; const f = fixture([], 1000, () => new Promise<void>(resolve => {resume = resolve;}));
    await f.flow.initialize(); await f.flow.start(defaultDraft()); await f.flow.presented(f.flow.snapshot().previewId!);
    const confirming = f.flow.confirm(); assert.equal(f.flow.snapshot().phase, 'confirming'); await f.flow.confirm(); assert.equal(f.sent.length, 0);
    if (invalidation === 'cancel') f.flow.cancel();
    if (invalidation === 'context') f.flow.context({...context, contextKey: 'new-revision'});
    if (invalidation === 'dirty') f.flow.dirty();
    if (invalidation === 'stop') {f.flow.stop(); const remounted = f.make(); remounted.context(context); await remounted.initialize(); assert.equal(remounted.busy(), false); f.flow.activate();}
    resume(); await confirming; assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().request, null); assert.equal(f.flow.snapshot().audit.length, 0);
  }
});
test('UNRUN: delayed native admission carries the old generation and cannot mutate after a new bootstrap', async () => {
  const f = fixture(); let resume!: () => void, mutations = 0, original: Request | null = null;
  f.api.submit = (r, generation) => {original = r; return new Promise<void>(resolve => {resume = () => {if (generation === String(f.inventories())) mutations++; resolve();};});};
  await f.flow.initialize(); await f.flow.start(defaultDraft()); await f.flow.presented(f.flow.snapshot().previewId!);
  const sending = f.flow.confirm(); await tick(); assert.ok(original); f.flow.stop();
  const remounted = f.make(); remounted.context(context); await remounted.initialize(); assert.equal(f.inventories(), 2);
  resume(); await sending; assert.equal(mutations, 0); assert.equal(remounted.busy(), false);
  // This transport models the native atomic-generation gate; it is not native execution evidence.
});
