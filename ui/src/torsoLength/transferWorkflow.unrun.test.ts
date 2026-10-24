// AUTHORED / UNRUN. Correlated metadata fixtures, never photo/render acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchOptions} from '../batch/batchWorkflow.ts';
import {createPresetWorkflow,type PresetReply,type PresetOptions,validatePresetReply} from '../presets/presetWorkflow.ts';
import {batchScopeOptions} from '../batch/batchScopeOptions.ts';
import {TORSO_TRANSFER_OP as OP,torsoTransferAck,type TorsoTransferEvidence} from './transferModel.ts';
const token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
const visual=(id=targetId):TorsoTransferEvidence=>({version:1,document_id:id,revision:'2',source_proof:proof('2'),
  before_sha256:'3'.repeat(64),candidate_sha256:'4'.repeat(64),before_people_sha256:'5'.repeat(64),candidate_people_sha256:'5'.repeat(64),
  source_size:[32,24],before_output_size:[32,24],after_output_size:[32,24],parameters:{version:1,amount:.3},
  body_ref:{asset_sha256:'2'.repeat(64),body_instance_id:'body:target',analysis_revision:1},
  associated_face:{associated_face_ref:{asset_sha256:'2'.repeat(64),face_instance_id:'face:target',analysis_revision:2},associated_face_box:[.3,.1,.7,.3],associated_face_evidence_sha256:'9'.repeat(64)},
  body_support_sha256:'a'.repeat(64),body_review_sha256:'b'.repeat(64),before_bank_sha256:'c'.repeat(64),candidate_bank_sha256:'d'.repeat(64),
  before:{mime:'image/png',width:32,height:24,sha256:'6'.repeat(64),base64:'iVBORw=='},after:{mime:'image/png',width:32,height:24,sha256:'7'.repeat(64),base64:'iVBORw=='}});
function plan(requestId:string):BatchReply{return {request_id:requestId,action:'preflight',success:true,preflight_token:token,
  source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},module_scope:[OP],applies:{[OP]:{version:1,amount:.3}},policy:'skip_and_report',
  targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}},torso_transfer:visual()}],rejected_docs:[],ok:1,blocked:0};}
function batchFixture(mutate:(v:BatchReply)=>void=()=>{}){
  let id='',action='preflight',n=0;const calls:BatchOptions[]=[];
  const flow=createBatchWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=plan(id);
    if(action==='commit'){value.action='commit';delete value.targets;value.torso_review_ack=calls[calls.length-1].torsoReviewAck;
      value.target_outcomes=[{index:1,path:'/target.raw',document_id:targetId,expected_revision:'2',result_revision:'3',outcome:'applied'}];}
    mutate(value);return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`torso-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Torso scalars'});
  return {flow,calls};
}
test('batch refuses missing/stale acknowledgments and forwards exact third argument',async()=>{
  const {flow,calls}=batchFixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  await flow.commit();assert.equal(calls.length,1);
  const ack=torsoTransferAck([visual()]);await flow.commit(undefined,undefined,[{...ack[0],after_sha256:'f'.repeat(64)}]);assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,ack);assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(calls[1].torsoReviewAck,ack);assert.notEqual(calls[1].torsoReviewAck,ack);
});
test('batch rejects missing evidence, foreign target body, mixed scope and terminal ack substitution',async()=>{
  for(const change of [(v:BatchReply)=>{delete (v.targets![0] as BatchTarget).torso_transfer;},
    (v:BatchReply)=>{(v.targets![0] as BatchTarget).torso_transfer!.body_ref.asset_sha256='f'.repeat(64);},
    (v:BatchReply)=>{v.module_scope!.push('lnx.exposure.v1');}]){
    const {flow,calls}=batchFixture(change);await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit();assert.equal(calls.length,1);
  }
  const {flow}=batchFixture(v=>{if(v.action==='commit')delete v.torso_review_ack;});await flow.start();await flow.commit(undefined,undefined,torsoTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
});
function presetReview(id:string):PresetReply{return {protocol:1,request_id:id,action:'preflight',success:true,outcome_unknown:false,document_id:'loaded',id:'torso',module_scope:[OP],revision:'2',preflight_token:token,applies:{[OP]:{version:1,amount:.3}},source_proof:proof('2'),torso_transfer:visual('loaded')};}
function presetFixture(){
  let id='',action='preflight',n=0;const calls:PresetOptions[]=[];
  const flow=createPresetWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=presetReview(id);
    if(action==='apply'){value.action='apply';delete value.torso_transfer;value.torso_review_ack=calls[calls.length-1].torsoReviewAck;
      value.before={[OP]:{target_recipe_key:'a'.repeat(64)}};value.after={[OP]:{target_recipe_key:'b'.repeat(64)}};value.doc_state={document_id:'loaded'};}
    return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`preset-${++n}`});flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-2'});return {flow,calls};
}
test('preset requires matching frozen token, context and exact target image pair',async()=>{
  const {flow,calls}=presetFixture();await flow.submit('apply',{id:'torso'},[OP]);assert.equal(calls.length,0);
  await flow.submit('preflight',{id:'torso'},[OP]);assert.equal(flow.snapshot().phase,'done');
  const ack=torsoTransferAck([visual('loaded')]);
  for(const options of [{id:'torso',preflightToken:token},{id:'torso',preflightToken:'f'.repeat(32),torsoReviewAck:ack},{id:'other',preflightToken:token,torsoReviewAck:ack}]){await flow.submit('apply',options,[OP]);assert.equal(calls.length,1);}
  await flow.submit('apply',{id:'torso',preflightToken:token,torsoReviewAck:ack},[OP]);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].torsoReviewAck,ack);
});
test('preset rejects changed or dismissed review and incomplete body proof',async()=>{
  for(const dismiss of [true,false]){
    const {flow,calls}=presetFixture();await flow.submit('preflight',{id:'torso'},[OP]);
    if(dismiss)flow.dismissReview();else flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-3'});
    await flow.submit('apply',{id:'torso',preflightToken:token,torsoReviewAck:torsoTransferAck([visual('loaded')])},[OP]);assert.equal(calls.length,1);
  }
  const result=presetReview('p');delete result.torso_transfer;
  assert.throws(()=>validatePresetReply(result,'preflight',{id:'torso',documentId:'loaded'},'p',[OP]));
});
test('torso is only offered as its own reported transferable batch scope',()=>{
  assert.equal(batchScopeOptions([{operation_id:OP,transferable:false}]).some(v=>v.ops.includes(OP)),false);
  const offered=batchScopeOptions([{operation_id:OP,transferable:true},{operation_id:'lnx.exposure.v1',transferable:true}]);
  assert.deepEqual(offered.filter(v=>v.ops.includes(OP)).map(v=>v.ops),[[OP]]);
});
