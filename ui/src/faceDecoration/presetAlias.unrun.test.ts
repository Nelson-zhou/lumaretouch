// AUTHORED / UNRUN. Synthetic protocol fixtures only; not build, rendering, or photograph-quality evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {presetFixture} from '../collarbone/presetFixture';
import {canonical} from './model';
import {OP,decorationPresetAck,sameDecorationPresetAck,validDecorationPreset,verifyDecorationPreset,type DecorationPresetV1,type DecorationPresetV2} from './transferModel';
import {observeDecorationPresetAliasHistory,decorationPresetAliasHistoryClass,decorationPresetAliasMarker,decorationPresetAliasWritePending,setDecorationPresetAliasWritePending,subscribeDecorationPresetAliasWrites} from './presetAliasHistoryRegistry';
import {validatePresetReply,createPresetWorkflow,type PresetReply} from '../presets/presetWorkflow';
import {createBatchWorkflow} from '../batch/batchWorkflow';
function decorationFixture():DecorationPresetV1{const base=presetFixture();return {...base,coverage:{version:1,support_transfer:'none',targets:[{face_ref:base.face_ref,scope:'target-reviewed-visible-skin',visibility_sha256:'c'.repeat(64),recipe_sha256:'d'.repeat(64)}]}};}
const sha=(value:unknown)=>createHash('sha256').update(canonical(value)).digest('hex');
function fixture(){
 const base=decorationFixture();assert.equal(base.version,1);
 const active=structuredClone(base.visual);active.coverage_sha256=sha(base.coverage);
 const sibling={...structuredClone(active),document_id:'9'.repeat(32),revision:'9',candidate_state_sha256:active.before_state_sha256,after_output_size:active.before_output_size};
 const review:DecorationPresetV2={...base,version:2,visual:active,owner:{...base.owner,people_scope:'project'},members:[
  {path:'/shared/source.png',role:'active',visual:active},{path:'/shared/source.png',role:'sibling',visual:sibling}],review_sha256:'',before_bank_sha256:'1'.repeat(64)};
 const {review_sha256:_,...identity}=review;review.review_sha256=sha(identity);
 const ops=[OP,'lnx.hsl.v1'],token='f'.repeat(32),ack=decorationPresetAck(review),marker=decorationPresetAliasMarker(review,ops);
 const preflight:PresetReply={protocol:1,request_id:'review',action:'preflight',success:true,outcome_unknown:false,id:'preset',document_id:review.load_id,
  revision:review.visual.revision,source_proof:review.owner.source_proof,preflight_token:token,module_scope:ops,applies:{[OP]:{version:1,pattern:'freckle_dust',strength:.5},'lnx.hsl.v1':{}},face_decoration_visual_required:true,face_decoration_preset:review};
 const success:PresetReply={protocol:1,request_id:'apply',action:'apply',success:true,outcome_unknown:false,id:'preset',document_id:review.load_id,
  preflight_token:token,module_scope:ops,face_decoration_visual_required:true,face_decoration_preset_ack:ack,batch_id:'preset-alias-batch',face_decoration_preset_alias_review:marker,
  alias_members:review.members.map(({visual})=>({document_id:visual.document_id,expected_revision:visual.revision,result_revision:String(BigInt(visual.revision)+1n)})),
  before:{[OP]:{},'lnx.hsl.v1':{}},after:{[OP]:{},'lnx.hsl.v1':{}},
  doc_state:{document_id:review.load_id,people:{binding:{document_id:active.document_id,document_revision:Number(BigInt(active.revision)+1n)}}}};
 return {review,ops,token,ack,marker,preflight,success};
}
test('v2 binds all independent member visuals but allows distinct document aliases with identical paths',async()=>{
 const f=fixture();assert.ok(validDecorationPreset(f.review,f.review.load_id,f.review.visual.revision,f.review.owner.source_proof));
 assert.ok(await verifyDecorationPreset(f.review));
 const bad=structuredClone(f.review);bad.members[1].visual.document_id=bad.members[0].visual.document_id;
 assert.equal(validDecorationPreset(bad,bad.load_id,bad.visual.revision,bad.owner.source_proof),false);
 const changed=structuredClone(f.review);changed.members[1].visual.candidate_state_sha256='e'.repeat(64);
 assert.equal(validDecorationPreset(changed,changed.load_id,changed.visual.revision,changed.owner.source_proof),false);
 const drift=structuredClone(f.review);drift.members[1].path='/different/path.png';assert.equal(await verifyDecorationPreset(drift),false);
 const single=decorationFixture();assert.ok(validDecorationPreset(single,single.load_id,single.visual.revision,single.owner.source_proof));
});
test('ordered all-member ACK cannot be replaced with one image or reversed members',()=>{
 const f=fixture();assert.ok('members'in f.ack);if(!('members'in f.ack))return;
 assert.ok(sameDecorationPresetAck(f.ack,decorationPresetAck(f.review)));
 assert.equal(sameDecorationPresetAck({...f.ack,members:[...f.ack.members].reverse()},f.ack),false);
 assert.equal(sameDecorationPresetAck({...f.ack,members:f.ack.members.slice(0,1)},f.ack),false);
 assert.equal(sameDecorationPresetAck({...f.ack,replace_legacy:true},f.ack),false);
});
test('success requires exact composite marker, current binding, ordered +1 publication and complete mixed scope',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 assert.doesNotThrow(()=>validatePresetReply(f.success,'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:null},{alias_members:f.success.alias_members!.slice(0,1)},
  {alias_members:[...f.success.alias_members!].reverse()},{face_decoration_preset_alias_review:{...f.marker,selected_modules:[OP]}},
  {doc_state:{document_id:f.review.load_id,people:{binding:{document_id:'elsewhere',document_revision:1}}}}])
  assert.throws(()=>validatePresetReply({...f.success,...patch},'apply',opts,'apply',f.ops));
});
test('unknown apply retains fence and original query identity; matching full result alone releases it',async()=>{
 const f=fixture();let sends=0,done=false;const ids=['review','apply'];
 const flow=createPresetWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:request_id==='review'?f.preflight:done?f.success:{
  protocol:1,request_id,action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,preflight_token:f.token,module_scope:f.ops,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,batch_id:f.success.batch_id,error:'unknown after claim'}})},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset'},f.ops);
 await flow.submit('apply',{id:'preset',preflightToken:f.token,faceDecorationPresetAck:f.ack},f.ops);
 assert.equal(flow.snapshot().phase,'uncertain');assert.equal(decorationPresetAliasWritePending(),true);
 flow.acknowledgeInspection();await flow.submit('apply',{id:'preset',preflightToken:f.token,faceDecorationPresetAck:f.ack},f.ops);assert.equal(sends,2);
 done=true;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(decorationPresetAliasWritePending(),false);assert.equal(sends,2);
});
test('reopened exact composite marker fences partial/foreign history without creating another history controller',async()=>{
 const f=fixture(),batch_id='reopened-preset-alias';
 observeDecorationPresetAliasHistory({workspace_generation:'preset-history-epoch',batches:[{batch_id,targets:2,module_scope:['lnx.people_graph.v1'],face_decoration_preset_alias_review:f.marker}]});
 assert.equal(decorationPresetAliasHistoryClass(batch_id)?.memberCount,2);
 let sends=0,complete=false;const flow=createBatchWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:{
  request_id,action:'undo',success:true,outcome_unknown:false,batch_id,module_scope:['lnx.people_graph.v1'],face_decoration_preset_alias_review:f.marker,restored:complete?[0,3]:[0],conflicts:[]}})},()=>{});
 await flow.undo(batch_id);assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().queryOnly,true);
 flow.close();flow.acknowledgeInspection();await flow.redo(batch_id);assert.equal(sends,1);
 complete=true;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(sends,1);
 observeDecorationPresetAliasHistory({workspace_generation:'preset-history-epoch',batches:[{batch_id,face_decoration_preset_alias_review:null}]});
 assert.equal(decorationPresetAliasHistoryClass(batch_id)?.memberCount,null);
});
test('visible member ACK requires actual independent load, decode and hash plus aggregate readiness',()=>{
 const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
 const panel=read('./DecorationPresetReview.tsx'),transport=read('./visualTransport.ts');
 for(const text of ['await image.decode()','loaded.before&&loaded.after','ready&&checked','members.every','memberDocumentId:visual.document_id','读取本成员实际完整前后图像'])assert.ok(panel.includes(text));
 assert.ok(transport.includes('r.member_document_id!==request.memberDocumentId'));
 assert.ok(transport.includes('await verifyCollarboneImage(r.image)'));
 assert.ok(read('../people/usePeopleWorkflow.ts').includes("historyKind==='face_decoration_preset_alias'"));
 assert.ok(read('../presets/PresetPanel.tsx').includes('w.ui.submitted?.options.faceDecorationPresetAck===undefined'));
});

test('only verified workspace replacement retires an old-epoch pending fence and notifies people controls',()=>{
 observeDecorationPresetAliasHistory({workspace_generation:'old-preset-epoch',batches:[]});
 let changes=0;const unsubscribe=subscribeDecorationPresetAliasWrites(()=>{changes++;});
 setDecorationPresetAliasWritePending('old-request',true,'old-preset-epoch');
 observeDecorationPresetAliasHistory({workspace_generation:'old-preset-epoch',batches:[]});
 assert.equal(decorationPresetAliasWritePending(),true);assert.equal(changes,1);
 // A request already associated with the newly verified workspace is not stale.
 setDecorationPresetAliasWritePending('new-request',true,'new-preset-epoch');
 observeDecorationPresetAliasHistory({workspace_generation:'new-preset-epoch',batches:[]});
 assert.equal(decorationPresetAliasWritePending(),true);assert.equal(changes,3);
 setDecorationPresetAliasWritePending('new-request',false);assert.equal(decorationPresetAliasWritePending(),false);
 unsubscribe();
});

test('known post-ledger publication is retained as UNKNOWN diagnostics, never completed or replayed',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 const {before:_,after:__,doc_state:___,...publication}=f.success;
 const unknown:PresetReply={...publication,success:false,outcome_unknown:true,error:'published; final state uncertain'};
 assert.doesNotThrow(()=>validatePresetReply(unknown,'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,alias_members:unknown.alias_members!.slice(0,1)},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,face_decoration_preset_alias_review:{...f.marker,member_count:3}},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,outcome_unknown:false},'apply',opts,'apply',f.ops));
});
test('exact unclaimed v2 ACK can be refused without stored scope but never with publication claims',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 const refused:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:false,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,error:'expired before claim'};
 assert.doesNotThrow(()=>validatePresetReply(refused,'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:null},{operation_committed:true},{module_scope:[OP]},
  {preflight_token:'wrong'},{face_decoration_preset_ack:{...f.ack,replace_legacy:true}}])
  assert.throws(()=>validatePresetReply({...refused,...patch},'apply',opts,'apply',f.ops));
});
test('verified project replacement retires exact old preset request as UNKNOWN and ignores its late callback',async()=>{
 const f=fixture(),epoch=f.review.owner.document.epoch;observeDecorationPresetAliasHistory({workspace_generation:epoch,batches:[]});
 let publish!: (value:{phase:string;request_id:string;result:PresetReply})=>void,started!:()=>void;
 const begun=new Promise<void>(resolve=>{started=resolve;}),late=new Promise<{phase:string;request_id:string;result:PresetReply}>(resolve=>{publish=resolve;});
 const ids=['review','apply'];
 const flow=createPresetWorkflow({request:async()=>({requested:true}),read:async request_id=>{
  if(request_id==='review')return {phase:'done',request_id,result:f.preflight};started();return late;
 }},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset'},f.ops);
 const applying=flow.submit('apply',{id:'preset',preflightToken:f.token,faceDecorationPresetAck:f.ack},f.ops);await begun;
 observeDecorationPresetAliasHistory({workspace_generation:epoch,batches:[]});assert.equal(flow.snapshot().phase,'working');
 observeDecorationPresetAliasHistory({workspace_generation:'verified-reopened-preset-epoch',batches:[]});
 assert.equal(flow.snapshot().phase,'error');assert.match(flow.snapshot().message,/结果仍未知/);assert.equal(decorationPresetAliasWritePending(),false);
 publish({phase:'done',request_id:'apply',result:f.success});await applying;
 assert.equal(flow.snapshot().phase,'error');assert.equal(flow.snapshot().result,null);flow.dispose();
});
test('only composite history requests retire on verified replacement of their captured workspace',async()=>{
 const f=fixture(),batch_id='recover-preset-history',workspace_generation='history-before-reopen';
 observeDecorationPresetAliasHistory({workspace_generation,batches:[{batch_id,targets:2,module_scope:['lnx.people_graph.v1'],face_decoration_preset_alias_review:f.marker}]});
 const flow=createBatchWorkflow({request:async()=>({requested:true}),read:async request_id=>({phase:'done',request_id,result:{request_id,action:'undo',success:false,outcome_unknown:true,batch_id,error:'unknown undo'}})},()=>{});
 await flow.undo(batch_id);assert.equal(flow.snapshot().phase,'uncertain');
 observeDecorationPresetAliasHistory({workspace_generation,batches:[]});assert.equal(flow.snapshot().phase,'uncertain');
 observeDecorationPresetAliasHistory({workspace_generation:'history-verified-reopen',batches:[]});
 assert.equal(flow.snapshot().phase,'error');assert.match(flow.snapshot().message,/结果仍未知/);assert.equal(flow.snapshot().result,null);flow.dispose();
});

test('supplementary mixed ACKs must retain exact presence and ordered values even in no-write refusal',()=>{
 const f=fixture(),spill=[{document_id:'load',revision:'1',before_sha256:'a'.repeat(64),after_sha256:'b'.repeat(64)}];
 const opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack,spillReviewAck:spill};
 const refused:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:false,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,error:'expired before claim'};
 assert.throws(()=>validatePresetReply(refused,'apply',opts,'apply',f.ops));
 assert.doesNotThrow(()=>validatePresetReply({...refused,...{spill_review_ack:spill}},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...refused,...{spill_review_ack:[]}},'apply',opts,'apply',f.ops));
});

test('native identity-only unknown may omit actual scope but never carries unproven publication',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 const unknown:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,error:'native outcome unknown'};
 assert.doesNotThrow(()=>validatePresetReply(unknown,'apply',opts,'apply',f.ops));
 assert.doesNotThrow(()=>validatePresetReply({...unknown,batch_id:'known-ledger-id'},'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:''},{batch_id:null},{face_decoration_preset_alias_review:f.marker},{alias_members:f.success.alias_members},
  {doc_state:f.success.doc_state},{operation_committed:true},{face_decoration_preset_ack:{...f.ack,replace_legacy:true}}])
  assert.throws(()=>validatePresetReply({...unknown,...patch},'apply',opts,'apply',f.ops));
});

test('batch-ID-only unknown is retained but never manufactures a composite marker or actual scope',async()=>{
 const f=fixture(),batch_id='diagnostic-only-preset-batch';
 observeDecorationPresetAliasHistory({workspace_generation:f.review.owner.document.epoch,batches:[]});
 const unknown:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,batch_id,error:'ledger ID known; full publication proof unavailable'};
 const ids=['review','apply'];let sends=0;
 const flow=createPresetWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:request_id==='review'?f.preflight:unknown})},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset'},f.ops);
 await flow.submit('apply',{id:'preset',preflightToken:f.token,faceDecorationPresetAck:f.ack},f.ops);
 assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().result?.batch_id,batch_id);assert.equal(decorationPresetAliasWritePending(),true);
 assert.equal(Object.hasOwn(flow.snapshot().result!,'module_scope'),false);assert.equal(Object.hasOwn(flow.snapshot().result!,'face_decoration_preset_alias_review'),false);
 assert.equal(decorationPresetAliasHistoryClass(batch_id),undefined);
 flow.acknowledgeInspection();await flow.submit('apply',{id:'preset',preflightToken:f.token,faceDecorationPresetAck:f.ack},f.ops);assert.equal(sends,2);
 const opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 assert.doesNotThrow(()=>validatePresetReply({...unknown,module_scope:f.ops},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,module_scope:[OP]},'apply',opts,'apply',f.ops));
 observeDecorationPresetAliasHistory({workspace_generation:'diagnostic-only-reopened-workspace',batches:[]});flow.dispose();
});

test('bank digest, distinct member geometry and independently valid source provenance are frozen',async()=>{
 const f=fixture(),changed=structuredClone(f.review);
 changed.before_bank_sha256='2'.repeat(64);assert.equal(await verifyDecorationPreset(changed),false);
 assert.equal(validDecorationPreset({...f.review,before_bank_sha256:undefined},f.review.load_id,f.review.visual.revision,f.review.owner.source_proof),false);
 const derived=structuredClone(f.review);
 for(const member of derived.members){member.visual.source_proof.creative_source={sha256:member.visual.source_proof.asset_sha256,width:1,height:1};}
 derived.visual=structuredClone(derived.members[0].visual);derived.owner.source_proof=structuredClone(derived.visual.source_proof);
 derived.members[1].visual.source_proof.original_sha256='e'.repeat(64);
 assert.ok(validDecorationPreset(derived,derived.load_id,derived.visual.revision,derived.owner.source_proof));
 derived.members[1].visual.source_proof.creative_source=null;
 assert.equal(validDecorationPreset(derived,derived.load_id,derived.visual.revision,derived.owner.source_proof),false);
 for(const mutate of [(v:DecorationPresetV2)=>{v.members=v.members.slice(0,1);},(v:DecorationPresetV2)=>{v.members[1].role='active';},
  (v:DecorationPresetV2)=>{v.members[1].visual.after_output_size=[2,1];},(v:DecorationPresetV2)=>{v.members[1].visual.coverage_sha256='f'.repeat(64);},
  (v:DecorationPresetV2)=>{v.members[1].visual.revision=String(Number.MAX_SAFE_INTEGER);}]){
  const value=structuredClone(f.review);mutate(value);assert.equal(validDecorationPreset(value,value.load_id,value.visual.revision,value.owner.source_proof),false);
 }
});
test('retained decoration can review a full selected non-decoration recipe without fabricating selection',()=>{
 const f=fixture(),module_scope=['lnx.hsl.v1'];
 const preflight={...f.preflight,module_scope,applies:{'lnx.hsl.v1':{version:1}}};
 assert.doesNotThrow(()=>validatePresetReply(preflight,'preflight',{id:'preset',documentId:f.review.load_id},'review',module_scope));
 const marker=decorationPresetAliasMarker(f.review,module_scope);
 const result={...f.success,module_scope,face_decoration_preset_alias_review:marker,before:{'lnx.hsl.v1':{}},after:{'lnx.hsl.v1':{}}};
 assert.doesNotThrow(()=>validatePresetReply(result,'apply',{id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack},'apply',module_scope));
});
test('new marker rejects over32 modules, C1 control IDs and conflicting family ownership',()=>{
 const f=fixture(),workspace_generation='decoration-marker-bounds';
 for(const [index,patch] of [{selected_modules:Array.from({length:33},(_,i)=>`lnx.module_${i}.v1`)},{selected_modules:['lnx.hsl.v1\u0085']},{selected_modules:['lnx.people_graph.v1']}].entries()){
  const batch_id=`invalid-${index}`;observeDecorationPresetAliasHistory({workspace_generation,batches:[{batch_id,targets:2,module_scope:['lnx.people_graph.v1'],face_decoration_preset_alias_review:{...f.marker,...patch}}]});
  assert.equal(decorationPresetAliasHistoryClass(batch_id)?.marker,null);
 }
 observeDecorationPresetAliasHistory({workspace_generation,batches:[{batch_id:'cross-family',targets:2,module_scope:['lnx.people_graph.v1'],face_decoration_preset_alias_review:f.marker,face_decoration_support_alias_review:{version:1,review_sha256:f.marker.review_sha256,member_count:2}}]});
 assert.equal(decorationPresetAliasHistoryClass('cross-family')?.marker,null);
});
test('compensated apply and history terminals never claim no prior write; unknown cannot release recovery',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,faceDecorationPresetAck:f.ack};
 const compensated:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:false,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,face_decoration_visual_required:true,face_decoration_preset_ack:f.ack,rolled_back:true,requires_reload:false,error:'compensated exactly'};
 assert.doesNotThrow(()=>validatePresetReply(compensated,'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...compensated,...{no_write:true}},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...compensated,outcome_unknown:true},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...compensated,face_decoration_preset_ack:undefined},'apply',opts,'apply',f.ops));
 const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8'),hook=read('../presets/usePresetWorkflow.ts');
 assert.ok(hook.includes('result.rolled_back===true'));
 assert.ok(hook.includes('retainDecorationPresetAliasReadback(readback)'));
 assert.ok(hook.includes('await latest.current.onRefresh();const fresh=await engineStatus()'));
 assert.ok(hook.includes('memberIds.every'));
 assert.ok(read('../native.ts').includes('status.ready_caps?.face_decoration_preset_alias_protocol === 1'));
});
