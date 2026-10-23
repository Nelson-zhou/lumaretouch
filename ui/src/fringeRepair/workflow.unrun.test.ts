/** Authored fixtures. NEVER EXECUTED in this source-only implementation pass. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {createFringeWorkflow} from './workflow.ts';
import {readReview, reviewImageKey, validDraft, sourceKey, type FringeMutation, type FringeRequest} from './model.ts';
import {readInventory} from './receipts.ts';
import type {FringeTransport} from './protocol.ts';

const source = {sha256: 'd'.repeat(64), width: 12, height: 8};
// Boundary validation is not PNG decoder validation; the UI separately checks
// decoded natural dimensions and visible frame delivery before acknowledgment.
const png = 'data:image/png;base64,AA==';
const review = () => ({source, recipe_document_id: 'a'.repeat(32), recipe_revision: '7',
  image: {before: png, after: png, coverage: png, width: 12, height: 8,
    domain: 'production-output', quality: 'full-source-render-downsampled-srgb8', note: 'Fixture, not a quality result.'},
  recipe: {version: 1, algorithm: 'lrt-fringe-repair-v1', enabled: true, strength: 50, source: null,
    coverage: {domain: 'post-optics-pre-crop-normalized-v1', strokes: []}},
  defaults: {strength: 50, min_strength: 0, max_strength: 100}});
const receipt = (request: FringeRequest, unknown = false) => ({protocol: 1, action: 'apply', ...request,
  success: !unknown, outcome_unknown: unknown, requires_reload: unknown, no_change: false,
  history: unknown ? null : {undo_steps: 1, redo_steps: 0}});
function harness(options: {unknown?: boolean; beforeSubmit?: () => Promise<void>} = {}) {
  let serial = 1, preview = '', session = '', document = '', shown = false;
  let submitted: FringeRequest | null = null, submitCount = 0, renderCount = 0, resultCount = 0;
  const mutations: FringeMutation[] = [];
  const api: FringeTransport = {
    audit: async () => ({protocol: 1, audit_scope: 'application-process', client_generation: '1', count: 0, items: []}),
    preview: async (action, p, s, d, mutation) => {
      if (action === 'preview') {preview = p; session = s; document = d; shown = false; renderCount++; mutations.push(structuredClone(mutation!));}
      if (action === 'presented') shown = true;
      return {};
    },
    status: async () => ({protocol: 1, preview_id: preview, session_id: session, document_id: document,
      state: shown ? 'presented' : 'ready', success: true, ...review()}),
    submit: async request => {submitted = request; submitCount++; return {};},
    result: async () => {resultCount++; return {phase: 'done', request_id: submitted!.request_id, result: receipt(submitted!, options.unknown)};},
  };
  const workflow = createFringeWorkflow(api, {refresh: async () => {}, beforeSubmit: options.beforeSubmit,
    id: () => (serial++).toString(16).padStart(32, '0'), sleep: async () => {}});
  workflow.context({enabled: true, canStart: true, documentId: 'photo-one', contextKey: 'source-one:revision-seven'});
  return {workflow, api, mutations, counts: () => ({submitCount, renderCount, resultCount})};
}
test('enter previews enabled auto recipe without saving; coverage requires explicit update', async () => {
  const {workflow, counts, mutations} = harness();
  await workflow.initialize(); await workflow.start();
  assert.deepEqual(mutations, [{action: 'enter'}]); assert.equal(workflow.snapshot().draft?.enabled, true);
  const draft = workflow.snapshot().draft!;
  assert.equal(workflow.beginStroke(), true);
  workflow.endStroke({id: 'b'.repeat(32), mode: 'subtract', points: [[.2, .3], [.3, .4]], radius: .04, opacity: 1, feather: .5});
  assert.equal(workflow.snapshot().dirty, true); assert.equal(counts().renderCount, 1); assert.equal(counts().submitCount, 0);
  await workflow.confirm(); assert.equal(counts().submitCount, 0);
  await workflow.update(); assert.equal(counts().renderCount, 2);
  assert.equal(mutations[1].action, 'set'); assert.equal(workflow.snapshot().draft?.strength, draft.strength);
  await workflow.presented(workflow.snapshot().previewId!); await workflow.confirm();
  assert.equal(counts().submitCount, 1); assert.equal(workflow.snapshot().phase, 'success');
});
test('editing after decoded presentation invalidates apply until new update and presentation', async () => {
  const {workflow, counts} = harness(); await workflow.initialize(); await workflow.start();
  await workflow.presented(workflow.snapshot().previewId!);
  workflow.edit({...workflow.snapshot().draft!, strength: 35});
  await workflow.confirm(); assert.equal(counts().submitCount, 0);
  assert.equal(workflow.snapshot().presented, false); assert.equal(workflow.snapshot().phase, 'editing');
});
test('identical PNGs in a new candidate get new per-image keys and no inherited presentation', async () => {
  const {workflow} = harness(); await workflow.initialize(); await workflow.start();
  const previous = workflow.snapshot().reviewPreviewId!;
  await workflow.presented(previous);
  workflow.edit({...workflow.snapshot().draft!, strength: 20});
  const updating = workflow.update();
  assert.equal(workflow.snapshot().reviewPreviewId, previous);
  assert.notEqual(workflow.snapshot().previewId, previous); // Pending identity does not relabel old pixels.
  await updating;
  const next = workflow.snapshot().reviewPreviewId!;
  assert.notEqual(next, previous); assert.equal(workflow.snapshot().review?.image.before, png);
  for (const side of ['before', 'after', 'coverage'] as const) assert.notEqual(reviewImageKey(previous, side), reviewImageKey(next, side));
  assert.equal(workflow.snapshot().presented, false);
  await workflow.presented(previous); assert.equal(workflow.snapshot().presented, false);
  await workflow.presented(next); assert.equal(workflow.snapshot().presented, true);
  // Browser verification that key-remounted identical images emit onLoad remains UNRUN.
});
test('unknown original outcomes are queried, never duplicated by reopening or confirm', async () => {
  const {workflow, counts} = harness({unknown: true}); await workflow.initialize(); await workflow.start();
  await workflow.presented(workflow.snapshot().previewId!); await workflow.confirm();
  assert.equal(workflow.snapshot().phase, 'uncertain'); workflow.cancel();
  await workflow.start(); await workflow.confirm(); await workflow.check();
  assert.equal(counts().submitCount, 1); assert.equal(counts().resultCount, 2); assert.equal(workflow.busy(), true);
});
test('cancel while waiting for curve barrier prevents a late native submit', async () => {
  let release!: () => void;
  const gate = new Promise<void>(resolve => {release = resolve;});
  const {workflow, counts} = harness({beforeSubmit: () => gate}); await workflow.initialize(); await workflow.start();
  await workflow.presented(workflow.snapshot().previewId!); const applying = workflow.confirm();
  workflow.cancel(); release(); await applying;
  assert.equal(counts().submitCount, 0); assert.equal(workflow.snapshot().open, false);
});
test('upstream or source context change cancels the uncommitted source-owned draft', async () => {
  const {workflow, counts} = harness(); await workflow.initialize(); await workflow.start();
  workflow.context({enabled: true, documentId: 'photo-two', contextKey: 'source-two:revision-seven'});
  assert.equal(workflow.snapshot().draft, null); assert.equal(workflow.snapshot().open, false);
  await workflow.confirm(); assert.equal(counts().submitCount, 0);
});
test('native audit is mandatory and unresolved original receipt blocks new entry', async () => {
  const {workflow, api, counts} = harness();
  const request = {request_id: 'fringe-old', preview_id: 'b'.repeat(32), session_id: 'c'.repeat(32), document_id: 'old-photo'};
  api.audit = async () => ({protocol: 1, audit_scope: 'application-process', client_generation: '2', count: 1,
    items: [{original_request: request, original_receipt: receipt(request, true), engine_state: 'epoch_changed', unresolved: true}]});
  await workflow.start(); assert.equal(counts().renderCount, 0);
  await workflow.initialize(); await workflow.start(); assert.equal(counts().renderCount, 0);
  assert.equal(workflow.snapshot().request?.request_id, 'fringe-old'); assert.equal(workflow.busy(), true);
});
test('missing inventory and contradictory inventory fail closed', async () => {
  const {workflow, api} = harness(); api.audit = async () => ({});
  await workflow.initialize(); assert.equal(workflow.snapshot().inventory, 'failed'); assert.equal(workflow.busy(), true);
  assert.throws(() => readInventory({protocol: 1, audit_scope: 'application-process', client_generation: '0', count: 0, items: []}));
});
test('source ownership is explicit and null recipe source is only allowed for empty vectors', () => {
  assert.equal(readReview(review()).recipe.source, null);
  const invalid = review(); (invalid.recipe.coverage.strokes as unknown[]).push({id: 'test'});
  assert.throws(() => readReview(invalid));
  assert.equal(sourceKey({a: 1, b: {c: 2}}), sourceKey({b: {c: 2}, a: 1}));
  assert.throws(() => readReview({...review(), source: null}));
});
test('manual vectors obey distinct stroke, per-stroke and aggregate budgets without clipping', () => {
  const stroke = {id: 'b'.repeat(32), mode: 'add' as const, points: [[.5, .5] as [number, number]], radius: .04, opacity: 1, feather: .5};
  const draft = {enabled: true, strength: 50, reset_coverage: false, strokes: [stroke]};
  assert.equal(validDraft(draft), true);
  assert.equal(validDraft({...draft, strokes: [stroke, stroke]}), false);
  assert.equal(validDraft({...draft, strokes: [{...stroke, points: Array.from({length: 1025}, () => [.5, .5] as [number, number])}]}), false);
  assert.equal(validDraft({...draft, strokes: Array.from({length: 9}, (_, index) => ({...stroke,
    id: (index + 1).toString(16).padStart(32, '0'), points: Array.from({length: 1024}, () => [.5, .5] as [number, number])}))}), false);
});
