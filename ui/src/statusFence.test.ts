import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createStatusFence} from './statusFence.ts';
test('a delayed thumbnail continuation cannot restore the previous document controls',async()=>{
  const fence=createStatusFence(),a=fence.issue(),applied:string[]=[];assert.ok(fence.accept(a,10));
  let resume!:()=>void;const wait=new Promise<void>(r=>resume=r);
  const old=(async()=>{await wait;if(fence.current(a,10))applied.push('old');})();
  const b=fence.issue();assert.ok(fence.accept(b,11));applied.push('new');resume();await old;
  assert.deepEqual(applied,['new']);
});
test('same-revision newer snapshots supersede old reads, but pending reads do not starve accepted work',()=>{
  const f=createStatusFence(),a=f.issue();assert.ok(f.accept(a,1));const b=f.issue();
  assert.ok(f.current(a,1));assert.ok(f.accept(b,1));assert.equal(f.current(a,1),false);
  assert.equal(f.accept(a,1),false);assert.equal(f.accept(f.issue(),0),false);assert.ok(f.current(b,1));
});
