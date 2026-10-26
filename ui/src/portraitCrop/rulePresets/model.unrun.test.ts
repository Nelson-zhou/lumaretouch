// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN; no Node, TypeScript parser or product imports were executed.
import assert from 'node:assert/strict';
import test from 'node:test';
import {checkedCatalogue, checkedName, checkedReply, rulesFromDraft, SCHEMA, type Catalogue} from './model.ts';
import {RulePresetCatalogue} from './controller.ts';
const draft = {aspect_ratio: '.75', headroom_fraction: '.1', head_fraction: '.6', horizontal_position: '.5'};
const empty = (): Catalogue => ({schema: SCHEMA, catalogue_id: 'a'.repeat(32), revision: 0, entries: []});
const saved = (): Catalogue => ({...empty(), revision: 1, entries: [{id: 'rule-1', name: 'Portrait', rules: rulesFromDraft(draft)}]});
test('catalogue refuses image state, unknown schema, booleans and duplicate identities', () => {
  assert.deepEqual(checkedCatalogue(saved()), saved());
  for (const key of ['source_uid', 'face_id', 'crown', 'chin', 'rect', 'preview_token', 'review_confirmed', 'version']) {
    const c = saved(); Object.assign(c.entries[0].rules, {[key]: 1}); assert.throws(() => checkedCatalogue(c));
  }
  assert.throws(() => checkedCatalogue({...saved(), schema: 'future.v2'}));
  assert.throws(() => checkedCatalogue({...saved(), source: 'photo'}));
  assert.throws(() => checkedCatalogue({...saved(), entries: [saved().entries[0], saved().entries[0]]}));
  assert.throws(() => checkedCatalogue({...saved(), entries: [{...saved().entries[0], rules: {...rulesFromDraft(draft), aspect_ratio: true}}]}));
  assert.throws(() => checkedReply({status: 'rejected', message: 'missing no-change proof'}));
});
test('bounded names and rule ranges never silently clamp or fill defaults', () => {
  for (const value of ['', ' leading', 'trailing ', '\u202ebidi', 'a'.repeat(65), '😀'.repeat(49)]) assert.throws(() => checkedName(value));
  assert.equal(checkedName('人'.repeat(64)), '人'.repeat(64));
  for (const value of ['', 'NaN', 'Infinity', '0', '1001']) assert.throws(() => rulesFromDraft({...draft, aspect_ratio: value}));
  assert.throws(() => rulesFromDraft({...draft, head_fraction: '.91'}));
});
test('a lost mutation is never retried; unchanged reads cannot unlock a delayed write', async () => {
  const requests: unknown[] = []; let current = empty();
  const c = new RulePresetCatalogue(async request => {requests.push(request); if (request.action === 'list') return {status: 'snapshot', catalogue: current}; throw Error('receipt lost');});
  await c.refresh(); await c.create('Portrait', draft);
  assert.equal(c.snapshot().uncertain?.action, 'create');
  await c.refresh(); assert.ok(c.snapshot().uncertain); assert.throws(() => c.create('Another', draft));
  current = saved(); await c.refresh(); assert.equal(c.snapshot().uncertain, null);
  assert.equal(requests.filter(r => (r as {action: string}).action === 'create').length, 1);
});
test('known rejection clears stale writes until explicit refresh; rename and delete are separate requests', async () => {
  const requests: {action: string}[] = [];
  const c = new RulePresetCatalogue(async request => {requests.push(request); return request.action === 'list' ? {status: 'snapshot', catalogue: saved()} : {status: 'rejected', no_change: true, message: 'stale revision'};});
  await c.refresh(); assert.throws(() => c.create('Portrait', draft)); await c.rename('rule-1', 'New name');
  assert.equal(c.snapshot().catalogue, null); assert.equal(c.snapshot().uncertain, null);
  assert.throws(() => c.delete('rule-1')); await c.refresh(); await c.delete('rule-1');
  assert.deepEqual(requests.map(r => r.action), ['list', 'rename', 'list', 'delete']);
});
