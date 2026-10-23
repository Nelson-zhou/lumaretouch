/** AUTHORED ONLY. UNRUN: no import, test runner, build, product launch or typecheck was performed. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createWorkflow, type Transport} from './workflow.ts';
import {defaultDraft, readRecipe, readReview, type Request} from './model.ts';

const image = {before: 'data:image/png;base64,iVBORw0KGgo=', after: 'data:image/png;base64,iVBORw0KGgo=',
  width: 2, height: 2, domain: 'production-output', quality: 'proxy-render-srgb8', note: 'Fixture only, not a decoded image.'};
const recipe = {recipe_document_id: 'abcdef0123456789abcdef0123456789', recipe_revision: '9007199254740993'};
const tick = () => new Promise<void>(resolve => setImmediate(resolve));
function completed(r: Request, patch: Record<string, unknown> = {}) {
  return {phase: 'done', request_id: r.request_id, result: {protocol: 1, action: 'apply', ...r,
    success: true, outcome_unknown: false, requires_reload: false, no_change: false,
    history: {undo_steps: 1, redo_steps: 0}, ...patch}};
}
function fixture(timeoutMs = 1000) {
  const sent: Request[] = [], queried: string[] = [], canceled: string[] = [];
  let serial = 0, refreshes = 0, preview: Record<string, unknown> = {};
  const api: Transport = {
    preview: async (action, preview_id, session_id, document_id) => {
      if (action === 'preview') preview = {protocol: 1, preview_id, session_id, document_id, state: 'ready', success: true, ...recipe, image};
      if (action === 'presented') preview = {...preview, state: 'presented'};
      if (action === 'cancel') canceled.push(preview_id);
      return {requested: true};
    },
    status: async () => preview,
    submit: async request => {sent.push(request); return {requested: true};},
    result: async request_id => {queried.push(request_id); return completed(sent[0]);},
  };
  const flow = createWorkflow(api, async () => {refreshes++;}, {id: () => (++serial).toString(16).padStart(32, '0'), timeoutMs, sleep: async () => {await tick();}});
  flow.context({enabled: true, documentId: 'photo-original', contextKey: 'epoch-1:revision-4'});
  async function ready() {await flow.start(defaultDraft()); assert.equal(flow.snapshot().phase, 'ready');}
  async function presented() {await ready(); await flow.presented(flow.snapshot().previewId!); assert.equal(flow.snapshot().presented, true);}
  return {flow, api, sent, queried, canceled, ready, presented, preview: () => preview,
    replacePreview: (next: Record<string, unknown>) => {preview = next;}, refreshes: () => refreshes};
}

test('UNRUN: strict production-output image and lossless recipe revision contracts', () => {
  assert.equal(readReview(image).quality, 'proxy-render-srgb8');
  assert.equal(readRecipe(recipe).recipe_revision, '9007199254740993');
  for (const bad of [{...recipe, recipe_revision: 1}, {...recipe, recipe_revision: '-1'}, {...recipe, recipe_revision: '18446744073709551616'},
    {...recipe, recipe_document_id: 'other'}, {...recipe, recipe_document_id: '0'.repeat(32)}]) assert.throws(() => readRecipe(bad));
  for (const bad of [{...image, domain: 'source-normalized'}, {...image, before: 'data:image/jpeg;base64,aA=='}, {...image, width: 0}, {...image, note: null}]) assert.throws(() => readReview(bad));
});
test('UNRUN: rejected peer preparation never acquires ownership or previews', async () => {
  const f = fixture(); let previews = 0;
  const api = {...f.api, preview: async (...args: Parameters<Transport['preview']>) => {previews++; return f.api.preview(...args);}};
  const flow = createWorkflow(api, async () => {}, {prepare: async () => {throw Error('another editor owns the document');}});
  flow.context({enabled: true, documentId: 'photo-original', contextKey: 'revision-1'});
  const open: boolean[] = []; flow.subscribe(state => open.push(state.open));
  await flow.start(defaultDraft()); assert.equal(flow.snapshot().phase, 'failure'); assert.equal(previews, 0);
  assert.ok(open.every(value => value === false));
});
test('UNRUN: cancellation while settling edits prevents a late preparation from creating a preview', async () => {
  const f = fixture(); let resume!: () => void, previews = 0;
  const api = {...f.api, preview: async (...args: Parameters<Transport['preview']>) => {previews++; return f.api.preview(...args);}};
  const flow = createWorkflow(api, async () => {}, {prepare: () => new Promise<void>(resolve => {resume = resolve;})});
  flow.context({enabled: true, documentId: 'photo-original', contextKey: 'revision-1'});
  const preparing = flow.start(defaultDraft()); assert.equal(flow.snapshot().phase, 'preparing');
  flow.cancel(); resume(); await preparing; assert.equal(flow.snapshot().phase, 'idle'); assert.equal(previews, 0);
});
test('UNRUN: generating a preview is not apply; image-presentation acknowledgment is mandatory', async () => {
  const f = fixture(); await f.ready(); await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm();
  assert.equal(f.sent.length, 1); assert.equal(f.flow.snapshot().phase, 'success'); assert.equal(f.refreshes(), 1);
});
test('UNRUN: native presented rejection cannot be replaced with a server-ready receipt', async () => {
  const f = fixture(); await f.ready(); const original = f.api.preview;
  f.api.preview = async (...args) => {if (args[0] === 'presented') throw Error('native refused'); return original(...args);};
  await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm();
  assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().phase, 'failure');
});
test('UNRUN: server-presented recipe identity must exactly match the displayed preview', async () => {
  const f = fixture(); await f.ready(); const original = f.api.preview;
  f.api.preview = async (...args) => {const r = await original(...args); if (args[0] === 'presented') f.replacePreview({...f.preview(), recipe_revision: '9007199254740994'}); return r;};
  await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm();
  assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().phase, 'failure');
});
test('UNRUN: editing parameters invalidates commit eligibility until a new preview is presented', async () => {
  const f = fixture(); await f.presented(); const old = f.flow.snapshot().previewId;
  f.flow.dirty(); await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.flow.render({...defaultDraft(), tol: .4}); assert.notEqual(f.flow.snapshot().previewId, old);
  await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.flow.presented(f.flow.snapshot().previewId!); await f.flow.confirm(); assert.equal(f.sent.length, 1);
});
test('UNRUN: clear follows the same review barrier and a no-change receipt creates no claimed history', async () => {
  const f = fixture(); await f.flow.start({action: 'clear'}); await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.flow.presented(f.flow.snapshot().previewId!);
  f.api.result = async () => completed(f.sent[0], {no_change: true, history: {undo_steps: 0, redo_steps: 0}});
  await f.flow.confirm(); assert.equal(f.sent.length, 1); assert.match(f.flow.snapshot().message, /未新增历史/);
});
test('UNRUN: canceled and revision-invalidated drafts never apply', async () => {
  const f = fixture(); await f.presented(); f.flow.cancel(); await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.presented(); f.flow.context({enabled: true, documentId: 'photo-original', contextKey: 'epoch-1:revision-5'});
  await f.flow.confirm(); assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().phase, 'idle');
});
test('UNRUN: originals and opaque returned composites each bind their own document identity', async () => {
  const f = fixture(); await f.presented(); f.flow.context({enabled: true, documentId: 'opaque-sdr-returned-composite', contextKey: 'returned:revision-1'});
  await f.flow.confirm(); assert.equal(f.sent.length, 0);
  await f.presented(); await f.flow.confirm(); assert.equal(f.sent[0].document_id, 'opaque-sdr-returned-composite');
});
test('UNRUN: queue occupancy blocks new starts/commit but does not discard its own preview', async () => {
  const f = fixture(); f.flow.context({enabled: true, canStart: false, documentId: 'photo-original', contextKey: 'epoch-1:revision-4'});
  await f.flow.start(defaultDraft()); assert.equal(f.flow.snapshot().phase, 'idle');
  f.flow.context({enabled: true, canStart: true, documentId: 'photo-original', contextKey: 'epoch-1:revision-4'}); await f.presented();
  f.flow.context({enabled: true, canStart: false, documentId: 'photo-original', contextKey: 'epoch-1:revision-4'});
  await f.flow.confirm(); assert.equal(f.sent.length, 0); assert.equal(f.flow.snapshot().phase, 'ready');
});
test('UNRUN: a queue-accepted write is not success and repeated clicks submit only once', async () => {
  const f = fixture(); await f.presented(); let resolve!: (value: unknown) => void;
  f.api.result = () => new Promise(done => {resolve = done;});
  const work = f.flow.confirm(); await tick(); assert.equal(f.flow.snapshot().phase, 'sending');
  assert.equal(f.refreshes(), 0); await f.flow.confirm(); assert.equal(f.sent.length, 1);
  resolve(completed(f.sent[0])); await work; assert.equal(f.flow.snapshot().phase, 'success');
});
test('UNRUN: close and context change during a sent write preserve its receipt without cancel', async () => {
  const f = fixture(); await f.presented(); const canceledBefore = f.canceled.length; let resolve!: (value: unknown) => void;
  f.api.result = () => new Promise(done => {resolve = done;}); const work = f.flow.confirm(); await tick();
  f.flow.cancel(); f.flow.context({enabled: true, documentId: 'other-photo', contextKey: 'different'});
  assert.equal(f.flow.snapshot().open, false); assert.ok(f.flow.snapshot().request); assert.equal(f.canceled.length, canceledBefore);
  resolve(completed(f.sent[0])); await work; assert.equal(f.sent.length, 1); assert.match(f.flow.snapshot().message, /上一张照片/);
});
test('UNRUN: unmount retains an uncertain original receipt and ignores late completion while stopped', async () => {
  const f = fixture(); await f.presented(); const canceledBefore = f.canceled.length; let resolve!: (value: unknown) => void;
  f.api.result = () => new Promise(done => {resolve = done;}); const work = f.flow.confirm(); await tick(); f.flow.stop();
  resolve(completed(f.sent[0])); await work; assert.equal(f.flow.snapshot().phase, 'uncertain');
  assert.equal(f.canceled.length, canceledBefore); assert.equal(f.refreshes(), 0);
  f.flow.activate(); f.api.result = async () => completed(f.sent[0]); await f.flow.check();
  assert.equal(f.flow.snapshot().phase, 'success'); assert.equal(f.sent.length, 1);
});
test('UNRUN: lost send response and unknown result query only the original request', async () => {
  const f = fixture(); await f.presented(); f.api.submit = async request => {f.sent.push(request); throw Error('transport lost');};
  f.api.result = async request_id => ({phase: 'unavailable', request_id});
  await f.flow.confirm(); assert.equal(f.flow.snapshot().phase, 'uncertain'); const original = f.sent[0];
  await f.flow.start(defaultDraft()); await f.flow.confirm(); assert.equal(f.sent.length, 1);
  f.api.result = async request_id => {assert.equal(request_id, original.request_id); return completed(original);};
  await f.flow.check(); assert.equal(f.sent.length, 1); assert.equal(f.flow.snapshot().phase, 'success');
});
test('UNRUN: wrong identities, reload requirement, unknown outcome and absent history cannot claim saved', async () => {
  for (const patch of [{protocol: 2}, {document_id: 'wrong'}, {preview_id: 'wrong'}, {session_id: 'wrong'},
    {outcome_unknown: true}, {requires_reload: true}, {no_change: undefined}, {history: null}]) {
    const f = fixture(); await f.presented(); f.api.result = async () => completed(f.sent[0], patch);
    await f.flow.confirm(); assert.equal(f.flow.snapshot().phase, 'uncertain'); assert.equal(f.refreshes(), 0); assert.ok(f.flow.snapshot().request);
  }
});
test('UNRUN: timed-out submission remains queryable and is never automatically resent', async () => {
  const f = fixture(10); await f.presented(); f.api.submit = async request => {f.sent.push(request); return new Promise(() => {});};
  f.api.result = async () => new Promise(() => {}); await f.flow.confirm();
  assert.equal(f.flow.snapshot().phase, 'uncertain'); await f.flow.confirm(); assert.equal(f.sent.length, 1);
});
test('UNRUN: late stale image errors cannot invalidate a newer preview or a sent operation', async () => {
  const f = fixture(); await f.presented(); const old = f.flow.snapshot().previewId!;
  await f.flow.render({...defaultDraft(), tol: .2}); f.flow.failed('late image error', old);
  assert.equal(f.flow.snapshot().phase, 'ready');
});
