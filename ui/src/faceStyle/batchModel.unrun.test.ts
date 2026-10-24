// AUTHORED / UNRUN. Synthetic DTOs and source assertions are not rendered-photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {request, review, sourceRef, sourceContext} from '../people/transferFixtureData.test';
import {samePeopleRequest, validPeopleReview} from '../people/transferProof';
import type {PeopleView} from '../people/model';
import type {FaceStyleRecipe} from './model';
import {FACE_STYLES} from './model';
import {visualFixture} from '../collarbone/transferFixture';
import {faceStyleSelection, validFaceStyleSelection, faceStyleBatchSourceReady, faceStyleRecipeDigest,
  validFaceStyleBatchVisual, faceStyleBatchAck, sameFaceStyleBatchAck, faceStyleBatchReviewKey, faceStyleBatchImagesReady} from './batchModel';

test('binding v1 contains exactly 30 unique owned leaves in the fixed sorted ten-operation scope', () => {
  const selected = faceStyleSelection();
  assert.deepEqual(Object.keys(selected), Object.keys(selected).sort());
  assert.equal(Object.keys(selected).length, 10);
  assert.equal(Object.values(selected).flat().length, 30);
  assert.equal(validFaceStyleSelection(selected), true);
  for (const op of Object.keys(selected)) {
    const missing = structuredClone(selected); missing[op].pop();
    assert.equal(validFaceStyleSelection(missing), false);
  }
  assert.equal(validFaceStyleSelection({...selected, 'lnx.deform.v1': ['/slim_face']}), false);
  assert.equal(validFaceStyleSelection({...selected, 'lnx.chin_shape.v1': ['/linked', '/left', '/left']}), false);
  selected['lnx.face_size.v1'].push('/mask');
  assert.equal(faceStyleSelection()['lnx.face_size.v1'].length, 1);
});
test('exact recipe digest is domain-separated binary float64, including normalized signed zero', async () => {
  for (const style of FACE_STYLES) for (const amount of [0, -0, .5, 1, Number.MIN_VALUE]) {
    const bytes = Buffer.alloc(8); bytes.writeDoubleBE(amount === 0 ? 0 : amount);
    const expected = createHash('sha256').update(`lumaretouch.face-style.v1\0${style}\0`, 'utf8').update(bytes).digest('hex');
    assert.equal(await faceStyleRecipeDigest({version: 1, style, amount}), expected);
  }
});
test('named explicit map cannot be replaced with donor leaves, another amount or confirmed-person mode', () => {
  const r = {...request(), selection: faceStyleSelection(), face_style: {version: 1, style: 'classic', amount: .5} as FaceStyleRecipe};
  assert.equal(samePeopleRequest(r, r), true);
  for (const patch of [{face_style: {...r.face_style, amount: .6}}, {face_style: {...r.face_style, version: 2}},
    {selection: {'lnx.deform.v1': ['/slim_face']}}, {target_policy: 'confirmed_person_only'}, {face_style: null}])
    assert.equal(samePeopleRequest({...r, ...patch}, r), false);
  const ordinary = request();
  assert.equal(samePeopleRequest({...ordinary, face_style: r.face_style}, ordinary), false);
});
test('context face readiness is independent of donor parameters, conflicts and resolved availability', () => {
  const context = sourceContext();
  const view: PeopleView = {binding: context.binding, revision: context.state_revision, association_revision: context.association_revision,
    faces: [{face_ref: {...sourceRef}, box: [.1,.1,.8,.9], enabled: true, manual: false, analysis_status: 'verified'}],
    groups: {}, persons: {}, links: [], selected_face_id: sourceRef.face_instance_id, editing_target: null, editing_overrides: {}, resolved: null};
  assert.equal(faceStyleBatchSourceReady(view), true);
  view.resolved = {face_ref: sourceRef, state_revision: 0, association_revision: 0,
    conflicts: [{operation_id: 'lnx.face_size.v1', parameter_path: '/amount', reason: 'donor conflict', target_ids: []}],
    operations: {'lnx.face_size.v1': {'/amount': {value: .95, scope: 'face', target_id: 'donor', overridden: false}}}};
  assert.equal(faceStyleBatchSourceReady(view), true);
  for (const patch of [{enabled: false}, {analysis_status: 'unresolved'}, {face_ref: {...sourceRef, asset_sha256: 'd'.repeat(64)}}])
    assert.equal(faceStyleBatchSourceReady({...view, faces: [{...view.faces[0], ...patch}]} as PeopleView), false);
  assert.equal(faceStyleBatchSourceReady({...view, selected_face_id: null}), false);
});
test('target visual rejects coverage aliases and wrong recipe/target proof; zero still needs all leaves', () => {
  const r = {...request(), selection: faceStyleSelection(), face_style: {version: 1, style: 'classic', amount: 0} as FaceStyleRecipe};
  const evidence = review(); evidence.face_style = r.face_style;
  evidence.parameters = Object.entries(r.selection).flatMap(([operation_id, paths]) => paths.map(parameter_path => ({operation_id, parameter_path,
    value: parameter_path.endsWith('/linked') ? true : 0})));
  const {coverage_sha256: _, ...visual} = visualFixture(evidence);
  evidence.face_style_visual = {...visual, recipe_sha256: 'a'.repeat(64)};
  assert.equal(validPeopleReview(evidence, r, r.source, {document_id: evidence.target_document.document_id, revision: String(evidence.target_document.revision)}), true);
  assert.equal(validFaceStyleBatchVisual({...evidence.face_style_visual, coverage_sha256: 'b'.repeat(64)}, evidence), false);
  assert.equal(validFaceStyleBatchVisual({...evidence.face_style_visual, revision: '999'}, evidence), false);
  const missing = structuredClone(evidence); missing.parameters.pop();
  assert.equal(validPeopleReview(missing, r, r.source, {document_id: evidence.target_document.document_id, revision: String(evidence.target_document.revision)}), false);
  const ack = faceStyleBatchAck([evidence.face_style_visual]);
  for (const field of Object.keys(ack[0])) assert.equal(sameFaceStyleBatchAck([{...ack[0], [field]: 'wrong'}], ack), false);
  assert.equal(sameFaceStyleBatchAck([{...ack[0], coverage_sha256: 'b'.repeat(64)}], ack), false);
  const key = faceStyleBatchReviewKey('token:request', evidence.face_style_visual);
  assert.equal(faceStyleBatchImagesReady('token:request', [evidence.face_style_visual], {[key]: true}), true);
  assert.equal(faceStyleBatchImagesReady('token:other', [evidence.face_style_visual], {[key]: true}), false);
  assert.equal(faceStyleBatchImagesReady('token:request', [undefined], {[key]: true}), false);
});
test('reachable UI forwards named ack and gates on verified pixels plus explicit per-target review', () => {
  const panel = readFileSync(new URL('../people/ConfirmedPeopleTransfer.tsx', import.meta.url), 'utf8');
  for (const text of ['faceStyleBatchSourceReady(view)', "mode === 'face_style'", 'faceStyleSelection()', 'flow.commit(spill,shadow,torso,waist,head,collarbone,faceStyle)'])
    assert.ok(panel.includes(text));
  const images = readFileSync(new URL('./FaceStyleBatchReview.tsx', import.meta.url), 'utf8');
  for (const text of ['verifyFaceStyleBatchRecipe(value, recipe)', 'element.naturalWidth === value[side].width', 'loaded.before && loaded.after',
    'ready && acknowledged', 'disabled={disabled || !ready}', 'liveAttempt.current !== attempt', 'key={props.reviewKey}']) assert.ok(images.includes(text));
  const workflow = readFileSync(new URL('../batch/batchWorkflow.ts', import.meta.url), 'utf8');
  assert.ok(workflow.includes('state.plan!==plan||key!==reviewContext'));
  assert.ok(workflow.includes('pending?.faceStyleWrite'));
});
