// AUTHORED / UNRUN. Importing this suite also registers its shared model fixtures.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createSkinReferenceReviewGuard} from './reviewGuard.ts';
import {ack} from './model.ts';
import {createPeopleWorkflow} from '../people/workflow.ts';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {catalog, command, confirmation, image, preview, result, review, view} from './model.unrun.test.ts';

async function load(guard: ReturnType<typeof createSkinReferenceReviewGuard>, v: PeopleView, withImages = true) {
  const c = command('skin_reference_match_catalog', {}); c.request_id = 'catalog';
  guard.prepare(c, v); await guard.validate(c, result(c, catalog(v)), () => v); guard.complete(c);
  const p = command(); p.request_id = 'preview';
  guard.prepare(p, v); await guard.validate(p, result(p, {kind: p.action, review: review(v)}), () => v); guard.complete(p);
  if (withImages) for (const side of ['before', 'after'] as const) {
    const r = review(v), page = command('skin_reference_match_image', {token: r.token, side, sha256: r.visual[side].sha256, review_sha256: r.review_sha256});
    page.request_id = side;
    guard.prepare(page, v); await guard.validate(page, result(page, {kind: page.action, ...page.payload, image: image()}), () => v); guard.complete(page);
  }
}
test('guard requires actual catalog before preview and both exact image pages before confirm', async () => {
  const guard = createSkinReferenceReviewGuard(), v = view(), r = review(v);
  assert.throws(() => guard.prepare(command(), v));
  await load(guard, v, false);
  assert.throws(() => guard.prepare(command('skin_reference_match_confirm', {token: r.token, ack: ack(r)}), v));
  await load(guard, v);
  assert.doesNotThrow(() => guard.prepare(command('skin_reference_match_confirm', {token: r.token, ack: ack(r)}), v));
});
test('cursor-independent proof survives cursor movement but not a changed source/analysis fence', async () => {
  const guard = createSkinReferenceReviewGuard(), v = view(); await load(guard, v);
  const cursor = {...v, selected_face_id: v.faces[1].face_ref.face_instance_id,
    editing_target: {scope: 'face' as const, target_id: v.faces[1].face_ref.face_instance_id, face_ref: v.faces[1].face_ref}};
  guard.update(cursor); const r = review(v);
  assert.doesNotThrow(() => guard.prepare(command('skin_reference_match_confirm', {token: r.token, ack: ack(r)}), cursor));
  guard.update({...cursor, revision: v.revision + 1});
  assert.throws(() => guard.prepare(command('skin_reference_match_confirm', {token: r.token, ack: ack(r)}), cursor));
});
test('read payload cannot publish a document/frame and failed writes cannot claim a result', async () => {
  const guard = createSkinReferenceReviewGuard(), v = view(), c = command('skin_reference_match_catalog', {});
  guard.prepare(c, v);
  await assert.rejects(guard.validate(c, {...result(c, catalog(v)), doc_state: {people: v}}, () => v));
  await assert.rejects(guard.validate(c, {...result(c, catalog(v)), frame: {}} as PeopleResult, () => v));
  await assert.rejects(guard.validate(c, {...result(c, catalog(v)), success: false}, () => v));
});
test('an exact released read is terminal but cannot become a source/preview authority', async () => {
  const guard = createSkinReferenceReviewGuard(), v = view(), c = command('skin_reference_match_catalog', {});
  guard.prepare(c, v); await guard.validate(c, {...result(c), payload_released: true}, () => v); guard.complete(c);
  assert.throws(() => guard.prepare(command(), v));
});
test('confirmed write raises a same-document refresh fence until actual status reaches its revisions', async () => {
  const guard = createSkinReferenceReviewGuard(), v = view(); await load(guard, v);
  const {c, receipt} = confirmation(); guard.prepare(c, v); await guard.validate(c, receipt, () => v); guard.complete(c);
  assert.equal(guard.needsRefresh(v), true);
  assert.throws(() => guard.prepare(command('skin_reference_match_clear', {}), v));
  guard.update(receipt.doc_state.people); assert.equal(guard.needsRefresh(receipt.doc_state.people), false);
});
test('people owner handles read-only catalog without refresh or mutating the selected cursor', async () => {
  const v = view(); let sent: PeopleAction | null = null, refreshed = 0;
  const owner = createPeopleWorkflow({send: async c => {sent = c;}, read: async id => ({phase: 'done', request_id: id,
    result: result(sent!, catalog(v))}), refresh: async () => {refreshed++;}});
  owner.update(v, true); const c = command('skin_reference_match_catalog', {}); await owner.submit(c);
  assert.equal(refreshed, 0); assert.equal(owner.snapshot().pending, false);
  assert.equal(owner.snapshot().lastSkinReferenceResult?.result.request_id, c.request_id);
  assert.equal(v.selected_face_id, null); assert.equal(v.editing_target, null);
});
test('people owner retains malformed/unknown original request and later query never resends it', async () => {
  const v = view(); let sent = 0, captured: PeopleAction | null = null, correct = false;
  const owner = createPeopleWorkflow({send: async c => {captured = c; sent++;}, read: async id => ({phase: 'done', request_id: id,
    result: correct ? result(captured!, catalog(v)) : {...result(captured!, catalog(v)), skin_reference_match_request: undefined}}), refresh: async () => {}});
  owner.update(v, true); const c = command('skin_reference_match_catalog', {});
  await assert.rejects(owner.submit(c)); assert.equal(owner.snapshot().uncertain, true); assert.equal(owner.snapshot().pending, true);
  await assert.rejects(owner.submit({...c, request_id: 'replacement'})); assert.equal(sent, 1);
  correct = true; await owner.check(); assert.equal(sent, 1); assert.equal(owner.snapshot().uncertain, false);
  assert.equal(owner.snapshot().lastSkinReferenceResult?.command.request_id, c.request_id);
});
test('late old-document reads are validated against their capture then discarded, not made into new-photo uncertainty', async () => {
  const first = view(), next = {...view(), binding: {...view().binding, document_id: 'e'.repeat(32)}};
  let captured: PeopleAction | null = null, answer: ((value: unknown) => void) | null = null;
  const wait = new Promise<unknown>(resolve => {answer = resolve;});
  const owner = createPeopleWorkflow({send: async c => {captured = c;}, read: async id => {
    await wait; return {phase: 'done', request_id: id, result: result(captured!, catalog(first))};
  }, refresh: async () => {}});
  owner.update(first, true); const pending = owner.submit(command('skin_reference_match_catalog', {}));
  owner.update(next, true); answer!(undefined); await pending;
  assert.equal(owner.snapshot().lastSkinReferenceResult, null); assert.equal(owner.snapshot().uncertain, false);
});
