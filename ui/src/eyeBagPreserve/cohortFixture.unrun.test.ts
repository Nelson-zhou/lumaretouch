// AUTHORED / UNRUN. Synthetic DTOs only, never photographic acceptance.
import {createHash} from 'node:crypto';
import {cohortFixture} from '../collarbone/cohortFixture';
import {faceStyleSelection} from '../faceStyle/batchModel';
import type {AssociationRequest, AssociationTarget} from '../people/associationProof';
import type {EyeBagCohortCoverage} from './cohortModel';
function canonical(v: any): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(key => JSON.stringify(key) + ':' + canonical(v[key])).join(',') + '}';
  return JSON.stringify(v);
}
export const cohortCoverageDigest = (v: unknown) => createHash('sha256').update(canonical(v)).digest('hex');
export function eyeCohortFixture(operation: AssociationRequest['operation'] = 'create', generic = false, mixed = false, retainedOnly = false) {
  const f = cohortFixture(operation), people: AssociationRequest = structuredClone(f.people);
  people.selection = operation === 'unlink' ? {} : generic ? {'lnx.deform.v1': ['/face_slim']} : {'lnx.eye_bags.v2': ['/amount', '/preserve']};
  if (mixed && operation !== 'unlink' && !generic) people.selection = {...people.selection, ...faceStyleSelection(), 'lnx.collarbone.v1': ['/amount']};
  const rows: AssociationTarget[] = [f.plan.association_source, ...f.plan.targets].map((row, index) => {
    const {collarbone_visual, collarbone_coverage, ...association} = row.association!;
    const coverage: EyeBagCohortCoverage = {version: 1, support_transfer: 'none', replace_legacy: index === 1, face_ref: association.ref,
      before: {scope: 'target-reviewed-ridge', ridge_sha256: String(index + 1).repeat(64), sides: ['left']},
      after: operation === 'unlink' ? {scope: 'neutral-no-effect', ridge_sha256: null, sides: []}
        : {scope: 'target-reviewed-ridge', ridge_sha256: String(index + 1).repeat(64), sides: ['left']}};
    const visual = {...collarbone_visual!, coverage_sha256: cohortCoverageDigest(coverage)};
    const {coverage_sha256: _, ...base} = visual;
    return {...row, association: {...association, eye_bag_cohort: coverage, eye_bag_cohort_visual: visual,
      ...(mixed ? {collarbone_visual, collarbone_coverage, portrait_visual: {...base, cohort_sha256: 'c'.repeat(64)}} : {})}};
  });
  people.eye_bag_cohort = {version: 1, members: rows.map((row, index) => ({document_id: row.document_id, replace_legacy: index === 1}))};
  const intent = retainedOnly ? [{op: 'lnx.deform.v1', path: '/face_slim', value: .2}]
    : [{op: 'lnx.eye_bags.v2', path: '/amount', value: .4}, {op: 'lnx.eye_bags.v2', path: '/preserve', value: 1}];
  if (generic && !retainedOnly && operation !== 'unlink') intent.push({op: 'lnx.deform.v1', path: '/face_slim', value: .2});
  if (mixed) {
    for (const [op, paths] of Object.entries(faceStyleSelection())) for (const path of paths) intent.push({op, path, value: .1});
    intent.push({op: 'lnx.collarbone.v1', path: '/amount', value: 0});
  }
  return {people, sourceId: f.sourceId, targetId: f.targetId, plan: {eye_bag_cohort: true,
    ...(mixed ? {collarbone_cohort: true, portrait_cohort: true} : {}),
    persistent_association: {...f.plan.persistent_association, intent}, association_source: rows[0], targets: rows.slice(1), module_scope: Object.keys(people.selection)}};
}
