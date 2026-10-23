// AUTHORED / UNRUN. Source-only preset review fixtures, not visual acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPresetWorkflow,validatePresetReply,type PresetTransport,type PresetOptions,type PresetReply} from '../presets/presetWorkflow.ts';
import {shadowTransferAck,type ShadowTransferEvidence} from './transferModel.ts';
const op='lnx.hsl.v1',modules={[op]:{recipe:{version:1}}};
const context={enabled:true,editable:true,documentId:'doc-1'};
const tick=()=>new Promise<void>(r=>setImmediate(r));
function fixture(patch:Partial<PresetTransport>={},timeoutMs=5000){
  let n=0,time=0;const calls:Array<{action:string;options:PresetOptions}>=[],replies=new Map<string,PresetReply>();
  const api:PresetTransport={request:async(action,options)=>{
    calls.push({action,options});const id=options.requestId!;
    replies.set(id,{protocol:1,request_id:id,action,success:true,outcome_unknown:false,document_id:options.documentId,
      id:options.id??'imported',name:options.name??'示例',path:'/presets/p.json',module_scope:[op],before:modules,after:modules,
      doc_state:{document_id:options.documentId},preset:{schema:'lrt.preset.v1',id:options.id??'imported',name:options.name??'示例',kind:'custom',builtin:false,modules},
      catalog:{available:true,list:[],errors:[],modules:[],dir:'/presets',schema:'lrt.preset.v1'}});
    return {requested:true};},read:async id=>({phase:'done',request_id:id,result:replies.get(id)}),...patch};
  const flow=createPresetWorkflow(api,()=>{},{uuid:()=>`r${++n}`,now:()=>time,pause:async()=>{time+=10;await tick();},timeoutMs});
  flow.updateContext(context);return {flow,calls,api,replies};
}
// AUTHORED / UNRUN: protocol metadata fixtures, not renderer or browser visual acceptance.
const shadowOp='lnx.original_shadow.v1',shadowParams={enabled:true,strength:40,blend:'normal' as const};
const shadowVisual=():ShadowTransferEvidence=>({version:1,document_id:'doc-1',revision:'4',
  source_proof:{asset_sha256:'a'.repeat(64),original_sha256:'a'.repeat(64),creative_source:null},
  before_sha256:'b'.repeat(64),candidate_sha256:'c'.repeat(64),before_people_sha256:'d'.repeat(64),candidate_people_sha256:'d'.repeat(64),
  source_size:[12,8],before_output_size:[12,8],after_output_size:[12,8],parameters:{...shadowParams},
  before:{mime:'image/png',width:12,height:8,sha256:'e'.repeat(64),base64:'iVBORw=='},
  after:{mime:'image/png',width:12,height:8,sha256:'f'.repeat(64),base64:'iVBORw=='}});
const shadowPreflight=(requestId='shadow-review'):PresetReply=>({protocol:1,request_id:requestId,action:'preflight',success:true,
  outcome_unknown:false,document_id:'doc-1',id:'shadow',module_scope:[shadowOp],revision:'4',
  preflight_token:'1'.repeat(32),applies:{[shadowOp]:{...shadowParams}},source_proof:shadowVisual().source_proof,shadow_transfer:shadowVisual()});
function shadowFixture(){
  const value=fixture();
  value.api.read=async id=>{
    const request=value.calls.find(call=>call.options.requestId===id)!;
    const result=request.action==='preflight'?shadowPreflight(id):{...value.replies.get(id)!,module_scope:[shadowOp],
      preflight_token:request.options.preflightToken,before:{[shadowOp]:{...shadowParams}},after:{[shadowOp]:{...shadowParams}}};
    return {phase:'done',request_id:id,result};
  };return value;
}
test('shadow preflight requires matching source, target, scalars and bounded visual proof',()=>{
  const opts={id:'shadow',documentId:'doc-1'};
  assert.doesNotThrow(()=>validatePresetReply(shadowPreflight(),'preflight',opts,'shadow-review',[shadowOp]));
  const changes:Array<(reply:PresetReply)=>void>=[
    reply=>{delete reply.source_proof;},reply=>{delete reply.shadow_transfer;},
    reply=>{reply.source_proof={asset_sha256:'b'.repeat(64),original_sha256:'a'.repeat(64),creative_source:null};},
    reply=>{reply.shadow_transfer!.document_id='another-load-id';},
    reply=>{reply.shadow_transfer!.revision='3';},
    reply=>{reply.shadow_transfer!.parameters.strength=41;},
    reply=>{reply.applies![shadowOp]={...shadowParams,coverage:null};},
    reply=>{reply.shadow_transfer!.after.base64='iVBOR'+'A'.repeat(200003);},
  ];
  for(const change of changes){const reply=shadowPreflight();change(reply);
    assert.throws(()=>validatePresetReply(reply,'preflight',opts,'shadow-review',[shadowOp]));}
  const derived=shadowPreflight(),source={asset_sha256:'b'.repeat(64),original_sha256:'a'.repeat(64),creative_source:{sha256:'b'.repeat(64),width:12,height:8}};
  derived.source_proof=source;derived.shadow_transfer!.source_proof=source;
  assert.doesNotThrow(()=>validatePresetReply(derived,'preflight',opts,'shadow-review',[shadowOp]));
});
test('shadow apply waits for exactly the displayed PNG pair acknowledgment',async()=>{
  const {flow,calls}=shadowFixture();
  await flow.submit('apply',{id:'shadow'},[shadowOp]);assert.equal(calls.length,0);
  await flow.submit('preflight',{id:'shadow'},[shadowOp]);assert.equal(flow.snapshot().phase,'done');
  const review=flow.snapshot().result!,ack=shadowTransferAck([review.shadow_transfer!]);
  await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token},[shadowOp]);assert.equal(calls.length,1);
  await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token,shadowReviewAck:[]},[shadowOp]);assert.equal(calls.length,1);
  await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token,shadowReviewAck:[{...ack[0],after_sha256:review.shadow_transfer!.candidate_sha256}]},[shadowOp]);assert.equal(calls.length,1);
  await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token,shadowReviewAck:ack},[shadowOp]);
  assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1].options.shadowReviewAck,ack);
  assert.notEqual(calls[1].options.shadowReviewAck,ack);
});
test('dismissed or changed-context shadow preflight cannot apply an old acknowledgment',async()=>{
  for(const dismiss of [true,false]){
    const {flow,calls}=shadowFixture();await flow.submit('preflight',{id:'shadow'},[shadowOp]);const review=flow.snapshot().result!;
    const ack=shadowTransferAck([review.shadow_transfer!]);
    if(dismiss)flow.dismissReview();else flow.updateContext({...context,reviewContextKey:'changed-photo-revision'});
    await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token,shadowReviewAck:ack},[shadowOp]);assert.equal(calls.length,1);
  }
});
test('shadow cannot borrow another preset, token or target review for apply',async()=>{
  for(const patch of [{id:'other'},{preflightToken:'2'.repeat(32)},
    {shadowReviewAck:[{...shadowTransferAck([shadowVisual()])[0],document_id:'other'}]}]){
    const {flow,calls}=shadowFixture();await flow.submit('preflight',{id:'shadow'},[shadowOp]);const review=flow.snapshot().result!;
    await flow.submit('apply',{id:'shadow',preflightToken:review.preflight_token,shadowReviewAck:shadowTransferAck([review.shadow_transfer!]),...patch},[shadowOp]);
    assert.equal(calls.length,1);
  }
});
