// AUTHORED / UNRUN. No import, execution, UI, native or photographic acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {SKIN_FINISH_CONTROL_IDS, SKIN_FINISH_OPERATION, neutralSkinFinish, skinFinishAccess, skinFinishBindingKey,
  skinFinishPatch, skinFinishReading, skinFinishReadiness, skinFinishTargetReady, type SkinFinishKey, type SkinFinishFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: face_ref.face_instance_id, editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}},
    editing_overrides: {[SKIN_FINISH_OPERATION]: {'/whitening': .35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [SKIN_FINISH_OPERATION]: {'/whitening': {value: .35, scope: 'face', target_id: 'face-a', overridden: true},
        '/rosiness': {value: .2, scope: 'group', target_id: 'group', overridden: false}},
      'lnx.skin_colour.v1': {'/temperature': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const fences: SkinFinishFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {skin_finish_available: true};

test('exact two finish leaf identities and independent unit recipes, never signed colour or exposure', () => {
  assert.deepEqual(SKIN_FINISH_CONTROL_IDS, {whitening: 'LNX-REF-PC-32465-C-d82f09f52f', rosiness: 'LNX-REF-PC-32465-C-60936d5259'});
  assert.deepEqual(neutralSkinFinish(), {version: 1, whitening: 0, rosiness: 0});
  for (const key of ['whitening', 'rosiness'] as const) {
    for (const value of [0, .2, .75, 1]) assert.deepEqual(skinFinishPatch(key, value), {
      operation_id: 'lnx.skin_finish.v1', parameter_path: `/${key}`, unset: false, value,
    });
    for (const invalid of [-1, -.01, 1.01, NaN, Infinity, -Infinity]) assert.throws(() => skinFinishPatch(key, invalid));
  }
  for (const key of ['temperature', 'tint', 'exposure', 'blush', 'brightness']) assert.throws(() => skinFinishPatch(key as SkinFinishKey, .4));
});

test('resolved face value and write-target override stay distinct; missing readback is not neutral', () => {
  const view = fixture(); view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[SKIN_FINISH_OPERATION]['/whitening'] = .7;
  const reading = skinFinishReading(view, 'whitening');
  assert.equal(reading.value, .35); assert.equal(reading.override, .7); assert.equal(reading.source?.scope, 'face');
  assert.equal(skinFinishReading(view, 'rosiness').overridePresent, false);
  delete view.resolved!.operations[SKIN_FINISH_OPERATION];
  assert.equal(skinFinishReading(view, 'whitening').value, null); // Colour .8 is not a fallback.
  assert.equal(skinFinishReading(null, 'rosiness').value, null);
});

test('selected face, source, anatomy and resolved revisions must match exactly', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.selected_face_id = 'missing';}, view => {view.resolved = null;},
    ...[-.1, 1.1, NaN, '0.4'].map(value => (view: PeopleView) => {view.resolved!.operations[SKIN_FINISH_OPERATION]['/whitening'].value = value;}),
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(skinFinishReading(view, 'whitening').value, null);
    assert.equal(skinFinishAccess(view, 'whitening', available, fences).changeDisabled, true);
  }
});

test('conflicts and invalid explicit values are visible without replacing other finish leaves', () => {
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: SKIN_FINISH_OPERATION, parameter_path: '/whitening', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinFinishReading(view, 'whitening').value, null); assert.equal(skinFinishReading(view, 'rosiness').value, .2);
  view.editing_overrides[SKIN_FINISH_OPERATION]['/whitening'] = 'invalid';
  assert.equal(skinFinishReading(view, 'whitening').override, null); assert.equal(skinFinishReading(view, 'whitening').overridePresent, true);
});

test('zero recovery keeps target ownership while remaining reachable without face analysis or core', () => {
  const view = fixture(); assert.equal(skinFinishTargetReady(view), true);
  for (const capability of [null, undefined, {}, {skin_finish_available: false, skin_finish_reason: 'ABI unavailable'}]) {
    const access = skinFinishAccess(view, 'whitening', capability, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  assert.deepEqual(skinFinishReadiness({skin_finish_available: false, skin_finish_reason: 'ABI unavailable'}), {available: false, reason: 'ABI unavailable'});
  assert.equal(skinFinishReadiness({skin_colour_available: true} as {}).available, false);
  view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved'; view.resolved = null;
  assert.equal(skinFinishAccess(view, 'rosiness', available, {...fences, faceOk: false}).resetDisabled, false);
  view.editing_target!.face_ref!.analysis_revision += 1; assert.equal(skinFinishTargetReady(view), false);
  for (const scope of ['group', 'person'] as const) {
    view.editing_target = {scope, target_id: scope, face_ref: null}; assert.equal(skinFinishTargetReady(view), true);
    view.editing_target.target_id = 'toString'; assert.equal(skinFinishTargetReady(view), false);
  }
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null}; assert.equal(skinFinishTargetReady(view), true);
  view.editing_target.target_id = 'b'.repeat(64); assert.equal(skinFinishTargetReady(view), false);
});

test('pending, uncertain and external ownership fence both scalar edits and zero recovery', () => {
  assert.equal(skinFinishAccess(fixture(), 'rosiness', available, fences).changeDisabled, false);
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = skinFinishAccess(fixture(), 'rosiness', available, {...fences, ...change});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
});

test('input binding changes cancel stale drafts on navigation, revision, source or target changes', () => {
  const initial = skinFinishBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.document_revision += 1;}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};}, view => {view.resolved!.face_ref.analysis_revision += 1;},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(skinFinishBindingKey(view), initial);}
});
