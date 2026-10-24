// AUTHORED / UNRUN. Imports and fixtures have not been executed; no runtime or photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleView} from '../people/model.ts';
import {FACE_CONTOUR_OPERATION, FACE_CONTOUR_KEYS, FACE_CONTOUR_SIDES, FACE_CONTOUR_CONTROL_IDS,
  FACE_CONTOUR_CONTROL_PATHS, FACE_CONTOUR_SOURCE, checkFaceContour, neutralFaceContour,
  faceContourAccess, faceContourAdjustPatches, faceContourAmountPatch, faceContourBindingKey,
  faceContourLinkPatch, faceContourReading, faceContourReadiness, faceContourResetPatches,
  faceContourTargetReady, type FaceContourFences, type FaceContourKey, type FaceContourSide} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  const values = Object.fromEntries(FACE_CONTOUR_KEYS.flatMap(key => [
    [`/${key}/left`, {value: -.25, scope: 'face' as const, target_id: 'face-a', overridden: true}],
    [`/${key}/right`, {value: .4, scope: 'group' as const, target_id: 'group', overridden: false}],
    [`/${key}/linked`, {value: true, scope: 'default' as const, target_id: null, overridden: false}],
  ]));
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}}, persons: {person: {anonymous: true}}, links: [],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    editing_overrides: {[FACE_CONTOUR_OPERATION]: {'/temple/left': -.25}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [FACE_CONTOUR_OPERATION]: values,
      'lnx.deform.v1': {'/slim_face': {value: .8, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const fences: FaceContourFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const available = {face_contour_available: true};

test('exact three handbook leaves, subject-side recipe and strict signed finite domain', () => {
  assert.equal(FACE_CONTOUR_OPERATION, 'lnx.face_contour.v1');
  assert.deepEqual(FACE_CONTOUR_KEYS, ['temple', 'cheekbone', 'jaw']);
  assert.deepEqual(FACE_CONTOUR_SIDES, ['left', 'right']);
  assert.deepEqual(FACE_CONTOUR_CONTROL_IDS, {temple: 'LNX-REF-PC-32466-C-94bf91612d',
    cheekbone: 'LNX-REF-PC-32466-C-d24d97d234', jaw: 'LNX-REF-PC-32466-C-3bc7e245b7'});
  assert.deepEqual(FACE_CONTOUR_CONTROL_PATHS, {temple: '脸型/太阳穴', cheekbone: '脸型/颧骨', jaw: '脸型/下颌'});
  assert.equal(FACE_CONTOUR_SOURCE, 'https://wiki.pixcakeai.com/guide/9405.html');
  assert.deepEqual(neutralFaceContour(), {version: 1, temple: {linked: true, left: 0, right: 0},
    cheekbone: {linked: true, left: 0, right: 0}, jaw: {linked: true, left: 0, right: 0}});
  for (const key of FACE_CONTOUR_KEYS) for (const side of FACE_CONTOUR_SIDES) {
    for (const value of [-1, -.5, -.01, 0, .01, .5, 1]) {
      const recipe = neutralFaceContour(); recipe[key][side] = value;
      assert.deepEqual(checkFaceContour(recipe), recipe);
      assert.deepEqual(faceContourAmountPatch(key, side, value), {operation_id: FACE_CONTOUR_OPERATION,
        parameter_path: `/${key}/${side}`, unset: false, value});
    }
    for (const invalid of [-1.01, 1.01, NaN, Infinity, -Infinity, '0', null, true, {}]) {
      assert.throws(() => faceContourAmountPatch(key, side, invalid as number));
      const recipe = neutralFaceContour(); recipe[key][side] = invalid as number;
      assert.throws(() => checkFaceContour(recipe));
    }
  }
  for (const value of [null, undefined, [], {}, {...neutralFaceContour(), version: 2},
    {...neutralFaceContour(), slim_face: 0}, {...neutralFaceContour(), jaw: {left: 0, right: 0}},
    {...neutralFaceContour(), temple: {linked: 1, left: 0, right: 0}},
    {...neutralFaceContour(), cheekbone: {linked: false, left: 0, right: 0, extra: 0}}]) assert.throws(() => checkFaceContour(value));
  for (const key of ['slim_face', 'small_chin', 'version', 'temple/left', '']) {
    assert.throws(() => faceContourAmountPatch(key as FaceContourKey, 'left', .2));
    assert.throws(() => faceContourLinkPatch(key as FaceContourKey, true));
    assert.throws(() => faceContourResetPatches(key as FaceContourKey));
  }
  for (const side of ['viewer_left', 'linked', 'both', '']) assert.throws(() => faceContourAmountPatch('jaw', side as FaceContourSide, .2));
});

test('link-only toggles preserve unequal values; next linked adjustment patches exactly both sides', () => {
  for (const key of FACE_CONTOUR_KEYS) {
    for (const linked of [true, false]) assert.deepEqual(faceContourLinkPatch(key, linked), {
      operation_id: FACE_CONTOUR_OPERATION, parameter_path: `/${key}/linked`, unset: false, value: linked,
    });
    for (const side of FACE_CONTOUR_SIDES) {
      assert.deepEqual(faceContourAdjustPatches(key, side, -.6, false), [faceContourAmountPatch(key, side, -.6)]);
      assert.deepEqual(faceContourAdjustPatches(key, side, .7, true), [
        faceContourAmountPatch(key, 'left', .7), faceContourAmountPatch(key, 'right', .7)]);
      assert.deepEqual(faceContourAdjustPatches(key, side, 0, true), [
        faceContourAmountPatch(key, 'left', 0), faceContourAmountPatch(key, 'right', 0)]);
    }
    for (const invalid of [1, 0, 'true', null, undefined]) {
      assert.throws(() => faceContourLinkPatch(key, invalid as boolean));
      assert.throws(() => faceContourAdjustPatches(key, 'left', .2, invalid as boolean));
    }
  }
});

test('family neutral recovery is exactly six numeric leaves and preserves sparse inherited link flags', () => {
  const view = fixture(), before = JSON.stringify(view), patches = faceContourResetPatches();
  assert.equal(patches.length, 6);
  assert.deepEqual(patches, FACE_CONTOUR_KEYS.flatMap(key => FACE_CONTOUR_SIDES.map(side => faceContourAmountPatch(key, side, 0))));
  assert.equal(patches.some(patch => patch.parameter_path.endsWith('/linked')), false);
  assert.equal(patches.some(patch => patch.unset), false);
  for (const key of FACE_CONTOUR_KEYS) assert.deepEqual(faceContourResetPatches(key), [
    faceContourAmountPatch(key, 'left', 0), faceContourAmountPatch(key, 'right', 0)]);
  assert.notEqual(faceContourResetPatches(), patches);
  assert.equal(JSON.stringify(view), before);
});

test('selected effective numbers and link provenance never become shared-target readback', () => {
  const view = fixture(); view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[FACE_CONTOUR_OPERATION] = {'/temple/left': .9, '/temple/linked': false};
  const reading = faceContourReading(view, 'temple');
  assert.equal(reading.left.value, -.25); assert.equal(reading.left.override, .9);
  assert.equal(reading.right.value, .4); assert.equal(reading.right.overridePresent, false);
  assert.equal(reading.linked.value, true); assert.equal(reading.linked.override, false);
  assert.equal(reading.left.source?.scope, 'face'); assert.equal(reading.right.source?.scope, 'group');
  assert.equal(faceContourAccess(view, 'temple', available, fences).writeLinked, false);
  assert.equal(faceContourAccess(view, 'temple', available, fences).changeDisabled, false);
});

test('shared person/group/all scopes require their own explicit link choice rather than borrowing one face', () => {
  for (const scope of ['person', 'group', 'all_people'] as const) for (const key of FACE_CONTOUR_KEYS) {
    const view = fixture(); view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    let access = faceContourAccess(view, key, available, fences);
    assert.equal(access.writeLinked, null); assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    assert.match(access.reason ?? '', /共享范围/);
    for (const linked of [false, true]) {
      view.editing_overrides[FACE_CONTOUR_OPERATION][`/${key}/linked`] = linked;
      access = faceContourAccess(view, key, available, fences);
      assert.equal(access.writeLinked, linked); assert.equal(access.changeDisabled, false);
    }
    view.editing_overrides[FACE_CONTOUR_OPERATION][`/${key}/linked`] = 1;
    access = faceContourAccess(view, key, available, fences);
    assert.equal(access.writeLinked, null); assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
  }
  assert.equal(faceContourAccess(fixture(), 'jaw', available, fences).writeLinked, true);
});

test('missing, stale, invalid or conflicted readback stays unavailable rather than zero', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved = null;}, view => {view.selected_face_id = null;}, view => {view.faces = [];},
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .1;},
    view => {view.resolved!.face_ref.face_instance_id = 'other';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.faces[0].face_ref.analysis_revision = -1;}, view => {view.resolved!.state_revision += 1;},
    view => {view.resolved!.association_revision += 1;}, view => {delete view.resolved!.operations[FACE_CONTOUR_OPERATION];},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    for (const key of FACE_CONTOUR_KEYS) {
      const reading = faceContourReading(view, key);
      assert.equal(reading.left.value, null); assert.equal(reading.right.value, null); assert.equal(reading.linked.value, null);
      assert.equal(faceContourAccess(view, key, available, fences).changeDisabled, true);
    }
  }
  for (const key of FACE_CONTOUR_KEYS) for (const leaf of ['left', 'right', 'linked'] as const) {
    const path = `/${key}/${leaf}`, view = fixture();
    view.resolved!.conflicts.push({operation_id: FACE_CONTOUR_OPERATION, parameter_path: path, reason: 'conflict', target_ids: []});
    assert.equal(faceContourReading(view, key)[leaf].value, null);
    assert.equal(faceContourAccess(view, key, available, fences).changeDisabled, true);
    assert.equal(faceContourAccess(view, key, available, fences).resetDisabled, false);
    const missing = fixture(); delete missing.resolved!.operations[FACE_CONTOUR_OPERATION][path];
    assert.equal(faceContourReading(missing, key)[leaf].value, null);
    for (const value of leaf === 'linked' ? [0, 1, 'true', NaN] : [true, '0', NaN, Infinity, -1.01, 1.01]) {
      const invalid = fixture(); invalid.resolved!.operations[FACE_CONTOUR_OPERATION][path].value = value;
      assert.equal(faceContourReading(invalid, key)[leaf].value, null);
    }
  }
});

test('a sibling contour conflict blocks nonzero work but not atomic neutral recovery', () => {
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: FACE_CONTOUR_OPERATION, parameter_path: '/jaw/right', reason: 'conflict', target_ids: []});
  assert.equal(faceContourReading(view, 'temple').left.value, -.25);
  assert.equal(faceContourAccess(view, 'temple', available, fences).changeDisabled, true);
  assert.equal(faceContourAccess(view, 'temple', available, fences).resetDisabled, false);
});

test('dedicated capability is required for effect, never for neutral recovery', () => {
  for (const capability of [undefined, null, {}, {face_contour_available: false},
    {skin_texture_available: true} as object, {brow_shape_protocol: 2} as object]) {
    assert.equal(faceContourReadiness(capability).available, false);
    for (const key of FACE_CONTOUR_KEYS) {
      const access = faceContourAccess(fixture(), key, capability, fences);
      assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, false);
    }
  }
  assert.equal(faceContourReadiness({face_contour_available: false, face_contour_reason: 'exact core reason'}).reason, 'exact core reason');
  for (const key of FACE_CONTOUR_KEYS) assert.equal(faceContourAccess(fixture(), key, available, fences).changeDisabled, false);
});

test('neutral recovery survives missing anatomy, selected face and readback under valid shared ownership', () => {
  const view = fixture(); view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved';
  view.faces[0].face_ref.analysis_revision = 0; view.editing_target!.face_ref!.analysis_revision = 0;
  view.resolved = null; view.selected_face_id = null;
  for (const key of FACE_CONTOUR_KEYS) {
    assert.equal(faceContourTargetReady(view), true);
    assert.equal(faceContourAccess(view, key, null, {...fences, faceOk: false}).resetDisabled, false);
    assert.equal(faceContourAccess(view, key, null, {...fences, faceOk: false}).changeDisabled, true);
  }
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null}; view.faces = [];
  for (const key of FACE_CONTOUR_KEYS) assert.equal(faceContourAccess(view, key, null, {...fences, faceOk: false}).resetDisabled, false);
});

test('source, revision, exact face and own-property target fences also protect neutral recovery', () => {
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
  for (const change of changes) {const view = fixture(); change(view); assert.equal(faceContourTargetReady(view), false);
    for (const key of FACE_CONTOUR_KEYS) assert.equal(faceContourAccess(view, key, null, {...fences, faceOk: false}).resetDisabled, true);
  }
  const otherFace = fixture();
  const face_ref = {...otherFace.faces[0].face_ref, face_instance_id: 'face-b'};
  otherFace.faces.push({...otherFace.faces[0], face_ref});
  otherFace.editing_target = {scope: 'face', target_id: 'face-b', face_ref};
  assert.equal(faceContourTargetReady(otherFace), true);
  assert.equal(faceContourAccess(otherFace, 'jaw', available, fences).changeDisabled, true);
  assert.equal(faceContourAccess(otherFace, 'jaw', available, fences).writeLinked, null);
  assert.equal(faceContourAccess(otherFace, 'jaw', available, fences).resetDisabled, false);
});

test('unresolved, synthetic or disabled selection never authorizes nonzero effects', () => {
  for (const status of ['unresolved', 'synthetic'] as const) {
    const view = fixture(); view.faces[0].analysis_status = status;
    assert.equal(faceContourAccess(view, 'jaw', available, fences).changeDisabled, true);
    assert.equal(faceContourAccess(view, 'jaw', available, fences).resetDisabled, false);
  }
  const view = fixture(); view.faces[0].enabled = false;
  assert.equal(faceContourAccess(view, 'temple', available, fences).changeDisabled, true);
  assert.equal(faceContourAccess(fixture(), 'temple', available, {...fences, faceOk: false}).changeDisabled, true);
});

test('pending, uncertain, external queue and disabled-owner fences cover changes, link choices and reset', () => {
  for (const change of [{pending: true}, {uncertain: true}, {externalBusy: true}, {enabled: false}]) {
    for (const key of FACE_CONTOUR_KEYS) {
      const access = faceContourAccess(fixture(), key, available, {...fences, ...change});
      assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
    }
  }
  assert.match(faceContourAccess(fixture(), 'jaw', available, {...fences, uncertain: true}).reason ?? '', /原请求/);
});

test('source/target/revision/selection/status/value/link/refusal changes invalidate stale drafts', () => {
  const initial = faceContourBindingKey(fixture());
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_id = 'other';}, view => {view.binding.document_epoch = 'other';},
    view => {view.binding.document_revision += 1;}, view => {view.binding.asset_sha256 = 'other';},
    view => {view.revision += 1;}, view => {view.association_revision += 1;}, view => {view.selected_face_id = null;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.faces[0].face_ref.analysis_revision += 1;}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {view.resolved!.operations[FACE_CONTOUR_OPERATION]['/jaw/right'].value = -.8;},
    view => {view.resolved!.operations[FACE_CONTOUR_OPERATION]['/temple/linked'].value = false;},
    view => {view.resolved!.conflicts.push({operation_id: FACE_CONTOUR_OPERATION, parameter_path: '/jaw/left', reason: 'conflict', target_ids: []});},
    view => {view.editing_overrides[FACE_CONTOUR_OPERATION]['/cheekbone/linked'] = true;},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'temple.left: clipped support'}];},
  ];
  for (const change of changes) {const view = fixture(); change(view); assert.notEqual(faceContourBindingKey(view), initial);}
  assert.equal(faceContourBindingKey(null), 'unavailable');
});

test('reading and patch preparation never mutate canonical people facts or recipe inputs', () => {
  const view = fixture(), before = JSON.stringify(view), recipe = neutralFaceContour(); recipe.jaw.linked = false;
  const checked = checkFaceContour(recipe); checked.temple.left = .7;
  assert.equal(recipe.temple.left, 0);
  for (const key of FACE_CONTOUR_KEYS) {
    faceContourReading(view, key); faceContourAccess(view, key, available, fences);
    faceContourAdjustPatches(key, 'left', .2, true); faceContourLinkPatch(key, false); faceContourResetPatches(key);
  }
  faceContourBindingKey(view); faceContourResetPatches();
  assert.equal(JSON.stringify(view), before);
});
