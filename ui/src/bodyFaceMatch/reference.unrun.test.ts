// AUTHORED / UNRUN. No imports, tests, typechecks, builds, inference or visual acceptance executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validFaceSkinObservation, validOwnFaceReference, validOwnFaceReferenceSupport, validReferenceSourceStage} from './reference.ts';
import {faceFixture, ownFaceReferenceFixture, ownFaceSupportFixture} from './fixtures.unrun.ts';

test('own-face identity is exact measured target/source metadata, never transferable colour or a donor', () => {
  assert.equal(validOwnFaceReference(ownFaceReferenceFixture(), faceFixture), true);
  for (const mutate of [
    (v: any) => {delete v.landmark_digest;}, (v: any) => {v.landmark_digest = 'bad';},
    (v: any) => {v.face_ref.face_instance_id = 'donor';}, (v: any) => {v.face_ref.analysis_revision++;},
    (v: any) => {v.face_ref.asset_sha256 = 'b'.repeat(64);}, (v: any) => {v.face_ref.donor = true;},
    (v: any) => {v.face_skin_observation.source_sha256 = 'b'.repeat(64);},
    (v: any) => {v.face_skin_observation.contract = 'body-skin';},
    (v: any) => {v.face_skin_observation.semantic_model_sha256 = 'bad';},
    (v: any) => {v.face_skin_observation.producer_width = 0;},
    (v: any) => {v.face_skin_observation.producer_height = 1.5;},
    (v: any) => {v.reference_method = 'original-source-own-face-robust-log-chroma';},
    (v: any) => {v.reference_method = 'later-edited-face';},
    (v: any) => {v.reference_colour = [.2, .3, .4];}, (v: any) => {v.mask = [1, 1];},
  ]) {const value = ownFaceReferenceFixture(); mutate(value); assert.equal(validOwnFaceReference(value, faceFixture), false);}
  for (const value of [null, undefined, [], {}, 'face-a']) assert.equal(validOwnFaceReference(value, faceFixture), false);
});

test('actual source-stage reference window and counts are bounded to the disclosed decoded image', () => {
  const value = ownFaceSupportFixture(), source = value.source, decoded = {width: 600, height: 800};
  assert.equal(validOwnFaceReferenceSupport(value, faceFixture, source, decoded), true);
  for (const mutate of [
    (v: any) => {v.source_window = [0, 0, 801, 600];}, (v: any) => {v.source_window = [0, 590, 20, 20];},
    (v: any) => {v.source_window = [-1, 0, 100, 100];}, (v: any) => {v.source_window = [0, 0, 0, 100];},
    (v: any) => {v.source_window = [0, 0, 1.5, 100];}, (v: any) => {v.source_window = [0, 0, 10];},
    (v: any) => {v.reference_samples = 63;}, (v: any) => {v.reference_samples = 100_000;},
    (v: any) => {v.support_pixels = 0;}, (v: any) => {v.support_pixels = Infinity;},
    (v: any) => {v.protected_face_boxes = [];}, (v: any) => {v.protected_face_boxes = -1;},
    (v: any) => {v.runtime_quality_accepted = true;}, (v: any) => {v.source.sha256 = 'b'.repeat(64);},
    (v: any) => {v.source.width++;}, (v: any) => {v.face_ref.face_instance_id = 'donor';},
    (v: any) => {v.face_skin_observation.source_sha256 = 'b'.repeat(64);},
    (v: any) => {v.scope = 'body-self-reference';}, (v: any) => {v.reference_method = 'edited-face';},
    (v: any) => {v.reference_rgb = [.5, .5, .5];},
  ]) {const changed = ownFaceSupportFixture(); mutate(changed); assert.equal(validOwnFaceReferenceSupport(changed, faceFixture, source, decoded), false);}
  // Durable source may be larger than the existing source-stage/analysis proxy. Do not relabel proxy pixels as full size.
  const proxy = ownFaceSupportFixture(); proxy.source = {sha256: faceFixture.asset_sha256, width: 1200, height: 1600};
  assert.equal(validOwnFaceReferenceSupport(proxy, faceFixture, proxy.source, decoded), true);
  proxy.source_window = [700, 500, 200, 100];
  assert.equal(validOwnFaceReferenceSupport(proxy, faceFixture, proxy.source, decoded), false);
});

test('source stage enumerates only immutable source or verified frozen repair base, never later portrait face', () => {
  assert.equal(validReferenceSourceStage('immutable-source'), true);
  assert.equal(validReferenceSourceStage('verified-repair-base'), true);
  for (const stage of [null, undefined, 'original', 'edited-face', 'preview', 'other-person']) assert.equal(validReferenceSourceStage(stage), false);
  assert.equal(validFaceSkinObservation(ownFaceReferenceFixture().face_skin_observation, faceFixture.asset_sha256), true);
});
