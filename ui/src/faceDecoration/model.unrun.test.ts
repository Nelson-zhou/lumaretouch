// AUTHORED / UNRUN. These are source fixtures, not executed correctness or photographic evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {OP, CONTROL_ID, CONTROL_PATH, PATTERNS, neutral, check, patches, reading, access, targetReady,
  bindingKey, command, commandCurrent, referenceCurrent, proofValid, echoMatches, referenceReceiptValid,
  reviewReceiptValid, verifiedImage, type Fences} from './model.ts';
import {LIMITS, region, stroke} from './review.ts';
import {fixture, reference, receipt} from './fixture.unrun.test.ts';
const capability = {face_decoration_protocol: 1, face_decoration_available: true};
const fences: Fences = {enabled: true, pending: false, uncertain: false, blocked: false, faceOk: true};

test('exact handbook leaf has five original freckles and three original mole templates', () => {
  assert.equal(CONTROL_ID, 'LNX-REF-PC-32471-C-dd14134407'); assert.equal(CONTROL_PATH, '局部妆容/脸部装饰');
  assert.equal(PATTERNS.length, 8); assert.equal(PATTERNS.filter(p => p.kind === 'freckle').length, 5);
  assert.equal(PATTERNS.filter(p => p.kind === 'mole').length, 3); assert.equal(new Set(PATTERNS.map(p => p.id)).size, 8);
  assert.equal(new Set(PATTERNS.map(p => JSON.stringify(p.marks))).size, 8);
  assert.deepEqual(neutral(), {version: 1, pattern: 'freckle_dust', strength: 0});
  for (const pattern of PATTERNS) assert.equal(check({version: 1, pattern: pattern.id, strength: 1}).pattern, pattern.id);
});
test('strict non-AI recipe and leaf-only scoped writes never carry colour, pixels, support or consent', () => {
  for (const invalid of [-.01, 1.01, NaN, Infinity, '0', false, null]) assert.throws(() => check({...neutral(), strength: invalid}));
  for (const key of ['source', 'colour', 'region', 'reviewed', 'visible', 'version2']) assert.throws(() => check({...neutral(), [key]: 1}));
  assert.throws(() => check({...neutral(), pattern: 'apple'})); assert.throws(() => check({...neutral(), version: 2}));
  assert.deepEqual(patches({version: 1, pattern: 'mole_pair', strength: 0}, ['strength']), [
    {operation_id: OP, parameter_path: '/strength', unset: false, value: 0}]);
  assert.deepEqual(patches({version: 1, pattern: 'mole_pair', strength: .3}, ['pattern']), [
    {operation_id: OP, parameter_path: '/pattern', unset: false, value: 'mole_pair'}]);
});
test('authoritative selected face and both effective leaves must match the decoration report', () => {
  for (const mutate of [
    (v: ReturnType<typeof fixture>) => {v.binding.asset_sha256 = 'd'.repeat(64);},
    (v: ReturnType<typeof fixture>) => {v.face_decoration!.face_ref = {...v.face_decoration!.face_ref!, face_instance_id: 'face-b'};},
    (v: ReturnType<typeof fixture>) => {v.resolved!.state_revision++;},
    (v: ReturnType<typeof fixture>) => {v.resolved!.operations[OP]['/strength'].value = .4;},
    (v: ReturnType<typeof fixture>) => {delete v.resolved!.operations[OP];},
    (v: ReturnType<typeof fixture>) => {v.resolved!.conflicts.push({operation_id: OP, parameter_path: '/pattern', reason: 'conflict', target_ids: ['a','b']});},
  ]) {const v = fixture(); mutate(v); assert.equal(reading(v).recipe, null); assert.equal(access(v, capability, fences).changeDisabled, true);}
  const v = fixture(); v.editing_target = {scope: 'all_people', target_id: v.binding.asset_sha256, face_ref: null};
  v.editing_overrides[OP]['/strength'] = .8; assert.equal(reading(v).recipe?.strength, .3);
});
test('protocol/native/support/person fences are independent and zero recovery never clears another leaf', () => {
  const v = fixture(); assert.equal(access(v, capability, fences).changeDisabled, false);
  for (const key of ['pending','uncertain','blocked'] as const) {
    const a = access(v, capability, {...fences, [key]: true}); assert.equal(a.changeDisabled, true); assert.equal(a.resetDisabled, true); assert.equal(a.reviewDisabled, true);
  }
  assert.equal(access(v, undefined, fences).resetDisabled, true);
  for (const mutate of [(v: ReturnType<typeof fixture>) => {v.face_decoration!.native_available = false;},
    (v: ReturnType<typeof fixture>) => {v.face_decoration!.support_available = false; v.face_decoration!.support_reason = 'target-local support missing';},
    (v: ReturnType<typeof fixture>) => {v.face_decoration!.reviewed = false;},
    (v: ReturnType<typeof fixture>) => {v.faces[0].analysis_status = 'unresolved';},
  ]) {const value = fixture(); mutate(value); const a = access(value, capability, fences); assert.equal(a.changeDisabled, true); assert.equal(a.resetDisabled, false);}
  const a = access(v, {...capability, face_decoration_available: false, face_decoration_reason: 'ABI unavailable'}, fences);
  assert.equal(a.changeDisabled, true); assert.equal(a.reason, 'ABI unavailable'); assert.equal(a.resetDisabled, false);
});
test('shared scope is explicit; current-face painting cannot acknowledge a group/person/all target', () => {
  for (const scope of ['group','person','all_people'] as const) {
    const v = fixture(); v.editing_target = {scope, target_id: scope === 'all_people' ? v.binding.asset_sha256 : scope, face_ref: null};
    assert.equal(targetReady(v), true); assert.equal(access(v, capability, fences).reviewDisabled, true);
    assert.throws(() => reference(v)); v.editing_target.target_id = 'toString'; assert.equal(targetReady(v), false);
  }
});
test('each source, document, graph, face, analysis, association and scope change invalidates a captured reference', () => {
  const v = fixture(), req = reference(v), key = bindingKey(v); assert.equal(referenceCurrent(req, v), true);
  for (const mutate of [(x: typeof v) => {x.binding.document_id += 'b';}, (x: typeof v) => {x.binding.document_epoch += 'b';},
    (x: typeof v) => {x.binding.document_revision++;}, (x: typeof v) => {x.revision++;}, (x: typeof v) => {x.association_revision++;},
    (x: typeof v) => {x.selected_face_id = 'face-b';}, (x: typeof v) => {x.face_decoration!.landmark_digest = 'e'.repeat(64);},
    (x: typeof v) => {x.face_decoration!.source = {...x.face_decoration!.source, width: 8};},
    (x: typeof v) => {x.editing_target = {scope: 'all_people', target_id: x.binding.asset_sha256, face_ref: null};},
  ]) {const changed = structuredClone(v); mutate(changed); assert.notEqual(bindingKey(changed), key); assert.equal(referenceCurrent(req, changed), false);}
  assert.equal(commandCurrent(req, null), false);
});
test('reference is proof-only payload with a single report PNG and an exact echoed request', () => {
  const v = fixture(), req = reference(v), result = receipt(req, v);
  assert.equal(echoMatches(req, result), true); assert.equal(referenceReceiptValid(req, result), true);
  for (const mutate of [(r: typeof result) => {r.face_decoration_request!.target = {...req.target, target_id: 'other'};},
    (r: typeof result) => {r.face_decoration_request!.document_revision++;},
  ]) {const changed = structuredClone(result); mutate(changed); assert.equal(echoMatches(req, changed), false);}
  const duplicate = structuredClone(result); (duplicate.payload as Record<string, unknown>).source_preview = v.face_decoration!.source_preview;
  assert.equal(referenceReceiptValid(req, duplicate), false);
  const foreign = structuredClone(v.face_decoration!.reference_proof!); foreign.face_ref.asset_sha256 = 'd'.repeat(64);
  assert.equal(proofValid(foreign), false);
  const wrongRequest = structuredClone(result); wrongRequest.doc_state!.people!.face_decoration!.reference_proof!.reference_request_id = 'older';
  assert.equal(referenceReceiptValid(req, wrongRequest), false);
});
test('actual PNG bytes must match source proof before display, while dimensions are still independently decoded in the editor', async () => {
  const v = fixture(), r = v.face_decoration!;
  assert.equal((await verifiedImage(r.source_preview, r.reference_proof)).displayWidth, 2);
  await assert.rejects(verifiedImage({...r.source_preview!, base64: r.source_preview!.base64.replace('GMIA', 'GMIB')}, r.reference_proof));
  await assert.rejects(verifiedImage(r.source_preview, {...r.reference_proof!, preview_sha256: 'd'.repeat(64)}));
  await assert.rejects(verifiedImage({...r.source_preview!, source_width: 10}, r.reference_proof));
  await assert.rejects(verifiedImage({...r.source_preview!, mapping: 'cropped' as never}, r.reference_proof));
});
test('visible-skin review needs actual loaded image, nonempty add paint and all decoration-specific confirmations', () => {
  const source = {sha256: 'a'.repeat(64), width: 200, height: 100}, flags = {visible: true, unoccluded: true, owner: true};
  const one = stroke(source, 'add', 10, [.2,.3], 'stroke-one'), two = stroke(source, 'subtract', 5, [.5,.5], 'stroke-two');
  const value = region([one,two], true, flags); assert.equal(value.recipe.objects.length, 2);
  assert.deepEqual(value.recipe.objects[0].axes, [[10/199,0],[0,10/99]]); assert.notEqual(value.recipe.objects[0], one);
  assert.throws(() => region([one], false, flags)); assert.throws(() => region([], true, flags)); assert.throws(() => region([two], true, flags));
  for (const key of ['visible','unoccluded','owner'] as const) assert.throws(() => region([one], true, {...flags, [key]: false}));
  assert.throws(() => region(Array(LIMITS.strokes + 1).fill(one), true, flags));
  assert.throws(() => region([{...one, points: Array(LIMITS.pointsPerStroke + 1).fill([.1,.1])}], true, flags));
  assert.throws(() => stroke(source, 'add', 0, [.2,.3], 'bad')); assert.throws(() => stroke(source, 'add', 10, [-.2,.3], 'bad'));
});
test('review confirmation proves exact support pointer and graph advance, not a generic successful mutation', () => {
  const v = fixture(), proof = v.face_decoration!.reference_proof!;
  const req = command(v, 'face_decoration_review', 'review-request', {region: {}, reference_proof: proof});
  const next = structuredClone(v); next.revision++; next.face_decoration!.support_sha256 = 'd'.repeat(64);
  const result = receipt(req, next); result.payload = {kind: 'face_decoration_review', reference_proof: proof, support_sha256: 'd'.repeat(64)};
  assert.equal(reviewReceiptValid(req, result), true);
  next.face_decoration!.support_available = false; assert.equal(reviewReceiptValid(req, result), true); // Retained review is distinct from current semantic support.
  for (const mutate of [(r: typeof result) => {r.doc_state!.people!.revision--;},
    (r: typeof result) => {r.doc_state!.people!.face_decoration!.support_sha256 = 'e'.repeat(64);},
    (r: typeof result) => {(r.payload as {reference_proof: typeof proof}).reference_proof.preview_sha256 = 'f'.repeat(64);},
  ]) {const changed = structuredClone(result); mutate(changed); assert.equal(reviewReceiptValid(req, changed), false);}
});
