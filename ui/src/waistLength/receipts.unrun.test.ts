// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No transport, native core, import, compiler or test runner executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {confirmedPublication,innerReceipt} from './receipts.ts';
import type {Result,WaistLengthView} from './model.ts';
import type {Reply} from './nativeTransport.ts';
const reply=(patch:Partial<Reply>={}):Reply=>({event:'waist_length_result',protocol:1,action:'status',request_id:'outer-1',success:true,outcome_unknown:false,...patch});
function saved(rendered=false):Result{
 const publication={request_id:'inner-1',rendered,unapplied_reason:rendered?null:'native unavailable'};
 const view:WaistLengthView={binding:{document_id:'doc-1',document_epoch:'epoch-1',document_revision:2,asset_sha256:'a'.repeat(64)},state_revision:2,association_revision:1,people_association_revision:1,body_graph_sha256:'b'.repeat(64),people_graph_sha256:'c'.repeat(64),bodies:[],selected_body_ref:null,recipe:{version:1,amount:0},refusals:[],publication};
 return {phase:'done',request_id:'inner-1',success:true,outcome_unknown:false,rendered,unapplied_reason:publication.unapplied_reason,view};
}
test('failed read and absent or wrong inner receipt remain unknown, never negative execution proof',()=>{
 assert.equal(innerReceipt(reply({success:false,error:'not found'}),'inner-1').outcome_unknown,true);
 assert.equal(innerReceipt(reply({result:{receipt:{phase:'done',request_id:'other',success:true,outcome_unknown:false}}}),'inner-1').phase,'pending');
 assert.equal(innerReceipt(reply({result:{receipt:{phase:'unavailable',request_id:'inner-1'}}}),'inner-1').outcome_unknown,true);
 assert.equal(innerReceipt(reply({action:'edit',success:false,outcome_unknown:true}),'inner-1').phase,'pending');
 assert.equal(innerReceipt(reply({action:'edit',success:false,result:{receipt:{...saved(),request_id:'other'}}}),'inner-1').outcome_unknown,true);
});
test('only original edit rejection or matching explicit terminal receipt establishes outcome',()=>{
 assert.deepEqual(innerReceipt(reply({action:'edit',success:false,error:'rejected'}),'inner-1'),{phase:'done',request_id:'inner-1',success:false,outcome_unknown:false,error:'rejected'});
 const receipt=saved();assert.deepEqual(innerReceipt(reply({result:{receipt}}),'inner-1'),receipt);assert.equal(confirmedPublication(receipt),true);
 const applied=saved(true);assert.equal(confirmedPublication(applied),true);assert.deepEqual(innerReceipt(reply({result:{receipt:applied}}),'inner-1'),applied);
});
test('a success missing rendered, reason or matching canonical publication stays unknown',()=>{
 const cases:Result[]=[{...saved(),rendered:undefined},{...saved(),unapplied_reason:undefined},{...saved(),unapplied_reason:null},{...saved(),unapplied_reason:''},{...saved(true),unapplied_reason:'not rendered'},{...saved(),view:undefined}];
 for(const patch of [{request_id:'other'},{rendered:true},{unapplied_reason:'changed'}]){const value=saved();value.view!.publication={...value.view!.publication!,...patch};cases.push(value);}
 for(const receipt of cases){assert.equal(confirmedPublication(receipt),false);const result=innerReceipt(reply({result:{receipt}}),'inner-1');assert.equal(result.phase,'pending');assert.equal(result.outcome_unknown,true);}
});
