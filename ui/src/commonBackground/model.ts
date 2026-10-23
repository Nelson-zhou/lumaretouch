/** Reviewed deterministic colour-key replacement, separate from legacy neural matting. */
export type RGB = [number, number, number];
export type Mutation = {action: 'set'; bg: RGB; tol: number; softness: number} | {action: 'clear'};
export interface Review {
  before: string; after: string; width: number; height: number;
  domain: 'production-output'; quality: 'proxy-render-srgb8'; note: string;
}
export interface RecipeIdentity {recipe_document_id: string; recipe_revision: string}
export interface Request {request_id: string; preview_id: string; session_id: string; document_id: string}
/** These are draft starting values, not a claim about a saved document's parameters. */
export const defaultDraft = (): Extract<Mutation, {action: 'set'}> =>
  ({action: 'set', bg: [255, 255, 255], tol: .12, softness: .10});
export const hex = (rgb: RGB) => '#' + rgb.map(v => v.toString(16).padStart(2, '0')).join('');
export function parseHex(value: string): RGB {
  if (!/^#[0-9a-f]{6}$/i.test(value)) throw Error('请选择有效的背景颜色');
  return [1, 3, 5].map(i => parseInt(value.slice(i, i + 2), 16)) as RGB;
}
export function mutationValid(value: Mutation): boolean {
  return value.action === 'clear' || (value.action === 'set' && value.bg.length === 3 &&
    value.bg.every(v => Number.isInteger(v) && v >= 0 && v <= 255) &&
    Number.isFinite(value.tol) && value.tol >= 0 && value.tol <= 1 &&
    Number.isFinite(value.softness) && value.softness >= .001 && value.softness <= 1);
}
export const object = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value);
export function readRecipe(value: Record<string, unknown>): RecipeIdentity {
  if (typeof value.recipe_document_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.recipe_document_id) || /^0+$/.test(value.recipe_document_id) ||
      typeof value.recipe_revision !== 'string' || !/^(0|[1-9][0-9]{0,19})$/.test(value.recipe_revision) || BigInt(value.recipe_revision) > 18446744073709551615n) {
    throw Error('换底预览缺少有效的照片配方版本');
  }
  return {recipe_document_id: value.recipe_document_id, recipe_revision: value.recipe_revision};
}
export function readReview(value: unknown): Review {
  if (!object(value) || value.domain !== 'production-output' || value.quality !== 'proxy-render-srgb8' ||
      ![value.width, value.height].every(n => Number.isSafeInteger(n) && Number(n) > 0 && Number(n) <= 800) ||
      ![value.before, value.after].every(s => typeof s === 'string' &&
        /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(s) && s.length <= 4 * 1024 * 1024) ||
      typeof value.note !== 'string' || value.note.length > 4096) throw Error('换底预览不是有效的真实照片输出');
  return value as unknown as Review;
}
