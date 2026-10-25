// AUTHORED / UNRUN. No product imports, tests, inference or typechecks executed for this slice.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {LENS_OPERATION, LENS_PROTOCOL, initialLensRecipe, validLensCapability, validLensContext, validLensDepth, validLensRecipe,
  validLensReview, validLensReceipt, validLensWriteCommand, lensReviewKey, type LensContext, type LensDepthAsset,
  type LensOwner, type LensPng, type LensPreviewCommand, type LensReview, type LensApplyCommand} from './model.ts';
import {fitLensImage, lensDisplayToSource, lensSourceToDepth, sampleLensDepth} from './imagery.ts';
// Structural fixtures only. This short PNG prefix is deliberately NOT an authentic PNG.
const image = (): LensPng => ({mime: 'image/png', width: 4, height: 2, sha256: 'a'.repeat(64), base64: 'iVBORw=='});
const owner = (): LensOwner => ({document_id: 'doc-1', document_epoch: 'epoch-1', document_revision: '7',
  source: {sha256: 'b'.repeat(64), width: 8, height: 4, orientation: 'exif_normalized_once'}});
const depth = (): LensDepthAsset => ({version: 1, token: 'depth-1', owner: owner(), convention: 'near-zero-far-one',
  mapping: 'normalized_full_frame_pixel_centres', orientation: 'exif_normalized_once',
  raster: {format: 'u16-le', width: 4, height: 2, sha256: 'c'.repeat(64), base64: 'AAAAAAAAAAAAAAAAAAAAAA=='},
  provenance: {kind: 'manual', method: 'user_supplied_depth'}, subject_focus: null});
const context = (): LensContext => ({session_id: 'session-1', owner: owner(), source_image: image(), depth: depth(), depth_status: 'ready', message: ''});
const preview = (): LensPreviewCommand => ({version: LENS_PROTOCOL, action: 'preview', request_id: 'preview-1', session_id: 'session-1', owner: owner(), recipe: initialLensRecipe(depth())});
const review = (c = preview()): LensReview => ({version: LENS_PROTOCOL, request_id: c.request_id, session_id: c.session_id, token: 'review-1', owner: c.owner,
  recipe: c.recipe, recipe_sha256: 'd'.repeat(64), before: image(), after: {...image(), sha256: 'e'.repeat(64)}, notes: [], result_source_sha256: 'f'.repeat(64)});
const apply = (): LensApplyCommand => {const r = review(); return {version: LENS_PROTOCOL, action: 'apply', request_id: 'apply-1', session_id: r.session_id,
  owner: r.owner, token: r.token, recipe_sha256: r.recipe_sha256, before_sha256: r.before.sha256, after_sha256: r.after.sha256, reviewed: true,
  return_mode: 'new_image', result_source_sha256: r.result_source_sha256};};

test('depth must belong to exact current document/source with explicit provenance and raster contract', () => {
  assert.equal(validLensDepth(depth(), owner()), true);
  assert.equal(validLensDepth({...depth(), owner: {...owner(), document_revision: '8'}}, owner()), false);
  assert.equal(validLensDepth({...depth(), convention: 'inverse-depth'}, owner()), false);
  assert.equal(validLensDepth({...depth(), mapping: 'crop'}, owner()), false);
  assert.equal(validLensDepth({...depth(), raster: {...depth().raster, width: 3}}, owner()), false);
  assert.equal(validLensDepth({...depth(), provenance: {kind: 'ai'}}, owner()), false);
  assert.equal(validLensDepth({...depth(), subject_focus: {near: .3, far: .4, mask_sha256: 'f'.repeat(64)}}, owner()), false);
  assert.equal(validLensDepth({...depth(), generated_placeholder: true}, owner()), false);
  assert.equal(validLensDepth({...depth(), provenance: {kind: 'manual', method: 'user_defined_plane', depth_value: .5, acknowledgement_id: 'explicit-choice'}}, owner()), true);
  assert.equal(validLensDepth({...depth(), provenance: {kind: 'manual', method: 'user_defined_plane', depth_value: .5}}, owner()), false);
  assert.equal(validLensContext(context()), true);
  assert.equal(validLensContext({...context(), depth_status: 'missing-model'}), false);
  assert.equal(validLensContext({...context(), depth_status: 'missing-model', depth: null}), true);
});
test('capability is exact versioned operation, not presence of an optional model adapter', () => {
  assert.equal(validLensCapability({version: 1, operation_id: LENS_OPERATION, status: 'available', kernels: ['circular_disk'], reason: ''}), true);
  assert.equal(validLensCapability({version: 1, operation_id: LENS_OPERATION, status: 'unavailable', kernels: [], reason: 'not installed'}), true);
  assert.equal(validLensCapability({version: 1, operation_id: LENS_OPERATION, status: 'available', kernels: [], reason: ''}), false);
  assert.equal(validLensCapability({version: 1, operation_id: 'fake.lens', status: 'available', kernels: ['circular_disk'], reason: ''}), false);
});
test('neutral recipe is explicit and refinements remain source/depth owned', () => {
  const d = depth(), r = initialLensRecipe(d);
  assert.equal(r.max_radius_px, 0); assert.deepEqual(r.focus, {mode: 'interval', near: 0, far: 1, point: null});
  assert.equal(validLensRecipe(r, d), true);
  assert.equal(validLensRecipe({...r, max_radius_px: NaN}, d), false);
  assert.equal(validLensRecipe({...r, max_radius_px: 128.5}, d), false);
  assert.equal(validLensRecipe({...r, aperture: 'PixCakeCircleII'}, d), false);
  assert.equal(validLensRecipe({...r, focal_length_mm: 85}, d), false);
  assert.equal(validLensRecipe({...r, source: {...r.source, sha256: 'f'.repeat(64)}}, d), false);
  assert.equal(validLensRecipe({...r, depth: {...r.depth, token: 'other-depth'}}, d), false);
  assert.equal(validLensRecipe({...r, focus: {mode: 'subject', near: 0, far: 1, point: null}}, d), false);
  assert.equal(validLensRecipe({...r, focus: {mode: 'interval', near: .8, far: .2, point: null}}, d), false);
  const s = {id: 'stroke-1', mode: 'clear' as const, amount: 1, flow: .5, feather: .5, radius: .02, points: [{x: 0, y: 1}]};
  assert.equal(validLensRecipe({...r, refinements: [s]}, d), true);
  assert.equal(validLensRecipe({...r, refinements: [s, s]}, d), false);
  assert.equal(validLensRecipe({...r, refinements: [{...s, radius: 0}]}, d), false);
  assert.equal(validLensRecipe({...r, refinements: [{...s, points: [{x: -.01, y: 0}]}]}, d), false);
});
test('centre-coordinate conversion respects letterboxing, source pixel edges and reduced raster centres', () => {
  const source = owner().source;
  const fit = fitLensImage({left: 10, top: 20, width: 100, height: 100}, source);
  assert.deepEqual(fit, {left: 10, top: 45, width: 100, height: 50});
  assert.equal(lensDisplayToSource(40, 21, fit, source), null);
  assert.deepEqual(lensDisplayToSource(10, 45, fit, source), {x: 0, y: 0});
  assert.deepEqual(lensDisplayToSource(110, 95, fit, source), {x: 1, y: 1});
  assert.deepEqual(lensDisplayToSource(60, 70, fit, source), {x: .5, y: .5});
  assert.deepEqual(lensSourceToDepth({x: 0, y: 0}, source, 4, 2), {x: -.25, y: -.25});
  assert.deepEqual(lensSourceToDepth({x: 1, y: 1}, source, 4, 2), {x: 3.25, y: 1.25});
  const values = new Uint16Array([0, 0, 65535, 65535, 0, 0, 65535, 65535]);
  assert.equal(sampleLensDepth({asset: depth(), values}, {x: 0, y: .5}), 0);
  assert.equal(sampleLensDepth({asset: depth(), values}, {x: 1, y: .5}), 1);
  assert.equal(sampleLensDepth({asset: depth(), values}, {x: .5, y: .5}), .5);
});
test('review and acknowledgement identities bind recipe source and both actual image digests', () => {
  const c = preview(), r = review(c);
  assert.equal(validLensReview(r, c), true);
  assert.equal(validLensReview({...r, request_id: 'other-preview'}, c), false);
  assert.equal(validLensReview({...r, recipe: {...r.recipe, max_radius_px: 30}}, c), false);
  assert.equal(validLensReview({...r, owner: {...r.owner, document_epoch: 'reopened'}}, c), false);
  assert.equal(validLensReview({...r, after: {...r.after, width: 3}}, c), false);
  assert.equal(validLensReview({...r, version: 1}, c), false);
  assert.equal(validLensReview({...r, result_source_sha256: undefined}, c), false);
  assert.equal(validLensReview({...r, result_source_sha256: `sha256:${r.result_source_sha256}`}, c), false);
  assert.notEqual(lensReviewKey(r), lensReviewKey({...r, before: {...r.before, sha256: 'f'.repeat(64)}}));
  assert.notEqual(lensReviewKey(r), lensReviewKey({...r, recipe: {...r.recipe, max_radius_px: 1}}));
  assert.notEqual(lensReviewKey(r), lensReviewKey({...r, result_source_sha256: '1'.repeat(64)}));
});
test('new-copy commands are exact and cannot select original replacement or a v1 fallback', () => {
  const c = apply(); assert.equal(validLensWriteCommand(c), true);
  for (const patch of [{version: 1}, {return_mode: 'update_original'}, {return_mode: undefined}, {result_source_sha256: undefined},
    {result_source_sha256: 'not-a-hash'}, {reviewed: false}, {history_entry_id: 'invented'}, {request_id: 'not valid'}])
    assert.equal(validLensWriteCommand({...c, ...patch}), false);
  const cancel = {version: LENS_PROTOCOL, action: 'cancel', request_id: 'cancel', session_id: c.session_id, owner: c.owner, token: null};
  assert.equal(validLensWriteCommand(cancel), true);
  assert.equal(validLensWriteCommand({...cancel, return_mode: 'new_image'}), false);
});
test('pending, unknown, rejected and independent-copy commits cannot be confused', () => {
  const command = apply();
  const base = {version: LENS_PROTOCOL, request_id: command.request_id, session_id: command.session_id, action: command.action, owner: command.owner, token: command.token, message: ''};
  assert.equal(validLensReceipt({...base, phase: 'pending', outcome_unknown: true}, command), true);
  assert.equal(validLensReceipt({...base, phase: 'pending', outcome_unknown: false}, command), false);
  assert.equal(validLensReceipt({...base, phase: 'done', outcome_unknown: false, outcome: 'cancelled'}, command), false);
  const applied = {...base, phase: 'done', outcome_unknown: false, outcome: 'applied', recipe_sha256: command.recipe_sha256,
    before_sha256: command.before_sha256, after_sha256: command.after_sha256, return_mode: 'new_image', copied_original_document_id: command.owner.document_id,
    result_document_id: 'new-copy-1', result_revision: '1', result_source_sha256: command.result_source_sha256, no_change: false};
  assert.equal(validLensReceipt(applied, command), true);
  // New document revisions are not an increment of the source's revision, nor the creative-layer revision.
  assert.equal(validLensReceipt({...applied, result_revision: '0'}, command), true);
  for (const patch of [{version: 1}, {request_id: 'other'}, {result_revision: '-1'}, {result_revision: '01'}, {result_revision: '18446744073709551616'},
    {return_mode: 'update_original'}, {copied_original_document_id: 'other'}, {result_document_id: command.owner.document_id},
    {result_document_id: ''}, {result_source_sha256: command.after_sha256}, {no_change: true}, {document_revision: '8'},
    {history_entry_id: null}, {before_sha256: 'f'.repeat(64)}, {outcome_unknown: true}])
    assert.equal(validLensReceipt({...applied, ...patch}, command), false);
  const neutral = {...command, result_source_sha256: command.owner.source.sha256};
  assert.equal(validLensReceipt({...applied, result_source_sha256: neutral.result_source_sha256, no_change: true}, neutral), true);
  assert.equal(validLensReceipt({...applied, result_source_sha256: neutral.result_source_sha256, no_change: false}, neutral), false);
  const legacy = {...base, version: 1, phase: 'done', outcome_unknown: false, outcome: 'applied', recipe_sha256: command.recipe_sha256,
    before_sha256: command.before_sha256, after_sha256: command.after_sha256, document_revision: '8', no_change: false, history_entry_id: 'history'};
  assert.equal(validLensReceipt(legacy, command), false);
  assert.equal(validLensReceipt({...base, phase: 'done', outcome_unknown: false, outcome: 'rejected'}, command), true);
});
