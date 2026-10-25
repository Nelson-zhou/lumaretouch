// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These fixtures specify future guard execution only.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleResult} from '../people/model.ts';
import {createSkinReferenceChoiceGuard} from './reviewGuard.ts';
import {catalogReceipt, fixture, hash, result} from './fixtures.unrun.test.ts';

const asPeople = (value: unknown) => value as PeopleResult;
test('no catalog, no measurement; full verified original PNG then same-owner request is admitted', async () => {
  const f = fixture(), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
  assert.throws(() => g.prepare(f.command, f.context.view));
  g.prepare(c.command, f.context.view); await g.validate(c.command, c.result, () => f.context.view); g.complete(c.command);
  g.prepare(f.command, f.context.view); await g.validate(f.command, asPeople(f.result), () => f.context.view); g.complete(f.command);
});
test('bad catalog image bytes cannot create a usable source receipt', async () => {
  const f = fixture(), g = createSkinReferenceChoiceGuard();
  f.context.catalog.source_image.sha256 = hash('0'); const c = catalogReceipt(f.context);
  g.prepare(c.command, f.context.view); await assert.rejects(g.validate(c.command, c.result, () => f.context.view));
  g.complete(c.command); assert.throws(() => g.prepare(f.command, f.context.view));
});
test('another family catalog cannot authorize this family and stale owner revisions invalidate retained proof', async () => {
  const f = fixture(), b = fixture('body'), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
  g.prepare(c.command, f.context.view); await g.validate(c.command, c.result, () => f.context.view); g.complete(c.command);
  assert.throws(() => g.prepare(b.command, b.context.view));
  g.update({...f.context.view, binding: {...f.context.view.binding, document_revision: 8}});
  assert.throws(() => g.prepare(f.command, f.context.view));
});
test('catalog replacement clears old receipt; late catalog validation cannot restore it across current document switch', async () => {
  const f = fixture(), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
  g.prepare(c.command, f.context.view);
  const changed = {...f.context.view, binding: {...f.context.view.binding, document_epoch: 'new-epoch'}};
  await g.validate(c.command, c.result, () => changed); g.complete(c.command);
  assert.throws(() => g.prepare(f.command, f.context.view));
});
test('unknown outcome retains original capture until sole owner completion; no second request or retry exists', async () => {
  const f = fixture(), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
  g.prepare(c.command, f.context.view); await g.validate(c.command, c.result, () => f.context.view); g.complete(c.command);
  g.prepare(f.command, f.context.view);
  await assert.rejects(g.validate(f.command, asPeople({...f.result, outcome_unknown: true}), () => f.context.view));
  assert.throws(() => g.prepare({...f.command, request_id: 'new-request'}, f.context.view));
  await g.validate(f.command, asPeople(f.result), () => f.context.view); g.complete(f.command);
});
test('malformed identity, writes and a released read with retained payload cannot become terminal success', async () => {
  for (const changes of [{request_id: 'foreign'}, {frame_emitted: true}, {doc_state: {}}, {payload_released: true}]) {
    const f = fixture(), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
    g.prepare(c.command, f.context.view); await g.validate(c.command, c.result, () => f.context.view); g.complete(c.command);
    g.prepare(f.command, f.context.view);
    await assert.rejects(g.validate(f.command, asPeople({...f.result, ...changes}), () => f.context.view));
  }
});
test('released read drops the source catalog; subsequent request needs a fresh original catalog', async () => {
  const f = fixture(), g = createSkinReferenceChoiceGuard(), c = catalogReceipt(f.context);
  g.prepare(c.command, f.context.view); await g.validate(c.command, c.result, () => f.context.view); g.complete(c.command);
  g.prepare(f.command, f.context.view);
  await g.validate(f.command, asPeople({...result(f.command), payload_released: true}), () => f.context.view); g.complete(f.command);
  assert.throws(() => g.prepare({...f.command, request_id: 'new-request'}, f.context.view));
});
