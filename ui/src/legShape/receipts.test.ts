// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN; no native execution claim.
import test from 'node:test';
import assert from 'node:assert/strict';
import {innerReceipt} from './receipts.ts';
import type {Reply} from './nativeTransport';
const reply=(patch:Partial<Reply>):Reply=>({event:'leg_shape_result',protocol:1,action:'status',request_id:'outer',success:true,outcome_unknown:false,...patch});
test('failed status is never proof the original mutation did not execute',()=>{
 assert.equal(innerReceipt(reply({success:false,error:'source gone'}),'inner').outcome_unknown,true);
});
test('only confirmed original edit rejection is terminal negative evidence',()=>{
 const result=innerReceipt(reply({action:'edit',success:false,error:'not enqueued'}),'inner');
 assert.equal(result.phase,'done');assert.equal(result.success,false);assert.equal(result.outcome_unknown,false);
});
test('a receipt for a different original request stays unknown',()=>{
 assert.equal(innerReceipt(reply({result:{receipt:{phase:'done',request_id:'other',success:true,outcome_unknown:false}}}),'inner').outcome_unknown,true);
});
