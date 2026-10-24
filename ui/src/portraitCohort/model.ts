// SPDX-License-Identifier: GPL-3.0-or-later
import type {AssociationIntent, AssociationRequest, AssociationReview, AssociationTarget} from '../people/associationProof';
import {validAssociationReview} from '../people/associationProof';
import {validCollarboneVisualForTarget} from '../collarbone/transferModel';
import {faceStyleSelection} from '../faceStyle/batchModel';
import type {FaceStyleVisual} from '../faceStyle/model';
export const PORTRAIT_COHORT_LIMIT = 16;
export type PortraitCohortVisual = FaceStyleVisual & {cohort_sha256: string};
export type PortraitCohortAck = {document_id: string; revision: string; before_sha256: string; after_sha256: string; cohort_sha256: string};
type CohortPlan = {portrait_cohort?: boolean; persistent_association?: AssociationReview; association_source?: AssociationTarget;
  targets: AssociationTarget[]; module_scope: string[]};
export type PortraitCohortTarget = {document_id: string; path: string; source: boolean; visual: PortraitCohortVisual};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, names: string[]) => Object.keys(v).sort().join('|') === [...names].sort().join('|');
const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
/** Key coverage, not recipe coefficient matching. Generic edits cannot evade whole-member review. */
export function portraitIntentRequiresReview(intent: AssociationIntent[] | undefined): boolean {
  return !!intent && Object.entries(faceStyleSelection()).every(([op, paths]) => paths.every(path => intent.some(leaf => leaf.op === op && leaf.path === path)));
}
export function validPortraitCohortVisual(value: unknown, target: AssociationTarget): value is PortraitCohortVisual {
  if (!object(value) || !digest(value.cohort_sha256) || !target.association || typeof target.revision !== 'string'
    || Object.hasOwn(value, 'coverage_sha256') || Object.hasOwn(value, 'recipe_sha256')) return false;
  const {cohort_sha256, ...base} = value;
  return validCollarboneVisualForTarget({...base, coverage_sha256: cohort_sha256}, target.document_id, target.revision,
    target.association.owner.source_proof);
}
/** Source always comes first; preserve the frozen target order for the ACK. */
export function portraitCohortTargets(plan: CohortPlan): PortraitCohortTarget[] {
  if (plan.portrait_cohort !== true || !plan.association_source) return [];
  return [plan.association_source, ...plan.targets].flatMap((row, index) => row.association?.portrait_visual
    ? [{document_id: row.document_id, path: row.path, source: index === 0, visual: row.association.portrait_visual}] : []);
}
export function validPortraitCohort(plan: CohortPlan, request: AssociationRequest): boolean {
  const required = request.face_style !== undefined || portraitIntentRequiresReview(plan.persistent_association?.intent);
  const rows = plan.association_source ? [plan.association_source, ...plan.targets] : plan.targets;
  const present = rows.some(row => row.association?.portrait_visual !== undefined);
  if (plan.portrait_cohort !== true) return plan.portrait_cohort === undefined && !required && !present;
  if (!required || !plan.association_source || !plan.persistent_association || rows.length < 2 || rows.length > PORTRAIT_COHORT_LIMIT
    || !validAssociationReview(plan.persistent_association, request, plan.association_source, plan.targets)) return false;
  if (request.face_style && JSON.stringify(plan.module_scope) !== JSON.stringify(Object.keys(faceStyleSelection()))) return false;
  const cohort = rows[0].association?.portrait_visual?.cohort_sha256;
  // Python owns this frozen digest. Never reserialize intent numbers or infer a named recipe here.
  return digest(cohort) && rows.every(row => !row.blocked && validPortraitCohortVisual(row.association?.portrait_visual, row)
    && row.association!.portrait_visual!.cohort_sha256 === cohort);
}
export function portraitCohortReviewKey(token: string, visual: PortraitCohortVisual): string {
  return JSON.stringify(['portrait_cohort.v1', token, visual]);
}
export function portraitCohortImagesReady(token: string, values: (PortraitCohortVisual | undefined)[], ready: Record<string, boolean>): boolean {
  return values.length >= 2 && values.length <= PORTRAIT_COHORT_LIMIT
    && values.every(value => !!value && ready[portraitCohortReviewKey(token, value)] === true);
}
export function portraitCohortAck(values: PortraitCohortVisual[]): PortraitCohortAck[] {
  return values.map(value => ({document_id: value.document_id, revision: value.revision,
    before_sha256: value.before.sha256, after_sha256: value.after.sha256, cohort_sha256: value.cohort_sha256}));
}
export function samePortraitCohortAck(value: unknown, expected: PortraitCohortAck[] | undefined): value is PortraitCohortAck[] {
  if (!Array.isArray(value) || !expected || expected.length < 2 || expected.length > PORTRAIT_COHORT_LIMIT || value.length !== expected.length
    || new Set(expected.map(row => row.document_id)).size !== expected.length) return false;
  return value.every((row, index) => object(row) && keys(row, ['document_id', 'revision', 'before_sha256', 'after_sha256', 'cohort_sha256'])
    && Object.keys(row).every(key => row[key] === expected[index][key as keyof PortraitCohortAck]));
}
export const validPortraitCohortAck = (value: unknown, visuals: PortraitCohortVisual[]) => samePortraitCohortAck(value, portraitCohortAck(visuals));
