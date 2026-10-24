// AUTHORED / UNRUN. Synthetic queue and digest fixtures, not execution or photographic acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow, type BatchAction, type BatchContext, type BatchOptions, type BatchReply, type BatchTransport} from '../batch/batchWorkflow';
import {collarboneAck} from '../collarbone/transferModel';
import {eyeBatchFixture} from './batchFixture.unrun.test';
function fixture(mutate: (reply: BatchReply) => void = () => {}, mixed = false, count = 1) {
  const f = eyeBatchFixture({mixed, count}), source = {document_id: f.people.source.document.document_id, revision: '3', path: '/source.raw'};
  const targets = f.ids.map((document_id, index) => ({document_id, revision: '20', index: index + 1, path: `/target-${index}.raw`, blocked: null}));
  const calls: {action: BatchAction; options: BatchOptions}[] = [], replies = new Map<string, BatchReply>(); let seq = 0, time = 0;
  const api: BatchTransport = {request: async (action, options) => {
    calls.push({action, options}); const request_id = options.requestId!;
    const reply: BatchReply = action === 'preflight' ? {request_id, action, success: true, preflight_token: 'f'.repeat(32),
      source_snapshot: source, module_scope: Object.keys(f.people.selection), applies: structuredClone(f.people), policy: 'recheck',
      targets: targets.map((target, index) => ({...target, people_transfer: structuredClone(f.evidence[index])})), rejected_docs: [], ok: count, blocked: 0, people_transfer: true}
      : action === 'commit' ? {request_id, action, success: true, outcome_unknown: false, preflight_token: 'f'.repeat(32), batch_id: 'eye-batch',
        source_snapshot: source, module_scope: Object.keys(f.people.selection), eye_bag_review_ack: structuredClone(options.eyeBagReviewAck),
        ...(options.collarboneReviewAck ? {collarbone_review_ack: structuredClone(options.collarboneReviewAck)} : {}),
        target_outcomes: targets.map(target => ({...target, expected_revision: '20', current_revision: '20', result_revision: '21', outcome: 'applied'}))}
      : {request_id, action, success: true, outcome_unknown: false, batch_id: options.batchId, module_scope: ['lnx.people_graph.v1'], restored: [1], conflicts: []};
    mutate(reply); replies.set(request_id, reply); return {requested: true};
  }, read: async id => ({phase: 'done', request_id: id, result: replies.get(id)})};
  const flow = createBatchWorkflow(api, () => {}, {uuid: () => `eye-${++seq}`, now: () => time, pause: async () => {time += 10;}, timeoutMs: 15});
  const context: BatchContext = {docs: f.ids, moduleScope: Object.keys(f.people.selection), conflictPolicy: 'recheck', sourceDocumentId: source.document_id,
    enabled: true, label: 'eye-bag full mixed review', peopleTransfer: f.people, peopleProof: f.people.source, reviewEpoch: 0};
  flow.updateContext(context);
  const clavicle = mixed ? collarboneAck(f.evidence.map(value => value.collarbone_visual!)) : undefined;
  const commit = () => flow.commit(undefined, undefined, undefined, undefined, undefined, clavicle, undefined, undefined, f.ack);
  return {...f, flow, api, context, calls, replies, commit, clavicle};
}
test('review requires each policy and target evidence, rejects omission rather than dropping selected effects', async () => {
  for (const mutate of [(r: any) => {delete r.applies.eye_bag;}, (r: any) => {r.applies.eye_bag.targets[0].replace_legacy = true;},
    (r: any) => {delete r.targets[0].people_transfer.eye_bag_visual;},
    (r: any) => {r.targets[0].people_transfer.parameters = r.targets[0].people_transfer.parameters.filter((p: any) => p.operation_id !== 'lnx.deform.v1');},
    (r: any) => {r.targets[0].people_transfer.eye_bag_coverage.targets[0].sides = [];},
    (r: any) => {r.eye_bag_review_ack = [];},
    (r: any) => {r.targets[0].people_transfer.eye_bag.replace_legacy = true;}]) {
    const f = fixture(r => {if (r.action === 'preflight') mutate(r);}); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'error');
    await f.commit(); assert.equal(f.calls.length, 1);
  }
});
test('mixed eye and collarbone send both ordered ACK families without any donor support or writable scope payload', async () => {
  const f = fixture(() => {}, true, 2); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
  await f.flow.commit(); assert.equal(f.calls.length, 1);
  await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
  assert.deepEqual(f.calls[1].options.eyeBagReviewAck, f.ack); assert.deepEqual(f.calls[1].options.collarboneReviewAck, f.clavicle);
  assert.deepEqual(Object.keys(f.calls[1].options).sort(), ['collarboneReviewAck', 'eyeBagReviewAck', 'preflightToken', 'requestId']);
});
test('wrong coverage digest or stale policy ACK cannot trigger a write', async () => {
  const f = fixture(r => {if (r.action === 'preflight') (r.targets![0] as any).people_transfer.eye_bag_visual.coverage_sha256 = '0'.repeat(64);});
  await f.flow.start(); f.ack[0].coverage_sha256 = '0'.repeat(64); await f.commit(); assert.equal(f.calls.length, 1);
  const other = fixture(); await other.flow.start(); other.ack[0].replace_legacy = true; await other.commit(); assert.equal(other.calls.length, 1);
});
test('no-op null batch and unchanged target revisions are terminal without inventing an undo batch', async () => {
  const f = fixture(r => {if (r.action === 'commit') {r.batch_id = null; for (const row of r.target_outcomes!) {row.outcome = 'noop'; row.result_revision = '20';}}}, false, 2);
  await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.flow.snapshot().result!.batch_id, null);
  const bad = fixture(r => {if (r.action === 'commit') {r.target_outcomes![0].outcome = 'noop'; r.target_outcomes![0].result_revision = '21';}});
  await bad.flow.start(); await bad.commit(); assert.equal(bad.flow.snapshot().phase, 'uncertain');
});
test('missing, reordered, policy-changed ACK or changed mixed scope keeps original write query-only', async () => {
  for (const mutate of [(r: BatchReply) => {delete r.eye_bag_review_ack;},
    (r: BatchReply) => {r.eye_bag_review_ack!.reverse();},
    (r: BatchReply) => {r.eye_bag_review_ack![0].replace_legacy = true;},
    (r: BatchReply) => {r.module_scope = ['lnx.eye_bags.v2'];}]) {
    const f = fixture(r => {if (r.action === 'commit') mutate(r);}, false, 2);
    await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'uncertain'); assert.equal(f.flow.snapshot().queryOnly, true);
    f.flow.acknowledgeInspection(); f.flow.close(); await f.flow.start(); await f.commit(); assert.equal(f.calls.length, 2);
    const reply = f.replies.get(f.calls[1].options.requestId!)!; reply.eye_bag_review_ack = structuredClone(f.ack); reply.module_scope = [...f.context.moduleScope];
    await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.calls.length, 2);
  }
});
test('away and back while preflight read is unknown never revives its old review', async () => {
  const f = fixture(), read = f.api.read; f.api.read = async () => {throw Error('read disconnected');};
  await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'uncertain');
  f.flow.updateContext({...f.context, enabled: false}); f.flow.updateContext(f.context);
  f.api.read = read; await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'error'); assert.equal(f.flow.snapshot().plan, null);
  await f.commit(); assert.equal(f.calls.length, 1);
});
test('policy false to true to false epoch cannot revive a frozen review', async () => {
  const f = fixture(); await f.flow.start();
  f.flow.updateContext({...f.context, reviewEpoch: 2}); await f.commit(); assert.equal(f.calls.length, 1);
  assert.equal(f.flow.snapshot().phase, 'closed');
});
test('navigation and policy changes never abandon or replay an unknown write', async () => {
  const f = fixture(r => {if (r.action === 'commit') delete r.eye_bag_review_ack;}); await f.flow.start(); await f.commit();
  f.flow.updateContext({...f.context, enabled: false, reviewEpoch: 1}); f.flow.updateContext({...f.context, reviewEpoch: 2});
  f.flow.acknowledgeInspection(); await f.flow.start(); await f.commit(); assert.equal(f.calls.length, 2);
  const id = f.calls[1].options.requestId!; f.replies.get(id)!.eye_bag_review_ack = structuredClone(f.ack);
  await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.calls.length, 2);
});
test('closing during asynchronous coverage verification cannot submit', async t => {
  const f = fixture(); await f.flow.start(); let release!: (value: ArrayBuffer) => void;
  t.mock.method(crypto.subtle, 'digest', () => new Promise<ArrayBuffer>(resolve => {release = resolve;}));
  const pending = f.commit(); f.flow.close(); release(Uint8Array.from(Buffer.from(f.ack[0].coverage_sha256, 'hex')).buffer);
  await pending; assert.equal(f.calls.length, 1); assert.equal(f.flow.snapshot().phase, 'closed');
});
test('double clicks and ACK mutation during coverage verification cannot duplicate or change the write', async t => {
  const f = fixture(() => {}, true); await f.flow.start(); let release!: (value: ArrayBuffer) => void;
  const wait = new Promise<ArrayBuffer>(resolve => {release = resolve;}); t.mock.method(crypto.subtle, 'digest', () => wait);
  const ack = structuredClone(f.ack), clavicle = structuredClone(f.clavicle), first = f.commit(), second = f.commit();
  f.ack[0].replace_legacy = true; f.clavicle![0].after_sha256 = '0'.repeat(64);
  release(Uint8Array.from(Buffer.from(ack[0].coverage_sha256, 'hex')).buffer); await Promise.all([first, second]);
  assert.equal(f.calls.length, 2); assert.deepEqual(f.calls[1].options.eyeBagReviewAck, ack); assert.deepEqual(f.calls[1].options.collarboneReviewAck, clavicle);
});
test('known eye batch undo preserves query-only tracking on uncertain or wrong batch receipt', async () => {
  const f = fixture(r => {if (r.action === 'undo') {r.success = false; r.outcome_unknown = true;}});
  await f.flow.start(); await f.commit(); await f.flow.undo('eye-batch'); assert.equal(f.flow.snapshot().phase, 'uncertain');
  assert.equal(f.flow.snapshot().queryOnly, true); f.flow.acknowledgeInspection(); await f.flow.redo('eye-batch'); assert.equal(f.calls.length, 3);
});
