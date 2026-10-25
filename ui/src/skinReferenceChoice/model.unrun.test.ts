// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN. No product imports, tests, typecheck or build executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import type {PeopleResult} from '../people/model.ts';
import {BODY_OPERATION, choiceBinding, commandMatches, echoMatches, parseReport, receiptCurrent, validContext,
  validReceiptEnvelope, validRequest, type MeasuredCandidate} from './model.ts';
import {face, fixture, hash, result} from './fixtures.unrun.test.ts';

test('actual engine success envelope preserves all proof hashes and grants no consent', () => {
  const f = fixture(); assert.ok(validContext(f.context)); assert.ok(commandMatches(f.command, f.context));
  assert.ok(validReceiptEnvelope(f.command, f.result));
  const parsed = parseReport(f.report, f.command, f.context); assert.deepEqual(parsed, f.report); assert.notEqual(parsed, f.report);
  assert.equal(parsed!.grants_consent, false); assert.equal(parsed!.render_committed, false);
  assert.equal(parsed!.document_snapshot_sha256, f.report.document_snapshot_sha256);
  assert.ok(receiptCurrent(f.command, f.result as unknown as PeopleResult, f.context.view));
});
test('canonical success and compact native refusal are distinct from writes and uncertain outcomes', () => {
  const f = fixture(), {payload: _p, event: _event, created_id: _created, frame_emitted: _frame, batch_id: _batch, ...compact} = f.result;
  assert.ok(validReceiptEnvelope(f.command, {...compact, success: false, error: 'Source measurement refused'}));
  for (const changes of [{frame_emitted: true}, {frame: null}, {created_id: 'new-face'}, {batch_id: 'batch'},
    {doc_state: {people: f.context.view}}, {event: 'edit_result'}, {error: 'false success'}, {outcome_unknown: true},
    {grants_consent: true}, {request_id: 'later-request'}]) assert.equal(validReceiptEnvelope(f.command, {...f.result, ...changes}), false);
  assert.equal(validReceiptEnvelope(f.command, {...compact, payload: f.report}), false, 'success requires canonical no-write fields');
  assert.equal(validReceiptEnvelope(f.command, {...compact, success: false, error: 'refused', payload: f.report}), false);
  assert.ok(validReceiptEnvelope(f.command, {...result(f.command), payload_released: true}));
  assert.equal(validReceiptEnvelope(f.command, {...f.result, payload_released: true}), false);
});
test('omitted and explicit-null manual requests stay different in both exact echoes', () => {
  const f = fixture(); assert.ok(validRequest(f.command.payload));
  const explicit = {...f.command, payload: {...f.command.payload, manual_reference: null}};
  assert.ok(validRequest(explicit.payload)); assert.equal(echoMatches(explicit, f.result), false);
  assert.equal(parseReport(f.report, explicit, f.context), null);
  assert.ok(parseReport({...f.report, skin_reference_choice_request: explicit.payload}, explicit, f.context));
  assert.equal(validRequest({...f.command.payload, manual_reference: undefined}), false);
  assert.equal(validRequest({...f.command.payload, auto_confirm: true}), false);
});
test('both family catalogs are admitted, but body outer operation never changes the nested face measurement operation', () => {
  const f = fixture('body'); assert.ok(validContext(f.context)); assert.ok(parseReport(f.report, f.command, f.context));
  assert.equal(parseReport({...f.report, proposal: {...f.report.proposal, operation_id: BODY_OPERATION}}, f.command, f.context), null);
  assert.equal(parseReport({...f.report, family: 'face'}, f.command, f.context), null);
  assert.equal(commandMatches({...f.command, payload: {...f.command.payload, family: 'face'}}, f.context), false);
});
test('exact source image, request, original/creative precision, epoch and owner versions cannot be substituted', () => {
  const f = fixture();
  for (const changes of [{source_review_sha256: hash('0')}, {source_image_sha256: hash('0')}, {document_snapshot_sha256: ''},
    {source_pixels_sha256: hash('0')}, {revision: '8'}, {source: {...f.report.source, width: 15}},
    {source_proof: {...f.report.source_proof, original_sha256: hash('0')}},
    {skin_reference_choice_request: {...f.command.payload, manual_reference: face('b')}}])
    assert.equal(parseReport({...f.report, ...changes}, f.command, f.context), null);
  for (const changes of [{source_kind: 'creative', source_bits: 32}, {source_bits: '16'}, {source_encoding: 'encoded-srgb-f32-v1'},
    {state_revision: 6}, {association_revision: 3}])
    assert.equal(parseReport({...f.report, proposal: {...f.report.proposal, ...changes}}, f.command, f.context), null);
  const changed = {...f.context.view, binding: {...f.context.view.binding, document_epoch: 'new'}};
  assert.equal(receiptCurrent(f.command, f.result as unknown as PeopleResult, changed), false);
  assert.notEqual(choiceBinding({...f.context, view: changed}), choiceBinding(f.context));
});
test('complete candidate census, per-face evidence, source windows and native reliability bounds are enforced', () => {
  const f = fixture(), a = f.report.proposal.candidates[0] as MeasuredCandidate;
  for (const rows of [f.report.proposal.candidates.slice(0, 1), [a, a], [...f.report.proposal.candidates].reverse(),
    [{...a, face_ref: {...a.face_ref, analysis_revision: 4}}, f.report.proposal.candidates[1]],
    [{...a, source_window: [0, 9, 16, 8]}, f.report.proposal.candidates[1]],
    [{...a, landmark_digest: hash('0')}, f.report.proposal.candidates[1]],
    [{...a, protected_face_boxes: 0}, f.report.proposal.candidates[1]],
    [{...a, face_skin_observation: {...a.face_skin_observation, semantic_model_sha256: hash('0')}}, f.report.proposal.candidates[1]]])
    assert.equal(parseReport({...f.report, proposal: {...f.report.proposal, candidates: rows}}, f.command, f.context), null);
  for (const changes of [{robust_sample_count: 63}, {robust_weight: 63}, {effective_samples: 100.001},
    {retained_weight_fraction: 1.00001}, {retained_weight_fraction: .49}, {initial_log_luminance_mad: .501},
    {linear_luminance: .9}, {log_luminance: Infinity}]) {
    const rows = [{...a, measurement: {...a.measurement, ...changes}}, f.report.proposal.candidates[1]];
    assert.equal(parseReport({...f.report, proposal: {...f.report.proposal, candidates: rows}}, f.command, f.context), null);
  }
  const roundoff = {...a, measurement: {...a.measurement, robust_weight: 100.00005, effective_samples: 100.00005, retained_weight_fraction: 1.0000005}};
  assert.ok(parseReport({...f.report, proposal: {...f.report.proposal, candidates: [roundoff, f.report.proposal.candidates[1]]}}, f.command, f.context),
    'native admitted roundoff is retained unchanged, not clipped to exact count/one');
});
test('near ties require manual choice and IDs cannot fabricate a unique winner', () => {
  const f = fixture(), p = f.report.proposal, a = p.candidates[0] as MeasuredCandidate, b = p.candidates[1] as MeasuredCandidate;
  const tied = {...p, candidates: [a, {...b, measurement: {...b.measurement, log_luminance: a.measurement.log_luminance,
    linear_luminance: a.measurement.linear_luminance}}], top_log_luminance_gap: 0,
    reference_face_ref: null, selection_mode: 'none', automatic_status: 'blocked', automatic_reference_face_ref: null,
    automatic_blockers: ['brightest-measurements-too-close'], ambiguous_face_refs: [face('a'), face('b')]};
  assert.ok(parseReport({...f.report, proposal: tied}, f.command, f.context));
  assert.equal(parseReport({...f.report, proposal: {...tied, reference_face_ref: face('a'), automatic_reference_face_ref: face('a'),
    automatic_status: 'proposed', selection_mode: 'automatic-proposal'}}, f.command, f.context), null);
  const manual = {...f.command, payload: {...f.command.payload, manual_reference: face('b')}};
  assert.ok(parseReport({...f.report, skin_reference_choice_request: manual.payload,
    proposal: {...tied, reference_face_ref: face('b'), selection_mode: 'manual-override-proposal'}}, manual, f.context));
});
test('an unavailable enabled face is never silently removed to let another person win', () => {
  const f = fixture(), p = f.report.proposal;
  const partial = {...p, candidates: [p.candidates[0], {face_ref: face('b'), status: 'unavailable', reason: 'source-measurement-refused', detail: 'clipped source'}],
    ranked_face_refs: [face('a')], top_log_luminance_gap: null, reference_face_ref: null, selection_mode: 'none',
    automatic_status: 'blocked', automatic_reference_face_ref: null, automatic_blockers: ['enabled-face-measurement-unavailable']};
  assert.ok(parseReport({...f.report, proposal: partial}, f.command, f.context));
  assert.equal(parseReport({...f.report, proposal: {...partial, automatic_blockers: []}}, f.command, f.context), null);
  const manual = {...f.command, payload: {...f.command.payload, manual_reference: face('a')}};
  assert.ok(parseReport({...f.report, skin_reference_choice_request: manual.payload,
    proposal: {...partial, reference_face_ref: face('a'), selection_mode: 'manual-override-proposal'}}, manual, f.context));
});
test('authority flags, global census claims, hidden RGB/fit data and incomplete memory reservation fail closed', () => {
  const f = fixture();
  for (const changes of [{census_complete: true}, {body_extension_enabled: true}, {fit_retained: true}, {portable: true},
    {reference_face_exclusion_required: false}, {rgb: []}, {fit: {}}, {method: 'ai-confidence-ranking'}, {limitations: []}])
    assert.equal(parseReport({...f.report, proposal: {...f.report.proposal, ...changes}}, f.command, f.context), null);
  for (const changes of [{grants_consent: true}, {render_committed: true}, {source_image_load_required: false}, {review_required: false}])
    assert.equal(parseReport({...f.report, ...changes}, f.command, f.context), null);
  const {verification_workspace_bytes: _v, ...oldMemory} = f.report.memory;
  assert.equal(parseReport({...f.report, memory: oldMemory}, f.command, f.context), null);
  assert.equal(parseReport({...f.report, memory: {...f.report.memory, estimated_peak_bytes: 1}}, f.command, f.context), null);
  assert.ok(parseReport({...f.report, memory: {...f.report.memory, resident_input_bytes: 2 * 1024 ** 2,
    verification_workspace_bytes: 3 * 1024 ** 2, estimated_peak_bytes: 9 * 1024 ** 2}}, f.command, f.context),
    'historical helper allowance is not rewritten or rejected merely because final resident/reserve rose; actual admitted peak still fits');
  assert.ok(parseReport({...f.report, memory: {...f.report.memory, measurement_byte_budget: 14 * 1024 ** 2}}, f.command, f.context),
    'recovered live headroom may increase the historical measurement allowance above capture without changing actual admitted work');
  assert.equal(parseReport({...f.report, memory: {...f.report.memory, measurement_byte_budget: 17 * 1024 ** 2}}, f.command, f.context), null);
  const cycle: Record<string, unknown> = {...f.report}; cycle.extra = cycle;
  assert.equal(parseReport(cycle, f.command, f.context), null);
});
