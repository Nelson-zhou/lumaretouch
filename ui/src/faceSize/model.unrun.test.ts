// AUTHORED / UNRUN. No imports, tests, build, type check, runtime or real-photo acceptance have been executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {FACE_SIZE_OPERATION, FACE_SIZE_CONTROL_ID, FACE_SIZE_CONTROL_PATH, FACE_SIZE_SOURCE,
  FACE_SIZE_FROZEN_SOURCE, checkFaceSize, neutralFaceSize, faceSizeLocalScale, faceSizeReadiness,
  faceSizeReading, faceSizeTargetReady, faceSizeAccess, faceSizeBindingKey, faceSizePatch,
  faceSizeResetPatches, parseFaceSizeChoice, type FaceSizeFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [FACE_SIZE_OPERATION]: {'/amount': {value: .45, scope: 'group', target_id: 'group', overridden: false}},
    }}};
}
const fences: FaceSizeFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {face_size_available: true};

test('the exact handbook leaf is a distinct strict one-amount operation, with no bilateral or old aliases', () => {
  assert.equal(FACE_SIZE_OPERATION, 'lnx.face_size.v1');
  assert.equal(FACE_SIZE_CONTROL_ID, 'LNX-REF-PC-32466-C-728fc62cdd');
  assert.equal(FACE_SIZE_CONTROL_PATH, '脸型/小脸');
  assert.equal(FACE_SIZE_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(FACE_SIZE_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(neutralFaceSize(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, -.01, 0, .01, .5, 1]) {
    assert.deepEqual(checkFaceSize({version: 1, amount}), {version: 1, amount});
    assert.deepEqual(faceSizePatch(amount), {operation_id: 'lnx.face_size.v1', parameter_path: '/amount', unset: false, value: amount});
    assert.equal(faceSizeLocalScale(amount), 1 - .06 * amount);
  }
  for (const amount of [-1.001, 1.001, NaN, Infinity, -Infinity, '0', null, true, false, {}, undefined]) {
    assert.throws(() => checkFaceSize({version: 1, amount}));
    assert.throws(() => faceSizePatch(amount as number));
    assert.throws(() => faceSizeLocalScale(amount as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {amount: 0}, {version: 2, amount: 0},
    {version: true, amount: 0}, {version: '1', amount: 0}, {version: 1, amount: 0, linked: true},
    {version: 1, amount: 0, left: 0, right: 0}, {version: 1, amount: 0, slim_face: 0}]) assert.throws(() => checkFaceSize(recipe));
  assert.equal(faceSizeLocalScale(0), 1);
  assert.equal(faceSizeLocalScale(1), .94);
  assert.equal(faceSizeLocalScale(-1), 1.06);
});

test('capability is specifically face size, never borrowed from another geometry or enhancement feature', () => {
  assert.deepEqual(faceSizeReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {face_size_available: false}, {face_contour_available: true}]) {
    assert.equal(faceSizeReadiness(capability as Parameters<typeof faceSizeReadiness>[0]).available, false);
  }
  assert.deepEqual(faceSizeReadiness({face_size_available: false, face_size_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(faceSizeAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(faceSizeAccess(fixture(), {}, fences).resetDisabled, false);
});

test('selected effective value and provenance are authoritative and distinct from target explicit values', () => {
  const view = fixture();
  assert.equal(faceSizeReading(view).value, .45);
  assert.equal(faceSizeReading(view).source?.scope, 'group');
  assert.equal(faceSizeReading(view).source?.target_id, 'group');
  assert.equal(faceSizeReading(view).overridePresent, false);
  assert.equal(faceSizeAccess(view, available, fences).editValue, .45);
  view.editing_overrides[FACE_SIZE_OPERATION] = {'/amount': -.2};
  assert.equal(faceSizeReading(view).value, .45);
  assert.equal(faceSizeReading(view).override, -.2);
  assert.equal(faceSizeAccess(view, available, fences).editValue, -.2);
  for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
    view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'].value = value;
    assert.equal(faceSizeReading(view).value, null);
    assert.equal(faceSizeAccess(view, available, fences).changeDisabled, true);
    assert.equal(faceSizeAccess(view, available, fences).resetDisabled, false);
  }
});

test('shared targets start from their own explicit amount or a blank choice, never selected-face inheritance', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(faceSizeTargetReady(view), true);
    let access = faceSizeAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, null);
    assert.equal(access.changeDisabled, false); // A deliberate new scalar is allowed; no implicit baseline is supplied.
    view.editing_overrides[FACE_SIZE_OPERATION] = {'/amount': -.65};
    access = faceSizeAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, -.65);
    view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'].value = .1;
    assert.equal(faceSizeAccess(view, available, fences).editValue, -.65);
    view.editing_overrides[FACE_SIZE_OPERATION]['/amount'] = 'bad';
    access = faceSizeAccess(view, available, fences);
    assert.equal(access.editValue, null);
    assert.equal(access.reading.overridePresent, true);
    assert.equal(access.reading.override, null);
  }
});

test('unknown and conflicted effective reads never become a neutral value', () => {
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[FACE_SIZE_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'];},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: FACE_SIZE_OPERATION, parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(faceSizeReading(view).value, null);
    assert.equal(faceSizeAccess(view, available, fences).changeDisabled, true);
    assert.equal(faceSizeAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(faceSizeReading(null).value, null);
  assert.equal(faceSizeAccess(null, available, fences).resetDisabled, true);
});

test('source, face and authoritative revision mismatches block nonzero writes', () => {
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
    assert.equal(faceSizeReading(view).value, null);
    assert.equal(faceSizeAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral reset writes one exact zero leaf, remains possible without anatomy or native, but keeps owner fences', () => {
  assert.deepEqual(faceSizeResetPatches(), [{operation_id: FACE_SIZE_OPERATION, parameter_path: '/amount', unset: false, value: 0}]);
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = faceSizeAccess(view, {face_size_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, false);
  }
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = faceSizeAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, true);
  }
  assert.match(faceSizeAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('neutral recovery requires a current owned target, not the preview cursor or a different source', () => {
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
    assert.equal(faceSizeTargetReady(view), false);
    assert.equal(faceSizeAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(faceSizeTargetReady(view), true);
  const access = faceSizeAccess(view, available, fences);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.editValue, null);
  assert.equal(access.resetDisabled, false);
});

test('binding changes invalidate old events and blank shared drafts, including operation/provenance/refusal changes', () => {
  const original = faceSizeBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'].value = -.8;},
    view => {view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'].scope = 'face';},
    view => {view.resolved!.operations[FACE_SIZE_OPERATION]['/amount'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: FACE_SIZE_OPERATION, parameter_path: '/amount', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[FACE_SIZE_OPERATION] = {'/amount': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'actual source support is clipped'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(faceSizeBindingKey(view), original);}
  assert.equal(faceSizeBindingKey(null), 'unavailable');
});

test('explicit numeric choice accepts the signed range, not blank, malformed, out-of-range or non-finite input', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const) {
    assert.equal(parseFaceSizeChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999']) {
    assert.equal(parseFaceSizeChoice(text), null);
  }
});

test('UI does not infer composition compatibility or change legacy operations, preset values or canonical state', () => {
  const view = fixture();
  view.resolved!.operations['lnx.deform.v1'] = {'/slim_face': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
  view.resolved!.operations['lnx.face_contour.v1'] = {'/jaw/left': {value: .6, scope: 'face', target_id: 'face-a', overridden: true}};
  const before = JSON.stringify(view), recipe = neutralFaceSize(), checked = checkFaceSize(recipe);
  checked.amount = .7;
  assert.equal(recipe.amount, 0);
  assert.equal(faceSizeAccess(view, available, fences).changeDisabled, false); // Only engine evidence can accept/refuse actual composition.
  faceSizeReading(view); faceSizeBindingKey(view); faceSizeTargetReady(view); faceSizePatch(.2); faceSizeResetPatches();
  assert.equal(JSON.stringify(view), before);
});
