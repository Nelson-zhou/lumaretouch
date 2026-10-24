// AUTHORED / UNRUN. These fixtures have not been executed or typechecked.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createRecoveryWorkflow,recoveryReview,recoveryTargetMatches,type RecoveryTransport} from './workflow.ts';
import {LABELS,requiresRecoveryConfirmation,type RecoveryRequest,type RecoveryTarget} from './model.ts';
import type {CaptureDescriptor} from '../captureModel';
const capture='2122232425262728292a2b2c2d2e2f30';
const descriptor:CaptureDescriptor={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',shm_instance:'1112131415161718191a1b1c1d1e1f20',
  capture_id:capture,seq:'1',generation:'1',document_id:'123',ticket:'22',width:2,height:2,presentation_width:400,presentation_height:200,
  domain:'source-input',quality:'proxy-float-input',profile:'working-srgb'};
function frame(){
  const buffer=new ArrayBuffer(144),v=new DataView(buffer);v.setUint32(0,0x4c524350,false);v.setUint16(4,1,true);v.setUint16(6,128,true);
  for(const [field,start] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const)
    descriptor[field].match(/../g)!.forEach((byte,index)=>v.setUint8(start+index,parseInt(byte,16)));
  for(const [field,start] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const)v.setBigUint64(start,BigInt(descriptor[field]),true);
  for(const [field,start] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const)v.setUint32(start,descriptor[field],true);
  v.setBigUint64(104,16n,true);return buffer;
}
const image=(quality='full-source-render-srgb8')=>({before:'data:image/png;base64,AA==',after:'data:image/png;base64,AA==',width:2,height:2,domain:'production-output',quality,note:'fixture'});
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
function fixture(target:RecoveryTarget='eye_bag_preserve'){
  const sent:RecoveryRequest[]=[];let shown=false,sequence=0;
  const nextId=()=>sequence++===0?capture:sequence.toString(16).padStart(32,'0');
  const api:RecoveryTransport={arm:async()=>({ticket:'22'}),status:async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor}),
    frame:async()=>frame(),presented:async()=>({eligible:true}),cancel:async()=>{},
    preview:async action=>{shown=action==='presented';},
    previewStatus:async id=>({preview_id:id,document_id:'123',capture_id:capture,ticket:'22',target,state:shown?'presented':'ready',success:true,
      result:image(target==='eye_bag_preserve'?'full-source-render-srgb8':'proxy-render-srgb8')}),
    submit:async request=>{sent.push(request);},result:async request_id=>({phase:'done',request_id,result:{...sent[0],protocol:1,action:'apply',success:true,
      outcome_unknown:false,requires_reload:false,no_change:false,history:{undo_steps:1,redo_steps:0}}})};
  const flow=createRecoveryWorkflow(api,{refresh:async()=>{},id:nextId,timeoutMs:1000});
  flow.context({enabled:true,documentId:'123',contextKey:'source-face-repair-graph-1'});
  async function ready(){await flow.start(target);await flow.sourcePresented(flow.snapshot().frame!.descriptor);await tick();await flow.imagePresented(flow.snapshot().previewId!);}
  async function candidate(){await ready();flow.mutate({action:'clear',target});await tick();await flow.imagePresented(flow.snapshot().previewId!);}
  return {flow,api,sent,ready,candidate};
}
test('eye-bag v2 is a distinct target and full-source rendered evidence is mandatory',()=>{
  assert.ok(LABELS.eye_bag_preserve);assert.equal(requiresRecoveryConfirmation('eye_bag_preserve'),true);
  assert.equal(requiresRecoveryConfirmation('eye_light'),false);
  assert.equal(recoveryTargetMatches({target:'facial_wrinkles'},'eye_bag_preserve'),false);
  assert.throws(()=>recoveryReview(image('proxy-render-srgb8'),'eye_bag_preserve'));
  assert.throws(()=>recoveryReview(image(),'eye_light'));
  assert.equal(recoveryReview(image(),'eye_bag_preserve').quality,'full-source-render-srgb8');
});
test('view-only presentation never commits and final eye-bag presentation waits for explicit confirmation',async()=>{
  const f=fixture();await f.ready();assert.equal(f.sent.length,0);await f.flow.confirmReviewed();assert.equal(f.sent.length,0);
  f.flow.mutate({action:'clear',target:'eye_bag_preserve'});await tick();await f.flow.imagePresented(f.flow.snapshot().previewId!);
  assert.equal(f.flow.snapshot().awaitingConfirmation,true);assert.equal(f.sent.length,0);
  await f.flow.confirmReviewed();await f.flow.confirmReviewed();assert.equal(f.sent.length,1);f.flow.stop();
});
test('owner revision change invalidates an unsent final image confirmation',async()=>{
  const f=fixture();await f.candidate();f.flow.context({enabled:true,documentId:'123',contextKey:'source-face-repair-graph-2'});
  await f.flow.confirmReviewed();assert.equal(f.sent.length,0);f.flow.stop();
});
test('closing final review discards it without submitting',async()=>{
  const f=fixture();await f.candidate();f.flow.cancel();await f.flow.confirmReviewed();assert.equal(f.sent.length,0);f.flow.stop();
});
test('unknown confirmation result is queried without resubmitting',async()=>{
  const f=fixture();await f.candidate();f.api.result=async request_id=>({phase:'done',request_id,result:{...f.sent[0],protocol:1,action:'apply',success:false,outcome_unknown:true}});
  await f.flow.confirmReviewed();assert.equal(f.flow.snapshot().phase,'uncertain');await f.flow.confirmReviewed();await f.flow.check();
  assert.equal(f.sent.length,1);f.flow.stop();
});
test('legacy recovery retains presented final-candidate automatic commit',async()=>{
  const f=fixture('eye_light');await f.candidate();assert.equal(f.sent.length,1);f.flow.stop();
});

test('a staged explicit review cannot be replaced by another stroke or mutation',async()=>{
  const f=fixture();await f.candidate();const before=f.flow.snapshot().previewId;
  assert.equal(f.flow.beginStroke(),false);f.flow.mutate({action:'enable',target:'eye_bag_preserve',enabled:false});
  assert.equal(f.flow.snapshot().previewId,before);assert.equal(f.flow.snapshot().awaitingConfirmation,true);
  await f.flow.confirmReviewed();assert.equal(f.sent.length,1);assert.equal(f.sent[0].preview_id,before);f.flow.stop();
});
test('a stale preview presentation cannot authorize a newer staged recovery',async()=>{
  const f=fixture();await f.ready();f.flow.mutate({action:'clear',target:'eye_bag_preserve'});await tick();
  await f.flow.imagePresented('stale-preview');await f.flow.confirmReviewed();assert.equal(f.sent.length,0);
  assert.equal(f.flow.snapshot().awaitingConfirmation,false);f.flow.stop();
});
