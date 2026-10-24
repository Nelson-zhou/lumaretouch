// AUTHORED / UNRUN. Correlated metadata fixtures, never photo/render acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchReply,type BatchTarget,type BatchOptions} from '../batch/batchWorkflow.ts';
import {createPresetWorkflow,type PresetReply,type PresetOptions,validatePresetReply} from '../presets/presetWorkflow.ts';
import {batchScopeOptions} from '../batch/batchScopeOptions.ts';
import {HEAD_TRANSFER_OP as OP,headTransferAck,type HeadTransferEvidence} from './transferModel.ts';
const token='a'.repeat(32),sourceId='b'.repeat(32),targetId='c'.repeat(32);
const proof=(digit:string)=>({asset_sha256:digit.repeat(64),original_sha256:digit.repeat(64),creative_source:null});
const visual=(id=targetId):HeadTransferEvidence=>({version:1,document_id:id,revision:'2',source_proof:proof('2'),
  before_sha256:'3'.repeat(64),candidate_sha256:'4'.repeat(64),before_people_sha256:'5'.repeat(64),candidate_people_sha256:'5'.repeat(64),
  source_size:[32,24],before_output_size:[32,24],after_output_size:[32,24],parameters:{version:1,amount:.3},
  body_ref:{asset_sha256:'2'.repeat(64),body_instance_id:'body:target',analysis_revision:1},
  associated_face:{associated_face_ref:{asset_sha256:'2'.repeat(64),face_instance_id:'face:target',analysis_revision:2},associated_face_box:[.3,.1,.7,.3],associated_face_evidence_sha256:'9'.repeat(64)},
  body_support_sha256:'a'.repeat(64),body_review_sha256:'b'.repeat(64),before_bank_sha256:'c'.repeat(64),candidate_bank_sha256:'d'.repeat(64),
  before:{mime:'image/png',width:32,height:24,sha256:'6'.repeat(64),base64:'iVBORw=='},after:{mime:'image/png',width:32,height:24,sha256:'7'.repeat(64),base64:'iVBORw=='}});
function plan(requestId:string):BatchReply{return {request_id:requestId,action:'preflight',success:true,outcome_unknown:false,preflight_token:token,
  source_snapshot:{document_id:sourceId,revision:'4',path:'/source.raw',source_proof:proof('1')},module_scope:[OP],applies:{[OP]:{version:1,amount:.3}},policy:'skip_and_report',
  targets:[{index:1,path:'/target.raw',document_id:targetId,revision:'2',blocked:null,source_proof:proof('2'),before:{[OP]:{target_recipe_key:'d'.repeat(64)}},head_transfer:visual()}],rejected_docs:[],ok:1,blocked:0};}
function batchFixture(mutate:(v:BatchReply)=>void=()=>{}){
  let id='',action='preflight',n=0;const calls:BatchOptions[]=[];
  const flow=createBatchWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=plan(id);
    if(action==='commit'){value.action='commit';value.batch_id='batch-head-fixture';value.targets=[1];value.head_review_ack=calls[calls.length-1].headReviewAck;
      value.target_outcomes=[{index:1,reviewed_index:1,path:'/target.raw',document_id:targetId,expected_revision:'2',current_revision:'2',result_revision:'3',outcome:'applied'}];}
    mutate(value);return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`head-${++n}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Head scalars'});
  return {flow,calls};
}
test('batch refuses missing/stale acknowledgments and forwards exact fifth argument',async()=>{
  const {flow,calls}=batchFixture();await flow.start();assert.equal(flow.snapshot().phase,'review');
  await flow.commit();assert.equal(calls.length,1);
  const ack=headTransferAck([visual()]);await flow.commit(undefined,undefined,undefined,undefined,[{...ack[0],after_sha256:'f'.repeat(64)}]);assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,undefined,undefined,ack);assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(calls[1].headReviewAck,ack);assert.notEqual(calls[1].headReviewAck,ack);
});
test('batch rejects missing evidence, foreign target body, mixed scope and terminal ack substitution',async()=>{
  for(const change of [(v:BatchReply)=>{delete (v.targets![0] as BatchTarget).head_transfer;},
    (v:BatchReply)=>{(v.targets![0] as BatchTarget).head_transfer!.body_ref.asset_sha256='f'.repeat(64);},
    (v:BatchReply)=>{v.module_scope!.push('lnx.exposure.v1');}]){
    const {flow,calls}=batchFixture(change);await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit();assert.equal(calls.length,1);
  }
  const {flow}=batchFixture(v=>{if(v.action==='commit')delete v.head_review_ack;});await flow.start();await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
});
function presetReview(id:string):PresetReply{return {protocol:1,request_id:id,action:'preflight',success:true,outcome_unknown:false,document_id:'loaded',id:'head',module_scope:[OP],revision:'2',preflight_token:token,applies:{[OP]:{version:1,amount:.3}},source_proof:proof('2'),head_transfer:visual('loaded')};}
function presetFixture(mutate:(v:PresetReply)=>void=()=>{}){
  let id='',action='preflight',n=0;const calls:PresetOptions[]=[];
  const flow=createPresetWorkflow({request:async(next,opts)=>{id=opts.requestId!;action=next;calls.push(opts);return {requested:true};},read:async()=>{
    const value=presetReview(id);
    if(action==='apply'){value.action='apply';delete value.head_transfer;value.head_review_ack=calls[calls.length-1].headReviewAck;
      value.before={[OP]:{target_recipe_key:'a'.repeat(64)}};value.after={[OP]:{target_recipe_key:'b'.repeat(64)}};value.doc_state={document_id:'loaded'};}
    mutate(value);return {phase:'done',request_id:id,result:value};
  }},()=>{},{uuid:()=>`preset-${++n}`});flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-2'});return {flow,calls};
}
test('preset requires matching frozen token, context and exact target image pair',async()=>{
  const {flow,calls}=presetFixture();await flow.submit('apply',{id:'head'},[OP]);assert.equal(calls.length,0);
  await flow.submit('preflight',{id:'head'},[OP]);assert.equal(flow.snapshot().phase,'done');
  const ack=headTransferAck([visual('loaded')]);
  for(const options of [{id:'head',preflightToken:token},{id:'head',preflightToken:'f'.repeat(32),headReviewAck:ack},{id:'other',preflightToken:token,headReviewAck:ack}]){await flow.submit('apply',options,[OP]);assert.equal(calls.length,1);}
  await flow.submit('apply',{id:'head',preflightToken:token,headReviewAck:ack},[OP]);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].headReviewAck,ack);
});
test('preset rejects changed or dismissed review and incomplete body proof',async()=>{
  for(const dismiss of [true,false]){
    const {flow,calls}=presetFixture();await flow.submit('preflight',{id:'head'},[OP]);
    if(dismiss)flow.dismissReview();else flow.updateContext({enabled:true,editable:true,documentId:'loaded',reviewContextKey:'revision-3'});
    await flow.submit('apply',{id:'head',preflightToken:token,headReviewAck:headTransferAck([visual('loaded')])},[OP]);assert.equal(calls.length,1);
  }
  const result=presetReview('p');delete result.head_transfer;
  assert.throws(()=>validatePresetReply(result,'preflight',{id:'head',documentId:'loaded'},'p',[OP]));
});
test('head is only offered as its own reported transferable batch scope',()=>{
  assert.equal(batchScopeOptions([{operation_id:OP,transferable:false}]).some(v=>v.ops.includes(OP)),false);
  const offered=batchScopeOptions([{operation_id:OP,transferable:true},{operation_id:'lnx.exposure.v1',transferable:true}]);
  assert.deepEqual(offered.filter(v=>v.ops.includes(OP)).map(v=>v.ops),[[OP]]);
});
test('unknown batch retains original request and copied ordered acknowledgment across query',async()=>{
  let unknown=true;
  const {flow,calls}=batchFixture(value=>{if(value.action==='commit'&&unknown){value.success=false;value.outcome_unknown=true;value.error='Awaiting original receipt';}});
  await flow.start();const ack=headTransferAck([visual()]);await flow.commit(undefined,undefined,undefined,undefined,ack);
  assert.equal(flow.snapshot().phase,'uncertain');const requestId=calls[1].requestId;
  ack[0].after_sha256='f'.repeat(64);
  flow.close();flow.acknowledgeInspection();await flow.start();await flow.commit(undefined,undefined,undefined,undefined,ack);
  assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'uncertain');
  unknown=false;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);assert.equal(calls[1].requestId,requestId);
});
test('changed token, foreign family, changed revision and missing unknown acknowledgment never settle',async()=>{
  const edits=[(v:BatchReply)=>{v.preflight_token='f'.repeat(32);},
    (v:BatchReply)=>{v.module_scope=['lnx.torso_length.v1'];},
    (v:BatchReply)=>{v.head_review_ack=[{...v.head_review_ack![0],revision:'9'}];},
    (v:BatchReply)=>{v.success=false;v.outcome_unknown=true;delete v.head_review_ack;}];
  for(const edit of edits){const {flow,calls}=batchFixture(v=>{if(v.action==='commit')edit(v);});await flow.start();await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));
    assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'uncertain');await flow.start();assert.equal(calls.length,2);}
});
test('explicit pre-claim batch rejection does not turn into an unknown result',async()=>{
  const {flow}=batchFixture(value=>{if(value.action==='commit'){value.success=false;value.outcome_unknown=false;value.error='Token rejected before mutation';delete value.module_scope;delete value.head_review_ack;delete value.batch_id;delete value.targets;value.target_outcomes=[];}});
  await flow.start();await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(flow.snapshot().phase,'error');
});
test('preset unknown stays query-only with exact frozen proof and cannot be ended manually',async()=>{
  let unknown=true;
  const {flow,calls}=presetFixture(value=>{if(value.action==='apply'&&unknown){value.success=false;value.outcome_unknown=true;value.error='Awaiting original receipt';delete value.doc_state;delete value.before;delete value.after;}});
  await flow.submit('preflight',{id:'head'},[OP]);const ack=headTransferAck([visual('loaded')]);
  await flow.submit('apply',{id:'head',preflightToken:token,headReviewAck:ack},[OP]);assert.equal(flow.snapshot().phase,'uncertain');
  ack[0].before_sha256='f'.repeat(64);flow.acknowledgeInspection();flow.dismissReview();
  await flow.submit('preflight',{id:'head'},[OP]);assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'uncertain');
  unknown=false;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
test('foreign non-null proof is refused, legacy empty foreign slots are not authority',async()=>{
  const accepted=batchFixture(value=>{if(value.targets)(value.targets[0] as unknown as Record<string,unknown>).torso_transfer=null;});
  await accepted.flow.start();assert.equal(accepted.flow.snapshot().phase,'review');
  const refused=batchFixture(value=>{if(value.targets)(value.targets[0] as BatchTarget).torso_transfer=visual();});
  await refused.flow.start();assert.equal(refused.flow.snapshot().phase,'error');
  const mixed=presetFixture();await mixed.flow.submit('save',{id:'head',name:'mixed',moduleScope:[OP,'lnx.exposure.v1']});assert.equal(mixed.calls.length,0);
});
test('head success binds frozen row and advancing revision; skipped changed rows stay reported',async()=>{
  for(const patch of [{index:-1},{index:null},{index:Number.MAX_SAFE_INTEGER+1},{reviewed_index:2},{reviewed_index:undefined},{result_revision:'2'},{result_revision:'03'},{result_revision:null}]){
    const {flow}=batchFixture(value=>{if(value.action==='commit')Object.assign(value.target_outcomes![0],patch);});
    await flow.start();await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
  }
  const skipped=batchFixture(value=>{if(value.action==='commit'){Object.assign(value.target_outcomes![0],{index:2,outcome:'skipped',result_revision:'2'});value.targets=[];}});
  await skipped.flow.start();await skipped.flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(skipped.flow.snapshot().phase,'done');
  const relocated=batchFixture(value=>{if(value.action==='commit'){value.target_outcomes![0].index=2;value.targets=[2];}});
  await relocated.flow.start();await relocated.flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(relocated.flow.snapshot().phase,'done');
});

test('head refuses signed amounts, foreign waist evidence and waist acknowledgments',async()=>{
  for(const change of [(value:BatchReply)=>{value.applies![OP]={version:1,amount:-.25};(value.targets![0] as BatchTarget).head_transfer!.parameters.amount=-.25;},
    (value:BatchReply)=>{(value.targets![0] as BatchTarget).waist_transfer=visual();},
    (value:BatchReply)=>{value.applies![OP]={version:1,amount:.3,pivot:[.5,.2]};}]){
    const {flow,calls}=batchFixture(change);await flow.start();assert.equal(flow.snapshot().phase,'error');assert.equal(calls.length,1);
  }
  const {flow,calls}=batchFixture();await flow.start();const ack=headTransferAck([visual()]);
  await flow.commit(undefined,undefined,undefined,ack);assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,undefined,ack,ack);assert.equal(calls.length,1);
  await flow.commit(undefined,undefined,undefined,undefined,ack);assert.equal(calls.length,2);
});

test('head never settles contradictory terminal flags, even on explicit claim rejection',async()=>{
  for(const patch of [{requires_readback:true},{requires_reload:true},{status:'running'},{phase:'pending'},{phase:'accepted'},{requires_readback:'yes'},{phase:1}]){
    for(const reject of [false,true]){
      const {flow,calls}=batchFixture(value=>{if(value.action==='commit'){
        Object.assign(value,patch);
        if(reject){value.success=false;value.outcome_unknown=false;value.error='Claim rejected';delete value.module_scope;delete value.head_review_ack;delete value.batch_id;delete value.targets;value.target_outcomes=[];}
      }});
      await flow.start();await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));
      assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();await flow.start();assert.equal(calls.length,2);
      const preset=presetFixture(value=>{if(value.action==='apply'){
        Object.assign(value,patch);
        if(reject){value.success=false;value.outcome_unknown=false;value.error='Claim rejected';delete value.module_scope;delete value.head_review_ack;delete value.before;delete value.after;delete value.doc_state;}
      }});
      await preset.flow.submit('preflight',{id:'head'},[OP]);
      await preset.flow.submit('apply',{id:'head',preflightToken:token,headReviewAck:headTransferAck([visual('loaded')])},[OP]);
      assert.equal(preset.flow.snapshot().phase,'uncertain');preset.flow.acknowledgeInspection();assert.equal(preset.flow.snapshot().phase,'uncertain');
    }
  }
});

test('head rejects too many targets before queueing or silently truncating the review',async()=>{
  const {flow,calls}=batchFixture();
  flow.updateContext({docs:Array.from({length:9},(_,i)=>`/target-${i}.raw`),moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Head shrink'});
  await flow.start();assert.equal(flow.snapshot().phase,'error');assert.equal(calls.length,0);
});

test('two-target head commit binds ordered acknowledgment, original reviewed rows and distinct relocated rows',async()=>{
  const secondId='e'.repeat(32),second=visual(secondId);
  for(const mutation of ['none','reverse_ack','duplicate_applied_row','changed_reviewed_index']){
    const {flow}=batchFixture(value=>{
      value.ok=2;
      if(value.action==='preflight')value.targets!.push({...(value.targets![0] as BatchTarget),index:2,path:'/second.raw',document_id:secondId,head_transfer:second});
      else if(value.action==='commit'){
        value.target_outcomes![0].index=3;
        value.target_outcomes!.push({index:4,reviewed_index:2,path:'/second.raw',document_id:secondId,expected_revision:'2',current_revision:'2',result_revision:'4',outcome:'applied'});
        value.targets=[3,4];
        if(mutation==='reverse_ack')value.head_review_ack=[...value.head_review_ack!].reverse();
        if(mutation==='duplicate_applied_row')value.target_outcomes![1].index=3;
        if(mutation==='changed_reviewed_index')value.target_outcomes![1].reviewed_index=3;
      }
    });
    flow.updateContext({docs:['/target.raw','/second.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Head shrink'});
    await flow.start();assert.equal(flow.snapshot().phase,'review');
    await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual(),second]));
    assert.equal(flow.snapshot().phase,mutation==='none'?'done':'uncertain');
  }
});

test('head success needs batch identity, current applied revisions and exact applied row inventory',async()=>{
  for(const mutate of [(value:BatchReply)=>{delete value.batch_id;},(value:BatchReply)=>{delete value.targets;},
    (value:BatchReply)=>{value.targets=[2];},(value:BatchReply)=>{value.target_outcomes![0].current_revision='1';},
    (value:BatchReply)=>{value.target_outcomes![0].blocked='No valid target support';},
    (value:BatchReply)=>{value.target_outcomes![0].waist_transfer=visual();}]){
    const {flow}=batchFixture(value=>{if(value.action==='commit')mutate(value);});await flow.start();
    await flow.commit(undefined,undefined,undefined,undefined,headTransferAck([visual()]));assert.equal(flow.snapshot().phase,'uncertain');
  }
});

test('head preflight binds expected scope without inventing preset authority and can abandon a read-only unknown',async()=>{
  let unknown=true;
  const {flow,calls}=presetFixture(value=>{if(value.action==='preflight'&&unknown){value.success=false;value.outcome_unknown=true;value.error='Read-only preflight unavailable';delete value.head_transfer;}});
  await flow.submit('preflight',{id:'head',moduleScope:['lnx.waist_length.v1']},[OP]);assert.equal(calls.length,0);
  await flow.submit('preflight',{id:'head'},[OP]);assert.deepEqual(calls[0].moduleScope,[OP]);assert.equal(flow.snapshot().phase,'uncertain');
  const first=calls[0].requestId;flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'idle');
  unknown=false;await flow.submit('preflight',{id:'head'},[OP]);assert.equal(calls.length,2);assert.notEqual(calls[1].requestId,first);
  assert.equal(flow.snapshot().phase,'done');
  await flow.submit('apply',{id:'head',preflightToken:token,headReviewAck:headTransferAck([visual('loaded')])},[OP]);
  assert.equal(calls[2].moduleScope,undefined);assert.equal(flow.snapshot().phase,'done');
});

test('head batch read-only transport unknown can be abandoned, unlike an uncertain commit',async()=>{
  let unknown=true,id='',sequence=0;const requests:BatchOptions[]=[];
  const flow=createBatchWorkflow({request:async(_action,options)=>{id=options.requestId!;requests.push(options);return {requested:true};},
    read:async()=>unknown?{phase:'unavailable',request_id:id,error:'Read-only result not available'}:{phase:'done',request_id:id,result:plan(id)}},()=>{},{uuid:()=>`read-${++sequence}`});
  flow.updateContext({docs:['/target.raw'],moduleScope:[OP],conflictPolicy:'skip_and_report',sourceDocumentId:sourceId,enabled:true,label:'Head shrink'});
  await flow.start();assert.equal(flow.snapshot().phase,'uncertain');flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'closed');
  unknown=false;await flow.start();assert.equal(flow.snapshot().phase,'review');assert.equal(requests.length,2);assert.notEqual(requests[0].requestId,requests[1].requestId);
});
