// AUTHORED / UNRUN. No imports, execution, native, UI or photographic acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {SKIN_GLOSS_OPERATION, SKIN_GLOSS_CONTROL_ID, SKIN_GLOSS_CONTROL_PATH, SKIN_GLOSS_SOURCE,
  neutralSkinGloss, skinGlossAccess, skinGlossBindingKey, skinGlossPatch, skinGlossReading,
  skinGlossReadiness, skinGlossTargetReady, type SkinGlossFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: face_ref.face_instance_id, editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}},
    editing_overrides: {[SKIN_GLOSS_OPERATION]: {'/amount': -.35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [SKIN_GLOSS_OPERATION]: {'/amount': {value: -.35, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_colour.v1': {'/temperature': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_finish.v1': {'/whitening': {value: .6, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.hair_colour.v1': {'/gloss': {value: .5, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const fences: SkinGlossFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {skin_gloss_available: true};

test('one exact handbook leaf and independent signed amount with zero neutral', () => {
  assert.equal(SKIN_GLOSS_CONTROL_ID, 'LNX-REF-PC-32465-C-1eed7cf9a9');
  assert.equal(SKIN_GLOSS_CONTROL_PATH, '皮肤质感/光泽度');
  assert.equal(SKIN_GLOSS_SOURCE, 'https://www.pixcakeai.com/guide/32465');
  assert.deepEqual(neutralSkinGloss(), {version: 1, amount: 0});
  for (const value of [-1, -.75, -.2, 0, .2, .75, 1]) assert.deepEqual(skinGlossPatch(value), {
    operation_id: 'lnx.skin_gloss.v1', parameter_path: '/amount', unset: false, value,
  });
  for (const invalid of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}]) {
    assert.throws(() => skinGlossPatch(invalid as number));
  }
});

test('effective selected-face value is not the write-target default or another operation', () => {
  const view = fixture(); view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[SKIN_GLOSS_OPERATION]['/amount'] = .7;
  const reading = skinGlossReading(view);
  assert.equal(reading.value, -.35); assert.equal(reading.override, .7); assert.equal(reading.source?.scope, 'face');
  delete view.editing_overrides[SKIN_GLOSS_OPERATION]['/amount'];
  assert.equal(skinGlossReading(view).overridePresent, false);
  view.editing_overrides[SKIN_GLOSS_OPERATION]['/amount'] = 0;
  assert.equal(skinGlossReading(view).overridePresent, true); assert.equal(skinGlossReading(view).override, 0);
  delete view.resolved!.operations[SKIN_GLOSS_OPERATION];
  assert.equal(skinGlossReading(view).value, null); // No finish, colour or hair fallback.
  assert.equal(skinGlossReading(null).value, null); assert.equal(skinGlossReading(undefined).value, null);
});

test('selected face, source, anatomy identity and authoritative revisions must match', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.selected_face_id = 'missing';}, view => {view.selected_face_id = null;}, view => {view.resolved = null;},
    ...[-1.1, 1.1, NaN, Infinity, '0.4', false].map(value => (view: PeopleView) => {
      view.resolved!.operations[SKIN_GLOSS_OPERATION]['/amount'].value = value;
    }),
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(skinGlossReading(view).value, null);
    assert.equal(skinGlossAccess(view, available, fences).changeDisabled, true);
  }
});

test('gloss-specific conflicts and invalid explicit values are visible, not silently neutralized', () => {
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: 'lnx.skin_finish.v1', parameter_path: '/whitening', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinGlossReading(view).value, -.35);
  view.resolved!.conflicts.push({operation_id: SKIN_GLOSS_OPERATION, parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinGlossReading(view).value, null);
  view.editing_overrides[SKIN_GLOSS_OPERATION]['/amount'] = 'invalid';
  assert.equal(skinGlossReading(view).override, null); assert.equal(skinGlossReading(view).overridePresent, true);
});

test('capability is gloss-specific; readiness does not assert observable highlights or pixel changes', () => {
  assert.deepEqual(skinGlossReadiness(available), {available: true});
  assert.deepEqual(skinGlossReadiness({skin_gloss_available: false, skin_gloss_reason: 'ABI unavailable'}),
    {available: false, reason: 'ABI unavailable'});
  for (const capability of [null, undefined, {}, {skin_colour_available: true}, {skin_finish_available: true}]) {
    assert.equal(skinGlossReadiness(capability as {} | null | undefined).available, false);
    const access = skinGlossAccess(fixture(), capability as {} | null | undefined, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  // No UI highlight mask/count is fabricated. An allowed nonzero setting can still render unchanged.
  assert.equal(skinGlossAccess(fixture(), available, fences).changeDisabled, false);
});

test('zero recovery does not depend on core, selected-face readback or usable anatomy', () => {
  const view = fixture();
  view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved'; view.resolved = null;
  let access = skinGlossAccess(view, null, {...fences, faceOk: false});
  assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  view.faces[0].face_ref.analysis_revision = 0; view.editing_target!.face_ref!.analysis_revision = 0;
  assert.equal(skinGlossTargetReady(view), true);
  view.selected_face_id = null;
  access = skinGlossAccess(view, null, {...fences, faceOk: false}); assert.equal(access.resetDisabled, false);
  for (const scope of ['group', 'person'] as const) {
    view.editing_target = {scope, target_id: scope, face_ref: null}; assert.equal(skinGlossTargetReady(view), true);
    view.editing_target.target_id = 'toString'; assert.equal(skinGlossTargetReady(view), false);
    view.editing_target.target_id = 'missing'; assert.equal(skinGlossTargetReady(view), false);
  }
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.faces = []; assert.equal(skinGlossTargetReady(view), true);
  assert.equal(skinGlossAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
});

test('neutral recovery still refuses missing, stale, malformed or foreign ownership', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;},
    view => {view.editing_target!.target_id = 'missing';},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.face_ref!.asset_sha256 = 'b'.repeat(64);},
    view => {view.editing_target!.face_ref = null;}, view => {view.faces = [];},
    view => {view.editing_target = {scope: 'all_people', target_id: 'b'.repeat(64), face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.editing_target = {scope: 'person', target_id: 'person', face_ref: {...view.faces[0].face_ref}};},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(skinGlossTargetReady(view), false);
    assert.equal(skinGlossAccess(view, available, fences).resetDisabled, true);
  }
});

test('disabled or synthetic anatomy blocks nonzero changes without blocking owned neutral recovery', () => {
  for (const status of ['unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = status;
    assert.equal(skinGlossAccess(view, available, fences).changeDisabled, true);
    assert.equal(skinGlossAccess(view, available, fences).resetDisabled, false);
  }
  const view = fixture(); view.faces[0].enabled = false;
  assert.equal(skinGlossAccess(view, available, fences).changeDisabled, true);
  assert.equal(skinGlossAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('pending, uncertain and external mutation fences cover signed edits and zero recovery', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = skinGlossAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
  assert.match(skinGlossAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('binding invalidates stale drafts on navigation, revision, source, face or target changes', () => {
  const initial = skinGlossBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.document_revision += 1;}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.faces[0].face_ref.analysis_revision += 1;}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(skinGlossBindingKey(view), initial);}
  assert.equal(skinGlossBindingKey(null), 'unavailable');
});

test('reading and access never alter the people graph or neighboring operation values', () => {
  const view = fixture(), before = JSON.stringify(view);
  skinGlossReading(view); skinGlossAccess(view, available, fences); skinGlossBindingKey(view); skinGlossPatch(-1);
  assert.equal(JSON.stringify(view), before);
});
