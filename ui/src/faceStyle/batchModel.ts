// SPDX-License-Identifier: GPL-3.0-or-later
import {validCollarboneVisualForTarget, type CollarboneImage} from '../collarbone/transferModel';
import type {PeopleTransferReview} from '../people/transferProof';
import type {PeopleView} from '../people/model';
import {validFaceStyleRecipe, type FaceStyleRecipe, type FaceStyleVisual} from './model';

export const FACE_STYLE_BATCH_LIMIT = 16;
/** Binding v1 mirrors face_style_recipes.py::_BINDINGS and catalogue().owned_parameters.
 * These are keys only. Recipe values are composed by the engine, never read from a donor face. */
const bilateral = (field: string) => ['linked', 'left', 'right'].map(side => `/${field}/${side}`);
const OWNED_PARAMETERS: Readonly<Record<string, readonly string[]>> = Object.freeze({
  'lnx.face_contour.v1': [...bilateral('temple'), ...bilateral('cheekbone'), ...bilateral('jaw')],
  'lnx.face_size.v1': ['/amount'],
  'lnx.mid_face.v1': ['/amount'],
  'lnx.lower_face.v1': ['/amount'],
  'lnx.chin_shape.v1': ['/linked', '/left', '/right'],
  'lnx.chin_length.v1': ['/amount'],
  'lnx.brow_shape.v1': bilateral('position'),
  'lnx.eye_shape.v1': [...bilateral('size'), ...bilateral('spacing'), ...bilateral('position')],
  'lnx.nose_shape.v1': ['/height'],
  'lnx.mouth_shape.v1': ['/vertical'],
});
export const faceStyleSelection = (): Record<string, string[]> => Object.fromEntries(
  Object.keys(OWNED_PARAMETERS).sort().map(op => [op, [...OWNED_PARAMETERS[op]]]));
/** The current face is an endpoint anchor, not a donor-value or donor-conflict gate. */
export function faceStyleBatchSourceReady(view: PeopleView | null): boolean {
  if (!view) return false;
  const face = view.faces.find(row => row.face_ref.face_instance_id === view.selected_face_id);
  return !!face && face.enabled && face.analysis_status === 'verified' && face.face_ref.asset_sha256 === view.binding.asset_sha256;
}
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: string[]) => Object.keys(v).sort().join('|') === [...expected].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export function validFaceStyleSelection(value: unknown): value is Record<string, string[]> {
  return object(value) && keys(value, Object.keys(OWNED_PARAMETERS)) && Object.entries(OWNED_PARAMETERS).every(([op, paths]) => {
    const actual = value[op];
    return Array.isArray(actual) && actual.length === paths.length && actual.every(path => typeof path === 'string')
      && [...actual].sort().join('|') === [...paths].sort().join('|');
  });
}
export function sameFaceStyleRecipe(value: unknown, expected: FaceStyleRecipe): value is FaceStyleRecipe {
  return validFaceStyleRecipe(value) && validFaceStyleRecipe(expected)
    && value.version === expected.version && value.style === expected.style && value.amount === expected.amount;
}
export type FaceStyleBatchVisual = FaceStyleVisual & {recipe_sha256: string};
export type FaceStyleBatchAck = {document_id: string; revision: string; before_sha256: string; after_sha256: string; recipe_sha256: string};
export function validFaceStyleBatchVisual(value: unknown, review: PeopleTransferReview): value is FaceStyleBatchVisual {
  if (!object(value) || !hash(value.recipe_sha256) || !validFaceStyleRecipe(review.face_style)) return false;
  // Reuse the identical PNG/source/state contract, without accepting a coverage field on this wire.
  const {recipe_sha256, ...visual} = value;
  return validCollarboneVisualForTarget({...visual, coverage_sha256: recipe_sha256},
    review.target_document.document_id, String(review.target_document.revision), review.target_owner.source_proof)
    && !Object.hasOwn(value, 'coverage_sha256');
}
/** Stable cross-language recipe binding, independent of JSON number spellings.
 * SHA-256(UTF8("lumaretouch.face-style.v1\\0" + style + "\\0") || IEEE754-f64-BE(amount)). */
export async function faceStyleRecipeDigest(recipe: FaceStyleRecipe): Promise<string> {
  if (!validFaceStyleRecipe(recipe)) throw Error('新版脸型配方无效');
  const prefix = new TextEncoder().encode(`lumaretouch.face-style.v1\0${recipe.style}\0`);
  const bytes = new Uint8Array(prefix.length + 8); bytes.set(prefix);
  new DataView(bytes.buffer).setFloat64(prefix.length, recipe.amount === 0 ? 0 : recipe.amount, false);
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
}
export async function verifyFaceStyleBatchRecipe(value: FaceStyleBatchVisual, recipe: FaceStyleRecipe): Promise<boolean> {
  try {return value.recipe_sha256 === await faceStyleRecipeDigest(recipe);} catch {return false;}
}
export function faceStyleBatchReviewKey(token: string, value: FaceStyleBatchVisual): string {
  return JSON.stringify(['face_style.v1', token, value]);
}
export function faceStyleBatchImagesReady(token: string, values: (FaceStyleBatchVisual | undefined)[], ready: Record<string, boolean>): boolean {
  return values.length <= FACE_STYLE_BATCH_LIMIT && values.every(value => !!value && ready[faceStyleBatchReviewKey(token, value)] === true);
}
export function faceStyleBatchAck(values: FaceStyleBatchVisual[]): FaceStyleBatchAck[] {
  return values.map(value => ({document_id: value.document_id, revision: value.revision,
    before_sha256: value.before.sha256, after_sha256: value.after.sha256, recipe_sha256: value.recipe_sha256}));
}
export function sameFaceStyleBatchAck(value: unknown, expected: FaceStyleBatchAck[] | undefined): value is FaceStyleBatchAck[] {
  if (!Array.isArray(value) || !expected || !expected.length || value.length !== expected.length || value.length > FACE_STYLE_BATCH_LIMIT
    || new Set(expected.map(row => row.document_id)).size !== expected.length) return false;
  return value.every((row, i) => object(row) && keys(row, ['document_id', 'revision', 'before_sha256', 'after_sha256', 'recipe_sha256'])
    && Object.keys(row).every(key => row[key] === expected[i][key as keyof FaceStyleBatchAck]));
}
export const validFaceStyleBatchAck = (value: unknown, reviews: FaceStyleBatchVisual[]) => sameFaceStyleBatchAck(value, faceStyleBatchAck(reviews));
export type FaceStyleBatchImageMetadata = CollarboneImage;
