// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleAssetContext, type FaceRef, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model';
import {digest, documentId, safeRevision, sameFace, validEndpoint, validFaceRef,
  type EffectiveSourceProof, type PeopleEndpointProof} from '../people/transferProof';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
// Only immutable PNG metadata/byte verification is shared, never another operation's review or consent.
import {validCollarboneImage, validCollarboneImageMetadata, verifyCollarboneImage} from '../collarbone/transferModel';
import type {SpillImage} from '../spillRemoval/model';
import type {BodyRef, Source} from '../legShape/model';
import type {SourceImage} from '../legShape/sourcePreview';
import type {SkinBodyMask} from '../skinColour/bodyReviewModel';

export const OPERATION_ID = 'lnx.skin_reference_body_match.v1' as const;
export const LIMITS = {faces: 64, targets: 64, edge: 1024, requestBytes: 192 * 1024} as const;
export type SkinReferenceBodyAction = 'skin_reference_body_catalog' | 'skin_reference_body_preview'
  | 'skin_reference_body_image' | 'skin_reference_body_confirm' | 'skin_reference_body_clear';
export type SkinReferenceBodyReceipt = {command: PeopleAction; result: PeopleResult};
export type SkinReferenceBodySide = 'before' | 'after';
export type SkinReferenceBodySource = {sha256: string; width: number; height: number};
export type SkinReferenceBodyFace = {face_ref: FaceRef; box: [number, number, number, number]; enabled: boolean;
  available: boolean; reason: string | null; amount: number};
export type SkinReferenceBodyTarget = {face_ref: FaceRef; body_ref: BodyRef; points_sha256: string; source: Source;
  association: {person_id: string; body_ref: BodyRef; people_association_revision: number; confirmation_revision: number};
  /** This is the measured owner's FACE box, not estimated body geometry. */
  box: [number, number, number, number]; amount: number};
export type SkinReferenceBodyCurrent = {version: 1; operation_id: typeof OPERATION_ID; bank_sha256: string;
  reference_face_ref: FaceRef | null; target_face_refs: FaceRef[];
  amounts: {face_ref: FaceRef; amount: number; support_sha256: string}[]};
export type SkinReferenceBodyCatalog = {kind: 'skin_reference_body_catalog'; version: 1; operation_id: typeof OPERATION_ID;
  scope: 'current-photo-body-only'; source: SkinReferenceBodySource; source_proof: EffectiveSourceProof;
  document_id: string; revision: string; source_image: SpillImage; source_review_sha256: string;
  faces: SkinReferenceBodyFace[]; targets: SkinReferenceBodyTarget[]; current: SkinReferenceBodyCurrent;
  body_matching: true; automatic_reference: false; skin_reference_body_available: boolean; skin_reference_body_reason: string | null};
/** Independent operation consent. The generic brush editor cannot produce this by itself. */
export type SkinReferenceBodyConsent = {operation_id: typeof OPERATION_ID; body_ref: BodyRef; points_sha256: string;
  recipe: SkinBodyMask; visible: true; unoccluded: true; ownership_confirmed: true; reference_unchanged: true};
export type SkinReferenceBodyPreview = {version: 1; reference_face_ref: FaceRef; target_face_ref: FaceRef;
  review: SkinReferenceBodyConsent; amount: number; source_review_sha256: string; ownership_confirmed: true};
export type SkinReferenceBodyVisual = {version: 1; document_id: string; revision: string; source_proof: EffectiveSourceProof;
  source_size: [number, number]; before_output_size: [number, number]; after_output_size: [number, number];
  before: Omit<SpillImage, 'base64'>; after: Omit<SpillImage, 'base64'>; before_state_sha256: string;
  candidate_state_sha256: string; before_people_sha256: string; candidate_people_sha256: string};
export type SkinReferenceBodyReview = {version: 1; token: string; operation_id: typeof OPERATION_ID;
  owner: PeopleEndpointProof; source: SkinReferenceBodySource; reference_face_ref: FaceRef; target_face_ref: FaceRef;
  body_ref: BodyRef; body_review: SkinReferenceBodyConsent; amount: number; source_review_sha256: string;
  body_bank_sha256: string; before_current: SkinReferenceBodyCurrent; candidate_current: SkinReferenceBodyCurrent;
  candidate_state_revision: number; before_bank_sha256: string; candidate_bank_sha256: string;
  support_sha256: string; visual: SkinReferenceBodyVisual; review_sha256: string};
export type SkinReferenceBodyAck = {review_sha256: string; before_sha256: string; after_sha256: string};

export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export const exact = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const unit = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const positive = (v: unknown): v is number => unit(v) && v > 0;
const reason = (v: unknown): v is string | null => v === null || typeof v === 'string' && v.length <= 2000;
const textId = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 128;
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
export const isSkinReferenceBodyAction = (action: string): action is SkinReferenceBodyAction =>
  ['skin_reference_body_catalog', 'skin_reference_body_preview', 'skin_reference_body_image',
    'skin_reference_body_confirm', 'skin_reference_body_clear'].includes(action);
export const skinReferenceBodyContext = peopleAssetContext;
/** Editing cursor is not ownership. Source, measured faces, confirmed links and every engine fence are. */
export const skinReferenceBodyBinding = (view: PeopleView | null): string => canonical(view
  ? [view.binding, view.revision, view.association_revision, view.faces, view.links, view.persons, view.skin_reference_body_match] : null);
export function parseAmount(text: string): number | null {
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text.trim())) return null;
  const value = Number(text) / 100;
  return positive(value) ? value : null;
}
export const emptyMask = (): SkinBodyMask => ({version: 1, domain: 'source-normalized', objects: []});
export const targetKey = (target: Pick<SkinReferenceBodyTarget, 'face_ref' | 'body_ref'>): string =>
  canonical([target.face_ref, target.body_ref]);
export function validBodyRef(v: unknown): v is BodyRef {
  return object(v) && exact(v, ['asset_sha256', 'body_instance_id', 'analysis_revision'])
    && digest(v.asset_sha256) && textId(v.body_instance_id) && safeRevision(v.analysis_revision);
}
function refs(v: unknown, allowEmpty = false): v is FaceRef[] {
  return Array.isArray(v) && (allowEmpty || v.length > 0) && v.length <= LIMITS.faces && v.every(validFaceRef)
    && new Set(v.map(ref => ref.face_instance_id)).size === v.length;
}
function validSource(v: unknown): v is SkinReferenceBodySource {
  return object(v) && exact(v, ['sha256', 'width', 'height']) && digest(v.sha256) && size([v.width, v.height]);
}
function currentFace(ref: FaceRef, view: PeopleView, enabled = true): boolean {
  return ref.asset_sha256 === view.binding.asset_sha256 && view.faces.some(face => sameFace(face.face_ref, ref)
    && (!enabled || face.enabled && face.analysis_status === 'verified'));
}
function compactMatches(image: Omit<SpillImage, 'base64'>, output: [number, number]): boolean {
  const edge = Math.max(...output), scaled = (n: number) => {
    if (edge <= LIMITS.edge) return n;
    const q = Math.floor(n * LIMITS.edge / edge), r = n * LIMITS.edge % edge;
    return Math.max(1, q + (r * 2 > edge || r * 2 === edge && q % 2 === 1 ? 1 : 0));
  };
  return image.width === scaled(output[0]) && image.height === scaled(output[1]);
}
function validVisual(v: unknown): v is SkinReferenceBodyVisual {
  if (!object(v) || !exact(v, ['version', 'document_id', 'revision', 'source_proof', 'source_size',
    'before_output_size', 'after_output_size', 'before', 'after', 'before_state_sha256', 'candidate_state_sha256',
    'before_people_sha256', 'candidate_people_sha256']) || v.version !== 1 || !documentId(v.document_id)
    || !revision(v.revision) || !sourceProof(v.source_proof) || !size(v.source_size)
    || !size(v.before_output_size) || !size(v.after_output_size)
    || !validCollarboneImageMetadata(v.before) || !validCollarboneImageMetadata(v.after)
    || !['before_state_sha256', 'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256'].every(k => digest(v[k]))) return false;
  const derived = v.source_proof.creative_source;
  return (!derived || derived.width === v.source_size[0] && derived.height === v.source_size[1])
    && canonical(v.before_output_size) === canonical(v.after_output_size)
    && compactMatches(v.before, v.before_output_size) && compactMatches(v.after, v.after_output_size);
}
export function validCurrent(current: unknown, view: PeopleView): current is SkinReferenceBodyCurrent {
  if (!object(current) || !exact(current, ['version', 'operation_id', 'bank_sha256', 'reference_face_ref', 'target_face_refs', 'amounts'])
    || current.version !== 1 || current.operation_id !== OPERATION_ID || !digest(current.bank_sha256)
    || !refs(current.target_face_refs, true) || !Array.isArray(current.amounts)
    || current.amounts.length !== current.target_face_refs.length) return false;
  if (current.reference_face_ref === null ? current.target_face_refs.length !== 0
    : !validFaceRef(current.reference_face_ref) || !currentFace(current.reference_face_ref, view, false)) return false;
  const targets = current.target_face_refs;
  // A body's owner MAY be the donor. No face operation is enabled or copied.
  if (!targets.every(ref => currentFace(ref, view, false))) return false;
  const seen = new Set<string>();
  return current.amounts.every(row => {
    if (!object(row) || !exact(row, ['face_ref', 'amount', 'support_sha256']) || !validFaceRef(row.face_ref)
      || !positive(row.amount) || !digest(row.support_sha256) || seen.has(row.face_ref.face_instance_id)
      || !targets.some(ref => sameFace(ref, row.face_ref as FaceRef))) return false;
    seen.add(row.face_ref.face_instance_id); return true;
  });
}
export function validCatalog(v: unknown, view: PeopleView | null): v is SkinReferenceBodyCatalog {
  if (!view || !object(v) || !exact(v, ['kind', 'version', 'operation_id', 'scope', 'source', 'source_proof',
    'document_id', 'revision', 'source_image', 'source_review_sha256', 'faces', 'targets', 'current', 'body_matching',
    'automatic_reference', 'skin_reference_body_available', 'skin_reference_body_reason'])
    || v.kind !== 'skin_reference_body_catalog' || v.version !== 1 || v.operation_id !== OPERATION_ID
    || v.scope !== 'current-photo-body-only' || v.body_matching !== true || v.automatic_reference !== false
    || !validSource(v.source) || v.source.sha256 !== view.binding.asset_sha256 || !sourceProof(v.source_proof)
    || v.source_proof.asset_sha256 !== v.source.sha256 || v.document_id !== view.binding.document_id
    || v.revision !== String(view.binding.document_revision) || !validCollarboneImage(v.source_image)
    || !digest(v.source_review_sha256) || typeof v.skin_reference_body_available !== 'boolean'
    || !reason(v.skin_reference_body_reason) || !Array.isArray(v.faces) || v.faces.length > LIMITS.faces
    || v.faces.length !== view.faces.length || !Array.isArray(v.targets) || v.targets.length > LIMITS.targets
    || !validCurrent(v.current, view)) return false;
  const source = v.source, derived = v.source_proof.creative_source;
  if (!compactMatches(v.source_image, [source.width, source.height])
    || derived && (derived.width !== source.width || derived.height !== source.height)
    || (v.skin_reference_body_available ? v.skin_reference_body_reason !== null : !v.skin_reference_body_reason)) return false;
  const seen = new Set<string>();
  if (!v.faces.every(row => {
    if (!object(row) || !exact(row, ['face_ref', 'box', 'enabled', 'available', 'reason', 'amount'])
      || !validFaceRef(row.face_ref) || !currentFace(row.face_ref, view, false) || seen.has(row.face_ref.face_instance_id)
      || typeof row.enabled !== 'boolean' || typeof row.available !== 'boolean' || !reason(row.reason) || !unit(row.amount)
      || (row.available ? row.reason !== null : !row.reason) || !Array.isArray(row.box) || row.box.length !== 4
      || !row.box.every(unit) || row.box[0] >= row.box[2] || row.box[1] >= row.box[3]) return false;
    const local = view.faces.find(face => sameFace(face.face_ref, row.face_ref as FaceRef))!;
    if (row.enabled !== local.enabled || canonical(row.box) !== canonical(local.box)
      || row.available && (!local.enabled || local.analysis_status !== 'verified')) return false;
    const saved = (v.current as SkinReferenceBodyCurrent).amounts.find(item => sameFace(item.face_ref, local.face_ref));
    if (saved && saved.amount !== row.amount) return false;
    seen.add(row.face_ref.face_instance_id); return true;
  })) return false;
  const owners = new Set<string>(), bodies = new Set<string>();
  return v.targets.every(row => {
    if (!object(row) || !exact(row, ['face_ref', 'body_ref', 'points_sha256', 'source', 'association', 'box', 'amount'])
      || !validFaceRef(row.face_ref) || !currentFace(row.face_ref, view) || !validBodyRef(row.body_ref)
      || row.body_ref.asset_sha256 !== source.sha256 || !digest(row.points_sha256) || !unit(row.amount)
      || !object(row.source) || canonical(row.source) !== canonical({...source, orientation: 'exif_normalized_once'})
      || !object(row.association) || !exact(row.association, ['person_id', 'body_ref', 'people_association_revision', 'confirmation_revision'])
      || !textId(row.association.person_id) || canonical(row.association.body_ref) !== canonical(row.body_ref)
      || row.association.people_association_revision !== view.association_revision || !safeRevision(row.association.confirmation_revision)
      || owners.has(row.face_ref.face_instance_id) || bodies.has(row.body_ref.body_instance_id)) return false;
    const face = (v.faces as SkinReferenceBodyFace[]).find(item => sameFace(item.face_ref, row.face_ref as FaceRef));
    const association = row.association as SkinReferenceBodyTarget['association'], ref = row.face_ref;
    // Donor face-skin availability is NOT target-body eligibility. The target catalog carries that authority.
    if (!face?.enabled || canonical(row.box) !== canonical(face.box) || row.amount !== face.amount
      || !Object.hasOwn(view.persons, association.person_id)
      || !view.links.some(link => link.face_instance_id === ref.face_instance_id && link.person_id === association.person_id
        && link.state === 'confirmed' && safeRevision(link.confirmation_revision))) return false;
    owners.add(ref.face_instance_id); bodies.add(row.body_ref.body_instance_id); return true;
  });
}
export async function catalogImage(catalog: SkinReferenceBodyCatalog): Promise<SpillImage | null> {
  return await verifyCollarboneImage(catalog.source_image) ? catalog.source_image : null;
}
/** Called only after catalogImage passes. This PNG covers the full immutable source, not an edited canvas. */
export function sourceEditorImage(catalog: SkinReferenceBodyCatalog): SourceImage {
  const {source, source_image: image} = catalog;
  return {url: `data:image/png;base64,${image.base64}`, source: {...source, orientation: 'exif_normalized_once'},
    decodedWidth: source.width, decodedHeight: source.height, displayWidth: image.width, displayHeight: image.height,
    mapping: 'normalized_full_frame'};
}
export function validMask(v: unknown): v is SkinBodyMask {
  if (!object(v) || !exact(v, ['version', 'domain', 'objects']) || v.version !== 1 || v.domain !== 'source-normalized'
    || !Array.isArray(v.objects) || v.objects.length < 1 || v.objects.length > 64) return false;
  const ids = new Set<string>(); let points = 0, hasAdd = false;
  const point = (value: unknown) => Array.isArray(value) && value.length === 2 && value.every(unit);
  if (!v.objects.every(row => {
    if (!object(row) || !exact(row, ['id', 'name', 'enabled', 'operation', 'opacity', 'feather', 'kind', 'points', 'axes'])
      || typeof row.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(row.id) || ids.has(row.id)
      || typeof row.name !== 'string' || !row.name.trim() || Array.from(row.name).length > 80 || /[\u0000-\u001f]/.test(row.name)
      || typeof row.enabled !== 'boolean' || !['add', 'subtract'].includes(String(row.operation))
      || !unit(row.opacity) || typeof row.feather !== 'number' || !Number.isFinite(row.feather) || row.feather < 0 || row.feather > 100
      || row.kind !== 'brush' || !Array.isArray(row.points) || row.points.length < 1 || row.points.length > 1024
      || !row.points.every(point) || !Array.isArray(row.axes) || row.axes.length !== 2
      || !row.axes.every(axis => Array.isArray(axis) && axis.length === 2
        && axis.every(n => typeof n === 'number' && Number.isFinite(n) && Math.abs(n) <= 4))) return false;
    const axes = row.axes as [[number, number], [number, number]];
    if (Math.abs(axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0]) < 1e-12) return false;
    points += row.points.length; ids.add(row.id); hasAdd ||= row.enabled && row.operation === 'add' && row.opacity > 0;
    return true;
  })) return false;
  return points <= 4096 && hasAdd;
}
export function validConsent(v: unknown): v is SkinReferenceBodyConsent {
  return object(v) && exact(v, ['operation_id', 'body_ref', 'points_sha256', 'recipe', 'visible', 'unoccluded', 'ownership_confirmed', 'reference_unchanged'])
    && v.operation_id === OPERATION_ID && validBodyRef(v.body_ref) && digest(v.points_sha256) && validMask(v.recipe)
    && v.visible === true && v.unoccluded === true && v.ownership_confirmed === true && v.reference_unchanged === true;
}
export function validPreview(v: unknown): v is SkinReferenceBodyPreview {
  return object(v) && exact(v, ['version', 'reference_face_ref', 'target_face_ref', 'review', 'amount', 'source_review_sha256', 'ownership_confirmed'])
    && v.version === 1 && validFaceRef(v.reference_face_ref) && validFaceRef(v.target_face_ref) && validConsent(v.review)
    && positive(v.amount) && digest(v.source_review_sha256) && v.ownership_confirmed === true
    && v.reference_face_ref.asset_sha256 === v.target_face_ref.asset_sha256
    && v.review.body_ref.asset_sha256 === v.target_face_ref.asset_sha256
    && (v.reference_face_ref.face_instance_id !== v.target_face_ref.face_instance_id || sameFace(v.reference_face_ref, v.target_face_ref));
}
export const requestFits = (command: PeopleAction): boolean => new TextEncoder().encode(JSON.stringify(command)).byteLength <= LIMITS.requestBytes;
export function previewMatchesCatalog(preview: SkinReferenceBodyPreview, catalog: SkinReferenceBodyCatalog): boolean {
  return validPreview(preview) && catalog.skin_reference_body_available && preview.source_review_sha256 === catalog.source_review_sha256
    && catalog.faces.some(face => face.enabled && face.available && sameFace(face.face_ref, preview.reference_face_ref))
    && catalog.targets.some(target => sameFace(target.face_ref, preview.target_face_ref)
      && canonical(target.body_ref) === canonical(preview.review.body_ref) && target.points_sha256 === preview.review.points_sha256)
    && (!catalog.current.reference_face_ref || sameFace(catalog.current.reference_face_ref, preview.reference_face_ref));
}
/** Complete candidate: the selected target changes, all other body rows survive exactly. */
export function retainedTargetsMatch(review: SkinReferenceBodyReview): boolean {
  const before = review.before_current, after = review.candidate_current, selected = review.target_face_ref;
  const expected = [...before.target_face_refs.filter(ref => !sameFace(ref, selected)), selected];
  if (after.target_face_refs.length !== expected.length || !after.target_face_refs.every(ref => expected.some(item => sameFace(item, ref)))
    || !after.reference_face_ref || !sameFace(after.reference_face_ref, review.reference_face_ref)
    || before.reference_face_ref && !sameFace(before.reference_face_ref, review.reference_face_ref)) return false;
  return after.amounts.every(row => sameFace(row.face_ref, selected)
    ? row.amount === review.amount && row.support_sha256 === review.support_sha256
    : before.amounts.some(old => canonical(old) === canonical(row)));
}
export function sameCurrent(a: SkinReferenceBodyCurrent, b: SkinReferenceBodyCurrent): boolean {
  const ordered = (current: SkinReferenceBodyCurrent) => ({...current,
    target_face_refs: [...current.target_face_refs].sort((left, right) => left.face_instance_id.localeCompare(right.face_instance_id)),
    amounts: [...current.amounts].sort((left, right) => left.face_ref.face_instance_id.localeCompare(right.face_ref.face_instance_id))});
  return canonical(ordered(a)) === canonical(ordered(b));
}
export function validReview(v: unknown, view: PeopleView | null, preview: SkinReferenceBodyPreview): v is SkinReferenceBodyReview {
  if (!view || !validPreview(preview) || !object(v) || !exact(v, ['version', 'token', 'operation_id', 'owner', 'source',
    'reference_face_ref', 'target_face_ref', 'body_ref', 'body_review', 'amount', 'source_review_sha256', 'body_bank_sha256',
    'before_current', 'candidate_current', 'candidate_state_revision', 'before_bank_sha256', 'candidate_bank_sha256',
    'support_sha256', 'visual', 'review_sha256']) || v.version !== 1 || !token(v.token) || v.operation_id !== OPERATION_ID
    || !validEndpoint(v.owner) || !validSource(v.source) || !validFaceRef(v.reference_face_ref) || !validFaceRef(v.target_face_ref)
    || !validBodyRef(v.body_ref) || !validConsent(v.body_review) || !positive(v.amount)
    || !safeRevision(v.candidate_state_revision) || v.candidate_state_revision !== v.owner.state_revision + 1
    || !['body_bank_sha256', 'before_bank_sha256', 'candidate_bank_sha256', 'support_sha256', 'review_sha256'].every(field => digest(v[field]))
    || v.source_review_sha256 !== preview.source_review_sha256 || !sameFace(v.reference_face_ref, preview.reference_face_ref)
    || !sameFace(v.target_face_ref, preview.target_face_ref) || canonical(v.body_ref) !== canonical(preview.review.body_ref)
    || canonical(v.body_review) !== canonical(preview.review) || v.amount !== preview.amount
    || !currentFace(v.reference_face_ref, view) || !currentFace(v.target_face_ref, view)
    || !validVisual(v.visual) || !validCurrent(v.before_current, view) || !validCurrent(v.candidate_current, view)
    || v.before_current.bank_sha256 !== v.before_bank_sha256 || v.candidate_current.bank_sha256 !== v.candidate_bank_sha256) return false;
  const owner = v.owner, visual = v.visual, source = v.source;
  return owner.document.document_id === view.binding.document_id && owner.document.epoch === view.binding.document_epoch
    && owner.document.revision === view.binding.document_revision && owner.state_revision === view.revision
    && owner.association_revision === view.association_revision && owner.source_proof.asset_sha256 === view.binding.asset_sha256
    && source.sha256 === view.binding.asset_sha256 && visual.document_id === owner.document.document_id
    && visual.revision === String(owner.document.revision) && sameSpillSourceProof(visual.source_proof, owner.source_proof)
    && visual.source_size[0] === source.width && visual.source_size[1] === source.height
    && retainedTargetsMatch(v as SkinReferenceBodyReview);
}
export const ack = (review: SkinReferenceBodyReview): SkinReferenceBodyAck => ({review_sha256: review.review_sha256,
  before_sha256: review.visual.before.sha256, after_sha256: review.visual.after.sha256});
export const sameAck = (value: unknown, expected: SkinReferenceBodyAck): boolean => object(value)
  && exact(value, ['review_sha256', 'before_sha256', 'after_sha256']) && canonical(value) === canonical(expected);
export const reviewKey = (review: SkinReferenceBodyReview): string => canonical([OPERATION_ID, review.token, review.review_sha256, review.visual]);
export function echoMatches(command: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _requestId, ...captured} = command;
  return object(result.skin_reference_body_request) && canonical(result.skin_reference_body_request) === canonical(captured);
}
export function receiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!view || !isSkinReferenceBodyAction(command.action) || !echoMatches(command, result) || result.protocol !== 1
    || !result.success || result.outcome_unknown !== false || result.request_id !== command.request_id
    || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'all_people' || command.target.target_id !== view.binding.asset_sha256 || command.target.face_ref !== null
    || command.association_revision !== view.association_revision) return false;
  return command.action === 'skin_reference_body_confirm' || command.action === 'skin_reference_body_clear'
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision;
}
export function validReleasedReceipt(command: PeopleAction, result: PeopleResult): boolean {
  return isSkinReferenceBodyAction(command.action) && !['skin_reference_body_confirm', 'skin_reference_body_clear'].includes(command.action)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.payload_released === true
    && result.payload === undefined && result.request_id === command.request_id && result.action === command.action
    && result.document_id === command.document_id && echoMatches(command, result);
}
export function validImageReceipt(payload: unknown, command: PeopleAction): boolean {
  if (command.action !== 'skin_reference_body_image' || !object(payload)
    || !exact(payload, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image'])
    || payload.kind !== command.action || !exact(command.payload, ['token', 'side', 'sha256', 'review_sha256'])
    || !token(payload.token) || !['before', 'after'].includes(String(payload.side))
    || !digest(payload.sha256) || !digest(payload.review_sha256) || !validCollarboneImage(payload.image)) return false;
  return ['token', 'side', 'sha256', 'review_sha256'].every(field => payload[field] === command.payload[field])
    && payload.image.sha256 === payload.sha256;
}
export async function reviewImage(value: unknown, review: SkinReferenceBodyReview, side: SkinReferenceBodySide): Promise<SpillImage | null> {
  if (!object(value) || !exact(value, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image'])
    || value.kind !== 'skin_reference_body_image' || value.token !== review.token || value.side !== side
    || value.review_sha256 !== review.review_sha256 || value.sha256 !== review.visual[side].sha256
    || !validCollarboneImage(value.image)) return null;
  const image = value.image, expected = review.visual[side];
  return image.sha256 === expected.sha256 && image.width === expected.width && image.height === expected.height
    && await verifyCollarboneImage(image) ? image : null;
}
/** Exact mutation proof is checked before any refresh discards the captured pre-edit owner. */
export function validConfirmation(review: SkinReferenceBodyReview, result: PeopleResult): boolean {
  const p = result.payload, next = result.doc_state?.people, owner = review.owner;
  return object(p) && exact(p, ['kind', 'token', 'review_sha256', 'review', 'ack', 'reference_face_ref', 'target_face_ref',
    'body_ref', 'amount', 'candidate_state_revision', 'support_sha256', 'candidate_bank_sha256'])
    && p.kind === 'skin_reference_body_confirm' && p.token === review.token && p.review_sha256 === review.review_sha256
    && canonical(p.review) === canonical(review) && sameAck(p.ack, ack(review)) && canonical(p.reference_face_ref) === canonical(review.reference_face_ref)
    && canonical(p.target_face_ref) === canonical(review.target_face_ref) && canonical(p.body_ref) === canonical(review.body_ref)
    && p.amount === review.amount && p.candidate_state_revision === review.candidate_state_revision
    && p.candidate_bank_sha256 === review.candidate_bank_sha256 && p.support_sha256 === review.support_sha256
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.action === p.kind
    && result.document_id === owner.document.document_id && !!next && next.binding.document_id === owner.document.document_id
    && next.binding.document_epoch === owner.document.epoch && next.binding.asset_sha256 === owner.source_proof.asset_sha256
    && safeRevision(next.binding.document_revision) && next.binding.document_revision === owner.document.revision + 1
    && next.revision === review.candidate_state_revision && next.association_revision === owner.association_revision
    && validCurrent(next.skin_reference_body_match, next) && sameCurrent(next.skin_reference_body_match, review.candidate_current);
}
export function validClear(command: PeopleAction, result: PeopleResult): boolean {
  const p = result.payload, next = result.doc_state?.people;
  return command.action === 'skin_reference_body_clear' && exact(command.payload, []) && echoMatches(command, result)
    && object(p) && exact(p, ['kind', 'candidate_state_revision', 'cleared_face_refs']) && p.kind === command.action
    && safeRevision(p.candidate_state_revision) && p.candidate_state_revision === command.state_revision + 1
    && refs(p.cleared_face_refs) && p.cleared_face_refs.every(ref => ref.asset_sha256 === command.target.target_id)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.request_id === command.request_id
    && result.action === command.action && result.document_id === command.document_id && !!next
    && next.binding.document_id === command.document_id && next.binding.document_epoch === command.document_epoch
    && next.binding.asset_sha256 === command.target.target_id && safeRevision(next.binding.document_revision)
    && next.binding.document_revision === command.document_revision + 1
    && next.revision === p.candidate_state_revision && next.association_revision === command.association_revision
    && validCurrent(next.skin_reference_body_match, next)
    && next.skin_reference_body_match.target_face_refs.length === 0 && next.skin_reference_body_match.amounts.length === 0
    && p.cleared_face_refs.every(ref => currentFace(ref, next, false));
}
