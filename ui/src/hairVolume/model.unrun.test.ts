// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: no product imports, tests, builds, inference or visual acceptance have been executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {CONTROL_IDS, OPERATION, activeRegions, binding, checkDraft, checkPatch, checkProtection, checkRecipe,
  checkSourceGeometry, emptyDraft, emptyPatch, isNeutral, key, neutral, previewPayload, readPresented,
  readReference, readResult, readReview, readWorkspaceReopened, reviewAck,
  type Draft, type Patch, type Reference, type Request, type Review} from './model.ts';
import {normalizedImagePoint, pairedProbe, sourcePixelPoint} from './sourceGeometry.ts';

function people(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc-a', document_epoch: 'epoch-a', document_revision: 8, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2, faces: [{face_ref, enabled: true, box: [.3, .5, .7, .8], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: face_ref.face_instance_id,
    editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}}, editing_overrides: {}, resolved: null};
}
const crown = (): Patch => ({x: [.2, .3, .7, .8], y: [.1, .2, .4, .5],
  contour: [[.35, .25], [.5, .24], [.65, .25]], hair_samples: [[.35, .3], [.5, .3], [.65, .3]],
  background_samples: [[.35, .15], [.5, .15], [.65, .15]]});
function draft(): Draft {
  const value = emptyDraft(); value.recipe.crown.amount = .5; value.regions.crown = crown(); value.crown_confirmed = true;
  value.protection.visible_anatomy_reviewed = true; value.protection.whole_source_reviewed = true; return value;
}
function reference(): Reference {
  const ref = people().faces[0].face_ref;
  return {source: {sha256: ref.asset_sha256, width: 1001, height: 801}, face_ref: ref, recipe: neutral(), source_kind: 'original',
    semantic_evidence_sha256: 'b'.repeat(64), source_png: 'data:image/png;base64,AA==', source_png_sha256: 'c'.repeat(64),
    source_width: 1001, source_height: 801, source_preview_width: 1001, source_preview_height: 801,
    native_available: true, notice: 'Manual observed contours only.'};
}
function review(): Review {
  const ref = reference(), payload = previewPayload(draft());
  return {preview_id: '1'.repeat(32), review_token: 'd'.repeat(64), preview_sha256: 'd'.repeat(64), support_asset_sha256: 'e'.repeat(64),
    source: ref.source, face_ref: ref.face_ref, recipe: payload.recipe, regions: payload.regions, protection: payload.protection,
    semantic_evidence_sha256: ref.semantic_evidence_sha256!, before_png: ref.source_png, after_png: ref.source_png, support_png: ref.source_png,
    before_sha256: 'f'.repeat(64), after_sha256: '0'.repeat(64), support_sha256: '1'.repeat(64),
    source_width: 1001, source_height: 801, before_width: 1001, before_height: 801,
    after_width: 1001, after_height: 801, support_width: 1001, support_height: 801};
}
function request(): Request {
  return {cmd: 'hair_volume', protocol: 1, operation_id: OPERATION, request_id: 'hair-volume-original', action: 'commit',
    people_context: binding(people()).context!, payload: {preview_id: '1'.repeat(32), review_token: 'd'.repeat(64), confirmed: true}};
}

test('independent versioned crown and side intent; linked equality is explicit', () => {
  assert.equal(OPERATION, 'lnx.hair_volume.v1');
  assert.deepEqual(CONTROL_IDS, {crown: 'control:PC-32472:2', sides: 'control:PC-32472:3'});
  assert.equal(isNeutral(neutral()), true);
  for (const amount of [-1, -.2, 0, .2, 1]) {
    const recipe = neutral(); recipe.crown.amount = amount; recipe.sides = {version: 1, linked: false, left: amount, right: -amount};
    assert.deepEqual(checkRecipe(recipe), recipe);
  }
  for (const amount of [-1.1, 1.1, NaN, Infinity, '0.5']) assert.throws(() => checkRecipe({...neutral(), crown: {version: 1, amount}}));
  assert.throws(() => checkRecipe({...neutral(), amount: .5}));
  assert.throws(() => checkRecipe({...neutral(), crown: {version: 2, amount: 0}}));
  assert.throws(() => checkRecipe({...neutral(), sides: {version: 1, linked: true, left: .5, right: .2}}));
  const both = neutral(); both.crown.amount = -.5; both.sides = {version: 1, linked: false, left: .5, right: 0};
  assert.deepEqual(activeRegions(both), ['crown', 'left']);
});

test('each active operation needs its own complete reviewed contour and shared explicit protection review', () => {
  const valid = draft(); assert.deepEqual(previewPayload(valid).regions.crown, crown());
  const unfinished = draft(); unfinished.regions.left = emptyPatch();
  assert.equal(checkDraft(unfinished).regions.left?.x, null);
  assert.equal(previewPayload(unfinished).regions.left, null, 'inactive local partial work is not submitted');
  for (const change of [
    (d: Draft) => {d.crown_confirmed = false;}, (d: Draft) => {d.regions.crown = null;},
    (d: Draft) => {d.protection.visible_anatomy_reviewed = false;}, (d: Draft) => {d.protection.whole_source_reviewed = false;},
    (d: Draft) => {d.recipe.sides = {version: 1, linked: false, left: .2, right: 0};},
  ]) {const value = draft(); change(value); assert.throws(() => previewPayload(value));}
  assert.throws(() => previewPayload(emptyDraft()));
  assert.throws(() => checkProtection({...draft().protection, inferred_ear_landmarks: [[.1, .2]]}));
});

test('paired observed contour probes use strict tangent ordering and real interior/exterior sides', () => {
  assert.deepEqual(checkPatch(crown(), 'crown'), crown());
  for (const mutate of [
    (p: Patch) => {p.contour.pop();}, (p: Patch) => {p.hair_samples[0] = [.36, .3];},
    (p: Patch) => {p.background_samples[0] = [.35, .3];}, (p: Patch) => {p.hair_samples[1] = [.5, .15];},
    (p: Patch) => {p.contour[1][0] = p.contour[0][0];}, (p: Patch) => {p.x = [.2, .3, .3, .8];},
    (p: Patch) => {p.background_samples[1] = [.5, .05];}, (p: Patch) => {p.hair_samples[1] = [.5, .45];},
  ]) {const value = crown(); mutate(value); assert.throws(() => checkPatch(value, 'crown'));}
  const left: Patch = {x: [.1, .2, .3, .4], y: [.2, .3, .6, .7], contour: [[.25, .35], [.25, .45], [.25, .55]],
    hair_samples: [[.28, .35], [.28, .45], [.28, .55]], background_samples: [[.15, .35], [.15, .45], [.15, .55]]};
  assert.deepEqual(checkPatch(left, 'left'), left);
  assert.throws(() => checkPatch(left, 'right'), 'image side direction may not be silently swapped');
});

test('pixel safety minima reject tiny margins, short contours and near-zero observed probes without clipping', () => {
  const source = reference().source;
  checkSourceGeometry(previewPayload(draft()).regions, source);
  for (const mutate of [
    (p: Patch) => {p.x[0] = .0001;}, (p: Patch) => {p.x[1] = p.x[0] + .001;},
    (p: Patch) => {p.x[2] = p.x[1] + .001;}, (p: Patch) => {p.y[3] = p.y[2] + .001;},
    (p: Patch) => {p.contour[2][0] = .4;}, (p: Patch) => {p.hair_samples[0][1] = p.contour[0][1] + .0001;},
  ]) {const value = crown(); mutate(value); assert.throws(() => checkSourceGeometry({crown: value, left: null, right: null}, source));}
});

test('source normalized clicks and exact pixel coordinates are independent of display scale', () => {
  const source = reference().source;
  assert.deepEqual(normalizedImagePoint([260, 220], {left: 10, top: 20, width: 500, height: 400}), [.5, .5]);
  assert.deepEqual(normalizedImagePoint([510, 420], {left: 10, top: 20, width: 1000, height: 800}), [.5, .5]);
  assert.deepEqual(sourcePixelPoint([500, 400], source), [.5, .5]);
  assert.throws(() => sourcePixelPoint([1000, 400], source));
  assert.throws(() => normalizedImagePoint([0, 0], {left: 0, top: 0, width: 0, height: 0}));
  assert.deepEqual(pairedProbe([.6, .4], [.5, .3], 'crown'), [.5, .4]);
  assert.deepEqual(pairedProbe([.6, .4], [.5, .3], 'left'), [.6, .3]);
});

test('selected current-source FaceRef cannot be replaced by a group or old-original face on derived pixels', () => {
  const context = binding(people()).context!;
  assert.equal(binding(people()).measured, true); assert.deepEqual(readReference(reference(), context), reference());
  assert.deepEqual(readReference({...reference(), source_kind: 'derived'}, context).source, reference().source);
  assert.throws(() => readReference({...reference(), source_kind: 'derived', source: {...reference().source, sha256: '2'.repeat(64)}}, context));
  assert.throws(() => readReference({...reference(), source_png_sha256: null}, context));
  for (const scope of ['all_people', 'person', 'group'] as const) {
    const value = people(); value.editing_target = {scope, target_id: 'group', face_ref: null}; assert.equal(binding(value).targetReady, false);
  }
  const synthetic = people(); synthetic.faces[0].analysis_status = 'synthetic'; assert.equal(binding(synthetic).measured, false);
});

test('full mixed review binds exact source, face, recipe, geometry, protection and actual image evidence', () => {
  assert.deepEqual(readReview(review(), reference(), draft()), review());
  for (const mutate of [
    (r: Review) => {r.source = {...r.source, sha256: '0'.repeat(64)};},
    (r: Review) => {r.face_ref = {...r.face_ref, face_instance_id: 'other-person'};},
    (r: Review) => {r.recipe = neutral();}, (r: Review) => {r.regions = {...r.regions, crown: null};},
    (r: Review) => {r.protection = {...r.protection, whole_source_reviewed: false};},
    (r: Review) => {r.semantic_evidence_sha256 = '0'.repeat(64);}, (r: Review) => {r.support_asset_sha256 = '';},
    (r: Review) => {r.after_width = 1000;}, (r: Review) => {r.support_height = 800;},
    (r: Review) => {r.before_png = 'https://example.invalid/not-the-candidate.png';},
  ]) {const value = review(); mutate(value); assert.throws(() => readReview(value, reference(), draft()));}
  // These model-only data URLs are not decode proof. ReviewImages independently requires decoded dimensions,
  // SHA-256 of delivered PNG bytes, full simultaneous visibility, document focus, two painted frames and explicit ACK.
});

test('exact actual image acknowledgment is separate from contour consent', () => {
  const original = review(), ack = {kind: 'presented', presented: true, ...reviewAck(original)};
  readPresented(ack, original);
  for (const field of ['preview_id', 'review_token', 'before_sha256', 'after_sha256', 'support_sha256'])
    assert.throws(() => readPresented({...ack, [field]: 'different'}, original));
  assert.throws(() => readPresented({...ack, presented: false}, original));
});

test('unknown result remains query-only; only exact native reopen proof permits explicit retirement', () => {
  const original = request();
  const receipt = {event: 'hair_volume_result', protocol: 1, operation_id: OPERATION, request_id: original.request_id,
    action: original.action, document_id: original.people_context.document_id, people_context: structuredClone(original.people_context),
    request_payload: structuredClone(original.payload), success: false, outcome_unknown: true};
  assert.throws(() => readResult(receipt, original)); assert.equal(readWorkspaceReopened(receipt, original), null);
  const reopened = {...receipt, workspace_reopened: true}; assert.equal(readWorkspaceReopened(reopened, original), reopened);
  for (const change of [{success: true}, {outcome_unknown: false}, {workspace_reopened: false}, {request_id: 'new'},
    {action: 'clear'}, {operation_id: 'lnx.head_size.v1'}, {request_payload: {}},
    {people_context: {...original.people_context, document_epoch: 'different'}}])
    assert.throws(() => readWorkspaceReopened({...reopened, ...change}, original));
  assert.equal(key({a: 1, b: 2}), key({b: 2, a: 1}));
});
