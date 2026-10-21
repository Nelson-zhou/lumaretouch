import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createInspectionController,type InspectionStatus,type InspectionAccepted,type InspectionIntent,type InspectionApi,type InspectionUiState} from './inspectionController.ts';
function deferred<T>(){let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>{resolve=r;});return {promise,resolve};}
async function until(check:()=>boolean){for(let i=0;i<100;i++){if(check())return;await new Promise(r=>setImmediate(r));}assert.fail('controller did not reach expected state');}
function fixture(){
  const hex=readFileSync(new URL('../../core/inspection/packet-v1.hex',import.meta.url),'utf8').trim();
  const bytes=Uint8Array.from(hex.match(/../g)!,x=>parseInt(x,16));
  return bytes.buffer as ArrayBuffer;
}
function harness(){
  const state:InspectionStatus={epoch:'07'.repeat(16),generation:'4',available:true,state:'ready',error:null,request_id:null,worker_id:null,published_epoch:null,published_id:null};
  const intent:InspectionIntent={key:'first',canvasWidth:10,canvasHeight:10,roi:{x:1,y:2,width:2,height:1}};
  const owner:InspectionAccepted={epoch:state.epoch,request_id:'9007199254740993',accepted:true,expectation:{epoch:state.epoch,ticket:{id:'9007199254740993',document:'2',sourceGeneration:'3',recipe:'4',viewport:'5'},canvasWidth:10,canvasHeight:10,roi:{...intent.roi},maxPayloadBytes:8}};
  const calls={start:0,pull:0,cancel:0,release:0,paint:0,reveal:0};const reports:InspectionUiState[]=[];
  const api:InspectionApi={status:async()=>({...state}),start:async()=>{calls.start++;state.request_id=owner.request_id;return owner;},pull:async()=>{calls.pull++;state.published_epoch=owner.epoch;state.published_id=owner.request_id;return fixture();},cancel:async()=>{calls.cancel++;},release:async()=>{calls.release++;state.published_epoch=null;state.published_id=null;}};
  const callbacks={clear:()=>{},paint:()=>{calls.paint++;},reveal:()=>{calls.reveal++;},state:(s:InspectionUiState)=>{reports.push(s);}};
  const cleanup={owner:null as InspectionAccepted|null,serial:0,latest:0};
  const make=()=>createInspectionController(api,callbacks,async()=>{},()=>0,cleanup);
  return {state,intent,owner,calls,reports,api,callbacks,cleanup,make};
}
test('paint is hidden until release and final identity check; identical intent does not restart',async()=>{
  const h=harness(),gate=deferred<void>();const release=h.api.release;
  h.api.release=async(...args)=>{await gate.promise;return release(...args);};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.paint===1);assert.equal(h.calls.reveal,0);
  gate.resolve();await until(()=>h.calls.reveal===1);c.update({...h.intent});await new Promise(r=>setImmediate(r));assert.equal(h.calls.start,1);c.dispose();
});
test('generation change during release prevents stale reveal',async()=>{
  const h=harness();const release=h.api.release;h.api.release=async(...args)=>{h.state.generation='5';return release(...args);};
  const c=h.make();c.update(h.intent);await until(()=>h.reports.some(s=>s.state==='error'));assert.equal(h.calls.reveal,0);assert.equal(h.calls.release,1);c.dispose();
});
test('dispose during pending pull still releases received buffer without painting',async()=>{
  const h=harness(),gate=deferred<ArrayBuffer>();h.api.pull=async()=>{h.calls.pull++;h.state.published_epoch=h.owner.epoch;h.state.published_id=h.owner.request_id;return gate.promise;};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.pull===1);c.dispose();gate.resolve(fixture());await until(()=>h.calls.release===1);assert.equal(h.calls.paint,0);assert.equal(h.calls.reveal,0);
});
test('malformed packet and paint exception both release publication',async()=>{
  for(const malformed of [true,false]){
    const h=harness();if(malformed){const pull=h.api.pull;h.api.pull=async(...args)=>(await pull(...args)).slice(0,128);}else h.callbacks.paint=()=>{throw new Error('canvas failed');};
    const c=h.make();c.update(h.intent);await until(()=>h.reports.some(s=>s.state==='error'));assert.equal(h.calls.release,1);assert.equal(h.calls.reveal,0);c.dispose();
  }
});
test('accepted canvas/ROI mismatch is rejected before pull',async()=>{
  const h=harness();h.owner.expectation.roi.x=2;const c=h.make();c.update(h.intent);await until(()=>h.calls.cancel===1);assert.equal(h.calls.pull,0);assert.equal(h.calls.cancel,1);c.dispose();
});
test('late accepted start is cancelled before latest intent is admitted',async()=>{
  const h=harness(),gate=deferred<InspectionAccepted>();const start=h.api.start;let first=true;
  h.api.start=async(...args)=>{if(first){first=false;h.calls.start++;return gate.promise;}return start(...args);};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.start===1);c.update({...h.intent,key:'latest'});gate.resolve(h.owner);await until(()=>h.calls.reveal===1);assert.ok(h.calls.cancel>=1);assert.equal(h.calls.start,2);c.dispose();
});
test('lost pull response and failed status preserve lease across remount',async()=>{
  const h=harness();const pull=h.api.pull,status=h.api.status;let failStatus=false;
  h.api.pull=async(...args)=>{await pull(...args);failStatus=true;throw new Error('lost response');};
  h.api.status=async()=>{if(failStatus)throw new Error('disconnected');return status();};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.cancel===1);assert.equal(h.cleanup.owner,h.owner);c.dispose();
  failStatus=false;h.api.pull=pull;const next=h.make();next.update({...h.intent,key:'retry'});await until(()=>h.calls.reveal===1);assert.equal(h.calls.release,2);assert.equal(h.cleanup.owner,null);next.dispose();
});
test('same generation superseding request cannot paint stale buffer',async()=>{
  const h=harness();const pull=h.api.pull;h.api.pull=async(...args)=>{const b=await pull(...args);h.state.request_id='99';return b;};
  const c=h.make();c.update(h.intent);await until(()=>h.reports.some(s=>s.state==='error'));assert.equal(h.calls.paint,0);assert.equal(h.calls.reveal,0);assert.equal(h.calls.release,1);c.dispose();
});
test('uncertain release proven absent is not repeated',async()=>{
  const h=harness();const release=h.api.release;h.api.release=async(...args)=>{await release(...args);throw new Error('lost release reply');};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.reveal===1);assert.equal(h.calls.release,1);c.dispose();
});
test('retained failed release is reconciled before another request',async()=>{
  const h=harness();const release=h.api.release;let fail=true;
  h.api.release=async(...args)=>{if(fail)throw new Error('release unavailable');return release(...args);};
  const c=h.make();c.update(h.intent);await until(()=>h.calls.cancel===1);assert.equal(h.cleanup.owner,h.owner);
  fail=false;c.update({...h.intent,key:'retry'});await until(()=>h.calls.reveal===1);assert.equal(h.calls.release,2);assert.equal(h.cleanup.owner,null);c.dispose();
});
