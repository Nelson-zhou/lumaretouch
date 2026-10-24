// AUTHORED / UNRUN. No product imports, tests, build or typecheck executed during authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sameAssociationRequest, validAssociationReview, validCapsule} from '../people/associationProof';
import {associationRequest} from '../people/associationRequest';
import {inventory, sourceId, targetId, sourceRef} from '../people/transferFixtureData.test';
import {faceStyleSelection} from '../faceStyle/batchModel';
import {portraitFixture} from './cohortFixture';
import {portraitIntentRequiresReview, validPortraitCohort, portraitCohortTargets, portraitCohortAck, validPortraitCohortAck,
  portraitCohortReviewKey, portraitCohortImagesReady} from './model';
test('named create and patch require the exact recipe and all 30 locally composed keys', () => {
  for (const operation of ['create', 'patch'] as const) {
    const {people, plan} = portraitFixture(operation);
    assert.ok(sameAssociationRequest(people, people));
    assert.ok(validAssociationReview(plan.persistent_association, people, plan.association_source, plan.targets));
    assert.ok(validPortraitCohort(plan, people));
    for (const mutate of [(p: any) => {p.face_style.amount = .6;}, (p: any) => {p.face_style.version = 2;},
      (p: any) => {p.selection['lnx.face_size.v1'].push('/extra');}, (p: any) => {delete p.selection['lnx.face_contour.v1'];},
      (p: any) => {p.targets[0].target_refs.push(p.source_ref);}, (p: any) => {p.face_style.badge = 'classic';}]) {
      const copy = structuredClone(people); mutate(copy); assert.equal(sameAssociationRequest(copy, people), false);
    }
  }
});
test('unlink omits recipe entirely and retains all-member review from canonical intent', () => {
  const {people, plan} = portraitFixture('unlink');
  assert.deepEqual(people.selection, {}); assert.equal(Object.hasOwn(people, 'face_style'), false);
  assert.ok(validPortraitCohort(plan, people));
  assert.equal(sameAssociationRequest({...people, face_style: {version: 1, style: 'classic', amount: 0}}, people), false);
  assert.equal(validPortraitCohort({...plan, portrait_cohort: undefined}, people), false);
});
test('generic patches trigger from all managed keys, not named coefficient matching', () => {
  const {people, plan} = portraitFixture('patch', false);
  assert.equal(people.face_style, undefined); assert.ok(portraitIntentRequiresReview(plan.persistent_association.intent));
  assert.ok(validPortraitCohort(plan, people));
  assert.equal(portraitIntentRequiresReview(plan.persistent_association.intent.slice(1)), false);
  const capsule = {...plan.persistent_association, local_document_id: sourceId};
  const {operation: _, ...stored} = capsule;
  assert.ok(validCapsule(stored)); assert.equal(validCapsule({...stored, face_style: {version: 1, style: 'classic', amount: .5}}), false);
});
test('named inventory builder never takes donor values and unlink strips supplied recipe', () => {
  const list = inventory(); list.source.associations = [];
  const target = list.targets[0]; if (target.blocked !== null) throw Error('fixture'); target.associations = [];
  const recipe = {version: 1 as const, style: 'classic' as const, amount: 0};
  const request = associationRequest(list, [targetId], sourceRef, faceStyleSelection(), {[targetId]: [sourceRef]}, 'create', 'new', recipe);
  assert.deepEqual(request?.face_style, recipe); assert.deepEqual(request?.selection, faceStyleSelection());
  const {plan} = portraitFixture('unlink'), {operation: _, ...review} = plan.persistent_association;
  list.source.associations = [{...review, local_document_id: sourceId}]; target.associations = [{...review, local_document_id: targetId}];
  const unlink = associationRequest(list, [targetId], sourceRef, faceStyleSelection(), {[targetId]: [sourceRef]}, 'unlink', 'unused', recipe);
  assert.ok(unlink); assert.deepEqual(unlink.selection, {}); assert.equal(Object.hasOwn(unlink, 'face_style'), false);
});
test('source-first opaque cohort digest and exact target proofs cannot be substituted', () => {
  const {people, plan, sourceId, targetId} = portraitFixture();
  const rows = portraitCohortTargets(plan), visuals = rows.map(row => row.visual), ack = portraitCohortAck(visuals);
  assert.deepEqual(rows.map(row => row.document_id), [sourceId, targetId]); assert.ok(validPortraitCohortAck(ack, visuals));
  for (const invalid of [ack.slice(1), [...ack].reverse(), [...ack, ack[0]], ack.map((row, i) => i ? row : {...row, cohort_sha256: 'a'.repeat(64)})])
    assert.equal(validPortraitCohortAck(invalid, visuals), false);
  for (const mutate of [(p: any) => {delete p.association_source.association.portrait_visual;}, (p: any) => {p.targets[0].association.portrait_visual.cohort_sha256 = 'a'.repeat(64);},
    (p: any) => {p.targets[0].association.portrait_visual.recipe_sha256 = 'c'.repeat(64);}, (p: any) => {p.targets[0].association.portrait_visual.revision = '999';},
    (p: any) => {p.targets[0].association.portrait_visual.document_id = p.association_source.document_id;}, (p: any) => {p.portrait_cohort = false;},
    (p: any) => {p.module_scope.reverse();}]) {
    const copy = structuredClone(plan); mutate(copy); assert.equal(validPortraitCohort(copy, people), false);
  }
});
test('all members need loaded and explicit current review; keys include whole frozen visual', () => {
  const {plan} = portraitFixture(), visuals = portraitCohortTargets(plan).map(row => row.visual), token = 'token:request';
  const ready = Object.fromEntries(visuals.map(visual => [portraitCohortReviewKey(token, visual), true]));
  assert.ok(portraitCohortImagesReady(token, visuals, ready));
  assert.equal(portraitCohortImagesReady('token:replacement', visuals, ready), false);
  assert.equal(portraitCohortImagesReady(token, [], ready), false);
  assert.equal(portraitCohortImagesReady(token, [undefined, visuals[1]], ready), false);
  const ui = readFileSync(new URL('./PortraitCohortReview.tsx', import.meta.url), 'utf8');
  for (const text of ['loaded.before && loaded.after', 'ready && acknowledged', 'element.naturalWidth === value[side].width',
    'disabled={disabled || !ready}', 'liveAttempt.current !== attempt', 'key={props.reviewKey}']) assert.ok(ui.includes(text));
  const panel = readFileSync(new URL('../people/ConfirmedPeopleTransfer.tsx', import.meta.url), 'utf8');
  assert.ok(panel.includes('flow.commit(spill,shadow,torso,waist,head,collarbone,faceStyle,portrait)'));
  const model = readFileSync(new URL('./model.ts', import.meta.url), 'utf8');
  assert.equal(model.includes('crypto.subtle'), false);
});
