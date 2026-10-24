// AUTHORED / UNRUN. Synthetic contracts only; no runtime, TypeScript or photo acceptance claimed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow, type BatchAction, type BatchOptions, type BatchReply, type BatchTransport} from '../batch/batchWorkflow';
import {portraitFixture} from './cohortFixture';
import {portraitCohortAck, portraitCohortTargets} from './model';
import {collarboneAck} from '../collarbone/transferModel';
import {collarboneCohortTargets} from '../collarbone/cohortModel';
function fixture(operation: 'create' | 'patch' | 'unlink' = 'create', named = true, collarbone = false,
  mutate: (reply: BatchReply) => void = () => {}) {
  const f = portraitFixture(operation, named, collarbone), token = 'f'.repeat(32), rows = [f.plan.association_source, ...f.plan.targets];
  const source = {document_id: f.sourceId, revision: '3', path: '/source.raw'};
  const calls: {action: BatchAction; options: BatchOptions}[] = [], replies = new Map<string, BatchReply>(); let count = 0, time = 0;
  const api: BatchTransport = {request: async (action, options) => {
    calls.push({action, options}); const id = options.requestId!;
    const outcomes = rows.map(row => ({...row, expected_revision: row.revision, result_revision: String(Number(row.revision) + 1), outcome: 'applied'}));
    const reply: BatchReply = action === 'preflight' ? {...f.plan, request_id: id, action, success: true, preflight_token: token, source_snapshot: source,
      people_transfer: true, policy: 'recheck', applies: f.people as unknown as Record<string, unknown>, rejected_docs: [], ok: 1, blocked: 0}
      : action === 'commit' ? {request_id: id, action, success: true, outcome_unknown: false, batch_id: 'portrait-batch', preflight_token: token,
        source_snapshot: source, module_scope: [...f.plan.module_scope], portrait_cohort: true, portrait_cohort_ack: options.portraitCohortAck?.map(row => ({...row})),
        ...(collarbone ? {collarbone_cohort: true, collarbone_review_ack: options.collarboneReviewAck?.map(row => ({...row}))} : {}),
        persistent_association: f.plan.persistent_association, source_outcome: outcomes[0], target_outcomes: outcomes.slice(1)}
      : {request_id: id, action, success: true, outcome_unknown: false, restored: [0, 1], conflicts: []};
    mutate(reply); replies.set(id, reply); return {requested: true};
  }, read: async id => ({phase: 'done', request_id: id, result: replies.get(id)})};
  const flow = createBatchWorkflow(api, () => {}, {uuid: () => `portrait-${++count}`, now: () => time, pause: async () => {time += 10;}, timeoutMs: 15});
  flow.updateContext({docs: [f.targetId], moduleScope: f.plan.module_scope, conflictPolicy: 'recheck', sourceDocumentId: f.sourceId,
    referencePath: source.path, enabled: true, label: 'portrait cohort', peopleTransfer: f.people, peopleProof: f.people.source});
  const ack = portraitCohortAck(portraitCohortTargets(f.plan).map(row => row.visual));
  const collarboneReview = collarbone ? collarboneAck(collarboneCohortTargets(f.plan).map(row => row.visual)) : undefined;
  const commit = (value = ack, collarboneValue = collarboneReview) => flow.commit(undefined, undefined, undefined, undefined, undefined, collarboneValue, undefined, value);
  return {...f, flow, api, calls, ack, commit, collarboneReview};
}
test('named cohort cannot commit target-only, wrong-order, foreign scope ACK or one-shot recipe ACK', async () => {
  const f = fixture(); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
  await f.commit(f.ack.slice(1)); assert.equal(f.calls.length, 1);
  await f.commit([...f.ack].reverse()); assert.equal(f.calls.length, 1);
  await f.flow.commit(undefined, undefined, undefined, undefined, undefined, undefined, f.ack as any); assert.equal(f.calls.length, 1);
  await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
  assert.deepEqual(f.calls[1].options.portraitCohortAck, f.ack); assert.deepEqual(f.calls[1].options.moduleScope, f.plan.module_scope);
});
test('generic subsequent patch and empty-scope unlink retain mandatory whole-cohort images', async () => {
  for (const operation of ['patch', 'unlink'] as const) {
    const f = fixture(operation, false); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
    await f.flow.commit(); assert.equal(f.calls.length, 1);
    await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
    assert.deepEqual(f.calls[1].options.moduleScope, operation === 'unlink' ? [] : ['lnx.face_size.v1']);
    assert.equal(f.flow.snapshot().plan?.applies.face_style, undefined);
  }
});
test('portrait and collarbone approvals coexist only as complete actual persistent cohorts', async () => {
  const f = fixture('patch', true, true); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
  await f.commit(f.ack, []); assert.equal(f.calls.length, 1);
  await f.commit(f.ack.slice(1)); assert.equal(f.calls.length, 1);
  await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
  assert.deepEqual(f.calls[1].options.collarboneReviewAck, f.collarboneReview);
  assert.deepEqual(f.calls[1].options.portraitCohortAck, f.ack);
});
test('missing marker, any member image or exact frozen scope rejects preflight before write', async () => {
  for (const change of [(r: any) => {delete r.portrait_cohort;}, (r: any) => {delete r.association_source.association.portrait_visual;},
    (r: any) => {delete r.targets[0].association.portrait_visual;}, (r: any) => {r.module_scope.reverse();},
    (r: any) => {r.association_source.path = '/other.raw';},
    (r: any) => {r.targets[0].association.portrait_visual.cohort_sha256 = 'a'.repeat(64);},
    (r: any) => {r.persistent_association.face_style = r.applies.face_style;}]) {
    const f = fixture('create', true, false, reply => {if (reply.action === 'preflight') change(reply);});
    await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'error'); assert.equal(f.calls.length, 1);
  }
});
test('tampered terminal scope, token, cohort, source, ACK, revision or null batch remains query-only', async () => {
  for (const change of [(r: any) => {r.module_scope = [];}, (r: any) => {r.preflight_token = '0'.repeat(32);},
    (r: any) => {delete r.portrait_cohort;}, (r: any) => {r.portrait_cohort_ack.reverse();},
    (r: any) => {r.portrait_cohort_ack[0].cohort_sha256 = 'a'.repeat(64);}, (r: any) => {delete r.source_outcome;},
    (r: any) => {r.source_outcome.result_revision = r.source_outcome.expected_revision;},
    (r: any) => {r.target_outcomes[0].result_revision = r.target_outcomes[0].expected_revision;},
    (r: any) => {r.batch_id = null;}, (r: any) => {delete r.outcome_unknown;}]) {
    const f = fixture('patch', true, false, reply => {if (reply.action === 'commit') change(reply);});
    await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'uncertain');
    f.flow.acknowledgeInspection(); assert.equal(f.flow.snapshot().phase, 'uncertain');
    await f.flow.start(); assert.equal(f.calls.length, 2);
  }
});
test('unknown commit and history operation query original identity without repeat publication', async () => {
  const f = fixture(); await f.flow.start(); const read = f.api.read;
  f.api.read = async id => ({phase: 'pending', request_id: id}); await f.commit();
  assert.equal(f.flow.snapshot().phase, 'uncertain'); assert.equal(f.flow.snapshot().queryOnly, true);
  f.flow.close(); f.api.read = read; await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.calls.length, 2);
  f.api.read = async id => ({phase: 'pending', request_id: id}); await f.flow.undo('portrait-batch');
  assert.equal(f.flow.snapshot().queryOnly, true); f.flow.acknowledgeInspection(); assert.equal(f.flow.snapshot().phase, 'uncertain');
  f.api.read = read; await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.calls.length, 3);
});
test('explicit canonical no-op preflight rejection never becomes a synthetic successful batch', async () => {
  const f = fixture('patch'); f.api.read = async id => ({phase: 'done', request_id: id, result: {request_id: id, action: 'preflight', success: false,
    outcome_unknown: false, error: 'association intent did not change'}});
  await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'error'); assert.equal(f.flow.snapshot().plan, null);
  await f.commit(); assert.equal(f.calls.length, 1);
});
