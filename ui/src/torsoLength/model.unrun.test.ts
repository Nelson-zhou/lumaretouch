// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Static fixtures, not runtime, pixel or naturalness acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ANCHORS,FLAGS,OPERATION_ID,REQUIREMENT_ID,adjust,canReview,check,checkReviewSupport,neutral,request,type BodyChoice,type ReviewSupport,type TorsoLengthView} from './model.ts';
const ref={asset_sha256:'a'.repeat(64),body_instance_id:'body-1',analysis_revision:2};
const support=():ReviewSupport=>({version:1,method:'user-reviewed-visible-torso-length-support',outer_left:.05,inner_left:.15,inner_right:.85,outer_right:.95,upper_zero:.03,upper_plateau:.08,head_box:[.4,.1,.6,.24],left_arm_box:[.2,.28,.35,.75],right_arm_box:[.65,.28,.8,.75],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']});
const body=():BodyChoice=>({body_ref:{...ref},enabled:true,operation_enabled:true,points:Array.from({length:33},(_,index)=>({index,x:.5,y:.5,z:0,visibility:1,presence:1})),points_sha256:'b'.repeat(64),source:{sha256:ref.asset_sha256,width:800,height:1200,orientation:'exif_normalized_once'},reviewed:false,support:null,association:{person_id:'person-1',body_ref:{...ref},people_association_revision:3,confirmation_revision:1}});
const view=():TorsoLengthView=>({binding:{document_id:'document-1',document_epoch:'epoch-1',document_revision:5,asset_sha256:ref.asset_sha256},state_revision:6,association_revision:7,people_association_revision:3,body_graph_sha256:'c'.repeat(64),people_graph_sha256:'d'.repeat(64),bodies:[body()],selected_body_ref:{...ref},recipe:neutral(),refusals:[]});
test('exact independent torso ID and signed zero-neutral recipe; no waist or AI recipe keys',()=>{
 assert.equal(OPERATION_ID,'lnx.torso_length.v1');assert.equal(REQUIREMENT_ID,'LNX-REF-PC-32473-C-f1662d2dec');
 assert.deepEqual(neutral(),{version:1,amount:0});assert.deepEqual(adjust(neutral(),-1),{version:1,amount:-1});assert.equal(adjust(neutral(),1).amount,1);
 for(const amount of [NaN,Infinity,-Infinity,-1.01,1.01,true,'0',null])assert.throws(()=>check({version:1,amount} as never));
 assert.throws(()=>check({version:1,amount:0,width:0} as never));
});
test('real head, arms, hands and shoulder/hip observations plus confirmed association are necessary',()=>{
 assert.deepEqual([...ANCHORS],Array.from({length:25},(_,i)=>i));assert.equal(canReview(body()),true);
 for(const index of ANCHORS){const b=body();b.points[index].visibility=.79;assert.equal(canReview(b),false);}
 const b=body();b.association=null;assert.equal(canReview(b),false);
 const foreign=body();foreign.association!.body_ref.body_instance_id='other';assert.equal(canReview(foreign),false);
 const sparse=body();sparse.points=sparse.points.slice(0,25);assert.equal(canReview(sparse),false);
});
test('support is measured geometry, strictly interior ordered boundaries and separate full-contour boxes',()=>{
 assert.deepEqual(checkReviewSupport(support()),support());
 for(const patch of [{outer_left:0},{upper_zero:.1},{inner_left:.4},{head_box:[.4,.04,.6,.24]},{left_arm_box:[.2,.28,.9,.75]},{right_arm_box:[.8,.28,.65,.75]},{inner_right:true},{head_box:[.4,.1,.6,1]},{associated_face_ref:{}}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
 for(const flag of FLAGS)assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,[flag]:false}} as never));
 assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,extra:true}} as never));
 // Canonical face facts are deliberately not accepted as user-authored review geometry.
 assert.throws(()=>checkReviewSupport({...support(),associated_face_box:[.4,.1,.6,.24],associated_face_evidence_sha256:'e'.repeat(64)} as never));
});
test('request uses current canonical BodyRef and all graph/revision fences, never portrait patching',()=>{
 const v=view(),payload={recipe:{version:1,amount:.4},base:neutral()},r=request(v,'recipe',payload,'gesture-1');
 assert.equal(r.operation_id,OPERATION_ID);assert.deepEqual(r.body_ref,ref);assert.equal(r.document_revision,5);assert.equal(r.state_revision,6);assert.equal(r.association_revision,7);assert.equal(r.people_association_revision,3);assert.equal(r.body_graph_sha256,v.body_graph_sha256);assert.equal(r.people_graph_sha256,v.people_graph_sha256);
 payload.recipe.amount=.9;assert.equal((r.payload.recipe as {amount:number}).amount,.4);
 assert.throws(()=>request({...v,selected_body_ref:null},'recipe',{},'gesture-2'));
});
