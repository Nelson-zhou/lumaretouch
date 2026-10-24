// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleContext, type FaceRef, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model';

/** Product-local recipe names, never identifiers for the historical SHAPE_PRESETS. */
export const FACE_STYLES = ['classic', 'youthful', 'bold', 'youth', 'round', 'long', 'square'] as const;
export const FACE_STYLE_LABELS: Record<FaceStyle, string> = {classic: '经典', youthful: '幼态', bold: '英气', youth: '少年', round: '圆脸适用', long: '长脸适用', square: '方脸适用'};
export type FaceStyle = typeof FACE_STYLES[number];
export type FaceStyleAction = 'face_style_catalog' | 'face_style_preview' | 'face_style_image' | 'face_style_confirm';
export type FaceStyleReceipt = {command: PeopleAction; result: PeopleResult};
export const isFaceStyle = (value: unknown): value is FaceStyle => FACE_STYLES.some(style => style === value);
export const sameFace = (a: FaceRef | null | undefined, b: FaceRef | null | undefined): boolean => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export const faceStyleBinding = (view: PeopleView | null): string => JSON.stringify(view
  ? [view.binding, view.revision, view.association_revision, view.editing_target, view.selected_face_id] : null);
export function faceStyleTargetReady(view: PeopleView | null): boolean {
  if (!view || !peopleContext(view)) return false;
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return !!selected && selected.enabled && selected.analysis_status === 'verified'
    && selected.face_ref.asset_sha256 === view.binding.asset_sha256 && view.editing_target?.scope === 'face'
    && view.editing_target.target_id === selected.face_ref.face_instance_id
    && sameFace(view.editing_target.face_ref, selected.face_ref) && sameFace(view.resolved?.face_ref, selected.face_ref)
    && view.resolved?.state_revision === view.revision && view.resolved.association_revision === view.association_revision
    && view.resolved.conflicts.length === 0;
}
/** Disclosure only: the backend validates the complete candidate, including compatible zero recipes.
 * An active historical control is never automatically cleared, converted, or a blanket UI veto. */
export function faceStyleLegacyWarning(view: PeopleView | null): string | null {
  if (!faceStyleTargetReady(view)) return null;
  const values = ['/slim_face', '/small_chin', '/big_eye', '/smile'].map(path => view!.resolved!.operations['lnx.deform.v1']?.[path]?.value);
  if (values.some(value => typeof value !== 'number' || !Number.isFinite(value)))
    return '旧版参数读数不完整。预览会由引擎检查完整实际参数；不会将未知读数当作 0，也不会清除或换算旧效果。';
  return values.some(value => value !== 0)
    ? '此脸保留了旧版效果。新版候选不会清除或换算旧参数；引擎将检查完整合并后的实际效果，仅拒绝真正冲突的候选。兼容的配方或 0 程度仍可预览。'
    : null;
}
export function parseFaceStyleAmount(text: string): number | null {
  if (!text.trim() || !/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())) return null;
  const value = Number(text) / 100;
  return Number.isFinite(value) && value >= 0 && value <= 1 ? value : null;
}
export function faceStyleReceiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!faceStyleEchoMatches(command, result) || !view || !['face_style_catalog', 'face_style_preview', 'face_style_image', 'face_style_confirm'].includes(command.action)
    || result.protocol !== 1 || !result.success || result.outcome_unknown
    || result.request_id !== command.request_id || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'face' || view.editing_target?.scope !== 'face'
    || command.target.target_id !== view.selected_face_id || command.target.target_id !== view.editing_target.target_id
    || command.target.face_ref?.asset_sha256 !== view.binding.asset_sha256
    || !sameFace(command.target.face_ref, view.editing_target.face_ref)) return false;
  return command.action === 'face_style_confirm'
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
      && view.association_revision === command.association_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision
      && view.association_revision === command.association_revision;
}

import {digest, validEndpoint, validFaceRef, type PeopleEndpointProof} from '../people/transferProof';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneImageMetadata, validCollarboneImage, verifyCollarboneImage,
  type CollarboneImage, type CollarboneVisual} from '../collarbone/transferModel';
import type {SpillImage} from '../spillRemoval/model';
export type FaceStyleRecipe = {version: 1; style: FaceStyle; amount: number};
export type FaceStyleVisual = Omit<CollarboneVisual, 'coverage_sha256'>;
export type FaceStyleReview = {version: 1; token: string; recipe: FaceStyleRecipe; owner: PeopleEndpointProof;
  face_ref: FaceRef; patches_sha256: string; visual: FaceStyleVisual; review_sha256: string};
export type FaceStyleAck = {review_sha256: string; before_sha256: string; after_sha256: string};
export type FaceStyleSide = 'before' | 'after';
export const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const keys = (value: Record<string, unknown>, expected: string[]) => Object.keys(value).sort().join('|') === [...expected].sort().join('|');
const size = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2
  && v.every(n => Number.isSafeInteger(n) && n > 0 && n <= 4294967295);
export function validFaceStyleRecipe(v: unknown): v is FaceStyleRecipe {
  return object(v) && keys(v, ['version', 'style', 'amount']) && v.version === 1 && isFaceStyle(v.style)
    && typeof v.amount === 'number' && Number.isFinite(v.amount) && v.amount >= 0 && v.amount <= 1;
}
function validVisual(v: unknown, owner: PeopleEndpointProof): v is FaceStyleVisual {
  if (!object(v) || !keys(v, ['version', 'document_id', 'revision', 'source_proof', 'before_state_sha256',
    'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256', 'source_size',
    'before_output_size', 'after_output_size', 'before', 'after']) || v.version !== 1
    || v.document_id !== owner.document.document_id || v.revision !== String(owner.document.revision)
    || !sameSpillSourceProof(v.source_proof, owner.source_proof)
    || !['before_state_sha256', 'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256'].every(key => digest(v[key]))
    || !size(v.source_size) || !size(v.before_output_size) || !size(v.after_output_size)
    || !validCollarboneImageMetadata(v.before) || !validCollarboneImageMetadata(v.after)) return false;
  const extent = (n: number, edge: number) => {
    if (edge <= 1024) return n;
    const product = n * 1024, q = Math.floor(product / edge), r = product - q * edge;
    return Math.max(1, q + (r * 2 > edge || r * 2 === edge && q % 2 === 1 ? 1 : 0));
  };
  const matches = (image: CollarboneImage, output: [number, number]) => image.width === extent(output[0], Math.max(...output))
    && image.height === extent(output[1], Math.max(...output));
  const source = owner.source_proof.creative_source;
  return (!source || source.width === v.source_size[0] && source.height === v.source_size[1])
    && matches(v.before, v.before_output_size) && matches(v.after, v.after_output_size);
}
export function validFaceStyleReview(value: unknown, view: PeopleView | null, recipe: FaceStyleRecipe): value is FaceStyleReview {
  if (!view || !faceStyleTargetReady(view) || !object(value)
    || !keys(value, ['version', 'token', 'recipe', 'owner', 'face_ref', 'patches_sha256', 'visual', 'review_sha256'])
    || value.version !== 1 || typeof value.token !== 'string' || !/^[a-f0-9]{32}$/.test(value.token)
    || !validFaceStyleRecipe(value.recipe) || value.recipe.style !== recipe.style || value.recipe.amount !== recipe.amount
    || !validEndpoint(value.owner) || !validFaceRef(value.face_ref) || !sameFace(value.face_ref, view.editing_target?.face_ref)
    || !digest(value.patches_sha256) || !digest(value.review_sha256)) return false;
  const owner = value.owner;
  return owner.document.document_id === view.binding.document_id && owner.document.epoch === view.binding.document_epoch
    && owner.document.revision === view.binding.document_revision && owner.state_revision === view.revision
    && owner.association_revision === view.association_revision && owner.source_proof.asset_sha256 === view.binding.asset_sha256
    && validVisual(value.visual, owner);
}
export const faceStyleAck = (review: FaceStyleReview): FaceStyleAck => ({review_sha256: review.review_sha256,
  before_sha256: review.visual.before.sha256, after_sha256: review.visual.after.sha256});
export function sameFaceStyleAck(value: unknown, expected: FaceStyleAck): boolean {
  return object(value) && keys(value, ['review_sha256', 'before_sha256', 'after_sha256'])
    && value.review_sha256 === expected.review_sha256 && value.before_sha256 === expected.before_sha256 && value.after_sha256 === expected.after_sha256;
}
export async function faceStyleImage(value: unknown, review: FaceStyleReview, side: FaceStyleSide): Promise<SpillImage | null> {
  if (!object(value) || !keys(value, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image'])
    || value.kind !== 'face_style_image' || value.token !== review.token || value.side !== side
    || value.review_sha256 !== review.review_sha256 || value.sha256 !== review.visual[side].sha256
    || !validCollarboneImage(value.image)) return null;
  const image = value.image, expected = review.visual[side];
  return image.sha256 === expected.sha256 && image.width === expected.width && image.height === expected.height
    && await verifyCollarboneImage(image) ? image : null;
}

/** Echo validation is semantic object equality, independent of key insertion order. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value) ?? 'undefined';
}
export function faceStyleEchoMatches(command: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _requestId, ...request} = command;
  return object(result.face_style_request) && canonical(result.face_style_request) === canonical(request);
}
