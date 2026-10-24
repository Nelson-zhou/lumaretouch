// AUTHORED / UNRUN. Synthetic transport only; no build, runtime or image acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow, type BatchAction, type BatchOptions, type BatchReply, type BatchTransport, type BatchContext} from '../batch/batchWorkflow';
import {eyeBagCohortAck, eyeBagCohortTargets} from './cohortModel';
import {eyeCohortFixture} from './cohortFixture.unrun.test';
import {portraitCohortAck, portraitCohortTargets} from '../portraitCohort/model';
import {collarboneAck} from '../collarbone/transferModel';
import {collarboneCohortTargets} from '../collarbone/cohortModel';
function fixture(operation: 'create' | 'patch' | 'unlink' = 'create', mixed = false, mutate: (r: BatchReply) => void = () => {}) {
  const f = eyeCohortFixture(operation, operation !== 'create', mixed), rows = [f.plan.association_source, ...f.plan.targets];
  const token = 'f'.repeat(32), source = {document_id: f.sourceId, revision: '3', path: '/source.raw'};
  const calls: {action: BatchAction; options: BatchOptions}[] = [], replies = new Map<string, BatchReply>(); let seq = 0, time = 0;
  const api: BatchTransport = {request: async (action, options) => {
    calls.push({action, options}); const request_id = options.requestId!;
    const outcomes = rows.map(row => ({...row, expected_revision: row.revision, result_revision: String(Number(row.revision) + 1), outcome: 'applied'}));
    const result: BatchReply = action === 'preflight' ? {...structuredClone(f.plan), request_id, action, success: true, preflight_token: token,
      source_snapshot: source, people_transfer: true, applies: structuredClone(f.people) as unknown as Record<string, unknown>, policy: 'recheck', rejected_docs: [], ok: 1, blocked: 0}
      : action === 'commit' ? {request_id, action, success: true, outcome_unknown: false, batch_id: 'eye-cohort-batch', preflight_token: token,
        source_snapshot: source, module_scope: [...f.plan.module_scope], eye_bag_cohort: true, eye_bag_cohort_ack: structuredClone(options.eyeBagCohortAck),
        ...(mixed ? {portrait_cohort: true, portrait_cohort_ack: structuredClone(options.portraitCohortAck),
          collarbone_cohort: true, collarbone_review_ack: structuredClone(options.collarboneReviewAck)} : {}),
        persistent_association: f.plan.persistent_association, source_outcome: outcomes[0], target_outcomes: outcomes.slice(1)}
      : {request_id, action, success: true, outcome_unknown: false, batch_id: options.batchId, module_scope: ['lnx.people_graph.v1'], restored: [0, 1], conflicts: []};
    mutate(result); replies.set(request_id, result); return {requested: true};
  }, read: async request_id => ({phase: 'done', request_id, result: replies.get(request_id)})};
  const flow = createBatchWorkflow(api, () => {}, {uuid: () => `cohort-${++seq}`, now: () => time, pause: async () => {time += 10;}, timeoutMs: 15});
  const context: BatchContext = {docs: [f.targetId], sourceDocumentId: f.sourceId, referencePath: source.path, moduleScope: f.plan.module_scope,
    conflictPolicy: 'recheck', enabled: true, label: 'eye cohort', peopleTransfer: f.people, peopleProof: f.people.source, reviewEpoch: 0};
  flow.updateContext(context);
  const ack = eyeBagCohortAck(eyeBagCohortTargets(f.plan));
  const portrait = mixed ? portraitCohortAck(portraitCohortTargets(f.plan).map(row => row.visual)) : undefined;
  const clavicle = mixed ? collarboneAck(collarboneCohortTargets(f.plan).map(row => row.visual)) : undefined;
  const commit = (review = ack, p = portrait, c = clavicle) => flow.commit(undefined, undefined, undefined, undefined, undefined, c, undefined, p, undefined, review);
  return {...f, calls, replies, api, flow, ack, portrait, clavicle, commit, context};
}
test('create and retained generic patch/unlink require complete source-first ACK and preserve empty scope', async () => {
  for (const operation of ['create', 'patch', 'unlink'] as const) {
    const f = fixture(operation); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
    await f.flow.commit(); await f.commit(f.ack.slice(1)); await f.commit([...f.ack].reverse()); assert.equal(f.calls.length, 1);
    await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
    assert.deepEqual(f.calls[1].options.eyeBagCohortAck, f.ack); assert.deepEqual(f.calls[1].options.moduleScope, f.plan.module_scope);
    assert.equal(f.calls[1].options.peopleTransfer, undefined); assert.equal(f.calls[1].options.eyeBagReviewAck, undefined);
  }
});
test('mixed portrait/collarbone/eye cohort all remain mandatory over the identical full candidate', async () => {
  const f = fixture('patch', true); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
  await f.commit(f.ack, []); await f.commit(f.ack, f.portrait, []); assert.equal(f.calls.length, 1);
  await f.commit(); assert.equal(f.flow.snapshot().phase, 'done'); assert.deepEqual(f.calls[1].options.portraitCohortAck, f.portrait);
  assert.deepEqual(f.calls[1].options.collarboneReviewAck, f.clavicle);
});
test('missing source or target evidence, policy, either coverage side or marker rejects before mutation', async () => {
  for (const change of [(r: any) => {delete r.eye_bag_cohort;}, (r: any) => {delete r.applies.eye_bag_cohort;},
    (r: any) => {delete r.association_source.association.eye_bag_cohort_visual;},
    (r: any) => {delete r.targets[0].association.eye_bag_cohort.before;},
    (r: any) => {r.applies.eye_bag_cohort.members.reverse();}, (r: any) => {r.eye_bag_cohort_ack = [];}]) {
    const f = fixture('patch', false, r => {if (r.action === 'preflight') change(r);}); await f.flow.start();
    assert.equal(f.flow.snapshot().phase, 'error'); await f.commit(); assert.equal(f.calls.length, 1);
  }
});
test('scope, token, ACK, policy, source, missing outcome flag, null/noop or partial receipt stays query-only', async () => {
  for (const change of [(r: any) => {r.module_scope = [];}, (r: any) => {r.preflight_token = '0'.repeat(32);},
    (r: any) => {delete r.eye_bag_cohort_ack;}, (r: any) => {r.eye_bag_cohort_ack.reverse();},
    (r: any) => {r.eye_bag_cohort_ack[0].replace_legacy = true;}, (r: any) => {delete r.source_outcome;},
    (r: any) => {delete r.outcome_unknown;}, (r: any) => {r.batch_id = null;},
    (r: any) => {r.target_outcomes[0].outcome = 'noop';}, (r: any) => {r.target_outcomes[0].result_revision = '20';}]) {
    const f = fixture('patch', false, r => {if (r.action === 'commit') change(r);}); await f.flow.start(); await f.commit();
    assert.equal(f.flow.snapshot().phase, 'uncertain'); assert.equal(f.flow.snapshot().queryOnly, true);
    f.flow.acknowledgeInspection(); f.flow.close(); await f.flow.start(); await f.commit(); assert.equal(f.calls.length, 2);
  }
});
test('bad dual coverage digest cannot write; policy epochs and away/back cannot revive a read', async () => {
  const bad = fixture('patch', false, r => {if (r.action === 'preflight') (r.targets![0] as any).association.eye_bag_cohort_visual.coverage_sha256 = '0'.repeat(64);});
  await bad.flow.start(); bad.ack[1].coverage_sha256 = '0'.repeat(64); await bad.commit(); assert.equal(bad.calls.length, 1);
  const f = fixture(), read = f.api.read; f.api.read = async () => {throw Error('offline');}; await f.flow.start();
  f.flow.updateContext({...f.context, enabled: false}); f.flow.updateContext(f.context); f.api.read = read;
  await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'error'); await f.commit(); assert.equal(f.calls.length, 1);
  const p = fixture(); await p.flow.start(); p.flow.updateContext({...p.context, reviewEpoch: 2}); await p.commit(); assert.equal(p.calls.length, 1);
});
test('unknown writes and history query only the original identity through hide/context changes', async () => {
  const f = fixture(), read = f.api.read; await f.flow.start(); f.api.read = async id => ({phase: 'pending', request_id: id}); await f.commit();
  f.flow.close(); f.flow.updateContext({...f.context, enabled: false, reviewEpoch: 1}); f.flow.acknowledgeInspection(); await f.flow.start(); assert.equal(f.calls.length, 2);
  f.api.read = read; await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done');
  f.api.read = async id => ({phase: 'pending', request_id: id}); await f.flow.undo('eye-cohort-batch'); assert.equal(f.flow.snapshot().queryOnly, true);
  f.flow.acknowledgeInspection(); await f.flow.redo('eye-cohort-batch'); assert.equal(f.calls.length, 3);
  f.api.read = read; await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done');
});
test('closing or changing policy while digest work is pending never publishes and clicks cannot duplicate', async t => {
  const f = fixture(); await f.flow.start(); const original = crypto.subtle.digest.bind(crypto.subtle);
  const waits: (() => void)[] = []; t.mock.method(crypto.subtle, 'digest', (...args: Parameters<SubtleCrypto['digest']>) => new Promise<ArrayBuffer>(resolve => {
    waits.push(() => {void original(...args).then(resolve);});
  }));
  const first = f.commit(), second = f.commit(); f.flow.close(); for (const release of waits) release(); await Promise.all([first, second]); assert.equal(f.calls.length, 1);
});
test('canonical identical-intent refusal is a pre-write error, never synthetic success', async () => {
  const f = fixture('patch'); f.api.read = async request_id => ({phase: 'done', request_id, result: {request_id, action: 'preflight', success: false,
    outcome_unknown: false, error: 'association intent did not change'}});
  await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'error'); assert.equal(f.calls.length, 1);
});
