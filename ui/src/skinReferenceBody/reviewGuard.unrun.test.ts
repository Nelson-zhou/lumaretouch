// AUTHORED / UNRUN. These fixtures are not runtime or visual acceptance evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleAction, PeopleResult} from '../people/model.ts';
import {createPeopleWorkflow} from '../people/workflow.ts';
import {createSkinReferenceBodyReviewGuard} from './reviewGuard.ts';
import {ack} from './model.ts';
import {catalog, command, confirmation, image, preview, result, review, view} from './model.unrun.test.ts';

async function freeze() {
  const guard = createSkinReferenceBodyReviewGuard(), v = view(); guard.update(v);
  const catalogCommand = command('skin_reference_body_catalog', {});
  guard.prepare(catalogCommand, v); await guard.validate(catalogCommand, result(catalogCommand, catalog()), () => v); guard.complete(catalogCommand);
  const c = command(), r = review(); guard.prepare(c, v);
  await guard.validate(c, result(c, {kind: 'skin_reference_body_preview', review: r}), () => v); guard.complete(c);
  return {guard, v, r};
}
async function serve(frozen: Awaited<ReturnType<typeof freeze>>, side: 'before' | 'after') {
  const {guard, v, r} = frozen;
  const c = command('skin_reference_body_image', {token: r.token, side, sha256: r.visual[side].sha256, review_sha256: r.review_sha256});
  guard.prepare(c, v); await guard.validate(c, result(c, {kind: c.action, ...c.payload, image: image()}), () => v); guard.complete(c);
}
test('admission requires this operation catalog, body selection and own consent before freezing', async () => {
  const guard = createSkinReferenceBodyReviewGuard(), v = view(); guard.update(v);
  assert.throws(() => guard.prepare(command(), v));
  const c = command('skin_reference_body_catalog', {}); guard.prepare(c, v);
  await assert.rejects(() => guard.validate(c, {...result(c, catalog()), skin_reference_body_request: undefined}, () => v));
  await guard.validate(c, result(c, catalog()), () => v); guard.complete(c);
  assert.throws(() => guard.prepare(command('skin_reference_body_preview', {...preview(), review: {...preview().review, operation_id: 'lnx.body_face_match.v1'}}), v));
});
test('both exact image pages are required and source/association change invalidates frozen admission', async () => {
  const frozen = await freeze(), commit = command('skin_reference_body_confirm', {token: frozen.r.token, ack: ack(frozen.r)});
  assert.throws(() => frozen.guard.prepare(commit, frozen.v));
  await serve(frozen, 'before'); assert.throws(() => frozen.guard.prepare(commit, frozen.v));
  await serve(frozen, 'after'); assert.doesNotThrow(() => frozen.guard.prepare(commit, frozen.v));
  frozen.guard.complete(commit);
  const next = {...frozen.v, association_revision: frozen.v.association_revision + 1}; frozen.guard.update(next);
  assert.throws(() => frozen.guard.prepare({...commit, association_revision: next.association_revision}, next));
});
test('read replies cannot publish frames/documents and released mutation results cannot erase proof', async () => {
  const guard = createSkinReferenceBodyReviewGuard(), v = view(), c = command('skin_reference_body_catalog', {}); guard.update(v); guard.prepare(c, v);
  await assert.rejects(() => guard.validate(c, {...result(c, catalog()), doc_state: {people: v}}, () => v));
  await assert.rejects(() => guard.validate(c, {...result(c, catalog()), frame: {}} as PeopleResult, () => v));
  const frozen = await freeze(); await serve(frozen, 'before'); await serve(frozen, 'after');
  const commit = confirmation(); frozen.guard.prepare(commit.c, frozen.v);
  await assert.rejects(() => frozen.guard.validate(commit.c, {...commit.receipt, payload: undefined, payload_released: true}, () => frozen.v));
});
test('successful mutation holds canonical owner until real readback; refresh does not replay a write', async () => {
  const frozen = await freeze(); await serve(frozen, 'before'); await serve(frozen, 'after');
  const commit = confirmation(); frozen.guard.prepare(commit.c, frozen.v);
  await frozen.guard.validate(commit.c, commit.receipt, () => frozen.v); frozen.guard.complete(commit.c);
  assert.equal(frozen.guard.needsRefresh(frozen.v), true);
  assert.throws(() => frozen.guard.prepare(command('skin_reference_body_clear', {}), frozen.v));
  frozen.guard.update(commit.receipt.doc_state.people);
  assert.equal(frozen.guard.needsRefresh(commit.receipt.doc_state.people), false);
});
test('canonical PeopleOwner classifies body read without refresh and requires original uncertain request, not resend', async () => {
  let sent: PeopleAction | null = null, sends = 0, refreshes = 0;
  const workflow = createPeopleWorkflow({send: async c => {sent = c; sends++;},
    read: async request_id => ({phase: 'done', request_id, result: result(sent!, catalog())}),
    refresh: async () => {refreshes++;}});
  workflow.update(view(), true); await workflow.submit(command('skin_reference_body_catalog', {}));
  assert.equal(sends, 1); assert.equal(refreshes, 0);
  assert.equal(workflow.snapshot().lastSkinReferenceBodyResult?.command.action, 'skin_reference_body_catalog');
  assert.equal(workflow.snapshot().lastSkinReferenceResult, null);

  const unknown = createPeopleWorkflow({send: async () => {sends++;}, read: async request_id => ({phase: 'unavailable', request_id}), refresh: async () => {refreshes++;}});
  unknown.update(view(), true); const original = command('skin_reference_body_catalog', {});
  await assert.rejects(() => unknown.submit(original)); assert.equal(unknown.snapshot().uncertain, true);
  const before = sends; await assert.rejects(() => unknown.submit({...original, request_id: 'replacement'}));
  assert.equal(sends, before); await assert.rejects(() => unknown.check()); assert.equal(sends, before);
});
