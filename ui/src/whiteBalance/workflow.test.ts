import test from 'node:test';
import assert from 'node:assert/strict';
import {createWhiteBalanceWorkflow,type Request} from './workflow.ts';
const tick=()=>new Promise<void>(resolve=>setImmediate(resolve));
function fixture(timeoutMs=1000){
  const sent:Request[]=[];let reply:unknown;let refreshed=0;
  const ports={send:async(r:Request)=>{sent.push(r);},query:async()=>reply,refresh:async()=>{refreshed++;},id:()=>`r${sent.length}`,sleep:async()=>{},timeoutMs};
  const flow=createWhiteBalanceWorkflow(ports);flow.context({enabled:true,documentId:'doc'});
  const complete=(r:Request,patch={})=>({phase:'done',request_id:r.request_id,result:{protocol:1,...r,success:true,outcome_unknown:false,requires_reload:false,
    after:{temperature_shift:0,tint_shift:0,options:{algorithm:r.algorithm??'legacy-xyz-ratio-v1',picked_gains:[1,1,1]}},...patch}});
  return {flow,ports,sent,complete,setReply:(x:unknown)=>{reply=x;},refreshes:()=>refreshed};
}
test('queue acceptance is not completion; matching terminal evidence is required',async()=>{
  const f=fixture();let resolve!:(x:unknown)=>void;
  f.ports.query=()=>new Promise(r=>{resolve=r;});
  const work=f.flow.start('reset',undefined,'doc');await tick();
  assert.equal(f.flow.snapshot().phase,'waiting');assert.equal(f.refreshes(),0);
  resolve(f.complete(f.sent[0]));await work;
  assert.equal(f.flow.snapshot().phase,'success');assert.equal(f.refreshes(),1);
});
test('wrong document receipt locks without automatic resend',async()=>{
  const f=fixture();f.ports.query=async()=>f.complete(f.sent[0],{document_id:'other'});
  await f.flow.start('reset',undefined,'doc');assert.equal(f.flow.snapshot().phase,'uncertain');
  await f.flow.start('reset',undefined,'doc');assert.equal(f.sent.length,1);
});
test('timeout queries the original request and never submits twice',async()=>{
  const f=fixture();f.ports.query=async()=>({phase:'pending',request_id:f.sent[0].request_id});
  await f.flow.start('reset',undefined,'doc');assert.equal(f.flow.snapshot().phase,'uncertain');
  f.ports.query=async()=>f.complete(f.sent[0]);await f.flow.check();assert.equal(f.sent.length,1);assert.equal(f.flow.snapshot().phase,'success');
});
test('document change during confirmation prevents submission',async()=>{
  const f=fixture();f.flow.context({enabled:true,documentId:'new'});
  await f.flow.start('set_algorithm','linear-srgb-d-white-ratio-v1','doc');assert.equal(f.sent.length,0);
});
test('unknown outcome can only be unlocked after a different loaded document',async()=>{
  const f=fixture();f.ports.send=async()=>{throw Error('lost connection');};
  await f.flow.start('reset',undefined,'doc');f.flow.acknowledgeAfterReload();assert.equal(f.flow.snapshot().phase,'uncertain');
  f.flow.context({enabled:true,documentId:'reloaded'});f.flow.acknowledgeAfterReload();assert.equal(f.flow.snapshot().phase,'idle');
});
test('refresh failure does not undo a confirmed mutation',async()=>{
  const f=fixture();f.ports.query=async()=>f.complete(f.sent[0]);f.ports.refresh=async()=>{throw Error('refresh failed');};
  await f.flow.start('reset',undefined,'doc');assert.equal(f.flow.snapshot().phase,'success');assert.match(f.flow.snapshot().message,/刷新失败/);
});
test('wrong resulting algorithm cannot be accepted as success',async()=>{
  const f=fixture();f.ports.query=async()=>f.complete(f.sent[0],{after:{options:{algorithm:'legacy-xyz-ratio-v1'}}});
  await f.flow.start('set_algorithm','linear-srgb-d-white-ratio-v1','doc');assert.equal(f.flow.snapshot().phase,'uncertain');
});

test('hung send and query become uncertain without resending',async()=>{
  for(const stage of ['send','query'] as const){
    const f=fixture(2);f.ports[stage]=()=>new Promise<never>(()=>{});
    await f.flow.start('reset',undefined,'doc');assert.equal(f.flow.snapshot().phase,'uncertain');
  }
});
test('hung refresh retains confirmed success and late response cannot overwrite a stopped owner',async()=>{
  const f=fixture(2);f.ports.query=async()=>f.complete(f.sent[0]);f.ports.refresh=()=>new Promise<never>(()=>{});
  await f.flow.start('reset',undefined,'doc');assert.equal(f.flow.snapshot().phase,'success');assert.match(f.flow.snapshot().message,/刷新失败/);
  const g=fixture();let resolve!:(x:unknown)=>void;g.ports.query=()=>new Promise(r=>{resolve=r;});
  const task=g.flow.start('reset',undefined,'doc');await tick();
  g.flow.stop();resolve(g.complete(g.sent[0]));await task;
  assert.equal(g.flow.snapshot().phase,'uncertain');assert.equal(g.refreshes(),0);
});

test('a disposed owner and stale confirmation cannot submit a new mutation',async()=>{
  const f=fixture();const generation=f.flow.generation();f.flow.stop();
  await f.flow.start('reset',undefined,'doc');assert.equal(f.sent.length,0);
  f.flow.activate();await f.flow.start('set_algorithm','linear-srgb-d-white-ratio-v1','doc',generation);
  assert.equal(f.sent.length,0);
});
