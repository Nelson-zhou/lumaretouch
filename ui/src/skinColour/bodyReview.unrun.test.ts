// AUTHORED / UNRUN. No UI/native/source-photo acceptance has been performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import type {PeopleAction, PeopleResult, PeopleView} from '../people/model.ts';
import {bodyMaskPoint, bodyRefKey, bodyReview, bodyReviewKey, emptyBodyMask, previewMatches,
  referenceMatches, renderedSkinImage, skinBodyAttached, skinBodyReceiptCurrent, skinBodyRequestFits,
  skinBodyTarget, type SkinBodyChoice, type SkinBodyMask, type SkinBodyPreview, type SkinBodyReference} from './bodyReviewModel.ts';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const face = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 2};
const body: SkinBodyChoice = {body_ref: {asset_sha256: face.asset_sha256, body_instance_id: 'body-a', analysis_revision: 3}, points_sha256: 'b'.repeat(64)};
function people(): PeopleView {
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face.asset_sha256}, revision: 4, association_revision: 2,
    faces: [{face_ref: {...face}, enabled: true, box: [.1, .1, .5, .5], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: face.face_instance_id, resolved: null,
    editing_target: {scope: 'face', target_id: face.face_instance_id, face_ref: {...face}}, editing_overrides: {},
    skin_body: {attached: true, needs_review: false, reason: null, face_ref: {...face}, source: {sha256: face.asset_sha256, width: 600, height: 800}}};
}
function mask(): SkinBodyMask {
  return {version: 1, domain: 'source-normalized', objects: [{id: 'brush-a', name: '皮肤添加', enabled: true, operation: 'add', kind: 'brush', opacity: 1, feather: 20,
    points: [[0, 0], [1, 1]], axes: [[.02, 0], [0, .015]]}]};
}
const flags = {visible: true, unoccluded: true, ownership_confirmed: true};
function reference(): SkinBodyReference {
  return {kind: 'reference', face_ref: {...face}, source: {sha256: face.asset_sha256, width: 600, height: 800}, attached: false,
    bodies: [structuredClone(body)], source_preview: {mime: 'image/png', base64: 'AAAA', width: 600, height: 800,
      source_sha256: face.asset_sha256, source_width: 600, source_height: 800, decoded_width: 600, decoded_height: 800,
      mapping: 'normalized_full_frame', orientation: 'exif_normalized_once'}};
}
function candidate(): SkinBodyPreview {
  const ref = reference(); return {kind: 'preview', preview_id: 'preview-a', source: ref.source, face_ref: {...face},
    before: {mime: 'image/png', base64: 'AAAA', width: 400, height: 300, mapping: 'rendered_result'},
    after: {mime: 'image/png', base64: 'BBBB', width: 400, height: 300, mapping: 'rendered_result'},
    overlay: ref.source_preview, review: bodyReview(body, mask(), flags), runtime_quality_accepted: false};
}
function command(action: PeopleAction['action'] = 'skin_body_reference'): PeopleAction {
  const view = people(); return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch,
    document_revision: view.binding.document_revision, state_revision: view.revision, association_revision: view.association_revision,
    target: view.editing_target!, action, request_id: 'request-a', payload: {}};
}
function result(request: PeopleAction): PeopleResult {
  return {protocol: 1, document_id: request.document_id, request_id: request.request_id, action: request.action,
    success: true, outcome_unknown: false, doc_state: {people: people()}, payload: reference()};
}

test('pointer coordinates map full image edges, not landmark pixel centres', () => {
  const rect = {left: 30, top: 40, width: 600, height: 800};
  assert.deepEqual(bodyMaskPoint(30, 40, rect), [0, 0]);
  assert.deepEqual(bodyMaskPoint(630, 840, rect), [1, 1]);
  assert.deepEqual(bodyMaskPoint(330, 440, rect), [.5, .5]);
  assert.equal(bodyMaskPoint(29, 40, rect), null);
  assert.equal(bodyMaskPoint(30, 841, rect), null);
  assert.equal(bodyMaskPoint(NaN, 40, rect), null);
  assert.equal(bodyMaskPoint(30, 40, {...rect, width: 0}), null);
});

test('manual recipe preserves radius axes, feather and every submitted point', () => {
  const draft = mask(), review = bodyReview(body, draft, flags);
  assert.deepEqual(review.recipe, draft); assert.notEqual(review.recipe, draft);
  assert.deepEqual(review.body_ref, body.body_ref); assert.equal(review.points_sha256, body.points_sha256);
  assert.equal(review.recipe.objects[0].feather, 20); assert.deepEqual(review.recipe.objects[0].axes, [[.02, 0], [0, .015]]);
  for (const field of ['visible', 'unoccluded', 'ownership_confirmed'] as const) assert.throws(() => bodyReview(body, draft, {...flags, [field]: false}));
  assert.throws(() => bodyReview(body, emptyBodyMask(), flags));
  const subtract = mask(); subtract.objects[0].operation = 'subtract'; assert.throws(() => bodyReview(body, subtract, flags));
  const invalid = mask(); invalid.objects[0].feather = Infinity; assert.throws(() => bodyReview(body, invalid, flags));
  const degenerate = mask(); degenerate.objects[0].axes = [[0, 0], [0, 0]]; assert.throws(() => bodyReview(body, degenerate, flags));
});

test('byte cap refuses oversized UTF-8 review before sending without decimating geometry', () => {
  const request = command('skin_body_preview'); request.payload = {review: bodyReview(body, mask(), flags)};
  assert.equal(skinBodyRequestFits(request), true);
  const large = {...request, payload: {review: '皮肤'.repeat(40_000)}};
  const saved = JSON.stringify(large); assert.equal(skinBodyRequestFits(large), false); assert.equal(JSON.stringify(large), saved);
});

test('reference requires exact current face, source and retained body identity', () => {
  assert.equal(skinBodyTarget(people()), true); assert.equal(referenceMatches(reference(), people()), true);
  const stale = reference(); stale.face_ref.analysis_revision += 1; assert.equal(referenceMatches(stale, people()), false);
  const foreign = reference(); foreign.bodies[0].body_ref.asset_sha256 = 'c'.repeat(64); assert.equal(referenceMatches(foreign, people()), false);
  const duplicate = reference(); duplicate.bodies.push(structuredClone(duplicate.bodies[0])); assert.equal(referenceMatches(duplicate, people()), false);
  const shared = people(); shared.editing_target = {scope: 'all_people', target_id: face.asset_sha256, face_ref: null}; assert.equal(skinBodyTarget(shared), false);
  const none = reference(); none.bodies = []; assert.equal(referenceMatches(none, people()), true);
});

test('candidate must echo the exact reviewed vectors and keep rendered/source domains distinct', () => {
  const review = bodyReview(body, mask(), flags), good = candidate(); assert.equal(previewMatches(good, reference(), review), true);
  const wrong = candidate(); wrong.review.recipe.objects[0].points.push([.1, .1]); assert.equal(previewMatches(wrong, reference(), review), false);
  const dimensions = candidate(); dimensions.after.width += 1; assert.equal(previewMatches(dimensions, reference(), review), false);
  const fakeAcceptance = candidate(); fakeAcceptance.runtime_quality_accepted = true as false; assert.equal(previewMatches(fakeAcceptance, reference(), review), false);
  assert.equal(renderedSkinImage({...good.after, mapping: 'normalized_full_frame' as 'rendered_result'}), null);
  assert.equal(renderedSkinImage({...good.after, width: 1281}), null);
  assert.equal(bodyReviewKey({b: 2, a: {d: 4, c: 3}}), bodyReviewKey({a: {c: 3, d: 4}, b: 2}));
  assert.notEqual(bodyRefKey(body.body_ref), bodyRefKey({...body.body_ref, analysis_revision: 4}));
});

test('correlated body receipts clear after target, source, analysis or document revision changes', () => {
  const request = command(), reply = result(request); assert.equal(skinBodyReceiptCurrent(request, reply, people()), true);
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_epoch = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.binding.asset_sha256 = 'c'.repeat(64);}, view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = 'face-b';}, view => {view.editing_target!.face_ref!.analysis_revision += 1;},
  ];
  for (const change of changes) {const view = people(); change(view); assert.equal(skinBodyReceiptCurrent(request, reply, view), false);}
  assert.equal(skinBodyReceiptCurrent(request, {...reply, request_id: 'other'}, people()), false);
  assert.equal(skinBodyReceiptCurrent(request, {...reply, outcome_unknown: true}, people()), false);
  const confirm = command('skin_body_confirm'), newer = people(); newer.revision += 1; newer.binding.document_revision += 1;
  assert.equal(skinBodyReceiptCurrent(confirm, result(confirm), newer), true);
});

test('attachment after reload is authoritative and stale support remains distinct from usable support', () => {
  const restored = people(); assert.equal(skinBodyAttached(restored), true);
  restored.skin_body!.needs_review = true; restored.skin_body!.reason = 'Body analysis changed';
  assert.equal(skinBodyAttached(restored), true); // Removable descriptor, not usable coverage.
  restored.skin_body!.face_ref.analysis_revision += 1; assert.equal(skinBodyAttached(restored), null);
  const empty = people(); empty.skin_body = undefined; assert.equal(skinBodyAttached(empty), null);
  const detached = people(); detached.skin_body!.attached = false; assert.equal(skinBodyAttached(detached), false);
  assert.ok(source('./SkinBodyPanel.tsx').includes('needs_review === false'));
  assert.ok(source('./SkinColourControl.tsx').includes('needs_review === false'));
});

test('canvas cancels captured strokes, invalidates review immediately and exposes hard limits', () => {
  const canvas = source('./SkinBodySourceEditor.tsx');
  for (const text of ['bodyMaskPoint(', 'onPointerCancel={cancel}', 'onLostPointerCapture=', 'onDraftStart();',
    'pixels / source.width', 'pixels / source.height', 'feather, points: [p]',
    'Math.min(1024, remaining)', '本笔已达到记录上限', '羽化与排除区以引擎审核图为准']) assert.ok(canvas.includes(text));
  assert.equal(canvas.includes('source.width - 1'), false); assert.equal(canvas.includes('source.height - 1'), false);
});

test('confirmation needs real loaded images, unchanged review, explicit consent and the same people owner', () => {
  const panel = source('./SkinBodyPanel.tsx'), control = source('./SkinColourControl.tsx');
  for (const text of ['people.submitCaptured(command)', 'skinBodyRequestFits(command)', '192 KiB', 'comparisonLoaded', 'draftMatches',
    'naturalWidth === image.width', 'naturalHeight === image.height', 'preview_id: preview.preview_id, reviewed: true',
    'request.context !== latest.current', 'receipt.result.payload_released', "send('skin_body_detach', {})",
    '先在全身塑形中完成身体分析与人物关联', 'coreAvailable', '已发请求仍待确认']) assert.ok(panel.includes(text));
  assert.ok(control.includes("control === 'temperature' && <SkinBodyPanel"));
  assert.ok(panel.includes('busy || !canDetach || attached !== true')); // No core/body validity gate on detach.
  assert.equal(panel.includes('runHistory'), false); assert.equal(panel.includes('runEnhance'), false);
});

test('Tauri admission and current workflow retain only correlated body results without a second owner', () => {
  const bridge = source('../../src-tauri/src/people_api.rs'), workflow = source('../people/workflow.ts');
  for (const action of ['skin_body_reference', 'skin_body_preview', 'skin_body_confirm', 'skin_body_detach']) {
    assert.ok(bridge.includes(`"${action}"`)); assert.ok(source('../people/model.ts').includes(`'${action}'`));
  }
  assert.ok(bridge.includes('request.to_string().len() > 256 * 1024'));
  assert.ok(workflow.includes('lastBodyResult: skinBodyReceiptCurrent(command, result, current)'));
  assert.ok(workflow.includes('!skinBodyReceiptCurrent(view.lastBodyResult.command, view.lastBodyResult.result, value)'));
  assert.ok(workflow.includes('lastBodyResult: null'));
});
