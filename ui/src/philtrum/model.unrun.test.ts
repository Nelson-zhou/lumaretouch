// AUTHORED / UNRUN. Imports, tests, builds, type checks, runtime and real-photo acceptance were NOT executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {PHILTRUM_OPERATION, PHILTRUM_CONTROL_ID, PHILTRUM_CONTROL_PATH, PHILTRUM_SOURCE,
  PHILTRUM_FROZEN_SOURCE, checkPhiltrum, neutralPhiltrum, philtrumReadiness, philtrumReading,
  philtrumTargetReady, philtrumAccess, philtrumBindingKey, philtrumPatch, philtrumResetPatches,
  parsePhiltrumChoice, type PhiltrumFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [PHILTRUM_OPERATION]: {'/amount': {value: .45, scope: 'group', target_id: 'group', overridden: false}},
    }}};
}
const fences: PhiltrumFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {philtrum_available: true};

test('exact philtrum identity and strict versioned signed amount do not alias neighboring operations', () => {
  assert.equal(PHILTRUM_OPERATION, 'lnx.philtrum.v1');
  assert.equal(PHILTRUM_CONTROL_ID, 'LNX-REF-PC-32466-C-2605502c27');
  assert.equal(PHILTRUM_CONTROL_PATH, '脸型/人中');
  assert.equal(PHILTRUM_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(PHILTRUM_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(neutralPhiltrum(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, -.01, 0, .01, .5, 1]) {
    assert.deepEqual(checkPhiltrum({version: 1, amount}), {version: 1, amount});
    assert.deepEqual(philtrumPatch(amount), {operation_id: 'lnx.philtrum.v1', parameter_path: '/amount', unset: false, value: amount});
  }
  for (const amount of [-1.001, 1.001, NaN, Infinity, -Infinity, '0', null, true, false, {}, undefined]) {
    assert.throws(() => checkPhiltrum({version: 1, amount}));
    assert.throws(() => philtrumPatch(amount as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {amount: 0}, {version: 2, amount: 0},
    {version: true, amount: 0}, {version: '1', amount: 0}, {version: 1, amount: 0, linked: true},
    {version: 1, amount: 0, left: 0, right: 0}, {version: 1, amount: 0, mouth_vertical: 0},
    {version: 1, amount: 0, mid_face: 0}, {version: 1, amount: 0, lower_face: 0},
    {version: 1, amount: 0, chin_length: 0}, {version: 1, amount: 0, clinical_length: 1}]) {
    assert.throws(() => checkPhiltrum(recipe));
  }
});

test('only the dedicated capability enables nonzero edits, but neutral reset remains possible without it', () => {
  assert.deepEqual(philtrumReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {philtrum_available: false},
    {mid_face_available: true}, {lower_face_available: true}, {chin_length_available: true}, {mouth_shape_available: true}]) {
    assert.equal(philtrumReadiness(capability as Parameters<typeof philtrumReadiness>[0]).available, false);
  }
  assert.deepEqual(philtrumReadiness({philtrum_available: false, philtrum_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(philtrumAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(philtrumAccess(fixture(), {}, fences).resetDisabled, false);
});

test('selected actual amount/provenance and target-owned explicit amount remain separate', () => {
  const view = fixture();
  assert.equal(philtrumReading(view).value, .45);
  assert.equal(philtrumReading(view).source?.scope, 'group');
  assert.equal(philtrumReading(view).source?.target_id, 'group');
  assert.equal(philtrumReading(view).overridePresent, false);
  assert.equal(philtrumAccess(view, available, fences).editValue, .45);
  view.editing_overrides[PHILTRUM_OPERATION] = {'/amount': -.2};
  assert.equal(philtrumReading(view).value, .45);
  assert.equal(philtrumReading(view).override, -.2);
  assert.equal(philtrumAccess(view, available, fences).editValue, -.2);
  for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
    view.resolved!.operations[PHILTRUM_OPERATION]['/amount'].value = value;
    assert.equal(philtrumReading(view).value, null);
    assert.equal(philtrumAccess(view, available, fences).changeDisabled, true);
    assert.equal(philtrumAccess(view, available, fences).resetDisabled, false);
  }
});

test('all-people, group and person edits use their own explicit amount or a deliberate blank choice', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(philtrumTargetReady(view), true);
    let access = philtrumAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, null);
    assert.equal(access.changeDisabled, false);
    view.editing_overrides[PHILTRUM_OPERATION] = {'/amount': -.65};
    access = philtrumAccess(view, available, fences);
    assert.equal(access.reading.value, .45);
    assert.equal(access.editValue, -.65);
    view.resolved!.operations[PHILTRUM_OPERATION]['/amount'].value = .1;
    assert.equal(philtrumAccess(view, available, fences).editValue, -.65);
    view.editing_overrides[PHILTRUM_OPERATION]['/amount'] = 'bad';
    access = philtrumAccess(view, available, fences);
    assert.equal(access.editValue, null);
    assert.equal(access.reading.overridePresent, true);
    assert.equal(access.reading.override, null);
    assert.equal(access.changeDisabled, false);
  }
});

test('missing, malformed and conflicted effective readings never become a neutral placeholder', () => {
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[PHILTRUM_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[PHILTRUM_OPERATION]['/amount'];},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: PHILTRUM_OPERATION, parameter_path: '/amount', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(philtrumReading(view).value, null);
    assert.equal(philtrumAccess(view, available, fences).changeDisabled, true);
    assert.equal(philtrumAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(philtrumReading(null).value, null);
  assert.equal(philtrumAccess(null, available, fences).resetDisabled, true);
});

test('source, face identity and authoritative revisions fence nonzero writes', () => {
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
    assert.equal(philtrumReading(view).value, null);
    assert.equal(philtrumAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral writes one zero leaf without usable anatomy, native readiness or readable amounts', () => {
  assert.deepEqual(philtrumResetPatches(), [{operation_id: PHILTRUM_OPERATION, parameter_path: '/amount', unset: false, value: 0}]);
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = philtrumAccess(view, {philtrum_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, false);
  }
  const shared = fixture();
  shared.editing_target = {scope: 'all_people', target_id: shared.binding.asset_sha256, face_ref: null};
  shared.faces = []; shared.selected_face_id = null; shared.resolved = null;
  assert.equal(philtrumAccess(shared, {}, {...fences, faceOk: false}).resetDisabled, false);
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = philtrumAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true);
    assert.equal(access.resetDisabled, true);
  }
  assert.match(philtrumAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  assert.equal(philtrumAccess(fixture(), available, {...fences, faceOk: false, faceWhy: 'source face unavailable'}).reason,
    'source face unavailable');
});

test('neutral recovery still requires a valid target, not another source or the preview cursor', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.target_id = 'absent';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: view.faces[0].face_ref};},
    view => {view.binding.document_revision = -1;}, view => {view.association_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(philtrumTargetReady(view), false);
    assert.equal(philtrumAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(philtrumTargetReady(view), true);
  const access = philtrumAccess(view, available, fences);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.editValue, null);
  assert.equal(access.resetDisabled, false);
});

test('bindings invalidate obsolete drafts for source, target, membership, provenance and refusal changes', () => {
  const original = philtrumBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.groups.group.face_ids = [];}, view => {view.groups.group.priority += 1;},
    view => {view.persons.other = {anonymous: true};},
    view => {view.links.push({face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 1});},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[PHILTRUM_OPERATION]['/amount'].value = -.8;},
    view => {view.resolved!.operations[PHILTRUM_OPERATION]['/amount'].scope = 'face';},
    view => {view.resolved!.operations[PHILTRUM_OPERATION]['/amount'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: PHILTRUM_OPERATION, parameter_path: '/amount', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[PHILTRUM_OPERATION] = {'/amount': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'actual source nose/lip gap is too short'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(philtrumBindingKey(view), original);}
  assert.equal(philtrumBindingKey(null), 'unavailable');
});

test('raw signed choice rejects blank, malformed, nonfinite and out-of-range text rather than inventing zero', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const) {
    assert.equal(parsePhiltrumChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999']) {
    assert.equal(parsePhiltrumChoice(text), null);
  }
});

test('new edits and reset neither mutate nor migrate neighboring operations, including prior chin replacement state', () => {
  const view = fixture();
  for (const [operation, path] of [['lnx.deform.v1', '/small_chin'], ['lnx.face_size.v1', '/amount'],
    ['lnx.mid_face.v1', '/amount'], ['lnx.lower_face.v1', '/amount'], ['lnx.chin_length.v1', '/amount'],
    ['lnx.chin_shape.v1', '/left'], ['lnx.mouth_shape.v1', '/vertical'], ['lnx.face_contour.v1', '/jaw/left']]) {
    view.resolved!.operations[operation] = {[path]: {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
    view.editing_overrides[operation] = {[path]: -.2};
  }
  const before = JSON.stringify(view), recipe = neutralPhiltrum(), checked = checkPhiltrum(recipe);
  checked.amount = .7;
  assert.equal(recipe.amount, 0);
  assert.equal(philtrumAccess(view, available, fences).changeDisabled, false);
  philtrumReading(view); philtrumBindingKey(view); philtrumTargetReady(view); philtrumPatch(.2); philtrumResetPatches();
  assert.equal(JSON.stringify(view), before);
  // Engine-owned source and all-target geometry checks still decide whether the proposed composition is supported.
});
