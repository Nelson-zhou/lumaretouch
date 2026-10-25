// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. Structural placeholders are not real donor/output image evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {ExpressionController,previewKey,sourceDisplayKey} from './controller.ts';
import {CONFIRMATION_KEYS,OPERATION_ID,type DonorCommand,type ExpressionPort,type Packet,type PreviewCommand} from './model.ts';
import {command,current,photograph,ready} from './fixtures.unrun.ts';
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done;});return {promise,resolve};}
const envelope=(sent:Packet)=>({version:1,operation_id:OPERATION_ID,request_id:sent.command.request_id,command_sha256:sent.command_sha256,action:sent.command.action,binding:sent.command.binding});
const donorReady=(sent:Packet<DonorCommand>)=>({...envelope(sent),phase:'donor_ready',photo:photograph('b')});
const cancelled=(sent:Packet)=>({...envelope(sent),phase:'cancelled',no_write:true,message:'worker exited'});
async function awaitSent<T>(read:()=>T|undefined):Promise<T>{
  const deadline=Date.now()+2000;while(!read()&&Date.now()<deadline)await new Promise(resolve=>setTimeout(resolve,0));
  const sent=read();assert.ok(sent,'request was not produced');return sent;
}
function setup(overrides:Partial<ExpressionPort>={}){
  let ids=0,applications=0,cancellations=0;const released:string[]=[],requests:Packet[]=[];
  const port:ExpressionPort={protocol:1,capability:{protocol:1,operation_id:OPERATION_ID,available:true,reason:null},
    chooseDonor:async sent=>{requests.push(sent);return donorReady(sent);},
    preview:async sent=>{requests.push(sent);return ready(sent);},
    apply:async sent=>{applications++;requests.push(sent);throw Error('connection lost after send');},
    cancel:async request=>{cancellations++;const sent=requests.find(p=>p.command.request_id===request.request_id);if(!sent)throw Error('not registered');return cancelled(sent);},
    status:async()=>{throw Error('not yet available');},releasePreview:async token=>{released.push(token);},...overrides};
  const controller=new ExpressionController(port,{id:()=>`request-${++ids}`});controller.bind(current());
  return {controller,released,requests,applications:()=>applications,cancellations:()=>cancellations};
}
async function prepared(controller:ExpressionController){
  controller.selectTarget(current().photo.faces[0].face_ref);await controller.chooseDonor();controller.selectDonor(photograph('b').faces[0].face_ref);
  controller.displayed('target',sourceDisplayKey(current().photo),true);controller.displayed('donor',sourceDisplayKey(photograph('b')),true);
  controller.setFusion(command().fusion);CONFIRMATION_KEYS.forEach(key=>controller.confirm(key,true));await controller.preview();
  controller.reviewed(previewKey(controller.snapshot()),true);
}
test('lost save response fences repeat clicks, cancel and module replacement',async()=>{
  const h=setup();await prepared(h.controller);await h.controller.apply();assert.equal(h.controller.snapshot().phase,'unknown');assert.equal(h.applications(),1);
  h.controller.cancel();assert.equal(h.controller.snapshot().phase,'unknown');assert.equal(h.controller.canDetach(),false);assert.equal(h.cancellations(),0);
  assert.throws(()=>h.controller.dispose());await assert.rejects(()=>h.controller.apply());await h.controller.reconcile();assert.equal(h.applications(),1);
});
test('read-only cancellation accepts exact terminal completion only as discarded, never cancelled',async()=>{
  const d=deferred<unknown>(),cancel=deferred<unknown>();let sent:Packet<PreviewCommand>|undefined;
  const h=setup({preview:async value=>{sent=value;return d.promise;},cancel:()=>cancel.promise,status:async()=>cancelled(sent!)}),operation=prepared(h.controller);
  const actual=await awaitSent(()=>sent);h.controller.cancel();assert.equal(h.controller.snapshot().phase,'cancelling');assert.equal(h.controller.canDetach(),false);
  d.resolve(ready(actual));await operation;assert.equal(h.controller.snapshot().preview,null);assert.deepEqual(h.released,['token-1']);assert.equal(h.controller.snapshot().phase,'idle');assert.equal(h.controller.snapshot().receipt?.phase,'ready');
  cancel.resolve({...envelope(actual),phase:'cancelling',message:'awaiting worker exit'});await h.controller.reconcile();
  assert.equal(h.controller.snapshot().phase,'idle');assert.equal(h.controller.canDetach(),true);
});
test('changing source retains old pending save but removes its review authority',async()=>{
  const h=setup();await prepared(h.controller);await h.controller.apply();const request=h.controller.snapshot().request;
  const next=current();h.controller.bind({...next,binding:{...next.binding,document_epoch:'epoch-2',load_id:'load-2'}});
  assert.equal(h.controller.snapshot().request?.command.request_id,request?.command.request_id);assert.equal(h.controller.snapshot().reviewed,false);
  assert.equal(h.controller.snapshot().target_ref,null);assert.equal(h.applications(),1);
});
test('donor acquisition has a cancelable immutable request identity; late donor never publishes',async()=>{
  const d=deferred<unknown>(),cancel=deferred<unknown>();let sent:Packet<DonorCommand>|undefined;
  const h=setup({chooseDonor:value=>{sent=value;return d.promise;},cancel:()=>cancel.promise,status:async()=>cancelled(sent!)});
  const operation=h.controller.chooseDonor(),actual=await awaitSent(()=>sent);h.controller.cancel();
  d.resolve(donorReady(actual));await operation;assert.equal(h.controller.snapshot().donor,null);assert.equal(h.controller.snapshot().phase,'idle');assert.equal(h.controller.snapshot().receipt?.phase,'donor_ready');
  cancel.resolve(cancelled(actual));await h.controller.reconcile();assert.equal(h.controller.snapshot().request,null);
});
test('mask edits and source display failures revoke review and all confirmations',async()=>{
  const h=setup();await prepared(h.controller);h.controller.setFusion(command().fusion);
  assert.equal(h.controller.snapshot().preview,null);assert.deepEqual(h.controller.snapshot().confirmations,{});
  CONFIRMATION_KEYS.forEach(key=>h.controller.confirm(key,true));await h.controller.preview();h.controller.reviewed(previewKey(h.controller.snapshot()),true);
  h.controller.displayed('donor',sourceDisplayKey(photograph('b')),false);assert.equal(h.controller.snapshot().reviewed,false);await assert.rejects(()=>h.controller.apply());
});
test('missing capability fails closed without deleting historical content',()=>{
  const h=setup({capability:{protocol:1,operation_id:OPERATION_ID,available:false,reason:'native library unavailable'}});
  assert.equal(h.controller.snapshot().current?.available,false);assert.throws(()=>h.controller.selectTarget(current().photo.faces[0].face_ref));
});

test('cancellation does not settle on a mismatched, pending or unknown read receipt',async()=>{
  const d=deferred<unknown>(),cancel=deferred<unknown>();let sent:Packet<PreviewCommand>|undefined;
  let status:unknown;
  const h=setup({preview:async value=>{sent=value;return d.promise;},cancel:()=>cancel.promise,status:async()=>status}),operation=prepared(h.controller);
  const actual=await awaitSent(()=>sent);h.controller.cancel();
  status={...envelope(actual),phase:'unknown',message:'not yet observed'};await h.controller.reconcile();assert.equal(h.controller.canDetach(),false);
  status={...ready(actual),request_id:'foreign-request'};await h.controller.reconcile();assert.equal(h.controller.canDetach(),false);
  d.resolve(ready(actual));await operation;cancel.resolve(cancelled(actual));
  assert.equal(h.controller.snapshot().phase,'idle');assert.equal(h.controller.snapshot().receipt?.phase,'ready');
});
