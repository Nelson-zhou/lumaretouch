// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleAssetContext, type FaceRef, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model';
import {digest, documentId, safeRevision, sameFace, validEndpoint, validFaceRef,
  type EffectiveSourceProof, type PeopleEndpointProof} from '../people/transferProof';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneImage, validCollarboneImageMetadata, verifyCollarboneImage,
  type CollarboneImage} from '../collarbone/transferModel';
import type {FaceStyleVisual} from '../faceStyle/model';
import type {SpillImage} from '../spillRemoval/model';

export const OPERATION_ID = 'lnx.skin_reference_match.v1' as const;
export const LIMITS = {faces: 64, targets: 63, edge: 1024} as const;
export type SkinReferenceAction = 'skin_reference_match_catalog' | 'skin_reference_match_preview'
  | 'skin_reference_match_image' | 'skin_reference_match_confirm' | 'skin_reference_match_clear';
export type SkinReferenceReceipt = {command: PeopleAction; result: PeopleResult};
export type SkinReferenceSide = 'before' | 'after';
export type SkinReferenceSource = {sha256: string; width: number; height: number};
export type SkinReferenceFace = {face_ref: FaceRef; box: [number, number, number, number]; enabled: boolean;
  available: boolean; reason: string | null; amount: number};
export type SkinReferenceCurrent = {version: 1; operation_id: typeof OPERATION_ID; bank_sha256: string;
  reference_face_ref: FaceRef | null; target_face_refs: FaceRef[];
  amounts: {face_ref: FaceRef; amount: number; support_sha256: string}[]};
export type SkinReferenceCatalog = {kind: 'skin_reference_match_catalog'; version: 1; operation_id: typeof OPERATION_ID;
  scope: 'current-photo-face-only'; source: SkinReferenceSource; source_proof: EffectiveSourceProof;
  document_id: string; revision: string; source_image: SpillImage; source_review_sha256: string;
  faces: SkinReferenceFace[]; current: SkinReferenceCurrent; body_matching: false; automatic_reference: false;
  skin_reference_match_available: boolean; skin_reference_match_reason: string | null};
export type SkinReferencePreview = {version: 1; reference_face_ref: FaceRef; target_face_refs: FaceRef[];
  amount: number; source_review_sha256: string; ownership_confirmed: true};
export type SkinReferenceReview = {version: 1; token: string; operation_id: typeof OPERATION_ID;
  owner: PeopleEndpointProof; source: SkinReferenceSource; reference_face_ref: FaceRef; target_face_refs: FaceRef[];
  amount: number; before_target_face_refs: FaceRef[]; candidate_state_revision: number; before_bank_sha256: string;
  candidate_bank_sha256: string; support_sha256: Record<string, string>; source_review_sha256: string;
  visual: FaceStyleVisual; review_sha256: string};
export type SkinReferenceAck = {review_sha256: string; before_sha256: string; after_sha256: string};
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const unit = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const positive = (v: unknown): v is number => unit(v) && v > 0;
const reason = (v: unknown): v is string | null => v === null || typeof v === 'string' && v.length <= 2000;
const token = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{32}$/.test(v);
const revision = (v: unknown): v is string => typeof v === 'string' && /^(0|[1-9]\d{0,15})$/.test(v)
  && BigInt(v) <= BigInt(Number.MAX_SAFE_INTEGER);
const size = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2
  && v.every(n => typeof n === 'number' && Number.isSafeInteger(n) && n > 0 && n <= 4294967295);
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (object(v)) return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
  return JSON.stringify(v) ?? 'undefined';
}
export const isSkinReferenceAction = (action: string): action is SkinReferenceAction =>
  ['skin_reference_match_catalog', 'skin_reference_match_preview', 'skin_reference_match_image',
    'skin_reference_match_confirm', 'skin_reference_match_clear'].includes(action);
export const skinReferenceContext = peopleAssetContext;
/** Cursor changes are not ownership changes. Face measurements and every engine fence are. */
export const skinReferenceBinding = (view: PeopleView | null): string => canonical(view
  ? [view.binding, view.revision, view.association_revision, view.faces, view.skin_reference_match] : null);
export function parseAmount(text: string): number | null {
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())) return null;
  const value = Number(text) / 100;
  return positive(value) ? value : null;
}
function refs(v: unknown, allowEmpty = false): v is FaceRef[] {
  return Array.isArray(v) && (allowEmpty || v.length > 0) && v.length <= LIMITS.faces && v.every(validFaceRef)
    && new Set(v.map(ref => ref.face_instance_id)).size === v.length;
}
function validSource(v: unknown): v is SkinReferenceSource {
  return object(v) && keys(v, ['sha256', 'width', 'height']) && digest(v.sha256) && size([v.width, v.height]);
}
function currentFace(ref: FaceRef, view: PeopleView, enabled = true): boolean {
  return ref.asset_sha256 === view.binding.asset_sha256 && view.faces.some(face => sameFace(face.face_ref, ref)
    && (!enabled || face.enabled && face.analysis_status === 'verified'));
}
function compactMatches(image: CollarboneImage, output: [number, number]): boolean {
  const edge = Math.max(...output), scaled = (n: number) => {
    if (edge <= LIMITS.edge) return n;
    const q = Math.floor(n * LIMITS.edge / edge), r = n * LIMITS.edge % edge;
    return Math.max(1, q + (r * 2 > edge || r * 2 === edge && q % 2 === 1 ? 1 : 0));
  };
  return image.width === scaled(output[0]) && image.height === scaled(output[1]);
}
function validVisual(v: unknown): v is FaceStyleVisual {
  if (!object(v) || !keys(v, ['version', 'document_id', 'revision', 'source_proof', 'source_size',
    'before_output_size', 'after_output_size', 'before', 'after', 'before_state_sha256', 'candidate_state_sha256',
    'before_people_sha256', 'candidate_people_sha256']) || v.version !== 1 || !documentId(v.document_id)
    || !revision(v.revision) || !sourceProof(v.source_proof) || !size(v.source_size)
    || !size(v.before_output_size) || !size(v.after_output_size)
    || !validCollarboneImageMetadata(v.before) || !validCollarboneImageMetadata(v.after)
    || !['before_state_sha256', 'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256'].every(k => digest(v[k]))) return false;
  const derived = v.source_proof.creative_source;
  return (!derived || derived.width === v.source_size[0] && derived.height === v.source_size[1])
    && compactMatches(v.before, v.before_output_size) && compactMatches(v.after, v.after_output_size);
}
export function validCatalog(v: unknown, view: PeopleView | null): v is SkinReferenceCatalog {
  if (!view || !object(v) || !keys(v, ['kind', 'version', 'operation_id', 'scope', 'source', 'source_proof',
    'document_id', 'revision', 'source_image', 'source_review_sha256', 'faces', 'current', 'body_matching',
    'automatic_reference', 'skin_reference_match_available', 'skin_reference_match_reason'])
    || v.kind !== 'skin_reference_match_catalog' || v.version !== 1 || v.operation_id !== OPERATION_ID
    || v.scope !== 'current-photo-face-only' || v.body_matching !== false || v.automatic_reference !== false
    || !validSource(v.source) || v.source.sha256 !== view.binding.asset_sha256 || !sourceProof(v.source_proof)
    || v.source_proof.asset_sha256 !== v.source.sha256 || v.document_id !== view.binding.document_id
    || v.revision !== String(view.binding.document_revision) || !validCollarboneImage(v.source_image)
    || !digest(v.source_review_sha256) || typeof v.skin_reference_match_available !== 'boolean'
    || !reason(v.skin_reference_match_reason) || !Array.isArray(v.faces) || v.faces.length > LIMITS.faces
    || v.faces.length !== view.faces.length) return false;
  const source = v.source, derived = v.source_proof.creative_source;
  if (!compactMatches(v.source_image, [source.width, source.height])
    || derived && (derived.width !== source.width || derived.height !== source.height)
    || (v.skin_reference_match_available ? v.skin_reference_match_reason !== null : !v.skin_reference_match_reason)) return false;
  const seen = new Set<string>();
  if (!v.faces.every(row => {
    if (!object(row) || !keys(row, ['face_ref', 'box', 'enabled', 'available', 'reason', 'amount'])
      || !validFaceRef(row.face_ref) || !currentFace(row.face_ref, view, false) || seen.has(row.face_ref.face_instance_id)
      || typeof row.enabled !== 'boolean' || typeof row.available !== 'boolean' || !reason(row.reason) || !unit(row.amount)
      || (row.available ? row.reason !== null : !row.reason)
      || !Array.isArray(row.box) || row.box.length !== 4 || !row.box.every(unit)
      || row.box[0] >= row.box[2] || row.box[1] >= row.box[3]) return false;
    const local = view.faces.find(face => sameFace(face.face_ref, row.face_ref as FaceRef))!;
    if (row.enabled !== local.enabled || canonical(row.box) !== canonical(local.box)
      || row.available && (!local.enabled || local.analysis_status !== 'verified')) return false;
    seen.add(row.face_ref.face_instance_id); return true;
  })) return false;
  if (!validCurrent(v.current, view)) return false;
  return v.faces.every(row => {
    const amount = (v.current as SkinReferenceCurrent).amounts.find(item => sameFace(item.face_ref, row.face_ref));
    // Disabled faces can keep dormant leaves, but active rows must report their exact amount.
    return !amount || amount.amount === row.amount;
  });
}
export function validCurrent(current: unknown, view: PeopleView): current is SkinReferenceCurrent {
  if (!object(current) || !keys(current, ['version', 'operation_id', 'bank_sha256', 'reference_face_ref', 'target_face_refs', 'amounts'])
    || current.version !== 1 || current.operation_id !== OPERATION_ID || !digest(current.bank_sha256)
    || !refs(current.target_face_refs, true) || !Array.isArray(current.amounts)
    || current.target_face_refs.length > LIMITS.targets
    || current.amounts.length !== current.target_face_refs.length) return false;
  if (current.reference_face_ref === null ? current.target_face_refs.length !== 0
    : !validFaceRef(current.reference_face_ref) || current.target_face_refs.length === 0
      || !currentFace(current.reference_face_ref, view, false)) return false;
  const targets = current.target_face_refs, reference = current.reference_face_ref as FaceRef | null;
  if (!targets.every(ref => currentFace(ref, view, false) && (!reference || !sameFace(ref, reference)))) return false;
  const amounts = new Set<string>();
  return current.amounts.every(row => {
    if (!object(row) || !keys(row, ['face_ref', 'amount', 'support_sha256']) || !validFaceRef(row.face_ref)
      || !positive(row.amount) || !digest(row.support_sha256) || amounts.has(row.face_ref.face_instance_id)
      || !targets.some(ref => sameFace(ref, row.face_ref as FaceRef))) return false;
    amounts.add(row.face_ref.face_instance_id); return true;
  });
}
/** Byte verification is separate from browser decoding and the user's explicit ownership check. */
export async function catalogImage(catalog: SkinReferenceCatalog): Promise<SpillImage | null> {
  return await verifyCollarboneImage(catalog.source_image) ? catalog.source_image : null;
}
export function validPreview(v: unknown): v is SkinReferencePreview {
  return object(v) && keys(v, ['version', 'reference_face_ref', 'target_face_refs', 'amount', 'source_review_sha256', 'ownership_confirmed'])
    && v.version === 1 && validFaceRef(v.reference_face_ref) && refs(v.target_face_refs)
    && v.target_face_refs.length <= LIMITS.targets && positive(v.amount)
    && digest(v.source_review_sha256) && v.ownership_confirmed === true
    && v.target_face_refs.every(ref => ref.asset_sha256 === (v.reference_face_ref as FaceRef).asset_sha256
      && ref.face_instance_id !== (v.reference_face_ref as FaceRef).face_instance_id);
}
export function validReview(v: unknown, view: PeopleView | null, preview: SkinReferencePreview): v is SkinReferenceReview {
  if (!view || !validPreview(preview) || !object(v) || !keys(v, ['version', 'token', 'operation_id', 'owner', 'source',
    'reference_face_ref', 'target_face_refs', 'amount', 'before_target_face_refs', 'candidate_state_revision',
    'before_bank_sha256', 'candidate_bank_sha256', 'support_sha256', 'source_review_sha256', 'visual', 'review_sha256'])
    || v.version !== 1 || !token(v.token) || v.operation_id !== OPERATION_ID || !validEndpoint(v.owner)
    || !validSource(v.source) || !validFaceRef(v.reference_face_ref) || !refs(v.target_face_refs)
    || !refs(v.before_target_face_refs, true) || !positive(v.amount) || !safeRevision(v.candidate_state_revision)
    || v.candidate_state_revision !== v.owner.state_revision + 1 || !digest(v.before_bank_sha256) || !digest(v.candidate_bank_sha256)
    || !digest(v.review_sha256) || v.source_review_sha256 !== preview.source_review_sha256
    || !sameFace(v.reference_face_ref, preview.reference_face_ref) || canonical(v.target_face_refs) !== canonical(preview.target_face_refs)
    || v.amount !== preview.amount || !currentFace(v.reference_face_ref, view) || !v.target_face_refs.every(ref => currentFace(ref, view))
    || !v.before_target_face_refs.every(ref => currentFace(ref, view, false)) || !validVisual(v.visual)
    || !object(v.support_sha256) || !keys(v.support_sha256, v.target_face_refs.map(ref => ref.face_instance_id))
    || !Object.values(v.support_sha256).every(digest)) return false;
  const owner = v.owner, visual = v.visual, source = v.source;
  return owner.document.document_id === view.binding.document_id && owner.document.epoch === view.binding.document_epoch
    && owner.document.revision === view.binding.document_revision && owner.state_revision === view.revision
    && owner.association_revision === view.association_revision && owner.source_proof.asset_sha256 === view.binding.asset_sha256
    && source.sha256 === view.binding.asset_sha256 && visual.document_id === owner.document.document_id
    && visual.revision === String(owner.document.revision) && sameSpillSourceProof(visual.source_proof, owner.source_proof)
    && visual.source_size[0] === source.width && visual.source_size[1] === source.height;
}
export const ack = (review: SkinReferenceReview): SkinReferenceAck => ({review_sha256: review.review_sha256,
  before_sha256: review.visual.before.sha256, after_sha256: review.visual.after.sha256});
export const sameAck = (value: unknown, expected: SkinReferenceAck): boolean => object(value)
  && keys(value, ['review_sha256', 'before_sha256', 'after_sha256']) && canonical(value) === canonical(expected);
export const reviewKey = (review: SkinReferenceReview): string => canonical([review.token, review.review_sha256, review.visual]);
export function echoMatches(command: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _requestId, ...captured} = command;
  return object(result.skin_reference_match_request) && canonical(result.skin_reference_match_request) === canonical(captured);
}
export function receiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!view || !isSkinReferenceAction(command.action) || !echoMatches(command, result) || result.protocol !== 1
    || !result.success || result.outcome_unknown !== false || result.request_id !== command.request_id
    || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'all_people' || command.target.target_id !== view.binding.asset_sha256 || command.target.face_ref !== null
    || command.association_revision !== view.association_revision) return false;
  return command.action === 'skin_reference_match_confirm' || command.action === 'skin_reference_match_clear'
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision;
}
export function validReleasedReceipt(command: PeopleAction, result: PeopleResult): boolean {
  return isSkinReferenceAction(command.action) && !['skin_reference_match_confirm', 'skin_reference_match_clear'].includes(command.action)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.payload_released === true
    && result.payload === undefined && result.request_id === command.request_id && result.action === command.action
    && result.document_id === command.document_id && echoMatches(command, result);
}
export function validImageReceipt(payload: unknown, command: PeopleAction): boolean {
  if (command.action !== 'skin_reference_match_image' || !object(payload)
    || !keys(payload, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image'])
    || payload.kind !== command.action || !keys(command.payload, ['token', 'side', 'sha256', 'review_sha256'])
    || !token(payload.token) || !['before', 'after'].includes(String(payload.side))
    || !digest(payload.sha256) || !digest(payload.review_sha256) || !validCollarboneImage(payload.image)) return false;
  return ['token', 'side', 'sha256', 'review_sha256'].every(k => payload[k] === command.payload[k])
    && payload.image.sha256 === payload.sha256;
}
export async function reviewImage(value: unknown, review: SkinReferenceReview, side: SkinReferenceSide): Promise<SpillImage | null> {
  if (!object(value) || !keys(value, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image'])
    || value.kind !== 'skin_reference_match_image' || value.token !== review.token || value.side !== side
    || value.review_sha256 !== review.review_sha256 || value.sha256 !== review.visual[side].sha256
    || !validCollarboneImage(value.image)) return null;
  const image = value.image, expected = review.visual[side];
  return image.sha256 === expected.sha256 && image.width === expected.width && image.height === expected.height
    && await verifyCollarboneImage(image) ? image : null;
}
/** Validate the proof before refresh can discard the captured pre-edit owner. */
export function validConfirmation(review: SkinReferenceReview, result: PeopleResult): boolean {
  const p = result.payload, next = result.doc_state?.people, owner = review.owner;
  return object(p) && keys(p, ['kind', 'token', 'review_sha256', 'ack', 'reference_face_ref', 'target_face_refs',
    'amount', 'candidate_state_revision', 'support_sha256', 'candidate_bank_sha256'])
    && p.kind === 'skin_reference_match_confirm' && p.token === review.token && p.review_sha256 === review.review_sha256
    && sameAck(p.ack, ack(review)) && canonical(p.reference_face_ref) === canonical(review.reference_face_ref)
    && canonical(p.target_face_refs) === canonical(review.target_face_refs) && p.amount === review.amount
    && p.candidate_state_revision === review.candidate_state_revision && p.candidate_bank_sha256 === review.candidate_bank_sha256
    && canonical(p.support_sha256) === canonical(review.support_sha256)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.action === p.kind
    && result.document_id === owner.document.document_id && !!next && next.binding.document_id === owner.document.document_id
    && next.binding.document_epoch === owner.document.epoch && next.binding.asset_sha256 === owner.source_proof.asset_sha256
    && safeRevision(next.binding.document_revision) && next.binding.document_revision === owner.document.revision + 1
    && next.revision === review.candidate_state_revision && next.association_revision === owner.association_revision
    && validCurrent(next.skin_reference_match, next) && next.skin_reference_match.bank_sha256 === review.candidate_bank_sha256
    && canonical(next.skin_reference_match.reference_face_ref) === canonical(review.reference_face_ref)
    && next.skin_reference_match.target_face_refs.length === review.target_face_refs.length
    && next.skin_reference_match.target_face_refs.every(ref => review.target_face_refs.some(target => sameFace(ref, target)))
    && next.skin_reference_match.amounts.every(row => row.amount === review.amount
      && row.support_sha256 === review.support_sha256[row.face_ref.face_instance_id]);
}
export function validClear(command: PeopleAction, result: PeopleResult): boolean {
  const p = result.payload, next = result.doc_state?.people;
  return command.action === 'skin_reference_match_clear' && keys(command.payload, []) && echoMatches(command, result)
    && object(p) && keys(p, ['kind', 'candidate_state_revision', 'cleared_face_refs']) && p.kind === command.action
    && safeRevision(p.candidate_state_revision) && p.candidate_state_revision === command.state_revision + 1
    && refs(p.cleared_face_refs) && p.cleared_face_refs.every(ref => ref.asset_sha256 === command.target.target_id)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.request_id === command.request_id
    && result.action === command.action && result.document_id === command.document_id && !!next
    && next.binding.document_id === command.document_id && next.binding.document_epoch === command.document_epoch
    && next.binding.asset_sha256 === command.target.target_id && safeRevision(next.binding.document_revision)
    && next.binding.document_revision === command.document_revision + 1
    && next.revision === p.candidate_state_revision && next.association_revision === command.association_revision
    && validCurrent(next.skin_reference_match, next) && next.skin_reference_match.reference_face_ref === null
    && next.skin_reference_match.target_face_refs.length === 0 && next.skin_reference_match.amounts.length === 0
    && p.cleared_face_refs.every(ref => currentFace(ref, next, false));
}
