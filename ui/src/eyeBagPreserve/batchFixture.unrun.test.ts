// AUTHORED / UNRUN synthetic DTO fixture only. Does not render or demonstrate photo quality.
import {createHash} from 'node:crypto';
import {request, review, endpoint, targetId} from '../people/transferFixtureData.test';
import {visualFixture} from '../collarbone/transferFixture';
import {EYE_BAG_BATCH_OP, eyeBagBatchAck} from './batchModel';
export const canonical = (v: unknown): string => Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']'
  : v && typeof v === 'object' ? '{' + Object.keys(v).sort().map(key => JSON.stringify(key) + ':' + canonical((v as Record<string, unknown>)[key])).join(',') + '}'
  : JSON.stringify(v)!;
export const coverageDigest = (v: unknown) => createHash('sha256').update(canonical(v)).digest('hex');
export function eyeBatchFixture({count = 1, amount = .4, mixed = false, preserveOnly = false, replaceLegacy = false} = {}) {
  const people = request();
  people.selection = {[EYE_BAG_BATCH_OP]: preserveOnly ? ['/preserve'] : ['/amount', '/preserve'], 'lnx.deform.v1': ['/face_slim']};
  if (mixed) people.selection['lnx.collarbone.v1'] = ['/amount'];
  const ids = [targetId, 'c'.repeat(32)].slice(0, count);
  people.targets = ids.map(id => ({target: endpoint(id, 19), target_refs: structuredClone(people.targets[0].target_refs)}));
  people.eye_bag = {version: 1, targets: ids.map(document_id => ({document_id, replace_legacy: replaceLegacy}))};
  const evidence = ids.map(id => {
    const value = review(), owner = endpoint(id, 19);
    value.target_document = owner.document; value.target_owner = owner;
    value.parameters = [{operation_id: 'lnx.deform.v1', parameter_path: '/face_slim', value: .3},
      {operation_id: EYE_BAG_BATCH_OP, parameter_path: '/preserve', value: .8}];
    if (!preserveOnly) value.parameters.push({operation_id: EYE_BAG_BATCH_OP, parameter_path: '/amount', value: amount});
    value.eye_bag = {version: 1, replace_legacy: replaceLegacy};
    value.eye_bag_coverage = {version: 1, support_transfer: 'none', targets: value.target_refs.map(face_ref => ({face_ref,
      scope: amount === 0 ? 'neutral-no-effect' : 'target-reviewed-ridge', ridge_sha256: amount === 0 ? null : '8'.repeat(64), sides: amount === 0 ? [] : ['left', 'right']}))};
    value.eye_bag_visual = {...visualFixture(value), coverage_sha256: coverageDigest(value.eye_bag_coverage)};
    if (mixed) {
      value.parameters.push({operation_id: 'lnx.collarbone.v1', parameter_path: '/amount', value: 0});
      value.collarbone_coverage = {version: 1, support_transfer: 'none', targets: value.target_refs.map(face_ref => ({face_ref,
        scope: 'neutral-no-effect', body_review_sha256: null, clavicle_category: null, clavicle_sides: []}))};
      value.collarbone_visual = {...structuredClone(value.eye_bag_visual), coverage_sha256: coverageDigest(value.collarbone_coverage)};
    }
    return value;
  });
  return {people, evidence, ids, ack: eyeBagBatchAck(evidence)};
}
