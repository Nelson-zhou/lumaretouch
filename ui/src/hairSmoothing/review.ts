// SPDX-License-Identifier: GPL-3.0-or-later
import type {MaskObject} from '../localMasks/model';

export const HAIR_SMOOTHING_OPERATION = 'lnx.hair_smoothing.v1' as const;
export const HAIR_SMOOTHING_CONTROL_ID = 'control:PC-32472:8' as const;
export const HAIR_SMOOTHING_LIMITS = {strokes: 64, pointsPerStroke: 1024, totalPoints: 4096,
  requestBytes: 192 * 1024, minTextureScalePx: 1, maxTextureScalePx: 8, maxSourcePixels: 32_000_000} as const;
export type HairSmoothingSource = {sha256: string; width: number; height: number};
export type HairSmoothingBrush = Extract<MaskObject, {kind: 'brush'}>;
export type HairSmoothingMask = {version: 1; domain: 'source-normalized'; objects: HairSmoothingBrush[]};
export type HairSmoothingReview = {
  version: 1; domain: 'source-normalized'; target_recipe: HairSmoothingMask; context_recipe: HairSmoothingMask;
  protect_recipe: HairSmoothingMask; texture_scale: number; visible_hair_reviewed: true;
  protections_reviewed: true; ownership_confirmed: true;
};
export type HairSmoothingConfirmations = {visible_hair_reviewed: boolean; protections_reviewed: boolean; ownership_confirmed: boolean};
export const emptyHairSmoothingMask = (): HairSmoothingMask => ({version: 1, domain: 'source-normalized', objects: []});
export const emptyHairSmoothingConfirmations = (): HairSmoothingConfirmations => ({visible_hair_reviewed: false,
  protections_reviewed: false, ownership_confirmed: false});
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export const keys = (v: Record<string, unknown>, names: string[]): boolean => Object.keys(v).sort().join('|') === [...names].sort().join('|');
export const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const token = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128;
export const revision = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
export const finite = (v: unknown, low: number, high: number): v is number => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
export const extent = (v: unknown): v is number => revision(v) && v >= 2 && v <= 1_000_000;
export const validSource = (v: unknown): v is HairSmoothingSource => object(v) && keys(v, ['sha256', 'width', 'height'])
  && hash(v.sha256) && extent(v.width) && extent(v.height);
/** Measurement admission is separate from neutral cleanup of an oversized source. */
export const admittedSource = (v: unknown): v is HairSmoothingSource => validSource(v) && v.width <= 65536 && v.height <= 65536
  && v.width * v.height <= HAIR_SMOOTHING_LIMITS.maxSourcePixels;
/** Deterministic equality only; this is NOT a trusted source/owner digest. */
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (object(v)) return '{' + Object.keys(v).sort().map(key => JSON.stringify(key) + ':' + canonical(v[key])).join(',') + '}';
  return JSON.stringify(v) ?? 'undefined';
}
export function parseAmount(text: string): number | null {
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())) return null;
  const value = Number(text) / 100;
  return finite(value, 0, 1) ? value : null;
}
export function parseTextureScale(text: string, source: HairSmoothingSource): number | null {
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim()) || !admittedSource(source)) return null;
  const pixels = Number(text);
  return finite(pixels, HAIR_SMOOTHING_LIMITS.minTextureScalePx, HAIR_SMOOTHING_LIMITS.maxTextureScalePx)
    ? pixels / Math.min(source.width, source.height) : null;
}
const pair = (v: unknown, low: number, high: number): v is [number, number] => Array.isArray(v)
  && v.length === 2 && v.every(n => finite(n, low, high));
export function validHairSmoothingMask(v: unknown, protection = false): v is HairSmoothingMask {
  if (!object(v) || !keys(v, ['version', 'domain', 'objects']) || v.version !== 1 || v.domain !== 'source-normalized'
    || !Array.isArray(v.objects) || v.objects.length > HAIR_SMOOTHING_LIMITS.strokes) return false;
  let points = 0;
  const ids = new Set<string>();
  for (const brush of v.objects) {
    if (!object(brush) || !keys(brush, ['id', 'name', 'enabled', 'operation', 'kind', 'opacity', 'feather', 'points', 'axes'])
      || typeof brush.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(brush.id) || ids.has(brush.id)
      || typeof brush.name !== 'string' || !brush.name.trim() || brush.name.length > 80 || /[\u0000-\u001f]/.test(brush.name)
      || typeof brush.enabled !== 'boolean' || brush.kind !== 'brush' || !['add', 'subtract'].includes(String(brush.operation))
      || !finite(brush.opacity, 0, 1) || !finite(brush.feather, 0, 100)
      || !Array.isArray(brush.points) || brush.points.length < 1 || brush.points.length > HAIR_SMOOTHING_LIMITS.pointsPerStroke
      || !brush.points.every(p => pair(p, 0, 1)) || !Array.isArray(brush.axes) || brush.axes.length !== 2
      || !pair(brush.axes[0], -4, 4) || !pair(brush.axes[1], -4, 4)
      || Math.abs(brush.axes[0][0] * brush.axes[1][1] - brush.axes[0][1] * brush.axes[1][0]) < 1e-12
      || protection && (!brush.enabled || brush.operation !== 'add' || brush.opacity !== 1 || brush.feather !== 0)) return false;
    ids.add(brush.id); points += brush.points.length;
  }
  return points <= HAIR_SMOOTHING_LIMITS.totalPoints
    && (protection || v.objects.some(brush => brush.enabled && brush.operation === 'add' && brush.opacity > 0));
}
/** This operation's consent only. Ownership colour/volume reviews never substitute for it. */
export function validReview(v: unknown, source?: HairSmoothingSource): v is HairSmoothingReview {
  if (!object(v) || !keys(v, ['version', 'domain', 'target_recipe', 'context_recipe', 'protect_recipe', 'texture_scale',
    'visible_hair_reviewed', 'protections_reviewed', 'ownership_confirmed']) || v.version !== 1 || v.domain !== 'source-normalized'
    || v.visible_hair_reviewed !== true || v.protections_reviewed !== true || v.ownership_confirmed !== true
    || !finite(v.texture_scale, Number.MIN_VALUE, 1) || !validHairSmoothingMask(v.target_recipe)
    || !validHairSmoothingMask(v.context_recipe) || !validHairSmoothingMask(v.protect_recipe, true)) return false;
  const total = [v.target_recipe, v.context_recipe, v.protect_recipe].reduce((sum, mask) =>
    sum + mask.objects.reduce((n, brush) => n + brush.points.length, 0), 0);
  return total <= HAIR_SMOOTHING_LIMITS.totalPoints && (!source || admittedSource(source)
    && finite(v.texture_scale * Math.min(source.width, source.height), 1, 8));
}
export function makeHairSmoothingReview(source: HairSmoothingSource, target: HairSmoothingMask, context: HairSmoothingMask,
  protect: HairSmoothingMask, textureScaleText: string, flags: HairSmoothingConfirmations): HairSmoothingReview {
  if (!admittedSource(source)) throw Error('需要实际原始来源的准确尺寸和身份，不接受派生合成或显示代理。');
  if (!flags || flags.visible_hair_reviewed !== true || flags.protections_reviewed !== true || flags.ownership_confirmed !== true)
    throw Error('请独立确认实际可见头发、本人归属与所有保护范围。');
  const scale = parseTextureScale(textureScaleText, source);
  if (scale === null) throw Error('请在来源原生裁片观察后输入 1 至 8 像素的纹理尺度；不会猜测或自动限制数值。');
  const review: HairSmoothingReview = {version: 1, domain: 'source-normalized', target_recipe: structuredClone(target),
    context_recipe: structuredClone(context), protect_recipe: structuredClone(protect), texture_scale: scale,
    visible_hair_reviewed: true, protections_reviewed: true, ownership_confirmed: true};
  if (!validReview(review, source)) throw Error('需要有效的目标、同人上下文及硬保护笔迹；三类合计最多 4096 点，不自动简化。');
  return review;
}
/** Full-image pixel EDGES, matching local-mask rasterization p*extent - .5. */
export function sourcePoint(x: number, y: number, rect: {left: number; top: number; width: number; height: number}): [number, number] | null {
  if (![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) return null;
  const point: [number, number] = [(x - rect.left) / rect.width, (y - rect.top) / rect.height];
  return point.every(n => n >= 0 && n <= 1) ? point : null;
}
