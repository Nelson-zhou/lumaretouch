// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, PeopleAction, PeopleResult, PeopleView} from '../people/model';
import type {BodyRef} from '../legShape/model';
import type {SourcePreview} from '../legShape/sourcePreview';
import type {MaskObject} from '../localMasks/model';
import {validOwnFaceReference, validOwnFaceReferenceSupport, validReferenceSourceStage, type OwnFaceReference, type OwnFaceReferenceSupport, type ReferenceSourceStage} from '../bodyFaceMatch/reference';
import {matchesSource, previewImage} from '../legShape/sourcePreview';

export type SkinBodyFamily = 'skin_colour' | 'skin_finish' | 'body_skin_evenness' | 'body_face_match';
export const SKIN_BODY_FAMILIES = {
  skin_colour: {operation: 'lnx.skin_colour.v1', report: 'skin_body', actions: {
    reference: 'skin_body_reference', preview: 'skin_body_preview', confirm: 'skin_body_confirm', detach: 'skin_body_detach',
  }},
  skin_finish: {operation: 'lnx.skin_finish.v1', report: 'skin_finish_body', actions: {
    reference: 'skin_finish_body_reference', preview: 'skin_finish_body_preview', confirm: 'skin_finish_body_confirm', detach: 'skin_finish_body_detach',
  }},
  body_skin_evenness: {operation: 'lnx.body_skin_evenness.v1', report: 'body_skin_evenness', actions: {
    reference: 'body_skin_evenness_reference', preview: 'body_skin_evenness_preview', confirm: 'body_skin_evenness_confirm', detach: 'body_skin_evenness_detach',
  }},
  body_face_match: {operation: 'lnx.body_face_match.v1', report: 'body_face_match', actions: {
    reference: 'body_face_match_reference', preview: 'body_face_match_preview', confirm: 'body_face_match_confirm', detach: 'body_face_match_detach',
  }},
} as const;
export type SkinBodyAction = typeof SKIN_BODY_FAMILIES[SkinBodyFamily]['actions'][keyof typeof SKIN_BODY_FAMILIES.skin_colour.actions];
type SkinBodyIdentity = {family?: SkinBodyFamily; operation_id?: 'lnx.skin_colour.v1' | 'lnx.skin_finish.v1' | 'lnx.body_skin_evenness.v1' | 'lnx.body_face_match.v1'};
export function skinBodyActionFamily(action: PeopleAction['action']): SkinBodyFamily | null {
  for (const family of ['skin_colour', 'skin_finish', 'body_skin_evenness', 'body_face_match'] as const) {
    if ((Object.values(SKIN_BODY_FAMILIES[family].actions) as string[]).includes(action)) return family;
  }
  return null;
}
/** Legacy colour DTOs remain untagged; independent families carry both exact identities. */
export function skinBodyFamilyMatches(value: unknown, family: SkinBodyFamily = 'skin_colour'): boolean {
  if (!value || typeof value !== 'object') return false;
  const identity = value as SkinBodyIdentity;
  return family !== 'skin_colour'
    ? identity.family === family && identity.operation_id === SKIN_BODY_FAMILIES[family].operation
    : identity.family === undefined && identity.operation_id === undefined;
}
export type SkinBodySource = {sha256: string; width: number; height: number};
export type SkinBodyMask = {version: 1; domain: 'source-normalized'; objects: Extract<MaskObject, {kind: 'brush'}>[]};
export type SkinBodyChoice = {body_ref: BodyRef; points_sha256: string};
export type SkinBodyReview = SkinBodyChoice & {recipe: SkinBodyMask; visible: true; unoccluded: true; ownership_confirmed: true};
export type SkinBodyReport = SkinBodyIdentity & {attached: boolean; face_ref: FaceRef; source: SkinBodySource; needs_review?: boolean; reason?: string | null;
  /** New family only; current retained identity does not prove current render observability. */
  own_face_reference?: OwnFaceReference | null};
export type SkinBodyReference = SkinBodyReport & {kind: 'reference'; source_preview: SourcePreview; bodies: SkinBodyChoice[];
  reference_overlay?: SourcePreview; reference_support?: OwnFaceReferenceSupport; reference_source_stage?: ReferenceSourceStage};
export type SkinBodyRendered = {mime: 'image/png'; base64: string; width: number; height: number; mapping: 'rendered_result'};
export type SkinBodyPreview = SkinBodyIdentity & {
  kind: 'preview'; preview_id: string; source: SkinBodySource; face_ref: FaceRef;
  before: SkinBodyRendered; after: SkinBodyRendered; overlay: SourcePreview;
  review: SkinBodyReview; runtime_quality_accepted: false;
  /** Independent body-only families: explicit positive candidate, atomically accepted with its own support. */
  amount?: number;
  reference_support?: OwnFaceReferenceSupport;
  own_face_reference?: OwnFaceReference;
  reference_source_stage?: ReferenceSourceStage;
};
export type SkinBodyPayload = SkinBodyReference | SkinBodyPreview | (SkinBodyIdentity & {kind: 'confirmed' | 'detached'; attached: boolean});
export type SkinBodyResult = {command: PeopleAction; result: PeopleResult};
export function skinBodyReceiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  const family = skinBodyActionFamily(command.action);
  if (!view || !family
    || result.protocol !== 1 || !result.success || result.outcome_unknown || result.request_id !== command.request_id
    || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'face' || view.editing_target?.scope !== 'face'
    || command.target.target_id !== view.selected_face_id || command.target.target_id !== view.editing_target.target_id
    || command.target.face_ref?.asset_sha256 !== view.binding.asset_sha256
    || !sameSkinFace(command.target.face_ref, view.editing_target.face_ref)
    || (!result.payload_released && !skinBodyFamilyMatches(result.payload, family))) return false;
  const actions = SKIN_BODY_FAMILIES[family].actions;
  return command.action === actions.confirm || command.action === actions.detach
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
      && view.association_revision >= command.association_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision
      && view.association_revision === command.association_revision;
}
export const emptyBodyMask = (): SkinBodyMask => ({version: 1, domain: 'source-normalized', objects: []});
export const skinBodyRequestFits = (command: PeopleAction): boolean => new TextEncoder().encode(JSON.stringify(command)).byteLength <= 192 * 1024;
/** Explicit positive display amount for a private body-evenness candidate; blank never stages a default. */
export function parseBodyReviewAmount(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const amount = Number(trimmed) / 100;
  return Number.isFinite(amount) && amount > 0 && amount <= 1 ? amount : null;
}
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
export function skinBodyReport(view: PeopleView | null | undefined, family: SkinBodyFamily = 'skin_colour'): SkinBodyReport | null {
  const report = view?.[SKIN_BODY_FAMILIES[family].report];
  return report && skinBodyFamilyMatches(report, family) ? report : null;
}
export function skinBodyAttached(view: PeopleView | null | undefined, family: SkinBodyFamily = 'skin_colour'): boolean | null {
  const report = skinBodyReport(view, family), selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !report || !selected || typeof report.attached !== 'boolean' || !sameSkinFace(report.face_ref, selected.face_ref)
    || report.source?.sha256 !== view.binding.asset_sha256) return null;
  return report.attached;
}
export function referenceMatches(reference: SkinBodyReference, view: PeopleView, family: SkinBodyFamily = 'skin_colour'): boolean {
  const source = reference.source;
  return reference.kind === 'reference' && skinBodyFamilyMatches(reference, family) && skinBodyTarget(view) && sameSkinFace(reference.face_ref, view.editing_target?.face_ref)
    && digest(source?.sha256) && source.sha256 === view.binding.asset_sha256 && extent(source.width) && extent(source.height)
    && Array.isArray(reference.bodies) && reference.bodies.every(body => digest(body.points_sha256)
      && body.body_ref.asset_sha256 === source.sha256 && token(body.body_ref.body_instance_id) && revision(body.body_ref.analysis_revision))
    && new Set(reference.bodies.map(body => bodyRefKey(body.body_ref))).size === reference.bodies.length
    && (family !== 'body_face_match' || ownFaceReferenceMatches(reference));
}
/** Only actual same-person source measurements, disclosed with their real full-frame reference overlay. */
export function ownFaceReferenceMatches(reference: SkinBodyReference): boolean {
  const png = (value?: SourcePreview | null) => !!value && typeof value.base64 === 'string'
    && value.base64.length > 0 && value.base64.length <= 8 * 1024 * 1024 && /^[A-Za-z0-9+/]+={0,2}$/.test(value.base64);
  if (!png(reference.source_preview) || !png(reference.reference_overlay)) return false;
  const image = previewImage(reference.source_preview), overlay = previewImage(reference.reference_overlay ?? null);
  return !!image && matchesSource(image, {...reference.source, orientation: 'exif_normalized_once'})
    && matchesSource(overlay, {...reference.source, orientation: 'exif_normalized_once'})
    && image.decodedWidth === overlay.decodedWidth && image.decodedHeight === overlay.decodedHeight
    && validReferenceSourceStage(reference.reference_source_stage)
    && validOwnFaceReference(reference.own_face_reference, reference.face_ref)
    && bodyReviewKey(reference.own_face_reference.face_skin_observation) === bodyReviewKey(reference.reference_support?.face_skin_observation)
    && validOwnFaceReferenceSupport(reference.reference_support, reference.face_ref, reference.source,
      {width: image.decodedWidth, height: image.decodedHeight});
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
export function previewMatches(preview: SkinBodyPreview, reference: SkinBodyReference, review: SkinBodyReview, family: SkinBodyFamily = 'skin_colour', amount?: number): boolean {
  return preview.kind === 'preview' && skinBodyFamilyMatches(preview, family) && skinBodyFamilyMatches(reference, family)
    && (!['body_skin_evenness', 'body_face_match'].includes(family) || (typeof amount === 'number' && Number.isFinite(amount) && amount > 0 && amount <= 1 && preview.amount === amount))
    && (family !== 'body_face_match' || (ownFaceReferenceMatches(reference)
      && preview.reference_source_stage === reference.reference_source_stage
      && bodyReviewKey(preview.own_face_reference) === bodyReviewKey(reference.own_face_reference)
      && bodyReviewKey(preview.reference_support) === bodyReviewKey(reference.reference_support)))
    && token(preview.preview_id) && sameSkinFace(preview.face_ref, reference.face_ref)
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
