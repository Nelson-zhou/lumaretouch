// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No real engine, inference, native rendering or UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {WaistLengthController} from './controller.ts';
import {neutral,type Request,type Result,type WaistLengthView} from './model.ts';
const ref={asset_sha256:'a'.repeat(64),body_instance_id:'body-1',analysis_revision:1};
function view(amount=0,state_revision=1,document_id='doc-1'):WaistLengthView{return {binding:{document_id,document_epoch:'epoch-1',document_revision:state_revision,asset_sha256:ref.asset_sha256},state_revision,association_revision:1,people_association_revision:1,body_graph_sha256:`body-${state_revision}`,people_graph_sha256:'people-1',bodies:[],selected_body_ref:{...ref},recipe:{version:1,amount},refusals:[]};}
const done=(r:Request,v:WaistLengthView):Result=>({phase:'done',request_id:r.request_id,success:true,outcome_unknown:false,rendered:true,unapplied_reason:null,view:{...v,publication:{request_id:r.request_id,rendered:true,unapplied_reason:null}}});
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
test('latest unsent signed amount wins and canonical base advances, no extra history owner',async()=>{
 const sent:Request[]=[],resolvers:((r:Result)=>void)[]=[];
 const controller=new WaistLengthController({send:r=>{sent.push(r);return new Promise(resolve=>resolvers.push(resolve));},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.1}),'gesture-a');controller.edit(r=>({...r,amount:.2}),'gesture-b');controller.edit(r=>({...r,amount:-.3}),'gesture-b');
 assert.equal(sent.length,1);resolvers[0](done(sent[0],view(.1,2)));await tick();
 assert.equal(sent.length,2);assert.deepEqual(sent[1].payload.recipe,{version:1,amount:-.3});assert.deepEqual(sent[1].payload.base,{version:1,amount:.1});assert.equal(sent[1].gesture_id,'gesture-b');
 resolvers[1](done(sent[1],view(-.3,3)));await tick();assert.equal(controller.snapshot().phase,'idle');
});
test('uncertain mutation is never replayed and explicit reconcile queries its original ID',async()=>{
 const sent:Request[]=[],queried:string[]=[];
 const controller=new WaistLengthController({send:async r=>{sent.push(r);throw Error('lost acknowledgement');},status:async id=>{queried.push(id);return done(sent[0],view(.5,2));}});
 controller.update(view());controller.edit(r=>({...r,amount:.5}),'gesture-a');await tick();
 assert.equal(controller.snapshot().phase,'uncertain');assert.throws(()=>controller.edit(()=>neutral(),'gesture-b'));assert.equal(sent.length,1);
 await controller.reconcile();assert.deepEqual(queried,[sent[0].request_id]);assert.equal(sent.length,1);assert.equal(controller.snapshot().recipe.amount,.5);assert.equal(controller.snapshot().phase,'idle');
});
test('switching documents drops queued intent and old completion cannot replace current selection',async()=>{
 const sent:Request[]=[];let settle:(r:Result)=>void=()=>{};
 const controller=new WaistLengthController({send:r=>{sent.push(r);return new Promise(resolve=>{settle=resolve;});},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.2}),'gesture-a');controller.edit(r=>({...r,amount:.8}),'gesture-b');
 controller.clear();controller.update(view(-.4,7,'doc-2'));settle(done(sent[0],view(.2,2)));await tick();
 assert.equal(sent.length,1);assert.equal(controller.snapshot().view?.binding.document_id,'doc-2');assert.equal(controller.snapshot().recipe.amount,-.4);assert.equal(controller.snapshot().phase,'idle');
});
test('unavailable, incomplete or mismatched receipt never unlocks uncertain writes',async()=>{
 let sent:Request|undefined;
 const controller=new WaistLengthController({send:async r=>{sent=r;return {phase:'done',request_id:r.request_id,success:true};},status:async id=>({phase:'unavailable',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:1}),'gesture-a');await tick();assert.ok(sent);assert.equal(controller.snapshot().phase,'uncertain');
 await controller.reconcile();assert.equal(controller.snapshot().phase,'uncertain');assert.throws(()=>controller.edit(()=>neutral(),'gesture-b'));
});
test('successful-looking receipt without a rendered publication remains uncertain and query-only',async()=>{
 const sent:Request[]=[];
 const controller=new WaistLengthController({send:async r=>{sent.push(r);return {phase:'done',request_id:r.request_id,success:true,outcome_unknown:false,view:view(.2,2)};},status:async()=>done(sent[0],view(.2,2))});
 controller.update(view());controller.edit(r=>({...r,amount:.2}),'gesture-a');await tick();
 assert.equal(controller.snapshot().phase,'uncertain');assert.match(controller.snapshot().message,/实际发布结果/);assert.equal(sent.length,1);
 await controller.reconcile();assert.equal(controller.snapshot().phase,'idle');assert.equal(sent.length,1);
});
test('retained source review is visibly unapplied, and does not flush a queued nonzero effect',async()=>{
 const sent:Request[]=[];let settle:(r:Result)=>void=()=>{};
 const controller=new WaistLengthController({send:r=>{sent.push(r);return new Promise(resolve=>{settle=resolve;});},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view(.2));const saving=controller.action('support_review',{data:'fixture'});
 controller.edit(r=>({...r,amount:.7}),'queued-gesture');
 const receipt=done(sent[0],view(.2,2)),reason='native core unavailable';receipt.rendered=false;receipt.unapplied_reason=reason;receipt.view!.publication={request_id:sent[0].request_id,rendered:false,unapplied_reason:reason};
 settle(receipt);await saving;await tick();assert.equal(sent.length,1);assert.equal(controller.snapshot().phase,'idle');assert.equal(controller.snapshot().recipe.amount,.2);assert.match(controller.snapshot().message,/效果尚未应用/);
});
