// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. Structural fixtures only; no source-image or photo acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyNeckConfirmations, emptyNeckMask, makeNeckReview, parseAmount, parseHalfWidth, sourcePoint,
  validNeckMask, type NeckMask} from './review.ts';
import {confirmation, inspectionAck, validCrop, validWritePayload, validWriteResult, type NeckCommand, type NeckCrop, type NeckPreview, type NeckResult} from './model.ts';
import type {PeopleView} from '../people/model';

const source = {sha256: 'a'.repeat(64), width: 4096, height: 3072};
const choice = {body_ref: {asset_sha256: source.sha256, body_instance_id: 'body-actual', analysis_revision: 3}, points_sha256: 'b'.repeat(64)};
const flags = {visible: true, unoccluded: true, ownership_confirmed: true, protections_reviewed: true, visible_neck_skin_reviewed: true};
const region = (): NeckMask => ({version: 1, domain: 'source-normalized', objects: [{id: 'neck1', name: '手绘颈部',
  enabled: true, kind: 'brush', operation: 'add', opacity: 1, feather: 0, points: [[.4, .6]], axes: [[.02, 0], [0, .03]]}]});
test('UNRUN: blank amount and observed scale do not infer neutral/face/pose defaults', () => {
  assert.equal(parseAmount(''), null); assert.equal(parseAmount('0'), 0); assert.equal(parseAmount('100'), 1);
  for (const value of ['NaN', 'Infinity', '-1', '101']) assert.equal(parseAmount(value), null);
  assert.equal(parseHalfWidth('', source), null); assert.equal(parseHalfWidth('1.39', source), null);
  assert.equal(parseHalfWidth('12.01', source), null); assert.equal(parseHalfWidth('3', source), 3 / 3072);
});
test('UNRUN: independent neck consent is mandatory, including explicit empty protections', () => {
  assert.throws(() => makeNeckReview(choice, source, region(), emptyNeckMask(), '3', emptyNeckConfirmations()));
  assert.throws(() => makeNeckReview(choice, source, region(), emptyNeckMask(), '3', {} as typeof flags));
  const review = makeNeckReview(choice, source, region(), emptyNeckMask(), '3', flags);
  assert.equal(review.neck.line_half_width, 3 / 3072); assert.equal(review.neck.protections_reviewed, true);
  assert.deepEqual(review.neck.protect_recipe.objects, []);
  assert.throws(() => makeNeckReview({...choice, body_ref: {...choice.body_ref, asset_sha256: 'c'.repeat(64)}}, source, region(), emptyNeckMask(), '3', flags));
});
test('UNRUN: hard protections cannot be subtracted, feathered, hidden or partially opaque', () => {
  for (const patch of [{operation: 'subtract'}, {enabled: false}, {opacity: .5}, {feather: 1}]) {
    const mask = region(); Object.assign(mask.objects[0], patch); assert.equal(validNeckMask(mask, true), false);
  }
  assert.equal(validNeckMask(region(), true), true); assert.equal(validNeckMask(emptyNeckMask()), false);
});
test('UNRUN: vectors remain bounded, unique, finite and unsimplified', () => {
  const duplicate = region(); duplicate.objects.push(structuredClone(duplicate.objects[0])); assert.equal(validNeckMask(duplicate), false);
  const invalid = region(); invalid.objects[0].points = [[NaN, .5]]; assert.equal(validNeckMask(invalid), false);
  const oversized = region(); oversized.objects[0].points = Array.from({length: 1025}, () => [.2, .3]); assert.equal(validNeckMask(oversized), false);
  assert.deepEqual(sourcePoint(10, 20, {left: 10, top: 20, width: 100, height: 200}), [0, 0]);
  assert.deepEqual(sourcePoint(110, 220, {left: 10, top: 20, width: 100, height: 200}), [1, 1]);
  assert.equal(sourcePoint(111, 220, {left: 10, top: 20, width: 100, height: 200}), null);
});

// Deliberately metadata-only objects: these bytes are NOT valid source PNGs.
// verifyImage/browser presentation must reject them; no fixture supplies consent.
const image = (sha: string, width: number, height: number) => ({mime: 'image/png' as const, base64: 'iVBORw==', width, height, sha256: sha.repeat(64)});
const preview = (): NeckPreview => ({kind: 'preview', family: 'neck_wrinkle', operation_id: 'lnx.neck_wrinkle.v1', preview_id: 'p1', source,
  source_proof: {asset_sha256: source.sha256, original_sha256: source.sha256, creative_source: null}, input_sha256: 'd'.repeat(64), repair_sha256: 'e'.repeat(64),
  face_ref: {asset_sha256: source.sha256, face_instance_id: 'face-actual', analysis_revision: 2},
  review: makeNeckReview(choice, source, region(), emptyNeckMask(), '3', flags), amount: .4,
  before: image('1', 1024, 768), after: image('2', 1024, 768), support: image('3', 1024, 768),
  before_output_size: [4096, 3072], after_output_size: [4096, 3072], runtime_quality_accepted: false});
const crop = (plane: 'before' | 'after'): NeckCrop => ({kind: 'crop', family: 'neck_wrinkle', operation_id: 'lnx.neck_wrinkle.v1',
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
  assert.equal(validWritePayload({kind: 'detached', family: 'neck_wrinkle', operation_id: 'lnx.neck_wrinkle.v1', attached: false, amount: 0}, 'neck_wrinkle_detach', 0), true);
  assert.equal(validWritePayload({kind: 'detached', family: 'skin_colour', operation_id: 'lnx.skin_colour.v1', attached: false, amount: 0}, 'neck_wrinkle_detach', 0), false);
});
test('UNRUN: canonical post-state must preserve other edits and publish this exact face amount/support', () => {
  const owner = preview(), pair = inspectionAck(crop('before'), crop('after'), owner)!;
  const parameter = (value: number) => ({value, scope: 'face' as const, target_id: owner.face_ref.face_instance_id, overridden: true});
  const before: PeopleView = {binding: {document_id: 'doc1', document_epoch: 'epoch1', document_revision: 8, asset_sha256: source.sha256},
    revision: 5, association_revision: 3, faces: [{face_ref: owner.face_ref, enabled: true, analysis_status: 'verified', manual: false, box: [.1, .1, .4, .4]}],
    groups: {}, persons: {}, links: [], selected_face_id: owner.face_ref.face_instance_id,
    editing_target: {scope: 'face', target_id: owner.face_ref.face_instance_id, face_ref: owner.face_ref},
    editing_overrides: {'lnx.neck_wrinkle.v1': {'/amount': 0}},
    resolved: {face_ref: owner.face_ref, state_revision: 5, association_revision: 3, conflicts: [], operations: {'lnx.neck_wrinkle.v1': {'/amount': parameter(0)}}}};
  const command: NeckCommand = {document_id: 'doc1', document_epoch: 'epoch1', document_revision: 8, state_revision: 5,
    association_revision: 3, request_id: 'request1', target: before.editing_target!, action: 'neck_wrinkle_confirm', payload: confirmation(owner, pair)};
  const next = {...structuredClone(before), binding: {...before.binding, document_revision: 9}, revision: 6,
    editing_overrides: {'lnx.neck_wrinkle.v1': {'/amount': .4}},
    resolved: {...before.resolved!, state_revision: 6, operations: {'lnx.neck_wrinkle.v1': {'/amount': parameter(.4)}}},
    neck_wrinkle: {family: 'neck_wrinkle', operation_id: 'lnx.neck_wrinkle.v1', face_ref: owner.face_ref, source, attached: true, needs_review: false}};
  const result: NeckResult = {protocol: 1, action: command.action, request_id: command.request_id, document_id: command.document_id,
    success: true, outcome_unknown: false, doc_state: {people: next}, payload: {kind: 'confirmed', family: 'neck_wrinkle', operation_id: 'lnx.neck_wrinkle.v1', attached: true, amount: .4}};
  assert.equal(validWriteResult(command, result, before, owner, pair), true);
  assert.equal(validWriteResult(command, result, before, owner), false);
  assert.equal(validWriteResult(command, {...result, outcome_unknown: true}, before, owner, pair), false);
  assert.equal(validWriteResult(command, {...result, doc_state: {people: {} as PeopleView}}, before, owner, pair), false);
  const wrong = structuredClone(next); wrong.neck_wrinkle.attached = false;
  assert.equal(validWriteResult(command, {...result, doc_state: {people: wrong}}, before, owner, pair), false);
});
