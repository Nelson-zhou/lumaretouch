// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleContext, type FaceRef, type PeopleAction, type PeopleResult, type PeopleView} from '../people/model';
import {digest, documentId, validEndpoint, validFaceRef, type PeopleEndpointProof} from '../people/transferProof';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneImageMetadata, validCollarboneImage, verifyCollarboneImage, type CollarboneImage} from '../collarbone/transferModel';
import {matchesSource, previewImage, type SourcePreview} from '../legShape/sourcePreview';
import type {FaceStyleVisual} from '../faceStyle/model';
import type {SpillImage} from '../spillRemoval/model';
import {canonical, validEyes, type RidgeEyes, type RidgeSource} from './support';

import {validSourceCrops, type SourceCrops} from './sourceCrops';

export const OPERATION_ID = 'lnx.eye_bags.v2' as const;
export type EyeBagRecipe = {version: 2; amount: number; preserve: number};
export const neutral = (): EyeBagRecipe => ({version: 2, amount: 0, preserve: 1});
export type EyeBagAction = 'eye_bag_reference' | 'eye_bag_source_image' | 'eye_bag_preview' | 'eye_bag_image' | 'eye_bag_confirm';
export type EyeBagSide = 'before' | 'after' | 'support';
export type EyeBagReceipt = {command: PeopleAction; result: PeopleResult};
export type EyeBagReference = {kind: 'eye_bag_reference'; source: RidgeSource; face_ref: FaceRef; source_preview: SourcePreview;
  legacy_amount: number; recipe: EyeBagRecipe; eyes: RidgeEyes; source_crops: SourceCrops};
export type EyeBagCandidate = {recipe: EyeBagRecipe; eyes: RidgeEyes; replace_legacy: boolean};
type EyeBagReviewBase = {token: string; recipe: EyeBagRecipe; owner: PeopleEndpointProof; face_ref: FaceRef;
  support_sha256: string; candidate_state_revision: number; replace_legacy: boolean; visual: FaceStyleVisual; support_overlay: CollarboneImage; support_source: {source_width: number; source_height: number; decoded_width: number; decoded_height: number}; review_sha256: string};
export type EyeBagMember = {path: string; visual: FaceStyleVisual};
export type EyeBagReviewV1 = EyeBagReviewBase & {version: 1};
export type EyeBagReviewV2 = EyeBagReviewBase & {version: 2; members: EyeBagMember[]};
export type EyeBagReview = EyeBagReviewV1 | EyeBagReviewV2;
export type EyeBagSingleAck = {review_sha256: string; before_sha256: string; after_sha256: string; support_overlay_sha256: string};
export type EyeBagAliasAck = {review_sha256: string; support_overlay_sha256: string;
  members: {document_id: string; revision: string; before_sha256: string; after_sha256: string}[]};
export type EyeBagAck = EyeBagSingleAck | EyeBagAliasAck;
export type EyeBagAliasCommit = {batchId: string; documentEpoch: string; requestId: string; review: EyeBagReviewV2;
  command: PeopleAction; result: PeopleResult};
export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const unit = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
const revision = (v: unknown): v is string => typeof v === 'string' && /^(0|[1-9]\d{0,15})$/.test(v)
  && BigInt(v) <= BigInt(Number.MAX_SAFE_INTEGER);
const sameFace = (a: FaceRef | null | undefined, b: FaceRef | null | undefined) => !!a && !!b && canonical(a) === canonical(b);
export const eyeBagBinding = (v: PeopleView | null) => canonical(v ? [v.binding, v.revision, v.association_revision, v.editing_target, v.selected_face_id] : null);
export function targetReady(view: PeopleView | null): boolean {
  const selected = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  return !!view && !!peopleContext(view) && !!selected && selected.enabled && selected.analysis_status === 'verified'
    && view.editing_target?.scope === 'face' && view.editing_target.target_id === selected.face_ref.face_instance_id
    && selected.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(selected.face_ref, view.editing_target.face_ref)
    && sameFace(view.resolved?.face_ref, selected.face_ref) && view.resolved?.state_revision === view.revision
    && view.resolved?.association_revision === view.association_revision && view.resolved.conflicts.length === 0;
}
export const validRecipe = (v: unknown): v is EyeBagRecipe => object(v) && keys(v, ['version', 'amount', 'preserve']) && v.version === 2 && unit(v.amount) && unit(v.preserve);
export const validCandidate = (v: unknown): v is EyeBagCandidate => object(v) && keys(v, ['recipe', 'eyes', 'replace_legacy'])
  && validRecipe(v.recipe) && v.recipe.amount > 0 && validEyes(v.eyes, false) && typeof v.replace_legacy === 'boolean';
export function validReference(v: unknown, view: PeopleView | null): v is EyeBagReference {
  if (!view || !targetReady(view) || !object(v) || !keys(v, ['kind', 'source', 'face_ref', 'source_preview', 'legacy_amount', 'recipe', 'eyes', 'source_crops'])
    || v.kind !== 'eye_bag_reference' || !validFaceRef(v.face_ref) || !sameFace(v.face_ref, view.editing_target?.face_ref)
    || !object(v.source) || !keys(v.source, ['sha256', 'width', 'height']) || v.source.sha256 !== view.binding.asset_sha256
    || !validRecipe(v.recipe) || !validEyes(v.eyes) || !unit(v.legacy_amount)) return false;
  const image = previewImage(v.source_preview as SourcePreview);
  return matchesSource(image, {...v.source as RidgeSource, orientation: 'exif_normalized_once'}) && validSourceCrops(v.source_crops, v.source as RidgeSource);
}
function validVisual(v: unknown): v is FaceStyleVisual {
  const size = (s: unknown): s is [number, number] => Array.isArray(s) && s.length === 2 && s.every(n => Number.isSafeInteger(n) && n > 0 && n <= 4294967295);
  if (!object(v) || !keys(v, ['version', 'document_id', 'revision', 'source_proof', 'before_state_sha256', 'candidate_state_sha256',
    'before_people_sha256', 'candidate_people_sha256', 'source_size', 'before_output_size', 'after_output_size', 'before', 'after'])
    || v.version !== 1 || !documentId(v.document_id) || !revision(v.revision) || !sourceProof(v.source_proof)
    || !['before_state_sha256', 'candidate_state_sha256', 'before_people_sha256', 'candidate_people_sha256'].every(k => digest(v[k]))
    || !size(v.source_size) || !size(v.before_output_size) || !size(v.after_output_size)
    || !validCollarboneImageMetadata(v.before) || !validCollarboneImageMetadata(v.after)) return false;
  const derived = v.source_proof.creative_source;
  return (!derived || derived.width === v.source_size[0] && derived.height === v.source_size[1])
    && compactMatches(v.before, v.before_output_size) && compactMatches(v.after, v.after_output_size);
}
function compactMatches(image: CollarboneImage, size: [number, number]): boolean {
  const edge = Math.max(...size), scaled = (n: number) => {
    if (edge <= 1024) return n;
    const q = Math.floor(n * 1024 / edge), r = n * 1024 % edge;
    return Math.max(1, q + (r * 2 > edge || r * 2 === edge && q % 2 === 1 ? 1 : 0));
  };
  return image.width === scaled(size[0]) && image.height === scaled(size[1]);
}
/** The canonical source may use an admitted ALIGN8 decode. Never label its PNG as full resolution. */
function supportMapping(value: unknown, image: CollarboneImage, sourceSize: [number, number]): boolean {
  if (!object(value) || !keys(value, ['source_width', 'source_height', 'decoded_width', 'decoded_height'])
    || !Object.values(value).every(n => typeof n === 'number' && Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000)) return false;
  const {source_width: sw, source_height: sh, decoded_width: dw, decoded_height: dh} = value as EyeBagReview['support_source'];
  return sw === sourceSize[0] && sh === sourceSize[1] && dw <= sw && dh <= sh
    && (dw === sw && dh === sh || dw % 8 === 0 && dh % 8 === 0 && dw * sh < (dh + 8) * sw && dh * sw < (dw + 8) * sh)
    && (Math.max(dw, dh) <= 1024 ? image.width === dw && image.height === dh
      : Math.max(image.width, image.height) === 1024 && Math.abs(image.width * dh - image.height * dw) <= Math.max(dw, dh));
}
export function validReview(v: unknown, view: PeopleView | null, candidate: EyeBagCandidate): v is EyeBagReview {
  return validCandidate(candidate) && validFrozenReview(v, view) && canonical(v.recipe) === canonical(candidate.recipe)
    && v.replace_legacy === candidate.replace_legacy;
}
function validFrozenReview(v: unknown, view: PeopleView | null): v is EyeBagReview {
  if (!view || !targetReady(view) || !object(v)
    || !keys(v, ['version', 'token', 'recipe', 'owner', 'face_ref', 'support_sha256', 'candidate_state_revision', 'replace_legacy', 'visual', 'support_overlay', 'support_source', 'review_sha256', ...(v.version === 2 ? ['members'] : [])])
    || (v.version !== 1 && v.version !== 2) || typeof v.token !== 'string' || !/^[a-f0-9]{32}$/.test(v.token)
    || !validRecipe(v.recipe) || v.recipe.amount <= 0 || typeof v.replace_legacy !== 'boolean'
    || !validEndpoint(v.owner) || !validFaceRef(v.face_ref) || !sameFace(v.face_ref, view.editing_target?.face_ref)
    || !digest(v.support_sha256) || !Number.isSafeInteger(v.candidate_state_revision) || typeof v.candidate_state_revision !== 'number'
    || v.candidate_state_revision <= v.owner.state_revision || v.candidate_state_revision > v.owner.state_revision + 4 || !digest(v.review_sha256) || !validVisual(v.visual)
    || !validCollarboneImageMetadata(v.support_overlay) || !supportMapping(v.support_source, v.support_overlay, v.visual.source_size)) return false;
  const owner = v.owner, visual = v.visual;
  if (!(owner.document.document_id === view.binding.document_id && owner.document.epoch === view.binding.document_epoch
    && owner.document.revision === view.binding.document_revision && owner.state_revision === view.revision
    && owner.association_revision === view.association_revision && owner.source_proof.asset_sha256 === view.binding.asset_sha256
    && visual.document_id === owner.document.document_id && visual.revision === String(owner.document.revision)
    && sameSpillSourceProof(visual.source_proof, owner.source_proof))) return false;
  if (v.version === 1) return true;
  if (owner.people_scope !== 'project' || !Array.isArray(v.members) || v.members.length < 2 || v.members.length > 16) return false;
  const seen = new Set<string>();
  return v.members.every((member, index) => {
    if (!object(member) || !keys(member, ['path', 'visual']) || typeof member.path !== 'string' || !member.path.trim()
      || member.path.includes('\0') || new TextEncoder().encode(member.path).length > 4096 || !validVisual(member.visual)
      || seen.has(member.visual.document_id) || member.visual.source_proof.asset_sha256 !== owner.source_proof.asset_sha256
      || canonical(member.visual.source_size) !== canonical(visual.source_size)
      || index === 0 && canonical(member.visual) !== canonical(visual)) return false;
    seen.add(member.visual.document_id); return true;
  });
}
export const members = (review: EyeBagReview): EyeBagMember[] => review.version === 2 ? review.members : [{path: '', visual: review.visual}];
export const memberKey = (review: EyeBagReview, visual: FaceStyleVisual): string => canonical([review.version, review.token, review.review_sha256, visual]);
export const ack = (review: EyeBagReview): EyeBagAck => review.version === 2
  ? {review_sha256: review.review_sha256, support_overlay_sha256: review.support_overlay.sha256,
    members: review.members.map(({visual}) => ({document_id: visual.document_id, revision: visual.revision,
      before_sha256: visual.before.sha256, after_sha256: visual.after.sha256}))}
  : {review_sha256: review.review_sha256, before_sha256: review.visual.before.sha256,
    after_sha256: review.visual.after.sha256, support_overlay_sha256: review.support_overlay.sha256};
export function imageMetadata(review: EyeBagReview, side: EyeBagSide, documentId = review.visual.document_id): CollarboneImage {
  const visual = members(review).find(member => member.visual.document_id === documentId)?.visual;
  if (!visual || side === 'support' && documentId !== review.visual.document_id) throw Error('审核图不属于冻结成员或来源保护图。');
  return side === 'support' ? review.support_overlay : visual[side];
}
export const imageKey = (review: EyeBagReview, side: EyeBagSide, documentId = review.visual.document_id): string =>
  canonical([review.version, review.token, review.review_sha256, documentId, side, imageMetadata(review, side, documentId)]);
export async function reviewImage(v: unknown, review: EyeBagReview, side: EyeBagSide, documentId = review.visual.document_id): Promise<SpillImage | null> {
  if (!members(review).some(member => member.visual.document_id === documentId) || side === 'support' && documentId !== review.visual.document_id
    || !object(v) || !keys(v, ['kind', 'token', 'side', 'sha256', 'review_sha256', 'image', ...(review.version === 2 ? ['document_id'] : [])]) || v.kind !== 'eye_bag_image'
    || v.token !== review.token || v.side !== side || review.version === 2 && v.document_id !== documentId
    || v.review_sha256 !== review.review_sha256 || !validCollarboneImage(v.image)) return null;
  const expected = imageMetadata(review, side, documentId), image = v.image;
  return v.sha256 === expected.sha256 && image.sha256 === expected.sha256 && image.width === expected.width && image.height === expected.height
    && await verifyCollarboneImage(image) ? image : null;
}
export function echoMatches(command: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _id, ...captured} = command;
  return object(result.eye_bag_request) && canonical(result.eye_bag_request) === canonical(captured);
}
export const isEyeBagAction = (action: string): action is EyeBagAction => ['eye_bag_reference', 'eye_bag_source_image', 'eye_bag_preview', 'eye_bag_image', 'eye_bag_confirm'].includes(action);
export function receiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  if (!view || !isEyeBagAction(command.action) || !echoMatches(command, result) || result.protocol !== 1 || !result.success || result.outcome_unknown
    || result.request_id !== command.request_id || result.action !== command.action || result.document_id !== command.document_id
    || command.document_id !== view.binding.document_id || command.document_epoch !== view.binding.document_epoch
    || command.target.scope !== 'face' || view.editing_target?.scope !== 'face' || command.target.target_id !== view.selected_face_id
    || command.target.target_id !== view.editing_target.target_id || command.target.face_ref?.asset_sha256 !== view.binding.asset_sha256
    || !sameFace(command.target.face_ref, view.editing_target.face_ref) || view.association_revision !== command.association_revision) return false;
  return command.action === 'eye_bag_confirm'
    ? view.binding.document_revision >= command.document_revision && view.revision >= command.state_revision
    : view.binding.document_revision === command.document_revision && view.revision === command.state_revision;
}
export function validConfirmation(review: EyeBagReview, result: PeopleResult): boolean {
  const p = result.payload, next = result.doc_state?.people, resolved = next?.resolved;
  if (review.version === 2 && (!object(p) || typeof result.batch_id !== 'string' || !result.batch_id.trim()
    || result.batch_id.includes('\0') || new TextEncoder().encode(result.batch_id).length > 128
    || !Array.isArray(p.alias_members) || p.alias_members.length !== review.members.length
    || !p.alias_members.every((member, index) => {
      const visual = review.members[index].visual;
      return object(member) && keys(member, ['document_id', 'expected_revision', 'result_revision'])
        && member.document_id === visual.document_id && member.expected_revision === visual.revision
        && revision(member.result_revision) && BigInt(member.result_revision) === BigInt(visual.revision) + 1n;
    }))) return false;
  return object(p) && keys(p, ['kind', 'token', 'review_sha256', 'ack', 'recipe', 'support_sha256', 'replace_legacy', 'candidate_state_revision', ...(review.version === 2 ? ['alias_members'] : [])])
    && p.kind === 'eye_bag_confirm' && p.token === review.token && p.review_sha256 === review.review_sha256
    && canonical(p.ack) === canonical(ack(review)) && canonical(p.recipe) === canonical(review.recipe)
    && p.support_sha256 === review.support_sha256 && p.replace_legacy === review.replace_legacy && p.candidate_state_revision === review.candidate_state_revision
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.action === 'eye_bag_confirm'
    && result.document_id === review.owner.document.document_id
    && !!next && next.binding.document_id === review.owner.document.document_id && next.binding.document_epoch === review.owner.document.epoch
    && next.binding.asset_sha256 === review.owner.source_proof.asset_sha256 && next.binding.document_revision === review.owner.document.revision + 1
    && Number.isSafeInteger(review.owner.document.revision + 1) && next.revision === review.candidate_state_revision
    && canonical(next.eye_bag_preserve?.recipe) === canonical(review.recipe) && next.eye_bag_preserve?.support_sha256 === review.support_sha256
    && sameFace(next.eye_bag_preserve?.face_ref, review.face_ref) && !!resolved && sameFace(resolved.face_ref, review.face_ref)
    && resolved?.state_revision === next.revision && resolved?.association_revision === next.association_revision
    && resolved.operations[OPERATION_ID]?.['/amount']?.value === review.recipe.amount
    && resolved.operations[OPERATION_ID]?.['/preserve']?.value === review.recipe.preserve
    && (!review.replace_legacy || resolved.operations['lnx.enhance.v1']?.['/eye_bags']?.value === 0)
    && (!review.replace_legacy || next.eye_bag_preserve?.legacy_amount === 0) && next.association_revision === review.owner.association_revision;
}

/** Receipt identity survives panel closure. It is not a new undo stack. */
export function validAliasCommit(commit: EyeBagAliasCommit): boolean {
  const {command, result, review} = commit, owner = review.owner, next = result.doc_state?.people;
  const before: PeopleView | null = next ? {...next, binding: {...next.binding, document_revision: owner.document.revision},
    revision: owner.state_revision, resolved: next.resolved ? {...next.resolved, state_revision: owner.state_revision} : null} : null;
  if (review.version !== 2 || !validFrozenReview(review, before)) return false;
  return commit.batchId === result.batch_id && commit.requestId === command.request_id && result.request_id === command.request_id
    && commit.documentEpoch === command.document_epoch && command.document_epoch === owner.document.epoch
    && command.action === 'eye_bag_confirm' && command.document_id === owner.document.document_id
    && command.document_revision === owner.document.revision && command.state_revision === owner.state_revision
    && command.association_revision === owner.association_revision && command.target.scope === 'face'
    && command.target.target_id === review.face_ref.face_instance_id && sameFace(command.target.face_ref, review.face_ref)
    && keys(command.payload, ['token', 'ack']) && command.payload.token === review.token && canonical(command.payload.ack) === canonical(ack(review))
    && echoMatches(command, result) && validConfirmation(review, result);
}
