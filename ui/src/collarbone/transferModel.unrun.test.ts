// AUTHORED / UNRUN: no test runner, imports, UI, typecheck or build executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {review} from '../people/transferFixtureData.test';
import {visualFixture} from './transferFixture';
import {validCollarboneVisual,validCollarboneImageMetadata,collarboneAck,validCollarboneAck,collarboneReviewKey,collarboneImagesReady,verifyCollarboneImage} from './transferModel';
test('complete actual-target DTO permits original source and binds exact document/revision/source',()=>{
 const r=review(),v=visualFixture(r);assert.equal(validCollarboneVisual(v,r),true);
 for(const patch of [{document_id:'x'},{revision:'999'},{source_proof:{...v.source_proof,asset_sha256:'a'.repeat(64)}},{coverage_sha256:'x'},{before_state_sha256:null}])assert.equal(validCollarboneVisual({...v,...patch},r),false);
});
test('malformed, oversized, aspect-mismatched or unknown-property images refuse',()=>{
 const r=review(),v=visualFixture(r);
 for(const patch of [{width:1025},{height:0},{base64:'bad'},{sha256:'bad'},{copied_source:true}])assert.equal(validCollarboneImageMetadata({...v.before,...patch}),false);
 assert.equal(validCollarboneVisual({...v,before:{...v.before,width:100,height:1}},r),false);
});
test('token, request, source, coverage and image identities cannot reuse acknowledgment',()=>{
 const v=visualFixture(review()),key=collarboneReviewKey('token:request',v),ready={[key]:true};
 assert.equal(collarboneImagesReady('token:request',[v],ready),true);
 assert.equal(collarboneImagesReady('other:request',[v],ready),false);
 assert.equal(collarboneImagesReady('token:other',[v],ready),false);
 assert.equal(collarboneImagesReady('token:request',[{...v,coverage_sha256:'a'.repeat(64)}],ready),false);
 assert.equal(collarboneImagesReady('token:request',[undefined],ready),false);
});
test('ack is exact ordered PNG pair and coverage, never duplicated or partial',()=>{
 const v=visualFixture(review()),ack=collarboneAck([v]);assert.equal(validCollarboneAck(ack,[v]),true);
 assert.equal(validCollarboneAck([],[v]),false);assert.equal(validCollarboneAck([...ack,...ack],[v,v]),false);
 for(const field of ['document_id','revision','before_sha256','after_sha256','coverage_sha256'])assert.equal(validCollarboneAck([{...ack[0],[field]:'wrong'}],[v]),false);
});
test('synthetic hash is not accepted as verified image bytes',async()=>{assert.equal(await verifyCollarboneImage({...visualFixture(review()).before,base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jGq0AAAAASUVORK5CYII='}),false);});
test('actual display gates checkbox on hashes, load dimensions and coverage',()=>{
 const s=readFileSync(new URL('./CollarboneTransferReview.tsx',import.meta.url),'utf8');
 for(const fragment of ['verifyCollarboneCoverage(value,coverage)','image.naturalWidth===expected.width','disabled={disabled||!ready}','key={props.reviewKey}','setViewed({key:reviewKey,checked:false})','maxWidth:zoom?'])assert.ok(s.includes(fragment));
});
test('people wrapper forwards ack and persistent mode cannot silently drop selection',()=>{
 const s=readFileSync(new URL('../people/ConfirmedPeopleTransfer.tsx',import.meta.url),'utf8');
 assert.ok(s.includes('flow.commit(spill,shadow,torso,waist,head,collarbone,faceStyle)'));assert.ok(!s.includes('collarbonePersistentBlocked'));assert.ok(s.includes('确认源成员与所有目标的真实前后图像'));
});
test('workflow keeps unknown mutations pending and rejects absent visual review',()=>{
 const s=readFileSync(new URL('../batch/batchWorkflow.ts',import.meta.url),'utf8');
 for(const fragment of ['validCollarboneAck(collarboneReviewAck','pending?.collarboneAck!==undefined','sameCollarboneAck(result.collarbone_review_ack','COLLARBONE_VISUAL_LIMITS.targets'])assert.ok(s.includes(fragment));
});

test('integer half-way display rounding preserves exact ties-to-even extent',()=>{
 const r=review(),v=visualFixture(r);
 for(const [height,expected] of [[1,1],[3,2],[5,2],[7,4]]){
  const value={...v,source_size:[2048,height],before_output_size:[2048,height],after_output_size:[2048,height],before:{...v.before,width:1024,height:expected},after:{...v.after,width:1024,height:expected}};
  assert.equal(validCollarboneVisual(value,r),true);assert.equal(validCollarboneVisual({...value,before:{...value.before,height:expected+1}},r),false);
 }
});
