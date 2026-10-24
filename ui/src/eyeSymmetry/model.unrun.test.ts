// AUTHORED / UNRUN. No imports, execution, tests, builds, type checks, inference or real-photo acceptance were performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {EYE_SYMMETRY_OPERATION, EYE_SYMMETRY_CONTROL_IDS, EYE_SYMMETRY_CONTROL_PATHS, EYE_SYMMETRY_SOURCE,
  EYE_SYMMETRY_REFERENCE_LABELS, checkEyeSymmetry, neutralEyeSymmetry, eyeSymmetryNeutral, eyeSymmetryReadiness,
  eyeSymmetryReading, eyeSymmetryAccess, eyeSymmetryTargetReady, eyeSymmetryBindingKey, eyeSymmetryPatch,
  eyeSymmetrySizePatches, eyeSymmetryResetPatches, parseEyeSymmetryChoice, validEyeSymmetryReference,
  type EyeSymmetryFences, type EyeSymmetryKey} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'original', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {}, resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [],
      operations: {[EYE_SYMMETRY_OPERATION]: {
        '/horizontal': {value: .45, scope: 'group', target_id: 'group', overridden: false},
        '/size': {value: .7, scope: 'person', target_id: 'person', overridden: false},
        '/reference': {value: 'right', scope: 'all_people', target_id: face_ref.asset_sha256, overridden: false},
      }}}};
}
const fences: EyeSymmetryFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {eye_symmetry_available: true};
const keys = ['horizontal', 'size', 'reference'] as const;

test('exact four PC-32470 identities and strict three-leaf recipe remain independent from eye shape', () => {
  assert.equal(EYE_SYMMETRY_OPERATION, 'lnx.eye_symmetry.v1');
  assert.equal(EYE_SYMMETRY_SOURCE, 'https://www.pixcakeai.com/guide/32470');
  assert.deepEqual(EYE_SYMMETRY_CONTROL_IDS, {family: 'LNX-REF-PC-32470-C-2745ac86f5',
    horizontal: 'LNX-REF-PC-32470-C-a86e5c0175', size: 'LNX-REF-PC-32470-C-4601eb7797', reference: 'LNX-REF-PC-32470-C-118aa67e04'});
  assert.deepEqual(EYE_SYMMETRY_CONTROL_PATHS, {family: '眼睛对称', horizontal: '眼睛对称/水平对称', size: '眼睛对称/大小对称', reference: '眼睛对称/参考眼选择'});
  assert.deepEqual(neutralEyeSymmetry(), {version: 1, horizontal: 0, size: 0, reference: 'auto'});
  for (const horizontal of [0, .2, 1]) for (const size of [0, .7, 1]) for (const reference of ['auto', 'left', 'right'] as const) {
    assert.deepEqual(checkEyeSymmetry({version: 1, horizontal, size, reference}), {version: 1, horizontal, size, reference});
    assert.equal(eyeSymmetryNeutral({version: 1, horizontal, size, reference}), horizontal === 0 && size === 0);
  }
  for (const bad of [-.01, 1.01, NaN, Infinity, -Infinity, '0', true, null, undefined]) {
    assert.throws(() => checkEyeSymmetry({...neutralEyeSymmetry(), horizontal: bad}));
    assert.throws(() => checkEyeSymmetry({...neutralEyeSymmetry(), size: bad}));
    assert.throws(() => eyeSymmetryPatch('horizontal', bad as number));
    assert.throws(() => eyeSymmetryPatch('size', bad as number));
  }
  for (const bad of ['', 'larger', 'screen-left', 'LEFT', 0, 1, true, null, undefined]) {
    assert.equal(validEyeSymmetryReference(bad), false);
    assert.throws(() => checkEyeSymmetry({...neutralEyeSymmetry(), reference: bad}));
    assert.throws(() => eyeSymmetryPatch('reference', bad as 'auto'));
  }
  for (const recipe of [null, [], {}, {version: 1, horizontal: 0, size: 0}, {...neutralEyeSymmetry(), version: 2},
    {...neutralEyeSymmetry(), version: true}, {...neutralEyeSymmetry(), linked: true}, {...neutralEyeSymmetry(), amount: 0},
    {...neutralEyeSymmetry(), left: 0}, {...neutralEyeSymmetry(), reference_width: 20}]) assert.throws(() => checkEyeSymmetry(recipe));
  assert.throws(() => eyeSymmetryPatch('other' as EyeSymmetryKey, 0));
  assert.equal(EYE_SYMMETRY_REFERENCE_LABELS.left, '人物左眼');
  assert.equal(EYE_SYMMETRY_REFERENCE_LABELS.right, '人物右眼');
});

test('each selected-face effective value keeps its own provenance while explicit target values stay separate', () => {
  const view = fixture();
  assert.equal(eyeSymmetryReading(view, 'horizontal').value, .45);
  assert.equal(eyeSymmetryReading(view, 'horizontal').source?.scope, 'group');
  assert.equal(eyeSymmetryReading(view, 'size').value, .7);
  assert.equal(eyeSymmetryReading(view, 'size').source?.scope, 'person');
  assert.equal(eyeSymmetryReading(view, 'reference').value, 'right');
  assert.equal(eyeSymmetryAccess(view, 'reference', available, fences).editValue, 'right');
  view.editing_overrides[EYE_SYMMETRY_OPERATION] = {'/horizontal': .1, '/size': .2, '/reference': 'left'};
  assert.equal(eyeSymmetryAccess(view, 'horizontal', available, fences).editValue, .1);
  assert.equal(eyeSymmetryAccess(view, 'size', available, fences).editValue, .2);
  assert.equal(eyeSymmetryAccess(view, 'reference', available, fences).editValue, 'left');
  assert.equal(eyeSymmetryReading(view, 'reference').value, 'right');
});

test('all shared targets start each missing intent blank, including reference instead of guessing auto', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    for (const key of keys) {
      assert.equal(eyeSymmetryAccess(view, key, available, fences).editValue, null);
      assert.equal(eyeSymmetryAccess(view, key, available, fences).changeDisabled, false);
    }
    view.editing_overrides[EYE_SYMMETRY_OPERATION] = {'/size': .3, '/reference': 'auto'};
    assert.equal(eyeSymmetryAccess(view, 'size', available, fences).editValue, .3);
    assert.equal(eyeSymmetryAccess(view, 'reference', available, fences).editValue, 'auto');
    assert.equal(eyeSymmetryAccess(view, 'horizontal', available, fences).editValue, null);
    view.resolved!.operations[EYE_SYMMETRY_OPERATION]['/size'].value = .9;
    view.resolved!.operations[EYE_SYMMETRY_OPERATION]['/reference'].value = 'left';
    assert.equal(eyeSymmetryAccess(view, 'size', available, fences).editValue, .3);
    assert.equal(eyeSymmetryAccess(view, 'reference', available, fences).editValue, 'auto');
    view.editing_overrides[EYE_SYMMETRY_OPERATION]['/reference'] = 'bad';
    const reading = eyeSymmetryReading(view, 'reference');
    assert.equal(reading.override, null); assert.equal(reading.overridePresent, true);
    assert.equal(eyeSymmetryAccess(view, 'reference', available, fences).editValue, null);
  }
});

test('missing, malformed and conflicted authority does not become numeric zero or auto', () => {
  for (const key of keys) {
    for (const change of [
      (view: PeopleView) => {view.resolved = null;}, (view: PeopleView) => {view.selected_face_id = null;},
      (view: PeopleView) => {delete view.resolved!.operations[EYE_SYMMETRY_OPERATION];},
      (view: PeopleView) => {delete view.resolved!.operations[EYE_SYMMETRY_OPERATION][`/${key}`];},
      (view: PeopleView) => {view.resolved!.operations[EYE_SYMMETRY_OPERATION][`/${key}`].value = 'invalid';},
      (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: EYE_SYMMETRY_OPERATION,
        parameter_path: '/reference', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
    ]) {
      const view = fixture(); change(view);
      assert.equal(eyeSymmetryReading(view, key).value, null);
      assert.equal(eyeSymmetryAccess(view, key, available, fences).changeDisabled, true);
      assert.equal(eyeSymmetryAccess(view, key, available, fences).resetDisabled, false);
    }
  }
  assert.equal(eyeSymmetryAccess(null, 'size', available, fences).resetDisabled, true);
});

test('original and returned composite use matching source and exact revision authority, never a selected-person shortcut', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = -1;},
    view => {view.revision = NaN;}, view => {view.association_revision = .5;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';},
    view => {view.resolved!.face_ref.asset_sha256 = 'old-source';},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.faces[0].face_ref.asset_sha256 = 'old-source';},
    view => {view.faces[0].face_ref.analysis_revision = Infinity;},
  ];
  for (const change of changes) for (const key of keys) {
    const view = fixture(); change(view);
    assert.equal(eyeSymmetryReading(view, key).value, null);
    assert.equal(eyeSymmetryAccess(view, key, available, fences).changeDisabled, true);
  }
  const derived = fixture(); derived.binding = {...derived.binding, document_id: 'returned-composite', document_epoch: 'new-epoch', asset_sha256: 'b'.repeat(64)};
  for (const key of keys) assert.equal(eyeSymmetryAccess(derived, key, available, fences).changeDisabled, true);
  derived.faces[0].face_ref.asset_sha256 = derived.binding.asset_sha256;
  derived.resolved!.face_ref = {...derived.faces[0].face_ref};
  derived.editing_target!.face_ref = {...derived.faces[0].face_ref};
  for (const key of keys) assert.equal(eyeSymmetryAccess(derived, key, available, fences).changeDisabled, false);
});

test('dedicated capability gates edits; atomic neutral recovery needs no native or eye evidence', () => {
  assert.deepEqual(eyeSymmetryReadiness(available), {available: true});
  assert.deepEqual(eyeSymmetryReadiness({eye_symmetry_available: false, eye_symmetry_reason: 'missing core'}), {available: false, reason: 'missing core'});
  for (const capability of [null, undefined, {}, {eye_symmetry_available: false}, {eye_shape_protocol: 2}]) {
    assert.equal(eyeSymmetryReadiness(capability as Parameters<typeof eyeSymmetryReadiness>[0]).available, false);
  }
  for (const analysis_status of ['verified', 'synthetic', 'unresolved'] as const) {
    const view = fixture(); view.faces[0].enabled = false; view.faces[0].analysis_status = analysis_status; view.resolved = null;
    for (const key of keys) {
      const access = eyeSymmetryAccess(view, key, {}, {...fences, faceOk: false});
      assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    }
  }
  const shared = fixture(); shared.editing_target = {scope: 'all_people', target_id: shared.binding.asset_sha256, face_ref: null};
  shared.faces = []; shared.resolved = null; shared.selected_face_id = null;
  assert.equal(eyeSymmetryAccess(shared, 'horizontal', {}, {...fences, faceOk: false}).resetDisabled, false);
  assert.deepEqual(eyeSymmetryResetPatches(), [
    {operation_id: EYE_SYMMETRY_OPERATION, parameter_path: '/horizontal', unset: false, value: 0},
    {operation_id: EYE_SYMMETRY_OPERATION, parameter_path: '/size', unset: false, value: 0},
    {operation_id: EYE_SYMMETRY_OPERATION, parameter_path: '/reference', unset: false, value: 'auto'},
  ]);
  assert.deepEqual(eyeSymmetrySizePatches(.6, 'left'), [eyeSymmetryPatch('size', .6), eyeSymmetryPatch('reference', 'left')]);
  assert.deepEqual(eyeSymmetryPatch('reference', 'right'), {operation_id: EYE_SYMMETRY_OPERATION, parameter_path: '/reference', unset: false, value: 'right'});
});

test('pending, uncertain, competing editors and stale targets fence every write including reset', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) for (const key of keys) {
    const access = eyeSymmetryAccess(fixture(), key, available, {...fences, ...change});
    assert.equal(access.resetDisabled, true); assert.equal(access.changeDisabled, true);
  }
  assert.match(eyeSymmetryAccess(fixture(), 'size', available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  for (const change of [
    (view: PeopleView) => {view.editing_target = null;},
    (view: PeopleView) => {view.editing_target!.face_ref!.analysis_revision += 1;},
    (view: PeopleView) => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    (view: PeopleView) => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    (view: PeopleView) => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
    (view: PeopleView) => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: view.faces[0].face_ref};},
  ]) {
    const view = fixture(); change(view);
    assert.equal(eyeSymmetryTargetReady(view), false);
    assert.equal(eyeSymmetryAccess(view, 'horizontal', available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref}); view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(eyeSymmetryTargetReady(view), true);
  for (const key of keys) {
    const access = eyeSymmetryAccess(view, key, available, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.editValue, null); assert.equal(access.resetDisabled, false);
  }
});

test('reference, source, other-target membership and provenance changes invalidate drafts and stale callbacks', () => {
  const original = eyeSymmetryBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.faces[0].face_ref.analysis_revision += 1;}, view => {view.faces[0].enabled = false;},
    view => {view.faces.push({...view.faces[0], face_ref: {...view.faces[0].face_ref, face_instance_id: 'second'}});},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.groups.group.face_ids = [];}, view => {view.groups.group.priority += 1;},
    view => {view.persons.other = {anonymous: true};},
    view => {view.links.push({face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 1});},
    view => {view.resolved!.operations[EYE_SYMMETRY_OPERATION]['/reference'].value = 'left';},
    view => {view.resolved!.operations[EYE_SYMMETRY_OPERATION]['/size'].scope = 'face';},
    view => {view.resolved!.operations[EYE_SYMMETRY_OPERATION]['/horizontal'].target_id = 'other';},
    view => {view.editing_overrides[EYE_SYMMETRY_OPERATION] = {'/reference': 'auto'};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'both source eyes require real aperture evidence'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(eyeSymmetryBindingKey(view), original);}
  assert.equal(eyeSymmetryBindingKey(null), 'unavailable');
});

test('deliberate finite percent text rejects blank, negative or malformed values without implicit writes', () => {
  for (const [text, expected] of [['0', 0], ['100', 1], ['+100', 1], ['12.5', .125], [' 20 ', .2], ['1e1', .1]] as const) {
    assert.equal(parseEyeSymmetryChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', '-1', 'NaN', 'Infinity', '100.01', '0x10', '12abc', '1e999']) assert.equal(parseEyeSymmetryChoice(text), null);
});

test('reading, reference editing, size choice and reset never mutate source geometry or neighboring operations', () => {
  const view = fixture();
  for (const [operation, path] of [['lnx.deform.v1', '/big_eye'], ['lnx.eye_shape.v1', '/size/left'],
    ['lnx.eye_light.v1', '/strength'], ['lnx.philtrum.v1', '/amount'], ['lnx.skin_texture.v1', '/texture']]) {
    view.resolved!.operations[operation] = {[path]: {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
    view.editing_overrides[operation] = {[path]: .2};
  }
  const before = JSON.stringify(view), recipe = neutralEyeSymmetry(), checked = checkEyeSymmetry(recipe);
  checked.reference = 'left'; assert.equal(recipe.reference, 'auto');
  for (const key of keys) {eyeSymmetryReading(view, key); eyeSymmetryAccess(view, key, available, fences);}
  eyeSymmetryBindingKey(view); eyeSymmetryTargetReady(view); eyeSymmetrySizePatches(.3, 'right'); eyeSymmetryResetPatches();
  assert.equal(JSON.stringify(view), before);
});
