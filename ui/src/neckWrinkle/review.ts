// SPDX-License-Identifier: GPL-3.0-or-later
import type {BodyRef} from '../legShape/model';
import type {MaskObject} from '../localMasks/model';

export const NECK_WRINKLE_OPERATION = 'lnx.neck_wrinkle.v1' as const;
export const NECK_WRINKLE_CONTROL_ID = 'control:PC-32464:19' as const;
export const NECK_WRINKLE_LIMITS = {strokes: 64, pointsPerStroke: 1024, totalPoints: 4096,
  requestBytes: 192 * 1024, minHalfWidthPx: 1.4, maxHalfWidthPx: 12} as const;
export type NeckSource = {sha256: string; width: number; height: number};
export type NeckBrush = Extract<MaskObject, {kind: 'brush'}>;
export type NeckMask = {version: 1; domain: 'source-normalized'; objects: NeckBrush[]};
export type NeckBodyChoice = {body_ref: BodyRef; points_sha256: string};
export type NeckReview = NeckBodyChoice & {
  recipe: NeckMask; visible: true; unoccluded: true; ownership_confirmed: true;
  neck: {version: 1; domain: 'source-normalized'; line_half_width: number; protect_recipe: NeckMask;
    protections_reviewed: true; visible_neck_skin_reviewed: true};
};
export type NeckConfirmations = {visible: boolean; unoccluded: boolean; ownership_confirmed: boolean;
  protections_reviewed: boolean; visible_neck_skin_reviewed: boolean};
export const emptyNeckMask = (): NeckMask => ({version: 1, domain: 'source-normalized', objects: []});
export const emptyNeckConfirmations = (): NeckConfirmations => ({visible: false, unoccluded: false,
  ownership_confirmed: false, protections_reviewed: false, visible_neck_skin_reviewed: false});
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export const keys = (v: Record<string, unknown>, names: string[]): boolean => Object.keys(v).sort().join('|') === [...names].sort().join('|');
export const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const token = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128;
export const revision = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
export const finite = (v: unknown, low: number, high: number): v is number => typeof v === 'number' && Number.isFinite(v) && v >= low && v <= high;
export const extent = (v: unknown): v is number => revision(v) && v >= 2 && v <= 1_000_000;
export const validSource = (v: unknown): v is NeckSource => object(v) && keys(v, ['sha256', 'width', 'height']) && hash(v.sha256) && extent(v.width) && extent(v.height);
export const validBody = (v: unknown): v is BodyRef => object(v) && keys(v, ['asset_sha256', 'body_instance_id', 'analysis_revision'])
  && hash(v.asset_sha256) && token(v.body_instance_id) && revision(v.analysis_revision);
export const bodyKey = (v: BodyRef): string => JSON.stringify([v.asset_sha256, v.body_instance_id, v.analysis_revision]);
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
export function parseHalfWidth(text: string, source: NeckSource): number | null {
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim()) || !validSource(source)) return null;
  const pixels = Number(text);
  return finite(pixels, NECK_WRINKLE_LIMITS.minHalfWidthPx, NECK_WRINKLE_LIMITS.maxHalfWidthPx)
    ? pixels / Math.min(source.width, source.height) : null;
}
const pair = (v: unknown, low: number, high: number): v is [number, number] => Array.isArray(v)
  && v.length === 2 && v.every(n => finite(n, low, high));
export function validNeckMask(v: unknown, protection = false): v is NeckMask {
  if (!object(v) || !keys(v, ['version', 'domain', 'objects']) || v.version !== 1 || v.domain !== 'source-normalized'
    || !Array.isArray(v.objects) || v.objects.length > NECK_WRINKLE_LIMITS.strokes) return false;
  let points = 0;
  const ids = new Set<string>();
  for (const brush of v.objects) {
    if (!object(brush) || !keys(brush, ['id', 'name', 'enabled', 'operation', 'kind', 'opacity', 'feather', 'points', 'axes'])
      || typeof brush.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(brush.id) || ids.has(brush.id)
      || typeof brush.name !== 'string' || !brush.name.trim() || brush.name.length > 80 || /[\u0000-\u001f]/.test(brush.name)
      || typeof brush.enabled !== 'boolean' || brush.kind !== 'brush' || !['add', 'subtract'].includes(String(brush.operation))
      || !finite(brush.opacity, 0, 1) || !finite(brush.feather, 0, 100)
      || !Array.isArray(brush.points) || brush.points.length < 1 || brush.points.length > NECK_WRINKLE_LIMITS.pointsPerStroke
      || !brush.points.every(p => pair(p, 0, 1)) || !Array.isArray(brush.axes) || brush.axes.length !== 2
      || !pair(brush.axes[0], -4, 4) || !pair(brush.axes[1], -4, 4)
      || Math.abs(brush.axes[0][0] * brush.axes[1][1] - brush.axes[0][1] * brush.axes[1][0]) < 1e-12
      || protection && (!brush.enabled || brush.operation !== 'add' || brush.opacity !== 1 || brush.feather !== 0)) return false;
    ids.add(brush.id); points += brush.points.length;
  }
  return points <= NECK_WRINKLE_LIMITS.totalPoints
    && (protection || v.objects.some(brush => brush.enabled && brush.operation === 'add' && brush.opacity > 0));
}
/** Independent neck consent; never accepts another body's/operation's reviewed descriptor. */
export function makeNeckReview(choice: NeckBodyChoice, source: NeckSource, recipe: NeckMask,
  protect: NeckMask, halfWidthText: string, flags: NeckConfirmations): NeckReview {
  if (!validSource(source) || !validBody(choice.body_ref) || choice.body_ref.asset_sha256 !== source.sha256 || !hash(choice.points_sha256))
    throw Error('需要明确选择属于当前来源的真实关联身体，不能借用其他人物。');
  if (!flags || flags.visible !== true || flags.unoccluded !== true || flags.ownership_confirmed !== true
    || flags.protections_reviewed !== true || flags.visible_neck_skin_reviewed !== true)
    throw Error('请独立确认可见颈部皮肤、无遮挡、人物归属与保护范围。');
  if (!validNeckMask(recipe) || !validNeckMask(protect, true)) throw Error('需要有效的颈部与上下文笔迹，以及独立的硬保护笔迹。');
  if (recipe.objects.reduce((n, b) => n + b.points.length, 0) + protect.objects.reduce((n, b) => n + b.points.length, 0)
    > NECK_WRINKLE_LIMITS.totalPoints) throw Error('颈部与保护笔迹合计超过 4096 点；不会自动删减点。');
  const halfWidth = parseHalfWidth(halfWidthText, source);
  if (halfWidth === null) throw Error('请根据当前来源实际细纹输入 1.4 至 12 像素的半宽；不从脸框或姿态推算。');
  return {body_ref: {...choice.body_ref}, points_sha256: choice.points_sha256, recipe: structuredClone(recipe),
    visible: true, unoccluded: true, ownership_confirmed: true,
    neck: {version: 1, domain: 'source-normalized', line_half_width: halfWidth,
      protect_recipe: structuredClone(protect), protections_reviewed: true, visible_neck_skin_reviewed: true}};
}
/** Full-image pixel EDGES, matching local-mask rasterization p*extent - .5. */
export function sourcePoint(x: number, y: number, rect: {left: number; top: number; width: number; height: number}): [number, number] | null {
  if (![x, y, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) return null;
  const point: [number, number] = [(x - rect.left) / rect.width, (y - rect.top) / rect.height];
  return point.every(n => n >= 0 && n <= 1) ? point : null;
}
