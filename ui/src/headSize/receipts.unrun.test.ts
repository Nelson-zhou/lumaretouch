// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. Receipt fixtures are not native publication evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {confirmedPublication,innerReceipt} from './receipts.ts';
import type {HeadSizeView,Result} from './model.ts';
import type {Reply} from './nativeTransport.ts';
const receipt=():Result=>({phase:'done',request_id:'head-inner-1',success:true,outcome_unknown:false,rendered:true,unapplied_reason:null,view:{publication:{request_id:'head-inner-1',rendered:true,unapplied_reason:null}} as HeadSizeView});
const reply=(r?:Result,action:Reply['action']='status'):Reply=>({event:'head_size_result',protocol:1,request_id:'head-outer-1',action,success:true,outcome_unknown:false,result:r?{receipt:r}:{}});
test('actual publication request identity and rendered/reason fields must match exactly',()=>{
 assert.equal(confirmedPublication(receipt()),true);
 for(const patch of [{rendered:undefined},{unapplied_reason:'not applied'},{outcome_unknown:true},{success:false},{view:undefined}])assert.equal(confirmedPublication({...receipt(),...patch}),false);
 const wrong=receipt();wrong.view!.publication!.request_id='other';assert.equal(confirmedPublication(wrong),false);
 const retained=receipt();retained.rendered=false;retained.unapplied_reason='missing head native core';retained.view!.publication={request_id:retained.request_id,rendered:false,unapplied_reason:retained.unapplied_reason};assert.equal(confirmedPublication(retained),true);
 retained.view!.publication!.unapplied_reason='different';assert.equal(confirmedPublication(retained),false);
});
test('failed read-only status and missing receipts never become negative execution proof',()=>{
 const failed={...reply(),success:false,error:'status unavailable'};
 const unknown=innerReceipt(failed,'head-inner-1');assert.equal(unknown.phase,'pending');assert.equal(unknown.outcome_unknown,true);
 const mismatched=receipt();mismatched.request_id='other';assert.equal(innerReceipt(reply(mismatched),'head-inner-1').outcome_unknown,true);
 const originalRejected=innerReceipt({...failed,action:'edit'},'head-inner-1');assert.equal(originalRejected.phase,'done');assert.equal(originalRejected.success,false);assert.equal(originalRejected.outcome_unknown,false);
});
test('success-looking receipt missing actual publication cannot unlock writes',()=>{
 const r=receipt();delete r.view!.publication;
 const result=innerReceipt(reply(r),'head-inner-1');assert.equal(result.phase,'pending');assert.equal(result.outcome_unknown,true);
 assert.deepEqual(innerReceipt(reply(receipt()),'head-inner-1'),receipt());
});
