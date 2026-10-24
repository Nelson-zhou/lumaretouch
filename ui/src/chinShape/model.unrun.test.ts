// AUTHORED / UNRUN. No imports, execution, tests, build, type check, inference or photo acceptance were performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {ParameterValue, PeopleView} from '../people/model.ts';
import {CHIN_SHAPE_OPERATION, CHIN_SHAPE_CONTROL_ID, CHIN_SHAPE_CONTROL_PATH, CHIN_SHAPE_SOURCE,
  CHIN_SHAPE_FROZEN_SOURCE, CHIN_SHAPE_SIDES, checkChinShape, neutralChinShape, chinShapeReadiness,
  chinShapeReading, chinShapeTargetReady, chinShapeAccess, chinShapeBindingKey, chinShapeAmountPatch,
  chinShapeAdjustPatches, chinShapeLinkedPatches, chinShapeUnlockPatch, chinShapeResetPatches,
  parseChinShapeChoice, type ChinShapeFences, type ChinShapeSide} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [CHIN_SHAPE_OPERATION]: {
        '/left': {value: .45, scope: 'group', target_id: 'group', overridden: false},
        '/right': {value: -.2, scope: 'face', target_id: 'face-a', overridden: true},
        '/linked': {value: false, scope: 'group', target_id: 'group', overridden: false},
      },
    }}};
}
const fences: ChinShapeFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {chin_shape_available: true};

test('exact distinct chin leaf and strict finite bilateral state, linked means equal', () => {
  assert.equal(CHIN_SHAPE_OPERATION, 'lnx.chin_shape.v1');
  assert.equal(CHIN_SHAPE_CONTROL_ID, 'LNX-REF-PC-32466-C-ed7837df9a');
  assert.equal(CHIN_SHAPE_CONTROL_PATH, '脸型/尖下巴');
  assert.equal(CHIN_SHAPE_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.equal(CHIN_SHAPE_FROZEN_SOURCE, 'https://www.pixcakeai.com/guide/32466');
  assert.deepEqual(CHIN_SHAPE_SIDES, ['left', 'right']);
  assert.deepEqual(neutralChinShape(), {version: 1, linked: true, left: 0, right: 0});
  for (const value of [-1, -.5, -.01, 0, .01, .5, 1]) {
    for (const linked of [true, false]) {
      const recipe = {version: 1, linked, left: value, right: value};
      assert.deepEqual(checkChinShape(recipe), recipe);
    }
    for (const side of CHIN_SHAPE_SIDES) {
      const recipe = {...neutralChinShape(), linked: false, [side]: value};
      assert.deepEqual(checkChinShape(recipe), recipe);
      assert.deepEqual(chinShapeAmountPatch(side, value), {operation_id: CHIN_SHAPE_OPERATION,
        parameter_path: `/${side}`, unset: false, value});
    }
  }
  for (const value of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}, undefined]) {
    for (const side of CHIN_SHAPE_SIDES) {
      assert.throws(() => checkChinShape({...neutralChinShape(), linked: false, [side]: value}));
      assert.throws(() => chinShapeAmountPatch(side, value as number));
    }
    assert.throws(() => chinShapeLinkedPatches(value as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {linked: true, left: 0, right: 0},
    {...neutralChinShape(), version: 2}, {...neutralChinShape(), linked: 1},
    {...neutralChinShape(), left: -.2, right: .4}, {...neutralChinShape(), amount: .2},
    {...neutralChinShape(), small_chin: .2}, {...neutralChinShape(), curvature: .2},
    {version: 1, left: 0, right: 0}]) assert.throws(() => checkChinShape(recipe));
  for (const side of ['viewer_left', 'linked', 'both', 'small_chin', ''])
    assert.throws(() => chinShapeAmountPatch(side as ChinShapeSide, .2));
});

test('unlock retains values; relinking is an atomic explicit equal choice, not flag-only or migration', () => {
  assert.deepEqual(chinShapeUnlockPatch(), {operation_id: CHIN_SHAPE_OPERATION,
    parameter_path: '/linked', unset: false, value: false});
  for (const value of [-1, -.2, 0, .4, 1]) {
    const both = CHIN_SHAPE_SIDES.map(side => chinShapeAmountPatch(side, value));
    assert.deepEqual(chinShapeLinkedPatches(value), [{operation_id: CHIN_SHAPE_OPERATION,
      parameter_path: '/linked', unset: false, value: true}, ...both]);
    for (const side of CHIN_SHAPE_SIDES) {
      assert.deepEqual(chinShapeAdjustPatches(side, value, true), both);
      assert.deepEqual(chinShapeAdjustPatches(side, value, false), [chinShapeAmountPatch(side, value)]);
    }
  }
  for (const linked of [1, 0, 'true', null, undefined])
    assert.throws(() => chinShapeAdjustPatches('left', .2, linked as boolean));
  assert.deepEqual(chinShapeResetPatches(), [chinShapeAmountPatch('left', 0), chinShapeAmountPatch('right', 0)]);
});

test('dedicated native capability is availability, never an anatomy or neighboring-core substitute', () => {
  assert.deepEqual(chinShapeReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {chin_shape_available: false},
    {lower_face_available: true}, {mid_face_available: true}, {face_size_available: true}, {face_contour_available: true}]) {
    assert.equal(chinShapeReadiness(capability as Parameters<typeof chinShapeReadiness>[0]).available, false);
  }
  assert.deepEqual(chinShapeReadiness({chin_shape_available: false, chin_shape_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(chinShapeAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(chinShapeAccess(fixture(), {}, fences).resetDisabled, false);
  for (const analysis_status of ['synthetic', 'unresolved'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status;
    assert.equal(chinShapeAccess(view, available, fences).changeDisabled, true);
  }
  const disabled = fixture(); disabled.faces[0].enabled = false;
  assert.equal(chinShapeAccess(disabled, available, fences).changeDisabled, true);
  assert.equal(chinShapeAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('selected effective values and provenance remain separate from explicit target values', () => {
  const view = fixture(), reading = chinShapeReading(view);
  assert.equal(reading.left.value, .45);
  assert.equal(reading.left.source?.scope, 'group');
  assert.equal(reading.left.source?.target_id, 'group');
  assert.equal(reading.right.value, -.2);
  assert.equal(reading.right.source?.scope, 'face');
  assert.equal(reading.linked.value, false);
  assert.equal(reading.left.overridePresent, false);
  const access = chinShapeAccess(view, available, fences);
  assert.equal(access.editLeft, .45); assert.equal(access.editRight, -.2); assert.equal(access.writeLinked, false);
  view.editing_overrides[CHIN_SHAPE_OPERATION] = {'/left': -.7, '/right': -.7, '/linked': true};
  const explicit = chinShapeAccess(view, available, fences);
  assert.equal(explicit.editLeft, -.7); assert.equal(explicit.editRight, -.7); assert.equal(explicit.writeLinked, true);
  assert.equal(explicit.reading.left.value, .45); assert.equal(explicit.reading.right.value, -.2);
  assert.equal(explicit.reading.linked.value, false);
});

test('every shared scope starts blank unless that exact scope owns an explicit value', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(chinShapeTargetReady(view), true);
    let access = chinShapeAccess(view, available, fences);
    assert.equal(access.reading.left.value, .45);
    assert.equal(access.writeLinked, null); assert.equal(access.editLeft, null); assert.equal(access.editRight, null);
    assert.equal(access.changeDisabled, false);
    view.editing_overrides[CHIN_SHAPE_OPERATION] = {'/left': -.65, '/linked': false};
    access = chinShapeAccess(view, available, fences);
    assert.equal(access.editLeft, -.65); assert.equal(access.editRight, null); assert.equal(access.writeLinked, false);
    view.resolved!.operations[CHIN_SHAPE_OPERATION]['/left'].value = .1;
    assert.equal(chinShapeAccess(view, available, fences).editLeft, -.65);
    view.editing_overrides[CHIN_SHAPE_OPERATION] = {'/left': 'bad', '/right': Infinity, '/linked': 'true'};
    access = chinShapeAccess(view, available, fences);
    assert.equal(access.editLeft, null); assert.equal(access.editRight, null); assert.equal(access.writeLinked, null);
    assert.equal(access.reading.left.overridePresent, true); assert.equal(access.reading.left.override, null);
  }
});

test('unknown, malformed, stale, conflicted and linked-unequal actual reads never become fake zeros', () => {
  for (const side of CHIN_SHAPE_SIDES) {
    for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
      const view = fixture(); view.resolved!.operations[CHIN_SHAPE_OPERATION][`/${side}`].value = value;
      assert.equal(chinShapeReading(view)[side].value, null);
      assert.equal(chinShapeAccess(view, available, fences).changeDisabled, true);
      assert.equal(chinShapeAccess(view, available, fences).resetDisabled, false);
    }
  }
  const linkedUnequal = fixture(); linkedUnequal.resolved!.operations[CHIN_SHAPE_OPERATION]['/linked'].value = true;
  for (const item of Object.values(chinShapeReading(linkedUnequal))) {
    assert.equal(item.value, null); assert.equal(item.source, undefined); assert.match(item.reason ?? '', /不一致/);
  }
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[CHIN_SHAPE_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[CHIN_SHAPE_OPERATION]['/linked'];},
    (view: PeopleView) => {view.resolved!.operations[CHIN_SHAPE_OPERATION]['/linked'].value = 'true';},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: CHIN_SHAPE_OPERATION,
      parameter_path: '/right', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(chinShapeAccess(view, available, fences).changeDisabled, true);
    assert.equal(chinShapeAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(chinShapeReading(null).left.value, null);
  assert.equal(chinShapeAccess(null, available, fences).resetDisabled, true);
});

test('source, face, document, state and association revisions gate every nonzero edit', () => {
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
    assert.equal(chinShapeReading(view).left.value, null);
    assert.equal(chinShapeAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral recovery is two zero leaves, independent of native/anatomy/readability but not ownership', () => {
  assert.deepEqual(chinShapeResetPatches(), [
    {operation_id: CHIN_SHAPE_OPERATION, parameter_path: '/left', unset: false, value: 0},
    {operation_id: CHIN_SHAPE_OPERATION, parameter_path: '/right', unset: false, value: 0},
  ]);
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = chinShapeAccess(view, {chin_shape_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = chinShapeAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
  assert.match(chinShapeAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  assert.equal(chinShapeAccess(fixture(), available, {...fences, faceOk: false, faceWhy: 'source unavailable'}).reason,
    'source unavailable');
});

test('reset target is owned and source-bound, not inferred from the selected preview face', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.target_id = 'absent';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.binding.document_revision = -1;}, view => {view.association_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(chinShapeTargetReady(view), false);
    assert.equal(chinShapeAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  assert.equal(chinShapeTargetReady(view), true);
  const access = chinShapeAccess(view, available, fences);
  assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  assert.equal(access.writeLinked, null); assert.equal(access.editLeft, null); assert.equal(access.editRight, null);
});

test('draft/callback binding changes with source, revision, scope, selected face, authority and refusals', () => {
  const original = chinShapeBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[CHIN_SHAPE_OPERATION]['/left'].value = -.8;},
    view => {view.resolved!.operations[CHIN_SHAPE_OPERATION]['/linked'].value = true;},
    view => {view.resolved!.operations[CHIN_SHAPE_OPERATION]['/left'].scope = 'face';},
    view => {view.resolved!.operations[CHIN_SHAPE_OPERATION]['/left'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: CHIN_SHAPE_OPERATION, parameter_path: '/left', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[CHIN_SHAPE_OPERATION] = {'/left': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'source chin support clipped'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(chinShapeBindingKey(view), original);}
  assert.equal(chinShapeBindingKey(null), 'unavailable');
});

test('raw blank is not zero; explicit signed finite numeric choice is required', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const)
    assert.equal(parseChinShapeChoice(text), expected);
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999'])
    assert.equal(parseChinShapeChoice(text), null);
});

test('model is nonmutating and preserves every old operation; compatibility belongs to the renderer', () => {
  const view = fixture();
  for (const [operation, path, value] of [
    ['lnx.deform.v1', '/small_chin', .4], ['lnx.slim_face.v2', '/left', .5],
    ['lnx.face_size.v1', '/amount', .6], ['lnx.mid_face.v1', '/amount', .7],
    ['lnx.lower_face.v1', '/amount', .8], ['lnx.face_contour.v1', '/jaw/left', .9],
  ] as [string, string, ParameterValue][]) {
    view.resolved!.operations[operation] = {[path]: {value, scope: 'face', target_id: 'face-a', overridden: true}};
  }
  const before = JSON.stringify(view), recipe = neutralChinShape(), checked = checkChinShape(recipe);
  checked.left = .7;
  assert.equal(recipe.left, 0);
  assert.equal(chinShapeAccess(view, available, fences).changeDisabled, false);
  chinShapeReading(view); chinShapeBindingKey(view); chinShapeTargetReady(view);
  for (const patch of [...chinShapeLinkedPatches(.2), chinShapeUnlockPatch(), ...chinShapeResetPatches()])
    assert.equal(patch.operation_id, CHIN_SHAPE_OPERATION);
  assert.equal(JSON.stringify(view), before);
});
