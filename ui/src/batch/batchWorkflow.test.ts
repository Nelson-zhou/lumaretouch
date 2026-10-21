import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createBatchWorkflow,type BatchTransport,type BatchOptions,type BatchAction,type BatchContext,type BatchReply} from './batchWorkflow.ts';
const token='a'.repeat(32),source={document_id:'b'.repeat(32),revision:'4',path:'/source.raw'};
const target={index:1,path:'/target.raw',document_id:'c'.repeat(32),revision:'2',blocked:null};
const context:BatchContext={docs:['/target.raw'],moduleScope:['ev'],conflictPolicy:'skip_and_report',sourceDocumentId:'loaded-1',enabled:true,label:'曝光'};
const tick=()=>new Promise<void>(r=>setImmediate(r));
const deferred=<T>()=>{let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>resolve=r);return {promise,resolve};};
function fixture(patch:Partial<BatchTransport>={},timeoutMs=50){
  let n=0,time=0;const calls:Array<{action:BatchAction;opts:BatchOptions}>=[],replies=new Map<string,BatchReply>();
  const api:BatchTransport={request:async(action,opts)=>{
    calls.push({action,opts});const id=opts.requestId!;
    const common={request_id:id,action,success:true};
    replies.set(id,action==='preflight'?{...common,preflight_token:token,source_snapshot:source,module_scope:['ev'],applies:{ev:{ev:1}},
      policy:opts.conflictPolicy,targets:[target],rejected_docs:[],ok:1,blocked:0}:action==='commit'?{...common,preflight_token:token,source_snapshot:source,
      target_outcomes:[{...target,expected_revision:'2',current_revision:'2',result_revision:'3',outcome:'applied'}]}:{...common,restored:[1],conflicts:[]});
    return {requested:true};},
    read:async id=>({phase:'done',request_id:id,result:replies.get(id)}),...patch};
  const flow=createBatchWorkflow(api,()=>{}, {uuid:()=>`request-${++n}`,now:()=>time,pause:async()=>{time+=10;await tick();},timeoutMs});
  flow.updateContext(context);return {flow,calls,replies,api};
}
test('preflight does not auto-commit and confirmation sends only the frozen token',async()=>{
  const {flow,calls}=fixture();await flow.start();assert.equal(flow.snapshot().phase,'review');assert.equal(calls.length,1);
  await flow.commit();assert.equal(flow.snapshot().phase,'done');assert.deepEqual(calls[1],{action:'commit',opts:{preflightToken:token,requestId:'request-2'}});
});
test('selection, scope, policy or document changes invalidate review before commit',async()=>{
  for(const patch of [{docs:['/other']},{moduleScope:['wb']},{conflictPolicy:'recheck'},{sourceDocumentId:'loaded-2'},{enabled:false}]){
    const {flow,calls}=fixture();await flow.start();flow.updateContext({...context,...patch});await flow.commit();
    assert.equal(flow.snapshot().phase,'closed');assert.equal(calls.length,1);
  }
});
test('dismissed late preflight cannot revive the dialog',async()=>{
  const wait=deferred<{requested:boolean}>();const {flow}=fixture({request:()=>wait.promise});
  const started=flow.start();flow.close();wait.resolve({requested:true});await started;assert.equal(flow.snapshot().phase,'closed');
});
test('double confirmation cannot enqueue twice and completion survives context changes',async()=>{
  const {flow,calls,api}=fixture();await flow.start();const oldRead=api.read,wait=deferred<Awaited<ReturnType<BatchTransport['read']>>>();
  api.read=()=>wait.promise;const commit=flow.commit();await tick();await flow.commit();flow.updateContext({...context,docs:['/new']});
  assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'committing');
  wait.resolve(await oldRead('request-2'));await commit;assert.equal(flow.snapshot().phase,'done');
});
test('timeout remains unknown and query reuses the same request without resubmitting',async()=>{
  const {flow,calls,api}=fixture({},15);await flow.start();const oldRead=api.read;
  api.read=async id=>({phase:'pending',request_id:id});await flow.commit();assert.equal(flow.snapshot().phase,'uncertain');
  await flow.start();assert.equal(calls.length,2);api.read=oldRead;await flow.query();
  assert.equal(calls.length,2);assert.equal(flow.snapshot().phase,'done');
});
test('wrong request or token can never report success',async()=>{
  for(const bad of ['request','token']){
    const {flow,api}=fixture();await flow.start();const old=api.read;
    api.read=async id=>{const r=await old(id);return bad==='request'?{...r,request_id:'wrong'}:{...r,result:{...r.result!,preflight_token:'d'.repeat(32)}};};
    await flow.commit();assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().result,null);
  }
});
test('incomplete preflight and mismatched target results fail closed',async()=>{
  const {flow,api}=fixture();const original=api.read;
  api.read=async id=>{const r=await original(id);return {...r,result:{...r.result!,ok:99}};};
  await flow.start();assert.equal(flow.snapshot().phase,'error');await flow.commit();
  api.read=original;await flow.start();api.read=async id=>{const r=await original(id);return {...r,result:{...r.result!,target_outcomes:[]}};};
  await flow.commit();assert.equal(flow.snapshot().phase,'uncertain');
});
test('engine rejection and unknown terminal outcome are not labelled completed',async()=>{
  const {flow,api}=fixture();await flow.start();api.read=async id=>({phase:'done',request_id:id,
    result:{request_id:id,action:'commit',success:false,outcome_unknown:true,error:'publication failed'}});
  await flow.commit();assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().result?.outcome_unknown,true);
  flow.close();assert.equal(flow.snapshot().hidden,true);await flow.start();assert.equal(flow.snapshot().hidden,false);
  flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'closed');
});
test('batch undo waits for its correlated terminal receipt',async()=>{
  const {flow,calls}=fixture();await flow.undo('batch-1');assert.equal(flow.snapshot().phase,'done');
  assert.deepEqual(calls[0],{action:'undo',opts:{batchId:'batch-1',requestId:'request-1'}});
  assert.deepEqual(flow.snapshot().result?.restored,[1]);
});


test('closing a timeout retains the original request and resumes rather than resubmits',async()=>{
  const {flow,calls,api}=fixture({},15);await flow.start();const old=api.read;
  api.read=async id=>({phase:'pending',request_id:id});await flow.commit();flow.close();
  assert.equal(flow.snapshot().phase,'uncertain');assert.equal(flow.snapshot().hidden,true);
  await flow.start();assert.equal(calls.length,2);assert.equal(flow.snapshot().hidden,false);
  api.read=old;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
});
test('stalled request and read promises have bounded waits without losing ownership',async()=>{
  for(const stage of ['request','read']){
    const {flow,api,calls}=fixture({},5);await flow.start();const oldRequest=api.request,oldRead=api.read;
    if(stage==='request')api.request=async(a,o)=>{await oldRequest(a,o);return new Promise(()=>{});};
    else api.read=()=>new Promise(()=>{});
    await flow.commit();assert.equal(flow.snapshot().phase,'uncertain');assert.equal(calls.length,2);
    api.read=oldRead;await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,2);
  }
});
test('canonical key ordering in terminal receipts does not change source identity',async()=>{
  const {flow,api}=fixture();await flow.start();const old=api.read;
  api.read=async id=>{const r=await old(id);return {...r,result:{...r.result!,source_snapshot:{path:source.path,revision:source.revision,document_id:source.document_id}}};};
  await flow.commit();assert.equal(flow.snapshot().phase,'done');
});

test('review controls are reachable and availability checks remain pure',async()=>{
  const {readFileSync}=await import('node:fs');
  const app=readFileSync(new URL('../App.tsx',import.meta.url),'utf8');
  const enabled=app.slice(app.indexOf('function p0enabled('),app.indexOf('function p0slider('));
  const action=app.slice(app.indexOf('async function p0action('),app.indexOf('// ── 预设与批量同步'));
  assert.match(app,/<BatchActions[\s\S]*?onReview=\{onBatchSync\}/);assert.doesNotMatch(enabled,/await onBatchSync/);
  assert.match(action,/lnx\.batch\.v1\.preflight[\s\S]*?await onBatchSync/);
  assert.equal((app.match(/document\.querySelector\('\.batchReviewBackdrop'\)/g)??[]).length,3);
  const dialog=readFileSync(new URL('./BatchReview.tsx',import.meta.url),'utf8');
  assert.match(dialog,/if\(!open\)return state\.phase==='uncertain'\?<button/);
});
