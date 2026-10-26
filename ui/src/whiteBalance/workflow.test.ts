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

// AUTHORED / UNRUN: new automatic route is not covered by historical test passes.
const autoInput={input_id:'a'.repeat(64),recipe_document_id:'recipe',recipe_revision:'7'};
test('auto captures exact input and a no-change receipt is not a new history claim',async()=>{
  const f=fixture();f.flow.context({enabled:true,documentId:'doc',autoAvailable:true,autoInput});
  f.ports.query=async()=>f.complete(f.sent[0],{original_request:{cmd:'white_balance',...f.sent[0]},phase:'no_change',no_change:true,
    diagnostic:{origin:'classic-statistical-estimate',policy:'stratified-trimmed-log-gray-world-v1'}});
  await f.flow.start('auto',undefined,'doc',f.flow.generation(),autoInput.input_id);
  assert.equal(f.sent.length,1);assert.equal(f.sent[0].input_id,autoInput.input_id);
  assert.equal(f.flow.snapshot().phase,'success');assert.match(f.flow.snapshot().message,/未增加历史/);
});
test('auto refuses unavailable helper and stale input instead of falling back',async()=>{
  const f=fixture();f.flow.context({enabled:true,documentId:'doc',autoAvailable:false,autoInput});
  await f.flow.start('auto',undefined,'doc',f.flow.generation(),autoInput.input_id);assert.equal(f.sent.length,0);
  f.flow.context({enabled:true,documentId:'doc',autoAvailable:true,autoInput});
  await f.flow.start('auto',undefined,'doc',f.flow.generation(),'stale');assert.equal(f.sent.length,0);
});
test('unknown auto cannot unlock on photo navigation or resubmit after remount',async()=>{
  const f=fixture();f.flow.context({enabled:true,documentId:'doc',autoAvailable:true,autoInput});
  f.ports.send=async(r:Request)=>{f.sent.push(r);throw Error('transport unknown');};
  await f.flow.start('auto',undefined,'doc',f.flow.generation(),autoInput.input_id);
  f.flow.context({enabled:true,documentId:'another',autoAvailable:true,autoInput});
  f.flow.acknowledgeAfterReload();assert.equal(f.flow.snapshot().phase,'uncertain');
  f.flow.stop();f.flow.activate();await f.flow.start('auto',undefined,'another',f.flow.generation(),autoInput.input_id);
  assert.equal(f.sent.length,1);
});
test('auto rejects a terminal receipt for another input and queries without resending',async()=>{
  const f=fixture();f.flow.context({enabled:true,documentId:'doc',autoAvailable:true,autoInput});
  f.ports.query=async()=>f.complete(f.sent[0],{original_request:{cmd:'white_balance',...f.sent[0],input_id:'b'.repeat(64)},
    phase:'applied',diagnostic:{origin:'classic-statistical-estimate',policy:'stratified-trimmed-log-gray-world-v1'}});
  await f.flow.start('auto',undefined,'doc',f.flow.generation(),autoInput.input_id);
  assert.equal(f.flow.snapshot().phase,'uncertain');await f.flow.check();assert.equal(f.sent.length,1);
});
