// AUTHORED / UNRUN. Wiring fixtures are not TypeScript, UI or runtime acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=(p:string)=>readFileSync(new URL(p,import.meta.url),'utf8');
test('retained current decoration uses full preset scope and mandatory exact image confirmation',()=>{
 const hook=read('../presets/usePresetWorkflow.ts'),flow=read('../presets/presetWorkflow.ts'),panel=read('../presets/PresetPanel.tsx');
 assert.ok(hook.includes('value.catalog?.face_decoration_review_required===true'));
 assert.ok(hook.includes("(value.catalog?.face_decoration_review_required===true||ops.includes(DECORATION_OP))?{moduleScope:[...ops]}"));
 assert.ok(flow.includes('verifyDecorationCoverage(frozen.face_decoration_preset.visual,frozen.face_decoration_preset.coverage)'));
 assert.ok(flow.includes('pending?.options.faceDecorationPresetAck!==undefined'));
 assert.ok(panel.includes('!w.decorationReady'));
});
test('all ordinary mapped targets need ordered image ACK while distinct eye/body ACKs remain required',()=>{
 const flow=read('../batch/batchWorkflow.ts'),panel=read('../batch/BatchReview.tsx');
 assert.ok(flow.includes('state.plan.face_decoration_visual_required===true'));
 assert.ok(flow.includes('sameDecorationAck(decorationSnapshot,decorationAck(targets.map'));
 assert.ok(flow.includes('validEyeBagBatchAck(eyeBagAckSnapshot'));
 assert.ok(flow.includes('validCollarboneAck(collarboneAckSnapshot'));
 assert.ok(flow.includes('request.decorationReviewSha==null'));
 assert.ok(flow.includes('result.face_decoration_batch_review.review_sha256!==request.decorationReviewSha'));
 assert.ok(panel.includes('decorationTargets.map(target=>'));
});
test('image display verifies coverage and decoded extents and never submits writes itself',()=>{
 const view=read('./TransferReview.tsx'),transport=read('./visualTransport.ts');
 assert.ok(view.includes('verifyDecorationCoverage(value,coverage)'));
 assert.ok(view.includes('image.naturalWidth===value[side].width'));
 assert.ok(view.includes('disabled={disabled||!ready}'));
 assert.ok(!view.includes('runPreset(')&&!view.includes('runBatch('));
 assert.ok(transport.includes('verifyCollarboneImage(r.image)'));
});
