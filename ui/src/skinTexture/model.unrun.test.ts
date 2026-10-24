// AUTHORED / UNRUN. These fixture imports have not been executed. No UI/native/photo acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {SKIN_TEXTURE_OPERATION, SKIN_TEXTURE_KEYS, SKIN_TEXTURE_CONTROL_IDS, SKIN_TEXTURE_CONTROL_PATHS,
  SKIN_TEXTURE_SOURCE, neutralSkinTexture, skinTextureAccess, skinTextureBindingKey, skinTexturePatch,
  skinTextureReading, skinTextureReadiness, skinTextureResetPatches, skinTextureTargetReady,
  type SkinTextureFences, type SkinTextureKey} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: face_ref.face_instance_id, editing_target: {scope: 'face', target_id: face_ref.face_instance_id, face_ref: {...face_ref}},
    editing_overrides: {[SKIN_TEXTURE_OPERATION]: {'/texture': -.35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [SKIN_TEXTURE_OPERATION]: {'/texture': {value: -.35, scope: 'face', target_id: 'face-a', overridden: true},
        '/clarity': {value: .2, scope: 'group', target_id: 'group', overridden: false}},
      'lnx.skin_gloss.v1': {'/amount': {value: .5, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_finish.v1': {'/whitening': {value: .6, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_colour.v1': {'/temperature': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const fences: SkinTextureFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {skin_texture_available: true};

test('exact two handbook leaves have independent signed texture and unsigned clarity domains', () => {
  assert.equal(SKIN_TEXTURE_OPERATION, 'lnx.skin_texture.v1');
  assert.deepEqual(SKIN_TEXTURE_KEYS, ['texture', 'clarity']);
  assert.deepEqual(SKIN_TEXTURE_CONTROL_IDS, {
    texture: 'LNX-REF-PC-32465-C-1c80d411ce', clarity: 'LNX-REF-PC-32465-C-46e0c819b6',
  });
  assert.deepEqual(SKIN_TEXTURE_CONTROL_PATHS, {texture: '皮肤质感/纹理度', clarity: '皮肤质感/清晰度'});
  assert.equal(SKIN_TEXTURE_SOURCE, 'https://www.pixcakeai.com/guide/32465');
  assert.deepEqual(neutralSkinTexture(), {version: 1, texture: 0, clarity: 0});
  for (const key of SKIN_TEXTURE_KEYS) {
    for (const value of key === 'texture' ? [-1, -.75, -.01, 0, .2, 1] : [0, .01, .2, .75, 1]) {
      assert.deepEqual(skinTexturePatch(key, value), {operation_id: SKIN_TEXTURE_OPERATION,
        parameter_path: `/${key}`, unset: false, value});
    }
    for (const invalid of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}]) {
      assert.throws(() => skinTexturePatch(key, invalid as number));
    }
  }
  for (const value of [-1, -.75, -.01]) assert.throws(() => skinTexturePatch('clarity', value));
  for (const key of ['detail_gain', 'strength', 'sharpness', 'contrast', 'amount', 'version', 'texture/clarity']) {
    assert.throws(() => skinTexturePatch(key as SkinTextureKey, .3));
  }
});

test('atomic reset contains exactly both neutral leaves and does not unset or mutate other parameters', () => {
  const patches = skinTextureResetPatches();
  assert.deepEqual(patches, [skinTexturePatch('texture', 0), skinTexturePatch('clarity', 0)]);
  assert.equal(patches.length, 2);
  assert.notEqual(skinTextureResetPatches(), patches);
  assert.deepEqual(skinTexturePatch('texture', 0), {
    operation_id: SKIN_TEXTURE_OPERATION, parameter_path: '/texture', unset: false, value: 0,
  });
  assert.deepEqual(skinTexturePatch('clarity', 0), {
    operation_id: SKIN_TEXTURE_OPERATION, parameter_path: '/clarity', unset: false, value: 0,
  });
});

test('selected-face values are distinct from target overrides, another leaf and neighboring operations', () => {
  const view = fixture(); view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[SKIN_TEXTURE_OPERATION]['/texture'] = .7;
  assert.equal(skinTextureReading(view, 'texture').value, -.35);
  assert.equal(skinTextureReading(view, 'texture').override, .7);
  assert.equal(skinTextureReading(view, 'texture').source?.scope, 'face');
  assert.equal(skinTextureReading(view, 'clarity').value, .2);
  assert.equal(skinTextureReading(view, 'clarity').source?.target_id, 'group');
  assert.equal(skinTextureReading(view, 'clarity').overridePresent, false);
  view.editing_overrides[SKIN_TEXTURE_OPERATION]['/clarity'] = 0;
  assert.equal(skinTextureReading(view, 'clarity').overridePresent, true);
  assert.equal(skinTextureReading(view, 'clarity').override, 0);
  delete view.resolved!.operations[SKIN_TEXTURE_OPERATION]['/texture'];
  assert.equal(skinTextureReading(view, 'texture').value, null);
  assert.equal(skinTextureReading(view, 'clarity').value, .2);
  delete view.resolved!.operations[SKIN_TEXTURE_OPERATION];
  for (const key of SKIN_TEXTURE_KEYS) {
    assert.equal(skinTextureReading(view, key).value, null);
    assert.equal(skinTextureReading(null, key).value, null);
    assert.equal(skinTextureReading(undefined, key).value, null);
  }
});

test('all resolved source scopes remain authoritative, not recomputed from editing target values', () => {
  for (const scope of ['default', 'all_people', 'group', 'person', 'face'] as const) {
    const view = fixture(), source = {value: -.2, scope,
      target_id: scope === 'default' ? null : scope === 'all_people' ? view.binding.asset_sha256
        : scope === 'face' ? 'face-a' : scope,
      overridden: scope === 'face'};
    view.resolved!.operations[SKIN_TEXTURE_OPERATION]['/texture'] = source;
    assert.equal(skinTextureReading(view, 'texture').source, source);
    assert.equal(skinTextureReading(view, 'texture').value, -.2);
    assert.equal(skinTextureReading(view, 'texture').override, -.35);
  }
});

test('source, selected face, measured identity and authoritative revisions must match exactly', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.binding.document_revision = NaN;}, view => {view.revision = -1;}, view => {view.association_revision = .5;},
    view => {view.faces[0].face_ref.analysis_revision = -1;}, view => {view.selected_face_id = 'missing';},
    view => {view.selected_face_id = null;}, view => {view.resolved = null;},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    for (const key of SKIN_TEXTURE_KEYS) {
      assert.equal(skinTextureReading(view, key).value, null);
      assert.equal(skinTextureAccess(view, key, available, fences).changeDisabled, true);
    }
  }
  for (const key of SKIN_TEXTURE_KEYS) {
    for (const value of [-1.1, 1.1, NaN, Infinity, '0.4', false, ...(key === 'clarity' ? [-.1] : [])]) {
      const view = fixture(); view.resolved!.operations[SKIN_TEXTURE_OPERATION][`/${key}`].value = value;
      assert.equal(skinTextureReading(view, key).value, null);
      assert.equal(skinTextureAccess(view, key, available, fences).changeDisabled, true);
    }
  }
});

test('conflicts and invalid explicit values are not silently hidden or replaced with zero', () => {
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: 'lnx.skin_gloss.v1', parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinTextureReading(view, 'texture').value, -.35);
  view.resolved!.conflicts.push({operation_id: SKIN_TEXTURE_OPERATION, parameter_path: '/texture', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});
  assert.equal(skinTextureReading(view, 'texture').value, null);
  assert.equal(skinTextureReading(view, 'clarity').value, .2);
  for (const key of SKIN_TEXTURE_KEYS) {
    view.editing_overrides[SKIN_TEXTURE_OPERATION][`/${key}`] = 'invalid';
    assert.equal(skinTextureReading(view, key).override, null);
    assert.equal(skinTextureReading(view, key).overridePresent, true);
  }
  view.editing_overrides[SKIN_TEXTURE_OPERATION]['/clarity'] = -.5;
  assert.equal(skinTextureReading(view, 'clarity').override, null);
});

test('readiness is dedicated to texture, and never asserts face readiness or photographic acceptance', () => {
  assert.deepEqual(skinTextureReadiness(available), {available: true});
  assert.deepEqual(skinTextureReadiness({skin_texture_available: false, skin_texture_reason: 'ABI unavailable'}),
    {available: false, reason: 'ABI unavailable'});
  for (const capability of [null, undefined, {}, {skin_colour_available: true}, {skin_finish_available: true}, {skin_gloss_available: true}]) {
    assert.equal(skinTextureReadiness(capability as {} | null | undefined).available, false);
    for (const key of SKIN_TEXTURE_KEYS) {
      const access = skinTextureAccess(fixture(), key, capability as {} | null | undefined, fences);
      assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    }
  }
  for (const key of SKIN_TEXTURE_KEYS) assert.equal(skinTextureAccess(fixture(), key, available, fences).changeDisabled, false);
});

test('neutral recovery stays reachable without core, selected-face readback or usable anatomy', () => {
  const view = fixture(); view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved'; view.resolved = null;
  view.faces[0].face_ref.analysis_revision = 0; view.editing_target!.face_ref!.analysis_revision = 0;
  assert.equal(skinTextureTargetReady(view), true);
  view.selected_face_id = null;
  for (const key of SKIN_TEXTURE_KEYS) {
    const access = skinTextureAccess(view, key, null, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  for (const scope of ['group', 'person'] as const) {
    view.editing_target = {scope, target_id: scope, face_ref: null}; assert.equal(skinTextureTargetReady(view), true);
    view.editing_target.target_id = 'toString'; assert.equal(skinTextureTargetReady(view), false);
    view.editing_target.target_id = 'missing'; assert.equal(skinTextureTargetReady(view), false);
  }
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.faces = []; assert.equal(skinTextureTargetReady(view), true);
  for (const key of SKIN_TEXTURE_KEYS) assert.equal(skinTextureAccess(view, key, null, {...fences, faceOk: false}).resetDisabled, false);
});

test('zero recovery retains ownership and revision fences even when anatomy and core are unavailable', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;},
    view => {view.editing_target!.target_id = 'missing';}, view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.face_ref!.asset_sha256 = 'b'.repeat(64);}, view => {view.editing_target!.face_ref = null;},
    view => {view.faces = [];}, view => {view.editing_target = {scope: 'all_people', target_id: 'b'.repeat(64), face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.editing_target = {scope: 'person', target_id: 'person', face_ref: {...view.faces[0].face_ref}};},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(skinTextureTargetReady(view), false);
    for (const key of SKIN_TEXTURE_KEYS) assert.equal(skinTextureAccess(view, key, null, {...fences, faceOk: false}).resetDisabled, true);
  }
});

test('unresolved, synthetic or disabled selected faces refuse nonzero edits, not owned zero recovery', () => {
  for (const status of ['unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = status;
    for (const key of SKIN_TEXTURE_KEYS) {
      assert.equal(skinTextureAccess(view, key, available, fences).changeDisabled, true);
      assert.equal(skinTextureAccess(view, key, available, fences).resetDisabled, false);
    }
  }
  const view = fixture(); view.faces[0].enabled = false;
  for (const key of SKIN_TEXTURE_KEYS) {
    assert.equal(skinTextureAccess(view, key, available, fences).changeDisabled, true);
    assert.equal(skinTextureAccess(fixture(), key, available, {...fences, faceOk: false}).changeDisabled, true);
  }
});

test('pending, uncertain, disabled and external owner fences cover all edits and both recovery actions', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    for (const key of SKIN_TEXTURE_KEYS) {
      const access = skinTextureAccess(fixture(), key, available, {...fences, ...change});
      assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
    }
  }
  assert.match(skinTextureAccess(fixture(), 'texture', available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('binding changes invalidate drafts for source, target, selected face, revisions and readback changes', () => {
  const initial = skinTextureBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.document_revision += 1;}, view => {view.binding.asset_sha256 = 'b'.repeat(64);},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.faces[0].face_ref.analysis_revision += 1;}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[SKIN_TEXTURE_OPERATION]['/texture'].value = .5;},
    view => {view.resolved!.operations[SKIN_TEXTURE_OPERATION]['/clarity'].value = .6;},
    view => {view.resolved!.conflicts.push({operation_id: SKIN_TEXTURE_OPERATION, parameter_path: '/texture', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[SKIN_TEXTURE_OPERATION]['/texture'] = .9;},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(skinTextureBindingKey(view), initial);}
  assert.equal(skinTextureBindingKey(null), 'unavailable');
});

test('model reads and patch preparation never mutate engine-owned people facts', () => {
  const view = fixture(), before = JSON.stringify(view);
  for (const key of SKIN_TEXTURE_KEYS) {
    skinTextureReading(view, key); skinTextureAccess(view, key, available, fences); skinTexturePatch(key, .5);
  }
  skinTextureBindingKey(view); skinTextureResetPatches();
  assert.equal(JSON.stringify(view), before);
});
