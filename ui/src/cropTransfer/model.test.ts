// AUTHORED / UNRUN. Synthetic protocol fixtures, not image/render quality acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {CROP_OP, cropImagesReady, cropReviewKey, validCropReview, type CropReview} from './model.ts';
export const crop = {rect_normalized: [0.1, 0.2, 0.9, 0.8] as [number, number, number, number], rotation_degrees: 90};
export const targetId = 'b'.repeat(32), sourceId = 'a'.repeat(32), token = 'c'.repeat(32);
export function review(): CropReview {
  return {version: 1, document_id: targetId, revision: '7', source_proof: {asset_sha256: 'd'.repeat(64),
    original_sha256: 'e'.repeat(64), creative_source: {sha256: 'd'.repeat(64), width: 640, height: 480}},
    candidate_sha256: 'f'.repeat(64), people_sha256: '0'.repeat(64), crop: structuredClone(crop),
    source_size: [640, 480], output_size: [288, 512],
    preview: {mime: 'image/png', base64: 'iVBORw==', width: 180, height: 320, sha256: '1'.repeat(64)}};
}
test('crop report binds exact target revision and frozen geometry', () => {
  const r = review(); assert.equal(validCropReview(r, targetId, '7', crop), true);
  for (const [id, revision, params] of [[sourceId, '7', crop], [targetId, '8', crop],
    [targetId, '7', {...crop, rotation_degrees: 0}]] as const) {
    assert.equal(validCropReview(r, id, revision, params), false);
  }
  assert.equal(CROP_OP, 'lnx.crop.v1');
});
test('source substitution, invalid PNG envelope and false dimensions reject', () => {
  const mutations = [
    (r: CropReview) => {r.source_proof.creative_source!.sha256 = '2'.repeat(64);},
    (r: CropReview) => {r.source_size[0]++;},
    (r: CropReview) => {r.output_size = [512, 288];},
    (r: CropReview) => {r.preview.width = 321;},
    (r: CropReview) => {r.preview.base64 = 'not png';},
    (r: CropReview) => {r.preview.sha256 = '';},
    (r: CropReview) => {r.people_sha256 = '';},
    (r: CropReview) => {r.crop.rotation_degrees = Infinity;},
  ];
  for (const change of mutations) {const r = review(); change(r); assert.equal(validCropReview(r, targetId, '7', crop), false);}
});
test('original-only target evidence remains source-owned', () => {
  const r = review(); r.source_proof.creative_source = null; r.source_proof.original_sha256 = r.source_proof.asset_sha256;
  assert.equal(validCropReview(r, targetId, '7', crop), true);
  r.source_proof.original_sha256 = '3'.repeat(64); assert.equal(validCropReview(r, targetId, '7', crop), false);
});
test('every target image is mandatory, missing report and later token cannot reuse readiness', () => {
  const a = review(), b = {...review(), document_id: '9'.repeat(32)};
  const ready = {[cropReviewKey(token, a)]: true};
  assert.equal(cropImagesReady(token, [a, b], ready), false);
  assert.equal(cropImagesReady(token, [a, undefined], ready), false);
  ready[cropReviewKey(token, b)] = true;
  assert.equal(cropImagesReady(token, [a, b], ready), true);
  assert.equal(cropImagesReady('8'.repeat(32), [a, b], ready), false);
  const altered = review(); altered.preview.base64 = 'iVBORx==';
  assert.equal(cropImagesReady(token, [altered], ready), false);
  ready[cropReviewKey(token, a)] = false;
  assert.equal(cropImagesReady(token, [a], ready), false);
});
