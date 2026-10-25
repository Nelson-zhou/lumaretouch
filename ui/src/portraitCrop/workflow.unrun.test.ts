// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Synthetic protocol fixtures, not real-image or runtime acceptance.
import assert from 'node:assert/strict';
import test from 'node:test';
import {PortraitCropController} from './controller.ts';
import {checkedAnchors, checkedCurrent, checkedPreview, checkedReceipt, checkedRules, checkedWorkspaceReopened, imageKey,
  type Current, type ImageProof, type Preview, type Receipt, type Request, type Transport} from './model.ts';
const hash = (letter: string) => letter.repeat(64);
// Deliberately not photographic evidence. No production code imports this fixture.
const fakePng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==';
const image = (width: number, height: number): ImageProof => ({mime: 'image/png', width: 1, height: 1, sha256: hash('a'), base64: fakePng, source_width: width, source_height: height, mapping: 'normalized_full_frame'});
function current(): Current {
  return {session_id: 'session-A', capture_sha256: hash('b'),
    binding: {document_id: 'document-A', revision: '7', document_epoch: 'workspace-A', load_id: 'load-A',
      original_sha256: hash('c'), source_proof: {asset_sha256: hash('c'), original_sha256: hash('c'), creative_source: null},
      state_sha256: hash('d'), non_crop_sha256: hash('e'), people_sha256: hash('f'), repair_sha256: hash('0'), uncropped_sha256: hash('1')},
    source: {width: 1000, height: 1000, orientation: 'exif_normalized_once', mapping: 'source_edge_pixels', source_sha256: hash('1'),
      analysis_sha256: hash('2'), model_sha256: hash('3'), semantic_model_sha256: hash('4'), proxy_sha256: hash('5'), proxy_size: [1, 1], inference: 'fresh_whole_frame_display_proxy', image: image(1000, 1000),
      faces: [{face_id: 'face-A', landmarks_sha256: hash('6'), bbox: [400, 250, 600, 500], chin_proposal: [500, 500], center_proposal: [500, 350]}]}, before: image(1000, 1000)};
}
function preview(request: Request): Preview {
  const requested = {aspect_ratio: 1, headroom_fraction: .1, head_fraction: .5, horizontal_position: .5, vertical_position: .35};
  return {preview_token: 'preview-A', capture_sha256: hash('b'), candidate_sha256: hash('7'), preview_request_id: request.request_id,
    before: image(1000, 1000), after: image(600, 600), plan: {version: 1, convention: 'lrt.portrait-crop.source-edge-pixels.v1', operation_id: 'lnx.crop.v1', rotation_degrees: 0,
      source_size: [1000, 1000], anchors: structuredClone(request.anchors) as Preview['plan']['anchors'], rules: structuredClone(request.rules) as Preview['plan']['rules'],
      continuous_rect_pixels: [200, 140, 800, 740], pixel_bounds: [200, 140, 800, 740], rect_normalized: [.2, .14, .8, .74], output_size: [600, 600],
      requested, achieved: {...requested, head_height_pixels: 300}, is_full_frame: false, backend: 'rust-portrait-crop-v1'}};
}
function receipt(request: Request, phase: Receipt['phase'], extra: Partial<Receipt> = {}): Receipt {
  return {event: 'portrait_crop_result', version: 1, request_id: request.request_id, action: request.action,
    command_sha256: hash('8'), original_request: structuredClone(request), phase, ...extra};
}
function harness(apply: (request: Request) => Promise<unknown> = async request => receipt(request, 'committed', {
  original_request_id: request.request_id, result: {status: 'applied', document_id: 'document-A', revision: '8'},
  preview_token: 'preview-A', candidate_sha256: hash('7')})) {
  const sent: Request[] = [], queried: Request[] = [];
  let statusReply: unknown;
  const transport: Transport = {
    async send(request) {
      sent.push(structuredClone(request));
      if (request.action === 'current') return receipt(request, 'current_ready', {current: current()});
      if (request.action === 'preview') return receipt(request, 'ready', {preview: preview(request)});
      if (request.action === 'cancel') return receipt(request, 'cancelled', {no_write: true});
      return apply(request);
    },
    async status(request) {queried.push(structuredClone(request)); return statusReply;},
  };
  const controller = new PortraitCropController(transport);
  controller.setContext('exact-document-A-source-edit-repair-analysis-v7'); controller.setEnabled(true);
  return {controller, sent, queried, setStatus(value: unknown) {statusReply = value;}};
}
async function prepare(h: ReturnType<typeof harness>) {
  const c = h.controller;
  await c.acquire();
  const captured = c.snapshot().current!;
  c.sourceImageReady(`${captured.session_id}:${imageKey(captured.source.image)}`, true);
  c.selectFace('face-A'); c.useFaceProposal(); c.mark('crown', [500, 200]);
  c.confirmAnchor('crown', true); c.confirmAnchor('chin', true); c.confirmAnchor('face_center', true);
  c.setRules({aspect_ratio: '1', headroom_fraction: '.1', head_fraction: '.5', horizontal_position: '.5'});
  await c.prepare();
}
function review(c: PortraitCropController) {
  const p = c.snapshot().preview!;
  c.previewImageReady(p.preview_token, 'before', imageKey(p.before), true);
  c.previewImageReady(p.preview_token, 'after', imageKey(p.after), true);
  c.confirmReview(true);
}
test('UNRUN: blank, nonfinite, contradictory and out-of-range local rules reject', () => {
  const valid = {aspect_ratio: '1', headroom_fraction: '.1', head_fraction: '.5', horizontal_position: '.5'};
  for (const patch of [{aspect_ratio: ''}, {aspect_ratio: 'NaN'}, {aspect_ratio: '0x1'}, {head_fraction: '0'}, {headroom_fraction: '.7'}, {horizontal_position: '1.1'}]) assert.throws(() => checkedRules({...valid, ...patch}));
  assert.throws(() => checkedAnchors({crown: [500, 501], chin: [500, 500], face_center: [500, 350]}, 1000, 1000));
});
test('UNRUN: detector selection proposes neither crown nor any confirmed anchor', async () => {
  const h = harness(); await h.controller.acquire();
  assert.equal(h.controller.snapshot().selectedFace, null);
  h.controller.selectFace('face-A');
  assert.deepEqual(h.controller.snapshot().anchors, {});
  await assert.rejects(h.controller.prepare());
  assert.equal(h.sent.length, 1);
});
test('UNRUN: stale/original source analysis and mismatched grid are rejected', () => {
  const stale = current(); (stale.source as unknown as Record<string, unknown>).inference = 'original_precompute';
  assert.throws(() => checkedCurrent(stale));
  const wrong = current(); wrong.source.source_sha256 = hash('9'); assert.throws(() => checkedCurrent(wrong));
});
test('UNRUN: actual candidate required; both full images and explicit review precede apply', async () => {
  const h = harness(); await prepare(h);
  await assert.rejects(h.controller.apply());
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 0);
  const p = h.controller.snapshot().preview!;
  h.controller.previewImageReady(p.preview_token, 'before', imageKey(p.before), true);
  assert.throws(() => h.controller.confirmReview(true));
  review(h.controller); await h.controller.apply();
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
  assert.equal(h.controller.snapshot().phase, 'idle');
  assert.equal(h.controller.snapshot().preview, null);
});
test('UNRUN: request echoes, image identity, rotation and achieved ratios must match', async () => {
  const h = harness(); await prepare(h);
  const request = h.sent.find(r => r.action === 'preview')!, captured = h.controller.snapshot().current!;
  const good = preview(request); checkedPreview(good, captured, request);
  const changed = structuredClone(good); changed.plan.achieved.head_fraction = .6;
  assert.throws(() => checkedPreview(changed, captured, request));
  const rotated = structuredClone(good); (rotated.plan as unknown as Record<string, unknown>).rotation_degrees = 1;
  assert.throws(() => checkedPreview(rotated, captured, request));
  const wrong = receipt(request, 'ready', {preview: good}); wrong.original_request = {...request, face_id: 'face-B'};
  assert.throws(() => checkedReceipt(wrong, request, null));
});
test('UNRUN: anchor or rule changes revoke a ready candidate and explicit review', async () => {
  const h = harness(); await prepare(h); review(h.controller);
  h.controller.mark('crown', [501, 200]);
  assert.equal(h.controller.snapshot().preview, null);
  assert.equal(h.controller.snapshot().reviewConfirmed, false);
  assert.ok(Object.values(h.controller.snapshot().confirmations).every(v => !v));
});
test('UNRUN: unknown apply survives closure and photo switch; status never resends', async () => {
  const h = harness(async request => receipt(request, 'unknown', {outcome_unknown: true, original_request_id: request.request_id}));
  await prepare(h); review(h.controller); await h.controller.apply();
  const original = h.sent.find(r => r.action === 'apply')!;
  h.controller.dismiss(); h.controller.setContext('document-B-exact-revision');
  await assert.rejects(h.controller.acquire());
  h.setStatus(receipt(original, 'committed', {original_request_id: original.request_id, preview_token: 'preview-A', candidate_sha256: hash('7'), result: {status: 'applied', document_id: 'document-A', revision: '8'}}));
  await h.controller.reconcile();
  assert.equal(h.controller.snapshot().phase, 'idle');
  assert.equal(h.controller.snapshot().current, null);
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
  assert.deepEqual(h.queried[0], original);
});
test('UNRUN: missing/mismatched status remains fenced and does not prove no write', async () => {
  const h = harness(async () => {throw Error('lost reply');}); await prepare(h); review(h.controller); await h.controller.apply();
  h.setStatus(null); await h.controller.reconcile(); assert.equal(h.controller.snapshot().phase, 'uncertain');
  await assert.rejects(h.controller.apply());
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
});
test('UNRUN: explicit cancel before apply makes no crop mutation', async () => {
  const h = harness(); await prepare(h); review(h.controller); await h.controller.cancel();
  assert.equal(h.controller.snapshot().preview, null);
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 0);
});
test('UNRUN: a late source result after dismissal cannot restore measurements', async () => {
  let resolve!: (value: unknown) => void, request!: Request;
  const c = new PortraitCropController({send: r => {request = r; return new Promise(r => {resolve = r;});}, status: async () => null});
  c.setContext('document-A-exact'); c.setEnabled(true);
  const pending = c.acquire(); c.dismiss();
  resolve(receipt(request, 'current_ready', {current: current()})); await pending;
  assert.equal(c.snapshot().current, null);
  assert.equal(c.snapshot().preview, null);
});
test('UNRUN: double apply cannot enqueue a second mutation while first is unresolved', async () => {
  let complete!: (value: unknown) => void;
  const h = harness(() => new Promise(resolve => {complete = resolve;}));
  await prepare(h); review(h.controller);
  const applying = h.controller.apply();
  await assert.rejects(h.controller.apply());
  const original = h.sent.find(r => r.action === 'apply')!;
  complete(receipt(original, 'committed', {original_request_id: original.request_id, preview_token: 'preview-A', candidate_sha256: hash('7'), result: {status: 'applied', document_id: 'document-A', revision: '8'}}));
  await applying;
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
});
test('UNRUN: a changed pinned host digest cannot settle an unknown original write', async () => {
  const h = harness(async request => receipt(request, 'unknown', {outcome_unknown: true, original_request_id: request.request_id}));
  await prepare(h); review(h.controller); await h.controller.apply();
  const original = h.sent.find(r => r.action === 'apply')!;
  h.setStatus(receipt(original, 'committed', {command_sha256: hash('9'), original_request_id: original.request_id, preview_token: 'preview-A', candidate_sha256: hash('7'), result: {status: 'applied', document_id: 'document-A', revision: '8'}}));
  await h.controller.reconcile();
  assert.equal(h.controller.snapshot().phase, 'uncertain');
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
});

function reopened(original: Request) {
  return {workspace_reopened: true, authority: 'native_verified_project_reopen_v1', original_request: structuredClone(original), outcome_unknown: true,
    authoritative_event: {event: 'project_opened', open: true, path: '/synthetic/fixture/project.lrt', project_id: 'project-B', docs: 1, dirty: false},
    message: 'Synthetic UNRUN authoritative-reopen protocol fixture, not an actual project event.'};
}
test('UNRUN: only exact native-authority reopen evidence retires old unknown lock', async () => {
  const h = harness(async request => receipt(request, 'unknown', {outcome_unknown: true, original_request_id: request.request_id}));
  await prepare(h); review(h.controller); await h.controller.apply();
  const original = h.sent.find(r => r.action === 'apply')!;
  h.controller.setContext('new-context-is-not-reopen-proof');
  assert.equal(h.controller.snapshot().phase, 'uncertain');
  h.setStatus(reopened(original)); await h.controller.reconcile();
  assert.equal(h.controller.snapshot().phase, 'idle');
  assert.equal(h.controller.snapshot().pending, null);
  assert.equal(h.controller.snapshot().current, null);
  assert.equal(h.controller.snapshot().historicalUnknown?.request_id, original.request_id);
  assert.match(h.controller.snapshot().message, /历史结果仍未知/);
  assert.equal(h.sent.filter(r => r.action === 'apply').length, 1);
});
test('UNRUN: reopen marker alone, failed project event or changed original cannot unlock', async () => {
  const h = harness(async request => receipt(request, 'unknown', {outcome_unknown: true, original_request_id: request.request_id}));
  await prepare(h); review(h.controller); await h.controller.apply();
  const original = h.sent.find(r => r.action === 'apply')!;
  const valid = reopened(original);
  for (const bad of [
    {workspace_reopened: true, original_request: original},
    {...valid, authority: 'unverified'},
    {...valid, authoritative_event: {...valid.authoritative_event, error: 'reload failed'}},
    {...valid, original_request: {...original, candidate_sha256: hash('9')}},
    {...valid, phase: 'rejected', no_write: true},
  ]) {
    assert.throws(() => checkedWorkspaceReopened(bad, original));
    h.setStatus(bad); await h.controller.reconcile();
    assert.equal(h.controller.snapshot().phase, 'uncertain');
    assert.equal(h.controller.snapshot().historicalUnknown, null);
  }
});
test('UNRUN: unknown current-source request also retires only on verified reopen evidence', async () => {
  let original!: Request, result: unknown;
  const c = new PortraitCropController({send: async request => {original = request; throw Error('original read receipt lost');}, status: async () => result});
  c.setContext('document-A-exact'); c.setEnabled(true); await c.acquire();
  assert.equal(c.snapshot().pending?.action, 'current');
  assert.equal(c.snapshot().phase, 'uncertain');
  c.setContext('context-only-change');
  assert.equal(c.snapshot().pending?.action, 'current');
  result = reopened(original); await c.reconcile();
  assert.equal(c.snapshot().pending, null);
  assert.equal(c.snapshot().historicalUnknown?.action, 'current');
  assert.match(c.snapshot().message, /不是裁剪应用请求/);
  assert.doesNotMatch(c.snapshot().message, /已应用/);
});
