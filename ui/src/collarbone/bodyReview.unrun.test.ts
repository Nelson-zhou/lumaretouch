// AUTHORED / UNRUN. No imports, test execution, native processing or photograph acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {bodyReview, emptyBodyMask, parseBodyReviewAmount, previewMatches, referenceMatches,
  SKIN_BODY_FAMILIES, skinBodyActionFamily, skinBodyAttached, skinBodyFamilyMatches, skinBodyReceiptCurrent,
  type SkinBodyReview, type SkinBodyChoice, type SkinBodyMask, type SkinBodyPreview, type SkinBodyReference} from '../skinColour/bodyReviewModel.ts';

const family = 'collarbone' as const;
const tags = {family, operation_id: 'lnx.collarbone.v1'} as const;
const face = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 2};
const source = {sha256: face.asset_sha256, width: 600, height: 800};
const body: SkinBodyChoice = {body_ref: {asset_sha256: face.asset_sha256, body_instance_id: 'body-a', analysis_revision: 3}, points_sha256: 'b'.repeat(64)};
function people(): PeopleView {
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face.asset_sha256},
    revision: 4, association_revision: 2, faces: [{face_ref: {...face}, enabled: true,
      box: [.1, .1, .5, .5], manual: false, analysis_status: 'verified'}], groups: {}, persons: {}, links: [],
    selected_face_id: face.face_instance_id, resolved: null,
    editing_target: {scope: 'face', target_id: face.face_instance_id, face_ref: {...face}}, editing_overrides: {},
    collarbone: {...tags, attached: false, needs_review: false, face_ref: {...face}, source: {...source}}};
}
function mask(): SkinBodyMask {
  return {...emptyBodyMask(), objects: [{id: 'brush', name: '本人的身体皮肤', enabled: true, operation: 'add',
    kind: 'brush', opacity: 1, feather: 20, points: [[.3, .5], [.3, .6]], axes: [[.02, 0], [0, .015]]}]};
}
const flags = {visible: true, unoccluded: true, ownership_confirmed: true};
function reviewedBody(): SkinBodyReview {
  return {...bodyReview(body, mask(), flags), clavicle: {version: 1, domain: 'source-normalized', category: 'female',
    eligibility_confirmed: true, visible_anatomy_confirmed: true,
    curves: [{id: 'left', width: 16 / 600, points: [[.2, .3], [.3, .32], [.4, .3]]}]}};
}
function reference(): SkinBodyReference {
  return {...tags, kind: 'reference', attached: false, face_ref: {...face}, source: {...source}, bodies: [structuredClone(body)],
    source_preview: {mime: 'image/png', base64: 'AAAA', width: 600, height: 800, source_sha256: source.sha256,
      source_width: 600, source_height: 800, decoded_width: 600, decoded_height: 800,
      mapping: 'normalized_full_frame', orientation: 'exif_normalized_once'}};
}
function preview(): SkinBodyPreview {
  return {...tags, kind: 'preview', preview_id: 'preview-a', amount: .4, source: {...source}, face_ref: {...face},
    review: reviewedBody(), overlay: reference().source_preview, runtime_quality_accepted: false,
    before: {mime: 'image/png', base64: 'AAAA', width: 600, height: 800, mapping: 'rendered_result'},
    after: {mime: 'image/png', base64: 'BBBB', width: 600, height: 800, mapping: 'rendered_result'}};
}
function command(action: PeopleAction['action'] = 'collarbone_reference'): PeopleAction {
  const view = people(); return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch,
    document_revision: view.binding.document_revision, state_revision: view.revision, association_revision: view.association_revision,
    target: view.editing_target!, action, request_id: 'request-a', payload: {}};
}
function result(request: PeopleAction): PeopleResult {
  return {protocol: 1, document_id: request.document_id, request_id: request.request_id, action: request.action,
    success: true, outcome_unknown: false, doc_state: {people: people()}, payload: reference()};
}

test('new action family is exact, independent and not a colour or finish alias', () => {
  assert.equal(SKIN_BODY_FAMILIES[family].operation, tags.operation_id);
  assert.equal(SKIN_BODY_FAMILIES[family].report, 'collarbone');
  for (const verb of ['reference', 'preview', 'confirm', 'detach'] as const) {
    assert.equal(SKIN_BODY_FAMILIES[family].actions[verb], `collarbone_${verb}`);
    assert.equal(skinBodyActionFamily(SKIN_BODY_FAMILIES[family].actions[verb]), family);
    assert.notEqual(skinBodyActionFamily(SKIN_BODY_FAMILIES.skin_colour.actions[verb]), family);
    assert.notEqual(skinBodyActionFamily(SKIN_BODY_FAMILIES.skin_finish.actions[verb]), family);
  }
  for (const identity of [{}, {family}, {operation_id: tags.operation_id},
    {family, operation_id: 'lnx.skin_finish.v1'}, {family: 'skin_finish', operation_id: tags.operation_id},
    {family: 'skin_colour', operation_id: tags.operation_id}]) assert.equal(skinBodyFamilyMatches(identity, family), false);
  assert.equal(skinBodyFamilyMatches(tags, family), true);
  assert.equal(skinBodyFamilyMatches(tags), false);
  assert.equal(skinBodyFamilyMatches(tags, 'skin_finish'), false);
});

test('candidate amount is explicitly positive and cannot borrow blank or neutral intent', () => {
  for (const text of ['', ' ', '0', '-0', '-1', '101', 'Infinity', 'NaN', '0x10', '40%', '1,5']) {
    assert.equal(parseBodyReviewAmount(text), null);
  }
  for (const [text, amount] of [[' 40 ', .4], ['.5', .005], ['+25', .25], ['1e2', 1]] as const) {
    assert.equal(parseBodyReviewAmount(text), amount);
  }
  const ref = reference(), review = reviewedBody();
  assert.equal(previewMatches(preview(), ref, review, family, .4), true);
  for (const amount of [undefined, 0, -.1, 1.1, NaN, Infinity, .5]) assert.equal(previewMatches(preview(), ref, review, family, amount), false);
  const missing = preview(); delete missing.amount;
  assert.equal(previewMatches(missing, ref, review, family, .4), false);
  const wrong = preview(); wrong.amount = '0.4' as unknown as number;
  assert.equal(previewMatches(wrong, ref, review, family, .4), false);
});

test('reference and candidate require independent exact source, vectors and BodyRef review', () => {
  assert.equal(referenceMatches(reference(), people(), family), true);
  const shared = people(); shared.editing_target = {scope: 'all_people', target_id: face.asset_sha256, face_ref: null};
  assert.equal(referenceMatches(reference(), shared, family), false);
  const stale = reference(); stale.bodies[0].body_ref.asset_sha256 = 'c'.repeat(64);
  assert.equal(referenceMatches(stale, people(), family), false);
  const duplicate = reference(); duplicate.bodies.push(structuredClone(duplicate.bodies[0]));
  assert.equal(referenceMatches(duplicate, people(), family), false);
  const review = reviewedBody();
  for (const mutate of [(v: SkinBodyPreview) => {v.family = 'skin_finish';},
    (v: SkinBodyPreview) => {v.operation_id = 'lnx.skin_colour.v1';},
    (v: SkinBodyPreview) => {v.review.body_ref.body_instance_id = 'other-body';},
    (v: SkinBodyPreview) => {v.review.points_sha256 = 'c'.repeat(64);},
    (v: SkinBodyPreview) => {v.review.recipe.objects[0].points.push([.1, .1]);},
    (v: SkinBodyPreview) => {v.source.sha256 = 'c'.repeat(64);},
    (v: SkinBodyPreview) => {v.after.width++;},
    (v: SkinBodyPreview) => {v.runtime_quality_accepted = true as false;}]) {
    const candidate = preview(); mutate(candidate);
    assert.equal(previewMatches(candidate, reference(), review, family, .4), false);
  }
});

test('body report never borrows another operation and retains stale support only for recovery', () => {
  const view = people(); assert.equal(skinBodyAttached(view, family), false);
  view.collarbone!.attached = true; assert.equal(skinBodyAttached(view, family), true);
  view.collarbone!.needs_review = true; assert.equal(skinBodyAttached(view, family), true);
  view.collarbone!.face_ref.analysis_revision++; assert.equal(skinBodyAttached(view, family), null);
  delete view.collarbone;
  view.skin_finish_body = {...tags, family: 'skin_finish', operation_id: 'lnx.skin_finish.v1', attached: true, face_ref: {...face}, source};
  assert.equal(skinBodyAttached(view, family), null);
});

test('queryable receipts remain correlated to exact current action, family and ownership', () => {
  const request = command(), reply = result(request); assert.equal(skinBodyReceiptCurrent(request, reply, people()), true);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, payload: {...reference(), family: 'skin_finish'}}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, outcome_unknown: true}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, request_id: 'wrong'}, people()), false);
  const changed = people(); changed.binding.document_revision++;
  assert.equal(skinBodyReceiptCurrent(request, reply, changed), false);
  const confirm = command('collarbone_confirm');
  changed.revision++; changed.association_revision++;
  assert.equal(skinBodyReceiptCurrent(confirm, result(confirm), changed), true);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, payload_released: true, payload: undefined}, people()), true);
});


test('candidate metadata cannot omit, swap or alter explicit traces, category, confirmations or half width', () => {
  const submitted = reviewedBody();
  for (const mutate of [
    (v: SkinBodyPreview) => {delete v.review.clavicle;},
    (v: SkinBodyPreview) => {v.review.clavicle!.category = 'elder_female';},
    (v: SkinBodyPreview) => {v.review.clavicle!.curves[0].points[0][0] += .001;},
    (v: SkinBodyPreview) => {v.review.clavicle!.curves[0].width += .001;},
    (v: SkinBodyPreview) => {v.review.clavicle!.curves[0].id = 'right';},
    (v: SkinBodyPreview) => {v.review.clavicle!.visible_anatomy_confirmed = false as true;},
  ]) {const value = preview(); mutate(value); assert.equal(previewMatches(value, reference(), submitted, family, .4), false);}
  const absent = bodyReview(body, mask(), flags), candidate = preview(); delete candidate.review.clavicle;
  assert.equal(previewMatches(candidate, reference(), absent, family, .4), false);
  const illegal = reviewedBody(); illegal.clavicle!.curves[0].points[0] = [0, .3];
  candidate.review = illegal; assert.equal(previewMatches(candidate, reference(), illegal, family, .4), false);
});

test('older body families reject new clavicle metadata rather than inheriting its anatomy authority', () => {
  for (const old of ['skin_finish', 'body_skin_evenness'] as const) {
    const ref = reference(), value = preview();
    ref.family = old; ref.operation_id = SKIN_BODY_FAMILIES[old].operation;
    value.family = old; value.operation_id = SKIN_BODY_FAMILIES[old].operation;
    assert.equal(previewMatches(value, ref, reviewedBody(), old, .4), false);
    value.review = bodyReview(body, mask(), flags);
    assert.equal(previewMatches(value, ref, bodyReview(body, mask(), flags), old, .4), true);
  }
});
