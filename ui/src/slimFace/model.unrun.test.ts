// AUTHORED / UNRUN. Imports and fixtures have not executed; no numerical, UI or photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {FACE_CONTOUR_KEYS, FACE_CONTOUR_OPERATION} from '../faceContour/model.ts';
import {LEGACY_SLIM_FACE_OPERATION, SLIM_FACE_CONTROL_ID, SLIM_FACE_CONTROL_PATH, SLIM_FACE_OPERATION,
  SLIM_FACE_SIDES, SLIM_FACE_SOURCE, checkSlimFace, legacySlimFacePatch, neutralSlimFace, parseSlimFaceChoice,
  replaceLegacySlimFacePatches, slimFaceAccess, slimFaceAdjustPatches, slimFaceAmountPatch, slimFaceBindingKey,
  slimFaceLinkPatch, slimFaceReading, slimFaceResetPatches, type SlimFaceFences, type SlimFaceSide} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  const neutralContour = Object.fromEntries(FACE_CONTOUR_KEYS.flatMap(key => [
    [`/${key}/left`, {value: 0, scope: 'default' as const, target_id: null, overridden: false}],
    [`/${key}/right`, {value: 0, scope: 'default' as const, target_id: null, overridden: false}],
    [`/${key}/linked`, {value: true, scope: 'default' as const, target_id: null, overridden: false}],
  ]));
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {[SLIM_FACE_OPERATION]: {}, [LEGACY_SLIM_FACE_OPERATION]: {}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [SLIM_FACE_OPERATION]: {
        '/left': {value: 0, scope: 'default', target_id: null, overridden: false},
        '/right': {value: 0, scope: 'default', target_id: null, overridden: false},
        '/linked': {value: true, scope: 'default', target_id: null, overridden: false},
      },
      [LEGACY_SLIM_FACE_OPERATION]: {'/slim_face': {value: 0, scope: 'default', target_id: null, overridden: false}},
      [FACE_CONTOUR_OPERATION]: neutralContour,
    }}};
}
const fences: SlimFaceFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {face_contour_available: true};

test('exact new operation and frozen leaf, strict signed finite bilateral recipe, no legacy conversion', () => {
  assert.equal(SLIM_FACE_OPERATION, 'lnx.slim_face.v2');
  assert.equal(LEGACY_SLIM_FACE_OPERATION, 'lnx.deform.v1');
  assert.equal(SLIM_FACE_CONTROL_ID, 'LNX-REF-PC-32466-C-da1d54e292');
  assert.equal(SLIM_FACE_CONTROL_PATH, '脸型/瘦脸');
  assert.equal(SLIM_FACE_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.deepEqual(SLIM_FACE_SIDES, ['left', 'right']);
  assert.deepEqual(neutralSlimFace(), {version: 2, linked: true, left: 0, right: 0});
  for (const side of SLIM_FACE_SIDES) {
    for (const value of [-1, -.5, -.01, 0, .01, .5, 1]) {
      const recipe = neutralSlimFace(); recipe[side] = value;
      assert.deepEqual(checkSlimFace(recipe), recipe);
      assert.deepEqual(slimFaceAmountPatch(side, value), {operation_id: SLIM_FACE_OPERATION,
        parameter_path: `/${side}`, unset: false, value});
    }
    for (const value of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}]) {
      const recipe = neutralSlimFace(); recipe[side] = value as number;
      assert.throws(() => checkSlimFace(recipe));
      assert.throws(() => slimFaceAmountPatch(side, value as number));
      assert.throws(() => legacySlimFacePatch(value as number));
    }
  }
  for (const invalid of [null, undefined, [], {}, {...neutralSlimFace(), version: 1},
    {...neutralSlimFace(), linked: 1}, {...neutralSlimFace(), slim_face: .2},
    {version: 2, left: 0, right: 0}, {version: 1, slim_face: .4}]) assert.throws(() => checkSlimFace(invalid));
  for (const side of ['viewer_left', 'slim_face', 'linked', 'both', ''])
    assert.throws(() => slimFaceAmountPatch(side as SlimFaceSide, .2));
});

test('flag-only linking preserves unequal numbers; only next numeric edit writes both sides', () => {
  const recipe = {version: 2 as const, linked: true, left: -.2, right: .6};
  assert.deepEqual(checkSlimFace(recipe), recipe);
  for (const linked of [true, false]) assert.deepEqual(slimFaceLinkPatch(linked), {
    operation_id: SLIM_FACE_OPERATION, parameter_path: '/linked', unset: false, value: linked,
  });
  for (const side of SLIM_FACE_SIDES) {
    assert.deepEqual(slimFaceAdjustPatches(side, -.6, false), [slimFaceAmountPatch(side, -.6)]);
    assert.deepEqual(slimFaceAdjustPatches(side, .7, true), [slimFaceAmountPatch('left', .7), slimFaceAmountPatch('right', .7)]);
    assert.deepEqual(slimFaceAdjustPatches(side, 0, true), slimFaceResetPatches());
  }
  for (const linked of [1, 0, 'true', null, undefined]) {
    assert.throws(() => slimFaceLinkPatch(linked as boolean));
    assert.throws(() => slimFaceAdjustPatches('left', .2, linked as boolean));
  }
  assert.deepEqual(slimFaceResetPatches(), [slimFaceAmountPatch('left', 0), slimFaceAmountPatch('right', 0)]);
  assert.equal(slimFaceResetPatches().some(patch => patch.unset || patch.parameter_path === '/linked'), false);
});

test('replacement is one legacy-zero plus chosen-value transaction, never copying strength or unsetting inheritance', () => {
  assert.deepEqual(replaceLegacySlimFacePatches(.25, .25, true), [legacySlimFacePatch(0),
    slimFaceAmountPatch('left', .25), slimFaceAmountPatch('right', .25)]);
  assert.deepEqual(replaceLegacySlimFacePatches(-.3, .7, false), [legacySlimFacePatch(0),
    slimFaceAmountPatch('left', -.3), slimFaceAmountPatch('right', .7)]);
  assert.deepEqual(replaceLegacySlimFacePatches(0, 0, true), [legacySlimFacePatch(0), ...slimFaceResetPatches()]);
  assert.equal(replaceLegacySlimFacePatches(.2, .2, true).some(patch => patch.unset || patch.parameter_path === '/linked'), false);
  assert.throws(() => replaceLegacySlimFacePatches(.2, .4, true));
  assert.throws(() => replaceLegacySlimFacePatches(.2, .2, 1 as unknown as boolean));
  for (const invalid of [NaN, Infinity, -Infinity, 1.1, -1.1]) {
    assert.throws(() => replaceLegacySlimFacePatches(invalid, 0, false));
    assert.throws(() => replaceLegacySlimFacePatches(0, invalid, false));
  }
  for (const amount of [-1, -.4, 0, .7, 1]) assert.deepEqual(legacySlimFacePatch(amount), {
    operation_id: LEGACY_SLIM_FACE_OPERATION, parameter_path: '/slim_face', unset: false, value: amount,
  });
});

test('replacement display choice requires deliberate finite decimal input, never blank-as-zero or legacy defaults', () => {
  for (const text of ['', ' ', '\n', '+', '-', '.', 'NaN', 'Infinity', '-Infinity', '100.01', '-100.01', '0x64', '0b10', '10px'])
    assert.equal(parseSlimFaceChoice(text), null);
  for (const [text, value] of [['0', 0], [' 0 ', 0], ['-100', -1], ['100', 1], ['25', .25], ['-.5', -.005], ['1e2', 1]] as const)
    assert.equal(parseSlimFaceChoice(text), value);
});

test('legacy remains literal readback and blocks normal new editing until explicit replacement', () => {
  const view = fixture();
  view.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'] = {
    value: -.8, scope: 'group', target_id: 'group', overridden: false,
  };
  view.editing_overrides[LEGACY_SLIM_FACE_OPERATION]['/slim_face'] = .3;
  const access = slimFaceAccess(view, available, fences);
  assert.equal(access.reading.legacy.value, -.8); assert.equal(access.reading.legacy.override, .3);
  assert.equal(access.reading.legacy.source?.scope, 'group');
  assert.equal(access.reading.left.value, 0); assert.equal(access.reading.right.value, 0);
  assert.equal(access.legacyActive, true); assert.equal(access.changeDisabled, true);
  assert.equal(access.replacementDisabled, false); assert.equal(access.legacyChangeDisabled, false);
  assert.match(access.reason ?? '', /不会自动转换/);
  assert.equal(slimFaceAccess(fixture(), available, fences).replacementDisabled, true);
});

test('active new or standalone contours cannot silently coexist with another active owner', () => {
  const view = fixture(); view.resolved!.operations[SLIM_FACE_OPERATION]['/left'].value = .2;
  let access = slimFaceAccess(view, available, fences);
  assert.equal(access.active, true); assert.equal(access.changeDisabled, false);
  assert.equal(access.legacyChangeDisabled, true); assert.equal(access.resetDisabled, false);
  for (const key of FACE_CONTOUR_KEYS) for (const side of SLIM_FACE_SIDES) {
    const contour = fixture(); contour.resolved!.operations[FACE_CONTOUR_OPERATION][`/${key}/${side}`].value = -.2;
    contour.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'].value = .3;
    access = slimFaceAccess(contour, available, fences);
    assert.equal(access.contourActive, true); assert.equal(access.changeDisabled, true);
    assert.equal(access.replacementDisabled, true); assert.equal(access.resetDisabled, false);
    assert.match(access.replacementReason ?? '', /独立二维轮廓/);
    delete contour.resolved!.operations[FACE_CONTOUR_OPERATION][`/${key}/${side}`];
    assert.equal(slimFaceAccess(contour, available, fences).contourActive, null);
    assert.equal(slimFaceAccess(contour, available, fences).replacementDisabled, true);
  }
});

test('shared scope uses its own explicit link flag, never the selected face inheritance', () => {
  for (const scope of ['person', 'group', 'all_people'] as const) {
    const view = fixture();
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    let access = slimFaceAccess(view, available, fences);
    assert.equal(access.writeLinked, null); assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    assert.match(access.reason ?? '', /共享范围/);
    for (const linked of [false, true]) {
      view.editing_overrides[SLIM_FACE_OPERATION]['/linked'] = linked;
      access = slimFaceAccess(view, available, fences);
      assert.equal(access.writeLinked, linked); assert.equal(access.changeDisabled, false);
      assert.equal(access.reading.linked.value, true); assert.equal(access.reading.linked.override, linked);
    }
    view.editing_overrides[SLIM_FACE_OPERATION]['/linked'] = 1;
    assert.equal(slimFaceAccess(view, available, fences).writeLinked, null);
    assert.equal(slimFaceAccess(view, available, fences).changeDisabled, true);
  }
  assert.equal(slimFaceAccess(fixture(), available, fences).writeLinked, true);
});

test('missing, stale, malformed and conflicted new or legacy readback never becomes neutral', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved = null;}, view => {view.selected_face_id = null;}, view => {view.faces = [];},
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = 'other';}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .1;},
    view => {view.resolved!.face_ref.face_instance_id = 'other';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.faces[0].face_ref.analysis_revision = -1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;},
  ];
  for (const change of changes) {
    const view = fixture(); change(view); const access = slimFaceAccess(view, available, fences);
    for (const leaf of ['left', 'right', 'linked', 'legacy'] as const) assert.equal(access.reading[leaf].value, null);
    assert.equal(access.changeDisabled, true); assert.equal(access.replacementDisabled, true);
  }
  for (const [operation, path, leaf] of [[SLIM_FACE_OPERATION, '/left', 'left'], [SLIM_FACE_OPERATION, '/right', 'right'],
    [SLIM_FACE_OPERATION, '/linked', 'linked'], [LEGACY_SLIM_FACE_OPERATION, '/slim_face', 'legacy']] as const) {
    const missing = fixture(); delete missing.resolved!.operations[operation][path];
    assert.equal(slimFaceReading(missing)[leaf].value, null);
    for (const value of leaf === 'linked' ? [0, 1, 'true', NaN] : [true, '0', NaN, Infinity, -1.01, 1.01]) {
      const invalid = fixture(); invalid.resolved!.operations[operation][path].value = value;
      assert.equal(slimFaceReading(invalid)[leaf].value, null);
      assert.equal(slimFaceAccess(invalid, available, fences).changeDisabled, true);
    }
    const conflict = fixture(); conflict.resolved!.conflicts.push({operation_id: operation, parameter_path: path,
      reason: 'conflict', target_ids: ['group', 'other']});
    assert.equal(slimFaceReading(conflict)[leaf].value, null);
    assert.equal(slimFaceAccess(conflict, available, fences).changeDisabled, true);
    assert.equal(slimFaceAccess(conflict, available, fences).resetDisabled, false);
  }
  const sibling = fixture(); sibling.resolved!.conflicts.push({operation_id: FACE_CONTOUR_OPERATION,
    parameter_path: '/jaw/linked', reason: 'conflict', target_ids: []});
  assert.equal(slimFaceAccess(sibling, available, fences).changeDisabled, true);
  assert.equal(slimFaceAccess(sibling, available, fences).resetDisabled, false);
});

test('existing contour capability gates only new effects; valid legacy stays editable without native core', () => {
  for (const capability of [null, undefined, {}, {face_contour_available: false},
    {slim_face_available: true} as object, {brow_shape_protocol: 2} as object]) {
    const view = fixture(); view.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'].value = .3;
    const access = slimFaceAccess(view, capability, fences);
    assert.equal(access.core.available, false); assert.equal(access.changeDisabled, true);
    assert.equal(access.replacementDisabled, true); assert.equal(access.legacyChangeDisabled, false);
    assert.equal(access.resetDisabled, false);
  }
  assert.equal(slimFaceAccess(fixture(), {face_contour_available: false, face_contour_reason: 'exact native reason'}, fences).core.reason,
    'exact native reason');
});

test('neutral recovery requires current owner and target, not anatomy, selection, readings, links or native core', () => {
  const view = fixture(); view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved';
  view.resolved = null; view.selected_face_id = null;
  assert.equal(slimFaceAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null}; view.faces = [];
  assert.equal(slimFaceAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    const access = slimFaceAccess(fixture(), available, {...fences, ...change});
    for (const key of ['changeDisabled', 'replacementDisabled', 'legacyChangeDisabled', 'resetDisabled'] as const)
      assert.equal(access[key], true);
  }
  assert.match(slimFaceAccess(fixture(), available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('exact source, revision and own-property target fences also prevent resets to another owner', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = -1;},
    view => {view.revision = NaN;}, view => {view.association_revision = Infinity;},
    view => {view.editing_target!.target_id = 'other';}, view => {view.editing_target!.face_ref = null;},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;}, view => {view.editing_target!.face_ref!.asset_sha256 = 'foreign';},
    view => {view.editing_target = {scope: 'all_people', target_id: 'foreign', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'missing', face_ref: null};},
    view => {view.editing_target = {scope: 'person', target_id: 'toString', face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(slimFaceAccess(view, null, {...fences, faceOk: false}).resetDisabled, true);
  }
  const view = fixture(), face_ref = {...view.faces[0].face_ref, face_instance_id: 'face-b'};
  view.faces.push({...view.faces[0], face_ref}); view.editing_target = {scope: 'face', target_id: 'face-b', face_ref};
  const access = slimFaceAccess(view, available, fences);
  assert.equal(access.changeDisabled, true); assert.equal(access.writeLinked, null); assert.equal(access.resetDisabled, false);
});

test('unverified, synthetic and disabled faces cannot authorize new or historical nonzero changes', () => {
  for (const status of ['unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = status;
    const access = slimFaceAccess(view, available, fences);
    assert.equal(access.changeDisabled, true); assert.equal(access.legacyChangeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  const view = fixture(); view.faces[0].enabled = false;
  assert.equal(slimFaceAccess(view, available, fences).changeDisabled, true);
  assert.equal(slimFaceAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('source, target, selection, provenance and all related readback changes invalidate replacement drafts', () => {
  const initial = slimFaceBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.document_revision += 1;}, view => {view.binding.asset_sha256 = 'other';},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.faces[0].face_ref.analysis_revision += 1;}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[SLIM_FACE_OPERATION]['/right'].value = -.8;},
    view => {view.resolved!.operations[SLIM_FACE_OPERATION]['/linked'].value = false;},
    view => {view.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'].value = .4;},
    view => {view.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'].scope = 'group';},
    view => {view.resolved!.operations[LEGACY_SLIM_FACE_OPERATION]['/slim_face'].target_id = 'group';},
    view => {view.resolved!.operations[FACE_CONTOUR_OPERATION]['/temple/left'].value = .3;},
    view => {view.resolved!.conflicts.push({operation_id: SLIM_FACE_OPERATION, parameter_path: '/left', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[SLIM_FACE_OPERATION]['/linked'] = true;},
    view => {view.editing_overrides[LEGACY_SLIM_FACE_OPERATION]['/slim_face'] = .1;},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'clipped source footprint'}];},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null}; delete view.groups.group;},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(slimFaceBindingKey(view), initial);}
  const shared = fixture(); shared.editing_target = {scope: 'group', target_id: 'group', face_ref: null};
  const key = slimFaceBindingKey(shared); delete shared.groups.group;
  assert.notEqual(slimFaceBindingKey(shared), key);
  assert.equal(slimFaceBindingKey(null), 'unavailable');
});

test('readback and patch preparation do not mutate canonical people data or recipe input', () => {
  const view = fixture(), before = JSON.stringify(view), recipe = neutralSlimFace();
  const checked = checkSlimFace(recipe); checked.left = .4;
  assert.equal(recipe.left, 0);
  slimFaceReading(view); slimFaceAccess(view, available, fences); slimFaceBindingKey(view);
  slimFaceAdjustPatches('left', .2, true); slimFaceLinkPatch(false); slimFaceResetPatches();
  replaceLegacySlimFacePatches(-.2, .4, false); legacySlimFacePatch(0);
  assert.equal(JSON.stringify(view), before);
});
