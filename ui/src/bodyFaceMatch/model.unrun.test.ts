// AUTHORED / UNRUN. No imports, fixtures, UI, native processing or photograph acceptance were executed.
import {test} from 'node:test';
import {ownFaceReferenceFixture} from './fixtures.unrun.ts';
import assert from 'node:assert/strict';
import type {PeopleView, ResolvedParameter} from '../people/model.ts';
import {BODY_FACE_MATCH_OPERATION, BODY_FACE_MATCH_CONTROL_ID, BODY_FACE_MATCH_CONTROL_PATH,
  BODY_FACE_MATCH_SOURCE, BODY_FACE_MATCH_LABEL, checkBodyFaceMatch, neutralBodyFaceMatch,
  bodyFaceMatchReadiness, bodyFaceMatchReading, bodyFaceMatchTargetReady, bodyFaceMatchSelectionMatches,
  bodyFaceMatchAccess, bodyFaceMatchBindingKey, bodyFaceMatchReviewed, bodyFaceMatchPatch, bodyFaceMatchResetPatches,
  parseBodyFaceMatchChoice, type BodyFaceMatchFences} from './model.ts';

function fixture(): PeopleView {
  const face_ref = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 3};
  return {binding: {document_id: 'doc', document_epoch: 'epoch', document_revision: 7, asset_sha256: face_ref.asset_sha256},
    revision: 5, association_revision: 2,
    faces: [{face_ref, enabled: true, box: [.1, .1, .6, .8], manual: false, analysis_status: 'verified'},
      {face_ref: {...face_ref, face_instance_id: 'face-b'}, enabled: true, box: [.65, .1, .9, .8], manual: false, analysis_status: 'verified'}],
    groups: {group: {label: 'Group', priority: 1, face_ids: ['face-a']}, other: {label: 'Other', priority: 2, face_ids: ['face-b']}},
    persons: {person: {anonymous: true}},
    links: [{face_instance_id: 'face-a', person_id: 'person', state: 'confirmed', confirmation_revision: 2}],
    selected_face_id: 'face-a', editing_target: {scope: 'face', target_id: 'face-a', face_ref: {...face_ref}},
    body_face_match: {family: 'body_face_match', operation_id: 'lnx.body_face_match.v1', attached: true,
      own_face_reference: ownFaceReferenceFixture(face_ref), needs_review: false, face_ref: {...face_ref}, source: {sha256: face_ref.asset_sha256, width: 600, height: 800}},
    editing_overrides: {[BODY_FACE_MATCH_OPERATION]: {'/amount': .35}},
    resolved: {face_ref: {...face_ref}, state_revision: 5, association_revision: 2, conflicts: [], operations: {
      [BODY_FACE_MATCH_OPERATION]: {'/amount': {value: .35, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_colour.v1': {'/temperature': {value: .3, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_finish.v1': {'/whitening': {value: .7, scope: 'face', target_id: 'face-a', overridden: true}},
      'lnx.skin_texture.v1': {'/texture': {value: -.4, scope: 'face', target_id: 'face-a', overridden: true}},
    }}};
}
const available = {body_face_match_available: true};
const fences: BodyFaceMatchFences = {enabled: true, pending: false, uncertain: false, externalBusy: false, faceOk: true};
const resolvedAmount = (view: PeopleView) => view.resolved!.operations[BODY_FACE_MATCH_OPERATION]['/amount'];

test('one exact partial leaf, honest visible label, independent strict finite amount recipe', () => {
  assert.equal(BODY_FACE_MATCH_OPERATION, 'lnx.body_face_match.v1');
  assert.equal(BODY_FACE_MATCH_CONTROL_ID, 'LNX-REF-PC-32465-C-d8b09012a9');
  assert.equal(BODY_FACE_MATCH_CONTROL_PATH, '肤色统一（身体）');
  assert.equal(BODY_FACE_MATCH_SOURCE, 'https://www.pixcakeai.com/guide/32465');
  assert.equal(BODY_FACE_MATCH_LABEL, '身体向本人脸部色度匹配（手绘审核）');
  assert.deepEqual(neutralBodyFaceMatch(), {version: 1, amount: 0});
  for (const amount of [0, .01, .25, .8, 1]) {
    const recipe = {version: 1, amount};
    assert.deepEqual(checkBodyFaceMatch(recipe), recipe);
    assert.notEqual(checkBodyFaceMatch(recipe), recipe);
    assert.deepEqual(bodyFaceMatchPatch(amount), {operation_id: BODY_FACE_MATCH_OPERATION,
      parameter_path: '/amount', unset: false, value: amount});
  }
  for (const amount of [-1, -.01, 1.01, NaN, Infinity, -Infinity, '0.3', null, true, {}]) {
    assert.throws(() => checkBodyFaceMatch({version: 1, amount}));
    assert.throws(() => bodyFaceMatchPatch(amount as number));
  }
  for (const recipe of [null, [], {}, {version: 2, amount: 0}, {version: '1', amount: 0}, {amount: 0},
    {version: 1}, {version: 1, amount: 0, brightness: 0}, {version: 1, strength: .5},
    {version: 1, broad_gain: 0}, {version: 1, temperature: .5}]) assert.throws(() => checkBodyFaceMatch(recipe));
});

test('blank or invalid choice is not an implicit zero, clamp or copied inherited amount', () => {
  for (const text of ['', ' ', '-', '+', '.', '-0', '-1', '101', 'NaN', 'Infinity', '0x10', '30%', '1 2', '1,5']) {
    assert.equal(parseBodyFaceMatchChoice(text), null);
  }
  for (const [text, value] of [['0', 0], ['100', 1], [' 25 ', .25], ['12.5', .125], ['.5', .005], ['+50', .5], ['1e2', 1]] as const) {
    assert.equal(parseBodyFaceMatchChoice(text), value);
  }
});

test('neutral recovery is exactly one explicit amount zero without legacy or adjacent changes', () => {
  assert.deepEqual(bodyFaceMatchResetPatches(), [{operation_id: BODY_FACE_MATCH_OPERATION,
    parameter_path: '/amount', unset: false, value: 0}]);
  assert.notEqual(bodyFaceMatchResetPatches(), bodyFaceMatchResetPatches());
});

test('first use stages review but cannot directly persist active amount without its own support', () => {
  const view = fixture(); delete view.body_face_match;
  const access = bodyFaceMatchAccess(view, available, fences);
  assert.equal(access.reviewDisabled, false); assert.equal(access.changeDisabled, true);
  assert.equal(access.reviewed, false); assert.equal(access.resetDisabled, false);
  view.skin_body = {attached: true, needs_review: false, face_ref: {...view.faces[0].face_ref},
    source: {sha256: view.binding.asset_sha256, width: 600, height: 800}};
  view.skin_finish_body = {...view.skin_body, family: 'skin_finish', operation_id: 'lnx.skin_finish.v1'};
  view.body_skin_evenness = {...view.skin_body, family: 'body_skin_evenness', operation_id: 'lnx.body_skin_evenness.v1'};
  assert.equal(bodyFaceMatchReviewed(view), false);
  assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
});

test('body attachment must be the current exact family, source, face and valid review', () => {
  const mutations: ((view: PeopleView) => void)[] = [
    view => {delete view.body_face_match;}, view => {view.body_face_match = null;},
    view => {view.body_face_match!.family = 'skin_finish';},
    view => {view.body_face_match!.operation_id = 'lnx.skin_colour.v1';},
    view => {delete view.body_face_match!.family;}, view => {delete view.body_face_match!.operation_id;},
    view => {view.body_face_match!.attached = false;}, view => {view.body_face_match!.needs_review = true;},
    view => {delete view.body_face_match!.needs_review;},
    view => {delete view.body_face_match!.own_face_reference;},
    view => {view.body_face_match!.own_face_reference = null;},
    view => {view.body_face_match!.own_face_reference!.face_ref.face_instance_id = 'donor';},
    view => {view.body_face_match!.own_face_reference!.face_ref.analysis_revision++;},
    view => {view.body_face_match!.own_face_reference!.face_skin_observation.source_sha256 = 'b'.repeat(64);},
    view => {view.body_face_match!.own_face_reference!.landmark_digest = 'bad';},
    view => {view.body_face_match!.face_ref.face_instance_id = 'face-b';},
    view => {view.body_face_match!.face_ref.analysis_revision++;},
    view => {view.body_face_match!.source.sha256 = 'b'.repeat(64);},
  ];
  for (const mutate of mutations) {
    const view = fixture(); mutate(view);
    assert.equal(bodyFaceMatchReviewed(view), false);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
    assert.equal(bodyFaceMatchAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(bodyFaceMatchReviewed(fixture()), true);
});

test('selected-face authority and explicit shared intent remain independent', () => {
  const view = fixture();
  view.editing_target = {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null};
  view.editing_overrides[BODY_FACE_MATCH_OPERATION]['/amount'] = .8;
  const access = bodyFaceMatchAccess(view, available, fences);
  assert.equal(access.reading.value, .35); assert.equal(access.reading.source?.target_id, 'face-a');
  assert.equal(access.reading.override, .8); assert.equal(access.editValue, .8);
  delete view.editing_overrides[BODY_FACE_MATCH_OPERATION]['/amount'];
  assert.equal(bodyFaceMatchAccess(view, available, fences).editValue, null);
  assert.equal(bodyFaceMatchReading(view).overridePresent, false);
  assert.equal(bodyFaceMatchReading(view).value, .35);
  view.editing_overrides[BODY_FACE_MATCH_OPERATION]['/amount'] = 0;
  assert.equal(bodyFaceMatchReading(view).overridePresent, true);
  assert.equal(bodyFaceMatchAccess(view, available, fences).editValue, 0);
  view.editing_overrides[BODY_FACE_MATCH_OPERATION]['/amount'] = 'invalid';
  assert.equal(bodyFaceMatchReading(view).overridePresent, true);
  assert.equal(bodyFaceMatchReading(view).override, null);
  assert.equal(bodyFaceMatchAccess(view, available, fences).editValue, null);
  assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, false);
});

test('only a face target may use its own inherited amount instead of a deliberate blank choice', () => {
  const view = fixture(); delete view.editing_overrides[BODY_FACE_MATCH_OPERATION];
  assert.equal(bodyFaceMatchAccess(view, available, fences).editValue, .35);
  for (const scope of ['group', 'person', 'all_people'] as const) {
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(bodyFaceMatchAccess(view, available, fences).editValue, null);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, false);
  }
});

test('current owned default/all/group/person/face provenance is returned, not replaced by local intent', () => {
  for (const scope of ['default', 'all_people', 'group', 'person', 'face'] as const) {
    const view = fixture();
    const source = {value: .2, scope, target_id: scope === 'default' ? null
      : scope === 'all_people' ? view.binding.asset_sha256 : scope === 'face' ? 'face-a' : scope, overridden: scope === 'face'};
    view.resolved!.operations[BODY_FACE_MATCH_OPERATION]['/amount'] = source;
    assert.equal(bodyFaceMatchReading(view).source, source);
    assert.equal(bodyFaceMatchReading(view).value, .2);
    assert.equal(bodyFaceMatchReading(view).override, .35);
  }
});

test('foreign, disowned and nonmember readback provenance is unknown, never fabricated neutral', () => {
  const sources: ResolvedParameter[] = [
    {value: .2, scope: 'default', target_id: 'face-a', overridden: false},
    {value: .2, scope: 'all_people', target_id: 'b'.repeat(64), overridden: false},
    {value: .2, scope: 'face', target_id: 'face-b', overridden: true},
    {value: .2, scope: 'group', target_id: 'other', overridden: true},
    {value: .2, scope: 'group', target_id: 'absent', overridden: true},
    {value: .2, scope: 'group', target_id: 'toString', overridden: true},
    {value: .2, scope: 'person', target_id: 'absent', overridden: true},
    {value: .2, scope: 'group', target_id: 'group', contributing_targets: ['group', 'other'], overridden: true},
  ];
  for (const source of sources) {const view = fixture();
    view.resolved!.operations[BODY_FACE_MATCH_OPERATION]['/amount'] = source;
    assert.equal(bodyFaceMatchReading(view).value, null);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
    assert.equal(bodyFaceMatchAccess(view, available, fences).resetDisabled, false);
  }
  const view = fixture();
  view.resolved!.operations[BODY_FACE_MATCH_OPERATION]['/amount'] = {
    value: .2, scope: 'person', target_id: 'person', overridden: true};
  view.links[0].state = 'candidate'; assert.equal(bodyFaceMatchReading(view).value, null);
  view.links[0].state = 'confirmed'; view.links[0].confirmation_revision = 3;
  assert.equal(bodyFaceMatchReading(view).value, null);
});

test('missing, stale, conflicted and invalid authoritative values remain unknown', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.resolved = null;}, view => {view.selected_face_id = null;}, view => {view.selected_face_id = 'absent';},
    view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;},
    view => {view.faces[0].face_ref.analysis_revision = -1;},
    view => {view.resolved!.face_ref.asset_sha256 = 'b'.repeat(64);},
    view => {view.resolved!.face_ref.face_instance_id = 'face-b';}, view => {view.resolved!.face_ref.analysis_revision += 1;},
    view => {view.resolved!.state_revision += 1;}, view => {view.resolved!.association_revision += 1;},
    view => {delete view.resolved!.operations[BODY_FACE_MATCH_OPERATION];},
    view => {delete view.resolved!.operations[BODY_FACE_MATCH_OPERATION]['/amount'];},
    view => {view.resolved!.conflicts.push({operation_id: BODY_FACE_MATCH_OPERATION, parameter_path: '/amount', reason: 'tie', target_ids: ['g1', 'g2']});},
  ];
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(bodyFaceMatchReading(view).value, null);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
  }
  for (const value of [-.1, 1.1, NaN, Infinity, '0.4', false]) {const view = fixture();
    resolvedAmount(view).value = value; assert.equal(bodyFaceMatchReading(view).value, null);
  }
  const view = fixture();
  view.resolved!.conflicts.push({operation_id: 'lnx.skin_finish.v1', parameter_path: '/whitening', reason: 'tie', target_ids: []});
  assert.equal(bodyFaceMatchReading(view).value, .35);
  assert.equal(bodyFaceMatchReading(null).value, null); assert.equal(bodyFaceMatchReading(undefined).value, null);
});

test('active writes require current preview membership, not merely existence of the edit target', () => {
  const view = fixture();
  view.editing_target = {scope: 'face', target_id: 'face-b', face_ref: {...view.faces[1].face_ref}};
  assert.equal(bodyFaceMatchTargetReady(view), true); assert.equal(bodyFaceMatchSelectionMatches(view), false);
  assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
  assert.equal(bodyFaceMatchAccess(view, available, fences).resetDisabled, false);
  view.editing_target = {scope: 'group', target_id: 'other', face_ref: null};
  assert.equal(bodyFaceMatchSelectionMatches(view), false);
  view.editing_target.target_id = 'group'; assert.equal(bodyFaceMatchSelectionMatches(view), true);
  view.groups.group.face_ids = []; assert.equal(bodyFaceMatchSelectionMatches(view), false);
  view.editing_target = {scope: 'person', target_id: 'person', face_ref: null};
  assert.equal(bodyFaceMatchSelectionMatches(view), true);
  for (const state of ['candidate', 'rejected', 'unresolved'] as const) {
    view.links[0].state = state; assert.equal(bodyFaceMatchSelectionMatches(view), false);
  }
  view.links[0].state = 'confirmed';
  for (const confirmation of [null, -1, .5, 3]) {
    view.links[0].confirmation_revision = confirmation; assert.equal(bodyFaceMatchSelectionMatches(view), false);
  }
  view.links[0].confirmation_revision = 2; delete view.persons.person;
  assert.equal(bodyFaceMatchSelectionMatches(view), false);
});

test('dedicated capability and verified anatomy are admission gates, not source-quality proof', () => {
  assert.deepEqual(bodyFaceMatchReadiness(available), {available: true});
  assert.deepEqual(bodyFaceMatchReadiness({body_face_match_available: false, body_face_match_reason: 'missing core'}),
    {available: false, reason: 'missing core'});
  for (const capability of [null, undefined, {}, {body_face_match_available: false}]) {
    assert.equal(bodyFaceMatchAccess(fixture(), capability, fences).changeDisabled, true);
    assert.equal(bodyFaceMatchAccess(fixture(), capability, fences).resetDisabled, false);
  }
  for (const change of [(view: PeopleView) => {view.faces[0].enabled = false;},
    (view: PeopleView) => {view.faces[0].analysis_status = 'unresolved';},
    (view: PeopleView) => {view.faces[0].analysis_status = 'synthetic';}]) {
    const view = fixture(); change(view);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
    assert.equal(bodyFaceMatchAccess(view, available, fences).resetDisabled, false);
  }
  assert.equal(bodyFaceMatchAccess(fixture(), available, {...fences, faceOk: false}).changeDisabled, true);
});

test('neutral recovery needs ownership but not selected preview, valid reading, anatomy or core', () => {
  const view = fixture(); view.resolved = null; view.selected_face_id = null;
  view.faces[0].enabled = false; view.faces[0].analysis_status = 'unresolved';
  view.faces[0].face_ref.analysis_revision = 0; view.editing_target!.face_ref!.analysis_revision = 0;
  assert.equal(bodyFaceMatchTargetReady(view), true);
  assert.equal(bodyFaceMatchAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  for (const scope of ['group', 'person', 'all_people'] as const) {
    view.editing_target = {scope, target_id: scope === 'all_people' ? view.binding.asset_sha256 : scope, face_ref: null};
    view.faces = [];
    assert.equal(bodyFaceMatchTargetReady(view), true);
    assert.equal(bodyFaceMatchAccess(view, null, {...fences, faceOk: false}).resetDisabled, false);
  }
});

test('active and neutral writes both retain source, owner, revision and concurrent-work fences', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.editing_target = null;}, view => {view.binding.document_id = '';}, view => {view.binding.document_epoch = '';},
    view => {view.binding.asset_sha256 = '';}, view => {view.binding.document_revision = NaN;},
    view => {view.revision = -1;}, view => {view.association_revision = .5;}, view => {view.faces = [];},
    view => {view.editing_target!.target_id = 'absent';}, view => {view.editing_target!.face_ref = null;},
    view => {view.editing_target!.face_ref!.analysis_revision += 1;},
    view => {view.editing_target!.face_ref!.asset_sha256 = 'b'.repeat(64);},
    view => {view.editing_target = {scope: 'all_people', target_id: 'b'.repeat(64), face_ref: null};},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: {...view.faces[0].face_ref}};},
    view => {view.editing_target = {scope: 'person', target_id: 'person', face_ref: {...view.faces[0].face_ref}};},
  ];
  for (const scope of ['group', 'person'] as const) for (const id of ['', 'absent', 'toString', '__proto__']) {
    changes.push(view => {view.editing_target = {scope, target_id: id, face_ref: null};});
  }
  for (const change of changes) {const view = fixture(); change(view);
    assert.equal(bodyFaceMatchTargetReady(view), false);
    assert.equal(bodyFaceMatchAccess(view, null, {...fences, faceOk: false}).resetDisabled, true);
    assert.equal(bodyFaceMatchAccess(view, available, fences).changeDisabled, true);
  }
  for (const patch of [{enabled: false}, {pending: true}, {uncertain: true}, {externalBusy: true}]) {
    const access = bodyFaceMatchAccess(fixture(), available, {...fences, ...patch});
    assert.equal(access.changeDisabled, true); assert.equal(access.resetDisabled, true);
  }
});

test('source, target, membership, provenance and refusal changes invalidate drafts without graph mutations', () => {
  const changes: ((view: PeopleView) => void)[] = [
    view => {view.binding.document_epoch = 'new';}, view => {view.binding.document_id = 'new';},
    view => {view.binding.asset_sha256 = 'b'.repeat(64);}, view => {view.binding.document_revision += 1;},
    view => {view.revision += 1;}, view => {view.association_revision += 1;},
    view => {view.selected_face_id = 'face-b';}, view => {view.faces[0].enabled = false;},
    view => {view.faces[0].analysis_status = 'unresolved';}, view => {view.faces[0].face_ref.analysis_revision += 1;},
    view => {view.editing_target = {scope: 'group', target_id: 'group', face_ref: null};},
    view => {view.groups.group.face_ids = [];}, view => {delete view.persons.person;}, view => {view.links = [];},
    view => {resolvedAmount(view).value = .4;}, view => {resolvedAmount(view).scope = 'group';},
    view => {resolvedAmount(view).contributing_targets = ['group'];},
    view => {view.editing_overrides[BODY_FACE_MATCH_OPERATION]['/amount'] = .9;},
    view => {view.body_face_match!.needs_review = true;},
    view => {view.body_face_match!.reason = 'Body analysis changed';},
    view => {view.body_face_match!.own_face_reference!.landmark_digest = 'f'.repeat(64);},
    view => {view.body_face_match!.own_face_reference!.face_skin_observation.semantic_model_sha256 = 'f'.repeat(64);},
    view => {view.body_face_match!.attached = false;},
    view => {view.resolved!.conflicts.push({operation_id: BODY_FACE_MATCH_OPERATION, parameter_path: '/amount', reason: 'tie', target_ids: []});},
    view => {view.refusals = [{face_instance_id: 'face-a', reason: 'support unavailable'}];},
  ];
  for (const change of changes) {const view = fixture(), key = bodyFaceMatchBindingKey(view); change(view);
    assert.notEqual(bodyFaceMatchBindingKey(view), key);
  }
  const view = fixture(), before = JSON.stringify(view);
  bodyFaceMatchAccess(view, available, fences); bodyFaceMatchReading(view); bodyFaceMatchBindingKey(view);
  bodyFaceMatchPatch(.5); bodyFaceMatchResetPatches(); checkBodyFaceMatch(neutralBodyFaceMatch());
  assert.equal(JSON.stringify(view), before); assert.equal(bodyFaceMatchBindingKey(null), 'unavailable');
});
