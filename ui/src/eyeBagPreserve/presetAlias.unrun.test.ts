// AUTHORED / UNRUN. Synthetic protocol fixtures only; not build, rendering, or photograph-quality evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {eyeBagFixture} from './presetFixture';
import {canonical} from './support';
import {EYE_BAG_PRESET_OP,eyeBagPresetAck,sameEyeBagPresetAck,validEyeBagPreset,verifyEyeBagCoverage,type EyeBagPresetReviewV2} from './presetModel';
import {observeEyeBagPresetAliasHistory,eyeBagPresetAliasHistoryClass,presetAliasMarker,eyeBagPresetAliasWritePending,setEyeBagPresetAliasWritePending,subscribeEyeBagPresetAliasWrites} from './presetAliasHistoryRegistry';
import {validatePresetReply,createPresetWorkflow,type PresetReply} from '../presets/presetWorkflow';
import {createBatchWorkflow} from '../batch/batchWorkflow';
const sha=(value:unknown)=>createHash('sha256').update(canonical(value)).digest('hex');
function fixture(){
 const base=eyeBagFixture();assert.equal(base.version,1);
 const active=structuredClone(base.visual);active.coverage_sha256=sha(base.coverage);
 const sibling={...structuredClone(active),document_id:'9'.repeat(32),revision:'9',candidate_state_sha256:active.before_state_sha256,after_output_size:active.before_output_size};
 const review:EyeBagPresetReviewV2={...base,version:2,visual:active,owner:{...base.owner,people_scope:'project'},members:[
  {path:'/shared/source.png',role:'active',visual:active},{path:'/shared/source.png',role:'sibling',visual:sibling}],review_sha256:''};
 const {review_sha256:_,...identity}=review;review.review_sha256=sha(identity);
 const ops=[EYE_BAG_PRESET_OP,'lnx.hsl.v1'],token='f'.repeat(32),ack=eyeBagPresetAck(review),marker=presetAliasMarker(review,ops);
 const preflight:PresetReply={protocol:1,request_id:'review',action:'preflight',success:true,outcome_unknown:false,id:'preset',document_id:review.load_id,
  revision:review.visual.revision,source_proof:review.owner.source_proof,preflight_token:token,module_scope:ops,applies:{[EYE_BAG_PRESET_OP]:{recipe:{version:2,amount:.5,preserve:1}},'lnx.hsl.v1':{}},eye_bag_preset:review,eye_bag_replace_legacy:false};
 const success:PresetReply={protocol:1,request_id:'apply',action:'apply',success:true,outcome_unknown:false,id:'preset',document_id:review.load_id,
  preflight_token:token,module_scope:ops,eye_bag_preset_ack:ack,batch_id:'preset-alias-batch',eye_bag_preset_alias_review:marker,
  alias_members:review.members.map(({visual})=>({document_id:visual.document_id,expected_revision:visual.revision,result_revision:String(BigInt(visual.revision)+1n)})),
  before:{[EYE_BAG_PRESET_OP]:{},'lnx.hsl.v1':{}},after:{[EYE_BAG_PRESET_OP]:{},'lnx.hsl.v1':{}},
  doc_state:{document_id:review.load_id,people:{binding:{document_id:active.document_id,document_revision:Number(BigInt(active.revision)+1n)}}}};
 return {review,ops,token,ack,marker,preflight,success};
}
test('v2 binds all independent member visuals but allows distinct document aliases with identical paths',async()=>{
 const f=fixture();assert.ok(validEyeBagPreset(f.review,f.review.load_id,f.review.visual.revision,f.review.owner.source_proof,false));
 assert.ok(await verifyEyeBagCoverage(f.review));
 const bad=structuredClone(f.review);bad.members[1].visual.document_id=bad.members[0].visual.document_id;
 assert.equal(validEyeBagPreset(bad,bad.load_id,bad.visual.revision,bad.owner.source_proof,false),false);
 const changed=structuredClone(f.review);changed.members[1].visual.candidate_state_sha256='e'.repeat(64);
 assert.equal(validEyeBagPreset(changed,changed.load_id,changed.visual.revision,changed.owner.source_proof,false),false);
 const drift=structuredClone(f.review);drift.members[1].path='/different/path.png';assert.equal(await verifyEyeBagCoverage(drift),false);
 const single=eyeBagFixture();assert.ok(validEyeBagPreset(single,single.load_id,single.visual.revision,single.owner.source_proof,false));
});
test('ordered all-member ACK cannot be replaced with one image or reversed members',()=>{
 const f=fixture();assert.ok('members'in f.ack);if(!('members'in f.ack))return;
 assert.ok(sameEyeBagPresetAck(f.ack,eyeBagPresetAck(f.review)));
 assert.equal(sameEyeBagPresetAck({...f.ack,members:[...f.ack.members].reverse()},f.ack),false);
 assert.equal(sameEyeBagPresetAck({...f.ack,members:f.ack.members.slice(0,1)},f.ack),false);
 assert.equal(sameEyeBagPresetAck({...f.ack,replace_legacy:true},f.ack),false);
});
test('success requires exact composite marker, current binding, ordered +1 publication and complete mixed scope',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack};
 assert.doesNotThrow(()=>validatePresetReply(f.success,'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:null},{alias_members:f.success.alias_members!.slice(0,1)},
  {alias_members:[...f.success.alias_members!].reverse()},{eye_bag_preset_alias_review:{...f.marker,selected_modules:[EYE_BAG_PRESET_OP]}},
  {doc_state:{document_id:f.review.load_id,people:{binding:{document_id:'elsewhere',document_revision:1}}}}])
  assert.throws(()=>validatePresetReply({...f.success,...patch},'apply',opts,'apply',f.ops));
});
test('unknown apply retains fence and original query identity; matching full result alone releases it',async()=>{
 const f=fixture();let sends=0,done=false;const ids=['review','apply'];
 const flow=createPresetWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:request_id==='review'?f.preflight:done?f.success:{
  protocol:1,request_id,action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,preflight_token:f.token,module_scope:f.ops,eye_bag_preset_ack:f.ack,batch_id:f.success.batch_id,error:'unknown after claim'}})},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset',eyeBagReplaceLegacy:false},f.ops);
 await flow.submit('apply',{id:'preset',preflightToken:f.token,eyeBagPresetAck:f.ack},f.ops);
 assert.equal(flow.snapshot().phase,'uncertain');assert.equal(eyeBagPresetAliasWritePending(),true);
 flow.acknowledgeInspection();await flow.submit('apply',{id:'preset',preflightToken:f.token,eyeBagPresetAck:f.ack},f.ops);assert.equal(sends,2);
 done=true;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(eyeBagPresetAliasWritePending(),false);assert.equal(sends,2);
});
test('reopened exact composite marker fences partial/foreign history without creating another history controller',async()=>{
 const f=fixture(),batch_id='reopened-preset-alias';
 observeEyeBagPresetAliasHistory({workspace_generation:'preset-history-epoch',batches:[{batch_id,targets:2,module_scope:['lnx.people_graph.v1'],eye_bag_preset_alias_review:f.marker}]});
 assert.equal(eyeBagPresetAliasHistoryClass(batch_id)?.memberCount,2);
 let sends=0,complete=false;const flow=createBatchWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:{
  request_id,action:'undo',success:true,outcome_unknown:false,batch_id,module_scope:['lnx.people_graph.v1'],eye_bag_preset_alias_review:f.marker,restored:complete?[0,3]:[0],conflicts:[]}})},()=>{});
 await flow.undo(batch_id);assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().queryOnly,true);
 flow.close();flow.acknowledgeInspection();await flow.redo(batch_id);assert.equal(sends,1);
 complete=true;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(sends,1);
 observeEyeBagPresetAliasHistory({workspace_generation:'preset-history-epoch',batches:[{batch_id,eye_bag_preset_alias_review:null}]});
 assert.equal(eyeBagPresetAliasHistoryClass(batch_id)?.memberCount,null);
});
test('visible member ACK requires actual independent load, decode and hash plus aggregate readiness',()=>{
 const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
 const panel=read('./EyeBagPresetReview.tsx'),transport=read('./presetTransport.ts');
 for(const text of ['await image.decode()','loaded.before&&loaded.after','ready&&checked','members.every','memberDocumentId:visual.document_id','读取本成员实际完整前后图像'])assert.ok(panel.includes(text));
 assert.ok(transport.includes('r.member_document_id!==request.memberDocumentId'));
 assert.ok(transport.includes('await verifyCollarboneImage(r.image)'));
 assert.ok(read('../people/usePeopleWorkflow.ts').includes("historyKind==='eye_bag_preset'"));
 assert.ok(read('../presets/PresetPanel.tsx').includes('w.ui.submitted?.options.eyeBagPresetAck===undefined&&<button'));
});

test('only verified workspace replacement retires an old-epoch pending fence and notifies people controls',()=>{
 observeEyeBagPresetAliasHistory({workspace_generation:'old-preset-epoch',batches:[]});
 let changes=0;const unsubscribe=subscribeEyeBagPresetAliasWrites(()=>{changes++;});
 setEyeBagPresetAliasWritePending('old-request',true,'old-preset-epoch');
 observeEyeBagPresetAliasHistory({workspace_generation:'old-preset-epoch',batches:[]});
 assert.equal(eyeBagPresetAliasWritePending(),true);assert.equal(changes,1);
 // A request already associated with the newly verified workspace is not stale.
 setEyeBagPresetAliasWritePending('new-request',true,'new-preset-epoch');
 observeEyeBagPresetAliasHistory({workspace_generation:'new-preset-epoch',batches:[]});
 assert.equal(eyeBagPresetAliasWritePending(),true);assert.equal(changes,3);
 setEyeBagPresetAliasWritePending('new-request',false);assert.equal(eyeBagPresetAliasWritePending(),false);
 unsubscribe();
});

test('known post-ledger publication is retained as UNKNOWN diagnostics, never completed or replayed',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack};
 const {before:_,after:__,doc_state:___,...publication}=f.success;
 const unknown:PresetReply={...publication,success:false,outcome_unknown:true,error:'published; final state uncertain'};
 assert.doesNotThrow(()=>validatePresetReply(unknown,'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,alias_members:unknown.alias_members!.slice(0,1)},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,eye_bag_preset_alias_review:{...f.marker,member_count:3}},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,outcome_unknown:false},'apply',opts,'apply',f.ops));
});
test('exact unclaimed v2 ACK can be refused without stored scope but never with publication claims',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack};
 const refused:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:false,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,eye_bag_preset_ack:f.ack,error:'expired before claim'};
 assert.doesNotThrow(()=>validatePresetReply(refused,'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:null},{operation_committed:true},{module_scope:[EYE_BAG_PRESET_OP]},
  {preflight_token:'wrong'},{eye_bag_preset_ack:{...f.ack,replace_legacy:true}}])
  assert.throws(()=>validatePresetReply({...refused,...patch},'apply',opts,'apply',f.ops));
});
test('verified project replacement retires exact old preset request as UNKNOWN and ignores its late callback',async()=>{
 const f=fixture(),epoch=f.review.owner.document.epoch;observeEyeBagPresetAliasHistory({workspace_generation:epoch,batches:[]});
 let publish!: (value:{phase:string;request_id:string;result:PresetReply})=>void,started!:()=>void;
 const begun=new Promise<void>(resolve=>{started=resolve;}),late=new Promise<{phase:string;request_id:string;result:PresetReply}>(resolve=>{publish=resolve;});
 const ids=['review','apply'];
 const flow=createPresetWorkflow({request:async()=>({requested:true}),read:async request_id=>{
  if(request_id==='review')return {phase:'done',request_id,result:f.preflight};started();return late;
 }},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset',eyeBagReplaceLegacy:false},f.ops);
 const applying=flow.submit('apply',{id:'preset',preflightToken:f.token,eyeBagPresetAck:f.ack},f.ops);await begun;
 observeEyeBagPresetAliasHistory({workspace_generation:epoch,batches:[]});assert.equal(flow.snapshot().phase,'working');
 observeEyeBagPresetAliasHistory({workspace_generation:'verified-reopened-preset-epoch',batches:[]});
 assert.equal(flow.snapshot().phase,'error');assert.match(flow.snapshot().message,/结果仍未知/);assert.equal(eyeBagPresetAliasWritePending(),false);
 publish({phase:'done',request_id:'apply',result:f.success});await applying;
 assert.equal(flow.snapshot().phase,'error');assert.equal(flow.snapshot().result,null);flow.dispose();
});
test('only composite history requests retire on verified replacement of their captured workspace',async()=>{
 const f=fixture(),batch_id='recover-preset-history',workspace_generation='history-before-reopen';
 observeEyeBagPresetAliasHistory({workspace_generation,batches:[{batch_id,targets:2,module_scope:['lnx.people_graph.v1'],eye_bag_preset_alias_review:f.marker}]});
 const flow=createBatchWorkflow({request:async()=>({requested:true}),read:async request_id=>({phase:'done',request_id,result:{request_id,action:'undo',success:false,outcome_unknown:true,batch_id,error:'unknown undo'}})},()=>{});
 await flow.undo(batch_id);assert.equal(flow.snapshot().phase,'uncertain');
 observeEyeBagPresetAliasHistory({workspace_generation,batches:[]});assert.equal(flow.snapshot().phase,'uncertain');
 observeEyeBagPresetAliasHistory({workspace_generation:'history-verified-reopen',batches:[]});
 assert.equal(flow.snapshot().phase,'error');assert.match(flow.snapshot().message,/结果仍未知/);assert.equal(flow.snapshot().result,null);flow.dispose();
});

test('supplementary mixed ACKs must retain exact presence and ordered values even in no-write refusal',()=>{
 const f=fixture(),spill=[{document_id:'load',revision:'1',before_sha256:'a'.repeat(64),after_sha256:'b'.repeat(64)}];
 const opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack,spillReviewAck:spill};
 const refused:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:false,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,eye_bag_preset_ack:f.ack,error:'expired before claim'};
 assert.throws(()=>validatePresetReply(refused,'apply',opts,'apply',f.ops));
 assert.doesNotThrow(()=>validatePresetReply({...refused,...{spill_review_ack:spill}},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...refused,...{spill_review_ack:[]}},'apply',opts,'apply',f.ops));
});

test('native identity-only unknown may omit actual scope but never carries unproven publication',()=>{
 const f=fixture(),opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack};
 const unknown:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,eye_bag_preset_ack:f.ack,error:'native outcome unknown'};
 assert.doesNotThrow(()=>validatePresetReply(unknown,'apply',opts,'apply',f.ops));
 assert.doesNotThrow(()=>validatePresetReply({...unknown,batch_id:'known-ledger-id'},'apply',opts,'apply',f.ops));
 for(const patch of [{batch_id:''},{batch_id:null},{eye_bag_preset_alias_review:f.marker},{alias_members:f.success.alias_members},
  {doc_state:f.success.doc_state},{operation_committed:true},{eye_bag_preset_ack:{...f.ack,replace_legacy:true}}])
  assert.throws(()=>validatePresetReply({...unknown,...patch},'apply',opts,'apply',f.ops));
});

test('batch-ID-only unknown is retained but never manufactures a composite marker or actual scope',async()=>{
 const f=fixture(),batch_id='diagnostic-only-preset-batch';
 observeEyeBagPresetAliasHistory({workspace_generation:f.review.owner.document.epoch,batches:[]});
 const unknown:PresetReply={protocol:1,request_id:'apply',action:'apply',success:false,outcome_unknown:true,id:'preset',document_id:f.review.load_id,
  preflight_token:f.token,eye_bag_preset_ack:f.ack,batch_id,error:'ledger ID known; full publication proof unavailable'};
 const ids=['review','apply'];let sends=0;
 const flow=createPresetWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'done',request_id,result:request_id==='review'?f.preflight:unknown})},()=>{},{uuid:()=>ids.shift()!});
 flow.updateContext({enabled:true,editable:true,documentId:f.review.load_id,reviewContextKey:'original'});
 await flow.submit('preflight',{id:'preset',eyeBagReplaceLegacy:false},f.ops);
 await flow.submit('apply',{id:'preset',preflightToken:f.token,eyeBagPresetAck:f.ack},f.ops);
 assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().result?.batch_id,batch_id);assert.equal(eyeBagPresetAliasWritePending(),true);
 assert.equal(Object.hasOwn(flow.snapshot().result!,'module_scope'),false);assert.equal(Object.hasOwn(flow.snapshot().result!,'eye_bag_preset_alias_review'),false);
 assert.equal(eyeBagPresetAliasHistoryClass(batch_id),undefined);
 flow.acknowledgeInspection();await flow.submit('apply',{id:'preset',preflightToken:f.token,eyeBagPresetAck:f.ack},f.ops);assert.equal(sends,2);
 const opts={id:'preset',documentId:f.review.load_id,preflightToken:f.token,eyeBagPresetAck:f.ack};
 assert.doesNotThrow(()=>validatePresetReply({...unknown,module_scope:f.ops},'apply',opts,'apply',f.ops));
 assert.throws(()=>validatePresetReply({...unknown,module_scope:[EYE_BAG_PRESET_OP]},'apply',opts,'apply',f.ops));
 observeEyeBagPresetAliasHistory({workspace_generation:'diagnostic-only-reopened-workspace',batches:[]});flow.dispose();
});
