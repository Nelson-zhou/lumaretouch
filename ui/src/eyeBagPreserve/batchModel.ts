// SPDX-License-Identifier: GPL-3.0-or-later
// Ordinary explicit face-map transfer only. Support and recovery are never portable.
import type {FaceRef} from '../people/model';
import {documentId, validFaceRef, sameFace, type PeopleTransferReview} from '../people/transferProof';
import {validCollarboneVisual, type CollarboneVisual, type CollarboneImage} from '../collarbone/transferModel';
import type {EyeBagPresetCoverage} from './presetModel';

export const EYE_BAG_BATCH_OP = 'lnx.eye_bags.v2';
export const EYE_BAG_BATCH_LIMIT = 16;
export type EyeBagBatchPolicy = {version: 1; targets: {document_id: string; replace_legacy: boolean}[]};
export type EyeBagTargetPolicy = {version: 1; replace_legacy: boolean};
export type EyeBagBatchCoverage = EyeBagPresetCoverage;
export type EyeBagBatchVisual = CollarboneVisual;
export type EyeBagBatchImageMetadata = CollarboneImage;
export type EyeBagBatchAck = {document_id: string; revision: string; before_sha256: string; after_sha256: string;
  coverage_sha256: string; replace_legacy: boolean};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export function validEyeBagBatchPolicy(value: unknown, ids: string[]): value is EyeBagBatchPolicy {
  if (!object(value) || !keys(value, ['version', 'targets']) || value.version !== 1 || !Array.isArray(value.targets)
    || !ids.length || ids.length > EYE_BAG_BATCH_LIMIT || new Set(ids).size !== ids.length || !ids.every(documentId)
    || value.targets.length !== ids.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['document_id', 'replace_legacy']) || !documentId(row.document_id)
      || typeof row.replace_legacy !== 'boolean' || !ids.includes(row.document_id) || seen.has(row.document_id)) return false;
    seen.add(row.document_id);
  }
  return seen.size === ids.length;
}
export function sameEyeBagBatchPolicy(value: unknown, expected: EyeBagBatchPolicy, ids: string[]): boolean {
  return validEyeBagBatchPolicy(value, ids) && validEyeBagBatchPolicy(expected, ids)
    && value.targets.every(row => expected.targets.some(other => other.document_id === row.document_id && other.replace_legacy === row.replace_legacy));
}
/** No default policy: even false must be explicitly selected for every frozen document. */
export function eyeBagBatchPolicy(ids: string[], choices: Record<string, boolean | undefined>): EyeBagBatchPolicy | undefined {
  if (ids.some(id => typeof choices[id] !== 'boolean')) return undefined;
  const value: EyeBagBatchPolicy = {version: 1, targets: ids.map(document_id => ({document_id, replace_legacy: choices[document_id]!}))};
  return validEyeBagBatchPolicy(value, ids) ? value : undefined;
}
export function validEyeBagBatchCoverage(value: unknown, refs: FaceRef[]): value is EyeBagBatchCoverage {
  if (!object(value) || !keys(value, ['version', 'support_transfer', 'targets']) || value.version !== 1
    || value.support_transfer !== 'none' || !refs.length || refs.length > 128 || !Array.isArray(value.targets)
    || value.targets.length !== refs.length || new Set(refs.map(ref => ref.face_instance_id)).size !== refs.length) return false;
  const seen = new Set<string>();
  for (const row of value.targets) {
    if (!object(row) || !keys(row, ['face_ref', 'scope', 'ridge_sha256', 'sides']) || !validFaceRef(row.face_ref)
      || seen.has(row.face_ref.face_instance_id) || !refs.some(ref => sameFace(ref, row.face_ref as FaceRef))
      || !Array.isArray(row.sides) || row.sides.some(side => side !== 'left' && side !== 'right')
      || new Set(row.sides).size !== row.sides.length || row.sides.join('|') !== [...row.sides].sort().join('|')) return false;
    if (row.scope === 'neutral-no-effect' ? row.ridge_sha256 !== null || row.sides.length !== 0
      : row.scope !== 'target-reviewed-ridge' || !hash(row.ridge_sha256) || row.sides.length < 1 || row.sides.length > 2) return false;
    seen.add(row.face_ref.face_instance_id);
  }
  return seen.size === refs.length;
}
export function validEyeBagTargetPolicy(value: unknown, expected: boolean): value is EyeBagTargetPolicy {
  return object(value) && keys(value, ['version', 'replace_legacy']) && value.version === 1 && value.replace_legacy === expected;
}
export function validEyeBagBatchReview(review: PeopleTransferReview, replaceLegacy: boolean): boolean {
  if (review.target_policy !== 'explicit_face_map' || !validEyeBagTargetPolicy(review.eye_bag, replaceLegacy)
    || !validEyeBagBatchCoverage(review.eye_bag_coverage, review.target_refs) || !validCollarboneVisual(review.eye_bag_visual, review)) return false;
  const leaves = review.parameters.filter(leaf => leaf.operation_id === EYE_BAG_BATCH_OP);
  if (!leaves.length || leaves.some(leaf => !['/amount', '/preserve'].includes(leaf.parameter_path)
    || typeof leaf.value !== 'number' || !Number.isFinite(leaf.value) || leaf.value < 0 || leaf.value > 1)) return false;
  const amount = leaves.find(leaf => leaf.parameter_path === '/amount');
  const active = review.eye_bag_coverage.targets.some(row => row.scope === 'target-reviewed-ridge');
  if (active && review.parameters.some(leaf => leaf.operation_id === 'lnx.enhance.v1' && leaf.parameter_path === '/eye_bags'
    && typeof leaf.value === 'number' && leaf.value > 0)) return false;
  if (review.collarbone_visual) {
    const {coverage_sha256: _eye, ...eye} = review.eye_bag_visual!;
    const {coverage_sha256: _collarbone, ...collarbone} = review.collarbone_visual;
    if (canonical(eye) !== canonical(collarbone)) return false;
  }
  // Preserve-only updates retain each target's own amount, so do not infer activity from the donor.
  return amount === undefined || review.eye_bag_coverage.targets.every(row => (row.scope === 'neutral-no-effect') === (amount.value === 0));
}
function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (object(v)) return '{' + Object.keys(v).sort().map(key => JSON.stringify(key) + ':' + canonical(v[key])).join(',') + '}';
  const encoded = JSON.stringify(v); if (typeof encoded !== 'string') throw Error('Invalid eye-bag coverage'); return encoded;
}
export async function verifyEyeBagBatchCoverage(visual: EyeBagBatchVisual, coverage: EyeBagBatchCoverage): Promise<boolean> {
  try {return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(coverage)))),
    n => n.toString(16).padStart(2, '0')).join('') === visual.coverage_sha256;} catch {return false;}
}
export function eyeBagBatchReviewKey(token: string, visual: EyeBagBatchVisual, policy: EyeBagTargetPolicy): string {
  return JSON.stringify([EYE_BAG_BATCH_OP, token, policy, visual]);
}
export function eyeBagBatchImagesReady(token: string, reviews: PeopleTransferReview[], ready: Record<string, boolean>): boolean {
  return reviews.length <= EYE_BAG_BATCH_LIMIT && reviews.every(review => !!review.eye_bag_visual && !!review.eye_bag
    && ready[eyeBagBatchReviewKey(token, review.eye_bag_visual, review.eye_bag)] === true);
}
export function eyeBagBatchAck(reviews: PeopleTransferReview[]): EyeBagBatchAck[] {
  return reviews.map(review => {
    if (!review.eye_bag || !review.eye_bag_visual) throw Error('祛眼袋审核缺少冻结策略或图像');
    const value = review.eye_bag_visual;
    return {document_id: value.document_id, revision: value.revision, before_sha256: value.before.sha256,
      after_sha256: value.after.sha256, coverage_sha256: value.coverage_sha256, replace_legacy: review.eye_bag.replace_legacy};
  });
}
export function sameEyeBagBatchAck(value: unknown, expected: EyeBagBatchAck[] | undefined): value is EyeBagBatchAck[] {
  if (!Array.isArray(value) || !expected?.length || expected.length > EYE_BAG_BATCH_LIMIT || value.length !== expected.length
    || new Set(expected.map(row => row.document_id)).size !== expected.length) return false;
  return value.every((row, index) => object(row) && keys(row, ['document_id', 'revision', 'before_sha256', 'after_sha256', 'coverage_sha256', 'replace_legacy'])
    && Object.keys(row).every(key => row[key] === expected[index][key as keyof EyeBagBatchAck]));
}
export function validEyeBagBatchAck(value: unknown, reviews: PeopleTransferReview[]): value is EyeBagBatchAck[] {
  try {return sameEyeBagBatchAck(value, eyeBagBatchAck(reviews));} catch {return false;}
}
