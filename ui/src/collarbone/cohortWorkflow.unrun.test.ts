// AUTHORED / UNRUN. Synthetic receipts only, not execution or photographic acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchTransport,type BatchReply,type BatchAction,type BatchOptions} from '../batch/batchWorkflow';
import {cohortFixture} from './cohortFixture';
import {collarboneCohortTargets} from './cohortModel';
import {collarboneAck} from './transferModel';
function fixture(operation:'create'|'patch'|'unlink'='create',activeOnly=false,mutate:(reply:BatchReply)=>void=()=>{}){
 const f=cohortFixture(operation,activeOnly),token='f'.repeat(32),rows=[f.plan.association_source,...f.plan.targets];
 const source={document_id:f.sourceId,revision:'3',path:'/source.raw'},calls:{action:BatchAction;options:BatchOptions}[]=[],replies=new Map<string,BatchReply>();let count=0,time=0;
 const api:BatchTransport={request:async(action,options)=>{calls.push({action,options});const id=options.requestId!;
  const outcomes=rows.map(row=>({...row,expected_revision:row.revision,result_revision:String(Number(row.revision)+1),outcome:'applied'}));
  const reply:BatchReply=action==='preflight'?{...f.plan,request_id:id,action,success:true,preflight_token:token,source_snapshot:source,
   people_transfer:true,policy:'recheck',applies:f.people as unknown as Record<string,unknown>,rejected_docs:[],ok:1,blocked:0}
   :{request_id:id,action,success:true,outcome_unknown:false,preflight_token:token,source_snapshot:source,module_scope:f.plan.module_scope,
    collarbone_cohort:true,collarbone_review_ack:options.collarboneReviewAck,persistent_association:f.plan.persistent_association,
    source_outcome:outcomes[0],target_outcomes:outcomes.slice(1)};
  mutate(reply);replies.set(id,reply);return {requested:true};},read:async id=>({phase:'done',request_id:id,result:replies.get(id)})};
 const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`cohort-${++count}`,now:()=>time,pause:async()=>{time+=10;},timeoutMs:15});
 flow.updateContext({docs:[f.targetId],moduleScope:f.plan.module_scope,conflictPolicy:'recheck',sourceDocumentId:f.sourceId,referencePath:source.path,enabled:true,
  label:'cohort',peopleTransfer:f.people,peopleProof:f.people.source});
 return {...f,flow,api,calls,ack:collarboneAck(collarboneCohortTargets(f.plan).map(row=>row.visual))};
}
test('persistent create cannot commit with only target acknowledgment',async()=>{
 const {flow,calls,ack}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
 await flow.commit(undefined,undefined,undefined,undefined,undefined,ack.slice(1));assert.equal(calls.length,1);
 await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].options.collarboneReviewAck,ack);
});
test('empty-scope unlink and active-only patch retain whole-cohort approval',async()=>{
 for(const [operation,active] of [['unlink',false],['patch',true]] as const){
  const {flow,calls,ack}=fixture(operation,active);await flow.start();assert.equal(flow.snapshot().phase,'review');
  await flow.commit();assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(flow.snapshot().phase,'done');
 }
});
test('missing source image, marker or target evidence rejects preflight',async()=>{
 for(const change of [(r:any)=>{delete r.association_source.association.collarbone_visual;},(r:any)=>{delete r.collarbone_cohort;},
  (r:any)=>{delete r.targets[0].association.collarbone_coverage;},(r:any)=>{r.collarbone_cohort=false;}]){
  const {flow,calls}=fixture('create',false,r=>{if(r.action==='preflight')change(r);});await flow.start();assert.equal(flow.snapshot().phase,'error');assert.equal(calls.length,1);
 }
});
test('cohort terminal marker and source-first acknowledgment are not substitutable',async()=>{
 for(const change of [(r:any)=>{delete r.collarbone_cohort;},(r:any)=>{r.collarbone_review_ack.reverse();},(r:any)=>{r.collarbone_review_ack=r.collarbone_review_ack.slice(1);},
  (r:any)=>{r.preflight_token='0'.repeat(32);},(r:any)=>{delete r.source_outcome;}]){
  const {flow,calls,ack}=fixture('unlink',false,r=>{if(r.action==='commit')change(r);});await flow.start();await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);
  assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'uncertain');assert.equal(calls.length,2);
 }
});
test('unknown cohort mutation queries original request without a second publication',async()=>{
 const {flow,api,calls,ack}=fixture('patch',true);await flow.start();const read=api.read;api.read=async id=>({phase:'pending',request_id:id});
 await flow.commit(undefined,undefined,undefined,undefined,undefined,ack);assert.equal(flow.snapshot().phase,'uncertain');flow.close();api.read=read;await flow.query();
 assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
