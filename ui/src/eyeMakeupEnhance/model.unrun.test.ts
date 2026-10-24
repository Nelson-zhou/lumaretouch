// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED / UNRUN: synthetic model checks, not browser or photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {check, neutral, OP, CONTROLS, adjustPatches, linkPatches, resetPatches, zeroSidePatches, parseChoice, targetReady, proofValid, verifiedImage} from './model';
test('four independently linked signed bilateral controls',()=>{
  const r=neutral();r.amount={linked:false,left:-.5,right:.3};r.structure={linked:false,left:.8,right:0};
  assert.deepEqual(check(r),r);assert.equal(CONTROLS.length,4);
  for(const bad of [NaN,Infinity,true,1.01]){const v=structuredClone(r) as unknown as Record<string,unknown>;v.amount={linked:false,left:bad,right:0};assert.throws(()=>check(v));}
  assert.throws(()=>check({...r,saturation:{linked:true,left:0,right:.2}}));
});
test('atomic link and one-side neutral recovery touch no other controls',()=>{
  assert.deepEqual(adjustPatches('brightness','left',.2,false),[{operation_id:OP,parameter_path:'/brightness/left',value:.2,unset:false}]);
  assert.equal(linkPatches('amount',-.4).length,3);
  assert.deepEqual(zeroSidePatches('structure','right').map(p=>p.parameter_path),['/structure/linked','/structure/right']);
  assert.equal(resetPatches().length,8);assert.equal(resetPatches('amount').length,2);
});
test('blank and invalid text never become zero',()=>{
  assert.equal(parseChoice(''),null);assert.equal(parseChoice('  '),null);assert.equal(parseChoice('NaN'),null);
  assert.equal(parseChoice('10x'),null);assert.equal(parseChoice('-25'),-.25);assert.equal(parseChoice('0'),0);
});
test('missing current owner and fake preview proof remain closed',async()=>{
  assert.equal(targetReady(null),false);assert.equal(proofValid({source:'donor'}),false);
  await assert.rejects(verifiedImage(null,null));
});
