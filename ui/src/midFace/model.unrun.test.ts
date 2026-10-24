// AUTHORED / UNRUN. Imports, tests, build, type check, runtime and real-photo acceptance were NOT executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {MID_FACE_OPERATION, MID_FACE_CONTROL_ID, MID_FACE_CONTROL_PATH, MID_FACE_SOURCE,
  MID_FACE_FROZEN_SOURCE, checkMidFace, neutralMidFace, midFaceLocalEndpointRatio, midFaceReadiness,
  midFaceReading, midFaceTargetReady, midFaceAccess, midFaceBindingKey, midFacePatch,
  midFaceResetPatches, parseMidFaceChoice, type MidFaceFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [MID_FACE_OPERATION]: {'/amount': {value: .45, scope: 'group', target_id: 'group', overridden: false}},
    }}};
}
const fences: MidFaceFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {mid_face_available: true};

test('exact mid-face leaf is a strict distinct signed amount, not a lower-face, whole-face or chin alias', () => {
  assert.equal(MID_FACE_OPERATION, 'lnx.mid_face.v1');
  assert.equal(MID_FACE_CONTROL_ID, 'LNX-REF-PC-32466-C-ea67c9d99f');
  assert.equal(MID_FACE_CONTROL_PATH, '脸型/中庭');
  assert.equal(MID_FACE_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(MID_FACE_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(neutralMidFace(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, -.01, 0, .01, .5, 1]) {
    assert.deepEqual(checkMidFace({version: 1, amount}), {version: 1, amount});
    assert.deepEqual(midFacePatch(amount), {operation_id: 'lnx.mid_face.v1', parameter_path: '/amount', unset: false, value: amount});
    assert.equal(midFaceLocalEndpointRatio(amount), 1 + .08 * amount);
  }
  for (const amount of [-1.001, 1.001, NaN, Infinity, -Infinity, '0', null, true, false, {}, undefined]) {
    assert.throws(() => checkMidFace({version: 1, amount}));
    assert.throws(() => midFacePatch(amount as number));
    assert.throws(() => midFaceLocalEndpointRatio(amount as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {amount: 0}, {version: 2, amount: 0},
    {version: true, amount: 0}, {version: '1', amount: 0}, {version: 1, amount: 0, linked: true},
    {version: 1, amount: 0, left: 0, right: 0}, {version: 1, amount: 0, small_chin: 0},
    {version: 1, amount: 0, face_size: 0}, {version: 1, amount: 0, short_face: 0},
    {version: 1, amount: 0, lower_face: 0}, {version: 1, amount: 0, preserve_nose: true}]) assert.throws(() => checkMidFace(recipe));
  assert.equal(midFaceLocalEndpointRatio(0), 1);
  assert.equal(midFaceLocalEndpointRatio(1), 1.08);
  assert.equal(midFaceLocalEndpointRatio(-1), .92);
  // This UI formula describes endpoints only. It does not prove warp quality or uniform scaling.
});

test('only dedicated mid-face capability enables nonzero edits; neutral reset does not need it', () => {
  assert.deepEqual(midFaceReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {mid_face_available: false},
    {lower_face_available: true}, {face_size_available: true}, {face_contour_available: true}]) {
    assert.equal(midFaceReadiness(capability as Parameters<typeof midFaceReadiness>[0]).available, false);
  }
  assert.deepEqual(midFaceReadiness({mid_face_available: false, mid_face_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(midFaceAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(midFaceAccess(fixture(), {}, fences).resetDisabled, false);
});

test('selected effective value and provenance stay separate from current target explicit values', () => {
  const view = fixture();
  assert.equal(midFaceReading(view).value, .45);
  assert.equal(midFaceReading(view).source?.scope, 'group');
  assert.equal(midFaceReading(view).source?.target_id, 'group');
  assert.equal(midFaceReading(view).overridePresent, false);
  assert.equal(midFaceAccess(view, available, fences).editValue, .45);
  view.editing_overrides[MID_FACE_OPERATION] = {'/amount': -.2};
  assert.equal(midFaceReading(view).value, .45);
  assert.equal(midFaceReading(view).override, -.2);
  assert.equal(midFaceAccess(view, available, fences).editValue, -.2);
  for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
    view.resolved!.operations[MID_FACE_OPERATION]['/amount'].value = value;
    assert.equal(midFaceReading(view).value, null);
    assert.equal(midFaceAccess(view, available, fences).changeDisabled, true);
    assert.equal(midFaceAccess(view, available, fences).resetDisabled, false);
  }
});

test('shared scopes use their own explicit amount or a deliberate empty choice, never selected-face inheritance', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(midFaceTargetReady(view), true);
    let access = midFaceAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, null);
    assert.equal(access.changeDisabled, false);
    view.editing_overrides[MID_FACE_OPERATION] = {'/amount': -.65};
    access = midFaceAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, -.65);
    view.resolved!.operations[MID_FACE_OPERATION]['/amount'].value = .1;
    assert.equal(midFaceAccess(view, available, fences).editValue, -.65);
    view.editing_overrides[MID_FACE_OPERATION]['/amount'] = 'bad';
    access = midFaceAccess(view, available, fences);
    assert.equal(access.editValue, null);
    assert.equal(access.reading.overridePresent, true);
    assert.equal(access.reading.override, null);
  }
});

test('unknown or conflicted effective reads never become a neutral placeholder', () => {
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[MID_FACE_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[MID_FACE_OPERATION]['/amount'];},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: MID_FACE_OPERATION, parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(midFaceReading(view).value, null);
    assert.equal(midFaceAccess(view, available, fences).changeDisabled, true);
    assert.equal(midFaceAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(midFaceReading(null).value, null);
  assert.equal(midFaceAccess(null, available, fences).resetDisabled, true);
});

test('current source, face reference and all authoritative revisions are required for nonzero writes', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = -1;},
    view => {view.revision = NaN;}, view => {view.association_revision = .5;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';},
    view => {view.resolved!.face_ref.asset_sha256 = 'other';},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.faces[0].face_ref.asset_sha256 = 'other';},
    view => {view.faces[0].face_ref.analysis_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(midFaceReading(view).value, null);
    assert.equal(midFaceAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral writes exactly one zero leaf without native, readable amount or anatomy, while preserving owner fences', () => {
  assert.deepEqual(midFaceResetPatches(), [{operation_id: MID_FACE_OPERATION, parameter_path: '/amount', unset: false, value: 0}]);
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = midFaceAccess(view, {mid_face_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, false);
  }
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = midFaceAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, true);
  }
  assert.match(midFaceAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  assert.equal(midFaceAccess(fixture(), available, {...fences, faceOk: false, faceWhy: 'source face unavailable'}).reason,
    'source face unavailable');
});

test('neutral recovery requires a valid owned target, not the preview cursor or another source', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.target_id = 'absent';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
    view => {view.binding.document_revision = -1;}, view => {view.association_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(midFaceTargetReady(view), false);
    assert.equal(midFaceAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(midFaceTargetReady(view), true);
  const access = midFaceAccess(view, available, fences);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.editValue, null);
  assert.equal(access.resetDisabled, false);
});

test('binding changes discard obsolete callbacks and blank shared drafts, including authority and refusal changes', () => {
  const original = midFaceBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[MID_FACE_OPERATION]['/amount'].value = -.8;},
    view => {view.resolved!.operations[MID_FACE_OPERATION]['/amount'].scope = 'face';},
    view => {view.resolved!.operations[MID_FACE_OPERATION]['/amount'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: MID_FACE_OPERATION, parameter_path: '/amount', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[MID_FACE_OPERATION] = {'/amount': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'actual source support is clipped'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(midFaceBindingKey(view), original);}
  assert.equal(midFaceBindingKey(null), 'unavailable');
});

test('deliberate signed numeric choice rejects blank, malformed, out-of-range and nonfinite text', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const) {
    assert.equal(parseMidFaceChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999']) {
    assert.equal(parseMidFaceChoice(text), null);
  }
});

test('UI preserves earlier operations and state, and delegates actual geometry coexistence to the engine', () => {
  const view = fixture();
  for (const [operation, path] of [['lnx.deform.v1', '/small_chin'], ['lnx.face_size.v1', '/amount'], ['lnx.lower_face.v1', '/amount'],
    ['lnx.face_contour.v1', '/jaw/left']]) {
    view.resolved!.operations[operation] = {[path]: {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
  }
  const before = JSON.stringify(view), recipe = neutralMidFace(), checked = checkMidFace(recipe);
  checked.amount = .7;
  assert.equal(recipe.amount, 0);
  assert.equal(midFaceAccess(view, available, fences).changeDisabled, false);
  midFaceReading(view); midFaceBindingKey(view); midFaceTargetReady(view); midFacePatch(.2); midFaceResetPatches();
  assert.equal(JSON.stringify(view), before);
});
