// AUTHORED / UNRUN. Receipt-routing fixtures only, not rendered spill evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchTransport} from './batchWorkflow.ts';

const OP='lnx.spill_removal.v1',token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
function preflight(requestId:string):BatchReply{
  return {request_id:requestId,action:'preflight',success:true,preflight_token:token,
    source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},
    module_scope:[OP],applies:{[OP]:{enabled:true,strength:61}},policy:'skip_and_report',
    targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,
      source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}}}],
    rejected_docs:[],ok:1,blocked:0};
}
const target=(value:BatchReply)=>(value.targets as BatchTarget[])[0];
function fixture(mutate:(value:BatchReply)=>void=()=>{}){
  let requestId='',action='preflight',n=0;
  const calls:string[]=[];
  const api:BatchTransport={request:async(next,options)=>{action=next;requestId=options.requestId!;calls.push(next);return {requested:true};},
    read:async()=>{
      const value=preflight(requestId);
      if(action==='commit')Object.assign(value,{action:'commit',target_outcomes:[{
        index:1,path:'/target.raw',document_id:targetId,expected_revision:'2',result_revision:'3',outcome:'applied'}]});
      mutate(value);return {phase:'done',request_id:requestId,result:value};
    }};
  const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`spill-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',
    sourceDocumentId:sourceId,enabled:true,label:'Spill scalars'});
  return {flow,calls};
}

test('spill original targets require source and frozen target-owned evidence before confirmation',async()=>{
  const {flow,calls}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  assert.deepEqual(calls,['preflight']);await flow.commit();assert.equal(flow.snapshot().phase,'done');
});

test('spill rejects absent, malformed or mismatched scalar and dependency evidence',async()=>{
  const changes:Array<(value:BatchReply)=>void>=[
    value=>{delete value.source_snapshot!.source_proof;},
    value=>{value.source_snapshot!.source_proof={...proof('1'),original_sha256:'2'.repeat(64)};},
    value=>{value.source_snapshot!.document_id='e'.repeat(32);},
    value=>{delete target(value).source_proof;},
    value=>{target(value).source_proof={...proof('2'),creative_source:{sha256:'2'.repeat(64),width:0,height:24}};},
    value=>{delete target(value).before;},
    value=>{target(value).before={[OP]:{target_recipe_key:'not-a-hash'}};},
    value=>{target(value).document_id=sourceId;},
    value=>{value.applies![OP]={enabled:true,strength:61,coverage:null};},
    value=>{value.applies![OP]={enabled:1,strength:61};},
    value=>{value.applies![OP]={enabled:true,strength:101};},
    value=>{Object.assign(target(value),{blocked:true});},
  ];
  for(const change of changes){const {flow,calls}=fixture(change);await flow.start();
    assert.equal(flow.snapshot().phase,'error');await flow.commit();assert.deepEqual(calls,['preflight']);}
});

test('spill permits a distinct derived target proof without borrowing source identity',async()=>{
  const {flow}=fixture(value=>{target(value).source_proof={asset_sha256:'3'.repeat(64),original_sha256:'2'.repeat(64),
    creative_source:{sha256:'3'.repeat(64),width:32,height:24}};});
  await flow.start();assert.equal(flow.snapshot().phase,'review');
});

test('blocked spill targets may omit evidence that failed verification',async()=>{
  const {flow}=fixture(value=>{target(value).blocked='Target source is missing';delete target(value).source_proof;
    delete target(value).before;value.ok=0;value.blocked=1;});
  await flow.start();assert.equal(flow.snapshot().phase,'review');
});

test('spill commit keeps the exact frozen source proof and ignores object key order',async()=>{
  for(const mismatch of [false,true]){
    const {flow}=fixture(value=>{if(value.action==='commit')value.source_snapshot!.source_proof=mismatch?proof('9'):
      {creative_source:null,original_sha256:'1'.repeat(64),asset_sha256:'1'.repeat(64)};});
    await flow.start();await flow.commit();assert.equal(flow.snapshot().phase,mismatch?'uncertain':'done');
  }
});
