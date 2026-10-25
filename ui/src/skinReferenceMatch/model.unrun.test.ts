// AUTHORED / UNRUN. No test, typecheck, build, product execution or photo acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import type {FaceRef, PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {OPERATION_ID, ack, catalogImage, echoMatches, parseAmount, receiptCurrent, reviewImage,
  skinReferenceBinding, skinReferenceContext, validCatalog, validClear, validConfirmation, validCurrent,
  validImageReceipt, validPreview, validReleasedReceipt, validReview,
  type SkinReferenceCatalog, type SkinReferenceCurrent, type SkinReferencePreview, type SkinReferenceReview} from './model.ts';

const hash = (value: string) => value.repeat(64);
function refs(): FaceRef[] {
  return ['a', 'b', 'c'].map(id => ({asset_sha256: hash('a'), face_instance_id: `face-${id}`, analysis_revision: 3}));
}
function neutral(): SkinReferenceCurrent {
  return {version: 1, operation_id: OPERATION_ID, bank_sha256: hash('b'), reference_face_ref: null, target_face_refs: [], amounts: []};
}
export function view(): PeopleView {
  return {binding: {document_id: 'd'.repeat(32), document_epoch: 'epoch', document_revision: 7, asset_sha256: hash('a')},
    revision: 5, association_revision: 2, faces: refs().map((face_ref, index) => ({face_ref, enabled: true,
      box: [index / 3, .1, (index + .9) / 3, .9], manual: false, analysis_status: 'verified'})),
    groups: {}, persons: {}, links: [], selected_face_id: null, editing_target: null, editing_overrides: {}, resolved: null,
    skin_reference_match: neutral()};
}
export function image() {
  // Fixed one-pixel PNG is a protocol fixture, not face-matching or visual-quality evidence.
  const base64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7s8AAAAASUVORK5CYII=';
  return {mime: 'image/png' as const, base64, width: 1, height: 1, sha256: createHash('sha256').update(Buffer.from(base64, 'base64')).digest('hex')};
}
export function catalog(v = view()): SkinReferenceCatalog {
  return {kind: 'skin_reference_match_catalog', version: 1, operation_id: OPERATION_ID, scope: 'current-photo-face-only',
    source: {sha256: v.binding.asset_sha256, width: 1, height: 1}, source_proof: {asset_sha256: hash('a'), original_sha256: hash('a'), creative_source: null},
    document_id: v.binding.document_id, revision: String(v.binding.document_revision), source_image: image(), source_review_sha256: hash('c'),
    faces: v.faces.map(face => ({face_ref: face.face_ref, box: face.box, enabled: true, available: true, reason: null, amount: 0})),
    current: neutral(), body_matching: false, automatic_reference: false, skin_reference_match_available: true, skin_reference_match_reason: null};
}
export function preview(): SkinReferencePreview {
  return {version: 1, reference_face_ref: refs()[0], target_face_refs: [refs()[2], refs()[1]], amount: .5,
    source_review_sha256: hash('c'), ownership_confirmed: true};
}
export function review(v = view()): SkinReferenceReview {
  const c = catalog(v), p = preview(), {base64: _, ...metadata} = image();
  return {version: 1, token: 'f'.repeat(32), operation_id: OPERATION_ID, source: c.source,
    reference_face_ref: p.reference_face_ref, target_face_refs: p.target_face_refs, amount: p.amount,
    before_target_face_refs: [], candidate_state_revision: v.revision + 1, before_bank_sha256: hash('b'), candidate_bank_sha256: hash('e'),
    source_review_sha256: p.source_review_sha256, support_sha256: {'face-b': hash('1'), 'face-c': hash('2')}, review_sha256: hash('3'),
    owner: {document: {document_id: v.binding.document_id, epoch: v.binding.document_epoch, revision: v.binding.document_revision},
      people_scope: 'project', state_revision: v.revision, association_revision: v.association_revision, graph_sha256: hash('4'), source_proof: c.source_proof},
    visual: {version: 1, document_id: v.binding.document_id, revision: String(v.binding.document_revision), source_proof: c.source_proof,
      source_size: [1, 1], before_output_size: [1, 1], after_output_size: [1, 1], before: metadata, after: metadata,
      before_state_sha256: hash('5'), candidate_state_sha256: hash('6'), before_people_sha256: hash('7'), candidate_people_sha256: hash('8')}};
}
export function command(action: PeopleAction['action'] = 'skin_reference_match_preview', payload: Record<string, unknown> = preview()): PeopleAction {
  return {...skinReferenceContext(view())!, action, request_id: 'request-a', payload};
}
export function result(c: PeopleAction, payload?: unknown): PeopleResult {
  const {request_id: _, ...echo} = c;
  return {protocol: 1, request_id: c.request_id, action: c.action, document_id: c.document_id, success: true,
    outcome_unknown: false, skin_reference_match_request: echo, ...(payload === undefined ? {} : {payload})};
}
export function confirmation() {
  const r = review(), c = command('skin_reference_match_confirm', {token: r.token, ack: ack(r)}), next = view();
  next.binding.document_revision++; next.revision++;
  // The native report sorts targets independently of the submitted order.
  next.skin_reference_match = {version: 1, operation_id: OPERATION_ID, bank_sha256: r.candidate_bank_sha256,
    reference_face_ref: r.reference_face_ref, target_face_refs: [...r.target_face_refs].reverse(), amounts: [...r.target_face_refs].reverse()
      .map(face_ref => ({face_ref, amount: r.amount, support_sha256: r.support_sha256[face_ref.face_instance_id]}))};
  const receipt = {...result(c, {kind: c.action, token: r.token, review_sha256: r.review_sha256, ack: ack(r),
    reference_face_ref: r.reference_face_ref, target_face_refs: r.target_face_refs, amount: r.amount,
    candidate_state_revision: r.candidate_state_revision, candidate_bank_sha256: r.candidate_bank_sha256, support_sha256: r.support_sha256}),
    doc_state: {people: next}};
  return {r, c, receipt};
}
test('positive partial amount, explicit distinct same-source faces and source ownership are mandatory', () => {
  assert.equal(parseAmount('25'), .25); assert.equal(parseAmount('100'), 1);
  for (const text of ['', ' ', '0', '-1', '101', 'NaN', 'Infinity', '0x10', '1e1']) assert.equal(parseAmount(text), null);
  const p = preview(); assert.equal(validPreview(p), true);
  for (const candidate of [{...p, ownership_confirmed: false}, {...p, amount: 0}, {...p, target_face_refs: []},
    {...p, target_face_refs: [p.reference_face_ref]}, {...p, target_face_refs: [p.target_face_refs[0], p.target_face_refs[0]]},
    {...p, target_face_refs: [{...p.reference_face_ref, analysis_revision: 4}]}, {...p, automatic_reference: true},
    {...p, source_review_sha256: ''}]) assert.equal(validPreview(candidate), false);
});
test('asset target is cursor independent but document source/analysis and revisions invalidate drafts', () => {
  const v = view(), c = command(), r = result(c); assert.equal(receiptCurrent(c, r, v), true);
  const cursor = {...v, selected_face_id: 'face-b', editing_target: {scope: 'face' as const, target_id: 'face-b', face_ref: refs()[1]}};
  assert.equal(skinReferenceBinding(cursor), skinReferenceBinding(v)); assert.deepEqual(skinReferenceContext(cursor), c && skinReferenceContext(v));
  assert.equal(receiptCurrent(c, r, cursor), true);
  assert.equal(receiptCurrent({...c, target: cursor.editing_target}, r, cursor), false);
  assert.notEqual(skinReferenceBinding({...v, revision: 6}), skinReferenceBinding(v));
  assert.equal(receiptCurrent(c, r, {...v, revision: 6}), false);
});
test('catalog discloses actual source, every face, neutral state and no body/automatic substitution', async () => {
  const c = catalog(), v = view(); assert.equal(validCatalog(c, v), true); assert.ok(await catalogImage(c));
  for (const changed of [{...c, body_matching: true}, {...c, automatic_reference: true}, {...c, faces: c.faces.slice(1)},
    {...c, source_image: {...c.source_image, width: 2}}, {...c, source_proof: {...c.source_proof, original_sha256: hash('e')}},
    {...c, faces: c.faces.map((face, i) => i ? face : {...face, box: [.8, .1, .2, .9]})}]) assert.equal(validCatalog(changed, v), false);
  assert.equal(await catalogImage({...c, source_image: {...c.source_image, sha256: hash('0')}}), null);
  assert.equal(validCurrent({...neutral(), bank_sha256: 'missing'}, v), false);
});
test('exact action and complete echo bind the original request, not a valid-looking foreign payload', () => {
  const c = command(), r = result(c); assert.equal(echoMatches(c, r), true);
  assert.equal(echoMatches(c, {...r, skin_reference_match_request: undefined}), false);
  assert.equal(echoMatches(c, {...r, skin_reference_match_request: {...r.skin_reference_match_request!, payload: {...c.payload, amount: .6}}}), false);
  assert.equal(receiptCurrent(c, {...r, outcome_unknown: true}, view()), false);
  assert.equal(validReleasedReceipt(c, {...r, payload_released: true}), true);
  assert.equal(validReleasedReceipt(c, {...r, payload_released: true, payload: {kind: c.action}}), false);
});
test('review pins donor, ordered selection, amount, bank, source proof, state advance and complete-output size', () => {
  const r = review(), p = preview(), v = view(); assert.equal(validReview(r, v, p), true);
  for (const changed of [{...r, target_face_refs: [...r.target_face_refs].reverse()}, {...r, candidate_state_revision: 7},
    {...r, source_review_sha256: hash('0')}, {...r, support_sha256: {'face-b': hash('1')}},
    {...r, visual: {...r.visual, after: {...r.visual.after, width: 2}}},
    {...r, owner: {...r.owner, document: {...r.owner.document, epoch: 'old'}}}]) assert.equal(validReview(changed, v, p), false);
});
test('both image pages bind token side review hash byte digest and actual PNG dimensions', async () => {
  const r = review(), payload = {kind: 'skin_reference_match_image', token: r.token, side: 'before',
    sha256: r.visual.before.sha256, review_sha256: r.review_sha256, image: image()};
  const c = command('skin_reference_match_image', {token: r.token, side: 'before', sha256: r.visual.before.sha256, review_sha256: r.review_sha256});
  assert.equal(validImageReceipt(payload, c), true); assert.ok(await reviewImage(payload, r, 'before'));
  assert.equal(await reviewImage(payload, r, 'after'), null);
  assert.equal(await reviewImage({...payload, review_sha256: hash('0')}, r, 'before'), null);
  assert.equal(await reviewImage({...payload, image: {...payload.image, base64: payload.image.base64.slice(0, -4) + 'AAAA'}}, r, 'before'), null);
});
test('confirm requires exact proof and full native report; reordered report is allowed, substituted donor or bank is not', () => {
  const {r, receipt} = confirmation(); assert.equal(validConfirmation(r, receipt), true);
  assert.equal(validConfirmation(r, {...receipt, doc_state: undefined}), false);
  const next = receipt.doc_state.people;
  for (const report of [{...next.skin_reference_match!, bank_sha256: hash('0')},
    {...next.skin_reference_match!, reference_face_ref: refs()[1]},
    {...next.skin_reference_match!, amounts: next.skin_reference_match!.amounts.map(row => ({...row, amount: .8}))}]) {
    assert.equal(validConfirmation(r, {...receipt, doc_state: {people: {...next, skin_reference_match: report}}}), false);
  }
});
test('clear requires exact owner revisions, nonempty cleared set and verified neutral report', () => {
  const c = command('skin_reference_match_clear', {}), next = view(); next.binding.document_revision++; next.revision++;
  const r = {...result(c, {kind: c.action, candidate_state_revision: next.revision, cleared_face_refs: [refs()[1]]}), doc_state: {people: next}};
  assert.equal(validClear(c, r), true);
  assert.equal(validClear(c, {...r, payload: {...r.payload as Record<string, unknown>, cleared_face_refs: []}}), false);
  assert.equal(validClear(c, {...r, doc_state: {people: {...next, skin_reference_match: undefined}}}), false);
  assert.equal(validReleasedReceipt(c, {...r, payload: undefined, payload_released: true}), false);
});
