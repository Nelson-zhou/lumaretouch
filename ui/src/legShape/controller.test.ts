// SPDX-License-Identifier: GPL-3.0-or-later
// Authored UNRUN. Synthetic transport-state fixtures, not native/pixel evidence.
import {describe,it} from 'node:test';
import assert from 'node:assert/strict';
import {LegController} from './controller.ts';
import {neutral,adjust,type LegView,type LegRecipe,type Request,type Result} from './model.ts';
function view(id='a',revision=0):LegView{return {binding:{document_id:'doc',document_epoch:'epoch',document_revision:revision,asset_sha256:id.repeat(64)},state_revision:revision,association_revision:0,people_association_revision:0,body_graph_sha256:'b'.repeat(64),people_graph_sha256:'c'.repeat(64),bodies:[],selected_body_ref:{asset_sha256:id.repeat(64),body_instance_id:`body:${id}`,analysis_revision:0},recipe:neutral(),refusals:[]};}
function pending<T>(){let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
describe('leg controller fences',()=>{
 it('sends one inflight and only latest unsent pair intent',async()=>{const first=pending<Result>();const sent:Request[]=[];const c=new LegController({send:r=>{sent.push(r);if(sent.length===1)return first.promise;const applied=view('a',sent.length);applied.recipe=r.payload.recipe as LegRecipe;return Promise.resolve({phase:'done',request_id:r.request_id,success:true,outcome_unknown:false,view:applied});},status:async id=>({phase:'unavailable',request_id:id})});c.update(view());c.edit(r=>adjust(r,'overall',.2),'g');c.edit(r=>adjust(r,'thigh',.4),'g');c.edit(r=>adjust(r,'calf',-.1),'g');assert.equal(sent.length,1);const next=view('a',1);next.recipe={version:1,thigh:.2,calf:.2};first.resolve({phase:'done',request_id:sent[0].request_id,success:true,outcome_unknown:false,view:next});await Promise.resolve();await Promise.resolve();assert.deepEqual(c.snapshot().recipe,{version:1,thigh:.4,calf:-.1});});
 it('photo switch cancels queued intent and does not apply old result to new target',async()=>{const first=pending<Result>();const sent:Request[]=[];const c=new LegController({send:r=>{sent.push(r);return first.promise;},status:async id=>({phase:'unavailable',request_id:id})});c.update(view());c.edit(r=>adjust(r,'thigh',.4),'g');c.edit(r=>adjust(r,'calf',.3),'g');c.update(view('d'));first.resolve({phase:'done',request_id:sent[0].request_id,success:true,outcome_unknown:false,view:view('a',1)});await Promise.resolve();await Promise.resolve();assert.equal(sent.length,1);assert.equal(c.snapshot().view?.binding.asset_sha256,'d'.repeat(64));assert.deepEqual(c.snapshot().recipe,neutral());});
 it('uncertain mutation is queried, never automatically resent',async()=>{let sends=0,queries=0;const c=new LegController({send:async()=>{sends++;throw Error('lost reply');},status:async id=>{queries++;return {phase:'pending',request_id:id,outcome_unknown:true};}});c.update(view());c.edit(r=>adjust(r,'calf',.3),'g');await Promise.resolve();await Promise.resolve();await Promise.resolve();await c.reconcile();assert.equal(sends,1);assert.equal(queries,1);assert.equal(c.snapshot().phase,'uncertain');});
});

it('clearing the document drops queued intent but retains uncertain receipt',async()=>{
 const deferred=pending<Result>();let sends=0;
 const c=new LegController({send:()=>{sends++;return deferred.promise;},status:async id=>({phase:'unavailable',request_id:id})});
 c.update(view());c.edit(r=>adjust(r,'overall',.2),'g');c.edit(r=>adjust(r,'calf',.4),'g');c.clear();
 assert.equal(c.snapshot().view,null);
 deferred.resolve({phase:'done',request_id:'wrong',success:true,outcome_unknown:false,view:view()});
 await Promise.resolve();await Promise.resolve();await Promise.resolve();
 assert.equal(sends,1);assert.equal(c.snapshot().phase,'uncertain');
});

it('concurrent reconciliation shares one query and a completed result stays idle',async()=>{
 const response=pending<Result>();let original:Request|undefined,queries=0;
 const c=new LegController({send:async request=>{original=request;throw Error('lost reply');},status:()=>{queries++;return response.promise;}});
 c.update(view());c.edit(r=>adjust(r,'thigh',.4),'g');
 await Promise.resolve();await Promise.resolve();await Promise.resolve();
 const first=c.reconcile(),second=c.reconcile();assert.equal(first,second);assert.equal(queries,1);
 assert.ok(original);const applied=view('a',1);applied.recipe={version:1,thigh:.4,calf:0};
 response.resolve({phase:'done',request_id:original.request_id,success:true,outcome_unknown:false,view:applied});
 await Promise.all([first,second]);await c.reconcile();
 assert.equal(c.snapshot().phase,'idle');assert.equal(queries,1);assert.deepEqual(c.snapshot().recipe,applied.recipe);
});
