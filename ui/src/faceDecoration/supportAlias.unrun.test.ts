// AUTHORED / UNRUN. Synthetic contracts only, never runtime or photographic acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {aliasFixture} from './multiowner.unrun.test';
import {region, stroke} from './review';
import {canonical, command} from './model';
import {supportAliasAck, supportAliasEchoMatches, supportAliasImage, validSupportAliasConfirmation, validSupportAliasReview,
  type SupportAliasDraft, type SupportAliasReview} from './supportAliasModel';
export function supportAliasFixture() {
  const {view, review: scalar} = aliasFixture(), reference_proof = structuredClone(view.face_decoration!.reference_proof!);
  const draft: SupportAliasDraft = {reference_proof, region: region([stroke(reference_proof.source, 'add', 1, [.5, .5], 'own-stroke')], true, {visible: true, unoccluded: true, owner: true})};
  const review: SupportAliasReview = {version: 1, token: 'e'.repeat(32), target: 'face_decoration_visibility', owner: scalar.owner, face_ref: scalar.face_ref,
    before_support_sha256: 'c'.repeat(64), support_sha256: '2'.repeat(64), before_bank_sha256: '3'.repeat(64), candidate_bank_sha256: '4'.repeat(64),
    reference_proof, region: draft.region, candidate_state_revision: view.revision + 1, review_sha256: 'f'.repeat(64),
    members: scalar.members.map(member => ({path: member.path, visual: member.visual, coverage: {version: 1, support_change: 'selected-face-only', targets: [{
      face_ref: scalar.face_ref, before_visibility_sha256: 'c'.repeat(64), visibility_sha256: '2'.repeat(64), before_recipe_sha256: 'd'.repeat(64), recipe_sha256: 'd'.repeat(64),
    }]}}))};
  return {view, draft, review};
}
test('source-painted draft is exact, independently scoped, and cannot borrow scalar alias authority', () => {
  const {view, draft, review} = supportAliasFixture();
  assert.ok(validSupportAliasReview(review, view, draft));
  assert.equal(validSupportAliasReview(aliasFixture().review, view, draft), false);
  for (const mutate of [
    (v: SupportAliasReview) => {v.region.recipe.objects[0].points[0][0] = .4;},
    (v: SupportAliasReview) => {v.reference_proof.reference_request_id = 'another-reference';},
    (v: SupportAliasReview) => {v.members.reverse();},
    (v: SupportAliasReview) => {v.members.pop();},
    (v: SupportAliasReview) => {v.members[1].visual.document_id = v.members[0].visual.document_id;},
    (v: SupportAliasReview) => {v.members[1].coverage.targets[0].recipe_sha256 = '9'.repeat(64);},
    (v: SupportAliasReview) => {v.members[1].coverage.targets[0].visibility_sha256 = '9'.repeat(64);},
    (v: SupportAliasReview) => {v.members[1].visual.candidate_state_sha256 = '9'.repeat(64);},
  ]) {const bad = structuredClone(review); mutate(bad); assert.equal(validSupportAliasReview(bad, view, draft), false);}
});
test('initial neutral support needs no prior record; selecting retained own support need not grow the bank', () => {
  const {view, draft, review} = supportAliasFixture();
  const neutral = structuredClone(review); neutral.before_support_sha256 = null;
  for (const member of neutral.members) member.coverage.targets[0].before_visibility_sha256 = null;
  assert.equal(validSupportAliasReview(neutral, view, draft), false);
  const neutralView = structuredClone(view); neutralView.face_decoration!.recipe.strength = 0;
  neutralView.resolved!.operations['lnx.face_decoration.v1']['/strength'].value = 0;
  assert.ok(validSupportAliasReview(neutral, neutralView, draft));
  const retained = structuredClone(review); retained.candidate_bank_sha256 = retained.before_bank_sha256;
  assert.ok(validSupportAliasReview(retained, view, draft));
  // A changed pointer to an immutable own record is not donor copying or a no-op.
  retained.support_sha256 = retained.before_support_sha256!;
  assert.equal(validSupportAliasReview(retained, view, draft), false);
});
test('other faces and every complete member remain independently frozen', () => {
  const {view, draft, review} = supportAliasFixture();
  for (const member of review.members) member.coverage.targets.push({face_ref: {...review.face_ref, face_instance_id: 'face-z'},
    before_visibility_sha256: null, visibility_sha256: null, before_recipe_sha256: '8'.repeat(64), recipe_sha256: '8'.repeat(64)});
  assert.ok(validSupportAliasReview(review, view, draft));
  review.members[1].coverage.targets[1].visibility_sha256 = review.support_sha256;
  assert.equal(validSupportAliasReview(review, view, draft), false);
});
test('support ACK is ordered complete review authority and scalar echo/image cannot substitute', async () => {
  const {view, review} = supportAliasFixture(), ack = supportAliasAck(review);
  assert.notEqual(canonical(ack), canonical({...ack, members: [...ack.members].reverse()}));
  const request = command(view, 'face_decoration_support_alias_confirm', 'confirm-own', {token: review.token, ack});
  const {request_id, ...echo} = request;
  const result = {protocol: 1 as const, request_id, action: request.action, document_id: request.document_id, success: true, outcome_unknown: false,
    face_decoration_support_alias_request: echo};
  assert.ok(supportAliasEchoMatches(request, result));
  assert.equal(supportAliasEchoMatches(request, {...result, face_decoration_support_alias_request: undefined, face_decoration_alias_request: echo}), false);
  assert.equal(validSupportAliasConfirmation(review, result), false);
  await assert.rejects(supportAliasImage({kind: 'face_decoration_alias_image'}, review, review.members[0].visual.document_id, 'before'));
});
