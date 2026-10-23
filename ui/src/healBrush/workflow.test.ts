// AUTHORED / UNRUN: no runtime, typecheck or UI acceptance claimed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHealBrushWorkflow,type HealBrushRequest,type HealBrushTransport} from './workflow.ts';
import type {CaptureDescriptor} from '../captureModel';
import type {Point} from '../sourcePatch/geometry';

const capture='2122232425262728292a2b2c2d2e2f30';
const descriptor:CaptureDescriptor={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',shm_instance:'1112131415161718191a1b1c1d1e1f20',
  capture_id:capture,seq:'1',generation:'9007199254740993',document_id:'123',ticket:'22',width:2,height:2,presentation_width:400,presentation_height:200,
  domain:'repair-input',quality:'proxy-float-input',profile:'working-srgb'};
const polygon:Point[]=[[0.1,0.1],[0.3,0.1],[0.3,0.3],[0.1,0.3]];
function frame(){
  const buffer=new ArrayBuffer(144),v=new DataView(buffer);v.setUint32(0,0x4c524350,false);v.setUint16(4,1,true);v.setUint16(6,128,true);
  for(const [field,start] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const)
    descriptor[field].match(/../g)!.forEach((byte,index)=>v.setUint8(start+index,parseInt(byte,16)));
  for(const [field,start] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const)v.setBigUint64(start,BigInt(descriptor[field]),true);
  for(const [field,start] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const)v.setUint32(start,descriptor[field],true);
  v.setBigUint64(104,16n,true);new Uint8Array(buffer,128).fill(127);return buffer;
}
function complete(request:HealBrushRequest,patch:Record<string,unknown>={}){
  return {phase:'done',request_id:request.request_id,result:{protocol:1,action:'apply',request_id:request.request_id,
    document_id:request.document_id,capture_id:request.capture_id,ticket:request.ticket,success:true,outcome_unknown:false,requires_reload:false,
    kind:'heal_vector',no_change:false,before_count:0,after_count:1,op_id:1,history:{undo_steps:1,redo_steps:0},...patch}};
}
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
function fixture(timeoutMs=1000){
  const sent:HealBrushRequest[]=[],canceled:{id:string;ticket:string|null}[]=[],queried:string[]=[];let refreshes=0;
  const api:HealBrushTransport={
    arm:async()=>({ticket:'22'}),
    status:async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor}),
    frame:async()=>frame(),presented:async()=>({eligible:true}),
    cancel:async(id,ticket)=>{canceled.push({id,ticket});},
    submit:async r=>{sent.push(r);return {accepted:true};},
    result:async requestId=>{queried.push(requestId);return complete(sent[0]);},
  };
  const flow=createHealBrushWorkflow(api,{refresh:async()=>{refreshes++;},id:()=>capture,timeoutMs,sleep:async()=>{}});
  flow.context({enabled:true,documentId:'123',contextKey:'revision-1'});
  async function ready(){await flow.start();assert.equal(flow.snapshot().phase,'painting');await flow.presented(flow.snapshot().frame!.descriptor);}
  return {flow,api,sent,canceled,queried,ready,refreshes:()=>refreshes};
}

test('presented repair-input is required, no original/display mask is submitted',async()=>{
  const f=fixture();await f.flow.start();await f.flow.apply(polygon);assert.equal(f.sent.length,0);
  await f.flow.presented(f.flow.snapshot().frame!.descriptor);await f.flow.apply(polygon);
  assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
  assert.deepEqual(Object.keys(f.sent[0].stroke).sort(),['hardness','opacity','points','size']);
  assert.deepEqual(f.sent[0].stroke.points,polygon);assert.equal(f.refreshes(),1);
});
test('wrong capture domain refuses before a stroke',async()=>{
  const f=fixture();f.api.status=async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor:{...descriptor,domain:'source-input'}});
  await f.flow.start();assert.equal(f.flow.snapshot().phase,'failure');assert.equal(f.sent.length,0);
});
test('pending apply never sends twice and requires the correct repair kind',async()=>{
  const f=fixture();await f.ready();let resolve!:(reply:unknown)=>void;
  f.api.result=()=>new Promise(done=>{resolve=done;});const work=f.flow.apply(polygon);await tick();
  await f.flow.apply(polygon);assert.equal(f.sent.length,1);assert.equal(f.refreshes(),0);
  resolve(complete(f.sent[0],{kind:'clone_stamp'}));await work;
  assert.equal(f.flow.snapshot().phase,'uncertain');assert.equal(f.refreshes(),0);
});
test('unknown outcome queries only the original request',async()=>{
  const f=fixture();await f.ready();f.api.result=async request_id=>({phase:'unavailable',request_id});
  await f.flow.apply(polygon);assert.equal(f.flow.snapshot().phase,'uncertain');await f.flow.start();await f.flow.apply(polygon);
  assert.equal(f.sent.length,1);const original=f.sent[0].request_id;
  f.api.result=async requestId=>{assert.equal(requestId,original);return complete(f.sent[0]);};
  await f.flow.check();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('source switch and cancel discard only unsubmitted strokes',async()=>{
  const f=fixture();await f.ready();f.flow.context({enabled:true,documentId:'456',contextKey:'other'});
  await f.flow.apply(polygon);assert.equal(f.sent.length,0);assert.equal(f.flow.snapshot().phase,'idle');
});
test('source switch after submit does not race commit or forget its receipt',async()=>{
  const f=fixture();await f.ready();let resolve!:(reply:unknown)=>void;
  f.api.result=()=>new Promise(done=>{resolve=done;});const work=f.flow.apply(polygon);await tick();
  f.flow.context({enabled:true,documentId:'456',contextKey:'other'});f.flow.cancel();
  assert.equal(f.flow.snapshot().phase,'waiting');assert.equal(f.canceled.length,0);
  resolve(complete(f.sent[0]));await work;assert.match(f.flow.snapshot().message,/上一张/);assert.equal(f.sent.length,1);
});
test('late arm after cancellation releases its ticket without displaying pixels',async()=>{
  const f=fixture();let resolve!:(reply:{ticket:string})=>void;f.api.arm=()=>new Promise(done=>{resolve=done;});
  const work=f.flow.start();f.flow.cancel();resolve({ticket:'22'});await work;
  assert.equal(f.flow.snapshot().frame,null);assert.ok(f.canceled.some(item=>item.ticket==='22'));assert.equal(f.sent.length,0);
});
test('zero strength and invalid or overlong strokes never submit',async()=>{
  const f=fixture();await f.ready();f.flow.settings({opacity:0});await f.flow.apply(polygon);assert.equal(f.sent.length,0);
  f.flow.settings({opacity:1});await f.flow.apply([[NaN,.5]]);await f.flow.apply(Array.from({length:1025},()=>[.5,.5] as Point));
  assert.equal(f.sent.length,0);f.flow.cancel();
});
test('next stroke waits for confirmed fresh context, external edits stop continuation',async()=>{
  const f=fixture();await f.ready();await f.flow.apply(polygon);assert.equal(f.flow.canContinue(),false);
  f.flow.context({enabled:true,documentId:'123',contextKey:'revision-2'});assert.equal(f.flow.canContinue(),true);
  f.flow.externalEdit();assert.equal(f.flow.canContinue(),false);
});
