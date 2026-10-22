import test from 'node:test';
import assert from 'node:assert/strict';
import {createLocalMaskWorkflow,type LocalMaskRequest,type LocalMaskTransport} from './workflow.ts';
import type {CaptureDescriptor} from '../captureModel';
import type {MaskMutation} from './model';
const capture='2122232425262728292a2b2c2d2e2f30';
const descriptor:CaptureDescriptor={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',shm_instance:'1112131415161718191a1b1c1d1e1f20',
  capture_id:capture,seq:'1',generation:'9007199254740993',document_id:'123',ticket:'22',width:2,height:2,presentation_width:400,presentation_height:200,
  domain:'source-input',quality:'proxy-float-input',profile:'working-srgb',mask_overlay:true,mask_suspended:null,sample_valid_rows:[[0,2],[0,2]]};
const mutation:MaskMutation={action:'bind',enabled:true};
function frame(){
  const buffer=new ArrayBuffer(144),v=new DataView(buffer);v.setUint32(0,0x4c524350,false);v.setUint16(4,1,true);v.setUint16(6,128,true);
  for(const [field,start] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const)
    descriptor[field].match(/../g)!.forEach((byte,index)=>v.setUint8(start+index,parseInt(byte,16)));
  for(const [field,start] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const)v.setBigUint64(start,BigInt(descriptor[field]),true);
  for(const [field,start] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const)v.setUint32(start,descriptor[field],true);
  v.setBigUint64(104,16n,true);new Uint8Array(buffer,128).fill(127);return buffer;
}
function complete(r:LocalMaskRequest,patch:Record<string,unknown>={}){
  return {phase:'done',request_id:r.request_id,result:{protocol:1,action:'apply',request_id:r.request_id,document_id:r.document_id,
    capture_id:r.capture_id,ticket:r.ticket,success:true,outcome_unknown:false,requires_reload:false,no_change:false,history:{undo_steps:1,redo_steps:0},...patch}};
}
function fixture(){
  const sent:LocalMaskRequest[]=[],queried:string[]=[];let refreshes=0;
  const api:LocalMaskTransport={arm:async()=>({ticket:'22'}),status:async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor}),
    frame:async()=>frame(),presented:async()=>({eligible:true}),cancel:async()=>{},submit:async r=>{sent.push(r);},
    result:async requestId=>{queried.push(requestId);return complete(sent[0]);}};
  const flow=createLocalMaskWorkflow(api,{refresh:async()=>{refreshes++;},id:()=>capture,timeoutMs:1000,sleep:async()=>{}});
  flow.context({enabled:true,documentId:'123',contextKey:'revision-1'});
  const ready=async(m:MaskMutation|null=mutation)=>{await flow.start(m);assert.equal(flow.snapshot().phase,'painting');await flow.presented(flow.snapshot().frame!.descriptor);};
  return {flow,api,sent,queried,ready,refreshes:()=>refreshes};
}
test('view-only saved coverage never submits and edits require presented source pixels',async()=>{
  const f=fixture();await f.ready(null);await f.flow.apply();assert.equal(f.sent.length,0);f.flow.cancel();
  await f.flow.start(mutation);await f.flow.apply();assert.equal(f.sent.length,0);
  await f.flow.presented(f.flow.snapshot().frame!.descriptor);await f.flow.apply();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('repair input or missing actual coverage cannot become editable mask source',async()=>{
  for(const bad of [{...descriptor,domain:'repair-input' as const},{...descriptor,mask_overlay:false}]){
    const f=fixture();f.api.status=async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor:bad});await f.flow.start(mutation);
    assert.equal(f.flow.snapshot().phase,'failure');assert.equal(f.flow.snapshot().frame,null);assert.equal(f.sent.length,0);
  }
});
test('unknown receipts query original operation without resending',async()=>{
  const f=fixture();await f.ready();f.api.result=async request_id=>{f.queried.push(request_id);return {phase:'unavailable',request_id};};
  await f.flow.apply();assert.equal(f.flow.snapshot().phase,'uncertain');await f.flow.apply();await f.flow.check();
  assert.equal(f.sent.length,1);assert.equal(new Set(f.queried).size,1);assert.equal(f.refreshes(),0);
});
test('source-space metadata remains unchanged and context changes discard drafts',async()=>{
  const f=fixture();const m:MaskMutation={action:'upsert',coordinate_space:'source',object:{id:'retained',kind:'linear',name:'renamed',enabled:true,operation:'add',opacity:.6,feather:13,start:[.1,.2],end:[.7,.8],cross:[-.6,.6]}};
  await f.ready(m);await f.flow.apply();assert.deepEqual(f.sent[0].mutation,m);
  await f.ready(m);f.flow.context({enabled:true,documentId:'123',contextKey:'revision-2'});await f.flow.apply();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'idle');
});
test('success needs matching capture and post-history evidence',async()=>{
  for(const patch of [{ticket:'wrong'},{history:null},{no_change:null},{requires_reload:true}]){
    const f=fixture();await f.ready();f.api.result=async()=>complete(f.sent[0],patch);await f.flow.apply();
    assert.equal(f.flow.snapshot().phase,'uncertain');assert.equal(f.refreshes(),0);assert.equal(f.sent.length,1);
  }
});
test('range eyedropper reads source RGB8 only and does not treat coverage alpha as color',async()=>{
  const f=fixture();const m:MaskMutation={action:'upsert',coordinate_space:'capture',object:{id:'range',kind:'color_range',name:'range',enabled:true,operation:'add',opacity:1,feather:0,color:[0,0,0],tolerance:.2}};
  await f.ready(m);f.flow.sample([.5,.5]);const next=f.flow.snapshot().mutation;
  assert.equal(next?.action,'upsert');if(next?.action!=='upsert'||next.object.kind!=='color_range')assert.fail('missing color range');
  assert.deepEqual(next.object.color,[127/255,127/255,127/255]);assert.equal(next.object.tolerance,.2);
  assert.match(f.flow.snapshot().message,/8 位.*近似/);assert.equal(f.sent.length,0);f.flow.cancel();
});
test('luminance eyedropper linearizes sRGB and preserves editable interval width',async()=>{
  const f=fixture();const m:MaskMutation={action:'upsert',coordinate_space:'capture',object:{id:'range',kind:'luminance_range',name:'range',enabled:true,operation:'add',opacity:1,feather:0,low:.4,high:.6}};
  await f.ready(m);f.flow.sample([.5,.5]);const next=f.flow.snapshot().mutation;
  if(next?.action!=='upsert'||next.object.kind!=='luminance_range')assert.fail('missing luminance range');
  const center=Math.pow((127/255+.055)/1.055,2.4);
  assert.ok(Math.abs(next.object.high-next.object.low-.2)<1e-10);
  assert.ok(Math.abs((next.object.high+next.object.low)/2-center)<1e-10);
  f.flow.range({low:0,high:1});await f.flow.apply();assert.equal(f.sent.length,1);
});

test('range eyedropper rejects padded pixels and missing validity without changing parameters',async()=>{
  for(const rows of [null,[[0,0],[0,0]] as [number,number][]]){
    const f=fixture();f.api.status=async()=>({phase:'ready',capture_id:capture,ticket:'22',descriptor:{...descriptor,sample_valid_rows:rows}});
    const m:MaskMutation={action:'upsert',coordinate_space:'capture',object:{id:'range',kind:'color_range',name:'range',enabled:true,operation:'add',opacity:1,feather:0,color:[.2,.3,.4],tolerance:.2}};
    await f.ready(m);f.flow.sample([.5,.5]);assert.deepEqual(f.flow.snapshot().mutation,m);assert.equal(f.sent.length,0);f.flow.cancel();
  }
});
