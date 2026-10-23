// AUTHORED / UNRUN. Receipt-routing fixtures only, not rendered spill evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchTransport} from './batchWorkflow.ts';
import {spillTransferAck,type SpillTransferEvidence} from '../spillRemoval/transferModel.ts';

const OP='lnx.spill_removal.v1',token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
// Metadata-only fixture: these are not verified photo pixels or visual acceptance evidence.
const visual=():SpillTransferEvidence=>({version:1,document_id:targetId,revision:'2',source_proof:proof('2'),
  before_sha256:'3'.repeat(64),candidate_sha256:'4'.repeat(64),before_people_sha256:'5'.repeat(64),candidate_people_sha256:'5'.repeat(64),
  source_size:[32,24],before_output_size:[32,24],after_output_size:[32,24],parameters:{enabled:true,strength:61},
  before:{mime:'image/png',width:32,height:24,sha256:'6'.repeat(64),base64:'iVBORw=='},
  after:{mime:'image/png',width:32,height:24,sha256:'7'.repeat(64),base64:'iVBORw=='}});
function preflight(requestId:string):BatchReply{
  return {request_id:requestId,action:'preflight',success:true,preflight_token:token,
    source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},
    module_scope:[OP],applies:{[OP]:{enabled:true,strength:61}},policy:'skip_and_report',
    targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,
      source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}},spill_transfer:visual()}],
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
  const flow=createBatchWorkflow(api,()=>{},{uuid:()=>`spill-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',
    sourceDocumentId:sourceId,enabled:true,label:'Spill scalars'});
  return {flow,calls,requests};
}
const acknowledgments=(flow:ReturnType<typeof createBatchWorkflow>)=>spillTransferAck(flow.snapshot().plan!.targets.filter(t=>!t.blocked).map(t=>t.spill_transfer!));

test('spill original targets require source and frozen target-owned evidence before confirmation',async()=>{
  const {flow,calls,requests}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  assert.deepEqual(calls,['preflight']);await flow.commit();assert.deepEqual(calls,['preflight']);
  const ack=acknowledgments(flow);await flow.commit(ack);assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(requests[1].spillReviewAck,ack);
});

test('spill rejects absent, malformed or mismatched scalar and dependency evidence',async()=>{
  const changes:Array<(value:BatchReply)=>void>=[
    value=>{delete value.source_snapshot!.source_proof;},
    value=>{value.source_snapshot!.source_proof={...proof('1'),original_sha256:'2'.repeat(64)};},
    value=>{value.source_snapshot!.document_id='e'.repeat(32);},
    value=>{delete target(value).source_proof;},
    value=>{target(value).source_proof={...proof('2'),creative_source:{sha256:'2'.repeat(64),width:0,height:24}};},
    value=>{delete target(value).before;},
    value=>{delete target(value).spill_transfer;},
    value=>{target(value).spill_transfer!.document_id=sourceId;},
    value=>{target(value).spill_transfer!.revision='3';},
    value=>{target(value).spill_transfer!.source_proof=proof('9');},
    value=>{target(value).spill_transfer!.parameters.strength=60;},
    value=>{target(value).spill_transfer!.after.width=257;},
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
    creative_source:{sha256:'3'.repeat(64),width:32,height:24}};
    target(value).spill_transfer!.source_proof=target(value).source_proof as SpillTransferEvidence['source_proof'];});
  await flow.start();assert.equal(flow.snapshot().phase,'review');
});

test('blocked spill targets may omit evidence that failed verification',async()=>{
  const {flow}=fixture(value=>{target(value).blocked='Target source is missing';delete target(value).source_proof;
    delete target(value).before;delete target(value).spill_transfer;value.ok=0;value.blocked=1;});
  await flow.start();assert.equal(flow.snapshot().phase,'review');
});

test('spill commit keeps the exact frozen source proof and ignores object key order',async()=>{
  for(const mismatch of [false,true]){
    const {flow}=fixture(value=>{if(value.action==='commit')value.source_snapshot!.source_proof=mismatch?proof('9'):
      {creative_source:null,original_sha256:'1'.repeat(64),asset_sha256:'1'.repeat(64)};});
    await flow.start();await flow.commit(acknowledgments(flow));assert.equal(flow.snapshot().phase,mismatch?'uncertain':'done');
  }
});

test('spill commit rejects partial, wrong-target, stale and recipe-hash acknowledgments',async()=>{
  for(const mutate of [
    (ack:ReturnType<typeof spillTransferAck>)=>ack.splice(0),
    (ack:ReturnType<typeof spillTransferAck>)=>{ack[0].document_id=sourceId;},
    (ack:ReturnType<typeof spillTransferAck>)=>{ack[0].revision='1';},
    (ack:ReturnType<typeof spillTransferAck>)=>{ack[0].before_sha256=visual().before_sha256;},
    (ack:ReturnType<typeof spillTransferAck>)=>{ack.push({...ack[0]});},
  ]){
    const {flow,calls}=fixture();await flow.start();const ack=acknowledgments(flow);mutate(ack);
    await flow.commit(ack);assert.deepEqual(calls,['preflight']);assert.equal(flow.snapshot().phase,'review');
  }
});

test('eight-target review includes every eligible image and excludes blocked targets',async()=>{
  const {flow,calls,requests}=fixture(value=>{
    if(value.action!=='preflight')return;
    const base=target(value);
    value.targets=Array.from({length:8},(_,index)=>{
      const id=(index+1).toString(16).repeat(32);
      return {...base,index,path:`/target-${index}.raw`,document_id:id,blocked:index===7?'Missing source':null,
        spill_transfer:index===7?undefined:{...visual(),document_id:id}};
    });value.ok=7;value.blocked=1;
  });
  await flow.start();assert.equal(flow.snapshot().phase,'review');const ack=acknowledgments(flow);
  await flow.commit(ack.slice(0,6));assert.deepEqual(calls,['preflight']);
  await flow.commit([...ack].reverse());assert.deepEqual(calls,['preflight']);
  // This fixture deliberately does not fabricate eight successful commit outcomes.
  await flow.commit(ack);assert.equal(calls.length,2);assert.equal(requests[1].spillReviewAck?.length,7);
  assert.equal(flow.snapshot().phase,'uncertain');
});

test('spill review rejects more than eight targets rather than showing a first-N subset',async()=>{
  const {flow,calls}=fixture(value=>{const base=target(value);value.targets=Array.from({length:9},(_,index)=>({...base,index,
    document_id:(index+1).toString(16).repeat(32)}));value.ok=9;});
  await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit([]);assert.deepEqual(calls,['preflight']);
});

test('close and changed edit context cannot reuse a previously acknowledged spill plan',async()=>{
  for(const close of [true,false]){
    const {flow,calls}=fixture();await flow.start();const ack=acknowledgments(flow);
    if(close)flow.close();else flow.updateContext({docs:['/other.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Changed'});
    await flow.commit(ack);assert.equal(flow.snapshot().plan,null);assert.deepEqual(calls,['preflight']);
  }
});
