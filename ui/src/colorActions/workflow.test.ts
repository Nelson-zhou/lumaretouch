import test from 'node:test';
import assert from 'node:assert/strict';
import {createColorActionWorkflow} from './workflow.ts';
import {colorActionStage,validateColorCommit,validateColorPreview,type ColorAction,type ColorActionRequest,type ColorActionTransport} from './model.ts';
import type {CaptureDescriptor} from '../captureModel';

const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
const region={x:0,y:0,width:2,height:2};
const png='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aHy0AAAAASUVORK5CYII=';
function captureBuffer(d:CaptureDescriptor){
  const buffer=new ArrayBuffer(128+d.width*d.height*4),v=new DataView(buffer);
  v.setUint32(0,0x4c524350,false);v.setUint16(4,1,true);v.setUint16(6,128,true);
  for(const [name,offset] of [['epoch',8],['shm_instance',24],['capture_id',40]] as const)
    for(let i=0;i<16;i++)v.setUint8(offset+i,parseInt(d[name].slice(i*2,i*2+2),16));
  for(const [name,offset] of [['seq',56],['generation',64],['document_id',72],['ticket',80]] as const)v.setBigUint64(offset,BigInt(d[name]),true);
  for(const [name,offset] of [['width',88],['height',92],['presentation_width',96],['presentation_height',100]] as const)v.setUint32(offset,d[name],true);
  v.setBigUint64(104,BigInt(d.width*d.height*4),true);return buffer;
}
function fixture(){
  let counter=0,descriptor:CaptureDescriptor,refreshes=0;
  const sent:{request:ColorActionRequest;preview:boolean}[]=[],cancelled:{id:string;ticket:string|null}[]=[];
  const replies=new Map<string,(reply:unknown)=>void>();
  const api:ColorActionTransport={
    arm:async(id,documentId,action,channel)=>{
      descriptor={version:1,epoch:'1'.repeat(32),shm_instance:'2'.repeat(32),capture_id:id,ticket:'5',generation:'11',seq:'9',document_id:documentId,
        width:2,height:2,presentation_width:2,presentation_height:2,domain:'color-action-input',quality:'proxy-float-input',profile:'working-srgb',
        picker_action:action,picker_channel:channel,source_stage:colorActionStage(action,channel)};
      return {ticket:'5'};
    },
    status:async()=>({phase:'ready',capture_id:descriptor.capture_id,ticket:descriptor.ticket,descriptor}),
    frame:async()=>captureBuffer(descriptor),presented:async()=>({eligible:true}),
    cancel:async(id,ticket)=>{cancelled.push({id,ticket});},
    submit:async(request,preview)=>{sent.push({request,preview});},
    result:async(id)=>new Promise(resolve=>replies.set(id,resolve)),
  };
  const flow=createColorActionWorkflow(api,{id:()=>String(++counter).padStart(32,'0'),refresh:async()=>{++refreshes;},timeoutMs:1000});
  flow.context({enabled:true,documentId:'7',contextKey:'original'});
  async function ready(action:ColorAction='curve'){
    await flow.start(action,'master');await flow.presented(flow.snapshot().frame!.descriptor);
  }
  function packet(index:number,patch:Record<string,unknown>={}){
    const {request:r,preview}=sent[index];
    const sample={version:1,action:r.action,channel:r.channel,policy:'stage-targeted-srgb-v1',mean_srgb:[.5,.5,.5],hsl:[0,0,.5],samples:r.region.width*r.region.height,region:r.region,source_stage:colorActionStage(r.action,r.channel),
      ...(r.action==='curve'?{point:[.5,.5+r.delta],point_index:1,sample_x:.5,achieved_delta:r.delta}:r.action==='hsl'?{weights:[1,0,0,0,0,0,0,0],achieved_delta:r.delta}:{})};
    return {phase:'done',request_id:r.request_id,result:{protocol:1,...r,success:true,outcome_unknown:false,sample,
      ...(preview?{preview:{format:'png',width:1,height:1,domain:'targeted-tool-stage',quality:'bounded-proxy-float-operator',data:png}}:
        {before:r.action==='hsl'?Array(24).fill(0):{},after:r.action==='hsl'?Array(24).fill(0):{},history:{undo_steps:1,redo_steps:0},requires_reload:false,no_change:false}),...patch}};
  }
  function resolve(index:number,patch:Record<string,unknown>={}){const r=sent[index].request;const reply=replies.get(r.request_id);assert.ok(reply,'original request must be polled');reply(packet(index,patch));}
  return {flow,api,sent,cancelled,ready,packet,resolve,replies,refreshes:()=>refreshes};
}

test('continuous drag has one in-flight and latest-only pending preview, then one final commit',async()=>{
  const f=fixture();await f.ready();f.flow.select(region);await tick();
  f.flow.adjust(.1);f.flow.adjust(.2);f.flow.adjust(.3);f.flow.finish();
  assert.equal(f.sent.length,1);f.resolve(0);await tick();
  assert.equal(f.sent.length,2);assert.equal(f.sent[1].request.delta,.3);assert.ok(f.flow.snapshot().preview);
  assert.equal(f.flow.snapshot().phase,'probing');f.resolve(1);await tick();
  assert.equal(f.sent.length,3);assert.equal(f.sent[2].preview,false);assert.equal(f.sent[2].request.delta,.3);
  f.flow.finish();f.flow.cancel();assert.equal(f.sent.length,3);assert.equal(f.flow.busy(),true);
  f.flow.context({enabled:false,documentId:'8',contextKey:'other'});assert.equal(f.flow.busy(),true);
  f.resolve(2);await tick();assert.equal(f.flow.snapshot().phase,'success');assert.equal(f.refreshes(),1);f.flow.stop();
});
test('curve and HSL click-only selects and previews without a mutation',async()=>{
  for(const action of ['curve','hsl'] as const){const f=fixture();await f.ready(action);f.flow.select(region);f.flow.finish();await tick();f.resolve(0);await tick();
    assert.equal(f.sent.length,1);assert.equal(f.sent[0].preview,true);assert.equal(f.sent[0].request.channel,'master');
    assert.equal(f.flow.snapshot().phase,'ready');assert.ok(f.flow.snapshot().preview);f.flow.stop();}
});
test('levels click automatically applies only after its exact preview succeeds',async()=>{
  const f=fixture();await f.ready('levels_black');f.flow.select(region);f.flow.finish();await tick();
  assert.equal(f.sent.length,1);f.resolve(0);await tick();assert.equal(f.sent.length,2);assert.equal(f.sent[1].preview,false);
  f.resolve(1);await tick();assert.equal(f.flow.snapshot().phase,'success');f.flow.stop();
});
test('Escape or pointercancel while waiting for the last preview cannot submit',async()=>{
  const f=fixture();await f.ready();f.flow.select(region);f.flow.adjust(.2);f.flow.finish();await tick();f.flow.cancel();
  f.resolve(0);await tick();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'idle');assert.equal(f.flow.busy(),false);f.flow.stop();
});
test('a changed region never displays the old region preview or commits from it',async()=>{
  const f=fixture();await f.ready();f.flow.select(region);await tick();f.flow.select({x:1,y:1,width:1,height:1});f.flow.adjust(.1);f.flow.finish();
  f.resolve(0);await tick();assert.equal(f.flow.snapshot().preview,null);assert.equal(f.sent.length,2);f.flow.cancel();f.resolve(1);await tick();f.flow.stop();
});
test('a mismatched commit receipt remains blocked; retry checks the original request only',async()=>{
  const f=fixture();await f.ready();f.flow.select(region);f.flow.adjust(.1);f.flow.finish();await tick();f.resolve(0);await tick();f.resolve(1);await tick();
  f.resolve(2,{document_id:'99'});await tick();assert.equal(f.flow.snapshot().phase,'uncertain');
  await f.flow.start('hsl');assert.equal(f.sent.length,3);
  const check=f.flow.check();await tick();f.resolve(2);await check;assert.equal(f.sent.length,3);assert.equal(f.flow.snapshot().phase,'success');f.flow.stop();
});
test('cancelled arming releases a late ticket instead of displaying its frame',async()=>{
  const f=fixture();let arm!:(value:{ticket:string})=>void;
  f.api.arm=()=>new Promise(resolve=>{arm=resolve;});const pending=f.flow.start('curve');f.flow.cancel();arm({ticket:'18'});await pending;
  assert.ok(f.cancelled.some(value=>value.ticket==='18'));assert.equal(f.flow.snapshot().frame,null);f.flow.stop();
});
test('HSL commit recipes are 24-value arrays and stage previews have strict provenance',()=>{
  assert.doesNotThrow(()=>validateColorCommit({action:'hsl',before:Array(24).fill(0),after:Array(24).fill(0),no_change:true,requires_reload:false,history:{undo_steps:0,redo_steps:0}}));
  assert.throws(()=>validateColorCommit({action:'hsl',before:{},after:{},no_change:true,requires_reload:false,history:{undo_steps:0,redo_steps:0}}));
  assert.throws(()=>validateColorPreview({format:'png',width:1,height:1,domain:'final-output',quality:'bounded-proxy-float-operator',data:png}));
});
