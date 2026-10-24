// AUTHORED / UNRUN. Pure model fixtures, not UI/native/numerical/photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {SKIN_COLOUR_CONTROL_IDS, SKIN_COLOUR_OPERATION, skinColourAccess, skinColourBindingKey,
  skinColourPatch, skinColourReading, skinColourReadiness, skinColourTargetReady,
  type SkinColourFences, type SkinColourKey} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {
    binding: {document_id: 'doc-a', document_epoch: 'epoch-a', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}},
    links: [], selected_face_id: face_ref.face_instance_id,
    editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}},
    editing_overrides: {[SKIN_COLOUR_OPERATION]: {'/temperature': .35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [],
      operations: {[SKIN_COLOUR_OPERATION]: {
        '/temperature': {value: .35, scope: 'face', target_id: 'face-a', overridden: true},
        '/tint': {value: -.2, scope: 'group', target_id: 'group', overridden: false},
      }}},
  };
}
const fences: SkinColourFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {skin_colour_available: true};

test('two exact handbook IDs and two independent signed canonical leaves', () => {
  assert.equal(SKIN_COLOUR_CONTROL_IDS.temperature, 'LNX-REF-PC-32465-C-f0ba809461');
  assert.equal(SKIN_COLOUR_CONTROL_IDS.tint, 'LNX-REF-PC-32465-C-0146f740bd');
  for (const key of ['temperature', 'tint'] as const) {
    for (const value of [-1, -.4, 0, .4, 1]) assert.deepEqual(skinColourPatch(key, value), {
      operation_id: 'lnx.skin_colour.v1', parameter_path: `/${key}`, unset: false, value,
    });
    for (const invalid of [-1.01, 1.01, NaN, Infinity, -Infinity]) assert.throws(() => skinColourPatch(key, invalid));
  }
  assert.throws(() => skinColourPatch('brightness' as SkinColourKey, 0));
});

test('readback uses selected face resolved values, never the target override or fake neutral', () => {
  const view = fixture();
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[SKIN_COLOUR_OPERATION]['/temperature'] = -.65;
  view.resolved!.operations[SKIN_COLOUR_OPERATION]['/temperature'] = {value: .35, scope: 'group', target_id: 'group', overridden: false};
  const reading = skinColourReading(view, 'temperature');
  assert.equal(reading.value, .35);
  assert.equal(reading.override, -.65);
  assert.equal(reading.source?.scope, 'group');
  assert.equal(skinColourReading(view, 'tint').override, null);
  assert.equal(skinColourReading(view, 'tint').overridePresent, false);
  delete view.resolved!.operations[SKIN_COLOUR_OPERATION]['/temperature'];
  assert.equal(skinColourReading(view, 'temperature').value, null);
  assert.equal(skinColourReading(null, 'temperature').value, null);
});

test('wrong source, selected face, anatomy revision and graph fences invalidate readback', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.selected_face_id = 'face-missing';},
    view => {view.resolved = null;},
    view => {view.resolved!.operations[SKIN_COLOUR_OPERATION]['/temperature'].value = '0.2';},
    view => {view.resolved!.operations[SKIN_COLOUR_OPERATION]['/temperature'].value = NaN;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(skinColourReading(view, 'temperature').value, null);
    assert.equal(skinColourAccess(view, 'temperature', available, fences).changeDisabled, true);
  }
});

test('conflicts are shown instead of guessed defaults and explicit invalid values are not called inherited', () => {
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: SKIN_COLOUR_OPERATION, parameter_path: '/temperature', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinColourReading(view, 'temperature').value, null);
  assert.equal(skinColourReading(view, 'tint').value, -.2);
  view.editing_overrides[SKIN_COLOUR_OPERATION]['/temperature'] = 'invalid';
  assert.equal(skinColourReading(view, 'temperature').override, null);
  assert.equal(skinColourReading(view, 'temperature').overridePresent, true);
});

test('all supported targets must be extant, source-bound and carry valid face aliases', () => {
  const view = fixture(); assert.equal(skinColourTargetReady(view), true);
  view.editing_target!.face_ref!.analysis_revision += 1;
  assert.equal(skinColourTargetReady(view), false);
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  assert.equal(skinColourTargetReady(view), true);
  view.editing_target.target_id = 'b'.repeat(64);
  assert.equal(skinColourTargetReady(view), false);
  for (const scope of ['group', 'person'] as const) {
    view.editing_target = {scope, target_id: scope, face_ref: null};
    assert.equal(skinColourTargetReady(view), true);
    view.editing_target.face_ref = {...view.faces[0].face_ref};
    assert.equal(skinColourTargetReady(view), false);
    view.editing_target = {scope, target_id: 'missing', face_ref: null};
    assert.equal(skinColourTargetReady(view), false);
    view.editing_target = {scope, target_id: 'toString', face_ref: null};
    assert.equal(skinColourTargetReady(view), false);
  }
  view.editing_target = null; assert.equal(skinColourTargetReady(view), false);
});

test('missing core, unverified face or missing preview disables edits but not fenced zero recovery', () => {
  for (const capability of [undefined, null, {}, {skin_colour_available: false, skin_colour_reason: 'ABI missing'}]) {
    const access = skinColourAccess(fixture(), 'temperature', capability, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  assert.deepEqual(skinColourReadiness({skin_colour_available: false, skin_colour_reason: 'ABI missing'}), {available: false, reason: 'ABI missing'});
  assert.equal(skinColourAccess(fixture(), 'temperature', available, fences).changeDisabled, false);
  const view = fixture(); view.faces[0].analysis_status = 'unresolved'; view.faces[0].enabled = false;
  const unverified = skinColourAccess(view, 'temperature', available, {...fences, faceOk: false});
  assert.equal(unverified.changeDisabled, true); assert.equal(unverified.resetDisabled, false);
  view.selected_face_id = null; view.resolved = null;
  assert.equal(skinColourAccess(view, 'temperature', {}, fences).resetDisabled, false);
});

test('pending, unknown receipt, unavailable owner and external edits fence both change and zero', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = skinColourAccess(fixture(), 'tint', {}, {...fences, ...change});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
  const view = fixture(); view.editing_target = null;
  assert.equal(skinColourAccess(view, 'tint', {}, fences).resetDisabled, true);
});

test('input bindings invalidate drafts after navigation, source changes, new analysis or receipts', () => {
  const original = skinColourBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'doc-b';},
    view => {view.binding.document_epoch = 'epoch-b';},
    view => {view.binding.document_revision += 1;},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.revision += 1;},
    view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(skinColourBindingKey(view), original);}
});
