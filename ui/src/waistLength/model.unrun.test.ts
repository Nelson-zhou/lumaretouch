// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No imports, tests, compiler, native core or UI were executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ANCHORS,FLAGS,WAIST_MARKERS,OPERATION_ID,REQUIREMENT_ID,adjust,canReview,check,checkReviewSupport,checkBodySupport,neutral,request,type BodyChoice,type ReviewSupport,type WaistLengthView} from './model.ts';
const ref={asset_sha256:'a'.repeat(64),body_instance_id:'body-1',analysis_revision:2};
const support=():ReviewSupport=>({version:1,method:'user-reviewed-visible-waist-length-support',outer_left:.03,inner_left:.1,inner_right:.9,outer_right:.97,upper_zero:.02,upper_plateau:.06,head_box:[.4,.09,.6,.24],left_arm_box:[.12,.26,.38,.76],right_arm_box:[.62,.26,.88,.76],waist_upper_left:[.36,.48],waist_upper_right:[.64,.48],waist_lower_left:[.38,.66],waist_lower_right:[.62,.66],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']});
function body():BodyChoice{
 const points=Array.from({length:33},(_,index)=>({index,x:.5,y:.2,z:0,visibility:1,presence:1}));
 points[11]={...points[11],x:.35,y:.3};points[12]={...points[12],x:.65,y:.3};points[23]={...points[23],x:.4,y:.78};points[24]={...points[24],x:.6,y:.78};
 return {body_ref:{...ref},enabled:true,operation_enabled:true,points,points_sha256:'b'.repeat(64),source:{sha256:ref.asset_sha256,width:800,height:1200,orientation:'exif_normalized_once'},reviewed:false,support:null,association:{person_id:'person-1',body_ref:{...ref},people_association_revision:3,confirmation_revision:1}};
}
const view=():WaistLengthView=>({binding:{document_id:'document-1',document_epoch:'epoch-1',document_revision:5,asset_sha256:ref.asset_sha256},state_revision:6,association_revision:7,people_association_revision:3,body_graph_sha256:'c'.repeat(64),people_graph_sha256:'d'.repeat(64),bodies:[body()],selected_body_ref:{...ref},recipe:neutral(),refusals:[]});
test('exact independent waist ID and signed zero-neutral recipe, not torso or width controls',()=>{
 assert.equal(OPERATION_ID,'lnx.waist_length.v1');assert.equal(REQUIREMENT_ID,'LNX-REF-PC-32473-C-5d33f285bb');
 assert.deepEqual(neutral(),{version:1,amount:0});assert.deepEqual(adjust(neutral(),-1),{version:1,amount:-1});assert.equal(adjust(neutral(),1).amount,1);
 for(const amount of [NaN,Infinity,-Infinity,-1.01,1.01,true,'0',null])assert.throws(()=>check({version:1,amount} as never));
 for(const extra of [{width:0},{torso_length:0},{waist_shape:0},{height:0}])assert.throws(()=>check({version:1,amount:0,...extra} as never));
});
test('real head, arms, hands and shoulder/hip observations with exact same-body association are mandatory',()=>{
 assert.deepEqual([...ANCHORS],Array.from({length:25},(_,i)=>i));assert.equal(canReview(body()),true);
 for(const index of ANCHORS){const b=body();b.points[index].visibility=.79;assert.equal(canReview(b),false);}
 const b=body();b.association=null;assert.equal(canReview(b),false);
 const foreign=body();foreign.association!.body_ref.body_instance_id='other';assert.equal(canReview(foreign),false);
 const sparse=body();sparse.points=sparse.points.slice(0,25);assert.equal(canReview(sparse),false);
});
test('four bilateral explicit markers are required, with no shoulder/hip or saved other-tool substitutes',()=>{
 assert.deepEqual([...WAIST_MARKERS],['waist_upper_left','waist_upper_right','waist_lower_left','waist_lower_right']);
 assert.deepEqual(checkReviewSupport(support()),support());
 for(const key of WAIST_MARKERS){const missing={...support()} as Partial<ReviewSupport>;delete missing[key];assert.throws(()=>checkReviewSupport(missing as ReviewSupport));for(const value of [[.4],[.4,.5,.6],[0,.5],[.4,1],[NaN,.5],[true,.5],null])assert.throws(()=>checkReviewSupport({...support(),[key]:value} as never));}
 for(const patch of [{method:'user-reviewed-visible-torso-length-support'},{waist_upper_left:[.7,.48]},{waist_lower_right:[.3,.66]},{waist_lower_left:[.38,.47]},{waist_upper_right:[.64,.67]}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
});
test('ordered background, full-contour boxes and all independent waist confirmations are closed',()=>{
 for(const patch of [{outer_left:0},{upper_zero:.1},{inner_left:.4},{head_box:[.4,.04,.6,.24]},{left_arm_box:[.2,.28,.95,.75]},{right_arm_box:[.8,.28,.65,.75]},{inner_right:true},{head_box:[.4,.1,.6,1]}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
 assert.ok(FLAGS.includes('bilateral_waist_endpoints_visible'));assert.ok(FLAGS.includes('waist_endpoints_manually_marked'));assert.ok(FLAGS.includes('complete_upper_trunk_reviewed'));
 for(const flag of FLAGS)assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,[flag]:false}} as never));
 assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,extra:true}} as never));
 for(const patch of [{associated_face_ref:{}},{associated_face_box:[.4,.1,.6,.24]},{associated_face_evidence_sha256:'e'.repeat(64)}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
});
test('source-scaled guard rejects tiny, sloping, crossed, displaced and non-waist bands',()=>{
 assert.deepEqual(checkBodySupport(support(),body()),support());
 const patches=[
  {waist_upper_left:[.36,.29]},
  {waist_lower_right:[.62,.79]},
  {waist_lower_left:[.38,.5],waist_lower_right:[.62,.5]},
  {waist_upper_left:[.49,.48],waist_upper_right:[.51,.48]},
  {waist_upper_right:[.64,.55]},
  {waist_lower_left:[.47,.66]},
  {waist_upper_left:[.52,.48]},
  {head_box:[.4,.09,.6,.31]},
 ];
 for(const patch of patches)assert.throws(()=>checkBodySupport({...support(),...patch} as ReviewSupport,body()));
 const small=body();small.source.height=200;assert.throws(()=>checkBodySupport(support(),small));
 const disabledConfidence=body();disabledConfidence.points[23].presence=.7;assert.throws(()=>checkBodySupport(support(),disabledConfidence));
});
test('request carries current canonical body/source/people fences without a separate history owner',()=>{
 const v=view(),payload={recipe:{version:1,amount:.4},base:neutral()},r=request(v,'recipe',payload,'gesture-1');
 assert.equal(r.operation_id,OPERATION_ID);assert.deepEqual(r.body_ref,ref);assert.equal(r.document_revision,5);assert.equal(r.state_revision,6);assert.equal(r.association_revision,7);assert.equal(r.people_association_revision,3);assert.equal(r.body_graph_sha256,v.body_graph_sha256);assert.equal(r.people_graph_sha256,v.people_graph_sha256);
 payload.recipe.amount=.9;assert.equal((r.payload.recipe as {amount:number}).amount,.4);
 assert.throws(()=>request({...v,selected_body_ref:null},'recipe',{},'gesture-2'));
});
