// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Structural fixtures only; no source-image or photo acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyHairSmoothingConfirmations, emptyHairSmoothingMask, makeHairSmoothingReview, parseAmount, parseTextureScale, sourcePoint,
  validHairSmoothingMask, validReview, type HairSmoothingMask} from './review.ts';
import {confirmation, inspectionAck, validCrop, validWritePayload, validWriteResult, sourceProof, verifyImage, validDiagnostics, type HairSmoothingCommand, type HairSmoothingCrop, type HairSmoothingPreview, type HairSmoothingResult} from './model.ts';
import type {PeopleView} from '../people/model';

const source = {sha256: 'a'.repeat(64), width: 4096, height: 3072};
const flags = {ownership_confirmed: true, protections_reviewed: true, visible_hair_reviewed: true};
const region = (): HairSmoothingMask => ({version: 1, domain: 'source-normalized', objects: [{id: 'hair1', name: '可见头发草稿',
  enabled: true, kind: 'brush', operation: 'add', opacity: 1, feather: 0, points: [[.4, .6]], axes: [[.02, 0], [0, .03]]}]});
test('UNRUN: blank amount and observed scale do not infer neutral/face/pose defaults', () => {
  assert.equal(parseAmount(''), null); assert.equal(parseAmount('0'), 0); assert.equal(parseAmount('100'), 1);
  for (const value of ['NaN', 'Infinity', '-1', '101']) assert.equal(parseAmount(value), null);
  assert.equal(parseTextureScale('', source), null); assert.equal(parseTextureScale('0.99', source), null);
  assert.equal(parseTextureScale('8.01', source), null); assert.equal(parseTextureScale('3', source), 3 / 3072);
});
test('UNRUN: independent hair consent needs target AND context, including explicit empty protections', () => {
  assert.throws(() => makeHairSmoothingReview(source, region(), region(), emptyHairSmoothingMask(), '3', emptyHairSmoothingConfirmations()));
  assert.throws(() => makeHairSmoothingReview(source, region(), region(), emptyHairSmoothingMask(), '3', {} as typeof flags));
  assert.throws(() => makeHairSmoothingReview(source, region(), emptyHairSmoothingMask(), emptyHairSmoothingMask(), '3', flags));
  const review = makeHairSmoothingReview(source, region(), region(), emptyHairSmoothingMask(), '3', flags);
  assert.equal(review.texture_scale, 3 / 3072); assert.equal(review.protections_reviewed, true);
  assert.deepEqual(review.protect_recipe.objects, []);
  assert.equal(validReview({...review, operation_id: 'lnx.hair_colour.v1'}, source), false);
  assert.equal(validReview({...review, neck: {}}, source), false);
  assert.equal(validReview({...review, texture_scale: 9 / 3072}, source), false);
});
test('UNRUN: hard protections cannot be subtracted, feathered, hidden or partially opaque', () => {
  for (const patch of [{operation: 'subtract'}, {enabled: false}, {opacity: .5}, {feather: 1}]) {
    const mask = region(); Object.assign(mask.objects[0], patch); assert.equal(validHairSmoothingMask(mask, true), false);
  }
  assert.equal(validHairSmoothingMask(region(), true), true); assert.equal(validHairSmoothingMask(emptyHairSmoothingMask()), false);
});
test('UNRUN: vectors remain bounded, unique, finite and unsimplified', () => {
  const duplicate = region(); duplicate.objects.push(structuredClone(duplicate.objects[0])); assert.equal(validHairSmoothingMask(duplicate), false);
  const invalid = region(); invalid.objects[0].points = [[NaN, .5]]; assert.equal(validHairSmoothingMask(invalid), false);
  const oversized = region(); oversized.objects[0].points = Array.from({length: 1025}, () => [.2, .3]); assert.equal(validHairSmoothingMask(oversized), false);
  assert.deepEqual(sourcePoint(10, 20, {left: 10, top: 20, width: 100, height: 200}), [0, 0]);
  assert.deepEqual(sourcePoint(110, 220, {left: 10, top: 20, width: 100, height: 200}), [1, 1]);
  assert.equal(sourcePoint(111, 220, {left: 10, top: 20, width: 100, height: 200}), null);
});

// Deliberately metadata-only objects: these bytes are NOT valid source PNGs.
// verifyImage/browser presentation must reject them; no fixture supplies consent.
const image = (sha: string, width: number, height: number) => ({mime: 'image/png' as const, base64: 'iVBORw==', width, height, sha256: sha.repeat(64)});
const preview = (): HairSmoothingPreview => ({kind: 'preview', family: 'hair_smoothing', operation_id: 'lnx.hair_smoothing.v1', preview_id: 'p1', source,
  source_proof: {asset_sha256: source.sha256, original_sha256: source.sha256, creative_source: null}, input_sha256: 'd'.repeat(64), repair_sha256: 'e'.repeat(64),
  face_ref: {asset_sha256: source.sha256, face_instance_id: 'face-actual', analysis_revision: 2},
  review: makeHairSmoothingReview(source, region(), region(), emptyHairSmoothingMask(), '3', flags), amount: .4,
  before: image('1', 1024, 768), after: image('2', 1024, 768), support: image('3', 1024, 768),
  before_output_size: [4096, 3072], after_output_size: [4096, 3072], diagnostics: {supported_pixels: 2000,
    context_rejected_pixels: 400, directional_pixels: 1500, changed_pixels: 700, no_signal_reason: null,
    texture_scale_px: 3, runtime_quality_accepted: false}, runtime_quality_accepted: false});
const crop = (plane: 'before' | 'after'): HairSmoothingCrop => ({kind: 'crop', family: 'hair_smoothing', operation_id: 'lnx.hair_smoothing.v1',
  preview_id: 'p1', source, source_proof: preview().source_proof, input_sha256: 'd'.repeat(64), repair_sha256: 'e'.repeat(64),
  plane, rect: [80, 100, 256, 128], domain: 'rendered_result', image: image(plane === 'before' ? '4' : '5', 256, 128)});
test('UNRUN: inspection must pair the exact candidate, native rectangle and repaired source', () => {
  const before = crop('before'), after = crop('after'), owner = preview();
  assert.ok(inspectionAck(before, after, owner));
  assert.equal(inspectionAck(before, {...after, rect: [81, 100, 256, 128]}, owner), null);
  assert.equal(inspectionAck(before, {...after, repair_sha256: 'f'.repeat(64)}, owner), null);
  assert.equal(inspectionAck(before, {...after, preview_id: 'old'}, owner), null);
  assert.equal(validCrop({...before, image: image('4', 128, 64)}, {preview_id: 'p1', plane: 'before', rect: before.rect}, owner), false);
});
test('UNRUN: confirmation binds all displayed images plus the inspected pair, not another operation', () => {
  const owner = preview(), pair = inspectionAck(crop('before'), crop('after'), owner)!;
  const ack = confirmation(owner, pair);
  assert.equal(ack.preview_id, 'p1'); assert.equal(ack.before_sha256, owner.before.sha256);
  assert.equal(ack.after_sha256, owner.after.sha256); assert.equal(ack.support_sha256, owner.support.sha256); assert.deepEqual(ack.inspection, pair);
  assert.equal(validWritePayload({kind: 'detached', family: 'hair_smoothing', operation_id: 'lnx.hair_smoothing.v1', attached: false, amount: 0}, 'hair_smoothing_detach', 0), true);
  assert.equal(validWritePayload({kind: 'detached', family: 'skin_colour', operation_id: 'lnx.skin_colour.v1', attached: false, amount: 0}, 'hair_smoothing_detach', 0), false);
});
test('UNRUN: canonical post-state must preserve other edits and publish this exact face amount/support', () => {
  const owner = preview(), pair = inspectionAck(crop('before'), crop('after'), owner)!;
  const parameter = (value: number) => ({value, scope: 'face' as const, target_id: owner.face_ref.face_instance_id, overridden: true});
  const before: PeopleView = {binding: {document_id: 'doc1', document_epoch: 'epoch1', document_revision: 8, asset_sha256: source.sha256},
    revision: 5, association_revision: 3, faces: [{face_ref: owner.face_ref, enabled: true, analysis_status: 'verified', manual: false, box: [.1, .1, .4, .4]}],
    groups: {}, persons: {}, links: [], selected_face_id: owner.face_ref.face_instance_id,
    editing_target: {scope: 'face', target_id: owner.face_ref.face_instance_id, face_ref: owner.face_ref},
    editing_overrides: {'lnx.hair_smoothing.v1': {'/amount': 0}},
    resolved: {face_ref: owner.face_ref, state_revision: 5, association_revision: 3, conflicts: [], operations: {'lnx.hair_smoothing.v1': {'/amount': parameter(0)}}}};
  const command: HairSmoothingCommand = {document_id: 'doc1', document_epoch: 'epoch1', document_revision: 8, state_revision: 5,
    association_revision: 3, request_id: 'request1', target: before.editing_target!, action: 'hair_smoothing_confirm', payload: confirmation(owner, pair)};
  const next = {...structuredClone(before), binding: {...before.binding, document_revision: 9}, revision: 6,
    editing_overrides: {'lnx.hair_smoothing.v1': {'/amount': .4}},
    resolved: {...before.resolved!, state_revision: 6, operations: {'lnx.hair_smoothing.v1': {'/amount': parameter(.4)}}},
    hair_smoothing: {family: 'hair_smoothing', operation_id: 'lnx.hair_smoothing.v1', face_ref: owner.face_ref, source, attached: true, needs_review: false}};
  const result: HairSmoothingResult = {protocol: 1, action: command.action, request_id: command.request_id, document_id: command.document_id,
    success: true, outcome_unknown: false, doc_state: {people: next}, payload: {kind: 'confirmed', family: 'hair_smoothing', operation_id: 'lnx.hair_smoothing.v1', attached: true, amount: .4}};
  assert.equal(validWriteResult(command, result, before, owner, pair), true);
  assert.equal(validWriteResult(command, result, before, owner), false);
  assert.equal(validWriteResult(command, {...result, outcome_unknown: true}, before, owner, pair), false);
  assert.equal(validWriteResult(command, {...result, doc_state: {people: {} as PeopleView}}, before, owner, pair), false);
  const wrong = structuredClone(next); wrong.hair_smoothing.attached = false;
  assert.equal(validWriteResult(command, {...result, doc_state: {people: wrong}}, before, owner, pair), false);
});

test('UNRUN: original-only proof rejects derived content even at identical dimensions', () => {
  const original = {asset_sha256: source.sha256, original_sha256: source.sha256, creative_source: null};
  assert.equal(sourceProof(original, source), true);
  assert.equal(sourceProof({...original, creative_source: {...source}}, source), false);
  assert.equal(sourceProof({...original, original_sha256: 'f'.repeat(64)}, source), false);
});
test('UNRUN: fake image metadata never proves image bytes or user inspection', async () => {
  assert.equal(await verifyImage(image('1', 2, 2)), false);
});
test('UNRUN: aggregate three-layer point budget cannot be bypassed by separate valid masks', () => {
  const dense = region(); dense.objects[0].points = Array.from({length: 1024}, () => [.4, .6]);
  dense.objects.push({...structuredClone(dense.objects[0]), id: 'hair2'});
  assert.equal(validHairSmoothingMask(dense), true);
  const review = {version: 1, domain: 'source-normalized', target_recipe: dense, context_recipe: dense,
    protect_recipe: region(), texture_scale: 3 / 3072, ...flags};
  assert.equal(validReview(review, source), false);
});

test('UNRUN: source diagnostics are bounded distinct counts, never actual final visual changes', () => {
  const p = preview(); assert.equal(validDiagnostics(p.diagnostics, source, p.review), true);
  assert.equal(validDiagnostics({...p.diagnostics, changed_pixels: 1501}, source, p.review), false);
  assert.equal(validDiagnostics({...p.diagnostics, directional_pixels: 2001}, source, p.review), false);
  assert.equal(validDiagnostics({...p.diagnostics, context_rejected_pixels: NaN}, source, p.review), false);
  assert.equal(validDiagnostics({...p.diagnostics, texture_scale_px: 4}, source, p.review), false);
  assert.equal(validDiagnostics({...p.diagnostics, runtime_quality_accepted: true}, source, p.review), false);
  assert.equal(validDiagnostics({...p.diagnostics, directional_pixels: 0, changed_pixels: 0, no_signal_reason: 'no-direction'}, source, p.review), true);
});
