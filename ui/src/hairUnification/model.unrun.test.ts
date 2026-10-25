// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No imports, tests, builds, UI or photographic acceptance have been executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {OPERATION, CONTROL_ID, binding, checkRecipe, checkSample, emptySample, key, neutral,
  readPresented, readReference, readResult, readReview, readWorkspaceReopened, reviewAck,
  type Draft, type Reference, type Request, type Result, type Review, type Sample} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc-a', document_epoch: 'epoch-a', document_revision: 8, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2, faces: [{face_ref, enabled: true, box: [.1, .1, .4, .7], manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: face_ref.face_instance_id,
    editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}}, editing_overrides: {}, resolved: null};
}
function sample(): Sample {return {version: 1, domain: 'source-normalized', objects: [{id: 'root1', name: 'Root sample', enabled: true,
  kind: 'brush', operation: 'add', opacity: 1, feather: 1, points: [[.1, .2]], axes: [[.01, 0], [0, .02]]}]};}
function reference(): Reference {
  const view = fixture();
  return {source: {sha256: view.binding.asset_sha256, width: 200, height: 100}, face_ref: view.faces[0].face_ref,
    recipe: neutral(), root_sample: emptySample(), tip_sample: emptySample(), support_sha256: 'b'.repeat(64), semantic_evidence_sha256: 'c'.repeat(64),
    source_png: 'data:image/png;base64,AA==', source_width: 200, source_height: 100,
    source_preview_width: 200, source_preview_height: 100, native_available: true, notice: 'Manual samples only'};
}
function draft(): Draft {return {recipe: {version: 1, amount: .5}, root_sample: sample(), tip_sample: emptySample(), ownership_confirmed: true};}
function review(): Review {
  const ref = reference(), choice = draft();
  return {preview_id: '1'.repeat(32), review_token: 'd'.repeat(64), preview_sha256: 'd'.repeat(64), sample_asset_sha256: 'e'.repeat(64),
    source: ref.source, face_ref: ref.face_ref, recipe: choice.recipe, root_sample: choice.root_sample, tip_sample: choice.tip_sample,
    reference_side: 'roots', before_png: ref.source_png, after_png: ref.source_png, support_png: ref.source_png,
    before_sha256: 'f'.repeat(64), after_sha256: '0'.repeat(64), support_sha256: '1'.repeat(64),
    source_width: 200, source_height: 100, before_width: 200, before_height: 100, after_width: 200, after_height: 100,
    support_width: 200, support_height: 100, sample_counts: {hair_pixels: 100, root_pixels: 40, tip_pixels: 0, selected_pixels: 40}};
}

test('signed root/tip intent is separate and strictly versioned', () => {
  assert.equal(OPERATION, 'lnx.hair_unification.v1'); assert.equal(CONTROL_ID, 'LNX-REF-PC-32472-C-fb2fe59a22');
  assert.deepEqual(neutral(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, 0, .5, 1]) assert.equal(checkRecipe({version: 1, amount}).amount, amount);
  for (const amount of [-1.1, 1.1, NaN, Infinity, '0.5']) assert.throws(() => checkRecipe({version: 1, amount}));
  assert.throws(() => checkRecipe({version: 2, amount: 0}));
  assert.throws(() => checkRecipe({version: 1, amount: 0, strength: .2}));
});

test('neutral UI eligibility retains exact ownership; engine still verifies original source and retained analysis', () => {
  const view = fixture(); assert.equal(binding(view).measured, true);
  view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved';
  assert.equal(binding(view).targetReady, true); assert.equal(binding(view).measured, false);
  view.editing_target!.face_ref!.asset_sha256 = 'b'.repeat(64); assert.equal(binding(view).targetReady, false);
  for (const scope of ['group', 'person', 'all_people'] as const) {
    const shared = fixture(); shared.editing_target = {scope, target_id: shared.binding.asset_sha256, face_ref: null};
    assert.equal(binding(shared).targetReady, false);
  }
});

test('workspace reopen is exact native unknown evidence, never an ordinary success or automatic release', () => {
  const request: Request = {cmd: 'hair_unification', protocol: 1, operation_id: OPERATION, request_id: 'unknown-original',
    action: 'commit', people_context: binding(fixture()).context!,
    payload: {preview_id: '1'.repeat(32), review_token: 'd'.repeat(64), confirmed: true}};
  // Native synthetic failure/reopen receipts need not carry a successful payload.
  const original = {event: 'hair_unification_result', protocol: 1, operation_id: OPERATION, request_id: request.request_id,
    action: request.action, document_id: request.people_context.document_id, people_context: structuredClone(request.people_context),
    request_payload: structuredClone(request.payload), success: false, outcome_unknown: true, error: 'Original outcome remains unknown'};
  assert.equal(readWorkspaceReopened(original, request), null);
  assert.throws(() => readResult(original, request));
  const reopened = {...original, workspace_reopened: true};
  assert.equal(readWorkspaceReopened(reopened, request), reopened);
  assert.throws(() => readResult(reopened, request));
  for (const change of [{success: true}, {outcome_unknown: false}, {workspace_reopened: false}, {workspace_reopened: 'true'},
    {request_id: 'new'}, {action: 'clear'}, {document_id: 'new'}, {protocol: 2}, {operation_id: 'lnx.hair_colour.v1'},
    {request_payload: {}}, {people_context: {...original.people_context, document_epoch: 'new'}}])
    assert.throws(() => readWorkspaceReopened({...reopened, ...change}, request));
  for (const ordinary of [{...original, success: true, outcome_unknown: false}, {...original, outcome_unknown: false}]) {
    assert.equal(readWorkspaceReopened(ordinary, request), null);
    assert.equal(readResult(ordinary, request), ordinary);
  }
  // Native provenance comes from the dedicated status ledger, whose engine-event intake rejects this key.
  // Merely reading this predicate neither retires a request nor authorizes another send.
});

test('source masks stay bounded, explicit and non-transferable', () => {
  assert.deepEqual(checkSample(sample()), sample()); assert.deepEqual(checkSample(emptySample()), emptySample());
  for (const mutate of [
    (s: Sample) => {s.objects[0].axes = [[0, 0], [0, 0]];},
    (s: Sample) => {s.objects[0].operation = 'intersect';},
    (s: Sample) => {s.objects[0].name = '';},
    (s: Sample) => {s.objects.push({...s.objects[0]});},
  ]) {const value = sample(); mutate(value); assert.throws(() => checkSample(value));}
  assert.throws(() => checkSample({...sample(), domain: 'screen-pixels'}));
  assert.throws(() => checkSample({...sample(), automatic_root_detection: true}));
  const many = sample(); many.objects = Array.from({length: 65}, (_, i) => ({...many.objects[0], id: `brush${i}`}));
  assert.throws(() => checkSample(many));
});

test('reference and full review bind exact face, source, signed draft, samples and immutable asset', () => {
  const context = binding(fixture()).context!;
  assert.deepEqual(readReference(reference(), context), reference());
  assert.deepEqual(readReview(review(), reference(), draft()), review());
  for (const mutate of [
    (r: Review) => {r.face_ref = {...r.face_ref, face_instance_id: 'someone-else'};},
    (r: Review) => {r.source = {...r.source, sha256: '0'.repeat(64)};},
    (r: Review) => {r.reference_side = 'tips';}, (r: Review) => {r.recipe = {version: 1, amount: -.5};},
    (r: Review) => {r.sample_asset_sha256 = '';}, (r: Review) => {r.after_width = 199;},
    (r: Review) => {r.root_sample = emptySample();}, (r: Review) => {r.sample_counts.selected_pixels = 1;},
    (r: Review) => {r.before_png = 'https://example.invalid/not-a-bound-image.png';},
  ]) {const value = review(); mutate(value); assert.throws(() => readReview(value, reference(), draft()));}
  // A valid PNG data URL shape is not proof of decoding/hash matching: ReviewImages supplies that independent gate.
});

test('exact loaded-image ACK cannot authorize another image or candidate', () => {
  const expected = {kind: 'presented', presented: true, ...reviewAck(review())};
  readPresented(expected, review());
  for (const field of ['preview_id', 'review_token', 'before_sha256', 'after_sha256', 'support_sha256'])
    assert.throws(() => readPresented({...expected, [field]: 'different'}, review()));
  assert.throws(() => readPresented({...expected, presented: false}, review()));
});

test('only exact original action, context, payload and document receipt can release query-only protection', () => {
  const request: Request = {cmd: 'hair_unification', protocol: 1, operation_id: OPERATION, request_id: 'original', action: 'commit',
    people_context: binding(fixture()).context!, payload: {preview_id: '1'.repeat(32), review_token: 'd'.repeat(64), confirmed: true}};
  const result: Result = {event: 'hair_unification_result', protocol: 1, operation_id: OPERATION, request_id: request.request_id,
    action: request.action, document_id: request.people_context.document_id, people_context: structuredClone(request.people_context),
    request_payload: structuredClone(request.payload), success: true, outcome_unknown: false, payload: {}};
  assert.equal(readResult(result, request), result);
  for (const change of [{request_id: 'new'}, {action: 'clear'}, {document_id: 'new'}, {protocol: 2},
    {operation_id: 'lnx.hair_colour.v1'}, {outcome_unknown: true}, {request_payload: {}},
    {people_context: {...result.people_context, document_revision: 9}}])
    assert.throws(() => readResult({...result, ...change}, request));
  assert.equal(key({b: 1, a: [2, 3]}), key({a: [2, 3], b: 1}));
});
