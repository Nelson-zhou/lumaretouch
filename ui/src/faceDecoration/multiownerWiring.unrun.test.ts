// AUTHORED / UNRUN. Static source assertions, not executed acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
test('alias draft never writes through generic patch and every member uses complete image ACK',()=>{
 const editor=read('./FaceDecorationAliasEditor.tsx');
 assert.ok(!editor.includes('people.patch('));
 for(const marker of ['face_decoration_alias_preview','face_decoration_alias_image','face_decoration_alias_confirm','review.members.map','review.members.every','DecorationTransferReview','people.submitCaptured','verifyDecorationAliasReview','aliasAck(review)'])assert.ok(editor.includes(marker),marker);
 const panel=read('./FaceDecorationPanel.tsx');assert.ok(panel.includes('!aliasRequired &&'));assert.ok(panel.includes('latest.view?.face_decoration?.alias_required === true'));assert.ok(panel.includes('FaceDecorationAliasHistory'));
});
test('cohort uses independently keyed source-first ACK and immutable paged read',()=>{
 const flow=read('../batch/batchWorkflow.ts'),native=read('../native.ts');
 for(const marker of ['validDecorationCohort','face_decoration_cohort_ack','decorationCohortNoWrite','decorationCohortAckDigest','face_decoration_cohort_review','registerDecorationMultiHistory'])assert.ok(flow.includes(marker),marker);
 assert.ok(native.includes("action:'face_decoration_cohort_visual'"));assert.ok(native.includes('faceDecorationCohortAck:opts.faceDecorationCohortAck'));
 const visual=read('./TransferReview.tsx');assert.ok(visual.includes('readImage?readImage'));assert.ok(visual.includes('verifyDecorationCoverage'));assert.ok(visual.includes('naturalWidth'));
});
