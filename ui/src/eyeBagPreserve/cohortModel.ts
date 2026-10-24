// SPDX-License-Identifier: GPL-3.0-or-later
import type {AssociationIntent, AssociationRequest, AssociationReview, AssociationTarget} from '../people/associationProof';
import {validAssociationReview} from '../people/associationProof';
import {sameFace, validFaceRef} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {validCollarboneVisualForTarget, type CollarboneVisual} from '../collarbone/transferModel';
import {sameEyeBagBatchAck, type EyeBagBatchAck} from './batchModel';
import {validEyeBagCohortPolicy} from './cohortPolicy';
export const EYE_BAG_COHORT_OP = 'lnx.eye_bags.v2';
export type EyeBagCohortSide = {scope: 'neutral-no-effect' | 'target-reviewed-ridge'; ridge_sha256: string | null; sides: ('left' | 'right')[]};
export type EyeBagCohortCoverage = {version: 1; support_transfer: 'none'; replace_legacy: boolean; face_ref: FaceRef;
  before: EyeBagCohortSide; after: EyeBagCohortSide};
export type EyeBagCohortVisual = CollarboneVisual;
export type EyeBagCohortAck = EyeBagBatchAck;
type CohortPlan = {eye_bag_cohort?: boolean; persistent_association?: AssociationReview; association_source?: AssociationTarget;
  targets: AssociationTarget[]; module_scope: string[]};
export type EyeBagCohortTarget = {document_id: string; path: string; source: boolean; visual: EyeBagCohortVisual; coverage: EyeBagCohortCoverage};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const eyeBagIntentRequiresReview = (intent: AssociationIntent[] | undefined) => intent?.some(row => row.op === EYE_BAG_COHORT_OP) === true;
function validSide(v: unknown): v is EyeBagCohortSide {
  if (!object(v) || !keys(v, ['scope', 'ridge_sha256', 'sides']) || !Array.isArray(v.sides)
    || v.sides.some(side => side !== 'left' && side !== 'right') || new Set(v.sides).size !== v.sides.length
    || v.sides.join('|') !== [...v.sides].sort().join('|')) return false;
  return v.scope === 'neutral-no-effect' ? v.ridge_sha256 === null && v.sides.length === 0
    : v.scope === 'target-reviewed-ridge' && digest(v.ridge_sha256) && v.sides.length >= 1 && v.sides.length <= 2;
}
export function validEyeBagCohortCoverage(value: unknown, ref: FaceRef, replaceLegacy: boolean): value is EyeBagCohortCoverage {
  return object(value) && keys(value, ['version', 'support_transfer', 'replace_legacy', 'face_ref', 'before', 'after'])
    && value.version === 1 && value.support_transfer === 'none' && value.replace_legacy === replaceLegacy
    && validFaceRef(value.face_ref) && sameFace(value.face_ref, ref) && validSide(value.before) && validSide(value.after);
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  const encoded = JSON.stringify(value); if (encoded === undefined) throw Error('Invalid cohort coverage'); return encoded;
}
function imageIdentity(value: unknown): string | undefined {
  if (!object(value)) return undefined;
  const {coverage_sha256: _coverage, cohort_sha256: _cohort, ...rest} = value;
  return canonical(rest);
}
export function eyeBagCohortTargets(plan: CohortPlan): EyeBagCohortTarget[] {
  if (plan.eye_bag_cohort !== true || !plan.association_source) return [];
  return [plan.association_source, ...plan.targets].flatMap((row, index) => row.association?.eye_bag_cohort && row.association.eye_bag_cohort_visual
    ? [{document_id: row.document_id, path: row.path, source: index === 0, coverage: row.association.eye_bag_cohort, visual: row.association.eye_bag_cohort_visual}] : []);
}
export function validEyeBagCohort(plan: CohortPlan, request: AssociationRequest): boolean {
  const rows = plan.association_source ? [plan.association_source, ...plan.targets] : plan.targets;
  const requested = Object.hasOwn(request, 'eye_bag_cohort');
  const knownRequired = Object.hasOwn(request.selection, EYE_BAG_COHORT_OP) || eyeBagIntentRequiresReview(plan.persistent_association?.intent);
  const present = rows.some(row => row.association && ['eye_bag_cohort', 'eye_bag_cohort_visual'].some(field => Object.hasOwn(row.association!, field)));
  if (plan.eye_bag_cohort !== true) return plan.eye_bag_cohort === undefined && !requested && !knownRequired && !present;
  const ids = [request.source.document.document_id, ...request.targets.map(row => row.target.document.document_id)];
  if (!requested || !validEyeBagCohortPolicy(request.eye_bag_cohort, ids) || !plan.association_source || !plan.persistent_association
    || rows.length !== ids.length || !validAssociationReview(plan.persistent_association, request, plan.association_source, plan.targets)) return false;
  return rows.every((row, index) => {
    const a = row.association, policy = request.eye_bag_cohort!.members[index];
    if (!a || row.blocked || row.document_id !== ids[index] || typeof row.revision !== 'string'
      || !validEyeBagCohortCoverage(a.eye_bag_cohort, a.ref, policy.replace_legacy)
      || !validCollarboneVisualForTarget(a.eye_bag_cohort_visual, row.document_id, row.revision, a.owner.source_proof)) return false;
    // Independently mandatory families must refer to exactly the same full mixed render.
    return [a.collarbone_visual, a.portrait_visual].every(other => other === undefined || imageIdentity(other) === imageIdentity(a.eye_bag_cohort_visual));
  });
}
export async function verifyEyeBagCohortCoverage(visual: EyeBagCohortVisual, coverage: EyeBagCohortCoverage): Promise<boolean> {
  try {return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(coverage)))),
    value => value.toString(16).padStart(2, '0')).join('') === visual.coverage_sha256;} catch {return false;}
}
export const eyeBagCohortReviewKey = (token: string, target: EyeBagCohortTarget) => JSON.stringify(['eye_bag_cohort.v1', token, target]);
export function eyeBagCohortImagesReady(token: string, targets: EyeBagCohortTarget[], ready: Record<string, boolean>): boolean {
  return targets.length >= 2 && targets.length <= 16 && targets.every(target => ready[eyeBagCohortReviewKey(token, target)] === true);
}
export function eyeBagCohortAck(targets: EyeBagCohortTarget[]): EyeBagCohortAck[] {
  return targets.map(({visual, coverage}) => ({document_id: visual.document_id, revision: visual.revision,
    before_sha256: visual.before.sha256, after_sha256: visual.after.sha256, coverage_sha256: visual.coverage_sha256, replace_legacy: coverage.replace_legacy}));
}
export function sameEyeBagCohortAck(value: unknown, expected: EyeBagCohortAck[] | undefined): value is EyeBagCohortAck[] {
  return !!expected && expected.length >= 2 && sameEyeBagBatchAck(value, expected);
}
export const validEyeBagCohortAck = (value: unknown, targets: EyeBagCohortTarget[]) => sameEyeBagCohortAck(value, eyeBagCohortAck(targets));
