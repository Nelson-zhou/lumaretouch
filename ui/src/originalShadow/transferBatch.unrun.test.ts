// AUTHORED / UNRUN. Receipt-routing fixtures only, not rendered shadow evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchTransport} from '../batch/batchWorkflow.ts';
import {shadowTransferAck,type ShadowTransferEvidence} from './transferModel.ts';

const OP='lnx.original_shadow.v1',token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
// Metadata-only fixture: these are not verified photo pixels or visual acceptance evidence.
const visual=():ShadowTransferEvidence=>({version:1,document_id:targetId,revision:'2',source_proof:proof('2'),
  before_sha256:'3'.repeat(64),candidate_sha256:'4'.repeat(64),before_people_sha256:'5'.repeat(64),candidate_people_sha256:'5'.repeat(64),
  source_size:[32,24],before_output_size:[32,24],after_output_size:[32,24],parameters:{enabled:true,strength:61,blend:'normal'},
  before:{mime:'image/png',width:32,height:24,sha256:'6'.repeat(64),base64:'iVBORw=='},
  after:{mime:'image/png',width:32,height:24,sha256:'7'.repeat(64),base64:'iVBORw=='}});
function preflight(requestId:string):BatchReply{
  return {request_id:requestId,action:'preflight',success:true,preflight_token:token,
    source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},
    module_scope:[OP],applies:{[OP]:{enabled:true,strength:61,blend:'normal'}},policy:'skip_and_report',
    targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,
      source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}},shadow_transfer:visual()}],
    rejected_docs:[],ok:1,blocked:0};
}
const target=(value:BatchReply)=>(value.targets as BatchTarget[])[0];
function fixture(mutate:(value:BatchReply)=>void=()=>{}){
  let requestId='',action='preflight',n=0;
  const calls:string[]=[];
  const requests:Parameters<BatchTransport['request']>[1][]=[];
  const api:BatchTransport={request:async(next,options)=>{action=next;requestId=options.requestId!;calls.push(next);requests.push(options);return {requested:true};},
    read:async()=>{
      const value=preflight(requestId);
      if(action==='commit')Object.assign(value,{action:'commit',target_outcomes:[{
        index:1,path:'/target.raw',document_id:targetId,expected_revision:'2',result_revision:'3',outcome:'applied'}]});
      mutate(value);return {phase:'done',request_id:requestId,result:value};
    }};
  const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`shadow-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',
    sourceDocumentId:sourceId,enabled:true,label:'Shadow scalars'});
  return {flow,calls,requests};
}
const acknowledgments=(flow:ReturnType<typeof createBatchWorkflow>)=>shadowTransferAck(flow.snapshot().plan!.targets.filter(t=>!t.blocked).map(t=>t.shadow_transfer!));

test('shadow original targets require source and frozen target-owned evidence before confirmation',async()=>{
  const {flow,calls,requests}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  assert.deepEqual(calls,['preflight']);await flow.commit();assert.deepEqual(calls,['preflight']);
  const ack=acknowledgments(flow);await flow.commit(undefined,ack);assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(requests[1].shadowReviewAck,ack);
});


test('shadow transfer missing target evidence or source-owned dependencies never commits',async()=>{
 for(const mutate of [(v:BatchReply)=>{delete target(v).shadow_transfer;},
   (v:BatchReply)=>{target(v).shadow_transfer!.parameters.blend='multiply';},
   (v:BatchReply)=>{target(v).shadow_transfer!.source_proof=proof('f');},
   (v:BatchReply)=>{v.module_scope!.push('lnx.spill_removal.v1');}]){
  const {flow,calls}=fixture(mutate);await flow.start();assert.equal(flow.snapshot().phase,'error');
  await flow.commit();assert.deepEqual(calls,['preflight']);
 }
});
test('shadow ack cannot use stale target hashes',async()=>{
 const {flow,calls}=fixture();await flow.start();const ack=acknowledgments(flow);
 ack[0].after_sha256='f'.repeat(64);await flow.commit(undefined,ack);
 assert.deepEqual(calls,['preflight']);assert.equal(flow.snapshot().phase,'review');
});
