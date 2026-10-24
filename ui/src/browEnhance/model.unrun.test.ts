// AUTHORED / UNRUN. No product imports, tests, build, type check, execution, inference or photo acceptance were performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {ParameterValue, PeopleView} from '../people/model.ts';
import {BROW_ENHANCE_OPERATION, BROW_ENHANCE_CONTROL_ID, BROW_ENHANCE_CONTROL_PATH, BROW_ENHANCE_SOURCE,
  BROW_ENHANCE_SIDES, checkBrowEnhance, neutralBrowEnhance, browEnhanceReadiness, browEnhanceReading,
  browEnhanceTargetReady, browEnhanceAccess, browEnhanceBindingKey, browEnhanceAmountPatch,
  browEnhanceAdjustPatches, browEnhanceLinkedPatches, browEnhanceUnlockPatch, browEnhanceZeroSidePatches,
  browEnhanceResetPatches, parseBrowEnhanceChoice, type BrowEnhanceFences, type BrowEnhanceSide} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}},
    links: [{face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 2}],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [BROW_ENHANCE_OPERATION]: {
        '/left': {value: .45, scope: 'group', target_id: 'group', overridden: false},
        '/right': {value: -.2, scope: 'face', target_id: 'face-a', overridden: true},
        '/linked': {value: false, scope: 'group', target_id: 'group', overridden: false},
      },
    }}};
}
const fences: BrowEnhanceFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {brow_enhance_available: true};

test('exact distinct source-brow leaf, finite signed bilateral state and equal linked amounts', () => {
  assert.equal(BROW_ENHANCE_OPERATION, 'lnx.brow_enhance.v1');
  assert.equal(BROW_ENHANCE_CONTROL_ID, 'LNX-REF-PC-32471-C-18765fa8ea');
  assert.equal(BROW_ENHANCE_CONTROL_PATH, '眉毛增强');
  assert.equal(BROW_ENHANCE_SOURCE, 'https://www.pixcakeai.com/guide/32471');
  assert.deepEqual(BROW_ENHANCE_SIDES, ['left', 'right']);
  assert.deepEqual(neutralBrowEnhance(), {version: 1, linked: true, left: 0, right: 0});
  for (const value of [-1, -.5, -.01, 0, .01, .5, 1]) {
    for (const linked of [true, false]) {
      const recipe = {version: 1, linked, left: value, right: value};
      assert.deepEqual(checkBrowEnhance(recipe), recipe);
    }
    for (const side of BROW_ENHANCE_SIDES) {
      const recipe = {...neutralBrowEnhance(), linked: false, [side]: value};
      assert.deepEqual(checkBrowEnhance(recipe), recipe);
      assert.deepEqual(browEnhanceAmountPatch(side, value), {operation_id: BROW_ENHANCE_OPERATION,
        parameter_path: `/${side}`, unset: false, value});
    }
  }
  for (const value of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}, undefined]) {
    for (const side of BROW_ENHANCE_SIDES) {
      assert.throws(() => checkBrowEnhance({...neutralBrowEnhance(), linked: false, [side]: value}));
      assert.throws(() => browEnhanceAmountPatch(side, value as number));
    }
    assert.throws(() => browEnhanceLinkedPatches(value as number));
  }
  for (const recipe of [null, undefined, [], {}, {version: 1}, {linked: true, left: 0, right: 0},
    {...neutralBrowEnhance(), version: 2}, {...neutralBrowEnhance(), linked: 1},
    {...neutralBrowEnhance(), left: -.2, right: .4}, {...neutralBrowEnhance(), amount: .2},
    {...neutralBrowEnhance(), material: 'brow'}, {...neutralBrowEnhance(), exposure: .2},
    {version: 1, left: 0, right: 0}]) assert.throws(() => checkBrowEnhance(recipe));
  for (const side of ['viewer_left', 'linked', 'both', 'thickness', '']) {
    assert.throws(() => browEnhanceAmountPatch(side as BrowEnhanceSide, .2));
    assert.throws(() => browEnhanceZeroSidePatches(side as BrowEnhanceSide));
  }
});

test('unlock retains amounts; relink is an explicit atomic common value, never copied or averaged', () => {
  assert.deepEqual(browEnhanceUnlockPatch(), {operation_id: BROW_ENHANCE_OPERATION,
    parameter_path: '/linked', unset: false, value: false});
  for (const value of [-1, -.2, 0, .4, 1]) {
    const both = BROW_ENHANCE_SIDES.map(side => browEnhanceAmountPatch(side, value));
    assert.deepEqual(browEnhanceLinkedPatches(value), [{operation_id: BROW_ENHANCE_OPERATION,
      parameter_path: '/linked', unset: false, value: true}, ...both]);
    for (const side of BROW_ENHANCE_SIDES) {
      assert.deepEqual(browEnhanceAdjustPatches(side, value, true), both);
      assert.deepEqual(browEnhanceAdjustPatches(side, value, false), [browEnhanceAmountPatch(side, value)]);
    }
  }
  for (const linked of [1, 0, 'true', null, undefined])
    assert.throws(() => browEnhanceAdjustPatches('left', .2, linked as boolean));
});

test('unsupported-side recovery explicitly unlocks and zeros only the chosen side; reset preserves mode', () => {
  for (const side of BROW_ENHANCE_SIDES) {
    assert.deepEqual(browEnhanceZeroSidePatches(side), [
      {operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/linked', unset: false, value: false},
      {operation_id: BROW_ENHANCE_OPERATION, parameter_path: `/${side}`, unset: false, value: 0},
    ]);
  }
  assert.deepEqual(browEnhanceResetPatches(), [
    {operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/left', unset: false, value: 0},
    {operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/right', unset: false, value: 0},
  ]);
});

test('dedicated readiness never borrows material, geometry, exposure or other native capability', () => {
  assert.deepEqual(browEnhanceReadiness(available), {available: true});
  for (const capability of [undefined, null, {}, {brow_enhance_available: false},
    {brow_shape_protocol: 2}, {brow_makeup_available: true}, {skin_gloss_available: true}, {exposure_available: true}])
    assert.equal(browEnhanceReadiness(capability as Parameters<typeof browEnhanceReadiness>[0]).available, false);
  assert.deepEqual(browEnhanceReadiness({brow_enhance_available: false, brow_enhance_reason: 'native core missing'}),
    {available: false, reason: 'native core missing'});
  assert.equal(browEnhanceAccess(fixture(), {}, fences).changeDisabled, true);
  assert.equal(browEnhanceAccess(fixture(), {}, fences).resetDisabled, false);
  for (const analysis_status of ['synthetic', 'unresolved'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status;
    assert.equal(browEnhanceAccess(view, available, fences).changeDisabled, true);
  }
  const disabled = fixture(); disabled.faces[0].enabled = false;
  assert.equal(browEnhanceAccess(disabled, available, fences).changeDisabled, true);
  assert.equal(browEnhanceAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('selected actual provenance is distinct from explicit target intent', () => {
  const view = fixture(), reading = browEnhanceReading(view);
  assert.equal(reading.left.value, .45); assert.equal(reading.left.source?.scope, 'group');
  assert.equal(reading.left.source?.target_id, 'group'); assert.equal(reading.right.value, -.2);
  assert.equal(reading.right.source?.scope, 'face'); assert.equal(reading.linked.value, false);
  assert.equal(reading.left.overridePresent, false);
  const access = browEnhanceAccess(view, available, fences);
  assert.equal(access.editLeft, .45); assert.equal(access.editRight, -.2); assert.equal(access.writeLinked, false);
  view.editing_overrides[BROW_ENHANCE_OPERATION] = {'/left': -.7, '/right': -.7, '/linked': true};
  const explicit = browEnhanceAccess(view, available, fences);
  assert.equal(explicit.editLeft, -.7); assert.equal(explicit.editRight, -.7); assert.equal(explicit.writeLinked, true);
  assert.equal(explicit.reading.left.value, .45); assert.equal(explicit.reading.right.value, -.2);
  assert.equal(explicit.reading.linked.value, false);
});

test('all shared scopes start blank unless the exact target owns explicit values', () => {
  for (const scope of ['all_people', 'group', 'person'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(browEnhanceTargetReady(view), true);
    let access = browEnhanceAccess(view, available, fences);
    assert.equal(access.reading.left.value, .45);
    assert.equal(access.writeLinked, null); assert.equal(access.editLeft, null); assert.equal(access.editRight, null);
    assert.equal(access.changeDisabled, false);
    view.editing_overrides[BROW_ENHANCE_OPERATION] = {'/left': -.65, '/linked': false};
    access = browEnhanceAccess(view, available, fences);
    assert.equal(access.editLeft, -.65); assert.equal(access.editRight, null); assert.equal(access.writeLinked, false);
    view.resolved!.operations[BROW_ENHANCE_OPERATION]['/left'].value = .1;
    assert.equal(browEnhanceAccess(view, available, fences).editLeft, -.65);
    view.editing_overrides[BROW_ENHANCE_OPERATION] = {'/left': 'bad', '/right': Infinity, '/linked': 'true'};
    access = browEnhanceAccess(view, available, fences);
    assert.equal(access.editLeft, null); assert.equal(access.editRight, null); assert.equal(access.writeLinked, null);
    assert.equal(access.reading.left.overridePresent, true); assert.equal(access.reading.left.override, null);
  }
});

test('stale group membership or unconfirmed person association cannot seed or submit edits', () => {
  const group = fixture(); group.editing_target = {scope: 'group', target_id: 'group', face_ref: null};
  group.groups.group.face_ids = [];
  let access = browEnhanceAccess(group, available, fences);
  assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  assert.equal(access.editLeft, null); assert.equal(access.writeLinked, null);
  for (const state of ['candidate', 'rejected', 'unresolved'] as const) {
    const person = fixture(); person.editing_target = {scope: 'person', target_id: 'person', face_ref: null};
    person.links[0].state = state;
    access = browEnhanceAccess(person, available, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    assert.equal(access.editLeft, null); assert.equal(access.writeLinked, null);
  }
  for (const confirmation_revision of [null, -1, NaN, Infinity, .5, 3]) {
    const person = fixture(); person.editing_target = {scope: 'person', target_id: 'person', face_ref: null};
    person.links[0].confirmation_revision = confirmation_revision;
    assert.equal(browEnhanceAccess(person, available, fences).changeDisabled, true);
  }
});

test('missing, malformed, conflicted and linked-unequal reads never become fake zeros', () => {
  for (const side of BROW_ENHANCE_SIDES) for (const value of [NaN, Infinity, -Infinity, -1.01, 1.01, '0', true]) {
    const view = fixture(); view.resolved!.operations[BROW_ENHANCE_OPERATION][`/${side}`].value = value;
    assert.equal(browEnhanceReading(view)[side].value, null);
    assert.equal(browEnhanceAccess(view, available, fences).changeDisabled, true);
    assert.equal(browEnhanceAccess(view, available, fences).resetDisabled, false);
  }
  const linkedUnequal = fixture(); linkedUnequal.resolved!.operations[BROW_ENHANCE_OPERATION]['/linked'].value = true;
  for (const item of Object.values(browEnhanceReading(linkedUnequal))) {
    assert.equal(item.value, null); assert.equal(item.source, undefined); assert.match(item.reason ?? '', /不一致/);
  }
  for (const change of [
    (view: PeopleView) => {view.resolved = null;},
    (view: PeopleView) => {delete view.resolved!.operations[BROW_ENHANCE_OPERATION];},
    (view: PeopleView) => {delete view.resolved!.operations[BROW_ENHANCE_OPERATION]['/linked'];},
    (view: PeopleView) => {view.resolved!.operations[BROW_ENHANCE_OPERATION]['/linked'].value = 'true';},
    (view: PeopleView) => {view.selected_face_id = null;},
    (view: PeopleView) => {view.resolved!.conflicts.push({operation_id: BROW_ENHANCE_OPERATION,
      parameter_path: '/right', reason: 'ambiguous_group_precedence', target_ids: ['a', 'b']});},
  ]) {
    const view = fixture(); change(view);
    assert.equal(browEnhanceAccess(view, available, fences).changeDisabled, true);
    assert.equal(browEnhanceAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(browEnhanceReading(null).left.value, null);
  assert.equal(browEnhanceAccess(null, available, fences).resetDisabled, true);
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
    assert.equal(browEnhanceReading(view).left.value, null);
    assert.equal(browEnhanceAccess(view, available, fences).changeDisabled, true);
  }
});

test('neutral recovery survives unavailable native, anatomy and reads but not ownership or request fences', () => {
  for (const analysis_status of ['unresolved', 'synthetic', 'verified'] as const) {
    const view = fixture(); view.faces[0].analysis_status = analysis_status; view.faces[0].enabled = false; view.resolved = null;
    const access = browEnhanceAccess(view, {brow_enhance_available: false}, {...fences, faceOk: false});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = browEnhanceAccess(fixture(), available, {...fences, ...change});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
  assert.match(browEnhanceAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
  assert.equal(browEnhanceAccess(fixture(), available, {...fences, faceOk: false, faceWhy: 'source unavailable'}).reason,
    'source unavailable');
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.target_id = 'absent';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'other', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'absent', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.binding.document_revision = -1;}, view => {view.association_revision = Infinity;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view);
    assert.equal(browEnhanceTargetReady(view), false);
    assert.equal(browEnhanceAccess(view, available, fences).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref});
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...face_ref}};
  const access = browEnhanceAccess(view, available, fences);
  assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  assert.equal(access.writeLinked, null); assert.equal(access.editLeft, null); assert.equal(access.editRight, null);
});

test('source, membership, selected face, provenance, authority and refusals invalidate drafts and callbacks', () => {
  const original = browEnhanceBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = null;}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.faces[0].enabled = false;}, view => {view.faces[0].analysis_status = 'unresolved';},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.groups.group.face_ids = [];}, view => {view.groups.group.priority += 1;},
    view => {view.links[0].state = 'rejected';}, view => {view.links[0].confirmation_revision = null;},
    view => {delete view.persons.person;},
    view => {view.resolved!.face_ref.analysis_revision += 1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[BROW_ENHANCE_OPERATION]['/left'].value = -.8;},
    view => {view.resolved!.operations[BROW_ENHANCE_OPERATION]['/linked'].value = true;},
    view => {view.resolved!.operations[BROW_ENHANCE_OPERATION]['/left'].scope = 'face';},
    view => {view.resolved!.operations[BROW_ENHANCE_OPERATION]['/left'].target_id = 'other';},
    view => {view.resolved!.conflicts.push({operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/left', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[BROW_ENHANCE_OPERATION] = {'/left': .3};},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'source forehead reference unreliable'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(browEnhanceBindingKey(view), original);}
  assert.equal(browEnhanceBindingKey(null), 'unavailable');
});

test('blank is unknown; explicit finite signed numeric choice is required', () => {
  for (const [text, expected] of [['-100', -1], ['0', 0], ['+100', 1], ['12.5', .125], [' -20 ', -.2], ['1e1', .1]] as const)
    assert.equal(parseBrowEnhanceChoice(text), expected);
  for (const text of ['', ' ', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x10', '12abc', '1e999'])
    assert.equal(parseBrowEnhanceChoice(text), null);
});

test('only the new operation is patched; existing material, geometry and exposure remain untouched', () => {
  const view = fixture();
  for (const [operation, path, value] of [
    ['lnx.brow_makeup.v1', '/left/amount', .4], ['lnx.brow_shape.v1', '/left/thickness', .5],
    ['lnx.eye_shape.v1', '/left/size', .6], ['lnx.deform.v1', '/slim_face', .7],
    ['lnx.exposure.v1', '/ev', .8], ['lnx.skin_gloss.v1', '/amount', .9],
  ] as [string, string, ParameterValue][]) {
    view.resolved!.operations[operation] = {[path]: {value, scope: 'face', target_id: 'face-a', overridden: true}};
  }
  const before = JSON.stringify(view), recipe = neutralBrowEnhance(), checked = checkBrowEnhance(recipe);
  checked.left = .7; assert.equal(recipe.left, 0);
  assert.equal(browEnhanceAccess(view, available, fences).changeDisabled, false);
  browEnhanceReading(view); browEnhanceBindingKey(view); browEnhanceTargetReady(view);
  for (const patch of [...browEnhanceLinkedPatches(.2), browEnhanceUnlockPatch(),
    ...browEnhanceZeroSidePatches('right'), ...browEnhanceResetPatches()]) assert.equal(patch.operation_id, BROW_ENHANCE_OPERATION);
  assert.equal(JSON.stringify(view), before);
});
