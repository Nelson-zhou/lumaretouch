// AUTHORED / UNRUN. DTO fixtures, not rendering or actual review acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {SKIN_BODY_FAMILIES, bodyReview, emptyBodyMask, previewMatches, referenceMatches, skinBodyActionFamily,
  skinBodyAttached, skinBodyFamilyMatches, skinBodyReceiptCurrent, skinBodyReport, skinBodyRequestFits,
  type SkinBodyMask, type SkinBodyPreview, type SkinBodyReference} from '../skinColour/bodyReviewModel.ts';
const tags = {family: 'skin_finish', operation_id: 'lnx.skin_finish.v1'} as const;
const face = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face', analysis_revision: 2};
const source = {sha256: face.asset_sha256, width: 600, height: 800};
const choice = {body_ref: {asset_sha256: face.asset_sha256, body_instance_id: 'body', analysis_revision: 3}, points_sha256: 'b'.repeat(64)};
const flags = {visible: true, unoccluded: true, ownership_confirmed: true};
function people(): PeopleView {
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face.asset_sha256}, revision: 4, association_revision: 2,
    faces: [{face_ref: {...face}, enabled: true, box: [.1, .1, .5, .5], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: face.face_instance_id, resolved: null,
    editing_target: {scope: 'face', target_id: face.face_instance_id, face_ref: {...face}}, editing_overrides: {},
    skin_body: {attached: true, needs_review: false, face_ref: {...face}, source: {...source}},
    skin_finish_body: {...tags, attached: false, needs_review: false, face_ref: {...face}, source: {...source}}};
}
function mask(): SkinBodyMask {return {version: 1, domain: 'source-normalized', objects: [{id: 'brush', name: 'Skin', kind: 'brush', enabled: true,
  operation: 'add', opacity: 1, feather: 20, axes: [[.02, 0], [0, .015]], points: [[.3, .6], [.4, .7]]}]};}
function reference(finish = true): SkinBodyReference {
  return {...(finish ? tags : {}), kind: 'reference', attached: false, source: {...source}, face_ref: {...face}, bodies: [structuredClone(choice)],
    source_preview: {mime: 'image/png', base64: 'AAAA', width: 600, height: 800, source_sha256: source.sha256,
      source_width: 600, source_height: 800, decoded_width: 600, decoded_height: 800,
      mapping: 'normalized_full_frame', orientation: 'exif_normalized_once'}};
}
function preview(finish = true): SkinBodyPreview {
  return {...(finish ? tags : {}), kind: 'preview', preview_id: 'preview', source: {...source}, face_ref: {...face}, runtime_quality_accepted: false,
    before: {mime: 'image/png', base64: 'AAAA', width: 400, height: 300, mapping: 'rendered_result'},
    after: {mime: 'image/png', base64: 'BBBB', width: 400, height: 300, mapping: 'rendered_result'},
    overlay: reference().source_preview, review: bodyReview(choice, mask(), flags)};
}
function command(action: PeopleAction['action'] = 'skin_finish_body_reference'): PeopleAction {
  const view = people(); return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch,
    document_revision: view.binding.document_revision, state_revision: view.revision, association_revision: view.association_revision,
    request_id: 'finish-request', target: view.editing_target!, action, payload: {}};
}
function result(request: PeopleAction): PeopleResult {return {protocol: 1, request_id: request.request_id, action: request.action,
  document_id: request.document_id, success: true, outcome_unknown: false, doc_state: {people: people()}, payload: reference()};}

test('all four finish actions are distinct and colour defaults remain unchanged', () => {
  assert.equal(SKIN_BODY_FAMILIES.skin_colour.report, 'skin_body');
  assert.equal(SKIN_BODY_FAMILIES.skin_finish.report, 'skin_finish_body');
  for (const kind of ['reference', 'preview', 'confirm', 'detach'] as const) {
    const old = `skin_body_${kind}`, finish = `skin_finish_body_${kind}`;
    assert.equal(SKIN_BODY_FAMILIES.skin_colour.actions[kind], old); assert.equal(SKIN_BODY_FAMILIES.skin_finish.actions[kind], finish);
    assert.equal(skinBodyActionFamily(old as PeopleAction['action']), 'skin_colour');
    assert.equal(skinBodyActionFamily(finish as PeopleAction['action']), 'skin_finish');
  }
  assert.equal(skinBodyActionFamily('patch'), null);
});

test('old colour reports never imply finish attachment and both exact finish tags are required', () => {
  const view = people(); assert.equal(skinBodyAttached(view), true); assert.equal(skinBodyAttached(view, 'skin_finish'), false);
  delete view.skin_finish_body; assert.equal(skinBodyAttached(view, 'skin_finish'), null);
  view.skin_finish_body = structuredClone(view.skin_body!); assert.equal(skinBodyReport(view, 'skin_finish'), null);
  for (const identity of [{}, {family: 'skin_finish'}, {operation_id: 'lnx.skin_finish.v1'},
    {family: 'skin_finish', operation_id: 'lnx.skin_colour.v1'}, {family: 'skin_colour', operation_id: 'lnx.skin_finish.v1'}]) {
    assert.equal(skinBodyFamilyMatches(identity, 'skin_finish'), false);
  }
  assert.equal(skinBodyFamilyMatches(tags, 'skin_finish'), true); assert.equal(skinBodyFamilyMatches(tags), false);
  view.skin_finish_body = {...tags, ...structuredClone(view.skin_body!), needs_review: true, reason: 'Analysis changed'};
  assert.equal(skinBodyAttached(view, 'skin_finish'), true); // Retained and removable is not accepted coverage.
  view.skin_finish_body.face_ref.analysis_revision += 1; assert.equal(skinBodyAttached(view, 'skin_finish'), null);
});

test('reference and full render review reject opposite-family payloads even for the same face and geometry', () => {
  const review = bodyReview(choice, mask(), flags);
  assert.equal(referenceMatches(reference(), people(), 'skin_finish'), true);
  assert.equal(referenceMatches(reference(false), people(), 'skin_finish'), false);
  assert.equal(referenceMatches(reference(), people()), false);
  assert.equal(referenceMatches(reference(false), people()), true);
  assert.equal(previewMatches(preview(), reference(), review, 'skin_finish'), true);
  assert.equal(previewMatches(preview(false), reference(), review, 'skin_finish'), false);
  assert.equal(previewMatches(preview(), reference(false), review, 'skin_finish'), false);
  assert.equal(previewMatches(preview(), reference(), review), false);
  assert.equal(previewMatches(preview(false), reference(false), review), true);
});

test('finish receipts bind exact action request and family, with released images never made into approval', () => {
  const request = command(), reply = result(request); assert.equal(skinBodyReceiptCurrent(request, reply, people()), true);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, payload: reference(false)}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, action: 'skin_body_reference'}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, request_id: 'colour-request'}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, outcome_unknown: true}, people()), false);
  const stale = people(); stale.binding.document_revision += 1; assert.equal(skinBodyReceiptCurrent(request, reply, stale), false);
  // Retaining a correlated released receipt allows the panel to explain that a fresh review is necessary.
  assert.equal(skinBodyReceiptCurrent(request, {...reply, payload: undefined, payload_released: true}, people()), true);
  for (const action of ['skin_finish_body_confirm', 'skin_finish_body_detach'] as const) {
    const commit = command(action), newer = people(); newer.revision += 1; newer.binding.document_revision += 1;
    const outcome = {...tags, kind: action.endsWith('confirm') ? 'confirmed' : 'detached', attached: action.endsWith('confirm')};
    assert.equal(skinBodyReceiptCurrent(commit, {...result(commit), payload: outcome}, newer), true);
    assert.equal(skinBodyReceiptCurrent(commit, {...result(commit), payload: {...outcome, family: undefined}}, newer), false);
  }
});

test('independent finish review requires all fresh confirmations and preserves submitted geometry', () => {
  const draft = mask(), saved = JSON.stringify(draft), review = bodyReview(choice, draft, flags);
  assert.deepEqual(review.recipe, draft); assert.notEqual(review.recipe, draft); assert.equal(JSON.stringify(draft), saved);
  for (const key of ['visible', 'unoccluded', 'ownership_confirmed'] as const) assert.throws(() => bodyReview(choice, draft, {...flags, [key]: false}));
  assert.throws(() => bodyReview(choice, emptyBodyMask(), flags));
  const modified = preview(); modified.review.recipe.objects[0].points.push([.5, .8]);
  assert.equal(previewMatches(modified, reference(), review, 'skin_finish'), false);
  const request = command('skin_finish_body_preview'); request.payload = {review}; assert.equal(skinBodyRequestFits(request), true);
  request.payload = {review: '皮肤'.repeat(40_000)}; const large = JSON.stringify(request);
  assert.equal(skinBodyRequestFits(request), false); assert.equal(JSON.stringify(request), large);
});
