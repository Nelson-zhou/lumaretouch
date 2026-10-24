// AUTHORED / UNRUN. Imports, tests, build, type check, runtime and real-photo acceptance were NOT executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {LOWER_FACE_OPERATION, LOWER_FACE_CONTROL_ID, LOWER_FACE_CONTROL_PATH, LOWER_FACE_SOURCE,
  LOWER_FACE_FROZEN_SOURCE, checkLowerFace, neutralLowerFace, lowerFaceLocalEndpointRatio, lowerFaceReadiness,
  lowerFaceReading, lowerFaceTargetReady, lowerFaceAccess, lowerFaceBindingKey, lowerFacePatch,
  lowerFaceResetPatches, parseLowerFaceChoice, type LowerFaceFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [LOWER_FACE_OPERATION]: {'/amount': {value: .45, scope: 'group', target_id: 'group', overridden: false}},
    }}};
}
const fences: LowerFaceFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {lower_face_available: true};

test('exact lower-third leaf is a strict distinct signed amount, not a whole-face or chin alias', () => {
  assert.equal(LOWER_FACE_OPERATION, 'lnx.lower_face.v1');
  assert.equal(LOWER_FACE_CONTROL_ID, 'LNX-REF-PC-32466-C-1ae8316994');
  assert.equal(LOWER_FACE_CONTROL_PATH, '脸型/下庭');
  assert.equal(LOWER_FACE_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(LOWER_FACE_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(neutralLowerFace(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, -.01, 0, .01, .5, 1]) {
    assert.deepEqual(checkLowerFace({version: 1, amount}), {version: 1, amount});
    assert.deepEqual(lowerFacePatch(amount), {operation_id: 'lnx.lower_face.v1', parameter_path: '/amount', unset: false, value: amount});
    assert.equal(lowerFaceLocalEndpointRatio(amount), 1 + .08 * amount);
  }
  for (const amount of [-1.001, 1.001, NaN, Infinity, -Infinity, '0', null, true, false, {}, undefined]) {
    assert.throws(() => checkLowerFace({version: 1, amount}));
    assert.throws(() => lowerFacePatch(amount as number));
    assert.throws(() => lowerFaceLocalEndpointRatio(amount as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {amount: 0}, {version: 2, amount: 0},
    {version: true, amount: 0}, {version: '1', amount: 0}, {version: 1, amount: 0, linked: true},
    {version: 1, amount: 0, left: 0, right: 0}, {version: 1, amount: 0, small_chin: 0},
    {version: 1, amount: 0, face_size: 0}, {version: 1, amount: 0, short_face: 0}]) assert.throws(() => checkLowerFace(recipe));
  assert.equal(lowerFaceLocalEndpointRatio(0), 1);
  assert.equal(lowerFaceLocalEndpointRatio(1), 1.08);
  assert.equal(lowerFaceLocalEndpointRatio(-1), .92);
  // This UI formula describes endpoints only. It does not prove warp quality or uniform scaling.
});

test('only dedicated lower-face capability enables nonzero edits; neutral reset does not need it', () => {
  assert.deepEqual(lowerFaceReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {lower_face_available: false},
    {face_size_available: true}, {face_contour_available: true}]) {
    assert.equal(lowerFaceReadiness(capability as Parameters<typeof lowerFaceReadiness>[0]).available, false);
  }
  assert.deepEqual(lowerFaceReadiness({lower_face_available: false, lower_face_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(lowerFaceAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(lowerFaceAccess(fixture(), {}, fences).resetDisabled, false);
});

test('selected effective value and provenance stay separate from current target explicit values', () => {
  const view = fixture();
  assert.equal(lowerFaceReading(view).value, .45);
  assert.equal(lowerFaceReading(view).source?.scope, 'group');
  assert.equal(lowerFaceReading(view).source?.target_id, 'group');
  assert.equal(lowerFaceReading(view).overridePresent, false);
  assert.equal(lowerFaceAccess(view, available, fences).editValue, .45);
  view.editing_overrides[LOWER_FACE_OPERATION] = {'/amount': -.2};
  assert.equal(lowerFaceReading(view).value, .45);
  assert.equal(lowerFaceReading(view).override, -.2);
  assert.equal(lowerFaceAccess(view, available, fences).editValue, -.2);
  for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
    view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'].value = value;
    assert.equal(lowerFaceReading(view).value, null);
    assert.equal(lowerFaceAccess(view, available, fences).changeDisabled, true);
    assert.equal(lowerFaceAccess(view, available, fences).resetDisabled, false);
  }
});

test('shared scopes use their own explicit amount or a deliberate empty choice, never selected-face inheritance', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(lowerFaceTargetReady(view), true);
    let access = lowerFaceAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, null);
    assert.equal(access.changeDisabled, false);
    view.editing_overrides[LOWER_FACE_OPERATION] = {'/amount': -.65};
    access = lowerFaceAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, -.65);
    view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'].value = .1;
    assert.equal(lowerFaceAccess(view, available, fences).editValue, -.65);
    view.editing_overrides[LOWER_FACE_OPERATION]['/amount'] = 'bad';
    access = lowerFaceAccess(view, available, fences);
    assert.equal(access.editValue, null);
    assert.equal(access.reading.overridePresent, true);
    assert.equal(access.reading.override, null);
  }
});

test('unknown or conflicted effective reads never become a neutral placeholder', () => {
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[LOWER_FACE_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'];},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: LOWER_FACE_OPERATION, parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(lowerFaceReading(view).value, null);
    assert.equal(lowerFaceAccess(view, available, fences).changeDisabled, true);
    assert.equal(lowerFaceAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(lowerFaceReading(null).value, null);
  assert.equal(lowerFaceAccess(null, available, fences).resetDisabled, true);
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
    assert.equal(lowerFaceReading(view).value, null);
    assert.equal(lowerFaceAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral writes exactly one zero leaf without native, readable amount or anatomy, while preserving owner fences', () => {
  assert.deepEqual(lowerFaceResetPatches(), [{operation_id: LOWER_FACE_OPERATION, parameter_path: '/amount', unset: false, value: 0}]);
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = lowerFaceAccess(view, {lower_face_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, false);
  }
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = lowerFaceAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, true);
  }
  assert.match(lowerFaceAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  assert.equal(lowerFaceAccess(fixture(), available, {...fences, faceOk: false, faceWhy: 'source face unavailable'}).reason,
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
    assert.equal(lowerFaceTargetReady(view), false);
    assert.equal(lowerFaceAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(lowerFaceTargetReady(view), true);
  const access = lowerFaceAccess(view, available, fences);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.editValue, null);
  assert.equal(access.resetDisabled, false);
});

test('binding changes discard obsolete callbacks and blank shared drafts, including authority and refusal changes', () => {
  const original = lowerFaceBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'].value = -.8;},
    view => {view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'].scope = 'face';},
    view => {view.resolved!.operations[LOWER_FACE_OPERATION]['/amount'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: LOWER_FACE_OPERATION, parameter_path: '/amount', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[LOWER_FACE_OPERATION] = {'/amount': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'actual source support is clipped'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(lowerFaceBindingKey(view), original);}
  assert.equal(lowerFaceBindingKey(null), 'unavailable');
});

test('deliberate signed numeric choice rejects blank, malformed, out-of-range and nonfinite text', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const) {
    assert.equal(parseLowerFaceChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999']) {
    assert.equal(parseLowerFaceChoice(text), null);
  }
});

test('UI preserves earlier operations and state, and delegates actual geometry coexistence to the engine', () => {
  const view = fixture();
  for (const [operation, path] of [['lnx.deform.v1', '/small_chin'], ['lnx.face_size.v1', '/amount'],
    ['lnx.face_contour.v1', '/jaw/left']]) {
    view.resolved!.operations[operation] = {[path]: {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
  }
  const before = JSON.stringify(view), recipe = neutralLowerFace(), checked = checkLowerFace(recipe);
  checked.amount = .7;
  assert.equal(recipe.amount, 0);
  assert.equal(lowerFaceAccess(view, available, fences).changeDisabled, false);
  lowerFaceReading(view); lowerFaceBindingKey(view); lowerFaceTargetReady(view); lowerFacePatch(.2); lowerFaceResetPatches();
  assert.equal(JSON.stringify(view), before);
});
