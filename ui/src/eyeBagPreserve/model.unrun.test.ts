// AUTHORED / UNRUN. Not typecheck, runtime, visual or quality acceptance evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {neutral, validRecipe, validCandidate, ack, imageMetadata, type EyeBagReview} from './model.ts';
import {canonical, emptyMask, reviewEyes, sourcePoint, validEyes, type RidgeBrush} from './support.ts';
const brush = (): RidgeBrush => ({id: 'left-1', name: '人物左眼卧蚕保护', enabled: true, kind: 'brush', operation: 'add', opacity: 1,
  feather: 0, points: [[.5, .55]], axes: [[6 / 4000, 0], [0, 6 / 3000]]});
const masks = () => ({left: {...emptyMask(), objects: [brush()]}, right: emptyMask()});
test('v2 neutral is amount0 preserve1; no v1 migration or extra support payload', () => {
  assert.deepEqual(neutral(), {version: 2, amount: 0, preserve: 1});
  for (const invalid of [{version: 1, amount: 0, preserve: 1}, {...neutral(), eyes: {}}, {...neutral(), preserve: Number.NaN}, {...neutral(), amount: 2}])
    assert.equal(validRecipe(invalid), false);
});
test('source-edge coordinates and radius retain exact source units', () => {
  assert.deepEqual(sourcePoint(110, 220, {left: 10, top: 20, width: 200, height: 400}), [.5, .5]);
  assert.equal(sourcePoint(9, 220, {left: 10, top: 20, width: 200, height: 400}), null);
  assert.equal(brush().axes[0][0] * 4000, 6); assert.equal(brush().axes[1][1] * 3000, 6);
  assert.equal(brush().feather, 0); assert.equal(brush().opacity, 1);
});
test('each present eye requires independent positive source review; absent side stays absent', () => {
  assert.throws(() => reviewEyes(masks(), {left: false, right: true}));
  const eyes = reviewEyes(masks(), {left: true, right: false});
  assert.deepEqual(Object.keys(eyes), ['left']); assert.equal(validEyes(eyes, false), true);
  assert.equal(validCandidate({recipe: {...neutral(), amount: .5}, eyes, replace_legacy: false}), true);
  assert.equal(validCandidate({recipe: neutral(), eyes: {}, replace_legacy: false}), false);
  assert.equal(validEyes({left: {...eyes.left!, visible: false}}), false);
  assert.equal(validEyes({left: {...eyes.left!, recipe: {...eyes.left!.recipe, objects: [{...brush(), opacity: .5}]}}}), false);
});
test('erase stays ordered and cannot become an automatic full or semantic mask', () => {
  const value = masks(); value.left.objects.push({...brush(), id: 'left-erase', operation: 'subtract'});
  const eyes = reviewEyes(value, {left: true, right: false});
  assert.equal(eyes.left!.recipe.objects[1].operation, 'subtract');
  assert.equal(validEyes({left: {...eyes.left!, recipe: {...eyes.left!.recipe, objects: [{...brush(), kind: 'full'}]}}}), false);
  assert.equal(validEyes({eye_light_visibility: eyes.left}), false);
});
test('ACK binds support and both actual image hashes, not boolean review alone', () => {
  const review = {review_sha256: 'r', visual: {before: {sha256: 'b'}, after: {sha256: 'a'}}, support_overlay: {sha256: 's'}} as EyeBagReview;
  assert.deepEqual(ack(review), {review_sha256: 'r', before_sha256: 'b', after_sha256: 'a', support_overlay_sha256: 's'});
  assert.equal(imageMetadata(review, 'support').sha256, 's');
  assert.equal(canonical({preserve: 1, amount: .5}), canonical({amount: .5, preserve: 1}));
});
