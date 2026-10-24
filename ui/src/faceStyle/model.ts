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

import {digest, documentId, validEndpoint, validFaceRef, type PeopleEndpointProof} from '../people/transferProof';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneImageMetadata, validCollarboneImage, verifyCollarboneImage,
  type CollarboneImage, type CollarboneVisual} from '../collarbone/transferModel';
import type {SpillImage} from '../spillRemoval/model';
export type FaceStyleRecipe = {version: 1; style: FaceStyle; amount: number};
export type FaceStyleVisual = Omit<CollarboneVisual, 'coverage_sha256'>;
type FaceStyleReviewBase = {token: string; recipe: FaceStyleRecipe; owner: PeopleEndpointProof;
  face_ref: FaceRef; patches_sha256: string; visual: FaceStyleVisual; review_sha256: string};
export type FaceStyleReviewV1 = FaceStyleReviewBase & {version: 1};
export type FaceStyleMember = {path: string; visual: FaceStyleVisual};
export type FaceStyleReviewV2 = FaceStyleReviewBase & {version: 2; members: FaceStyleMember[]};
export type FaceStyleReview = FaceStyleReviewV1 | FaceStyleReviewV2;
export type FaceStyleSingleAck = {review_sha256: string; before_sha256: string; after_sha256: string};
export type FaceStyleMemberAck = {document_id: string; revision: string; before_sha256: string; after_sha256: string};
export type FaceStyleAliasAck = {review_sha256: string; members: FaceStyleMemberAck[]};
export type FaceStyleAck = FaceStyleSingleAck | FaceStyleAliasAck;
export type FaceStyleAliasCommit = {batchId: string; documentEpoch: string; requestId: string; review: FaceStyleReviewV2;
  command: PeopleAction; result: PeopleResult};
export type FaceStyleSide = 'before' | 'after';
export const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const keys = (value: Record<string, unknown>, expected: string[]) => Object.keys(value).sort().join('|') === [...expected].sort().join('|');
const size = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2
  && v.every(n => Number.isSafeInteger(n) && n > 0 && n <= 4294967295);
export function validFaceStyleRecipe(v: unknown): v is FaceStyleRecipe {
  return object(v) && keys(v, ['version', 'style', 'amount']) && v.version === 1 && isFaceStyle(v.style)
    && typeof v.amount === 'number' && Number.isFinite(v.amount) && v.amount >= 0 && v.amount <= 1;
}
const revision = (v: unknown): v is string => typeof v === 'string' && /^(0|[1-9]\d{0,19})$/.test(v)
  && BigInt(v) <= BigInt(Number.MAX_SAFE_INTEGER);
function validVisual(v: unknown): v is FaceStyleVisual {
  if (!object(v) || !keys(v, ['version', 'document_id', 'revision', 'source_proof', 'before_state_sha256',
    'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256', 'source_size',
    'before_output_size', 'after_output_size', 'before', 'after']) || v.version !== 1
    || !documentId(v.document_id) || !revision(v.revision) || !sourceProof(v.source_proof)
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
  const source = v.source_proof.creative_source;
  return (!source || source.width === v.source_size[0] && source.height === v.source_size[1])
    && matches(v.before, v.before_output_size) && matches(v.after, v.after_output_size);
}
export function validFaceStyleReview(value: unknown, view: PeopleView | null, recipe: FaceStyleRecipe): value is FaceStyleReview {
  if (!view || !faceStyleTargetReady(view) || !object(value)
    || !keys(value, ['version', 'token', 'recipe', 'owner', 'face_ref', 'patches_sha256', 'visual', 'review_sha256', ...(value.version === 2 ? ['members'] : [])])
    || (value.version !== 1 && value.version !== 2) || typeof value.token !== 'string' || !/^[a-f0-9]{32}$/.test(value.token)
    || !validFaceStyleRecipe(value.recipe) || value.recipe.style !== recipe.style || value.recipe.amount !== recipe.amount
    || !validEndpoint(value.owner) || !validFaceRef(value.face_ref) || !sameFace(value.face_ref, view.editing_target?.face_ref)
    || !digest(value.patches_sha256) || !digest(value.review_sha256)) return false;
  const owner = value.owner;
  if (!(owner.document.document_id === view.binding.document_id && owner.document.epoch === view.binding.document_epoch
    && owner.document.revision === view.binding.document_revision && owner.state_revision === view.revision
    && owner.association_revision === view.association_revision && owner.source_proof.asset_sha256 === view.binding.asset_sha256
    && validVisual(value.visual) && value.visual.document_id === owner.document.document_id
    && value.visual.revision === String(owner.document.revision) && sameSpillSourceProof(value.visual.source_proof, owner.source_proof))) return false;
  if (value.version === 1) return true;
  if (owner.people_scope !== 'project' || !Array.isArray(value.members) || value.members.length < 2 || value.members.length > 16) return false;
  const seen = new Set<string>();
  return value.members.every((member, index) => {
    if (!object(member) || !keys(member, ['path', 'visual']) || typeof member.path !== 'string'
      || !member.path.trim() || new TextEncoder().encode(member.path).length > 4096 || member.path.includes('\0')
      || !validVisual(member.visual) || seen.has(member.visual.document_id)
      || member.visual.source_proof.asset_sha256 !== owner.source_proof.asset_sha256
      || index === 0 && canonical(member.visual) !== canonical(value.visual)) return false;
    seen.add(member.visual.document_id); return true;
  });
}
export const faceStyleMembers = (review: FaceStyleReview): FaceStyleMember[] => review.version === 2
  ? review.members : [{path: '', visual: review.visual}];
export const faceStyleMemberKey = (review: FaceStyleReview, visual: FaceStyleVisual): string => canonical([
  review.version, review.token, review.review_sha256, visual]);
export function faceStyleReviewReady(review: FaceStyleReview,
  images: Record<string, Partial<Record<FaceStyleSide, SpillImage>>>,
  loaded: Record<string, Partial<Record<FaceStyleSide, boolean>>>, acknowledged: Record<string, boolean>): boolean {
  const members = faceStyleMembers(review);
  return members.length >= (review.version === 2 ? 2 : 1) && members.length <= 16 && members.every(({visual}) => {
    const key = faceStyleMemberKey(review, visual);
    return !!images[key]?.before && !!images[key]?.after && loaded[key]?.before === true
      && loaded[key]?.after === true && acknowledged[key] === true;
  });
}
export function faceStyleAck(review: FaceStyleReview): FaceStyleAck {
  return review.version === 1 ? {review_sha256: review.review_sha256,
    before_sha256: review.visual.before.sha256, after_sha256: review.visual.after.sha256}
    : {review_sha256: review.review_sha256, members: review.members.map(({visual}) => ({document_id: visual.document_id,
      revision: visual.revision, before_sha256: visual.before.sha256, after_sha256: visual.after.sha256}))};
}
export function sameFaceStyleAck(value: unknown, expected: FaceStyleAck): boolean {
  if ('members' in expected) return object(value) && keys(value, ['review_sha256', 'members'])
    && value.review_sha256 === expected.review_sha256 && Array.isArray(value.members)
    && value.members.length >= 2 && value.members.length <= 16 && value.members.length === expected.members.length
    && new Set(expected.members.map(member => member.document_id)).size === expected.members.length
    && value.members.every((member, index) => object(member) && keys(member, ['document_id', 'revision', 'before_sha256', 'after_sha256'])
      && documentId(member.document_id) && revision(member.revision) && digest(member.before_sha256) && digest(member.after_sha256)
      && canonical(member) === canonical(expected.members[index]));
  return object(value) && keys(value, ['review_sha256', 'before_sha256', 'after_sha256'])
    && value.review_sha256 === expected.review_sha256 && value.before_sha256 === expected.before_sha256 && value.after_sha256 === expected.after_sha256;
}
export async function faceStyleImage(value: unknown, review: FaceStyleReview, side: FaceStyleSide,
  documentId = review.visual.document_id): Promise<SpillImage | null> {
  const visual = faceStyleMembers(review).find(member => member.visual.document_id === documentId)?.visual;
  if (!visual || !object(value) || !keys(value, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image', ...(review.version === 2 ? ['document_id'] : [])])
    || value.kind !== 'face_style_image' || value.token !== review.token || value.side !== side
    || review.version === 2 && value.document_id !== documentId
    || value.review_sha256 !== review.review_sha256 || value.sha256 !== visual[side].sha256
    || !validCollarboneImage(value.image)) return null;
  const image = value.image, expected = visual[side];
  return image.sha256 === expected.sha256 && image.width === expected.width && image.height === expected.height
    && await verifyCollarboneImage(image) ? image : null;
}

/** Validate before refresh: the panel may unmount or invalidate as the document revision advances. */
export function validFaceStyleConfirmation(review: FaceStyleReview, result: PeopleResult): boolean {
  const payload = result.payload;
  if (!object(payload) || payload.kind !== 'face_style_confirm' || payload.token !== review.token
    || payload.review_sha256 !== review.review_sha256 || payload.patches_sha256 !== review.patches_sha256
    || !sameFaceStyleAck(payload.ack, faceStyleAck(review))) return false;
  if (review.version === 1) return true;
  if (!keys(payload, ['kind', 'token', 'review_sha256', 'ack', 'recipe', 'patches_sha256', 'alias_members'])
    || canonical(payload.recipe) !== canonical(review.recipe) || typeof result.batch_id !== 'string'
    || !result.batch_id.trim() || new TextEncoder().encode(result.batch_id).length > 128 || result.batch_id.includes('\0')
    || !Array.isArray(payload.alias_members) || payload.alias_members.length !== review.members.length) return false;
  if (!payload.alias_members.every((member, index) => {
    const visual = review.members[index].visual;
    return object(member) && keys(member, ['document_id', 'expected_revision', 'result_revision'])
      && member.document_id === visual.document_id && member.expected_revision === visual.revision
      && revision(member.result_revision) && BigInt(member.result_revision) === BigInt(visual.revision) + 1n;
  })) return false;
  const next = result.doc_state?.people, owner = review.owner;
  // The frozen recipe stages all 30 owned leaves through set_override; graph state advances
  // per leaf, while each logical document and the graph-owner fence advance exactly once.
  const nextStateRevision = owner.state_revision + 30, nextDocumentRevision = owner.document.revision + 1;
  return result.protocol === 1 && result.success && result.outcome_unknown === false
    && result.action === 'face_style_confirm' && result.document_id === owner.document.document_id
    && !!next && next.binding.document_id === owner.document.document_id && next.binding.document_epoch === owner.document.epoch
    && Number.isSafeInteger(nextStateRevision) && Number.isSafeInteger(nextDocumentRevision)
    && next.binding.document_revision === nextDocumentRevision && next.binding.asset_sha256 === owner.source_proof.asset_sha256
    && next.revision === nextStateRevision && next.association_revision === owner.association_revision;
}

/** Only a complete captured alias receipt can introduce a protected batch-history handle. */
export function validFaceStyleAliasCommit(commit: FaceStyleAliasCommit): boolean {
  const {command, result, review} = commit, owner = review.owner;
  const next = result.doc_state?.people;
  const before: PeopleView | null = next ? {...next,
    binding: {...next.binding, document_revision: owner.document.revision}, revision: owner.state_revision,
    resolved: next.resolved ? {...next.resolved, state_revision: owner.state_revision} : null} : null;
  return review.version === 2 && validFaceStyleReview(review, before, review.recipe)
    && commit.batchId === result.batch_id && commit.requestId === command.request_id
    && result.request_id === command.request_id && commit.documentEpoch === command.document_epoch
    && command.action === 'face_style_confirm' && command.document_id === owner.document.document_id
    && command.document_epoch === owner.document.epoch && command.document_revision === owner.document.revision
    && command.state_revision === owner.state_revision && command.association_revision === owner.association_revision
    && command.target.scope === 'face' && command.target.target_id === review.face_ref.face_instance_id
    && sameFace(command.target.face_ref, review.face_ref) && keys(command.payload, ['token', 'ack'])
    && command.payload.token === review.token && sameFaceStyleAck(command.payload.ack, faceStyleAck(review))
    && faceStyleEchoMatches(command, result) && validFaceStyleConfirmation(review, result);
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
