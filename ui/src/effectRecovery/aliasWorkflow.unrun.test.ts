// AUTHORED / UNRUN. Synthetic contracts only; no tests, typecheck, UI or product execution performed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {aliasFixture} from '../eyeBagPreserve/aliasFixture.unrun.test.ts';
import {createRecoveryWorkflow,type RecoveryTransport} from './workflow.ts';
import {recoveryCanonical,recoveryAliasMemberKey,recoveryAliasMarker,type RecoveryAliasReview} from './aliasModel.ts';
import {observeRecoveryAliasHistory,recoveryAliasWritePending,recoveryAliasHistoryClass} from './aliasHistoryRegistry.ts';
import type {RecoveryRequest,RecoveryStroke} from './model.ts';
import type {CaptureDescriptor} from '../captureModel';
const capture='2122232425262728292a2b2c2d2e2f30';
const descriptor:CaptureDescriptor&{full_source:[number,number]}={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',shm_instance:'1112131415161718191a1b1c1d1e1f20',
  capture_id:capture,seq:'1',generation:'1',document_id:'123',ticket:'22',width:2,height:2,presentation_width:2,presentation_height:2,
  recipe_document_id:'d'.repeat(32),recipe_revision:'7',full_source:[2,2],domain:'source-input',quality:'proxy-float-input',profile:'working-srgb'};
function frame(){const buffer=new ArrayBuffer(144),view=new DataView(buffer);view.setUint32(0,0x4c524350,false);view.setUint16(4,1,true);view.setUint16(6,128,true);
  for(const [field,start] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const)descriptor[field].match(/../g)!.forEach((byte,index)=>view.setUint8(start+index,parseInt(byte,16)));
  for(const [field,start] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const)view.setBigUint64(start,BigInt(descriptor[field]),true);
  for(const [field,start] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const)view.setUint32(start,descriptor[field],true);
  view.setBigUint64(104,16n,true);return buffer;}
function review(token:string):RecoveryAliasReview{const base=aliasFixture().review,members=base.members.map(member=>({...structuredClone(member),visual:{...structuredClone(member.visual),candidate_state_sha256:member.visual.before_state_sha256}}));
  const body={version:2 as const,token,target:'eye_bag_preserve' as const,face_ref:base.face_ref,before_recovery_sha256:null,recovery_sha256:'7'.repeat(64),visual:members[0].visual,members};
  return {...body,review_sha256:createHash('sha256').update(recoveryCanonical(body)).digest('hex')};}
async function until(predicate:()=>boolean){for(let index=0;index<100;index++){if(predicate())return;await new Promise(resolve=>setTimeout(resolve,5));}assert.fail('fixture never reached expected state');}
function fixture(){const epoch=`recovery-fixture-${crypto.randomUUID()}`;observeRecoveryAliasHistory({workspace_generation:epoch,batches:[]});
  let sequence=0,presented=0,isPresented=false,value=review('c'.repeat(32));const sent:RecoveryRequest[]=[];
  const api:RecoveryTransport={arm:async()=>({ticket:'22'}),status:async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor}),frame:async()=>frame(),presented:async()=>({eligible:true}),cancel:async()=>{},
    preview:async(action,id)=>{if(action==='preview'){value=review(id);isPresented=false;}if(action==='presented'){presented++;isPresented=true;}},
    previewStatus:async id=>({protocol:2,preview_id:id,document_id:'123',capture_id:capture,ticket:'22',generation:'1',recipe_document_id:descriptor.recipe_document_id,recipe_revision:'7',
      target:'eye_bag_preserve',state:isPresented?'presented':'ready',success:true,review_sha256:value.review_sha256,result:{domain:'production-output',quality:'full-source-render-srgb8',note:'synthetic',review:value}}),
    submit:async request=>{sent.push(request);},result:async request_id=>{const request=sent[0],alias=request.alias_review!;return {phase:'done',request_id,result:{...request,action:'apply',success:true,outcome_unknown:false,requires_reload:false,no_change:false,no_write:false,
      batch_id:'recovery-fixture-batch',eye_bag_recovery_alias_review:recoveryAliasMarker(alias),module_scope:['lnx.people_graph.v1'],alias_members:alias.members.map(({visual})=>({document_id:visual.document_id,expected_revision:visual.revision,result_revision:String(BigInt(visual.revision)+1n)})),
      history:{undo_steps:0,redo_steps:0},doc_state:{document_id:'123',people:{binding:{document_id:descriptor.recipe_document_id,document_epoch:epoch,document_revision:8,asset_sha256:alias.face_ref.asset_sha256}}}}};}};
  const flow=createRecoveryWorkflow(api,{refresh:async()=>{},id:()=>sequence++===0?capture:sequence.toString(16).padStart(32,'0'),timeoutMs:1000});flow.context({enabled:true,documentId:'123',contextKey:epoch});
  const start=async()=>{await flow.start('eye_bag_preserve');await flow.sourcePresented(flow.snapshot().frame!.descriptor);await until(()=>!!flow.snapshot().aliasReview);};
  const mark=(index:number,ready=true)=>{const state=flow.snapshot(),v=state.aliasReview!;flow.aliasMemberReviewed(state.previewId!,recoveryAliasMemberKey(state.previewId!,v,v.members[index]),ready);};
  return {flow,api,sent,start,mark,presented:()=>presented,cleanup:()=>{flow.stop();observeRecoveryAliasHistory({workspace_generation:`retired-${epoch}`,batches:[]});}};
}
const stroke:RecoveryStroke={id:'fixture',name:'fixture',kind:'brush',enabled:true,operation:'add',opacity:1,feather:0,points:[[.5,.5]],axes:[[.02,0],[0,.02]]};
test('current member view-only baseline permits drawing without all-member presentation or write authority',async()=>{const f=fixture();try{await f.start();const initial=f.flow.snapshot(),old=initial.aliasReview!,oldId=initial.previewId!;
  assert.equal(f.flow.beginStroke(),false);f.mark(1);assert.equal(f.flow.beginStroke(),false);f.mark(0);
  assert.equal(f.presented(),0);assert.equal(f.flow.snapshot().awaitingConfirmation,false);await f.flow.imagePresented(oldId);await f.flow.confirmReviewed();assert.equal(f.sent.length,0);assert.equal(f.presented(),0);
  assert.equal(f.flow.beginStroke(),true);f.flow.stroke(stroke,true);assert.equal(f.flow.snapshot().aliasReview,null);
  f.flow.aliasMemberReviewed(oldId,recoveryAliasMemberKey(oldId,old,old.members[0]),true);await until(()=>!!f.flow.snapshot().aliasReview);
  f.mark(0);await f.flow.confirmReviewed();assert.equal(f.sent.length,0);assert.equal(f.presented(),0);
  f.mark(1);await until(()=>f.flow.snapshot().awaitingConfirmation);assert.equal(f.presented(),1);assert.equal(f.sent.length,0);
  await f.flow.confirmReviewed();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
}finally{f.cleanup();}});
test('known diagnostic batch ID on unknown apply does not invent history authority or release write fence',async()=>{const f=fixture();try{await f.start();f.mark(0);assert.equal(f.flow.beginStroke(),true);f.flow.stroke(stroke,true);await until(()=>!!f.flow.snapshot().aliasReview);f.mark(0);f.mark(1);await until(()=>f.flow.snapshot().awaitingConfirmation);
  f.api.result=async request_id=>({phase:'done',request_id,result:{...f.sent[0],action:'apply',success:false,outcome_unknown:true,requires_reload:true,batch_id:'diagnostic-only',error:'publication persistence unknown'}});
  await f.flow.confirmReviewed();assert.equal(f.flow.snapshot().phase,'uncertain');assert.equal(f.flow.snapshot().receiptBatchId,'diagnostic-only');assert.equal(recoveryAliasHistoryClass('diagnostic-only'),undefined);assert.equal(recoveryAliasWritePending(),true);
  f.flow.cancel();await f.flow.check();f.flow.acknowledgeAfterReload();assert.equal(f.sent.length,1);assert.equal(recoveryAliasWritePending(),true);
}finally{f.cleanup();}});
test('paged images require actual decode and display, and stale page callbacks lose authority',()=>{const ui=readFileSync(new URL('./RecoveryAliasReview.tsx',import.meta.url),'utf8');
  assert.ok(ui.includes('await image.decode()'));assert.ok(ui.includes('image.naturalWidth!==visual[side].width'));
  assert.ok(ui.includes('live.current=false;current.current=null;++generation.current'));
  assert.ok(ui.includes('if(live.current&&current.current===expected)setPresented(true)'));
  assert.ok(ui.includes('event.target.checked&&presented'));
});
