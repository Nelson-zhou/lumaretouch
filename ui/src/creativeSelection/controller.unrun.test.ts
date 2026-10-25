// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: production imports and these fixtures were not run, built or typechecked here.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import {CreativeSelectionController} from './controller.ts';
import {SELECTION_PROTOCOL, type CreativeSelectionPort, type SelectionApplyRequest, type SelectionContextRequest,
  type SelectionPng, type SelectionProof, type SelectionReply, type SelectionRequest, type SelectionReview} from './model.ts';

// Synthetic fixture PNGs are created only when a future verifier explicitly runs this file.
function png(rgb: [number, number, number]): SelectionPng {
  const crc = (bytes: Buffer) => {let value = 0xffffffff; for (const byte of bytes) {value ^= byte; for (let i = 0; i < 8; i++) value = (value >>> 1) ^ ((value & 1) ? 0xedb88320 : 0);} return (value ^ 0xffffffff) >>> 0;};
  const chunk = (kind: string, data: Buffer) => {const body = Buffer.concat([Buffer.from(kind), data]), head = Buffer.alloc(4), tail = Buffer.alloc(4); head.writeUInt32BE(data.length); tail.writeUInt32BE(crc(body)); return Buffer.concat([head, body, tail]);};
  const header = Buffer.alloc(13); header.writeUInt32BE(1, 0); header.writeUInt32BE(1, 4); header[8] = 8; header[9] = 2;
  const bytes = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', deflateSync(Buffer.from([0, ...rgb]))), chunk('IEND', Buffer.alloc(0))]);
  return {mime: 'image/png', width: 1, height: 1, sha256: createHash('sha256').update(bytes).digest('hex'), base64: bytes.toString('base64')};
}
const hash = 'a'.repeat(64), maskHash = 'b'.repeat(64);
const proof: SelectionProof = {document_id: 'doc', source_uid: 'source', ownership_token: 'owner', expected_revision: 3, layer_id: 'leaf',
  asset_id: 'actual-source-asset', source_sha256: hash, document_sha256: hash, transform_sha256: hash,
  existing_mask_id: null, existing_mask_sha256: null, canvas: {width: 100, height: 100}, source: {width: 100, height: 100}};
const binding = {document_id: proof.document_id, source_uid: proof.source_uid, ownership_token: proof.ownership_token, expected_revision: 3, layer_id: proof.layer_id};
const workspace = {scope: 'engine:load-1', binding, active: true, available: true, busy: false};
const event = (request: SelectionRequest, fields: Partial<SelectionReply>): SelectionReply => ({event: 'creative_selection_result', request_id: request.request_id, source_uid: request.source_uid, status: 'ready', ...fields});
const deferred = <T,>() => {let resolve!: (value: T) => void; const promise = new Promise<T>(done => {resolve = done;}); return {promise, resolve};};
function harness(extra: Partial<CreativeSelectionPort> = {}, existing = false) {
  const image = png([255, 255, 255]), after = png([30, 30, 30]); let id = 0, refreshed = 0;
  const ownProof = {...proof, existing_mask_id: existing ? 'old-mask' : null, existing_mask_sha256: existing ? hash : null};
  const port: CreativeSelectionPort = {protocol: SELECTION_PROTOCOL,
    context: async request => event(request, {context: {proof: ownProof, canvas_image: image, existing_mask_image: existing ? image : null}}),
    preview: async request => event(request, {review: {proof: request.proof, preview_token: 'preview', recipe: request.recipe,
      recipe_sha256: hash, mask_policy: request.mask_policy, output_mask_id: 'immutable-mask', output_mask_sha256: maskHash,
      before_composite: image, after_composite: after, before_mask: image, after_mask: after, ack: 'exact-host-ack'}}),
    apply: async request => event(request, {status: 'applied', proof: request.proof, preview_token: request.preview_token,
      revision: 4, mask_id: 'immutable-mask', mask_sha256: maskHash}),
    cancel: async request => event(request, {status: 'cancelled', target_request_id: request.target_request_id}), ...extra};
  const controller = new CreativeSelectionController(port, workspace, {requestId: () => `request-${++id}`, onApplied: () => {refreshed++;}});
  return {controller, port, image, get refreshed() {return refreshed;}};
}
async function ready(h: ReturnType<typeof harness>) {await h.controller.acquire(); h.controller.sourcePresented(h.image.sha256, 1, 1, true);}
async function review(h: ReturnType<typeof harness>) {
  h.controller.append({kind: 'rectangle', combine: 'new', x0: 5, y0: 5, x1: 50, y1: 50}); await h.controller.preview();
  const value = h.controller.snapshot().review as SelectionReview;
  for (const role of ['before_composite', 'after_composite', 'before_mask', 'after_mask'] as const) h.controller.presented(role, value.preview_token, 1, 1, true);
  h.controller.acknowledge(true);
}
test('draft undo/redo and deselect never call canonical apply', async () => {
  let writes = 0; const h = harness({apply: async request => {writes++; return event(request, {status: 'rejected'});}}); await ready(h);
  assert.equal(h.controller.append({kind: 'invert'}), true); assert.equal(h.controller.undo(), true);
  assert.equal(h.controller.snapshot().recipe?.operations.length, 0); assert.equal(h.controller.redo(), true);
  h.controller.deselect(); assert.equal(h.controller.canPreview(), false); assert.equal(writes, 0);
});
test('existing mask requires explicit combination and a correct real-image review before apply', async () => {
  const h = harness({}, true); await ready(h); h.controller.append({kind: 'invert'});
  assert.equal(h.controller.snapshot().mask_policy, null); assert.equal(h.controller.canPreview(), false);
  h.controller.policy('replace'); await review(h); assert.equal(h.controller.canApply(), true);
  h.controller.presented('after_mask', 'preview', 0, 0, false); assert.equal(h.controller.canApply(), false);
  h.controller.presented('after_mask', 'preview', 1, 1, true); h.controller.acknowledge(true);
  await h.controller.apply(); assert.equal(h.refreshed, 1); assert.equal(h.controller.snapshot().receipt?.mask_id, 'immutable-mask');
});
test('pending apply survives source change and is queried by original identity without replay', async () => {
  const wait = deferred<SelectionReply>(); let original!: SelectionApplyRequest, writes = 0;
  const h = harness({apply: request => {original = request; writes++; return wait.promise;}}); await ready(h); await review(h);
  const work = h.controller.apply(); h.controller.updateContext({...workspace, scope: 'engine:load-2', binding: {...binding, source_uid: 'other'}});
  await h.controller.apply(); assert.equal(writes, 1); assert.equal(h.controller.snapshot().request?.request_id, original.request_id);
  wait.resolve(event(original, {status: 'applied', proof: original.proof, preview_token: original.preview_token, revision: 4, mask_id: 'immutable-mask', mask_sha256: maskHash}));
  await work; assert.equal(h.refreshed, 1); assert.equal(h.controller.snapshot().stale, true);
});
test('pointer-cancellation contract: uncommitted paths never enter vector history', async () => {
  const h = harness(); await ready(h); const count = h.controller.snapshot().recipe?.operations.length;
  h.controller.notice('Pointer was cancelled before the view called append');
  assert.equal(h.controller.snapshot().recipe?.operations.length, count); assert.equal(h.controller.snapshot().undo.length, 0);
  // Actual pointer capture/blur/lost-capture DOM interaction still requires the separate UI checklist.
});
test('read cancellation names the original request and cannot invent an apply rollback', async () => {
  const wait = deferred<SelectionReply>(); let original!: SelectionContextRequest, target = '';
  const h = harness({context: request => {original = request; return wait.promise;}, cancel: async request => {target = request.target_request_id; return event(request, {status: 'cancelled', target_request_id: target});}});
  const work = h.controller.acquire(); await Promise.resolve(); await h.controller.cancel(); assert.equal(target, original.request_id);
  wait.resolve(event(original, {status: 'cancelled'})); await work; assert.equal(h.controller.snapshot().phase, 'cancelled');
});
test('only a native explicit project-reopen marker permits user dismissal; old write outcome stays unknown', async () => {
  let reopened = false;
  const h = harness({apply: async request => event(request, {status: 'unknown'}),
    receipt: async request => event(request, {status: 'unknown', workspace_reopened: reopened})});
  await ready(h); await review(h); await h.controller.apply();
  const original = h.controller.snapshot().request;
  assert.equal(h.controller.canDismissRetiredWorkspace(), false); h.controller.dismissRetiredWorkspace();
  assert.equal(h.controller.snapshot().request, original);
  reopened = true; await h.controller.check(); assert.equal(h.controller.canDismissRetiredWorkspace(), true);
  h.controller.dismissRetiredWorkspace(); assert.equal(h.controller.snapshot().request, null);
  assert.equal(h.controller.snapshot().retired_request, original); assert.equal(h.controller.snapshot().retired_receipt?.status, 'unknown');
  assert.equal(h.refreshed, 0); assert.equal(h.controller.snapshot().context, null);
  await h.controller.acquire(); assert.equal(h.controller.snapshot().retired_request, original);
  assert.equal(h.controller.snapshot().retired_receipt?.status, 'unknown');
});
