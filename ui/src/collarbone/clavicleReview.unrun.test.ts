// AUTHORED / UNRUN. No product imports, tests, builds, typechecks, UI or photographs were executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {checkClavicleReview, emptyClavicleDraft, clavicleReviewError, clavicleApplicabilityConflict, type ClavicleReview} from './clavicleReview.ts';
const source = {width: 1000, height: 800};
function review(): ClavicleReview {return {version: 1, domain: 'source-normalized', category: 'female',
  eligibility_confirmed: true, visible_anatomy_confirmed: true,
  curves: [{id: 'left', width: 16 / 800, points: [[.2, .3], [.3, .32], [.4, .3]]}]};}

test('no category, anatomy or width is inferred in a fresh local draft', () => {
  assert.deepEqual(emptyClavicleDraft(), {version: 1, domain: 'source-normalized', category: '',
    eligibility_confirmed: false, visible_anatomy_confirmed: false, curves: []});
  assert.throws(() => checkClavicleReview(emptyClavicleDraft(), source));
});
test('one explicitly visible side is sufficient and never completes the other side', () => {
  const value = review(), accepted = checkClavicleReview(value, source);
  assert.deepEqual(accepted, value); assert.notEqual(accepted, value); assert.notEqual(accepted.curves[0].points, value.curves[0].points);
  assert.equal(accepted.curves.length, 1);
  value.category = 'elder_female'; value.curves[0].id = 'right';
  assert.deepEqual(checkClavicleReview(value, source), value);
});
test('both distinct nonintersecting image sides are admitted without symmetry inference', () => {
  const value = review(); value.curves.push({id: 'right', width: 24 / 800, points: [[.55, .3], [.65, .29], [.75, .3]]});
  assert.deepEqual(checkClavicleReview(value, source), value);
});
test('strict metadata, confirmations, category and source domain reject unknown fields or coercion', () => {
  for (const mutate of [
    (v: any) => {v.version = 2;}, (v: any) => {v.domain = 'face-relative';}, (v: any) => {v.category = '';},
    (v: any) => {v.category = 'male';}, (v: any) => {v.category = 'child';}, (v: any) => {v.category = new String('female');},
    (v: any) => {v.eligibility_confirmed = false;}, (v: any) => {v.visible_anatomy_confirmed = false;},
    (v: any) => {v.eligibility_confirmed = 1;}, (v: any) => {v.visible_anatomy_confirmed = 'true';},
    (v: any) => {v.automatic = true;}, (v: any) => {delete v.domain;}, (v: any) => {v.curves[0].guessed = true;},
  ]) {const value = review(); mutate(value); assert.throws(() => checkClavicleReview(value, source));}
  for (const bad of [null, [], false, 1, 'female']) assert.throws(() => checkClavicleReview(bad, source));
});
test('half width is original-source short-side fraction with strict 4..256 pixel limits, no clamp', () => {
  for (const width of [4 / 800, 16 / 800, 256 / 800]) {
    const value = review(); value.curves[0].width = width; assert.equal(checkClavicleReview(value, source).curves[0].width, width);
  }
  for (const width of [0, -1, 3.99 / 800, 256.01 / 800, NaN, Infinity, '0.02', null, true]) {
    const value = review(); value.curves[0].width = width as number; assert.throws(() => checkClavicleReview(value, source));
  }
});
test('curve cardinality, exact image sides and point count are bounded', () => {
  for (const mutate of [(v: any) => {v.curves = [];}, (v: any) => {v.curves.push(structuredClone(v.curves[0]));},
    (v: any) => {v.curves[0].id = 'anatomical-left';}, (v: any) => {v.curves[0].points.pop();},
    (v: any) => {v.curves[0].points = Array.from({length: 9}, (_, i) => [.2 + i * .05, .3]);}]) {
    const value = review(); mutate(value); assert.throws(() => checkClavicleReview(value, source));
  }
});
test('all points must be finite, strictly interior and explicitly two-dimensional', () => {
  for (const point of [[0, .3], [1, .3], [-.1, .3], [.2, 0], [.2, 1], [.2, NaN], [.2, Infinity], ['.2', .3], [.2], [.2, .3, 0], null]) {
    const value = review(); value.curves[0].points[0] = point as any; assert.throws(() => checkClavicleReview(value, source));
  }
});
test('normalized duplicate, sub-two-pixel segment, self crossing and both directions of backtrack are refused', () => {
  for (const points of [
    [[.2, .3], [.2, .3], [.4, .3]], [[.2, .3], [.2005, .3], [.4, .3]],
    [[.2, .3], [.4, .3], [.3, .3]], [[.2, .3], [.4, .3], [.1, .3]],
    [[.2, .2], [.4, .4], [.2, .4], [.4, .2]],
  ]) {const value = review(); value.curves[0].points = points as [number, number][]; assert.throws(() => checkClavicleReview(value, source));}
});
test('cross-side touching, overlap and intersections are not admitted', () => {
  for (const points of [[[.3, .2], [.3, .32], [.3, .4]], [[.2, .3], [.3, .32], [.4, .3]]]) {
    const value = review(); value.curves.push({id: 'right', width: .02, points: points as [number, number][]});
    assert.throws(() => checkClavicleReview(value, source));
  }
});
test('pixel-edge geometry uses p*source width, not p*(width-1) or thumbnail dimensions', () => {
  const value = review(); value.curves[0].points = [[.2, .3], [.202, .3], [.4, .3]];
  assert.equal(checkClavicleReview(value, source).curves.length, 1);
  assert.throws(() => checkClavicleReview(value, {width: 500, height: 400}));
  for (const dimensions of [{width: 0, height: 800}, {width: NaN, height: 800}, {width: 1000.5, height: 800}]) assert.throws(() => checkClavicleReview(value, dimensions));
});
test('errors are explanatory, and applicability uses only explicit male/child labels without inferred categories', () => {
  assert.equal(clavicleReviewError(review(), source), null); assert.match(clavicleReviewError(emptyClavicleDraft(), source) ?? '', /明确选择/);
  for (const labels of [{gender_label: '男'}, {age_band: '儿童'}]) assert.ok(clavicleApplicabilityConflict(labels));
  for (const labels of [undefined, {}, {gender_label: '未标注'}, {age_band: '成人', gender_label: '女'}]) assert.equal(clavicleApplicabilityConflict(labels), null);
});


test('source-space minimum 2px segments, strictly acute direction changes and twice-half-width total length align with native admission', () => {
  for (const points of [[[.2, .3], [.2015, .3], [.4, .3]], [[.2, .3], [.3, .3], [.3, .4]],
    [[.2, .3], [.3, .3], [.29, .4]], [[.2, .3], [.21, .3], [.22, .3]]]) {
    const value = review(); value.curves[0].points = points as [number, number][];
    assert.throws(() => checkClavicleReview(value, source));
  }
  const boundary = review(); boundary.curves[0].points = [[.2, .3], [.216, .3], [.232, .3]];
  assert.deepEqual(checkClavicleReview(boundary, source), boundary);
  boundary.curves[0].width = 17 / 800; assert.throws(() => checkClavicleReview(boundary, source));
});
