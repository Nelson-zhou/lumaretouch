// AUTHORED / UNRUN. No test, typecheck, build, UI or real-photo execution performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import type {FaceRef, PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {OPERATION_ID, ack, catalogImage, echoMatches, parseAmount, previewMatchesCatalog, receiptCurrent,
  retainedTargetsMatch, reviewImage, skinReferenceBodyBinding, skinReferenceBodyContext, validCatalog,
  validClear, validConfirmation, validConsent, validCurrent, validImageReceipt, validMask, validPreview,
  validReleasedReceipt, validReview, type SkinReferenceBodyCatalog, type SkinReferenceBodyCurrent,
  type SkinReferenceBodyPreview, type SkinReferenceBodyReview} from './model.ts';

const hash = (v: string) => v.repeat(64);
const face = (id: string): FaceRef => ({asset_sha256: hash('a'), face_instance_id: `face-${id}`, analysis_revision: 3});
export function neutral(): SkinReferenceBodyCurrent {
  return {version: 1, operation_id: OPERATION_ID, bank_sha256: hash('b'), reference_face_ref: null, target_face_refs: [], amounts: []};
}
export function view(): PeopleView {
  return {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: hash('a')},
    revision: 5, association_revision: 2, faces: ['a', 'b'].map((id, i) => ({face_ref: face(id), enabled: true,
      box: [i / 2, .1, (i + .9) / 2, .5], manual: false, analysis_status: 'verified'})),
    groups: {}, persons: {'person-b': {anonymous: true}},
    links: [{face_instance_id: 'face-b', person_id: 'person-b', state: 'confirmed', confirmation_revision: 2}],
    selected_face_id: null, editing_target: null, editing_overrides: {}, resolved: null, skin_reference_body_match: neutral()};
}
export function image() {
  // Fixed one-pixel PNG is a protocol fixture, not imagery or runtime acceptance evidence.
  const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7s8AAAAASUVORK5CYII=';
  return {mime: 'image/png' as const, base64, width: 1, height: 1,
    sha256: createHash('sha256').update(Buffer.from(base64, 'base64')).digest('hex')};
}
export function preview(): SkinReferenceBodyPreview {
  return {version: 1, reference_face_ref: face('a'), target_face_ref: face('b'), amount: .5,
    source_review_sha256: hash('c'), ownership_confirmed: true,
    review: {operation_id: OPERATION_ID, body_ref: {asset_sha256: hash('a'), body_instance_id: 'body-b', analysis_revision: 1},
      points_sha256: hash('d'), recipe: {version: 1, domain: 'source-normalized', objects: [{id: 'stroke-a', name: 'body',
        enabled: true, operation: 'add', kind: 'brush', opacity: 1, feather: 10, points: [[.6, .8]], axes: [[.02, 0], [0, .02]]}]},
      visible: true, unoccluded: true, ownership_confirmed: true, reference_unchanged: true}};
}
export function catalog(v = view()): SkinReferenceBodyCatalog {
  const p = preview(), source = {sha256: hash('a'), width: 1, height: 1};
  return {kind: 'skin_reference_body_catalog', version: 1, operation_id: OPERATION_ID, scope: 'current-photo-body-only',
    source, source_proof: {asset_sha256: hash('a'), original_sha256: hash('a'), creative_source: null},
    document_id: v.binding.document_id, revision: String(v.binding.document_revision), source_image: image(), source_review_sha256: hash('c'),
    faces: v.faces.map(row => ({face_ref: row.face_ref, box: row.box, enabled: true, available: true, reason: null, amount: 0})),
    targets: [{face_ref: face('b'), body_ref: p.review.body_ref, points_sha256: p.review.points_sha256,
      source: {...source, orientation: 'exif_normalized_once'}, association: {person_id: 'person-b', body_ref: p.review.body_ref,
        people_association_revision: 2, confirmation_revision: 1}, box: v.faces[1].box, amount: 0}],
    current: neutral(), automatic_reference: false, body_matching: true, skin_reference_body_available: true, skin_reference_body_reason: null};
}
export function review(v = view()): SkinReferenceBodyReview {
  const p = preview(), c = catalog(v), {base64: _, ...metadata} = image();
  return {version: 1, token: 'f'.repeat(32), operation_id: OPERATION_ID,
    owner: {document: {document_id: v.binding.document_id, epoch: v.binding.document_epoch, revision: v.binding.document_revision},
      people_scope: 'project', state_revision: v.revision, association_revision: v.association_revision,
      graph_sha256: hash('1'), source_proof: c.source_proof}, source: c.source, reference_face_ref: p.reference_face_ref,
    target_face_ref: p.target_face_ref, body_ref: p.review.body_ref, body_review: p.review, amount: p.amount,
    source_review_sha256: p.source_review_sha256, body_bank_sha256: hash('2'), before_current: c.current,
    candidate_current: {version: 1, operation_id: OPERATION_ID, bank_sha256: hash('e'), reference_face_ref: p.reference_face_ref,
      target_face_refs: [p.target_face_ref], amounts: [{face_ref: p.target_face_ref, amount: p.amount, support_sha256: hash('3')}]},
    candidate_state_revision: v.revision + 1, before_bank_sha256: c.current.bank_sha256, candidate_bank_sha256: hash('e'),
    support_sha256: hash('3'), review_sha256: hash('4'), visual: {version: 1, document_id: v.binding.document_id,
      revision: String(v.binding.document_revision), source_proof: c.source_proof, source_size: [1, 1], before_output_size: [1, 1],
      after_output_size: [1, 1], before: metadata, after: metadata, before_state_sha256: hash('5'), candidate_state_sha256: hash('6'),
      before_people_sha256: hash('7'), candidate_people_sha256: hash('8')}};
}
export function command(action: PeopleAction['action'] = 'skin_reference_body_preview', payload: Record<string, unknown> = preview()): PeopleAction {
  return {...skinReferenceBodyContext(view())!, action, request_id: 'request-a', payload};
}
export function result(c: PeopleAction, payload?: unknown): PeopleResult {
  const {request_id: _, ...echo} = c;
  return {protocol: 1, request_id: c.request_id, action: c.action, document_id: c.document_id, success: true,
    outcome_unknown: false, skin_reference_body_request: echo, ...(payload === undefined ? {} : {payload})};
}
export function confirmation() {
  const r = review(), c = command('skin_reference_body_confirm', {token: r.token, ack: ack(r)}), next = view();
  next.binding.document_revision++; next.revision++; next.skin_reference_body_match = r.candidate_current;
  const receipt = {...result(c, {kind: c.action, token: r.token, review_sha256: r.review_sha256, review: r, ack: ack(r),
    reference_face_ref: r.reference_face_ref, target_face_ref: r.target_face_ref, body_ref: r.body_ref, amount: r.amount,
    candidate_state_revision: r.candidate_state_revision, candidate_bank_sha256: r.candidate_bank_sha256, support_sha256: r.support_sha256}),
    doc_state: {people: next}};
  return {r, c, receipt};
}

test('body-only selection allows donor=owner but never a foreign photo, stale same-instance or another consent family', () => {
  const p = preview(); assert.equal(validPreview(p), true);
  assert.equal(validPreview({...p, reference_face_ref: p.target_face_ref}), true);
  for (const candidate of [{...p, amount: 0}, {...p, ownership_confirmed: false}, {...p, reference_face_ref: {...p.target_face_ref, analysis_revision: 9}},
    {...p, review: {...p.review, operation_id: 'lnx.body_face_match.v1'}}, {...p, review: {...p.review, reference_unchanged: false}},
    {...p, target_face_ref: {...p.target_face_ref, asset_sha256: hash('f')}}, {...p, target_face_refs: [p.target_face_ref]}])
    assert.equal(validPreview(candidate), false);
  assert.equal(validConsent({...p.review, visible: false}), false);
  assert.equal(validConsent({...p.review, unoccluded: false}), false);
  assert.equal(validConsent({...p.review, ownership_confirmed: false}), false);
  for (const amount of ['', '0', '-1', '101', 'NaN', 'Infinity', '1e1']) assert.equal(parseAmount(amount), null);
});
test('manual recipe is source normalized, bounded, add/subtract only and never an inferred segment or empty consent', () => {
  const mask = preview().review.recipe; assert.equal(validMask(mask), true);
  for (const candidate of [{...mask, objects: []}, {...mask, domain: 'rendered_result'},
    {...mask, objects: [{...mask.objects[0], operation: 'intersect'}]}, {...mask, objects: [{...mask.objects[0], enabled: false}]},
    {...mask, objects: [{...mask.objects[0], points: [[NaN, .5]]}]}, {...mask, objects: [{...mask.objects[0], axes: [[0, 0], [0, 0]]}]},
    {...mask, objects: [mask.objects[0], mask.objects[0]]}]) assert.equal(validMask(candidate), false);
});
test('catalog proves actual source and explicit owner/body association, not face-box body inference', async () => {
  const c = catalog(), v = view(); assert.equal(validCatalog(c, v), true); assert.ok(await catalogImage(c));
  assert.equal(previewMatchesCatalog(preview(), c), true);
  for (const candidate of [{...c, body_matching: false}, {...c, faces: c.faces.slice(1)}, {...c, targets: [c.targets[0], c.targets[0]]},
    {...c, targets: [{...c.targets[0], association: {...c.targets[0].association, person_id: 'person-a'}}]},
    {...c, targets: [{...c.targets[0], points_sha256: 'not-a-digest'}]}, {...c, source_image: {...c.source_image, width: 2}}])
    assert.equal(validCatalog(candidate, v), false);
  assert.equal(validCatalog(c, {...v, links: v.links.map(link => ({...link, state: 'candidate'}))}), false);
  const bodyOnly = {...c, faces: c.faces.map((row, i) => i === 1 ? {...row, available: false, reason: 'No usable donor face skin'} : row)};
  assert.equal(validCatalog(bodyOnly, v), true); assert.equal(previewMatchesCatalog(preview(), bodyOnly), true);
  assert.equal(await catalogImage({...c, source_image: {...c.source_image, sha256: hash('0')}}), null);
});
test('current-photo binding ignores cursor but invalidates on ownership and measured source changes', () => {
  const v = view(), cursor = {...v, selected_face_id: 'face-a', editing_target: {scope: 'face' as const, target_id: 'face-a', face_ref: face('a')}};
  assert.equal(skinReferenceBodyBinding(v), skinReferenceBodyBinding(cursor));
  assert.deepEqual(skinReferenceBodyContext(v), skinReferenceBodyContext(cursor));
  assert.notEqual(skinReferenceBodyBinding(v), skinReferenceBodyBinding({...v, links: []}));
  const c = command(), r = result(c); assert.equal(echoMatches(c, r), true); assert.equal(receiptCurrent(c, r, v), true);
  assert.equal(echoMatches(c, {...r, skin_reference_body_request: undefined}), false);
  assert.equal(validReleasedReceipt(c, {...r, payload_released: true}), true);
});
test('frozen body review binds exact manual consent, body bank, donor, amount and retained target state', () => {
  const r = review(), p = preview(), v = view(); assert.equal(validReview(r, v, p), true);
  for (const changed of [{...r, body_ref: {...r.body_ref, analysis_revision: 9}}, {...r, body_review: {...r.body_review, reference_unchanged: false}},
    {...r, support_sha256: hash('0')}, {...r, candidate_state_revision: 9}, {...r, body_bank_sha256: ''},
    {...r, candidate_current: {...r.candidate_current, amounts: []}}, {...r, visual: {...r.visual, after_output_size: [2, 1]}}])
    assert.equal(validReview(changed, v, p), false);
  const old = {face_ref: face('a'), amount: .2, support_sha256: hash('9')};
  const retained = {...r, before_current: {...r.before_current, reference_face_ref: face('a'), target_face_refs: [old.face_ref], amounts: [old]},
    candidate_current: {...r.candidate_current, target_face_refs: [old.face_ref, r.target_face_ref], amounts: [old, ...r.candidate_current.amounts]}};
  assert.equal(retainedTargetsMatch(retained), true);
  assert.equal(retainedTargetsMatch({...retained, candidate_current: {...retained.candidate_current,
    amounts: [{...old, amount: .8}, ...r.candidate_current.amounts]}}), false);
});
test('actual PNG page binds this operation token/side/review/hash and confirmation checks the complete native report', async () => {
  const r = review(), payload = {kind: 'skin_reference_body_image', token: r.token, side: 'before',
    sha256: r.visual.before.sha256, review_sha256: r.review_sha256, image: image()};
  const c = command('skin_reference_body_image', {token: r.token, side: 'before', sha256: payload.sha256, review_sha256: r.review_sha256});
  assert.equal(validImageReceipt(payload, c), true); assert.ok(await reviewImage(payload, r, 'before'));
  assert.equal(await reviewImage({...payload, kind: 'skin_reference_match_image'}, r, 'before'), null);
  assert.equal(await reviewImage(payload, r, 'after'), null);
  const commit = confirmation(); assert.equal(validConfirmation(commit.r, commit.receipt), true);
  assert.equal(validConfirmation(commit.r, {...commit.receipt, doc_state: undefined}), false);
  const next = commit.receipt.doc_state.people;
  assert.equal(validConfirmation(commit.r, {...commit.receipt, doc_state: {people: {...next,
    skin_reference_body_match: {...next.skin_reference_body_match!, amounts: [{...r.candidate_current.amounts[0], amount: .9}]}}}}), false);
});
test('clear has a nonempty exact cleared set and neutral body report; another operation cannot substitute', () => {
  const c = command('skin_reference_body_clear', {}), next = view(); next.binding.document_revision++; next.revision++;
  const r = {...result(c, {kind: c.action, candidate_state_revision: next.revision, cleared_face_refs: [face('b')]}), doc_state: {people: next}};
  assert.equal(validClear(c, r), true);
  assert.equal(validClear(c, {...r, doc_state: {people: {...next, skin_reference_body_match: {...neutral(), reference_face_ref: face('a')}}}}), true);
  assert.equal(validCurrent({...neutral(), operation_id: 'lnx.skin_reference_match.v1'}, next), false);
  assert.equal(validClear(c, {...r, payload: {...r.payload as Record<string, unknown>, cleared_face_refs: []}}), false);
  assert.equal(validReleasedReceipt(c, {...r, payload: undefined, payload_released: true}), false);
});
