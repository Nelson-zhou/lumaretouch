// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. Algebra/schema fixtures are not photo or UI acceptance.
import {describe,it} from 'node:test';
import assert from 'node:assert/strict';
import {check,neutralFamily,targets,JOINTS,REQUIREMENT_ID} from './model.ts';
describe('isolated honest arm contract',()=>{
 it('retains one requirement and exact per-segment visible anchors',()=>{assert.equal(REQUIREMENT_ID,'LNX-REF-PC-32473-C-5d25f1744f');assert.deepEqual(JOINTS.left_forearm,[13,15]);assert.deepEqual(JOINTS.right_upper,[12,14]);});
 it('keeps the other side neutral',()=>{const f=neutralFamily();f.left_upper.amount=.4;assert.equal(check(f).right_upper.amount,0);assert.equal(check(f).left_forearm.amount,0);});
 it('defines linking as explicit targets rather than an extra amplitude',()=>{assert.deepEqual(targets('left_upper',true,false),['left_upper','right_upper']);assert.deepEqual(targets('right_forearm',false,true),['right_upper','right_forearm']);});
 it('refuses nonfinite/out-of-range strength',()=>{const f=neutralFamily();f.left_upper.amount=NaN;assert.throws(()=>check(f));f.left_upper.amount=1.01;assert.throws(()=>check(f));});
});
