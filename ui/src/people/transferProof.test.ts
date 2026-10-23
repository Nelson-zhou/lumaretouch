// UNRUN: no imports or tests were executed while authoring these fixtures.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {samePeopleRequest, validPeopleReview, validEndpoint, type PeopleTransferReview, type PeopleTransferRequest} from './transferProof.ts';
import {asset, endpoint, request, review, sourceId, sourceRef, targetId} from './transferFixtureData.test.ts';
const target = {document_id: targetId, revision: '20'};

test('one-transfer proof accepts independent revisions and identical source pixels / face refs', () => {
  const req = request();
  assert.equal(samePeopleRequest(req, req), true);
  assert.equal(validPeopleReview(review(), req, req.source, target), true);
});
test('explicit frozen evidence checks every owner fence, not source revision equality', () => {
  for (const mutate of [
    (v: any) => {v.target_owner.state_revision++;}, (v: any) => {v.target_owner.association_revision++;},
    (v: any) => {v.target_owner.document.epoch = 'other';}, (v: any) => {v.target_owner.document.revision++;},
    (v: any) => {v.target_owner.document.document_id = sourceId;}, (v: any) => {v.target_owner.people_scope = 'project';},
    (v: any) => {v.target_owner.graph_sha256 = 'f'.repeat(64);}, (v: any) => {v.source_owner.graph_sha256 = 'f'.repeat(64);},
    (v: any) => {v.target_owner.source_proof.original_sha256 = 'f'.repeat(64);},
    (v: any) => {v.target_state_revision = v.source_state_revision;},
    (v: any) => {v.target_refs[0].analysis_revision++;}, (v: any) => {v.target_refs[0].face_instance_id = 'different';},
    (v: any) => {v.target_refs.push({...v.target_refs[0]});}, (v: any) => {v.confirmed_person_id = 'fake-person';},
    (v: any) => {v.confirmation_revisions = [];}, (v: any) => {v.excluded.pop();},
    (v: any) => {v.parameters[0].value = {mask: 'not a scalar'};},
  ]) {
    const req = request(), value = structuredClone(review()); mutate(value);
    assert.equal(validPeopleReview(value, req, req.source, target), false);
  }
});
test('request matching accounts for every manually selected document and face', () => {
  const expected = request();
  for (const mutate of [
    (v: any) => {v.targets = [];}, (v: any) => {v.targets.push(structuredClone(v.targets[0]));},
    (v: any) => {v.targets[0].target_refs = [];}, (v: any) => {v.targets[0].target.document.document_id = 'f'.repeat(32);},
    (v: any) => {v.targets[0].target_refs[0].face_instance_id = 'other';},
    (v: any) => {v.selection['lnx.deform.v1'].push('/unasked');},
    (v: any) => {v.target_policy = 'confirmed_person_only';},
  ]) {
    const value = structuredClone(expected); mutate(value); assert.equal(samePeopleRequest(value, expected), false);
  }
});
test('proof field ordering is immaterial but derived source and extent remain exact', () => {
  const expected = request();
  expected.source.source_proof = {asset_sha256: asset, original_sha256: 'f'.repeat(64), creative_source: {sha256: asset, width: 800, height: 600}};
  const value = structuredClone(expected);
  value.source.document = {revision: value.source.document.revision, epoch: value.source.document.epoch, document_id: sourceId};
  assert.equal(samePeopleRequest(value, expected), true);
  value.source.source_proof.creative_source!.width++;
  assert.equal(samePeopleRequest(value, expected), false);
  const wrongOwner = endpoint(targetId); wrongOwner.people_scope = sourceId;
  assert.equal(validEndpoint(wrongOwner), false);
});
test('confirmed-person-only policy still requires same owner revisions, distinct asset and confirmation', () => {
  const req: PeopleTransferRequest = {target_policy: 'confirmed_person_only', source_ref: sourceRef, selection: request().selection};
  const proof = {document_id: sourceId, document_epoch: 'workspace-1', document_revision: 3,
    state_revision: 2, association_revision: 6, person_id: 'confirmed-1'};
  const sourceOwner = {...endpoint(sourceId), people_scope: 'project'};
  const targetOwner = {...endpoint(targetId, 19), people_scope: 'project', state_revision: 2,
    association_revision: 6, graph_sha256: sourceOwner.graph_sha256,
    source_proof: {asset_sha256: 'f'.repeat(64), original_sha256: 'f'.repeat(64), creative_source: null}};
  const value: PeopleTransferReview = {version: 1, source_document: endpoint(sourceId).document, target_document: endpoint(targetId, 19).document,
    source_ref: sourceRef, target_refs: [{...sourceRef, asset_sha256: 'f'.repeat(64)}], parameters: review().parameters,
    target_policy: 'confirmed_person_only', confirmed_person_id: 'confirmed-1', confirmation_revisions: [[sourceRef.face_instance_id, 4]],
    source_owner: sourceOwner, target_owner: targetOwner,
    source_state_revision: 2, target_state_revision: 2, source_association_revision: 6, target_association_revision: 6,
    transfer_policy: 'selected_parameter_keys_replace', excluded: review().excluded};
  assert.equal(validPeopleReview(value, req, proof, target), true);
  assert.equal(validPeopleReview({...value, target_state_revision: 19}, req, proof, target), false);
  assert.equal(validPeopleReview({...value, target_refs: [sourceRef]}, req, proof, target), false);
  assert.equal(validPeopleReview({...value, confirmation_revisions: []}, req, proof, target), false);
  assert.equal(validPeopleReview({...value, target_owner: {...targetOwner, people_scope: targetId}}, req, proof, target), false);
  assert.equal(validPeopleReview({...value, target_owner: {...targetOwner, graph_sha256: '0'.repeat(64)}}, req, proof, target), false);
});
