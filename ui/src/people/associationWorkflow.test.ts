// UNRUN source fixtures, requires an explicitly selected local TypeScript runner.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchTransport,type BatchReply,type BatchOptions,type BatchAction} from '../batch/batchWorkflow.ts';
import type {AssociationRequest,AssociationReview} from './associationProof';
import {request,sourceId,targetId} from './transferFixtureData.test.ts';
function fixture(operation:AssociationRequest['operation']='create'){
  const people:AssociationRequest={...request(),target_policy:'persistent_association',operation,association_id:'person-1'};
  if(operation==='unlink')people.selection={};
  const source={document_id:sourceId,revision:'3',path:'/source.raw'},token='f'.repeat(32);
  const endpoints=[{target:people.source,target_refs:[people.source_ref]},...people.targets];
  const targets=endpoints.map((e,index)=>({index,path:index?'/target.raw':'/source.raw',document_id:e.target.document.document_id,revision:String(e.target.document.revision),blocked:null,
    association:{owner:e.target,ref:e.target_refs[0],person_id:'person-1',candidate_sha256:'e'.repeat(64)}}));
  const evidence:AssociationReview={version:1,operation,association_id:'person-1',generation:'9'.repeat(64),
    members:endpoints.map(e=>({document_id:e.target.document.document_id,scope_id:e.target.people_scope,original_sha256:e.target.source_proof.original_sha256,ref:e.target_refs[0]})),
    intent:[{op:'lnx.deform.v1',path:'/face_slim',value:.3}]};
  let count=0;const calls:{action:BatchAction;options:BatchOptions}[]=[],replies=new Map<string,BatchReply>();
  const api:BatchTransport={request:async(action,options)=>{calls.push({action,options});const id=options.requestId!;
    const outcomes=targets.map(t=>({...t,expected_revision:t.revision,result_revision:String(Number(t.revision)+1),outcome:'applied'}));
    replies.set(id,action==='preflight'?{request_id:id,action,success:true,preflight_token:token,source_snapshot:source,people_transfer:true,
      module_scope:Object.keys(people.selection),policy:'recheck',applies:people,targets:targets.slice(1),association_source:targets[0],persistent_association:evidence,rejected_docs:[],ok:1,blocked:0}
      :{request_id:id,action,success:true,preflight_token:token,source_snapshot:source,target_outcomes:outcomes.slice(1),source_outcome:outcomes[0],persistent_association:structuredClone(evidence)});return {requested:true};},
    read:async id=>({phase:'done',request_id:id,result:replies.get(id)})};
  const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`association-${++count}`});
  flow.updateContext({docs:[targetId],moduleScope:Object.keys(people.selection),conflictPolicy:'recheck',sourceDocumentId:sourceId,referencePath:source.path,enabled:true,label:'association',peopleTransfer:people,peopleProof:people.source});
  return {flow,api,calls};
}
test('whole unlink with empty scalar selection still reaches strict frozen review',async()=>{
  const {flow,calls}=fixture('unlink');await flow.start();assert.equal(flow.snapshot().phase,'review');await flow.commit();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
test('missing source-member review cannot authorize association commit',async()=>{
  const {flow,api,calls}=fixture(),read=api.read;api.read=async id=>{const r=await read(id);if(r.result)delete r.result.association_source;return r;};
  await flow.start();await flow.commit();assert.equal(flow.snapshot().plan,null);assert.equal(calls.length,1);
});
test('source-member result is mandatory after atomic association commit',async()=>{
  const {flow,api,calls}=fixture();await flow.start();const read=api.read;api.read=async id=>{const r=await read(id);if(r.result)delete r.result.source_outcome;return r;};
  await flow.commit();assert.notEqual(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
test('persistent target cannot be silently reported skipped',async()=>{
  const {flow,api}=fixture();await flow.start();const read=api.read;api.read=async id=>{const r=await read(id);if(r.result?.target_outcomes)r.result.target_outcomes[0].outcome='skipped';return r;};
  await flow.commit();assert.notEqual(flow.snapshot().phase,'done');
});

test('association receipt cannot replace the frozen content generation or intent',async()=>{
  for(const mutate of [(r:any)=>{r.persistent_association.generation='8'.repeat(64);},(r:any)=>{r.persistent_association.intent[0].value=.9;},
    (r:any)=>{r.persistent_association.members[1].ref.analysis_revision++;},(r:any)=>{delete r.persistent_association;}]){
    const {flow,api}=fixture();await flow.start();const read=api.read;api.read=async id=>{const r=await read(id);mutate(r.result);return r;};
    await flow.commit();assert.notEqual(flow.snapshot().phase,'done');
  }
});

test('persistent changes require every document revision to advance',async()=>{
  const {flow,api}=fixture();await flow.start();const read=api.read;api.read=async id=>{const r=await read(id);if(r.result?.target_outcomes){const t=r.result.target_outcomes[0];t.result_revision=t.expected_revision;}return r;};
  await flow.commit();assert.notEqual(flow.snapshot().phase,'done');
});
