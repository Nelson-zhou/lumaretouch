// SPDX-License-Identifier: GPL-3.0-or-later
// Session draft only, not a graph, image cache, review proof or history owner.
import {validRecipe, type EyeBagRecipe} from './model';
import {validEyes, type EyeSide, type RidgeMask} from './support';
export type EyeBagDraft = {recipe: EyeBagRecipe; masks: Record<EyeSide, RidgeMask>; replaceLegacy: boolean};
export function validDraft(v: EyeBagDraft): boolean {
  if (!v || !validRecipe(v.recipe) || typeof v.replaceLegacy !== 'boolean' || !v.masks
    || Object.keys(v.masks).sort().join('|') !== 'left|right') return false;
  let count = 0;
  for (const side of ['left', 'right'] as const) {
    const mask = v.masks[side];
    if (!mask || mask.version !== 1 || mask.domain !== 'source-normalized' || !Array.isArray(mask.objects)) return false;
    if (mask.objects.length && !validEyes({[side]: {recipe: mask, visible: true, unoccluded: true, ownership_confirmed: true}}, false, false)) return false;
    count += mask.objects.reduce((n, o) => n + o.points.length, 0);
  }
  return count <= 4096 && JSON.stringify(v).length <= 256 * 1024;
}
