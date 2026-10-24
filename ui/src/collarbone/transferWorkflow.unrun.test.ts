// AUTHORED / UNRUN. Synthetic transport DTOs are not product execution or photo-quality evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchTransport,type BatchReply,type BatchOptions,type BatchAction} from '../batch/batchWorkflow';
import {request,review,sourceId,targetId} from '../people/transferFixtureData.test';
import {visualFixture} from './transferFixture';
import {collarboneAck} from './transferModel';
function fixture(mutate:(reply:BatchReply)=>void=()=>{}){
 const people=request(),evidence=review();people.selection={'lnx.collarbone.v1':['/amount']};
 evidence.parameters=[{operation_id:'lnx.collarbone.v1',parameter_path:'/amount',value:0}];
 evidence.collarbone_coverage={version:1,support_transfer:'none',targets:[{face_ref:evidence.target_refs[0],scope:'neutral-no-effect',body_review_sha256:null,clavicle_category:null,clavicle_sides:[]}]};
 evidence.collarbone_visual=visualFixture(evidence);
 const source={document_id:sourceId,revision:'3',path:'/source.raw'},target={document_id:targetId,revision:'20',index:1,path:'/target.raw',blocked:null};
 const calls:{action:BatchAction;options:BatchOptions}[]=[],replies=new Map<string,BatchReply>();let count=0,time=0;
 const api:BatchTransport={request:async(action,options)=>{calls.push({action,options});const id=options.requestId!;
   const reply:BatchReply=action==='preflight'?{request_id:id,action,success:true,preflight_token:'f'.repeat(32),source_snapshot:source,module_scope:Object.keys(people.selection),applies:people,policy:'recheck',targets:[{...target,people_transfer:evidence}],rejected_docs:[],ok:1,blocked:0,people_transfer:true}
    :{request_id:id,action,success:true,outcome_unknown:false,preflight_token:'f'.repeat(32),source_snapshot:source,module_scope:Object.keys(people.selection),collarbone_review_ack:options.collarboneReviewAck,target_outcomes:[{...target,expected_revision:'20',current_revision:'20',result_revision:'21',outcome:'applied'}]};
   mutate(reply);replies.set(id,reply);return {requested:true};},read:async id=>({phase:'done',request_id:id,result:replies.get(id)})};
 const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`collarbone-${++count}`,now:()=>time,pause:async()=>{time+=10;},timeoutMs:15});
 flow.updateContext({docs:[targetId],moduleScope:Object.keys(people.selection),conflictPolicy:'recheck',sourceDocumentId:sourceId,enabled:true,label:'collarbone',peopleTransfer:people,peopleProof:people.source});
 return {flow,api,calls,evidence,ack:collarboneAck([evidence.collarbone_visual])};
}
test('zero-strength transfer still needs exact reviewed image-pair acknowledgment',async()=>{
 const {flow,calls,ack}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
 await flow.commit();assert.equal(calls.length,1);
 await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].options.collarboneReviewAck,ack);assert.notEqual(calls[1].options.collarboneReviewAck,ack);
});
test('missing target images or wrong owner cannot produce committable review',async()=>{
 for(const mutate of [(r:any)=>{delete r.targets[0].people_transfer.collarbone_visual;},(r:any)=>{r.targets[0].people_transfer.collarbone_visual.document_id='wrong';}]){
  const {flow,calls,ack}=fixture(r=>{if(r.action==='preflight')mutate(r);});await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(calls.length,1);
 }
});
test('mismatched terminal acknowledgment keeps mutation uncertain and cannot release by inspection',async()=>{
 const {flow,calls,ack}=fixture(r=>{if(r.action==='commit')delete r.collarbone_review_ack;});await flow.start();await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);
 assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'uncertain');await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(calls.length,2);
});
test('query original request after timeout never sends second mutation',async()=>{
 const {flow,api,calls,ack}=fixture();await flow.start();const read=api.read;api.read=async id=>({phase:'pending',request_id:id});await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);
 assert.equal(flow.snapshot().phase,'uncertain');flow.close();api.read=read;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
