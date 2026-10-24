// AUTHORED / UNRUN. Correlated mailbox fixtures, not execution evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPeopleWorkflow} from '../people/workflow.ts';
import type {PeopleAction, PeopleMailbox, PeopleResult} from '../people/model';
import {fixture, reference, receipt} from './fixture.unrun.test.ts';
import {command, OP, releasedReferenceReceiptValid, referenceReceiptValid} from './model.ts';

test('forged decoration echo holds the original request; checking never submits it twice', async () => {
  const view = fixture(), request = reference(view), result = receipt(request, view); let sent = 0, reads = 0;
  const wrong = structuredClone(result); wrong.face_decoration_request!.target.target_id = 'face-b';
  let currentResult = wrong;
  const flow = createPeopleWorkflow({send: async () => {sent++;}, read: async request_id => {
    reads++; return {phase: 'done', request_id, result: currentResult};}, refresh: async () => {}});
  flow.update(view, true); await assert.rejects(flow.submit(request));
  assert.equal(flow.snapshot().pending, true); assert.equal(flow.snapshot().uncertain, true); assert.equal(sent, 1);
  await assert.rejects(flow.submit({...request, request_id: 'do-not-resubmit'})); assert.equal(sent, 1);
  currentResult = result; await flow.check(); assert.equal(sent, 1); assert.equal(reads, 2);
  assert.equal(flow.snapshot().pending, false); assert.equal(flow.snapshot().uncertain, false);
});
test('missing PNG/proof cannot promote a generic success to a usable reference', async () => {
  const view = fixture(), request = reference(view), result = receipt(request, view);
  result.doc_state!.people = structuredClone(view); result.doc_state!.people!.face_decoration!.source_preview = null;
  const flow = createPeopleWorkflow({send: async () => {}, read: async request_id => ({phase: 'done', request_id, result}), refresh: async () => {}});
  flow.update(view, true); await assert.rejects(flow.submit(request)); assert.equal(flow.snapshot().uncertain, true);
});
test('a reference receipt after source navigation does not transplant the old person or source', async () => {
  const view = fixture(), request = reference(view), result = receipt(request, view); let sent = 0;
  let release!: (value: PeopleMailbox) => void, started!: () => void;
  const began = new Promise<void>(resolve => {started = resolve;});
  const flow = createPeopleWorkflow({send: async () => {sent++;}, read: request_id => new Promise(resolve => {release = resolve; started();}), refresh: async () => {}});
  flow.update(view, true); const waiting = flow.submit(request); await began;
  const other = structuredClone(view); other.binding.document_id = 'doc-b'; other.binding.document_epoch = 'epoch-b'; flow.update(other, true);
  release({phase: 'done', request_id: request.request_id, result}); await waiting;
  assert.equal(sent, 1); assert.equal(flow.snapshot().uncertain, false);
  assert.match(flow.snapshot().message, /原照片请求已确认/); assert.equal(other.binding.document_id, 'doc-b');
});
test('known refusal is terminal without retry; an unknown review remains locked across query', async () => {
  const view = fixture(); const request = command(view, 'face_decoration_review', 'review-request', {reference_proof: view.face_decoration!.reference_proof, region: {}});
  const failure = receipt(request, view); failure.success = false; failure.error = 'Target semantic support is missing'; delete failure.payload;
  let sent = 0, current = failure;
  const flow = createPeopleWorkflow({send: async () => {sent++;}, read: async request_id => ({phase: 'done', request_id, result: current}), refresh: async () => {}});
  flow.update(view, true); await assert.rejects(flow.submit(request)); assert.equal(flow.snapshot().uncertain, false); assert.equal(flow.snapshot().pending, false);
  current = {...failure, request_id: 'unknown-review', outcome_unknown: true};
  await assert.rejects(flow.submit({...request, request_id: 'unknown-review'}));
  assert.equal(flow.snapshot().uncertain, true); assert.equal(flow.snapshot().pending, true);
  await assert.rejects(flow.check()); assert.equal(sent, 2); // Second distinct user request, never replayed.
});
test('decoration review is not allowed to report an unrequested alias-shared batch', async () => {
  const view = fixture(), request = reference(view), result = {...receipt(request, view), batch_id: 'hidden-shared-batch'};
  const flow = createPeopleWorkflow({send: async () => {}, read: async request_id => ({phase: 'done', request_id, result}), refresh: async () => {}});
  flow.update(view, true); await assert.rejects(flow.submit(request)); assert.equal(flow.snapshot().uncertain, true);
});
test('scalar intent still uses the existing canonical people patch envelope', async () => {
  const view = fixture(); let captured: PeopleAction | undefined, finished!: () => void;
  const done = new Promise<void>(resolve => {finished = resolve;});
  const flow = createPeopleWorkflow({send: async request => {captured = request;}, read: async request_id => {
    const request = captured!, next = structuredClone(view); next.revision++; next.binding.document_revision++;
    const result: PeopleResult = {protocol: 1, request_id, action: 'patch', document_id: request.document_id,
      success: true, outcome_unknown: false, doc_state: {people: next}};
    return {phase: 'done', request_id, result};}, refresh: async () => {finished();}});
  flow.update(view, true); flow.patch([{operation_id: OP, parameter_path: '/strength', unset: false, value: 0}]); await done;
  assert.equal(captured!.action, 'patch'); assert.equal(captured!.document_revision, view.binding.document_revision);
  assert.deepEqual(captured!.target, view.editing_target); assert.deepEqual(captured!.payload, {patches: [{operation_id: OP, parameter_path: '/strength', unset: false, value: 0}]});
});

function released(request = reference()): PeopleResult {
  const {request_id: _id, ...echo} = request;
  return {event: 'people_result', protocol: 1, action: request.action, request_id: request.request_id,
    document_id: request.document_id, face_decoration_request: echo, success: true, outcome_unknown: false,
    error: null, created_id: null, batch_id: null, frame_emitted: false, payload_released: true} as unknown as PeopleResult;
}
test('exact expired reference releases only the completed read and requires a fresh image request', async () => {
  const view = fixture(), request = reference(view), terminal = released(request); let sent = 0;
  assert.equal(releasedReferenceReceiptValid(request, terminal), true);
  assert.equal(referenceReceiptValid(request, terminal), false); // Terminal success is not image or review authority.
  const flow = createPeopleWorkflow({send: async () => {sent++;}, read: async request_id => ({phase: 'done', request_id, result: terminal}), refresh: async () => {}});
  flow.update(view, true); await flow.submit(request);
  assert.equal(flow.snapshot().pending, false); assert.equal(flow.snapshot().uncertain, false);
  assert.equal(flow.snapshot().faceDecorationReleasedRequestId, request.request_id);
  assert.match(flow.snapshot().message, /重新读取当前人物原图/); await flow.check(); assert.equal(sent, 1);
});
test('expired-reference diagnostic cannot release a write, forged identity or uncertain/mutating outcome', async () => {
  const view = fixture(), request = reference(view);
  const bad: ((r: PeopleResult) => void)[] = [
    r => {r.outcome_unknown = true;}, r => {r.success = false;}, r => {r.request_id = 'foreign';},
    r => {r.face_decoration_request!.document_revision++;}, r => {r.doc_state = {people: view};},
    r => {r.payload = {};}, r => {r.batch_id = 'hidden-batch';},
    r => {(r as unknown as Record<string, unknown>).frame_emitted = true;},
    r => {(r as unknown as Record<string, unknown>).created_id = 'new-object';},
    r => {r.error = 'not an exact released read';},
  ];
  for (const mutate of bad) {
    const result = released(request); mutate(result); assert.equal(releasedReferenceReceiptValid(request, result), false);
    const flow = createPeopleWorkflow({send: async () => {}, read: async request_id => ({phase: 'done', request_id, result}), refresh: async () => {}});
    flow.update(view, true); await assert.rejects(flow.submit(request)); assert.equal(flow.snapshot().uncertain, true);
    assert.equal(flow.snapshot().pending, true); assert.equal(flow.snapshot().faceDecorationReleasedRequestId, null);
  }
  const write = command(view, 'face_decoration_review', 'write-request', {reference_proof: view.face_decoration!.reference_proof, region: {}});
  const result = released(write); assert.equal(releasedReferenceReceiptValid(write, result), false);
  const flow = createPeopleWorkflow({send: async () => {}, read: async request_id => ({phase: 'done', request_id, result}), refresh: async () => {}});
  flow.update(view, true); await assert.rejects(flow.submit(write)); assert.equal(flow.snapshot().uncertain, true);
});
