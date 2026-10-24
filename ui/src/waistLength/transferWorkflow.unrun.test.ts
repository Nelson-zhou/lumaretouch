// AUTHORED / UNRUN. Correlated metadata fixtures, never photo/render acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchOptions} from '../batch/batchWorkflow.ts';
import {createPresetWorkflow,type PresetReply,type PresetOptions,validatePresetReply} from '../presets/presetWorkflow.ts';
import {batchScopeOptions} from '../batch/batchScopeOptions.ts';
import {WAIST_TRANSFER_OP as OP,waistTransferAck,type WaistTransferEvidence} from './transferModel.ts';
const token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
const visual=(id=targetId):WaistTransferEvidence=>({version:1,document_id:id,revision:'2',source_proof:proof('2'),
  before_sha256:'3'.repeat(64),candidate_sha256:'4'.repeat(64),before_people_sha256:'5'.repeat(64),candidate_people_sha256:'5'.repeat(64),
  source_size:[32,24],before_output_size:[32,24],after_output_size:[32,24],parameters:{version:1,amount:.3},
  body_ref:{asset_sha256:'2'.repeat(64),body_instance_id:'body:target',analysis_revision:1},
  associated_face:{associated_face_ref:{asset_sha256:'2'.repeat(64),face_instance_id:'face:target',analysis_revision:2},associated_face_box:[.3,.1,.7,.3],associated_face_evidence_sha256:'9'.repeat(64)},
  body_support_sha256:'a'.repeat(64),body_review_sha256:'b'.repeat(64),before_bank_sha256:'c'.repeat(64),candidate_bank_sha256:'d'.repeat(64),
  before:{mime:'image/png',width:32,height:24,sha256:'6'.repeat(64),base64:'iVBORw=='},after:{mime:'image/png',width:32,height:24,sha256:'7'.repeat(64),base64:'iVBORw=='}});
function plan(requestId:string):BatchReply{return {request_id:requestId,action:'preflight',success:true,outcome_unknown:false,preflight_token:token,
  source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},module_scope:[OP],applies:{[OP]:{version:1,amount:.3}},policy:'skip_and_report',
  targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}},waist_transfer:visual()}],rejected_docs:[],ok:1,blocked:0};}
function batchFixture(mutate:(v:BatchReply)=>void=()=>{}){
  let id='',action='preflight',n=0;const calls:BatchOptions[]=[];
  const flow=createBatchWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=plan(id);
    if(action==='commit'){value.action='commit';delete value.targets;value.waist_review_ack=calls[calls.length-1].waistReviewAck;
      value.target_outcomes=[{index:1,reviewed_index:1,path:'/target.raw',document_id:targetId,expected_revision:'2',result_revision:'3',outcome:'applied'}];}
    mutate(value);return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`waist-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Waist scalars'});
  return {flow,calls};
}
test('batch refuses missing/stale acknowledgments and forwards exact fourth argument',async()=>{
  const {flow,calls}=batchFixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  await flow.commit();assert.equal(calls.length,1);
  const ack=waistTransferAck([visual()]);await flow.commit(undefined,undefined,undefined,[{...ack[0],after_sha256:'f'.repeat(64)}]);assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,undefined,ack);assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(calls[1].waistReviewAck,ack);assert.notEqual(calls[1].waistReviewAck,ack);
});
test('batch rejects missing evidence, foreign target body, mixed scope and terminal ack substitution',async()=>{
  for(const change of [(v:BatchReply)=>{delete (v.targets![0] as BatchTarget).waist_transfer;},
    (v:BatchReply)=>{(v.targets![0] as BatchTarget).waist_transfer!.body_ref.asset_sha256='f'.repeat(64);},
    (v:BatchReply)=>{v.module_scope!.push('lnx.exposure.v1');}]){
    const {flow,calls}=batchFixture(change);await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit();assert.equal(calls.length,1);
  }
  const {flow}=batchFixture(v=>{if(v.action==='commit')delete v.waist_review_ack;});await flow.start();await flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
});
function presetReview(id:string):PresetReply{return {protocol:1,request_id:id,action:'preflight',success:true,outcome_unknown:false,document_id:'loaded',id:'waist',module_scope:[OP],revision:'2',preflight_token:token,applies:{[OP]:{version:1,amount:.3}},source_proof:proof('2'),waist_transfer:visual('loaded')};}
function presetFixture(mutate:(v:PresetReply)=>void=()=>{}){
  let id='',action='preflight',n=0;const calls:PresetOptions[]=[];
  const flow=createPresetWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=presetReview(id);
    if(action==='apply'){value.action='apply';delete value.waist_transfer;value.waist_review_ack=calls[calls.length-1].waistReviewAck;
      value.before={[OP]:{target_recipe_key:'a'.repeat(64)}};value.after={[OP]:{target_recipe_key:'b'.repeat(64)}};value.doc_state={document_id:'loaded'};}
    mutate(value);return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`preset-${++n}`});flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-2'});return {flow,calls};
}
test('preset requires matching frozen token, context and exact target image pair',async()=>{
  const {flow,calls}=presetFixture();await flow.submit('apply',{id:'waist'},[OP]);assert.equal(calls.length,0);
  await flow.submit('preflight',{id:'waist'},[OP]);assert.equal(flow.snapshot().phase,'done');
  const ack=waistTransferAck([visual('loaded')]);
  for(const options of [{id:'waist',preflightToken:token},{id:'waist',preflightToken:'f'.repeat(32),waistReviewAck:ack},{id:'other',preflightToken:token,waistReviewAck:ack}]){await flow.submit('apply',options,[OP]);assert.equal(calls.length,1);}
  await flow.submit('apply',{id:'waist',preflightToken:token,waistReviewAck:ack},[OP]);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].waistReviewAck,ack);
});
test('preset rejects changed or dismissed review and incomplete body proof',async()=>{
  for(const dismiss of [true,false]){
    const {flow,calls}=presetFixture();await flow.submit('preflight',{id:'waist'},[OP]);
    if(dismiss)flow.dismissReview();else flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-3'});
    await flow.submit('apply',{id:'waist',preflightToken:token,waistReviewAck:waistTransferAck([visual('loaded')])},[OP]);assert.equal(calls.length,1);
  }
  const result=presetReview('p');delete result.waist_transfer;
  assert.throws(()=>validatePresetReply(result,'preflight',{id:'waist',documentId:'loaded'},'p',[OP]));
});
test('waist is only offered as its own reported transferable batch scope',()=>{
  assert.equal(batchScopeOptions([{operation_id:OP,transferable:false}]).some(v=>v.ops.includes(OP)),false);
  const offered=batchScopeOptions([{operation_id:OP,transferable:true},{operation_id:'lnx.exposure.v1',transferable:true}]);
  assert.deepEqual(offered.filter(v=>v.ops.includes(OP)).map(v=>v.ops),[[OP]]);
});
test('unknown batch retains original request and copied ordered acknowledgment across query',async()=>{
  let unknown=true;
  const {flow,calls}=batchFixture(value=>{if(value.action==='commit'&&unknown){value.success=false;value.outcome_unknown=true;value.error='Awaiting original receipt';}});
  await flow.start();const ack=waistTransferAck([visual()]);await flow.commit(undefined,undefined,undefined,ack);
  assert.equal(flow.snapshot().phase,'uncertain');const requestId=calls[1].requestId;
  ack[0].after_sha256='f'.repeat(64);
  flow.close();flow.acknowledgeInspection();await flow.start();await flow.commit(undefined,undefined,undefined,ack);
  assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'uncertain');
  unknown=false;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);assert.equal(calls[1].requestId,requestId);
});
test('changed token, foreign family, changed revision and missing unknown acknowledgment never settle',async()=>{
  const edits=[(v:BatchReply)=>{v.preflight_token='f'.repeat(32);},
    (v:BatchReply)=>{v.module_scope=['lnx.torso_length.v1'];},
    (v:BatchReply)=>{v.waist_review_ack=[{...v.waist_review_ack![0],revision:'9'}];},
    (v:BatchReply)=>{v.success=false;v.outcome_unknown=true;delete v.waist_review_ack;}];
  for(const edit of edits){const {flow,calls}=batchFixture(v=>{if(v.action==='commit')edit(v);});await flow.start();await flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));
    assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'uncertain');await flow.start();assert.equal(calls.length,2);}
});
test('explicit pre-claim batch rejection does not turn into an unknown result',async()=>{
  const {flow}=batchFixture(value=>{if(value.action==='commit'){value.success=false;value.outcome_unknown=false;value.error='Token rejected before mutation';delete value.module_scope;delete value.waist_review_ack;value.target_outcomes=[];}});
  await flow.start();await flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));assert.equal(flow.snapshot().phase,'error');
});
test('preset unknown stays query-only with exact frozen proof and cannot be ended manually',async()=>{
  let unknown=true;
  const {flow,calls}=presetFixture(value=>{if(value.action==='apply'&&unknown){value.success=false;value.outcome_unknown=true;value.error='Awaiting original receipt';delete value.doc_state;delete value.before;delete value.after;}});
  await flow.submit('preflight',{id:'waist'},[OP]);const ack=waistTransferAck([visual('loaded')]);
  await flow.submit('apply',{id:'waist',preflightToken:token,waistReviewAck:ack},[OP]);assert.equal(flow.snapshot().phase,'uncertain');
  ack[0].before_sha256='f'.repeat(64);flow.acknowledgeInspection();flow.dismissReview();
  await flow.submit('preflight',{id:'waist'},[OP]);assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'uncertain');
  unknown=false;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
test('foreign non-null proof is refused, legacy empty foreign slots are not authority',async()=>{
  const accepted=batchFixture(value=>{if(value.targets)(value.targets[0] as unknown as Record<string,unknown>).torso_transfer=null;});
  await accepted.flow.start();assert.equal(accepted.flow.snapshot().phase,'review');
  const refused=batchFixture(value=>{if(value.targets)(value.targets[0] as BatchTarget).torso_transfer=visual();});
  await refused.flow.start();assert.equal(refused.flow.snapshot().phase,'error');
  const mixed=presetFixture();await mixed.flow.submit('save',{id:'waist',name:'mixed',moduleScope:[OP,'lnx.exposure.v1']});assert.equal(mixed.calls.length,0);
});
test('waist success binds frozen row and advancing revision; skipped changed rows stay reported',async()=>{
  for(const patch of [{index:-1},{index:null},{reviewed_index:2},{reviewed_index:undefined},{result_revision:'2'},{result_revision:null}]){
    const {flow}=batchFixture(value=>{if(value.action==='commit')Object.assign(value.target_outcomes![0],patch);});
    await flow.start();await flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
  }
  const skipped=batchFixture(value=>{if(value.action==='commit')Object.assign(value.target_outcomes![0],{index:2,outcome:'skipped',result_revision:'2'});});
  await skipped.flow.start();await skipped.flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));assert.equal(skipped.flow.snapshot().phase,'done');
  const relocated=batchFixture(value=>{if(value.action==='commit')value.target_outcomes![0].index=2;});
  await relocated.flow.start();await relocated.flow.commit(undefined,undefined,undefined,waistTransferAck([visual()]));assert.equal(relocated.flow.snapshot().phase,'done');
});
