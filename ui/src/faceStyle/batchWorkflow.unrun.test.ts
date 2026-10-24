// AUTHORED / UNRUN. Synthetic queue receipts only. No product, imports or tests executed while authoring.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createBatchWorkflow, type BatchAction, type BatchContext, type BatchOptions, type BatchReply, type BatchTransport} from '../batch/batchWorkflow';
import {request, review, endpoint, sourceId, targetId} from '../people/transferFixtureData.test';
import {visualFixture} from '../collarbone/transferFixture';
import {faceStyleSelection, faceStyleBatchAck} from './batchModel';
import type {FaceStyleRecipe} from './model';

function fixture(mutate: (reply: BatchReply) => void = () => {}, count = 1) {
  const recipe: FaceStyleRecipe = {version: 1, style: 'classic', amount: 0};
  const bytes = Buffer.alloc(8); bytes.writeDoubleBE(0);
  const digestBytes = createHash('sha256').update('lumaretouch.face-style.v1\0classic\0').update(bytes).digest();
  const people = {...request(), selection: faceStyleSelection(), face_style: recipe};
  const ids = [targetId, 'c'.repeat(32)].slice(0, count);
  people.targets = ids.map(id => ({target: endpoint(id, 19), target_refs: structuredClone(people.targets[0].target_refs)}));
  const evidence = ids.map(id => {
    const value = review(), owner = endpoint(id, 19); value.target_document = owner.document; value.target_owner = owner;
    value.face_style = {...recipe};
    value.parameters = Object.entries(people.selection).flatMap(([operation_id, paths]) => paths.map(parameter_path => ({
      operation_id, parameter_path, value: parameter_path.endsWith('/linked') ? true : 0})));
    const {coverage_sha256: _, ...visual} = visualFixture(value);
    value.face_style_visual = {...visual, recipe_sha256: digestBytes.toString('hex')}; return value;
  });
  const source = {document_id: sourceId, revision: '3', path: '/source.raw'};
  const targets = ids.map((id, index) => ({document_id: id, revision: '20', index: index + 1, path: `/target-${index}.raw`, blocked: null}));
  const calls: {action: BatchAction; options: BatchOptions}[] = [], replies = new Map<string, BatchReply>(); let seq = 0, time = 0;
  const api: BatchTransport = {request: async (action, options) => {
    calls.push({action, options}); const id = options.requestId!;
    const reply: BatchReply = action === 'preflight' ? {request_id: id, action, success: true, preflight_token: 'f'.repeat(32),
      source_snapshot: source, module_scope: Object.keys(people.selection), applies: people, policy: 'recheck',
      targets: targets.map((target, index) => ({...target, people_transfer: evidence[index]})), rejected_docs: [], ok: count, blocked: 0, people_transfer: true}
      : action === 'commit' ? {request_id: id, action, success: true, outcome_unknown: false, preflight_token: 'f'.repeat(32), batch_id: 'named-batch',
        source_snapshot: source, module_scope: Object.keys(people.selection), face_style_review_ack: structuredClone(options.faceStyleReviewAck),
        target_outcomes: targets.map(target => ({...target, expected_revision: '20', current_revision: '20', result_revision: '21', outcome: 'applied'}))}
      : {request_id: id, action, success: true, outcome_unknown: false, batch_id: options.batchId, restored: [1], conflicts: []};
    mutate(reply); replies.set(id, reply); return {requested: true};
  }, read: async id => ({phase: 'done', request_id: id, result: replies.get(id)})};
  const flow = createBatchWorkflow(api, () => {}, {uuid: () => `named-${++seq}`, now: () => time, pause: async () => {time += 10;}, timeoutMs: 15});
  const context: BatchContext = {docs: ids, moduleScope: Object.keys(people.selection), conflictPolicy: 'recheck', sourceDocumentId: sourceId,
    enabled: true, label: 'named face style', peopleTransfer: people, peopleProof: people.source};
  flow.updateContext(context);
  const ack = faceStyleBatchAck(evidence.map(value => value.face_style_visual!));
  const commit = () => flow.commit(undefined, undefined, undefined, undefined, undefined, undefined, ack);
  return {flow, api, context, calls, replies, evidence, ack, commit, digestBytes};
}
test('zero recipe requires exact per-target ACK and sends only token plus captured acknowledgment', async () => {
  const f = fixture(); await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review');
  await f.flow.commit(); assert.equal(f.calls.length, 1);
  await f.commit(); assert.equal(f.flow.snapshot().phase, 'done');
  assert.deepEqual(f.calls[1].options.faceStyleReviewAck, f.ack); assert.notEqual(f.calls[1].options.faceStyleReviewAck, f.ack);
  assert.deepEqual(Object.keys(f.calls[1].options).sort(), ['faceStyleReviewAck', 'preflightToken', 'requestId']);
});
test('partial selection, mismatched recipe, missing image or injected coverage cannot reach review', async () => {
  for (const mutate of [(r: any) => {r.applies.selection['lnx.face_size.v1'].push('/mask');},
    (r: any) => {r.targets[0].people_transfer.face_style.amount = .5;},
    (r: any) => {delete r.targets[0].people_transfer.face_style_visual;},
    (r: any) => {r.targets[0].people_transfer.face_style_visual.coverage_sha256 = 'a'.repeat(64);}]) {
    const f = fixture(r => {if (r.action === 'preflight') mutate(r);}); await f.flow.start();
    assert.equal(f.flow.snapshot().phase, 'error'); await f.commit(); assert.equal(f.calls.length, 1);
  }
});
test('recipe digest mismatch blocks mutation even if all shape fields and PNG acknowledgments match', async () => {
  const f = fixture(r => {if (r.action === 'preflight') (r.targets![0] as any).people_transfer.face_style_visual.recipe_sha256 = 'a'.repeat(64);});
  await f.flow.start(); assert.equal(f.flow.snapshot().phase, 'review'); f.ack[0].recipe_sha256 = 'a'.repeat(64);
  await f.commit(); assert.equal(f.calls.length, 1);
  assert.equal(f.flow.snapshot().phase, 'review');
});
test('no-op null batch identity and unchanged revisions resolve rather than becoming permanently uncertain', async () => {
  const f = fixture(r => {if (r.action === 'commit') {r.batch_id = null; for (const row of r.target_outcomes!) row.result_revision = '20';}}, 2);
  await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.flow.snapshot().result?.batch_id, null);
  const mixed = fixture(r => {if (r.action === 'commit') r.target_outcomes![0].result_revision = '20';}, 2);
  await mixed.flow.start(); await mixed.commit(); assert.equal(mixed.flow.snapshot().phase, 'done');
  const invalid = fixture(r => {if (r.action === 'commit') r.batch_id = null;});
  await invalid.flow.start(); await invalid.commit(); assert.equal(invalid.flow.snapshot().phase, 'uncertain');
});
test('missing or changed terminal recipe ACK retains the exact original write identity', async () => {
  const f = fixture(r => {if (r.action === 'commit') delete r.face_style_review_ack;});
  await f.flow.start(); await f.commit(); assert.equal(f.flow.snapshot().phase, 'uncertain');
  f.flow.acknowledgeInspection(); assert.equal(f.flow.snapshot().phase, 'uncertain');
  f.flow.close(); await f.flow.start(); await f.commit(); assert.equal(f.calls.length, 2);
  const original = f.calls[1].options.requestId!; f.replies.get(original)!.face_style_review_ack = structuredClone(f.ack);
  await f.flow.query(); assert.equal(f.flow.snapshot().phase, 'done'); assert.equal(f.calls.length, 2);
});
test('known named-batch undo remains query-only on an unknown receipt', async () => {
  const f = fixture(r => {if (r.action === 'undo') {r.success = false; r.outcome_unknown = true;}});
  await f.flow.start(); await f.commit(); await f.flow.undo('named-batch'); assert.equal(f.flow.snapshot().phase, 'uncertain');
  assert.equal(f.flow.snapshot().queryOnly, true); f.flow.acknowledgeInspection(); assert.equal(f.flow.snapshot().phase, 'uncertain');
  await f.flow.redo('named-batch'); assert.equal(f.calls.length, 3);
});
test('closing while asynchronous recipe digest is pending invalidates the write', async t => {
  const f = fixture(); await f.flow.start();
  let release!: (value: ArrayBuffer) => void;
  const wait = new Promise<ArrayBuffer>(resolve => {release = resolve;});
  t.mock.method(crypto.subtle, 'digest', () => wait);
  const committing = f.commit(); f.flow.close(); release(Uint8Array.from(f.digestBytes).buffer);
  await committing; assert.equal(f.calls.length, 1); assert.equal(f.flow.snapshot().phase, 'closed');
});
test('context replacement while digest is pending cannot submit the older plan', async t => {
  const f = fixture(); await f.flow.start(); let release!: (value: ArrayBuffer) => void;
  t.mock.method(crypto.subtle, 'digest', () => new Promise<ArrayBuffer>(resolve => {release = resolve;}));
  const committing = f.commit(); f.flow.updateContext({...f.context, enabled: false});
  release(Uint8Array.from(f.digestBytes).buffer); await committing; assert.equal(f.calls.length, 1);
});
test('double clicks and caller ACK mutation during digest cannot duplicate or change the captured write', async t => {
  const f = fixture(); await f.flow.start(); let release!: (value: ArrayBuffer) => void;
  const wait = new Promise<ArrayBuffer>(resolve => {release = resolve;}); t.mock.method(crypto.subtle, 'digest', () => wait);
  const expected = structuredClone(f.ack), first = f.commit(), second = f.commit();
  f.ack[0].after_sha256 = '0'.repeat(64); release(Uint8Array.from(f.digestBytes).buffer);
  await Promise.all([first, second]); assert.equal(f.calls.length, 2); assert.deepEqual(f.calls[1].options.faceStyleReviewAck, expected);
  assert.equal(f.flow.snapshot().phase, 'done');
});
