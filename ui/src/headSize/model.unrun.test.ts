// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No imports, tests, compiler, native core or app were executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ANCHORS,HEAD_ANCHORS,FLAGS,OPERATION_ID,REQUIREMENT_ID,adjust,canReview,check,checkReviewSupport,checkBodySupport,neutral,request,type BodyChoice,type ReviewSupport,type HeadSizeView} from './model.ts';
const ref={asset_sha256:'a'.repeat(64),body_instance_id:'body-1',analysis_revision:2};
const support=():ReviewSupport=>({version:1,method:'user-reviewed-complete-head-hair-support',head_box:[.3,.1,.7,.3],transition_box:[.22,.04,.78,.36],pivot:[.51,.21],confirmations:Object.fromEntries(FLAGS.map(k=>[k,true])) as ReviewSupport['confirmations']});
function body():BodyChoice{
 const points=Array.from({length:33},(_,index)=>({index,x:.5,y:.2,z:0,visibility:1,presence:1}));
 points[11]={...points[11],x:.28,y:.45};points[12]={...points[12],x:.72,y:.45};
 return {body_ref:{...ref},enabled:true,operation_enabled:true,points,points_sha256:'b'.repeat(64),source:{sha256:ref.asset_sha256,width:800,height:1200,orientation:'exif_normalized_once'},reviewed:false,support:null,association:{person_id:'person-1',body_ref:{...ref},people_association_revision:3,confirmation_revision:1},associated_face:{associated_face_ref:{asset_sha256:ref.asset_sha256,face_instance_id:'face-1',analysis_revision:4},associated_face_box:[.38,.16,.62,.26],associated_face_evidence_sha256:'e'.repeat(64)},associated_face_error:null};
}
const view=():HeadSizeView=>({binding:{document_id:'document-1',document_epoch:'epoch-1',document_revision:5,asset_sha256:ref.asset_sha256},state_revision:6,association_revision:7,people_association_revision:3,body_graph_sha256:'c'.repeat(64),people_graph_sha256:'d'.repeat(64),bodies:[body()],selected_body_ref:{...ref},recipe:neutral(),refusals:[]});
test('independent small-head ID and shrink-only zero-neutral recipe are exact',()=>{
 assert.equal(OPERATION_ID,'lnx.head_size.v1');assert.equal(REQUIREMENT_ID,'LNX-REF-PC-32473-C-dc1b0ba40a');
 assert.deepEqual(neutral(),{version:1,amount:0});assert.equal(adjust(neutral(),1).amount,1);
 for(const amount of [-1,-.001,1.001,NaN,Infinity,true,'0',null])assert.throws(()=>check({version:1,amount} as never));
 for(const extra of [{face_size:0},{hairline:0},{waist_length:0},{head_box:[0,0,1,1]}])assert.throws(()=>check({version:1,amount:0,...extra} as never));
});
test('all real head and shoulder observations plus current own factual face are required',()=>{
 assert.deepEqual([...ANCHORS],Array.from({length:13},(_,i)=>i));assert.deepEqual([...HEAD_ANCHORS],Array.from({length:11},(_,i)=>i));assert.equal(canReview(body()),true);
 for(const index of ANCHORS){const b=body();b.points[index].visibility=.79;assert.equal(canReview(b),false);}
 const lowPresence=body();lowPresence.points[11].presence=.79;assert.equal(canReview(lowPresence),false);
 const noFace=body();noFace.associated_face=null;assert.equal(canReview(noFace),false);
 const foreignFace=body();foreignFace.associated_face!.associated_face_ref.asset_sha256='f'.repeat(64);assert.equal(canReview(foreignFace),false);
 const noRelation=body();noRelation.association=null;assert.equal(canReview(noRelation),false);
 const foreignBody=body();foreignBody.association!.body_ref.body_instance_id='body-other';assert.equal(canReview(foreignBody),false);
 const sparse=body();sparse.points=sparse.points.slice(0,13);assert.equal(canReview(sparse),false);
 const lowerLimb=body();lowerLimb.points[27].visibility=0;assert.equal(canReview(lowerLimb),true);
});
test('complete manual head/hair box, separate outer transition and explicit pivot are mandatory',()=>{
 assert.deepEqual(checkReviewSupport(support()),support());
 for(const key of ['head_box','transition_box','pivot'] as const){const absent={...support()} as Partial<ReviewSupport>;delete absent[key];assert.throws(()=>checkReviewSupport(absent as ReviewSupport));}
 for(const patch of [{method:'user-reviewed-visible-face-size-support'},{head_box:[.3,.1,.7,1]},{transition_box:[.3,.04,.78,.36]},{transition_box:[.22,.12,.78,.36]},{pivot:[.7,.2]},{pivot:[.5]},{pivot:[.5,.2,.1]},{pivot:[true,.2]},{exclusions:[]}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
 for(const flag of FLAGS)assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,[flag]:false}} as never));
 assert.throws(()=>checkReviewSupport({...support(),confirmations:{...support().confirmations,extra:true}} as never));
 for(const patch of [{associated_face_ref:{}},{associated_face_box:[.38,.16,.62,.26]},{associated_face_evidence_sha256:'e'.repeat(64)}])assert.throws(()=>checkReviewSupport({...support(),...patch} as never));
});
test('actual whole-face and every observed head point must fit the complete head plateau',()=>{
 assert.deepEqual(checkBodySupport(support(),body()),support());
 const outsideFace=body();outsideFace.associated_face!.associated_face_box=[.29,.16,.62,.26];assert.throws(()=>checkBodySupport(support(),outsideFace));
 for(const index of HEAD_ANCHORS){const outside=body();outside.points[index].x=.71;assert.throws(()=>checkBodySupport(support(),outside));}
 const onEdge=body();onEdge.points[10].x=.3;assert.throws(()=>checkBodySupport(support(),onEdge));
});
test('source pixels guard all four clear margins, crop edges, small bounds, shoulders and contacts',()=>{
 for(const patch of [{transition_box:[.29,.04,.78,.36]},{transition_box:[.22,.09,.78,.36]},{transition_box:[.22,.04,.71,.36]},{transition_box:[.22,.04,.78,.31]},{transition_box:[.0001,.04,.78,.36]},{transition_box:[.22,.0001,.78,.36]},{transition_box:[.22,.04,.9999,.36]},{transition_box:[.22,.04,.78,.46]}])assert.throws(()=>checkBodySupport({...support(),...patch} as ReviewSupport,body()));
 const tiny=body();tiny.source.width=50;assert.throws(()=>checkBodySupport(support(),tiny));
 const touch=body();touch.points[11].y=.36;assert.throws(()=>checkBodySupport(support(),touch));
 const tilt=body();tilt.points[11].y=.56;assert.throws(()=>checkBodySupport(support(),tilt));
 const depth=body();depth.points[11].z=.2;assert.throws(()=>checkBodySupport(support(),depth));
 const narrow=body();narrow.points[11].x=.49;narrow.points[12].x=.51;assert.throws(()=>checkBodySupport(support(),narrow));
 assert.throws(()=>checkBodySupport({...support(),confirmations:{...support().confirmations,no_contacts:false}} as never,body()));
});
test('request uses current canonical body/source/people fences and never transports guessed face evidence',()=>{
 const v=view(),payload={recipe:{version:1,amount:.4},base:neutral()},r=request(v,'recipe',payload,'gesture-1');
 assert.equal(r.operation_id,OPERATION_ID);assert.deepEqual(r.body_ref,ref);assert.equal(r.document_revision,5);assert.equal(r.state_revision,6);assert.equal(r.association_revision,7);assert.equal(r.people_association_revision,3);assert.equal(r.body_graph_sha256,v.body_graph_sha256);assert.equal(r.people_graph_sha256,v.people_graph_sha256);
 payload.recipe.amount=.9;assert.equal((r.payload.recipe as {amount:number}).amount,.4);
 assert.throws(()=>request({...v,selected_body_ref:null},'recipe',{},'gesture-2'));
});
