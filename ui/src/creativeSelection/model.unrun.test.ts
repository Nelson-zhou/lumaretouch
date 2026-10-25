// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. These fixtures have not been imported, executed or typechecked in this environment.
import test from 'node:test';
import assert from 'node:assert/strict';
import {emptySelectionRecipe, selectionKey, selectionReplyMatches, validSelectionRecipe, type SelectionRecipe} from './model.ts';
import {selectionPoint, selectionShape} from './geometry.ts';

const canvas = {width: 6000, height: 4000};
test('client pixels map to frozen full canvas edges, never display proxy pixels or DPR', () => {
  const rect = {left: 100, top: 80, width: 600, height: 400};
  assert.deepEqual(selectionPoint(400, 280, rect, canvas), [3000, 2000]);
  assert.deepEqual(selectionPoint(700, 480, rect, canvas), [6000, 4000]);
  assert.equal(selectionPoint(99, 200, rect, canvas), null);
  assert.equal(selectionPoint(400, 280, {...rect, width: 0}, canvas), null);
});
test('reverse drag yields an ordered rectangle and fixed ratio survives canvas clipping', () => {
  assert.deepEqual(selectionShape('rectangle', 'new', [300, 400], [100, 200], canvas, {mode: 'free'}),
    {kind: 'rectangle', combine: 'new', x0: 100, y0: 200, x1: 300, y1: 400});
  const value = selectionShape('ellipse', 'intersect', [5900, 3900], [5999, 3999], canvas, {mode: 'ratio', width: 2, height: 1});
  assert.deepEqual(value, {kind: 'ellipse', combine: 'intersect', x0: 5900, y0: 3900, x1: 6000, y1: 3950});
});
test('fixed source-pixel size shifts at canvas edge, never shrinks silently', () => {
  assert.deepEqual(selectionShape('rectangle', 'add', [5900, 3900], [5900, 3900], canvas, {mode: 'size', width: 400, height: 300}),
    {kind: 'rectangle', combine: 'add', x0: 5600, y0: 3700, x1: 6000, y1: 4000});
  assert.equal(selectionShape('ellipse', 'new', [0, 0], [1, 1], canvas, {mode: 'size', width: 7000, height: 300}), null);
});
test('lasso is implicitly closed and brush only adds or subtracts with explicit bounded parameters', () => {
  const recipe: SelectionRecipe = {...emptySelectionRecipe(canvas), operations: [
    {kind: 'lasso', combine: 'new', points: [[0, 0], [100, 0], [100, 100]]},
    {kind: 'brush', combine: 'subtract', points: [[50, 50]], diameter: 60, hardness: .4, opacity: .5}, {kind: 'invert'}], feather_radius: 256};
  assert.equal(validSelectionRecipe(recipe), true);
  assert.equal(validSelectionRecipe({...recipe, feather_radius: 257}), false);
  assert.equal(validSelectionRecipe({...recipe, operations: [{...recipe.operations[1], combine: 'new'}]}), false);
  assert.equal(validSelectionRecipe({...recipe, operations: [{...recipe.operations[1], opacity: NaN}]}), false);
  assert.equal(validSelectionRecipe({...recipe, operations: [{kind: 'invert', hidden: true}]}), false);
  assert.equal(validSelectionRecipe({...recipe, coordinate_space: 'screen-pixels'}), false);
});
test('empty draft is valid locally but caller must not preview/apply deselection as a destructive empty mask', () => {
  assert.equal(validSelectionRecipe(emptySelectionRecipe(canvas)), true);
  assert.equal(validSelectionRecipe({...emptySelectionRecipe(canvas), operations: [{kind: 'rectangle', combine: 'new', x0: 0, y0: 0, x1: 0, y1: 1}]}), false);
});
test('stable comparison is key-order independent and reply matching rejects foreign or contradictory receipts', () => {
  assert.equal(selectionKey({a: 1, b: 2}), selectionKey({b: 2, a: 1}));
  const request = {action: 'cancel' as const, request_id: 'q', source_uid: 's', target_request_id: 'p'};
  assert.equal(selectionReplyMatches({event: 'creative_selection_result', request_id: 'q', source_uid: 'other', status: 'cancelled'}, request), false);
  assert.equal(selectionReplyMatches({event: 'creative_selection_result', request_id: 'q', source_uid: 's', status: 'applied', success: false}, request), false);
});
