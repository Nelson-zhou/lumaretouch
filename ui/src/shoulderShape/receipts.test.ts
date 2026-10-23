// Authored regression sources only. Not run in this source-only tranche.
import test from 'node:test';import assert from 'node:assert/strict';
import {innerReceipt} from './receipts.ts';
import type {Reply} from './nativePort.ts';
const reply=(patch:Partial<Reply>):Reply=>({event:'shoulder_shape_result',protocol:1,action:'status',request_id:'outer',success:true,outcome_unknown:false,...patch});
test('failed status lookup cannot resolve the original edit as rejected',()=>{const r=innerReceipt(reply({success:false,error:'source unavailable'}),'inner');assert.equal(r.phase,'pending');assert.equal(r.outcome_unknown,true);});
test('missing receipt remains unknown even when lookup succeeded',()=>{assert.equal(innerReceipt(reply({result:{view_error:'source missing'}}),'inner').outcome_unknown,true);});
test('authoritative inner failure resolves without any current source view',()=>{const receipt={phase:'done' as const,request_id:'inner',success:false,outcome_unknown:false,error:'original edit rejected'};assert.deepEqual(innerReceipt(reply({result:{receipt}}),'inner'),receipt);});
test('wrong inner identity never clears the pending mutation',()=>{assert.equal(innerReceipt(reply({result:{receipt:{phase:'done',request_id:'other',success:false,outcome_unknown:false}}}),'inner').phase,'pending');});
test('confirmed original-edit rejection remains a known non-write',()=>{assert.equal(innerReceipt(reply({action:'edit',success:false,error:'not submitted'}),'inner').outcome_unknown,false);});
