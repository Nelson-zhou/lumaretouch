// AUTHORED / UNRUN. No imports or fixtures executed, no acceptance claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import {cropSourcePoint, validSourceCrops, sourceCropImage, type SourceCrops} from './sourceCrops.ts';
const source = {sha256: 'a'.repeat(64), width: 6000, height: 4000};
const image = {mime: 'image/png' as const, width: 800, height: 400, sha256: 'b'.repeat(64)};
const crops = (): SourceCrops => ({version: 1, token: 'd'.repeat(32), mapping: 'source_pixel_edges', orientation: 'exif_normalized_once',
  source_sha256: source.sha256, source_width: source.width, source_height: source.height, input_stage: 'committed_repair', snapshot_sha256: 'c'.repeat(64),
  display_encoding: 'srgb_rgb8', sampling: 'one_source_pixel_per_image_pixel', eyes: {
    left: {rect: [1000, 1600, 800, 400], image}, right: {rect: [3000, 1600, 800, 400], image}}});
test('exact integer native crop metadata is required, not thumbnail mapping', () => {
  assert.equal(validSourceCrops(crops(), source), true);
  for (const bad of [{...crops(), mapping: 'normalized_full_frame'}, {...crops(), source_sha256: 'f'.repeat(64)},
    {...crops(), sampling: 'upsampled'}, {...crops(), eyes: {...crops().eyes, left: {...crops().eyes.left, rect: [1000.5, 1600, 800, 400]}}}])
    assert.equal(validSourceCrops(bad, source), false);
});
test('native viewport center and edges map back to full source edges', () => {
  const screen = {left: 20, top: 30, width: 400, height: 200}, crop = crops().eyes.left;
  assert.deepEqual(cropSourcePoint(20, 30, screen, crop, source), [1000 / 6000, 1600 / 4000]);
  assert.deepEqual(cropSourcePoint(420, 230, screen, crop, source), [1800 / 6000, 2000 / 4000]);
  assert.deepEqual(cropSourcePoint(220, 130, screen, crop, source), [1400 / 6000, 1800 / 4000]);
  assert.equal(cropSourcePoint(19, 30, screen, crop, source), null);
});
test('native spatial equality refuses mismatched dimensions and oversized crops', () => {
  const a = crops(); a.eyes.left.image = {...image, width: 799}; assert.equal(validSourceCrops(a, source), false);
  const b = crops(); b.eyes.left.rect = [5500, 1600, 800, 400]; assert.equal(validSourceCrops(b, source), false);
  const c = crops(); c.eyes.left.rect = [0, 0, 2049, 400]; assert.equal(validSourceCrops(c, source), false);
});
test('paged crop refuses cross-token, cross-snapshot and fake PNG bytes', async () => {
  const value = {kind: 'eye_bag_source_image', token: crops().token, side: 'left', snapshot_sha256: crops().snapshot_sha256,
    image: {...image, base64: 'AAAA'}};
  assert.equal(await sourceCropImage(value, crops(), 'left'), null);
  assert.equal(await sourceCropImage({...value, token: 'e'.repeat(32)}, crops(), 'left'), null);
  assert.equal(await sourceCropImage({...value, snapshot_sha256: 'e'.repeat(64)}, crops(), 'left'), null);
  assert.equal(await sourceCropImage(value, crops(), 'right'), null);
});
test('viewport resizing and zoom do not change source-space points', () => {
  const crop = crops().eyes.right;
  const small = cropSourcePoint(220, 130, {left: 20, top: 30, width: 400, height: 200}, crop, source);
  const native = cropSourcePoint(420, 230, {left: 20, top: 30, width: 800, height: 400}, crop, source);
  const zoom = cropSourcePoint(820, 430, {left: 20, top: 30, width: 1600, height: 800}, crop, source);
  assert.deepEqual(small, native); assert.deepEqual(native, zoom);
});
