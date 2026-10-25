// SPDX-License-Identifier: GPL-3.0-or-later
/** AUTHORED / UNRUN: no fixture was executed, built, typechecked or rendered in this source-only change. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {checkedHandoff, checkedReview, fetchReviewImage, reviewAck, reviewKey} from './presetReview.ts';
import {handoffFixture, reviewFixture, pageFixture, png} from './presetReviewFixture.unrun.test.ts';
import {checkedCatalogue} from './presetCatalogue.tsx';
const image = () => reviewFixture().before;
test('explicit preparation is a distinct unapproved phase with no review image authority', () => {
  const handoff = {...handoffFixture(), phase: 'awaiting_preparation', review: null};
  assert.ok(checkedHandoff(handoff));
  assert.equal(checkedHandoff({...handoff, phase: 'reviewing'}), null);
});
test('exact review rejects unsupported modules, partial image metadata and another handoff target', () => {
  const handoff = handoffFixture();
  assert.ok(checkedHandoff(handoff));
  assert.equal(checkedHandoff({...handoff, document_id: 'another-target'}), null);
  assert.equal(checkedReview({...reviewFixture(), module_ids: ['lnx.exposure.v1', 'portrait.unreviewed']}), null);
  assert.equal(checkedReview({...reviewFixture(), before: {...image(), page_count: 0}}), null);
  assert.equal(checkedHandoff({...handoff, phase: 'applying'}), null);
  assert.equal(checkedReview({...reviewFixture(), target: {...reviewFixture().target, revision: '18446744073709551616'}}), null);
});
test('all identity changes invalidate displayed image proof and exact approval', () => {
  const handoff = handoffFixture(), key = reviewKey('run-a', handoff), ack = reviewAck(handoff.review!);
  assert.deepEqual(Object.keys(ack).sort(), ['accepted', 'after_sha256', 'before_sha256', 'preset_id', 'preset_sha256', 'review_id', 'review_sha256', 'target']);
  assert.equal(ack.accepted, true);
  for (const changed of [
    {...handoff, operation_id: '4'.repeat(64)},
    {...handoff, review: {...handoff.review!, target: {...handoff.review!.target, load_id: 'new-load'}}},
    {...handoff, review: {...handoff.review!, after: {...image(), sha256: '5'.repeat(64)}}},
  ]) assert.notEqual(reviewKey('run-a', changed), key);
});
test('paged read verifies returned bytes and refuses swapped side, target, page or altered bytes', async () => {
  const handoff = handoffFixture();
  assert.equal(await fetchReviewImage('run-a', handoff, 'before', async input => pageFixture(input), () => true), `data:image/png;base64,${png}`);
  const mutations = [
    (page: any) => {page.side = 'after';}, (page: any) => {page.target.load_id = 'other-load';},
    (page: any) => {page.offset = 65536;}, (page: any) => {page.page_sha256 = '0'.repeat(64);},
    (page: any) => {page.base64 = `${png}=`;}, (page: any) => {page.sha256 = '0'.repeat(64);},
  ];
  for (const mutate of mutations) await assert.rejects(fetchReviewImage('run-a', handoff, 'before', async input => {
    const page = pageFixture(input); mutate(page); return page;
  }, () => true));
  await assert.rejects(fetchReviewImage('run-a', handoff, 'before', async input => pageFixture(input), () => false));
});
test('catalogue nullable source names do not hide whole-preset support refusal', () => {
  const catalogue = checkedCatalogue({schema: 'lrt.workflow-preset-catalogue.v1', complete: true, presets: [{id: 'portrait', name: 'Portrait', kind: 'portrait', builtin: false,
    preset_sha256: 'b'.repeat(64), module_ids: ['unsupported'], workflow_supported: false, support_reason: 'unsupported_workflow_preset_module'}],
    errors: [{code: 'fixture', file: null, message: 'Fixture diagnostic'}]});
  assert.ok(catalogue); assert.equal(catalogue.presets[0].workflow_supported, false);
});
