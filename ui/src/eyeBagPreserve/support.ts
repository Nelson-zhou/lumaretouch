// SPDX-License-Identifier: GPL-3.0-or-later
import type {MaskObject} from '../localMasks/model';
export const SUPPORT_KIND = 'eye_bag_ridge_visibility' as const;
export type EyeSide = 'left' | 'right';
export type Point = [number, number];
export type RidgeBrush = Extract<MaskObject, {kind: 'brush'}>;
export type RidgeMask = {version: 1; domain: 'source-normalized'; objects: RidgeBrush[]};
export type RidgeEye = {recipe: RidgeMask; visible: true; unoccluded: true; ownership_confirmed: true};
export type RidgeEyes = Partial<Record<EyeSide, RidgeEye>>;
export type RidgeSource = {sha256: string; width: number; height: number};
export const emptyMask = (): RidgeMask => ({version: 1, domain: 'source-normalized', objects: []});
export const canonical = (value: unknown): string => Array.isArray(value) ? '[' + value.map(canonical).join(',') + ']'
  : value && typeof value === 'object' ? '{' + Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => JSON.stringify(k) + ':' + canonical(v)).join(',') + '}'
  : JSON.stringify(value) ?? 'undefined';
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: string[]) => Object.keys(v).sort().join('|') === [...expected].sort().join('|');
const number = (v: unknown, lo: number, hi: number): v is number => typeof v === 'number' && Number.isFinite(v) && v >= lo && v <= hi;
/** Source pixel EDGES, matching p*w-.5 in the canonical Rust mask rasterizer. */
export function sourcePoint(x: number, y: number, rect: {left: number; top: number; width: number; height: number}): Point | null {
  if (![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) return null;
  const p: Point = [(x - rect.left) / rect.width, (y - rect.top) / rect.height];
  return p.every(n => n >= 0 && n <= 1) ? p : null;
}
export function ridgeBrush(side: EyeSide, mode: 'add' | 'subtract', radiusPixels: number, feather: number, source: RidgeSource, first: Point): RidgeBrush {
  if (!number(radiusPixels, .5, Math.min(source.width, source.height) / 2) || !number(feather, 0, 100)) throw Error('笔刷半径或羽化无效。');
  return {id: crypto.randomUUID().replaceAll('-', ''), name: `${side === 'left' ? '人物左眼' : '人物右眼'}卧蚕${mode === 'add' ? '保护' : '擦除'}`,
    enabled: true, operation: mode, kind: 'brush', opacity: 1, feather, points: [first], axes: [[radiusPixels / source.width, 0], [0, radiusPixels / source.height]]};
}
/** This validates bounded vectors only, not eye visibility or rasterized unit coverage. */
export function validEyes(v: unknown, allowEmpty = true): v is RidgeEyes {
  if (!object(v) || Object.keys(v).some(k => k !== 'left' && k !== 'right') || (!allowEmpty && !Object.keys(v).length)) return false;
  let total = 0;
  return Object.values(v).every(eye => {
    if (!object(eye) || !keys(eye, ['recipe', 'visible', 'unoccluded', 'ownership_confirmed'])
      || eye.visible !== true || eye.unoccluded !== true || eye.ownership_confirmed !== true || !object(eye.recipe)) return false;
    const mask = eye.recipe;
    if (!keys(mask, ['version', 'domain', 'objects']) || mask.version !== 1 || mask.domain !== 'source-normalized'
      || !Array.isArray(mask.objects) || !mask.objects.length || mask.objects.length > 64) return false;
    const ids = new Set<string>();
    return mask.objects.some(o => object(o) && o.enabled === true && o.operation === 'add' && o.opacity === 1)
      && mask.objects.every(o => {
        if (!object(o) || !keys(o, ['id', 'name', 'enabled', 'operation', 'kind', 'opacity', 'feather', 'points', 'axes'])
          || typeof o.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(o.id) || ids.has(o.id)
          || typeof o.name !== 'string' || !o.name.trim() || [...o.name].length > 80 || /[\x00-\x1f]/.test(o.name) || typeof o.enabled !== 'boolean'
          || !['add', 'subtract'].includes(String(o.operation)) || o.kind !== 'brush' || o.opacity !== 1 || !number(o.feather, 0, 100)
          || !Array.isArray(o.points) || !o.points.length || o.points.length > 1024
          || !o.points.every(p => Array.isArray(p) && p.length === 2 && p.every(n => number(n, 0, 1)))
          || !Array.isArray(o.axes) || o.axes.length !== 2 || !o.axes.every(p => Array.isArray(p) && p.length === 2 && p.every(n => number(n, -4, 4)))) return false;
        const axes = o.axes as [Point, Point]; ids.add(o.id); total += o.points.length;
        return Math.abs(axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0]) >= 1e-12 && total <= 4096;
      });
  });
}
export function reviewEyes(masks: Record<EyeSide, RidgeMask>, flags: Record<EyeSide, boolean>): RidgeEyes {
  const eyes: RidgeEyes = {};
  for (const side of ['left', 'right'] as const) {
    if (!masks[side].objects.length) continue;
    if (!flags[side]) throw Error('请逐眼确认清晰可见、无遮挡且属于当前人物的卧蚕范围。');
    eyes[side] = {recipe: structuredClone(masks[side]), visible: true, unoccluded: true, ownership_confirmed: true};
  }
  if (!validEyes(eyes, false)) throw Error('需要至少一眼有效手绘范围；最多每眼 64 笔、每笔 1024 点、双眼合计 4096 点。');
  return eyes;
}
