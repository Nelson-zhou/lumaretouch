// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN; synthetic state checks, not image or quality evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {adjust,check,neutral,checkSupport,type Support} from './model.ts';
test('overall sets thigh/calf, never an additional intensity',()=>{
 const pair=adjust(adjust(neutral(),'thigh',.4),'calf',-.2);
 assert.deepEqual(pair,{version:1,thigh:.4,calf:-.2});
 assert.deepEqual(adjust(pair,'overall',.3),{version:1,thigh:.3,calf:.3});
 assert.throws(()=>check({...pair,overall:.3} as typeof pair));
});
test('reject ranges, nonfinite values and invented bilateral unlock',()=>{
 for(const n of [NaN,Infinity,-1.1,1.1])assert.throws(()=>adjust(neutral(),'thigh',n));
 assert.throws(()=>check({...neutral(),linked:true} as ReturnType<typeof neutral>));
});
test('missing visible contour evidence cannot become a review',()=>{
 assert.throws(()=>checkSupport({version:1,method:'user-reviewed-visible-silhouette',stations:[.25,.5,.75],segments:{}} as Support));
});
