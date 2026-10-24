// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, PeopleAction, PeopleResult, PeopleView} from '../people/model';
import type {BodyRef} from '../legShape/model';
import type {SourcePreview} from '../legShape/sourcePreview';
import type {MaskObject} from '../localMasks/model';

export type SkinBodyAction = 'skin_body_reference' | 'skin_body_preview' | 'skin_body_confirm' | 'skin_body_detach';
export type SkinBodySource = {sha256: string; width: number; height: number};
export type SkinBodyMask = {version: 1; domain: 'source-normalized'; objects: Extract<MaskObject, {kind: 'brush'}>[]};
export type SkinBodyChoice = {body_ref: BodyRef; points_sha256: string};
export type SkinBodyReview = SkinBodyChoice & {recipe: SkinBodyMask; visible: true; unoccluded: true; ownership_confirmed: true};
export type SkinBodyReport = {attached: boolean; face_ref: FaceRef; source: SkinBodySource; needs_review?: boolean; reason?: string | null};
export type SkinBodyReference = SkinBodyReport & {kind: 'reference'; source_preview: SourcePreview; bodies: SkinBodyChoice[]};
export type SkinBodyRendered = {mime: 'image/png'; base64: string; width: number; height: number; mapping: 'rendered_result'};
export type SkinBodyPreview = {
  kind: 'preview'; preview_id: string; source: SkinBodySource; face_ref: FaceRef;
  before: SkinBodyRendered; after: SkinBodyRendered; overlay: SourcePreview;
  review: SkinBodyReview; runtime_quality_accepted: false;
};
export type SkinBodyPayload = SkinBodyReference | SkinBodyPreview | {kind: 'confirmed' | 'detached'; attached: boolean};
export type SkinBodyResult = {command: PeopleAction; result: PeopleResult};
export function skinBodyReceiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!view || !['skin_body_reference', 'skin_body_preview', 'skin_body_confirm', 'skin_body_detach'].includes(command.action)
    || result.protocol !== 1 || !result.success || result.outcome_unknown || result.request_id !== command.request_id
    || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'face' || view.editing_target?.scope !== 'face'
    || command.target.target_id !== view.selected_face_id || command.target.target_id !== view.editing_target.target_id
    || command.target.face_ref?.asset_sha256 !== view.binding.asset_sha256
    || !sameSkinFace(command.target.face_ref, view.editing_target.face_ref)) return false;
  return command.action === 'skin_body_confirm' || command.action === 'skin_body_detach'
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
      && view.association_revision >= command.association_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision
      && view.association_revision === command.association_revision;
}
export const emptyBodyMask = (): SkinBodyMask => ({version: 1, domain: 'source-normalized', objects: []});
export const skinBodyRequestFits = (command: PeopleAction): boolean => new TextEncoder().encode(JSON.stringify(command)).byteLength <= 192 * 1024;
export const bodyRefKey = (ref: BodyRef): string => JSON.stringify([ref.asset_sha256, ref.body_instance_id, ref.analysis_revision]);
/** Stable comparison of a returned canonical recipe, not a trust-bearing server digest. */
export function bodyReviewKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(bodyReviewKey).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
    return '{' + entries.map(([key, item]) => JSON.stringify(key) + ':' + bodyReviewKey(item)).join(',') + '}';
  }
  return JSON.stringify(value) ?? 'undefined';
}
export const sameSkinFace = (a?: FaceRef | null, b?: FaceRef | null): boolean => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export const sameSkinSource = (a?: SkinBodySource | null, b?: SkinBodySource | null): boolean => !!a && !!b
  && a.sha256 === b.sha256 && a.width === b.width && a.height === b.height;
const digest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const token = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 128;
const extent = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 2 && value <= 1_000_000;
const revision = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;

export function skinBodyTarget(view: PeopleView | null | undefined): boolean {
  if (!view || view.editing_target?.scope !== 'face' || view.editing_target.target_id !== view.selected_face_id) return false;
  const face = view.faces.find(row => row.face_ref.face_instance_id === view.selected_face_id);
  return !!face && face.enabled && face.analysis_status === 'verified'
    && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameSkinFace(face.face_ref, view.editing_target.face_ref);
}
/** Attachment is a refreshed engine fact, never inferred from a local painted draft. */
export function skinBodyAttached(view: PeopleView | null | undefined): boolean | null {
  const report = view?.skin_body, selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !report || !selected || !sameSkinFace(report.face_ref, selected.face_ref)
    || report.source.sha256 !== view.binding.asset_sha256) return null;
  return report.attached;
}
export function referenceMatches(reference: SkinBodyReference, view: PeopleView): boolean {
  const source = reference.source;
  return reference.kind === 'reference' && skinBodyTarget(view) && sameSkinFace(reference.face_ref, view.editing_target?.face_ref)
    && digest(source?.sha256) && source.sha256 === view.binding.asset_sha256 && extent(source.width) && extent(source.height)
    && Array.isArray(reference.bodies) && reference.bodies.every(body => digest(body.points_sha256)
      && body.body_ref.asset_sha256 === source.sha256 && token(body.body_ref.body_instance_id) && revision(body.body_ref.analysis_revision))
    && new Set(reference.bodies.map(body => bodyRefKey(body.body_ref))).size === reference.bodies.length;
}
export function bodyReview(choice: SkinBodyChoice, recipe: SkinBodyMask, confirmations: {visible: boolean; unoccluded: boolean; ownership_confirmed: boolean}): SkinBodyReview {
  if (!confirmations.visible || !confirmations.unoccluded || !confirmations.ownership_confirmed) throw Error('请确认所画身体皮肤可见、无遮挡并属于当前人物。');
  if (recipe.version !== 1 || recipe.domain !== 'source-normalized' || recipe.objects.length > 64
    || !recipe.objects.some(object => object.enabled && object.operation === 'add' && object.opacity > 0)
    || recipe.objects.some(object => object.kind !== 'brush' || !['add', 'subtract'].includes(object.operation)
      || !Number.isFinite(object.feather) || object.feather < 0 || object.feather > 100
      || !Number.isFinite(object.opacity) || object.opacity < 0 || object.opacity > 1
      || object.axes.length !== 2 || object.axes.some(axis => axis.length !== 2 || axis.some(n => !Number.isFinite(n) || Math.abs(n) > 4))
      || Math.abs(object.axes[0][0] * object.axes[1][1] - object.axes[0][1] * object.axes[1][0]) < 1e-12
      || object.points.length < 1 || object.points.length > 1024
      || object.points.some(point => point.length !== 2 || point.some(n => !Number.isFinite(n) || n < 0 || n > 1)))
    || recipe.objects.reduce((sum, object) => sum + object.points.length, 0) > 4096) throw Error('需要有界的添加/减去笔刷草稿，且至少包含一笔有效添加。');
  return {body_ref: {...choice.body_ref}, points_sha256: choice.points_sha256, recipe: structuredClone(recipe),
    visible: true, unoccluded: true, ownership_confirmed: true};
}
export function renderedSkinImage(value: SkinBodyRendered | null | undefined): string | null {
  if (!value || value.mime !== 'image/png' || value.mapping !== 'rendered_result'
    || !Number.isSafeInteger(value.width) || !Number.isSafeInteger(value.height)
    || value.width < 1 || value.height < 1 || value.width > 1280 || value.height > 1280
    || typeof value.base64 !== 'string' || !value.base64.length || value.base64.length > 8 * 1024 * 1024
    || !/^[A-Za-z0-9+/]+={0,2}$/.test(value.base64)) return null;
  return `data:image/png;base64,${value.base64}`;
}
export function previewMatches(preview: SkinBodyPreview, reference: SkinBodyReference, review: SkinBodyReview): boolean {
  return preview.kind === 'preview' && token(preview.preview_id) && sameSkinFace(preview.face_ref, reference.face_ref)
    && sameSkinSource(preview.source, reference.source) && preview.runtime_quality_accepted === false
    && bodyReviewKey(preview.review) === bodyReviewKey(review)
    && !!renderedSkinImage(preview.before) && !!renderedSkinImage(preview.after)
    && preview.before.width === preview.after.width && preview.before.height === preview.after.height;
}

/** Whole-canvas pixel EDGES: mask rasterization later maps p*w - .5, not p*(w-1). */
export function bodyMaskPoint(clientX: number, clientY: number, rect: {left: number; top: number; width: number; height: number}): [number, number] | null {
  if (![clientX, clientY, rect.left, rect.top, rect.width, rect.height].every(Number.isFinite) || rect.width <= 0 || rect.height <= 0) return null;
  const x = (clientX - rect.left) / rect.width, y = (clientY - rect.top) / rect.height;
  return x < 0 || x > 1 || y < 0 || y > 1 ? null : [x, y];
}
