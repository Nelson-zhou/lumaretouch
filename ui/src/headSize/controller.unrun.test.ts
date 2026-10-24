// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED, UNRUN. No inference, native geometry, UI or runtime acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {HeadSizeController} from './controller.ts';
import {neutral,type Request,type Result,type HeadSizeView} from './model.ts';
const ref={asset_sha256:'a'.repeat(64),body_instance_id:'body-1',analysis_revision:1};
function view(amount=0,state_revision=1,document_id='doc-1'):HeadSizeView{return {binding:{document_id,document_epoch:'epoch-1',document_revision:state_revision,asset_sha256:ref.asset_sha256},state_revision,association_revision:1,people_association_revision:1,body_graph_sha256:`body-${state_revision}`,people_graph_sha256:'people-1',bodies:[],selected_body_ref:{...ref},recipe:{version:1,amount},refusals:[]};}
const done=(r:Request,v:HeadSizeView):Result=>({phase:'done',request_id:r.request_id,success:true,outcome_unknown:false,rendered:true,unapplied_reason:null,view:{...v,publication:{request_id:r.request_id,rendered:true,unapplied_reason:null}}});
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
test('latest unsent positive shrink wins while canonical recipe base advances',async()=>{
 const sent:Request[]=[],resolvers:((r:Result)=>void)[]=[];
 const controller=new HeadSizeController({send:r=>{sent.push(r);return new Promise(resolve=>resolvers.push(resolve));},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.1}),'gesture-a');controller.edit(r=>({...r,amount:.2}),'gesture-b');controller.edit(r=>({...r,amount:.3}),'gesture-b');
 assert.equal(sent.length,1);resolvers[0](done(sent[0],view(.1,2)));await tick();
 assert.equal(sent.length,2);assert.deepEqual(sent[1].payload.recipe,{version:1,amount:.3});assert.deepEqual(sent[1].payload.base,{version:1,amount:.1});assert.equal(sent[1].gesture_id,'gesture-b');
 resolvers[1](done(sent[1],view(.3,3)));await tick();assert.equal(controller.snapshot().phase,'idle');
});
test('uncertain mutation cannot replay; reconciliation uses only the original identity',async()=>{
 const sent:Request[]=[],queried:string[]=[];
 const controller=new HeadSizeController({send:async r=>{sent.push(r);throw Error('lost acknowledgement');},status:async id=>{queried.push(id);return done(sent[0],view(.5,2));}});
 controller.update(view());controller.edit(r=>({...r,amount:.5}),'gesture-a');await tick();
 assert.equal(controller.snapshot().phase,'uncertain');assert.throws(()=>controller.edit(()=>neutral(),'gesture-b'));assert.equal(sent.length,1);
 await controller.reconcile();assert.deepEqual(queried,[sent[0].request_id]);assert.equal(sent.length,1);assert.equal(controller.snapshot().recipe.amount,.5);assert.equal(controller.snapshot().phase,'idle');
});
test('switching sources discards queued intent and ignores old completion for new selection',async()=>{
 const sent:Request[]=[];let settle:(r:Result)=>void=()=>{};
 const controller=new HeadSizeController({send:r=>{sent.push(r);return new Promise(resolve=>{settle=resolve;});},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.2}),'gesture-a');controller.edit(r=>({...r,amount:.8}),'gesture-b');
 controller.clear();controller.update(view(.4,7,'doc-2'));settle(done(sent[0],view(.2,2)));await tick();
 assert.equal(sent.length,1);assert.equal(controller.snapshot().view?.binding.document_id,'doc-2');assert.equal(controller.snapshot().recipe.amount,.4);assert.equal(controller.snapshot().phase,'idle');
});
test('graph drift discards queued shrink and prevents stale publication from replacing the graph',async()=>{
 const sent:Request[]=[];let settle:(r:Result)=>void=()=>{};
 const controller=new HeadSizeController({send:r=>{sent.push(r);return new Promise(resolve=>{settle=resolve;});},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.2}),'gesture-a');controller.edit(r=>({...r,amount:.9}),'gesture-b');
 controller.update({...view(.4,8),people_graph_sha256:'people-changed'});settle(done(sent[0],view(.2,2)));await tick();
 assert.equal(sent.length,1);assert.equal(controller.snapshot().recipe.amount,.4);assert.equal(controller.snapshot().view?.state_revision,8);
});
test('missing or mismatched actual publication stays query-only',async()=>{
 const sent:Request[]=[];
 const controller=new HeadSizeController({send:async r=>{sent.push(r);return {phase:'done',request_id:r.request_id,success:true,outcome_unknown:false,view:view(.2,2)};},status:async id=>({phase:'unavailable',request_id:id,outcome_unknown:true})});
 controller.update(view());controller.edit(r=>({...r,amount:.2}),'gesture-a');await tick();
 assert.equal(controller.snapshot().phase,'uncertain');assert.match(controller.snapshot().message,/实际发布结果/);
 await controller.reconcile();assert.equal(controller.snapshot().phase,'uncertain');assert.equal(sent.length,1);assert.throws(()=>controller.edit(()=>neutral(),'gesture-b'));
});
test('retained review is visibly unapplied and cannot flush a queued nonzero effect',async()=>{
 const sent:Request[]=[];let settle:(r:Result)=>void=()=>{};
 const controller=new HeadSizeController({send:r=>{sent.push(r);return new Promise(resolve=>{settle=resolve;});},status:async id=>({phase:'pending',request_id:id,outcome_unknown:true})});
 controller.update(view(.2));const saving=controller.action('support_review',{data:'fixture'});controller.edit(r=>({...r,amount:.7}),'queued-gesture');
 const receipt=done(sent[0],view(.2,2)),reason='native head core unavailable';receipt.rendered=false;receipt.unapplied_reason=reason;receipt.view!.publication={request_id:sent[0].request_id,rendered:false,unapplied_reason:reason};
 settle(receipt);await saving;await tick();assert.equal(sent.length,1);assert.equal(controller.snapshot().phase,'idle');assert.equal(controller.snapshot().recipe.amount,.2);assert.match(controller.snapshot().message,/效果尚未应用/);
});
