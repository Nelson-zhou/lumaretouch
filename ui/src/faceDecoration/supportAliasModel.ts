// SPDX-License-Identifier: GPL-3.0-or-later
/** Separate visibility-support authority. Never accepts a scalar-alias review or receipt. */
import type {FaceRef, PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {documentId, digest, validEndpoint, validFaceRef, type EffectiveSourceProof, type PeopleEndpointProof} from '../people/transferProof';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneImage, validCollarboneVisualForTarget, verifyCollarboneImage} from '../collarbone/transferModel';
import {canonical, commandCurrent, proofValid, sameFace, targetReady, type ReferenceProof} from './model';
import type {Region} from './review';
import type {DecorationVisual} from './transferModel';
export type SupportAliasAction = 'face_decoration_support_alias_preview' | 'face_decoration_support_alias_image' | 'face_decoration_support_alias_confirm';
export type SupportAliasDraft = {region: Region; reference_proof: ReferenceProof};
export type SupportAliasCoverage = {version: 1; support_change: 'selected-face-only'; targets: {
  face_ref: FaceRef; before_visibility_sha256: string | null; visibility_sha256: string | null;
  before_recipe_sha256: string; recipe_sha256: string;
}[]};
export type SupportAliasReview = {version: 1; token: string; target: 'face_decoration_visibility'; owner: PeopleEndpointProof; face_ref: FaceRef;
  before_support_sha256: string | null; support_sha256: string; before_bank_sha256: string; candidate_bank_sha256: string;
  reference_proof: ReferenceProof; region: Region; candidate_state_revision: number;
  members: {path: string; coverage: SupportAliasCoverage; visual: DecorationVisual}[]; review_sha256: string};
export type SupportAliasReceipt = {command: PeopleAction; result: PeopleResult};
export const isSupportAliasAction = (v: string): v is SupportAliasAction => ['face_decoration_support_alias_preview', 'face_decoration_support_alias_image', 'face_decoration_support_alias_confirm'].includes(v);
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const revision = (v: unknown): v is string => typeof v === 'string' && /^(0|[1-9]\d{0,15})$/.test(v) && Number.isSafeInteger(Number(v));
const optionalDigest = (v: unknown) => v === null || digest(v);
export function validSupportAliasCoverage(v: unknown, source: EffectiveSourceProof): v is SupportAliasCoverage {
  if (!object(v) || !keys(v, ['version', 'support_change', 'targets']) || v.version !== 1 || v.support_change !== 'selected-face-only'
    || !Array.isArray(v.targets) || !v.targets.length || v.targets.length > 64) return false;
  let previous = '';
  return v.targets.every(row => {
    if (!object(row) || !keys(row, ['face_ref', 'before_visibility_sha256', 'visibility_sha256', 'before_recipe_sha256', 'recipe_sha256'])
      || !validFaceRef(row.face_ref) || row.face_ref.asset_sha256 !== source.asset_sha256 || row.face_ref.face_instance_id <= previous
      || !optionalDigest(row.before_visibility_sha256) || !optionalDigest(row.visibility_sha256)
      || !digest(row.before_recipe_sha256) || row.before_recipe_sha256 !== row.recipe_sha256) return false;
    previous = row.face_ref.face_instance_id; return true;
  });
}
export async function verifySupportAliasCoverage(visual: DecorationVisual, coverage: SupportAliasCoverage): Promise<boolean> {
  const bytes = new TextEncoder().encode(canonical(coverage));
  const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
  return actual === visual.coverage_sha256;
}
export function validSupportAliasReview(v: unknown, view: PeopleView | null, draft: unknown): v is SupportAliasReview {
  if (!view || !targetReady(view) || view.editing_target?.scope !== 'face' || view.editing_target.target_id !== view.selected_face_id
    || !object(draft) || !keys(draft, ['region', 'reference_proof']) || !proofValid(draft.reference_proof)
    || !object(v) || !keys(v, ['version', 'token', 'target', 'owner', 'face_ref', 'before_support_sha256', 'support_sha256', 'before_bank_sha256', 'candidate_bank_sha256', 'reference_proof', 'region', 'candidate_state_revision', 'members', 'review_sha256'])
    || v.version !== 1 || v.target !== 'face_decoration_visibility' || typeof v.token !== 'string' || !/^[a-f0-9]{32}$/.test(v.token)
    || !digest(v.review_sha256) || !validEndpoint(v.owner) || !validFaceRef(v.face_ref) || !sameFace(v.face_ref, view.editing_target.face_ref)
    || !optionalDigest(v.before_support_sha256) || !digest(v.support_sha256) || v.before_support_sha256 === v.support_sha256
    || v.before_support_sha256 === null && (view.face_decoration?.recipe.strength ?? 0) > 0
    || !digest(v.before_bank_sha256) || !digest(v.candidate_bank_sha256)
    || !proofValid(v.reference_proof) || canonical(v.reference_proof) !== canonical(draft.reference_proof)
    || canonical(v.region) !== canonical(draft.region) || !sameFace(v.reference_proof.face_ref, v.face_ref)
    || canonical(v.reference_proof.source) !== canonical(view.face_decoration?.source)
    || v.reference_proof.landmark_digest !== view.face_decoration?.landmark_digest) return false;
  const owner = v.owner;
  if (owner.people_scope !== 'project' || owner.document.document_id !== view.binding.document_id || owner.document.epoch !== view.binding.document_epoch
    || owner.document.revision !== view.binding.document_revision || owner.state_revision !== view.revision || owner.association_revision !== view.association_revision
    || owner.source_proof.asset_sha256 !== view.binding.asset_sha256 || v.candidate_state_revision !== owner.state_revision + 1
    || !Number.isSafeInteger(v.candidate_state_revision) || !Array.isArray(v.members) || v.members.length < 2 || v.members.length > 16) return false;
  const ids = new Set<string>();
  return v.members.every((member, index) => {
    if (!object(member) || !keys(member, ['path', 'coverage', 'visual']) || typeof member.path !== 'string' || !member.path.trim()
      || member.path.includes('\0') || new TextEncoder().encode(member.path).length > 4096 || !object(member.visual)
      || !documentId(member.visual.document_id) || !revision(member.visual.revision) || ids.has(member.visual.document_id)
      || !sourceProof(member.visual.source_proof) || member.visual.source_proof.asset_sha256 !== owner.source_proof.asset_sha256
      || !validCollarboneVisualForTarget(member.visual, member.visual.document_id, member.visual.revision, member.visual.source_proof)
      || !validSupportAliasCoverage(member.coverage, member.visual.source_proof)
      || index === 0 && (member.visual.document_id !== owner.document.document_id || member.visual.revision !== String(owner.document.revision)
        || !sameSpillSourceProof(member.visual.source_proof, owner.source_proof))) return false;
    const selected = member.coverage.targets.find(row => sameFace(row.face_ref, v.face_ref as FaceRef));
    if (!selected || selected.before_visibility_sha256 !== v.before_support_sha256 || selected.visibility_sha256 !== v.support_sha256
      || member.coverage.targets.some(row => !sameFace(row.face_ref, v.face_ref as FaceRef) && row.before_visibility_sha256 !== row.visibility_sha256)
      || member.visual.before_state_sha256 !== member.visual.candidate_state_sha256
      || canonical(member.visual.before_output_size) !== canonical(member.visual.after_output_size)) return false;
    ids.add(member.visual.document_id); return true;
  });
}
export const supportAliasAck = (review: SupportAliasReview) => ({review_sha256: review.review_sha256, members: review.members.map(({visual}) => ({
  document_id: visual.document_id, revision: visual.revision, before_sha256: visual.before.sha256, after_sha256: visual.after.sha256,
}))});
export const supportAliasKey = (review: SupportAliasReview, visual: DecorationVisual) => canonical(['face_decoration_support_alias', review.token, review.review_sha256, visual]);
export async function verifySupportAliasReview(review: SupportAliasReview): Promise<boolean> {
  // Bank, region and graph digests remain engine-owned; exact echoed numbers are compared structurally above.
  return digest(review.review_sha256) && (await Promise.all(review.members.map(m => verifySupportAliasCoverage(m.visual, m.coverage)))).every(Boolean);
}
export function supportAliasEchoMatches(command: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _id, ...expected} = command;
  return isSupportAliasAction(command.action) && result.protocol === 1 && typeof result.success === 'boolean' && typeof result.outcome_unknown === 'boolean'
    && canonical(result.face_decoration_support_alias_request) === canonical(expected);
}
export function supportAliasReceiptCurrent(command: PeopleAction, result: PeopleResult, view: PeopleView | null): boolean {
  return supportAliasEchoMatches(command, result) && result.success && !result.outcome_unknown && result.request_id === command.request_id
    && result.action === command.action && result.document_id === command.document_id && !!view
    && (command.action === 'face_decoration_support_alias_confirm'
      ? command.document_id === view.binding.document_id && command.document_epoch === view.binding.document_epoch
        && sameFace(command.target.face_ref, view.editing_target?.face_ref) && view.binding.document_revision === command.document_revision + 1
      : commandCurrent(command, view));
}
export async function supportAliasImage(payload: unknown, review: SupportAliasReview, document: string, side: 'before' | 'after') {
  const expected = review.members.find(m => m.visual.document_id === document)?.visual[side];
  if (!expected || !object(payload) || !keys(payload, ['kind', 'token', 'document_id', 'side', 'sha256', 'review_sha256', 'image'])
    || payload.kind !== 'face_decoration_support_alias_image' || payload.token !== review.token || payload.document_id !== document
    || payload.side !== side || payload.sha256 !== expected.sha256 || payload.review_sha256 !== review.review_sha256 || !validCollarboneImage(payload.image))
    throw Error('共享来源装饰范围图像身份不匹配。');
  const image = payload.image;
  if (image.sha256 !== expected.sha256 || image.width !== expected.width || image.height !== expected.height || !await verifyCollarboneImage(image))
    throw Error('共享来源装饰范围图像内容不匹配。');
  return image;
}
export function validSupportAliasConfirmation(review: SupportAliasReview, result: PeopleResult): boolean {
  const p = result.payload, owner = review.owner, next = result.doc_state?.people;
  if (!object(p) || !keys(p, ['kind', 'token', 'review_sha256', 'target', 'face_ref', 'before_support_sha256', 'support_sha256', 'before_bank_sha256', 'candidate_bank_sha256', 'candidate_state_revision', 'ack', 'history_review_sha256', 'alias_members'])
    || p.kind !== 'face_decoration_support_alias_confirm' || p.token !== review.token || p.review_sha256 !== review.review_sha256
    || p.target !== review.target || canonical(p.face_ref) !== canonical(review.face_ref) || p.before_support_sha256 !== review.before_support_sha256
    || p.support_sha256 !== review.support_sha256 || p.before_bank_sha256 !== review.before_bank_sha256 || p.candidate_bank_sha256 !== review.candidate_bank_sha256
    || p.candidate_state_revision !== review.candidate_state_revision || !digest(p.history_review_sha256) || canonical(p.ack) !== canonical(supportAliasAck(review))
    || typeof result.batch_id !== 'string' || !result.batch_id.trim() || new TextEncoder().encode(result.batch_id).length > 128 || /[\u0000-\u001f\u007f]/.test(result.batch_id)
    || !Array.isArray(p.alias_members) || p.alias_members.length !== review.members.length) return false;
  const report = next?.face_decoration;
  return p.alias_members.every((member, index) => object(member) && keys(member, ['document_id', 'expected_revision', 'result_revision'])
    && member.document_id === review.members[index].visual.document_id && member.expected_revision === review.members[index].visual.revision
    && revision(member.result_revision) && BigInt(member.result_revision) === BigInt(review.members[index].visual.revision) + 1n)
    && result.protocol === 1 && result.success && result.outcome_unknown === false && result.action === 'face_decoration_support_alias_confirm'
    && result.document_id === owner.document.document_id && !!next && next.binding.document_id === owner.document.document_id
    && next.binding.document_epoch === owner.document.epoch && next.binding.asset_sha256 === owner.source_proof.asset_sha256
    && next.binding.document_revision === owner.document.revision + 1 && next.revision === review.candidate_state_revision
    && next.association_revision === owner.association_revision && !!report && sameFace(report.face_ref, review.face_ref)
    && report.support_sha256 === review.support_sha256 && report.reviewed === true;
}
export async function supportAliasHistoryDigest(review: SupportAliasReview): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(supportAliasAck(review))))), n => n.toString(16).padStart(2, '0')).join('');
}
