/** UI circles are in the final-cropped review plane. The engine inverses crop/rotation
 * once and retains affine vectors in the post-optics/pre-crop destination plane. */
export type Point = [number, number];
export interface FringeStroke {
  id: string; mode: 'add' | 'subtract'; points: Point[];
  radius: number; opacity: number; feather: number;
}
export interface FringeDraft {
  enabled: boolean; strength: number; strokes: FringeStroke[]; reset_coverage: boolean;
}
export type FringeMutation = {action: 'enter'} | ({action: 'set'} & FringeDraft);
export interface FringeRecipe {
  version: 1; algorithm: 'lrt-fringe-repair-v1'; enabled: boolean; strength: number;
  source: Record<string, unknown> | null;
  coverage: {domain: 'post-optics-pre-crop-normalized-v1'; strokes: unknown[]};
}
export interface FringeSource {sha256: string; width: number; height: number}
export interface FringeImage {
  before: string; after: string; coverage: string; width: number; height: number;
  domain: 'production-output'; quality: 'full-source-render-downsampled-srgb8'; note: string;
}
export interface RecipeIdentity {recipe_document_id: string; recipe_revision: string}
export interface FringeReview extends RecipeIdentity {
  image: FringeImage; recipe: FringeRecipe; source: FringeSource;
  defaults: {strength: number; min_strength: 0; max_strength: 100};
}
export interface FringeRequest {
  request_id: string; preview_id: string; session_id: string; document_id: string;
}
export interface FringeReceipt extends FringeRequest {
  protocol: 1; action: 'apply'; success: boolean; outcome_unknown: boolean;
  requires_reload: boolean; no_change: boolean;
  history: {undo_steps: number; redo_steps: number} | null; error?: string;
}
export interface BrushSettings {mode: 'add' | 'subtract'; size: number; opacity: number; feather: number}
export const MAX_STROKES = 128;
export const MAX_POINTS = 1024;
export const MAX_TOTAL_POINTS = 8192;
export const reviewImageKey = (preview: string, side: 'before' | 'after' | 'coverage'): string => `${preview}:${side}`;
export const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
const unit = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
export const opaqueId = (value: unknown): value is string =>
  typeof value === 'string' && /^[0-9a-f]{32}$/.test(value) && !/^0+$/.test(value);
/** Source objects are engine-owned; key order must not change their identity. */
export function sourceKey(value: unknown): string {
  const encode = (item: unknown, depth: number): unknown => {
    if (depth > 8) throw Error('来源描述超过结构预算');
    if (Array.isArray(item)) return item.map(child => encode(child, depth + 1));
    if (object(item)) return Object.fromEntries(Object.keys(item).sort().map(key => [key, encode(item[key], depth + 1)]));
    if (item === null || typeof item === 'string' || typeof item === 'boolean' || typeof item === 'number' && Number.isFinite(item)) return item;
    throw Error('来源描述含无效字段');
  };
  const result = JSON.stringify(encode(value, 0));
  if (result.length > 8192) throw Error('来源描述超过长度预算');
  return result;
}
export function validStroke(value: unknown): value is FringeStroke {
  return object(value) && opaqueId(value.id) && ['add', 'subtract'].includes(String(value.mode)) &&
    typeof value.radius === 'number' && Number.isFinite(value.radius) && value.radius > 0 && value.radius <= .5 &&
    unit(value.opacity) && unit(value.feather) && Array.isArray(value.points) && value.points.length > 0 &&
    value.points.length <= MAX_POINTS && value.points.every(point => Array.isArray(point) && point.length === 2 && point.every(unit));
}
export function validDraft(value: FringeDraft): boolean {
  return typeof value.enabled === 'boolean' && typeof value.reset_coverage === 'boolean' &&
    Number.isFinite(value.strength) && value.strength >= 0 && value.strength <= 100 &&
    Array.isArray(value.strokes) && value.strokes.length <= MAX_STROKES && value.strokes.every(validStroke) &&
    value.strokes.reduce((count, stroke) => count + stroke.points.length, 0) <= MAX_TOTAL_POINTS &&
    new Set(value.strokes.map(stroke => stroke.id)).size === value.strokes.length;
}
export function newStroke(point: Point, settings: BrushSettings, id = crypto.randomUUID().replaceAll('-', '')): FringeStroke {
  return {id, mode: settings.mode, points: [point], radius: settings.size / 200,
    opacity: settings.opacity / 100, feather: settings.feather / 100};
}
export function readRecipeIdentity(value: Record<string, unknown>): RecipeIdentity {
  if (!opaqueId(value.recipe_document_id) || typeof value.recipe_revision !== 'string' ||
      !/^(0|[1-9][0-9]{0,19})$/.test(value.recipe_revision) || BigInt(value.recipe_revision) > 18446744073709551615n)
    throw Error('祛边预览缺少有效的照片配方版本');
  return {recipe_document_id: value.recipe_document_id, recipe_revision: value.recipe_revision};
}
export function readReview(raw: Record<string, unknown>): FringeReview {
  const image = raw.image, recipe = raw.recipe, defaults = raw.defaults, source = raw.source;
  const png = (value: unknown) => typeof value === 'string' && value.length <= 4 * 1024 * 1024 &&
    /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
  if (!object(image) || image.domain !== 'production-output' || image.quality !== 'full-source-render-downsampled-srgb8' ||
      ![image.width, image.height].every(value => Number.isSafeInteger(value) && Number(value) > 0 && Number(value) <= 800) ||
      ![image.before, image.after, image.coverage].every(png) || typeof image.note !== 'string' || image.note.length > 4096)
    throw Error('祛边审核必须包含有界、同尺寸的真实前后照片与计算范围图');
  if (!object(recipe) || recipe.version !== 1 || recipe.algorithm !== 'lrt-fringe-repair-v1' ||
      typeof recipe.enabled !== 'boolean' || typeof recipe.strength !== 'number' || !Number.isFinite(recipe.strength) ||
      recipe.strength < 0 || recipe.strength > 100 || (recipe.source !== null && !object(recipe.source)) || !object(recipe.coverage) ||
      recipe.coverage.domain !== 'post-optics-pre-crop-normalized-v1' || !Array.isArray(recipe.coverage.strokes) ||
      recipe.coverage.strokes.length > MAX_STROKES || (recipe.coverage.strokes.length === 0) !== (recipe.source === null) ||
      !object(source) || Object.keys(source).length !== 3 || typeof source.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(source.sha256) ||
      ![source.width, source.height].every(value => Number.isSafeInteger(value) && Number(value) > 0 && Number(value) <= 1000000) ||
      (recipe.source !== null && sourceKey(recipe.source) !== sourceKey(source)))
    throw Error('祛边预览缺少当前来源绑定或正确的范围坐标域');
  if (!object(defaults) || defaults.min_strength !== 0 || defaults.max_strength !== 100 || defaults.strength !== 50)
    throw Error('祛边预览缺少本实现的程度范围与默认值');
  sourceKey(source);
  return {...readRecipeIdentity(raw), image: image as unknown as FringeImage, source: source as unknown as FringeSource,
    recipe: recipe as unknown as FringeRecipe, defaults: defaults as unknown as FringeReview['defaults']};
}
export const receiptKey = (receipt: FringeReceipt): string => JSON.stringify({
  request_id: receipt.request_id, preview_id: receipt.preview_id, session_id: receipt.session_id, document_id: receipt.document_id,
  success: receipt.success, outcome_unknown: receipt.outcome_unknown, requires_reload: receipt.requires_reload, no_change: receipt.no_change,
  undo_steps: receipt.history?.undo_steps ?? null, redo_steps: receipt.history?.redo_steps ?? null,
});
export function readReceipt(raw: unknown, request: FringeRequest): FringeReceipt {
  if (!object(raw) || raw.protocol !== 1 || raw.action !== 'apply' ||
      (['request_id', 'preview_id', 'session_id', 'document_id'] as const).some(key => raw[key] !== request[key]) ||
      typeof raw.success !== 'boolean' || typeof raw.outcome_unknown !== 'boolean' ||
      typeof raw.requires_reload !== 'boolean' || typeof raw.no_change !== 'boolean' ||
      (raw.success && (raw.outcome_unknown || raw.requires_reload)) || (raw.outcome_unknown && !raw.requires_reload))
    throw Error('祛边原操作回执不完整或身份不符');
  const history = object(raw.history) && [raw.history.undo_steps, raw.history.redo_steps].every(value =>
    Number.isSafeInteger(value) && Number(value) >= 0);
  if ((raw.success && !history) || (!raw.success && raw.history !== null && !history))
    throw Error('祛边修改缺少可核对的历史证据');
  return raw as unknown as FringeReceipt;
}
