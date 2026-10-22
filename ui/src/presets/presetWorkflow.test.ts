import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPresetWorkflow,type PresetTransport,type PresetOptions,type PresetReply} from './presetWorkflow.ts';
const op='lnx.hsl.v1',modules={[op]:{recipe:{version:1}}};
const context={enabled:true,editable:true,documentId:'doc-1'};
const tick=()=>new Promise<void>(r=>setImmediate(r));
const deferred=<T>()=>{let resolve!:(v:T)=>void;const promise=new Promise<T>(r=>resolve=r);return {promise,resolve};};
function fixture(patch:Partial<PresetTransport>={},timeoutMs=5000){
  let n=0,time=0;const calls:Array<{action:string;options:PresetOptions}>=[],replies=new Map<string,PresetReply>();
  const api:PresetTransport={request:async(action,options)=>{
    calls.push({action,options});const id=options.requestId!;
    replies.set(id,{protocol:1,request_id:id,action,success:true,outcome_unknown:false,document_id:options.documentId,
      id:options.id??'imported',name:options.name??'示例',path:'/presets/p.json',module_scope:[op],before:modules,after:modules,
      doc_state:{document_id:options.documentId},preset:{schema:'lrt.preset.v1',id:options.id??'imported',name:options.name??'示例',kind:'custom',builtin:false,modules},
      catalog:{available:true,list:[],errors:[],modules:[],dir:'/presets',schema:'lrt.preset.v1'}});
    return {requested:true};},read:async id=>({phase:'done',request_id:id,result:replies.get(id)}),...patch};
  const flow=createPresetWorkflow(api,()=>{},{uuid:()=>`r${++n}`,now:()=>time,pause:async()=>{time+=10;await tick();},timeoutMs});
  flow.updateContext(context);return {flow,calls,api,replies};
}
const save={id:'p',name:'婚纱',moduleScope:[op]};
test('save captures explicit scope and photo identity and waits for terminal result',async()=>{
  const {flow,calls,api}=fixture();const read=api.read,wait=deferred<Awaited<ReturnType<PresetTransport['read']>>>();api.read=()=>wait.promise;
  const work=flow.submit('save',save);await tick();assert.equal(flow.snapshot().phase,'working');
  assert.deepEqual(calls[0].options,{...save,documentId:'doc-1',requestId:'r1'});
  wait.resolve(await read('r1'));await work;assert.equal(flow.snapshot().phase,'done');
});
test('double clicks cannot enqueue twice; document switching does not discard receipt ownership',async()=>{
  const {flow,calls,api}=fixture();const read=api.read,wait=deferred<Awaited<ReturnType<PresetTransport['read']>>>();api.read=()=>wait.promise;
  const work=flow.submit('apply',{id:'p'},[op]);await tick();await flow.submit('apply',{id:'p'},[op]);
  flow.updateContext({...context,documentId:'doc-2'});assert.equal(calls.length,1);
  wait.resolve(await read('r1'));await work;assert.equal(flow.snapshot().phase,'done');
  assert.equal(flow.snapshot().submitted?.options.documentId,'doc-1');
});
test('timeout queries the same ID and never resubmits even when starting a new action',async()=>{
  const {flow,calls,api}=fixture({},15);const read=api.read;api.read=async id=>({phase:'pending',request_id:id});
  await flow.submit('save',save);assert.equal(flow.snapshot().phase,'uncertain');await flow.submit('delete',{id:'p'});
  api.read=read;await flow.query();assert.equal(calls.length,1);assert.equal(flow.snapshot().phase,'done');
});
test('transport rejection is uncertain; unavailable receipt never causes an automatic retry',async()=>{
  const {flow,calls,api}=fixture();api.request=async(action,options)=>{calls.push({action,options});throw Error('connection lost');};
  await flow.submit('save',save);assert.equal(flow.snapshot().phase,'uncertain');
  api.read=async id=>({phase:'unavailable',request_id:id});await flow.query();await flow.submit('save',save);
  assert.equal(calls.length,1);assert.equal(flow.snapshot().phase,'uncertain');
  flow.acknowledgeInspection();assert.equal(flow.snapshot().phase,'idle');assert.equal(calls.length,1);
});
test('wrong document, request, preset, scope or incomplete evidence cannot report success',async()=>{
  const patches:Array<Partial<PresetReply>>=[{document_id:'other'},{request_id:'other'},{id:'other'},
    {module_scope:[op,op]},{module_scope:['unexpected']},{preset:{id:'p'} as PresetReply['preset']},
    {success:true,outcome_unknown:true}];
  for(const patch of patches){const {flow,api}=fixture();const read=api.read;api.read=async id=>{const r=await read(id);return {...r,result:{...r.result!,...patch}};};
    await flow.submit('save',save);assert.equal(flow.snapshot().phase,'uncertain');}
});
test('apply requires before and after scope evidence; receipt state is never installed into a changed context',async()=>{
  const {flow,api}=fixture();const read=api.read;api.read=async id=>{const r=await read(id);return {...r,result:{...r.result!,before:{}}};};
  await flow.submit('apply',{id:'p'},[op]);assert.equal(flow.snapshot().phase,'uncertain');
});
test('engine rejection is a definite error; failed rollback remains uncertain',async()=>{
  for(const unknown of [false,true]){const {flow,api}=fixture();api.read=async id=>({phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'save',document_id:'doc-1',success:false,outcome_unknown:unknown,error:'failed'}});
    await flow.submit('save',save);assert.equal(flow.snapshot().phase,unknown?'uncertain':'error');}
});
test('catalog, import and delete work without a photo; editing still requires one',async()=>{
  const {flow,calls}=fixture();flow.updateContext({...context,editable:false,documentId:''});
  await flow.submit('save',save);assert.equal(calls.length,0);
  for(const action of ['list','import','delete'] as const){await flow.submit(action,action==='delete'?{id:'p'}:{});assert.equal(flow.snapshot().phase,'done');}
  assert.equal(calls.length,3);assert.ok(calls.every(c=>c.options.documentId===undefined));
});
test('readonly listing failure can be refreshed without manual mutation recovery',async()=>{
  const {flow,api}=fixture();const read=api.read;api.read=async()=>{throw Error('lost');};
  await flow.submit('list');assert.equal(flow.snapshot().phase,'error');api.read=read;await flow.submit('list');assert.equal(flow.snapshot().phase,'done');
});
test('save refuses empty implicit scopes and preserves copied request scope',async()=>{
  const {flow,calls,api}=fixture();await flow.submit('save',{id:'p',name:'name'});assert.equal(calls.length,0);
  const accepted=deferred<{requested:boolean}>(),original=api.request;api.request=async(a,o)=>{await original(a,o);return accepted.promise;};
  const input={...save,moduleScope:[op]},work=flow.submit('save',input);input.moduleScope.push('extra');
  accepted.resolve({requested:true});await work;assert.deepEqual(calls[0].options.moduleScope,[op]);
});
test('disposed workflow ignores late receipts and does not notify or restart',async()=>{
  const wait=deferred<{requested:boolean}>();const {flow,calls}=fixture({request:()=>wait.promise});
  const work=flow.submit('save',save);flow.dispose();wait.resolve({requested:true});await work;assert.equal(calls.length,0);
  assert.notEqual(flow.snapshot().phase,'done');
});
test('save rejects overlong names before mutation and accepts 80 Unicode code points',async()=>{
  const {flow,calls}=fixture();await flow.submit('save',{...save,name:'名'.repeat(81)});assert.equal(calls.length,0);
  await flow.submit('save',{...save,name:'😀'.repeat(80)});assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,1);
});
