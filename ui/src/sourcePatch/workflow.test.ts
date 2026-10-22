import test from 'node:test';
import assert from 'node:assert/strict';
import {createSourcePatchWorkflow,type SourcePatchRequest,type SourcePatchTransport} from './workflow.ts';
import type {CaptureDescriptor} from '../captureModel';
import {parseCaptureFrame} from '../captureFrame.ts';
import type {Point} from './geometry';

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
function complete(request:SourcePatchRequest,patch:Record<string,unknown>={}){
  return {phase:'done',request_id:request.request_id,result:{protocol:1,action:'apply',request_id:request.request_id,
    document_id:request.document_id,capture_id:request.capture_id,ticket:request.ticket,success:true,outcome_unknown:false,requires_reload:false,
    no_change:false,before_count:0,after_count:1,op_id:1,history:{undo_steps:1,redo_steps:0},...patch}};
}
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
function fixture(timeoutMs=1000){
  const sent:SourcePatchRequest[]=[],canceled:{id:string;ticket:string|null}[]=[],queried:string[]=[];let refreshes=0;
  const api:SourcePatchTransport={
    arm:async()=>({ticket:'22'}),
    status:async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor}),
    frame:async()=>frame(),presented:async()=>({eligible:true}),
    cancel:async(id,ticket)=>{canceled.push({id,ticket});},
    submit:async r=>{sent.push(r);return {accepted:true};},
    result:async requestId=>{queried.push(requestId);return complete(sent[0]);},
  };
  const flow=createSourcePatchWorkflow(api,{refresh:async()=>{refreshes++;},id:()=>capture,timeoutMs,sleep:async()=>{}});
  flow.context({enabled:true,documentId:'123',contextKey:'revision-1'});
  async function ready(){await flow.start();assert.equal(flow.snapshot().phase,'painting');await flow.presented(flow.snapshot().frame!.descriptor);}
  async function selected(){await ready();flow.setPolygon(polygon);flow.setOffset([0.4,0.2]);}
  return {flow,api,sent,canceled,queried,ready,selected,refreshes:()=>refreshes};
}

test('repair frames reuse strict LRCP identity checks without weakening proxy-only consumers',()=>{
  assert.throws(()=>parseCaptureFrame(frame(),descriptor));
  assert.equal(parseCaptureFrame(frame(),descriptor,'repair-input').descriptor.generation,'9007199254740993');
  assert.throws(()=>parseCaptureFrame(frame(),{...descriptor,ticket:'21'},'repair-input'));
  assert.throws(()=>parseCaptureFrame(frame(),{...descriptor,domain:'proxy-output',quality:'proxy-float-output'},'repair-input'));
});
test('not-yet-presented frame and zero offset cannot be applied',async()=>{
  const f=fixture();await f.flow.start();f.flow.setPolygon(polygon);await f.flow.apply();assert.equal(f.sent.length,0);
  await f.flow.presented(f.flow.snapshot().frame!.descriptor);f.flow.setPolygon(polygon);await f.flow.apply();
  assert.equal(f.sent.length,0);f.flow.cancel();
});
test('one apply submits once; queue acceptance is not a completed history step',async()=>{
  const f=fixture();await f.selected();let resolve!:(reply:unknown)=>void;
  f.api.result=()=>new Promise(done=>{resolve=done;});
  const work=f.flow.apply();await tick();assert.equal(f.flow.snapshot().phase,'waiting');assert.equal(f.refreshes(),0);
  await f.flow.apply();assert.equal(f.sent.length,1);
  resolve(complete(f.sent[0]));await work;assert.equal(f.flow.snapshot().phase,'success');assert.equal(f.refreshes(),1);
  assert.deepEqual(f.sent[0].polygon,polygon);assert.deepEqual(f.sent[0].offset,[0.4,0.2]);
});
test('cancel and context invalidation only discard an unsent draft',async()=>{
  const f=fixture();await f.selected();f.flow.cancel();await f.flow.apply();assert.equal(f.sent.length,0);
  await f.selected();f.flow.context({enabled:true,documentId:'123',contextKey:'revision-2'});
  assert.equal(f.flow.snapshot().phase,'idle');await f.flow.apply();assert.equal(f.sent.length,0);
});
test('capture commands occupying the shared queue block a new start but do not invalidate their own capture',async()=>{
  const f=fixture();
  f.flow.context({enabled:true,canStart:false,documentId:'123',contextKey:'revision-1'});
  await f.flow.start();assert.equal(f.flow.snapshot().phase,'failure');
  f.flow.context({enabled:true,canStart:true,documentId:'123',contextKey:'revision-1'});
  await f.flow.start();assert.equal(f.flow.snapshot().phase,'painting');
  f.flow.context({enabled:true,canStart:false,documentId:'123',contextKey:'revision-1'});
  assert.equal(f.flow.snapshot().phase,'painting');assert.equal(f.canceled.length,0);
  await f.flow.presented(f.flow.snapshot().frame!.descriptor);
  f.flow.setPolygon(polygon);f.flow.setOffset([0.4,0.2]);await f.flow.apply();
  assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('late arm response after cancellation releases its own ticket and never displays pixels',async()=>{
  const f=fixture();let resolve!:(reply:{ticket:string})=>void;f.api.arm=()=>new Promise(done=>{resolve=done;});
  const work=f.flow.start();f.flow.cancel();resolve({ticket:'22'});await work;
  assert.equal(f.flow.snapshot().phase,'idle');assert.equal(f.flow.snapshot().frame,null);
  assert.ok(f.canceled.some(item=>item.ticket==='22'));assert.equal(f.sent.length,0);
});
test('changing photo or canceling after submit preserves pending receipt without racing capture release',async()=>{
  const f=fixture();await f.selected();let resolve!:(reply:unknown)=>void;
  f.api.result=()=>new Promise(done=>{resolve=done;});const work=f.flow.apply();await tick();
  f.flow.context({enabled:true,documentId:'456',contextKey:'other'});f.flow.cancel();
  assert.equal(f.flow.snapshot().phase,'waiting');assert.equal(f.canceled.length,0);
  resolve(complete(f.sent[0]));await work;assert.equal(f.flow.snapshot().phase,'success');
  assert.match(f.flow.snapshot().message,/上一张/);assert.equal(f.sent.length,1);
});
test('unknown outcome queries only the original request, never resubmits',async()=>{
  const f=fixture();await f.selected();f.api.result=async request_id=>({phase:'unavailable',request_id});
  await f.flow.apply();assert.equal(f.flow.snapshot().phase,'uncertain');await f.flow.start();await f.flow.apply();assert.equal(f.sent.length,1);
  const original=f.sent[0].request_id;
  f.api.result=async requestId=>{assert.equal(requestId,original);return complete(f.sent[0]);};
  await f.flow.check();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('lost submit response is resolved by the original receipt, not a second submission',async()=>{
  const f=fixture();await f.selected();f.api.submit=async request=>{f.sent.push(request);throw Error('response lost');};
  await f.flow.apply();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('wrong document, capture, ticket or missing post-history proof cannot claim success',async()=>{
  for(const patch of [{document_id:'456'},{capture_id:'wrong'},{ticket:'23'},{history:null},{outcome_unknown:true},{requires_reload:true}]){
    const f=fixture();await f.selected();f.api.result=async()=>complete(f.sent[0],patch);
    await f.flow.apply();assert.equal(f.flow.snapshot().phase,'uncertain');assert.equal(f.refreshes(),0);
  }
});
test('no-change receipt does not claim an extra undo step',async()=>{
  const f=fixture();await f.selected();f.api.result=async()=>complete(f.sent[0],{no_change:true,after_count:0,op_id:null,history:{undo_steps:0,redo_steps:0}});
  await f.flow.apply();assert.equal(f.flow.snapshot().phase,'success');assert.match(f.flow.snapshot().message,/未新增历史/);
});
test('stopped owner ignores late receipt but retains its request for a subsequent check',async()=>{
  const f=fixture();await f.selected();let resolve!:(reply:unknown)=>void;
  f.api.result=()=>new Promise(done=>{resolve=done;});const work=f.flow.apply();await tick();f.flow.stop();
  resolve(complete(f.sent[0]));await work;assert.equal(f.flow.snapshot().phase,'uncertain');assert.equal(f.refreshes(),0);
  f.flow.activate();f.api.result=async()=>complete(f.sent[0]);await f.flow.check();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('hung send or result becomes uncertain, and only reopening can dismiss unresolved identity',async()=>{
  const f=fixture(20);await f.selected();f.api.submit=async request=>{f.sent.push(request);return new Promise(()=>{});};
  f.api.result=()=>new Promise(()=>{});await f.flow.apply();assert.equal(f.flow.snapshot().phase,'uncertain');
  f.flow.acknowledgeAfterReload();assert.equal(f.flow.snapshot().phase,'uncertain');
  f.flow.context({enabled:true,documentId:'456',contextKey:'new'});f.flow.acknowledgeAfterReload();assert.equal(f.flow.snapshot().phase,'idle');
  assert.equal(f.sent.length,1);
});
