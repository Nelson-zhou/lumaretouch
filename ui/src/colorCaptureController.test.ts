import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createColorCaptureController,type CaptureTransport,type CaptureUi} from './colorCaptureController.ts';
import type {CaptureDescriptor} from './captureModel';
const d:CaptureDescriptor={version:1,epoch:'0102030405060708090a0b0c0d0e0f10',shm_instance:'1112131415161718191a1b1c1d1e1f20',
 capture_id:'2122232425262728292a2b2c2d2e2f30',seq:'9007199254740993',generation:'17',document_id:'123',ticket:'22',
 width:1,height:1,presentation_width:1,presentation_height:1,domain:'proxy-output',quality:'proxy-float-output',profile:'working-srgb'};
const deferred=<T>()=>{let resolve!:(v:T)=>void,reject!:(e:unknown)=>void;const promise=new Promise<T>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise<void>(r=>setImmediate(r));
function fixture(patch:Partial<CaptureTransport>={}){
 const cancelled:string[]=[],states:CaptureUi[]=[];
 const hex=readFileSync(new URL('../../docs/protocols/color-capture-v1.hex',import.meta.url),'utf8').trim();
 const bytes=Uint8Array.from(hex.match(/../g)!.map(x=>parseInt(x,16))).buffer;
 const api:CaptureTransport={arm:async()=>({ticket:d.ticket,revision:4}),status:async()=>({phase:'ready',capture_id:d.capture_id,ticket:d.ticket,descriptor:d}),
 frame:async()=>bytes,presented:async()=>({eligible:true}),sample:async()=>({request_ticket:'23'}),cancel:async(id,ticket)=>{cancelled.push(id+':'+ticket);},...patch};
 const controller=createColorCaptureController(api,s=>states.push(s),{uuid:()=>d.capture_id,pause:tick});
 controller.updateContext({documentId:'123',revision:4,allowed:true,reason:''});
 return {controller,cancelled,states,api};
}
test('late arm receipt after cancellation is released and cannot fetch pixels',async()=>{
 const wait=deferred<{ticket:string;revision:number}>();let reads=0;
 const f=fixture({arm:()=>wait.promise,frame:async()=>{reads++;throw Error('must not fetch');}});
 try{const arm=f.controller.arm();f.controller.cancel();wait.resolve({ticket:'22',revision:4});await arm;
 assert.equal(reads,0);assert.equal(f.controller.snapshot().phase,'off');assert.equal(f.cancelled.length,1);}finally{f.controller.dispose();}
});
test('late frame and late presentation acknowledgement cannot rearm a cancelled owner',async()=>{
 const ack=deferred<{eligible:boolean}>(),f=fixture({presented:()=>ack.promise});
 try{await f.controller.arm();assert.equal(f.controller.snapshot().phase,'painting');const pending=f.controller.presented(d);
 f.controller.cancel();ack.resolve({eligible:true});assert.equal(await pending,false);assert.equal(f.controller.snapshot().frame,null);}finally{f.controller.dispose();}
 const frame=deferred<ArrayBuffer>(),g=fixture({frame:()=>frame.promise});
 try{const pending=g.controller.arm();await tick();g.controller.cancel();frame.resolve(new ArrayBuffer(0));await pending;
 assert.equal(g.controller.snapshot().phase,'off');}finally{g.controller.dispose();}
});
test('presentation is idempotent and edits invalidate the captured frame',async()=>{
 let acks=0;const f=fixture({presented:async()=>{acks++;return {eligible:true};}});
 try{await f.controller.arm();assert.equal(await f.controller.presented(d),true);await f.controller.presented(d);assert.equal(acks,1);
 f.controller.updateContext({documentId:'123',revision:5,allowed:true,reason:''});assert.equal(f.controller.snapshot().frame,null);
 assert.equal(await f.controller.presented(d),false);}finally{f.controller.dispose();}
});
test('a rejected obsolete sample cannot drop the newest queued click',async()=>{
 const first=deferred<{request_ticket:string}>();let calls=0,lastRequest='';
 const f=fixture({sample:async(_id,_ticket,request)=>{lastRequest=request;if(++calls===1)return first.promise;return {request_ticket:'24'};}});
 try{await f.controller.arm();await f.controller.presented(d);
 f.api.status=async()=>({phase:'eligible',capture_id:d.capture_id,ticket:d.ticket,sample:{capture_id:d.capture_id,ticket:d.ticket,
 request_id:lastRequest,request_ticket:'24',success:true,error:null,descriptor:d,region:{x:0,y:0,width:1,height:1},
 analysis:{mean_srgb:[.1,.2,.3],mean_lab_d65:[1,2,3],finite_samples:1,nonfinite_samples:0,samples:1}}});
 f.controller.pick({x:0,y:0,size:1});f.controller.pick({x:0,y:0,size:3});first.reject(Error('obsolete failure'));await tick();
 assert.equal(calls,2);assert.equal(f.controller.snapshot().phase,'eligible');assert.equal(f.controller.snapshot().point?.size,3);
 assert.equal(f.controller.snapshot().readout?.request_ticket,'24');}finally{f.controller.dispose();}
});
test('overwritten frame failure never falls back to unbound preview pixels',async()=>{
 const f=fixture({frame:async()=>{throw Error('overwritten');}});
 try{await f.controller.arm();assert.equal(f.controller.snapshot().phase,'error');assert.equal(f.controller.snapshot().frame,null);
 assert.equal(f.cancelled.length,1);}finally{f.controller.dispose();}
});
