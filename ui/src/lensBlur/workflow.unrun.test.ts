// AUTHORED / UNRUN. This file has not been imported, executed, typechecked or built.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import {createLensBlurWorkflow} from './workflow.ts';
import {LENS_OPERATION, LENS_COHORT_OPERATION, LENS_COHORT_MATH, LENS_PROTOCOL, lensReviewKey, recipeForLensRenderer,
  type LensBlurPort, type LensCapability, type LensContext, type LensPng, type LensReview, type LensPreviewCommand, type LensWriteCommand, type LensReceipt} from './model.ts';
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
function crc(bytes: Uint8Array): number {
  let value = 0xffffffff;
  for (const byte of bytes) {value ^= byte; for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);}
  return (value ^ 0xffffffff) >>> 0;
}
function png(red = 20): LensPng {
  const chunk = (kind: string, bytes: Buffer) => {const body = Buffer.concat([Buffer.from(kind), bytes]), head = Buffer.alloc(4), tail = Buffer.alloc(4); head.writeUInt32BE(bytes.length); tail.writeUInt32BE(crc(body)); return Buffer.concat([head, body, tail]);};
  const header = Buffer.alloc(13); header.writeUInt32BE(2, 0); header.writeUInt32BE(2, 4); header[8] = 8; header[9] = 2;
  const data = Buffer.from([0, red, 30, 40, red, 30, 40, 0, red, 30, 40, red, 30, 40]);
  const bytes = Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk('IHDR', header), chunk('IDAT', deflateSync(data)), chunk('IEND', Buffer.alloc(0))]);
  return {mime: 'image/png', width: 2, height: 2, sha256: sha(bytes), base64: bytes.toString('base64')};
}
function context(): LensContext {
  const raster = Buffer.from([0, 0, 255, 255, 0, 0, 255, 255]);
  const owner = {document_id: 'doc', document_epoch: 'epoch', document_revision: '2', source: {sha256: '1'.repeat(64), width: 2, height: 2, orientation: 'exif_normalized_once' as const}};
  return {session_id: 'session', owner, source_image: png(), depth_status: 'ready', message: '', depth: {version: 1, token: 'depth', owner,
    convention: 'near-zero-far-one', mapping: 'normalized_full_frame_pixel_centres', orientation: 'exif_normalized_once',
    raster: {format: 'u16-le', width: 2, height: 2, sha256: sha(raster), base64: raster.toString('base64')},
    provenance: {kind: 'manual', method: 'user_supplied_depth'}, subject_focus: null}};
}
function manualContext(): LensContext {
  const c = context(), raster = Buffer.from([0,128,0,128,0,128,0,128]);
  c.depth!.provenance = {kind: 'manual', method: 'user_defined_plane', depth_value: .5, acknowledgement_id: 'explicit-plane'};
  c.depth!.raster = {format: 'u16-le', width: 2, height: 2, sha256: sha(raster), base64: raster.toString('base64')};
  return c;
}
const capability = (renderers: LensCapability['renderers'] = ['direct-v1']): LensCapability => ({version: 2, operation_id: LENS_OPERATION,
  status: 'available', kernels: ['circular_disk'], renderers, reason: ''});
function identity(command: LensWriteCommand) {return {version: LENS_PROTOCOL, action: command.action, request_id: command.request_id, session_id: command.session_id, owner: command.owner, token: command.token, message: ''};}
function applied(command: LensWriteCommand): LensReceipt {
  if (command.action !== 'apply') throw Error('wrong fixture');
  return {...identity(command), phase: 'done', outcome_unknown: false, outcome: 'applied', recipe_sha256: command.recipe_sha256,
    before_sha256: command.before_sha256, after_sha256: command.after_sha256, return_mode: 'new_image', copied_original_document_id: command.owner.document_id,
    result_document_id: 'new-copy', result_revision: '1', result_source_sha256: command.result_source_sha256, no_change: false};
}
async function setup(options: NonNullable<Parameters<typeof createLensBlurWorkflow>[1]> = {}, sourceContext = context(), caps = capability()) {
  let serial = 0, receipt: unknown = null;
  const sent: LensWriteCommand[] = [], queried: LensWriteCommand[] = [], previews: LensPreviewCommand[] = [];
  const port: LensBlurPort = {protocol: LENS_PROTOCOL,
    async preview(command) {previews.push(command); return {version: LENS_PROTOCOL, request_id: command.request_id, session_id: command.session_id, token: 'review', owner: command.owner,
      recipe: command.recipe, recipe_sha256: '2'.repeat(64), before: png(), after: png(80), notes: [], result_source_sha256: '3'.repeat(64)} satisfies LensReview;},
    async submit(command) {sent.push(command); return receipt ?? {...identity(command), phase: 'pending', outcome_unknown: true};},
    async receipt(command) {queried.push(command); return receipt;}};
  const workflow = createLensBlurWorkflow(port, {requestId: () => `request-${++serial}`, ...options});
  workflow.setCapability(caps);
  await workflow.setContext(sourceContext);
  const source = sourceContext.source_image; workflow.sourcePresented(source.sha256, source.width, source.height, true);
  return {workflow, port, sent, queried, previews, setReceipt(value: unknown) {receipt = value;}};
}
function showBoth(w: ReturnType<typeof createLensBlurWorkflow>) {
  const r = w.snapshot().review!;
  w.presented('before', lensReviewKey(r), r.before.width, r.before.height, true);
  w.presented('after', lensReviewKey(r), r.after.width, r.after.height, true);
}
test('real loaded images and acknowledgement are separate; edits and unmount revoke consent', async () => {
  const {workflow: w, sent} = await setup();
  await w.preview(); w.acknowledge(true); await w.apply(); assert.equal(sent.length, 0);
  const r = w.snapshot().review!; w.presented('before', lensReviewKey(r), 2, 2, true); w.acknowledge(true); await w.apply(); assert.equal(sent.length, 0);
  showBoth(w); w.acknowledge(true); assert.equal(w.snapshot().acknowledged, true);
  w.edit({...w.snapshot().recipe!, max_radius_px: 10}); assert.equal(w.snapshot().review, null); assert.equal(w.snapshot().acknowledged, false);
  await w.preview(); showBoth(w); w.acknowledge(true); w.releasePresentation(); await w.apply(); assert.equal(sent.length, 0);
});
test('unknown and pending original writes are never resent or closed as cancelled', async () => {
  const {workflow: w, sent, queried, setReceipt} = await setup();
  await w.preview(); showBoth(w); w.acknowledge(true); await w.apply(); assert.equal(sent.length, 1); assert.equal(w.snapshot().phase, 'pending');
  await w.apply(); await w.cancel(); assert.equal(sent.length, 1);
  await w.check(); assert.equal(w.snapshot().phase, 'unknown'); assert.equal(queried[0].request_id, sent[0].request_id);
  await w.setContext({...context(), owner: {...context().owner, document_revision: '3'}}); assert.equal(w.snapshot().stale, true);
  await w.apply(); await w.cancel(); assert.equal(sent.length, 1);
  const c = sent[0]; assert.equal(c.action, 'apply'); if (c.action !== 'apply') throw Error('wrong fixture');
  assert.equal(c.version, LENS_PROTOCOL); assert.equal(c.return_mode, 'new_image'); assert.equal(c.result_source_sha256, '3'.repeat(64));
  setReceipt({...applied(c), result_document_id: c.owner.document_id});
  await w.check(); assert.equal(w.snapshot().phase, 'unknown'); assert.equal(sent.length, 1);
  setReceipt({...applied(c), result_source_sha256: c.after_sha256});
  await w.check(); assert.equal(w.snapshot().phase, 'unknown'); assert.equal(sent.length, 1);
  setReceipt(applied(c));
  await w.check(); assert.equal(w.snapshot().phase, 'applied'); assert.equal(sent.length, 1);
  assert.equal(w.snapshot().terminal_refresh, 'not-configured');
});
test('actual terminal callback receives the distinct copy and completes before automatic exit is eligible', async () => {
  let release!: () => void, entered!: () => void;
  const gate = new Promise<void>(resolve => {release = resolve;}), started = new Promise<void>(resolve => {entered = resolve;});
  const refreshed: {receipt: LensReceipt; command: LensWriteCommand}[] = [];
  const {workflow: w, sent, queried, setReceipt} = await setup({onTerminal: async (receipt, command) => {
    refreshed.push({receipt, command}); entered(); await gate;
  }});
  await w.preview(); showBoth(w); w.acknowledge(true); await w.apply();
  setReceipt(applied(sent[0])); const checking = w.check(); await started;
  assert.equal(w.snapshot().phase, 'applied'); assert.equal(w.snapshot().terminal_refresh, 'refreshing');
  await w.setContext({...context(), session_id: 'copy-session', owner: {...context().owner, document_id: 'new-copy'}});
  assert.equal(w.snapshot().context?.session_id, 'session');
  assert.deepEqual(refreshed[0].receipt, applied(sent[0])); assert.deepEqual(refreshed[0].command, sent[0]);
  await w.apply(); await w.cancel(); assert.equal(sent.length, 1);
  release(); await checking;
  assert.equal(w.snapshot().terminal_refresh, 'ready'); assert.equal(queried.length, 1);
});
test('failed editor refresh preserves successful save and retries only the original read-only callback', async () => {
  let refreshes = 0;
  const {workflow: w, sent, queried, setReceipt} = await setup({onTerminal: () => {
    if (++refreshes === 1) throw Error('read-only refresh unavailable');
  }});
  await w.preview(); showBoth(w); w.acknowledge(true); await w.apply();
  const receipt = applied(sent[0]); setReceipt(receipt); await w.check();
  assert.equal(w.snapshot().phase, 'applied'); assert.equal(w.snapshot().terminal_refresh, 'failed');
  assert.deepEqual(w.snapshot().terminal_receipt, receipt); assert.equal(w.snapshot().request, null);
  await w.apply(); await w.cancel(); await w.refreshTerminal();
  assert.equal(w.snapshot().terminal_refresh, 'ready'); assert.equal(refreshes, 2); assert.equal(sent.length, 1); assert.equal(queried.length, 1);
});
test('disabling module preserves recipe and neutral state but invalidates the review', async () => {
  const {workflow: w, sent} = await setup();
  w.edit({...w.snapshot().recipe!, max_radius_px: 12}); await w.preview(); showBoth(w); w.acknowledge(true);
  w.setCapability({version: 2, operation_id: LENS_OPERATION, status: 'unavailable', kernels: [], renderers: [], reason: 'missing native module'});
  assert.equal(w.snapshot().recipe?.max_radius_px, 12); assert.equal(w.snapshot().review, null);
  await w.apply(); assert.equal(sent.length, 0);
});
test('an unavailable capability with an empty reason still blocks all rendering', async () => {
  const {workflow: w, previews} = await setup();
  w.setCapability({version: 2, operation_id: LENS_OPERATION, status: 'unavailable', kernels: [], renderers: [], reason: ''});
  assert.equal(w.renderingAvailable(), false); assert.notEqual(w.rendererBlockReason(), '');
  await w.preview(); assert.equal(previews.length, 0);
});
test('new manual session prefers v1; explicit renderer selection preserves controls and revokes old review', async () => {
  const {workflow: w, previews, sent} = await setup({}, manualContext(), capability(['cohort-fft-v2', 'direct-v1']));
  assert.equal(w.snapshot().recipe?.version, 1);
  w.edit({...w.snapshot().recipe!, max_radius_px: 12, rotation_radians: .25});
  w.addStroke({id: 'paint', mode: 'blur', amount: .8, flow: .5, feather: .6, radius: .02, points: [{x: .4, y: .6}]});
  const v1 = structuredClone(w.snapshot().recipe!);
  const converted = recipeForLensRenderer(v1, 'cohort-fft-v2');
  assert.ok(converted); if (!converted) throw Error('missing v2 fixture');
  assert.equal(w.edit(converted), false); // Ordinary edits cannot act as a silent version migration.
  await w.preview(); showBoth(w); w.acknowledge(true);
  assert.equal(w.selectRenderer('cohort-fft-v2'), true);
  assert.equal(w.snapshot().recipe?.version, 2); assert.equal(w.snapshot().recipe?.operation_id, LENS_COHORT_OPERATION);
  assert.equal(w.snapshot().review, null); assert.equal(w.snapshot().acknowledged, false); assert.equal(w.snapshot().renderer_acknowledged, false);
  assert.deepEqual(w.snapshot().recipe?.refinements, v1.refinements); assert.equal(w.snapshot().recipe?.max_radius_px, v1.max_radius_px);
  await w.preview(); assert.equal(previews.length, 1); await w.apply(); assert.equal(sent.length, 0);
  w.acknowledgeRenderer(true); await w.preview(); assert.equal(previews.length, 2);
  const r = w.snapshot().review!; assert.equal(r.version, 3);
  assert.equal(r.recipe.version, 2); if (r.recipe.version !== 2) throw Error('wrong recipe fixture');
  assert.equal(r.recipe.math_identity, LENS_COHORT_MATH);
  showBoth(w); w.acknowledge(true); assert.equal(w.snapshot().acknowledged, true);
  w.acknowledgeRenderer(false); assert.equal(w.snapshot().review, null); assert.equal(w.snapshot().acknowledged, false);
  assert.equal(w.renderingAvailable(), false);
  assert.equal(w.selectRenderer('direct-v1'), true); assert.deepEqual(w.snapshot().recipe, v1);
});
test('cohort-only new session still requires explicit v2 math acknowledgement and never falls back', async () => {
  const {workflow: w, previews} = await setup({}, manualContext(), capability(['cohort-fft-v2']));
  assert.equal(w.snapshot().recipe?.version, 2); assert.equal(w.snapshot().renderer_acknowledged, false);
  await w.preview(); assert.equal(previews.length, 0);
  w.acknowledgeRenderer(true); await w.preview(); assert.equal(previews.length, 1);
  const retained = structuredClone(w.snapshot().recipe!);
  w.setCapability(capability(['direct-v1']));
  assert.deepEqual(w.snapshot().recipe, retained); assert.equal(w.snapshot().review, null);
  assert.equal(w.snapshot().renderer_acknowledged, false); assert.equal(w.renderingAvailable(), false);
  await w.preview(); assert.equal(previews.length, 1);
  w.setCapability(capability(['direct-v1', 'cohort-fft-v2']));
  assert.deepEqual(w.snapshot().recipe, retained); await w.preview(); assert.equal(previews.length, 1);
  w.acknowledgeRenderer(true); await w.preview(); assert.equal(previews.length, 2);
});
test('capability changes do not reinterpret an existing v1 recipe as v2', async () => {
  const {workflow: w, previews} = await setup({}, manualContext(), capability(['direct-v1']));
  const v1 = structuredClone(w.snapshot().recipe!);
  w.setCapability(capability(['cohort-fft-v2']));
  assert.deepEqual(w.snapshot().recipe, v1); assert.equal(w.renderingAvailable(), false);
  await w.preview(); assert.equal(previews.length, 0);
  assert.equal(w.selectRenderer('cohort-fft-v2'), true); assert.equal(w.snapshot().recipe?.version, 2);
});
test('v2 selection refuses real supplied-depth provenance instead of relabeling it as a manual plane', async () => {
  const {workflow: w, previews} = await setup({}, context(), capability(['direct-v1', 'cohort-fft-v2']));
  const saved = structuredClone(w.snapshot().recipe!);
  assert.equal(w.selectRenderer('cohort-fft-v2'), false); assert.deepEqual(w.snapshot().recipe, saved);
  const {workflow: onlyV2, previews: onlyPreviews} = await setup({}, context(), capability(['cohort-fft-v2']));
  assert.equal(onlyV2.renderingAvailable(), false); await onlyV2.preview(); assert.equal(onlyPreviews.length, 0);
  await w.preview(); assert.equal(previews.length, 1);
});
test('unresolved v2 write retains original identity across attempted renderer changes', async () => {
  const {workflow: w, previews, sent, queried, setReceipt} = await setup({}, manualContext(), capability(['direct-v1', 'cohort-fft-v2']));
  assert.equal(w.selectRenderer('cohort-fft-v2'), true); w.acknowledgeRenderer(true);
  await w.preview(); showBoth(w); w.acknowledge(true); await w.apply();
  assert.equal(sent.length, 1); assert.equal(w.snapshot().phase, 'pending');
  const original = structuredClone(w.snapshot().request), recipe = structuredClone(w.snapshot().recipe);
  assert.equal(w.selectRenderer('direct-v1'), false); w.acknowledgeRenderer(false);
  w.setCapability(capability(['direct-v1']));
  assert.deepEqual(w.snapshot().request, original); assert.deepEqual(w.snapshot().recipe, recipe);
  await w.preview(); await w.apply(); await w.cancel(); assert.equal(previews.length, 1); assert.equal(sent.length, 1);
  setReceipt(applied(sent[0])); await w.check(); assert.equal(queried.length, 1);
  assert.deepEqual(queried[0], original); assert.equal(w.snapshot().phase, 'applied');
});
test('cancel requires its matching terminal receipt, not a successful transport return', async () => {
  const {workflow: w, sent, setReceipt} = await setup();
  await w.cancel(); assert.equal(w.snapshot().phase, 'pending'); assert.equal(sent.length, 1);
  const c = sent[0]; setReceipt({...identity(c), phase: 'done', outcome_unknown: false, outcome: 'cancelled'});
  await w.check(); assert.equal(w.snapshot().phase, 'cancelled'); assert.equal(w.snapshot().request, null);
});
test('manual plane requires the explicit preparation method and is not AI or measured depth', async () => {
  const {workflow: w, port, sent} = await setup();
  let preparations = 0;
  port.prepareManualPlane = async command => {
    assert.equal(command.version, LENS_PROTOCOL); assert.equal(command.acknowledged_manual, true);
    preparations++;
    const c = context(), raster = Buffer.from([0,128,0,128,0,128,0,128]);
    c.depth!.provenance = {kind: 'manual', method: 'user_defined_plane', depth_value: command.depth_value, acknowledgement_id: command.request_id};
    c.depth!.raster = {format: 'u16-le', width: 2, height: 2, sha256: sha(raster), base64: raster.toString('base64')};
    return c;
  };
  const missing = {...context(), depth: null, depth_status: 'missing-model' as const};
  await w.setContext(missing); w.sourcePresented(missing.source_image.sha256, 2, 2, true);
  assert.equal(preparations, 0); assert.equal(w.snapshot().depth, null);
  await w.prepareManualPlane(); assert.equal(preparations, 1); assert.equal(sent.length, 0);
  assert.equal(w.snapshot().depth?.asset.provenance.kind, 'manual');
  assert.equal(w.snapshot().depth?.asset.subject_focus, null);
  assert.equal(w.snapshot().depth?.values.every(value => value === 32768), true);
});

test('session cancel does not depend on the expiring preview-image token', async () => {
  const {workflow: w, sent} = await setup();
  await w.preview(); assert.ok(w.snapshot().review);
  await w.cancel(); assert.equal(sent.length, 1);
  assert.equal(sent[0].action, 'cancel'); assert.equal(sent[0].token, null);
  assert.equal(sent[0].session_id, context().session_id);
});
