// AUTHORED / UNRUN. No project imports, tests, type checks, application runs or photo acceptance performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {CHIN_LENGTH_OPERATION, LEGACY_SMALL_CHIN_OPERATION, CHIN_LENGTH_CONTROL_ID, CHIN_LENGTH_CONTROL_PATH,
  CHIN_LENGTH_SOURCE, CHIN_LENGTH_FROZEN_SOURCE, checkChinLength, neutralChinLength, chinLengthReadiness,
  chinLengthReading, chinLengthTargetReady, chinLengthAccess, chinLengthBindingKey, chinLengthPatch,
  chinLengthResetPatches, legacySmallChinPatch, replaceLegacySmallChinPatches, parseChinLengthChoice,
  type ChinLengthFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [CHIN_LENGTH_OPERATION]: {'/amount': {value: 0, scope: 'default', target_id: null, overridden: false}},
      [LEGACY_SMALL_CHIN_OPERATION]: {'/small_chin': {value: 0, scope: 'default', target_id: null, overridden: false}},
    }}};
}
const fences: ChinLengthFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {chin_length_available: true};
const newLeaf = (view: PeopleView) => view.resolved!.operations[CHIN_LENGTH_OPERATION]['/amount'];
const oldLeaf = (view: PeopleView) => view.resolved!.operations[LEGACY_SMALL_CHIN_OPERATION]['/small_chin'];

test('exact new leaf and operation use strict version-one finite signed state, not a legacy alias', () => {
  assert.equal(CHIN_LENGTH_CONTROL_ID, 'LNX-REF-PC-32466-C-44a42baef4');
  assert.equal(CHIN_LENGTH_CONTROL_PATH, '脸型/下巴长短');
  assert.equal(CHIN_LENGTH_OPERATION, 'lnx.chin_length.v1');
  assert.equal(LEGACY_SMALL_CHIN_OPERATION, 'lnx.deform.v1');
  assert.equal(CHIN_LENGTH_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(CHIN_LENGTH_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(neutralChinLength(), {version: 1, amount: 0});
  for (const amount of [-1, -.5, -.001, 0, .001, .5, 1]) {
    assert.deepEqual(checkChinLength({version: 1, amount}), {version: 1, amount});
    assert.deepEqual(chinLengthPatch(amount), {operation_id: CHIN_LENGTH_OPERATION, parameter_path: '/amount', unset: false, value: amount});
  }
  for (const amount of [-1.001, 1.001, NaN, Infinity, -Infinity, '0', null, true, false, {}, undefined]) {
    assert.throws(() => checkChinLength({version: 1, amount}));
    assert.throws(() => chinLengthPatch(amount as number));
    assert.throws(() => legacySmallChinPatch(amount as number));
    assert.throws(() => replaceLegacySmallChinPatches(amount as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {amount: 0}, {version: 2, amount: 0},
    {version: true, amount: 0}, {version: '1', amount: 0}, {version: 1, amount: 0, linked: true},
    {version: 1, amount: 0, left: 0}, {version: 1, amount: 0, small_chin: 0}, {version: 1, small_chin: .3}]) {
    assert.throws(() => checkChinLength(recipe));
  }
});

test('dedicated capability alone enables the new operation, not another geometric core flag', () => {
  assert.deepEqual(chinLengthReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {chin_length_available: false}, {lower_face_available: true},
    {mid_face_available: true}, {chin_shape_available: true}, {face_contour_available: true}]) {
    assert.equal(chinLengthReadiness(capability as Parameters<typeof chinLengthReadiness>[0]).available, false);
  }
  assert.deepEqual(chinLengthReadiness({chin_length_available: false, chin_length_reason: 'core unavailable'}),
    {available: false, reason: 'core unavailable'});
  assert.equal(chinLengthAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(chinLengthAccess(fixture(), {}, fences).resetDisabled, false);
  assert.equal(chinLengthAccess(fixture(), {}, fences).legacyChangeDisabled, false);
});

test('replacement is exactly old zero plus the chosen new number in a single atomic patch list', () => {
  for (const chosen of [-1, -.4, 0, .3, 1]) {
    assert.deepEqual(replaceLegacySmallChinPatches(chosen), [
      {operation_id: 'lnx.deform.v1', parameter_path: '/small_chin', unset: false, value: 0},
      {operation_id: 'lnx.chin_length.v1', parameter_path: '/amount', unset: false, value: chosen},
    ]);
  }
  // No old number is accepted by this function, so it cannot copy, negate or convert one.
  assert.equal(replaceLegacySmallChinPatches(.2).length, 2);
  assert.deepEqual(chinLengthResetPatches(), [chinLengthPatch(0)]);
  assert.equal(chinLengthResetPatches().some(patch => patch.operation_id === LEGACY_SMALL_CHIN_OPERATION || patch.unset), false);
});

test('new neutral leaves saved legacy state untouched and both signs of active legacy block normal new writes', () => {
  for (const amount of [-.7, .7]) {
    const view = fixture(); oldLeaf(view).value = amount;
    const before = JSON.stringify(view), access = chinLengthAccess(view, available, fences);
    assert.equal(access.legacyActive, true);
    assert.equal(access.changeDisabled, true);
    assert.equal(access.replacementDisabled, false);
    assert.equal(access.resetDisabled, false);
    chinLengthResetPatches(); replaceLegacySmallChinPatches(.25);
    assert.equal(oldLeaf(view).value, amount);
    assert.equal(JSON.stringify(view), before);
  }
});

test('new active gates legacy writes while explicit replacement can recover a conflicting saved state', () => {
  const view = fixture(); newLeaf(view).value = -.3;
  assert.equal(chinLengthAccess(view, available, fences).legacyChangeDisabled, true);
  assert.equal(chinLengthAccess(view, available, fences).replacementDisabled, true);
  oldLeaf(view).value = .4;
  const access = chinLengthAccess(view, available, fences);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.legacyChangeDisabled, true);
  assert.equal(access.replacementDisabled, false);
  assert.equal(access.resetDisabled, false);
});

test('new and old effective provenance never collapse into their target-owned explicit numbers', () => {
  const view = fixture();
  Object.assign(newLeaf(view), {value: .45, scope: 'group', target_id: 'group'});
  Object.assign(oldLeaf(view), {value: 0, scope: 'face', target_id: 'face-a', overridden: true});
  view.editing_overrides = {[CHIN_LENGTH_OPERATION]: {'/amount': -.2}, [LEGACY_SMALL_CHIN_OPERATION]: {'/small_chin': .3}};
  const access = chinLengthAccess(view, available, fences);
  assert.equal(access.reading.amount.value, .45);
  assert.equal(access.reading.amount.source?.scope, 'group');
  assert.equal(access.reading.amount.source?.target_id, 'group');
  assert.equal(access.reading.amount.override, -.2);
  assert.equal(access.editValue, -.2);
  assert.equal(access.reading.legacy.value, 0);
  assert.equal(access.reading.legacy.source?.scope, 'face');
  assert.equal(access.reading.legacy.override, .3);
  assert.equal(access.legacyEditValue, .3);
});

test('all shared scopes start blank for both effects unless that scope owns an explicit number', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture(); newLeaf(view).value = .45;
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(chinLengthTargetReady(view), true);
    assert.equal(chinLengthAccess(view, available, fences).editValue, null);
    assert.equal(chinLengthAccess(view, available, fences).legacyEditValue, null);
    view.editing_overrides[CHIN_LENGTH_OPERATION] = {'/amount': -.65};
    view.editing_overrides[LEGACY_SMALL_CHIN_OPERATION] = {'/small_chin': 0};
    const access = chinLengthAccess(view, available, fences);
    assert.equal(access.editValue, -.65);
    assert.equal(access.legacyEditValue, 0);
    assert.equal(access.reading.amount.value, .45);
    view.editing_overrides[CHIN_LENGTH_OPERATION]['/amount'] = 'bad';
    assert.equal(chinLengthAccess(view, available, fences).editValue, null);
    assert.equal(chinLengthReading(view).amount.overridePresent, true);
  }
});

test('shared legacy explicit intent can require replacement even if preview-face old effect is zero', () => {
  const view = fixture();
  view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};
  view.editing_overrides[LEGACY_SMALL_CHIN_OPERATION] = {'/small_chin': .7};
  const access = chinLengthAccess(view, available, fences);
  assert.equal(access.legacyActive, false);
  assert.equal(access.targetLegacyActive, true);
  assert.equal(access.replacementNeeded, true);
  assert.equal(access.replacementDisabled, false);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.legacyEditValue, .7);
  view.editing_overrides[LEGACY_SMALL_CHIN_OPERATION]['/small_chin'] = 'bad';
  assert.equal(chinLengthAccess(view, available, fences).targetLegacyActive, null);
  assert.equal(chinLengthAccess(view, available, fences).changeDisabled, true);
});

test('shared new explicit intent blocks historical writes without claiming selected effective activation', () => {
  const view = fixture(); view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};
  view.editing_overrides[CHIN_LENGTH_OPERATION] = {'/amount': -.5};
  const access = chinLengthAccess(view, available, fences);
  assert.equal(access.active, false);
  assert.equal(access.targetActive, true);
  assert.equal(access.legacyChangeDisabled, true);
  assert.equal(access.resetDisabled, false);
});

test('unknown, nonfinite or conflicted readings are never treated as neutral', () => {
  for (const operation of [CHIN_LENGTH_OPERATION, LEGACY_SMALL_CHIN_OPERATION]) {
    const path = operation === CHIN_LENGTH_OPERATION ? '/amount' : '/small_chin';
    for (const change of [
      (view: PeopleView) => {delete view.resolved!.operations[operation];},
      (view: PeopleView) => {delete view.resolved!.operations[operation][path];},
      (view: PeopleView) => {view.resolved!.operations[operation][path].value = NaN;},
      (view: PeopleView) => {view.resolved!.operations[operation][path].value = '0';},
      (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: operation, parameter_path: path, reason: 'group conflict', target_ids: ['g1', 'g2']});},
    ]) {
      const view = fixture(); change(view);
      const access = chinLengthAccess(view, available, fences);
      assert.equal(access.changeDisabled, true);
      assert.equal(access.legacyChangeDisabled, true);
      assert.equal(access.replacementDisabled, true);
      assert.equal(access.resetDisabled, false);
    }
  }
  assert.equal(chinLengthReading(null).amount.value, null);
  assert.equal(chinLengthReading(null).legacy.value, null);
  assert.equal(chinLengthAccess(null, available, fences).resetDisabled, true);
});

test('source identity and authoritative revisions fence both effects and replacement', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = -1;},
    view => {view.revision = NaN;}, view => {view.association_revision = .5;},
    view => {view.resolved = null;}, view => {view.selected_face_id = null;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.face_ref.face_instance_id = 'other';},
    view => {view.resolved!.face_ref.asset_sha256 = 'other';},
    view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.faces[0].face_ref.asset_sha256 = 'other';},
    view => {view.faces[0].face_ref.analysis_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); oldLeaf(view).value = .7; change(view);
    const access = chinLengthAccess(view, available, fences);
    assert.equal(access.reading.amount.value, null);
    assert.equal(access.reading.legacy.value, null);
    assert.equal(access.changeDisabled, true);
    assert.equal(access.replacementDisabled, true);
    assert.equal(access.legacyChangeDisabled, true);
  }
});

test('reset needs owned source and target, not selected face anatomy or new native availability', () => {
  for (const analysis_status of ['verified', 'unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = chinLengthAccess(view, {}, {...fences, faceOk: false});
    assert.equal(access.resetDisabled, false);
    assert.equal(access.changeDisabled, true);
  }
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.target_id = 'absent';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(chinLengthTargetReady(view), false);
    assert.equal(chinLengthAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  const access = chinLengthAccess(view, available, fences);
  assert.equal(access.editValue, null);
  assert.equal(access.legacyEditValue, null);
  assert.equal(access.changeDisabled, true);
  assert.equal(access.resetDisabled, false);
});

test('pending, uncertain, disabled owner and competing editor block every mutation', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const view = fixture(); oldLeaf(view).value = .5;
    const access = chinLengthAccess(view, available, {...fences, ...change});
    assert.equal(access.resetDisabled, true);
    assert.equal(access.changeDisabled, true);
    assert.equal(access.replacementDisabled, true);
    assert.equal(access.legacyChangeDisabled, true);
  }
  assert.match(chinLengthAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('source, owner facts, target, provenance, both intents and memberships invalidate old draft keys', () => {
  const original = chinLengthBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;}, view => {newLeaf(view).value = -.8;},
    view => {oldLeaf(view).value = .7;}, view => {oldLeaf(view).scope = 'group';},
    view => {newLeaf(view).target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: LEGACY_SMALL_CHIN_OPERATION, parameter_path: '/small_chin', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[CHIN_LENGTH_OPERATION] = {'/amount': .3};},
    view => {view.editing_overrides[LEGACY_SMALL_CHIN_OPERATION] = {'/small_chin': .3};},
    view => {view.groups.group.face_ids.push('other');}, view => {delete view.persons.person;},
    view => {view.links.push({face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 2});},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'source support clipped'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(chinLengthBindingKey(view), original);}
  assert.equal(chinLengthBindingKey(null), 'unavailable');
});

test('raw numerical choices must be explicit, finite and in range; blanks are not reset consent', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const) {
    assert.equal(parseChinLengthChoice(text), expected);
  }
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999']) {
    assert.equal(parseChinLengthChoice(text), null);
  }
});

test('helpers never mutate people data or other recipes and do not invent neighboring geometry policy', () => {
  const view = fixture();
  for (const operation of ['lnx.chin_shape.v1', 'lnx.lower_face.v1', 'lnx.mid_face.v1', 'lnx.face_size.v1']) {
    view.resolved!.operations[operation] = {'/amount': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}};
  }
  const before = JSON.stringify(view), recipe = neutralChinLength(), checked = checkChinLength(recipe);
  checked.amount = .7; assert.equal(recipe.amount, 0);
  assert.equal(chinLengthAccess(view, available, fences).changeDisabled, false);
  chinLengthReading(view); chinLengthTargetReady(view); chinLengthBindingKey(view); chinLengthResetPatches();
  replaceLegacySmallChinPatches(-.3); legacySmallChinPatch(.6);
  assert.equal(JSON.stringify(view), before);
});
