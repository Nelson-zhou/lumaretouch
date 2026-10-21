import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRefreshPump} from './refreshPump.ts';
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(read:()=>Promise<boolean>){
  let id=0;const pending=new Map<number,()=>void>();
  const pump=createRefreshPump(read,fn=>{pending.set(++id,fn);return id;},i=>{pending.delete(i);});
  return {pump,pending,run(){const [i,fn]=pending.entries().next().value!;pending.delete(i);fn();}};
}
test('many slider submissions cause one status read, not one each',async()=>{
  let reads=0;const f=fixture(async()=>{reads++;return false;});
  for(let i=0;i<100;i++)f.pump.trigger();
  assert.equal(f.pending.size,1);f.run();await tick();assert.equal(reads,1);assert.equal(f.pending.size,0);
});
test('busy queue is followed until final values are readable',async()=>{
  let reads=0;const f=fixture(async()=>++reads<3);f.pump.trigger();
  for(let i=0;i<3;i++){f.run();await tick();}
  assert.equal(reads,3);assert.equal(f.pending.size,0);
});
test('new submission during in-flight read gets a trailing read',async()=>{
  let release!:(busy:boolean)=>void;let reads=0;
  const f=fixture(()=>++reads===1?new Promise(resolve=>{release=resolve;}):Promise.resolve(false));
  f.pump.trigger();f.run();f.pump.trigger();assert.equal(f.pending.size,0);
  release(false);await tick();assert.equal(f.pending.size,1);f.run();await tick();assert.equal(reads,2);
});
test('dispose prevents queued and in-flight reads from restarting',async()=>{
  let release!:(busy:boolean)=>void;
  const f=fixture(()=>new Promise(resolve=>{release=resolve;}));
  f.pump.trigger();f.run();f.pump.dispose();release(true);await tick();assert.equal(f.pending.size,0);
  f.pump.trigger();assert.equal(f.pending.size,0);
});
