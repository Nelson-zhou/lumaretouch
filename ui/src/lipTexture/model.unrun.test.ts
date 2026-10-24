// AUTHORED / UNRUN. No imports, fixtures, UI, native processing or photograph acceptance were executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {LIP_TEXTURE_OPERATION, LIP_TEXTURE_CONTROL_ID, LIP_TEXTURE_CONTROL_PATH, LIP_TEXTURE_SOURCE,
  checkLipTexture, neutralLipTexture, lipTextureReadiness, lipTextureReading, lipTextureTargetReady,
  lipTextureSelectionMatches, lipTextureAccess, lipTextureBindingKey, lipTexturePatch,
  lipTextureResetPatches, parseLipTextureChoice, type LipTextureFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'},
      {face_ref: {...face_ref, face_instance_id: 'face-b'}, enabled: true, box: [.65, .1, .9, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}, other: {label: 'Other', priority: 2, face_ids: ['face-b']}},
    persons: {person: {anonymous: true}},
    links: [{face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 2}],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {[LIP_TEXTURE_OPERATION]: {'/amount': .35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [LIP_TEXTURE_OPERATION]: {'/amount': {value: .35, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.lip_makeup.v1': {'/saturation': {value: .7, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.facial_wrinkles.v1': {'/wrinkle_mouth_surround': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_texture.v1': {'/texture': {value: -.4, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const available = {lip_texture_available: true};
const fences: LipTextureFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};

test('one exact leaf, new independent operation and strict unsigned amount recipe', () => {
  assert.equal(LIP_TEXTURE_OPERATION, 'lnx.lip_texture.v1');
  assert.equal(LIP_TEXTURE_CONTROL_ID, 'LNX-REF-PC-32464-C-b6315c40ca');
  assert.equal(LIP_TEXTURE_CONTROL_PATH, '面部祛瑕疵/唇纹修整');
  assert.equal(LIP_TEXTURE_SOURCE, 'https://www.pixcakeai.com/guide/32464');
  assert.deepEqual(neutralLipTexture(), {version: 1, amount: 0});
  for (const value of [0, .01, .25, .8, 1]) {
    const recipe = {version: 1, amount: value};
    assert.deepEqual(checkLipTexture(recipe), recipe);
    assert.notEqual(checkLipTexture(recipe), recipe);
    assert.deepEqual(lipTexturePatch(value), {operation_id: LIP_TEXTURE_OPERATION, parameter_path: '/amount', unset: false, value});
  }
  for (const value of [-1, -.01, 1.01, NaN, Infinity, -Infinity, '0.3', null, true, {}]) {
    assert.throws(() => checkLipTexture({version: 1, amount: value}));
    assert.throws(() => lipTexturePatch(value as number));
  }
  for (const recipe of [null, [], {}, {version: 2, amount: 0}, {version: '1', amount: 0}, {amount: 0},
    {version: 1}, {version: 1, amount: 0, brightness: 0}, {version: 1, strength: .5},
    {version: 1, saturation: .5}, {version: 1, texture: .5}]) assert.throws(() => checkLipTexture(recipe));
});

test('blank and invalid text never become an implicit zero, clamp or shared inherited value', () => {
  for (const text of ['', ' ', '-', '+', '.', '-0', '-1', '101', 'NaN', 'Infinity', '0x10', '30%', '1 2', '1,5']) {
    assert.equal(parseLipTextureChoice(text), null);
  }
  for (const [text, value] of [['0', 0], ['100', 1], [' 25 ', .25], ['12.5', .125], ['.5', .005], ['+50', .5], ['1e2', 1]] as const) {
    assert.equal(parseLipTextureChoice(text), value);
  }
});

test('recovery is exactly one explicit amount zero, with no unset or adjacent operation', () => {
  assert.deepEqual(lipTextureResetPatches(), [{operation_id: LIP_TEXTURE_OPERATION,
    parameter_path: '/amount', unset: false, value: 0}]);
  assert.notEqual(lipTextureResetPatches(), lipTextureResetPatches());
});

test('effective selected-face readback, its provenance and target intent stay separate', () => {
  const view = fixture();
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[LIP_TEXTURE_OPERATION]['/amount'] = .8;
  const access = lipTextureAccess(view, available, fences);
  assert.equal(access.reading.value, .35); assert.equal(access.reading.source?.target_id, 'face-a');
  assert.equal(access.reading.override, .8); assert.equal(access.editValue, .8);
  delete view.editing_overrides[LIP_TEXTURE_OPERATION]['/amount'];
  assert.equal(lipTextureAccess(view, available, fences).editValue, null);
  assert.equal(lipTextureReading(view).overridePresent, false);
  assert.equal(lipTextureReading(view).value, .35);
  view.editing_overrides[LIP_TEXTURE_OPERATION]['/amount'] = 0;
  assert.equal(lipTextureReading(view).overridePresent, true);
  assert.equal(lipTextureAccess(view, available, fences).editValue, 0);
  view.editing_overrides[LIP_TEXTURE_OPERATION]['/amount'] = 'invalid';
  assert.equal(lipTextureReading(view).overridePresent, true);
  assert.equal(lipTextureReading(view).override, null);
  assert.equal(lipTextureAccess(view, available, fences).editValue, null);
  assert.equal(lipTextureAccess(view, available, fences).changeDisabled, false);
});

test('only face targets may edit their own inherited amount without a blank shared choice', () => {
  const view = fixture(); delete view.editing_overrides[LIP_TEXTURE_OPERATION];
  assert.equal(lipTextureAccess(view, available, fences).editValue, .35);
  for (const scope of ['group', 'person', 'all_people'] as const) {
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(lipTextureAccess(view, available, fences).editValue, null);
    assert.equal(lipTextureAccess(view, available, fences).changeDisabled, false);
  }
});

test('all engine provenance scopes are displayed without replacing them from local intent', () => {
  for (const scope of ['default', 'all_people', 'group', 'person', 'face'] as const) {
    const view = fixture();
    const source = {value: .2, scope, target_id: scope === 'default' ? null
      : scope === 'all_people' ? view.binding.asset_sha256 : scope === 'face' ? 'face-a' : scope, overridden: scope === 'face'};
    view.resolved!.operations[LIP_TEXTURE_OPERATION]['/amount'] = source;
    assert.equal(lipTextureReading(view).source, source);
    assert.equal(lipTextureReading(view).value, .2);
    assert.equal(lipTextureReading(view).override, .35);
  }
});

test('missing, stale, conflicted or invalid authority never fabricates a neutral readback', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved = null;}, view => {view.selected_face_id = null;}, view => {view.selected_face_id = 'absent';},
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;},
    view => {view.faces[0].face_ref.analysis_revision = -1;},
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {delete view.resolved!.operations[LIP_TEXTURE_OPERATION];},
    view => {delete view.resolved!.operations[LIP_TEXTURE_OPERATION]['/amount'];},
    view => {view.resolved!.conflicts.push({operation_id: LIP_TEXTURE_OPERATION, parameter_path: '/amount', reason: 'tie', target_ids: ['g1', 'g2']});},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(lipTextureReading(view).value, null);
    assert.equal(lipTextureAccess(view, available, fences).changeDisabled, true);
  }
  for (const value of [-.1, 1.1, NaN, Infinity, '0.4', false]) {
    const view = fixture(); view.resolved!.operations[LIP_TEXTURE_OPERATION]['/amount'].value = value;
    assert.equal(lipTextureReading(view).value, null);
  }
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: 'lnx.lip_makeup.v1', parameter_path: '/brightness', reason: 'tie', target_ids: []});
  assert.equal(lipTextureReading(view).value, .35);
  assert.equal(lipTextureReading(null).value, null); assert.equal(lipTextureReading(undefined).value, null);
});

test('nonzero edits require preview membership in the current target, not just existence of that target', () => {
  const view = fixture();
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...view.faces[1].face_ref}};
  assert.equal(lipTextureTargetReady(view), true); assert.equal(lipTextureSelectionMatches(view), false);
  assert.equal(lipTextureAccess(view, available, fences).changeDisabled, true);
  assert.equal(lipTextureAccess(view, available, fences).resetDisabled, false);
  view.editing_target = {scope: 'group', target_id: 'other', face_ref: null};
  assert.equal(lipTextureSelectionMatches(view), false);
  view.editing_target.target_id = 'group'; assert.equal(lipTextureSelectionMatches(view), true);
  view.groups.group.face_ids = []; assert.equal(lipTextureSelectionMatches(view), false);
  view.editing_target = {scope: 'person', target_id: 'person', face_ref: null};
  assert.equal(lipTextureSelectionMatches(view), true);
  for (const state of ['candidate', 'rejected', 'unresolved'] as const) {
    view.links[0].state = state; assert.equal(lipTextureSelectionMatches(view), false);
  }
  view.links[0].state = 'confirmed';
  for (const confirmation of [null, -1, .5, 3]) {
    view.links[0].confirmation_revision = confirmation; assert.equal(lipTextureSelectionMatches(view), false);
  }
  view.links[0].confirmation_revision = 2;
  view.links[0].face_instance_id = 'face-b'; assert.equal(lipTextureSelectionMatches(view), false);
});

test('dedicated readiness is not proof of usable anatomy, support admission or a changed photograph', () => {
  assert.deepEqual(lipTextureReadiness(available), {available: true});
  assert.deepEqual(lipTextureReadiness({lip_texture_available: false, lip_texture_reason: 'ABI unavailable'}),
    {available: false, reason: 'ABI unavailable'});
  for (const cap of [null, undefined, {}, {lip_makeup_protocol: 1}, {skin_texture_available: true}]) {
    assert.equal(lipTextureReadiness(cap as {} | null | undefined).available, false);
    assert.equal(lipTextureAccess(fixture(), cap as {} | null | undefined, fences).changeDisabled, true);
    assert.equal(lipTextureAccess(fixture(), cap as {} | null | undefined, fences).resetDisabled, false);
  }
  for (const status of ['unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = status;
    assert.equal(lipTextureAccess(view, available, fences).changeDisabled, true);
    assert.equal(lipTextureAccess(view, available, fences).resetDisabled, false);
  }
  const view = fixture(); view.faces[0].enabled = false;
  assert.equal(lipTextureAccess(view, available, fences).changeDisabled, true);
  assert.equal(lipTextureAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('neutral recovery survives missing core, readback and anatomy while retaining valid scope ownership', () => {
  const view = fixture(); view.resolved = null; view.selected_face_id = null;
  view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved';
  view.faces[0].face_ref.analysis_revision = 0; view.editing_target!.face_ref!.analysis_revision = 0;
  assert.equal(lipTextureTargetReady(view), true);
  assert.equal(lipTextureAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  for (const scope of ['group', 'person', 'all_people'] as const) {
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    view.faces = [];
    assert.equal(lipTextureTargetReady(view), true);
    assert.equal(lipTextureAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  }
});

test('both normal edits and recovery retain source, owner, revision and concurrent-work fences', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;}, view => {view.faces = [];},
    view => {view.editing_target!.target_id = 'absent';}, view => {view.editing_target!.face_ref = null;},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.face_ref!.asset_sha256 = 'b'.repeat(64);},
    view => {view.editing_target = {scope: 'all_people', target_id: 'b'.repeat(64), face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.editing_target = {scope: 'person', target_id: 'person', face_ref: {...view.faces[0].face_ref}};},
  ];
  for (const scope of ['group', 'person'] as const) for (const id of ['', 'absent', 'toString', '__proto__']) {
    changes.push(view => {view.editing_target = {scope, target_id: id, face_ref: null};});
  }
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(lipTextureTargetReady(view), false);
    assert.equal(lipTextureAccess(view, null, {...fences, faceOk: false}).resetDisabled, true);
    assert.equal(lipTextureAccess(view, available, fences).changeDisabled, true);
  }
  for (const patch of [{enabled: false}, {pending: true}, {uncertain: true}, {externalBusy: true}]) {
    const access = lipTextureAccess(fixture(), available, {...fences, ...patch});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
});

test('source, target, memberships, authority and refusals invalidate input bindings without graph mutations', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_epoch = 'new';}, view => {view.binding.document_id = 'new';},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = 'face-b';}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.groups.group.face_ids = [];}, view => {delete view.persons.person;}, view => {view.links = [];},
    view => {view.resolved!.operations[LIP_TEXTURE_OPERATION]['/amount'].value = .4;},
    view => {view.resolved!.operations[LIP_TEXTURE_OPERATION]['/amount'].scope = 'group';},
    view => {view.editing_overrides[LIP_TEXTURE_OPERATION]['/amount'] = .9;},
    view => {view.resolved!.conflicts.push({operation_id: LIP_TEXTURE_OPERATION, parameter_path: '/amount', reason: 'tie', target_ids: []});},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'support unavailable'}];},
  ];
  for (const change of changes) {const view = fixture(), key = lipTextureBindingKey(view); change(view);
    assert.notEqual(lipTextureBindingKey(view), key);
  }
  const view = fixture(), before = JSON.stringify(view);
  lipTextureAccess(view, available, fences); lipTextureReading(view); lipTextureBindingKey(view);
  lipTexturePatch(.5); lipTextureResetPatches(); checkLipTexture(neutralLipTexture());
  assert.equal(JSON.stringify(view), before);
  assert.equal(lipTextureBindingKey(null), 'unavailable');
});
