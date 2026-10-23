// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN. Synthetic contract fixtures are not photographic acceptance.
import test from 'node:test';
import assert from 'node:assert/strict';
import {check,neutral,checkSupport,STATIONS,CONFIRMATIONS,type Support} from './model.ts';
const fixture=():Support=>({version:1,upper:.2,lower:.8,stations:[...STATIONS],negative:Array(9).fill(.08),positive:Array(9).fill(.1),region:{selection_box:[.1,.1,.9,.9],exclusions:[]},confirmations:Object.fromEntries(Object.keys(CONFIRMATIONS).map(k=>[k,true])) as Support['confirmations']});
test('waist is one inward original-range amount without bilateral unlock or length',()=>{
 assert.deepEqual(neutral(),{version:1,amount:0});assert.equal(check({version:1,amount:1}).amount,1);
 for(const amount of [-.01,1.01,NaN,Infinity])assert.throws(()=>check({version:1,amount}));
 assert.throws(()=>check({...neutral(),linked:true} as unknown as ReturnType<typeof neutral>));
});
test('bilateral measurements remain distinct and immutable',()=>{
 const raw=fixture(),checked=checkSupport(raw);assert.notDeepEqual(checked.negative,checked.positive);raw.negative[0]=.5;assert.equal(checked.negative[0],.08);
});
test('missing side, hidden anatomy flags, reversed bounds and invalid region are rejected',()=>{
 const absent=fixture();absent.positive=[];assert.throws(()=>checkSupport(absent));
 const occluded=fixture();occluded.confirmations.not_occluded=false as unknown as true;assert.throws(()=>checkSupport(occluded));
 const reversed=fixture();reversed.lower=.1;assert.throws(()=>checkSupport(reversed));
 const region=fixture();region.region.selection_box=[.5,.5,.4,.4];assert.throws(()=>checkSupport(region));
});
