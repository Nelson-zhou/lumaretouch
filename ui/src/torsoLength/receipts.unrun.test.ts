// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No transport, native core, import, compiler or test runner executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {innerReceipt} from './receipts.ts';
import type {Reply} from './nativeTransport.ts';
const reply=(patch:Partial<Reply>={}):Reply=>({event:'torso_length_result',protocol:1,action:'status',request_id:'outer-1',success:true,outcome_unknown:false,...patch});
test('failed read and absent or wrong inner receipt remain unknown, never negative execution proof',()=>{
 assert.equal(innerReceipt(reply({success:false,error:'not found'}),'inner-1').outcome_unknown,true);
 assert.equal(innerReceipt(reply({result:{receipt:{phase:'done',request_id:'other',success:true,outcome_unknown:false}}}),'inner-1').phase,'pending');
 assert.equal(innerReceipt(reply({result:{receipt:{phase:'unavailable',request_id:'inner-1'}}}),'inner-1').outcome_unknown,true);
 assert.equal(innerReceipt(reply({action:'edit',success:false,outcome_unknown:true}),'inner-1').phase,'pending');
});
test('only original edit rejection or matching explicit terminal receipt establishes outcome',()=>{
 assert.deepEqual(innerReceipt(reply({action:'edit',success:false,error:'rejected'}),'inner-1'),{phase:'done',request_id:'inner-1',success:false,outcome_unknown:false,error:'rejected'});
 const receipt={phase:'done' as const,request_id:'inner-1',success:true,outcome_unknown:false,rendered:false,unapplied_reason:'native unavailable'};
 assert.deepEqual(innerReceipt(reply({result:{receipt}}),'inner-1'),receipt);
});
