// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleContext, type FaceRef, type PeopleEnvelope, type PeopleResult, type PeopleView} from '../people/model';
import type {EffectiveSourceProof} from '../people/transferProof';
import {NECK_WRINKLE_OPERATION, NECK_WRINKLE_LIMITS, bodyKey, canonical, extent, finite, hash, keys, object,
  revision, token, validBody, validSource, type NeckBodyChoice, type NeckReview, type NeckSource} from './review';

export type NeckAction = 'neck_wrinkle_reference' | 'neck_wrinkle_preview' | 'neck_wrinkle_crop'
  | 'neck_wrinkle_confirm' | 'neck_wrinkle_detach';
export type NeckCommand = PeopleEnvelope & {action: NeckAction | 'patch' | 'select'; payload: Record<string, unknown>};
export type NeckResult = Omit<PeopleResult, 'action'> & {action: NeckCommand['action']};
export type NeckReceipt = {command: NeckCommand; result: NeckResult};
export type NeckImage = {mime: 'image/png'; base64: string; width: number; height: number; sha256: string};
export type NeckRect = [number, number, number, number];
export type NeckPlane = 'source' | 'before' | 'after';
export type NeckIdentity = {family: 'neck_wrinkle'; operation_id: typeof NECK_WRINKLE_OPERATION};
export type NeckSourceBinding = {source: NeckSource; source_proof: EffectiveSourceProof;
  input_sha256: string; repair_sha256: string};
export type NeckReference = NeckIdentity & NeckSourceBinding & {kind: 'reference'; reference_id: string;
  face_ref: FaceRef; bodies: NeckBodyChoice[]; source_image: NeckImage; attached: boolean};
export type NeckPreview = NeckIdentity & NeckSourceBinding & {kind: 'preview'; preview_id: string; face_ref: FaceRef;
  review: NeckReview; amount: number; before: NeckImage; after: NeckImage; support: NeckImage;
  before_output_size: [number, number]; after_output_size: [number, number]; runtime_quality_accepted: false};
export type NeckCropRequest = {plane: 'source'; reference_id: string; rect: NeckRect}
  | {plane: 'before' | 'after'; preview_id: string; rect: NeckRect};
export type NeckCrop = NeckIdentity & NeckSourceBinding & {kind: 'crop'; plane: NeckPlane; rect: NeckRect;
  domain: 'source' | 'rendered_result'; image: NeckImage; reference_id?: string; preview_id?: string};
export type NeckInspectionAck = {rect: NeckRect; before_sha256: string; after_sha256: string};
export type NeckConfirm = {preview_id: string; reviewed: true; before_sha256: string; after_sha256: string;
  support_sha256: string; inspection: NeckInspectionAck};
export type NeckReport = NeckIdentity & {attached: boolean; face_ref: FaceRef; source: NeckSource;
  needs_review?: boolean; reason?: string | null};
export type NeckSnapshot = {value: PeopleView | null; enabled: boolean; pending: boolean; uncertain: boolean;
  refreshRequired?: boolean; message?: string; lastResult: NeckReceipt | null;
  capability: {protocol?: number; available?: boolean; reason?: string | null}; report?: NeckReport | null};
/** Stable application-lifetime adapter over the EXISTING people request/receipt owner.
 * getSnapshot returns a cached immutable object; subscribe follows that owner.
 * This interface introduces no native request, receipt poller, undo or replay store. */
export interface NeckWrinklePort {
  getSnapshot: () => NeckSnapshot;
  subscribe: (listener: () => void) => () => void;
  submitCaptured: (command: NeckCommand) => Promise<void>;
  check: () => Promise<void>;
  refreshCurrent: () => Promise<void>;
}
export const sameFace = (a: FaceRef | null | undefined, b: FaceRef | null | undefined): boolean => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export const validFace = (v: unknown): v is FaceRef => object(v) && keys(v, ['asset_sha256', 'face_instance_id', 'analysis_revision'])
  && hash(v.asset_sha256) && token(v.face_instance_id) && revision(v.analysis_revision);
export const family = (v: unknown): v is NeckIdentity => object(v) && v.family === 'neck_wrinkle' && v.operation_id === NECK_WRINKLE_OPERATION;
export const isNeckAction = (v: string): v is NeckAction => ['neck_wrinkle_reference', 'neck_wrinkle_preview', 'neck_wrinkle_crop',
  'neck_wrinkle_confirm', 'neck_wrinkle_detach'].includes(v);
export function sourceProof(v: unknown, source: NeckSource): v is EffectiveSourceProof {
  if (!object(v) || !keys(v, ['asset_sha256', 'original_sha256', 'creative_source']) || v.asset_sha256 !== source.sha256 || !hash(v.original_sha256)) return false;
  return v.creative_source === null ? v.asset_sha256 === v.original_sha256 : object(v.creative_source)
    && keys(v.creative_source, ['sha256', 'width', 'height']) && v.creative_source.sha256 === source.sha256
    && v.creative_source.width === source.width && v.creative_source.height === source.height;
}
export const sourceBinding = (v: unknown): v is NeckSourceBinding => object(v) && validSource(v.source)
  && sourceProof(v.source_proof, v.source) && hash(v.input_sha256) && hash(v.repair_sha256);
export const sameSourceBinding = (a: NeckSourceBinding, b: NeckSourceBinding): boolean => canonical(a.source) === canonical(b.source)
  && canonical(a.source_proof) === canonical(b.source_proof) && a.input_sha256 === b.input_sha256 && a.repair_sha256 === b.repair_sha256;
export function targetReady(view: PeopleView | null | undefined, measured = false): boolean {
  if (!view || !token(view.binding.document_id) || !token(view.binding.document_epoch) || !hash(view.binding.asset_sha256)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || view.editing_target?.scope !== 'face' || view.selected_face_id !== view.editing_target.target_id) return false;
  const face = view.faces.find(row => row.face_ref.face_instance_id === view.selected_face_id);
  return !!face && validFace(face.face_ref) && face.face_ref.asset_sha256 === view.binding.asset_sha256
    && sameFace(face.face_ref, view.editing_target.face_ref) && (!measured || face.enabled && face.analysis_status === 'verified');
}
export const neckBinding = (view: PeopleView | null): string => view ? canonical([view.binding, view.revision,
  view.association_revision, view.selected_face_id, view.editing_target, view.faces, view.resolved,
  view.editing_overrides[NECK_WRINKLE_OPERATION], view.links, view.refusals]) : 'unavailable';
export function neckAmount(view: PeopleView | null): number | null {
  if (!targetReady(view) || !view?.resolved || !sameFace(view.resolved.face_ref, view.editing_target?.face_ref)
    || view.resolved.state_revision !== view.revision || view.resolved.association_revision !== view.association_revision
    || view.resolved.conflicts.some(conflict => conflict.operation_id === NECK_WRINKLE_OPERATION)) return null;
  const amount = view.resolved.operations[NECK_WRINKLE_OPERATION]?.['/amount'];
  if (!amount || !finite(amount.value, 0, 1)) return null;
  // This slice deliberately fences shared active intent; don't relabel inherited
  // nonzero state as a locally reviewed face amount.
  if (amount.scope !== 'face' && amount.value !== 0) return null;
  if (amount.scope === 'face' && amount.target_id !== view.selected_face_id) return null;
  return amount.value;
}
export function capture(view: PeopleView | null, action: NeckCommand['action'], payload: Record<string, unknown>): NeckCommand | null {
  if (!targetReady(view)) return null;
  const context = peopleContext(view); if (!context) return null;
  return {...structuredClone(context), request_id: crypto.randomUUID(), action, payload: structuredClone(payload)};
}
export const requestFits = (command: NeckCommand): boolean => new TextEncoder().encode(JSON.stringify(command)).byteLength <= NECK_WRINKLE_LIMITS.requestBytes;
export function imageMetadata(v: unknown, edge = 1280): v is NeckImage {
  return object(v) && keys(v, ['mime', 'base64', 'width', 'height', 'sha256']) && v.mime === 'image/png'
    && revision(v.width) && v.width > 0 && v.width <= edge && revision(v.height) && v.height > 0 && v.height <= edge
    && hash(v.sha256) && typeof v.base64 === 'string' && v.base64.length > 0 && v.base64.length <= 5592408
    && v.base64.length % 4 === 0 && v.base64.startsWith('iVBOR') && /^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);
}
export async function verifyImage(v: NeckImage): Promise<boolean> {
  try {
    if (!imageMetadata(v)) return false;
    const raw = atob(v.base64); if (btoa(raw) !== v.base64 || raw.length < 33 || raw.length > 4 * 1024 * 1024) return false;
    const bytes = Uint8Array.from(raw, char => char.charCodeAt(0)), header = new DataView(bytes.buffer);
    if (![137, 80, 78, 71, 13, 10, 26, 10].every((n, i) => bytes[i] === n) || header.getUint32(8) !== 13
      || header.getUint32(12) !== 0x49484452 || header.getUint32(16) !== v.width || header.getUint32(20) !== v.height) return false;
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
    return digest === v.sha256;
  } catch {return false;}
}
export const imageUrl = (v: NeckImage): string => `data:image/png;base64,${v.base64}`;
const fullFrame = (image: NeckImage, width: number, height: number) => image.width <= width && image.height <= height
  && Math.abs(image.width * height - image.height * width) <= Math.max(width, height);
export function validReference(v: unknown, view: PeopleView): v is NeckReference {
  return object(v) && keys(v, ['kind', 'family', 'operation_id', 'reference_id', 'source', 'source_proof', 'input_sha256', 'repair_sha256',
    'face_ref', 'bodies', 'source_image', 'attached']) && family(v) && sourceBinding(v) && v.kind === 'reference'
    && token(v.reference_id) && typeof v.attached === 'boolean' && targetReady(view, true)
    && validFace(v.face_ref) && sameFace(v.face_ref, view.editing_target?.face_ref) && v.source.sha256 === view.binding.asset_sha256
    && imageMetadata(v.source_image) && fullFrame(v.source_image, v.source.width, v.source.height)
    && Array.isArray(v.bodies) && v.bodies.length <= 64 && v.bodies.every(body => object(body) && keys(body, ['body_ref', 'points_sha256'])
      && validBody(body.body_ref) && body.body_ref.asset_sha256 === v.source.sha256 && hash(body.points_sha256))
    && new Set(v.bodies.map(body => bodyKey(body.body_ref))).size === v.bodies.length;
}
const outputSize = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && v.every(extent);
export function validPreview(v: unknown, reference: NeckReference, review: NeckReview, amount: number): v is NeckPreview {
  return object(v) && keys(v, ['kind', 'family', 'operation_id', 'preview_id', 'source', 'source_proof', 'input_sha256', 'repair_sha256',
    'face_ref', 'review', 'amount', 'before', 'after', 'support', 'before_output_size', 'after_output_size', 'runtime_quality_accepted'])
    && family(v) && sourceBinding(v) && v.kind === 'preview' && token(v.preview_id) && sameSourceBinding(v, reference)
    && validFace(v.face_ref) && sameFace(v.face_ref, reference.face_ref) && canonical(v.review) === canonical(review)
    && finite(amount, Number.MIN_VALUE, 1) && v.amount === amount && v.runtime_quality_accepted === false
    && outputSize(v.before_output_size) && outputSize(v.after_output_size) && canonical(v.before_output_size) === canonical(v.after_output_size)
    && imageMetadata(v.before) && imageMetadata(v.after) && imageMetadata(v.support)
    && v.before.width === v.after.width && v.before.height === v.after.height
    && fullFrame(v.before, ...v.before_output_size) && fullFrame(v.after, ...v.after_output_size)
    && fullFrame(v.support, reference.source.width, reference.source.height);
}
export function validRect(v: unknown, size: [number, number]): v is NeckRect {
  return Array.isArray(v) && v.length === 4 && v.every(revision) && v[2] >= 1 && v[3] >= 1 && v[2] <= 1024 && v[3] <= 1024
    && v[0] + v[2] <= size[0] && v[1] + v[3] <= size[1];
}
export function validCrop(v: unknown, request: NeckCropRequest, owner: NeckReference | NeckPreview): v is NeckCrop {
  const idKey = request.plane === 'source' ? 'reference_id' : 'preview_id';
  const ownerId = request.plane === 'source' && owner.kind === 'reference' ? owner.reference_id
    : request.plane !== 'source' && owner.kind === 'preview' ? owner.preview_id : null;
  const requestId = 'reference_id' in request ? request.reference_id : request.preview_id;
  const size: [number, number] = request.plane === 'source' ? [owner.source.width, owner.source.height]
    : owner.kind === 'preview' ? owner.before_output_size : [0, 0];
  return object(v) && keys(v, ['kind', 'family', 'operation_id', idKey, 'plane', 'rect', 'domain', 'source', 'source_proof',
    'input_sha256', 'repair_sha256', 'image']) && family(v) && sourceBinding(v) && v.kind === 'crop' && ownerId !== null
    && ownerId === requestId && v[idKey] === requestId && v.plane === request.plane
    && v.domain === (request.plane === 'source' ? 'source' : 'rendered_result') && validRect(request.rect, size)
    && canonical(v.rect) === canonical(request.rect) && sameSourceBinding(v, owner) && imageMetadata(v.image, 1024)
    && v.image.width === request.rect[2] && v.image.height === request.rect[3];
}
export function inspectionAck(before: NeckCrop | null, after: NeckCrop | null, preview: NeckPreview): NeckInspectionAck | null {
  if (!before || !after || before.plane !== 'before' || after.plane !== 'after' || canonical(before.rect) !== canonical(after.rect)
    || !validCrop(before, {preview_id: preview.preview_id, plane: 'before', rect: before.rect}, preview)
    || !validCrop(after, {preview_id: preview.preview_id, plane: 'after', rect: after.rect}, preview)) return null;
  return {rect: [...before.rect], before_sha256: before.image.sha256, after_sha256: after.image.sha256};
}
export function confirmation(preview: NeckPreview, inspection: NeckInspectionAck): NeckConfirm {
  return {preview_id: preview.preview_id, reviewed: true, before_sha256: preview.before.sha256,
    after_sha256: preview.after.sha256, support_sha256: preview.support.sha256, inspection: structuredClone(inspection)};
}
/** This is necessary, not sufficient: the canonical people owner must ALSO
 * validate/publish doc_state and fence an unknown or stale write receipt. */
export function validWritePayload(v: unknown, action: 'neck_wrinkle_confirm' | 'neck_wrinkle_detach', amount: number | undefined): boolean {
  return object(v) && keys(v, ['kind', 'family', 'operation_id', 'attached', 'amount']) && family(v)
    && v.kind === (action === 'neck_wrinkle_confirm' ? 'confirmed' : 'detached')
    && v.attached === (action === 'neck_wrinkle_confirm') && amount !== undefined && finite(amount, 0, 1)
    && v.amount === amount && (action !== 'neck_wrinkle_detach' || amount === 0);
}
export function validReport(v: unknown, face: FaceRef, source?: NeckSource): v is NeckReport {
  return object(v) && Object.keys(v).every(key => ['family', 'operation_id', 'attached', 'face_ref', 'source', 'needs_review', 'reason'].includes(key))
    && family(v) && typeof v.attached === 'boolean' && validFace(v.face_ref) && sameFace(v.face_ref, face)
    && validSource(v.source) && v.source.sha256 === face.asset_sha256 && (!source || canonical(v.source) === canonical(source))
    && (v.needs_review === undefined || typeof v.needs_review === 'boolean')
    && (v.reason === undefined || v.reason === null || typeof v.reason === 'string');
}
/** Canonical-owner post-state guard. Run even when the panel is closed/unmounted.
 * The owner retains the frozen preview and captured pre-write view; none of this
 * state is reconstructed from a newly selected face or a later display image. */
export function validWriteResult(command: NeckCommand, result: NeckResult, before: PeopleView, preview?: NeckPreview,
  inspected?: NeckInspectionAck): boolean {
  const action = command.action, face = command.target.face_ref;
  if (!face || !validFace(face) || command.target.scope !== 'face' || command.target.target_id !== face.face_instance_id
    || !['neck_wrinkle_confirm', 'neck_wrinkle_detach', 'patch'].includes(action)
    || result.protocol !== 1 || result.success !== true || result.outcome_unknown !== false || result.payload_released === true
    || result.request_id !== command.request_id || result.action !== action || result.document_id !== command.document_id
    || result.batch_id != null || command.document_id !== before.binding.document_id || command.document_epoch !== before.binding.document_epoch
    || command.document_revision !== before.binding.document_revision || command.state_revision !== before.revision
    || command.association_revision !== before.association_revision || !sameFace(before.editing_target?.face_ref, face)) return false;
  const amount = action === 'neck_wrinkle_confirm' ? preview?.amount : 0;
  if (amount === undefined || !finite(amount, 0, 1)) return false;
  if (action === 'neck_wrinkle_confirm') {
    if (!preview || !sameFace(preview.face_ref, face) || command.payload.preview_id !== preview.preview_id
      || !keys(command.payload, ['preview_id', 'reviewed', 'before_sha256', 'after_sha256', 'support_sha256', 'inspection'])
      || command.payload.reviewed !== true || command.payload.before_sha256 !== preview.before.sha256
      || command.payload.after_sha256 !== preview.after.sha256 || command.payload.support_sha256 !== preview.support.sha256
      || !inspected || !validRect(inspected.rect, preview.before_output_size) || !hash(inspected.before_sha256) || !hash(inspected.after_sha256)
      || canonical(command.payload.inspection) !== canonical(inspected)
      || !validWritePayload(result.payload, action, amount)) return false;
  } else if (action === 'neck_wrinkle_detach') {
    if (!keys(command.payload, []) || !validWritePayload(result.payload, action, 0)) return false;
  } else if (canonical(command.payload) !== canonical({patches: [{operation_id: NECK_WRINKLE_OPERATION,
    parameter_path: '/amount', unset: false, value: 0}]})) return false;
  const next = result.doc_state?.people as (PeopleView & {neck_wrinkle?: NeckReport | null}) | undefined;
  if (!next || !object(next) || !object(next.binding) || !object(next.editing_target) || !Array.isArray(next.faces)
    || !next.faces.every(row => object(row) && validFace(row.face_ref)) || !object(next.editing_overrides)
    || !object(next.resolved) || !object(next.resolved.operations) || !Array.isArray(next.resolved.conflicts)
    || !next.resolved.conflicts.every(row => object(row) && typeof row.operation_id === 'string')
    || next.binding.document_id !== command.document_id || next.binding.document_epoch !== command.document_epoch
    || next.binding.asset_sha256 !== face.asset_sha256 || next.binding.document_revision < command.document_revision
    || next.revision < command.state_revision || next.association_revision !== command.association_revision
    || !targetReady(next) || !sameFace(next.editing_target?.face_ref, face) || !next.resolved
    || !sameFace(next.resolved.face_ref, face) || next.resolved.state_revision !== next.revision
    || next.resolved.association_revision !== next.association_revision
    || next.resolved.conflicts.some(conflict => conflict.operation_id === NECK_WRINKLE_OPERATION)) return false;
  const resolved = next.resolved.operations[NECK_WRINKLE_OPERATION]?.['/amount'];
  if (!resolved || resolved.scope !== 'face' || resolved.target_id !== face.face_instance_id || resolved.value !== amount
    || next.editing_overrides[NECK_WRINKLE_OPERATION]?.['/amount'] !== amount) return false;
  const withoutNeck = (values: Record<string, unknown>) => Object.fromEntries(Object.entries(values).filter(([key]) => key !== NECK_WRINKLE_OPERATION));
  if (canonical(next.faces) !== canonical(before.faces) || canonical(next.groups) !== canonical(before.groups)
    || canonical(next.persons) !== canonical(before.persons) || canonical(next.links) !== canonical(before.links)
    || canonical(withoutNeck(next.editing_overrides)) !== canonical(withoutNeck(before.editing_overrides))
    || before.resolved && canonical(withoutNeck(next.resolved.operations)) !== canonical(withoutNeck(before.resolved.operations))) return false;
  if (!validReport(next.neck_wrinkle, face, action === 'neck_wrinkle_confirm' ? preview?.source : undefined)) return false;
  if (action === 'neck_wrinkle_confirm' && (!next.neck_wrinkle.attached || next.neck_wrinkle.needs_review !== false)
    || action === 'neck_wrinkle_detach' && next.neck_wrinkle.attached !== false) return false;
  // Neutral amount-only reset preserves the pointer's authoritative attached
  // status even when its evidence is stale; it must not smuggle in a detach.
  const prior = (before as PeopleView & {neck_wrinkle?: NeckReport | null}).neck_wrinkle;
  return action !== 'patch' || !validReport(prior, face) || prior.attached === next.neck_wrinkle.attached;
}
/** Transport identity and current document fences, before accepting any local image. */
export function receiptMatches(receipt: NeckReceipt, command: NeckCommand, view: PeopleView | null): boolean {
  const result = receipt.result;
  if (!view || canonical(receipt.command) !== canonical(command) || result.protocol !== 1 || result.outcome_unknown !== false
    || typeof result.success !== 'boolean' || result.request_id !== command.request_id || result.action !== command.action
    || result.document_id !== command.document_id || command.document_id !== view.binding.document_id
    || command.document_epoch !== view.binding.document_epoch) return false;
  const write = ['neck_wrinkle_confirm', 'neck_wrinkle_detach', 'patch', 'select'].includes(command.action);
  return write ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
    && view.association_revision >= command.association_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision
      && view.association_revision === command.association_revision && sameFace(view.editing_target?.face_ref, command.target.face_ref);
}
