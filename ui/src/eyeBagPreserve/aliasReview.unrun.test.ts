// AUTHORED / UNRUN. No tests, imports, typechecks, builds, runtime or photo quality checks executed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ack, imageKey, imageMetadata, memberKey, reviewImage, validReview, validConfirmation, validAliasCommit} from './model';
import {reviewReady, type EyeBagImages, type EyeBagLoaded} from './reviewState';
import {aliasFixture} from './aliasFixture.unrun.test';

test('v1 unchanged; v2 current-first complete members retain independent effective-source provenance and pixels', () => {
  const f = aliasFixture(); assert.equal(validReview(f.single, f.view, f.candidate), true); assert.equal(validReview(f.review, f.view, f.candidate), true);
  assert.notEqual(f.review.members[1].visual.source_proof.original_sha256, f.review.owner.source_proof.original_sha256);
  assert.notEqual(f.review.members[1].visual.before.sha256, f.review.visual.before.sha256);
  const mutations: ((r: any) => void)[] = [r => r.members.reverse(), r => r.members.pop(), r => r.members.push(r.members[1]),
    r => r.members[1].visual.source_size = [3, 2], r => r.members[1].visual.source_proof.asset_sha256 = 'c'.repeat(64),
    r => r.members[1].visual.source_proof.creative_source = null, r => r.owner.people_scope = r.owner.document.document_id,
    r => r.visual.before_state_sha256 = 'b'.repeat(64), r => r.members[1].visual.revision = '09', r => r.members[1].visual.revision = '9007199254740992',
    r => r.members[1].path = '', r => r.members[1].path = '汉'.repeat(1400), r => r.members[1].extra = true,
    r => r.support_source.decoded_width = 3, r => r.support_overlay.width = 3, r => r.members[1].visual.after.width = 3];
  for (const mutate of mutations) {const r = structuredClone(f.review); mutate(r); assert.equal(validReview(r, f.view, f.candidate), false);}
  for (const count of [16, 17]) {
    const r = structuredClone(f.review); r.members = Array.from({length: count}, (_, n) => n === 0 ? r.members[0]
      : {...r.members[1], visual: {...r.members[1].visual, document_id: n.toString(16).padStart(32, '0')}});
    assert.equal(validReview(r, f.view, f.candidate), count === 16);
  }
  assert.equal(validReview({...f.single, members: f.review.members}, f.view, f.candidate), false);
});

test('individual decoded pairs plus one source geometry acceptance are mandatory and token/hash bound', () => {
  const f = aliasFixture(), images: EyeBagImages = {}, loaded: EyeBagLoaded = {}, accepted: Record<string, boolean> = {};
  images[imageKey(f.review, 'support')] = f.pngs[0]; loaded[imageKey(f.review, 'support')] = true;
  f.review.members.forEach(({visual}, index) => {
    for (const side of ['before', 'after'] as const) {const key = imageKey(f.review, side, visual.document_id);
      images[key] = f.pngs[index * 2 + (side === 'after' ? 1 : 0)]; loaded[key] = true;}
    accepted[memberKey(f.review, visual)] = true;
  });
  assert.equal(reviewReady(f.review, images, loaded, accepted, true), true);
  assert.equal(reviewReady(f.review, images, loaded, accepted, false), false);
  assert.equal(reviewReady(f.review, images, loaded, {...accepted, [memberKey(f.review, f.review.members[1].visual)]: false}, true), false);
  const missing = {...images}; delete missing[imageKey(f.review, 'after', f.review.members[1].visual.document_id)];
  assert.equal(reviewReady(f.review, missing, loaded, accepted, true), false);
  assert.equal(reviewReady(f.review, images, {...loaded, [imageKey(f.review, 'support')]: false}, accepted, true), false);
  assert.equal(reviewReady({...f.review, token: '0'.repeat(32)}, images, loaded, accepted, true), false);
  assert.equal(reviewReady({...f.review, review_sha256: '0'.repeat(64)}, images, loaded, accepted, true), false);
  assert.throws(() => imageMetadata(f.review, 'support', f.review.members[1].visual.document_id));
  const value = ack(f.review); assert.ok('members' in value);
  assert.deepEqual(value, {review_sha256: f.review.review_sha256, support_overlay_sha256: f.review.support_overlay.sha256,
    members: f.review.members.map(({visual}) => ({document_id: visual.document_id, revision: visual.revision,
      before_sha256: visual.before.sha256, after_sha256: visual.after.sha256}))});
});

test('paged image exact document+side+bytes, support only current owner, v1 request response shape retained', async () => {
  const f = aliasFixture(), document_id = f.review.members[1].visual.document_id, image = f.pngs[2];
  const reply = {kind: 'eye_bag_image', token: f.review.token, side: 'before', sha256: image.sha256,
    review_sha256: f.review.review_sha256, image, document_id};
  assert.deepEqual(await reviewImage(reply, f.review, 'before', document_id), image);
  assert.equal(await reviewImage({...reply, document_id: f.review.visual.document_id}, f.review, 'before', document_id), null);
  assert.equal(await reviewImage({...reply, image: f.pngs[0]}, f.review, 'before', document_id), null);
  assert.equal(await reviewImage({...reply, side: 'after'}, f.review, 'before', document_id), null);
  assert.equal(await reviewImage({...reply, image: {...image, base64: image.base64.replace('GPw8', 'GPw9')}}, f.review, 'before', document_id), null);
  const support = {...reply, document_id: f.review.visual.document_id, side: 'support', image: f.pngs[0], sha256: f.pngs[0].sha256};
  assert.deepEqual(await reviewImage(support, f.review, 'support'), f.pngs[0]);
  assert.equal(await reviewImage({...support, document_id}, f.review, 'support', document_id), null);
  const {document_id: _, ...legacy} = support;
  assert.deepEqual(await reviewImage(legacy, f.single, 'support'), f.pngs[0]);
  assert.equal(await reviewImage(support, f.single, 'support'), null);
  assert.equal(await reviewImage(legacy, f.review, 'support'), null);
});

test('confirmation proves actual batch, complete exact ordered member +1 revisions and source support graph', () => {
  const f = aliasFixture(); assert.equal(validConfirmation(f.review, f.result), true); assert.equal(validAliasCommit(f.commit), true);
  const mutations: ((r: any) => void)[] = [r => r.batch_id = null, r => r.batch_id = '', r => r.payload.alias_members.pop(),
    r => r.payload.alias_members.reverse(), r => r.payload.alias_members[1].result_revision = '9',
    r => r.payload.alias_members[1].expected_revision = '8', r => r.payload.alias_members[1].result_revision = '010',
    r => r.payload.ack.members.reverse(), r => r.payload.ack.members.pop(), r => r.payload.ack.support_overlay_sha256 = '0'.repeat(64),
    r => r.payload.recipe.amount = .2, r => r.payload.support_sha256 = '0'.repeat(64), r => r.outcome_unknown = true,
    r => r.doc_state.people.binding.document_revision++, r => r.doc_state.people.revision++, r => r.doc_state.people.association_revision++];
  for (const mutate of mutations) {const r = structuredClone(f.result); mutate(r); assert.equal(validConfirmation(f.review, r), false);}
  assert.equal(validAliasCommit({...f.commit, batchId: 'fabricated'}), false);
  assert.equal(validAliasCommit({...f.commit, command: {...f.command, payload: {...f.command.payload, hidden: true}}}), false);
});

test('UI lazy pages, complete ACK, late callback revocation and source-crop honesty are wired', () => {
  const source = (name: string) => readFileSync(new URL(name, import.meta.url), 'utf8');
  const panel = source('./EyeBagPreservePanel.tsx'), pages = source('./EyeBagReviewImages.tsx');
  for (const text of ['members(review)[page]', 'document_id: documentId', 'live.current.review = null', 'reviewReady(review, images, loaded, accepted, supportAccepted)',
    'reviewImage(payload, request.review, request.side, request.documentId)', 'setAccepted({}); setSupportAccepted(false)', 'eye_bag_confirm', '查询原请求，不重复提交']) assert.ok(panel.includes(text), text);
  for (const text of ['每张分别使用自己的像素', '不是每张成员的已修补眼部检查图', '已逐张确认', 'pairReady(review, member, images, loaded)']) assert.ok(pages.includes(text), text);
  assert.ok(panel.includes('不代表其他共享成员已修补后的眼部'));
  assert.ok(source('../native.ts').includes('observeEyeBagAliasHistory(status.session?.sync, observation)'));
  assert.ok(source('../people/usePeopleWorkflow.ts').includes('history.protectEyeBagAlias(eyeReceipt)'));
});
