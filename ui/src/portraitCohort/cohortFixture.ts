// AUTHORED / UNRUN synthetic source-contract fixtures, never photographic acceptance.
import {cohortFixture} from '../collarbone/cohortFixture';
import {faceStyleSelection} from '../faceStyle/batchModel';
import type {AssociationRequest, AssociationReview, AssociationTarget} from '../people/associationProof';
import type {FaceStyleRecipe} from '../faceStyle/model';
import type {PortraitCohortVisual} from './model';
export function portraitFixture(operation: AssociationRequest['operation'] = 'create', named = true, collarbone = false) {
  const f = cohortFixture(operation), people: AssociationRequest = {...f.people};
  people.selection = operation === 'unlink' ? {} : named ? faceStyleSelection() : {'lnx.face_size.v1': ['/amount']};
  if (named && operation !== 'unlink') people.face_style = {version: 1, style: 'classic', amount: .5} as FaceStyleRecipe;
  const rows: AssociationTarget[] = [f.plan.association_source, ...f.plan.targets].map(row => {
    const {coverage_sha256: _, ...base} = row.association!.collarbone_visual!;
    const visual: PortraitCohortVisual = {...base, cohort_sha256: 'c'.repeat(64)};
    const {collarbone_coverage, collarbone_visual, ...association} = row.association!;
    return {...row, association: {...association, portrait_visual: visual,
      ...(collarbone ? {collarbone_coverage, collarbone_visual} : {})}};
  });
  const review: AssociationReview = {...f.plan.persistent_association, intent: Object.entries(faceStyleSelection()).flatMap(([op, paths]) => paths.map(path => ({op, path,
    // Deliberately not a named recipe's coefficients: the invariant is complete key coverage.
    value: path.endsWith('/linked') ? true : .123456789}))) };
  if (collarbone) review.intent.push({op: 'lnx.collarbone.v1', path: '/amount', value: 0});
  return {people, sourceId: f.sourceId, targetId: f.targetId, plan: {portrait_cohort: true,
    ...(collarbone ? {collarbone_cohort: true} : {}), persistent_association: review, association_source: rows[0], targets: rows.slice(1),
    module_scope: Object.keys(people.selection)}};
}
