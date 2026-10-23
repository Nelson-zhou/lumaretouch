import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createPresetWorkflow,validatePresetReply,type PresetTransport,type PresetOptions,type PresetReply} from './presetWorkflow.ts';
import {XMP_MODE,type XmpReport,type XmpSummary,type XmpTransfer} from '../xmpImport/model.ts';
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

// XMP additions: AUTHORED / UNRUN. These test protocol ownership, not real photo rendering.
const xmpOp='lnx.exposure.v1',xmpModules={[xmpOp]:{ev:1.25}};
const xmpReport=():XmpReport=>({version:1,source_sha256:'a'.repeat(64),report_sha256:'b'.repeat(64),filename:'sample.xmp',byte_length:512,
  process_version:'11.0',camera_raw_version:'15.0',can_import:true,properties:[],warnings:['Not Adobe rendering'],
  adaptations:[{id:'exposure',title:'Native EV',module:xmpOp,reason:'Explicit parameter adaptation'}]});
const xmpSummary=():XmpSummary=>({version:1,source_sha256:'a'.repeat(64),filename:'sample.xmp',selected:['exposure'],report:xmpReport(),read_only_summary:true});
const xmpTransfer=():XmpTransfer=>({version:1,document_id:'doc-1',revision:'7',xmp_sha256:'a'.repeat(64),
  source_proof:{asset_sha256:'c'.repeat(64),original_sha256:'c'.repeat(64),creative_source:null},
  before_sha256:'d'.repeat(64),candidate_sha256:'e'.repeat(64),before_people_sha256:'f'.repeat(64),candidate_people_sha256:'f'.repeat(64),
  source_size:[100,100],before_output_size:[100,100],after_output_size:[100,100],
  before:{mime:'image/png',width:1,height:1,sha256:'1'.repeat(64),base64:'iVBORw=='},
  after:{mime:'image/png',width:1,height:1,sha256:'2'.repeat(64),base64:'iVBORw=='}});
const xmpPreflight=(id:string):PresetReply=>({protocol:1,request_id:id,action:'preflight',success:true,outcome_unknown:false,
  document_id:'doc-1',id:'xmp-p',revision:'7',preflight_token:'0'.repeat(32),module_scope:[xmpOp],applies:xmpModules,
  xmp_report:xmpReport(),xmp_transfer:xmpTransfer()});
test('XMP inspection works without a photo and does not automatically import anything',async()=>{
  const {flow,calls,api}=fixture();flow.updateContext({...context,editable:false,documentId:''});
  api.read=async id=>({phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'xmp_inspect',success:true,outcome_unknown:false,
    path:'/sample.xmp',xmp_report:xmpReport()}});
  await flow.submit('xmp_inspect',{path:'/sample.xmp'});assert.equal(flow.snapshot().phase,'done');
  assert.equal(calls.length,1);assert.equal(calls[0].action,'xmp_inspect');assert.equal(calls[0].options.documentId,undefined);
});
test('XMP clean parser refusal is a known error and not an indefinite mutation lock',async()=>{
  const {flow,calls,api}=fixture();api.read=async id=>({phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'xmp_inspect',success:false,outcome_unknown:false,error:'Requires patched Expat 2.7.2'}});
  await flow.submit('xmp_inspect',{path:'/sample.xmp'});assert.equal(flow.snapshot().phase,'error');
  await flow.submit('xmp_inspect',{path:'/other.xmp'});assert.equal(calls.length,2);
});
test('XMP inspection transport uncertainty queries the same receipt and never imports or resubmits',async()=>{
  const {flow,calls,api}=fixture({},15);api.read=async id=>({phase:'pending',request_id:id});
  await flow.submit('xmp_inspect',{path:'/sample.xmp'});assert.equal(flow.snapshot().phase,'uncertain');
  await flow.submit('xmp_inspect',{path:'/sample.xmp'});assert.equal(calls.length,1);
  api.read=async id=>({phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'xmp_inspect',success:true,outcome_unknown:false,path:'/sample.xmp',xmp_report:xmpReport()}});
  await flow.query();assert.equal(flow.snapshot().phase,'done');assert.equal(calls.length,1);
});
test('inspection path mismatch cannot open a compatibility dialog as successful evidence',async()=>{
  const {flow,api}=fixture();api.read=async id=>({phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'xmp_inspect',success:true,outcome_unknown:false,path:'/other.xmp',xmp_report:xmpReport()}});
  await flow.submit('xmp_inspect',{path:'/sample.xmp'});assert.equal(flow.snapshot().phase,'uncertain');
});
test('XMP preflight requires the selected preset source and full matching target evidence',async()=>{
  for(const change of [false,true]){const {flow,api}=fixture();api.read=async id=>{
    const result=xmpPreflight(id);if(change)result.xmp_transfer!.document_id='other';return {phase:'done',request_id:id,result};};
    await flow.submit('preflight',{id:'xmp-p',xmpExpected:xmpSummary()},[xmpOp]);assert.equal(flow.snapshot().phase,change?'uncertain':'done');}
});
test('a document edit during XMP rendering invalidates even a completed preflight receipt',async()=>{
  const waiting=deferred<Awaited<ReturnType<PresetTransport['read']>>>();const {flow,api}=fixture();api.read=()=>waiting.promise;
  const work=flow.submit('preflight',{id:'xmp-p',xmpExpected:xmpSummary()},[xmpOp]);await tick();
  flow.updateContext({...context,reviewContextKey:'new-revision'});waiting.resolve({phase:'done',request_id:'r1',result:xmpPreflight('r1')});
  await work;assert.equal(flow.snapshot().phase,'error');assert.equal(flow.snapshot().result,null);
});
test('XMP apply cannot enqueue without a frozen review acknowledgment matching both source hashes',async()=>{
  const {flow,calls}=fixture();await flow.submit('apply',{id:'xmp-p',xmpExpected:xmpSummary()},[xmpOp]);assert.equal(calls.length,0);
  await flow.submit('apply',{id:'xmp-p',xmpExpected:xmpSummary(),preflightToken:'0'.repeat(32),xmpReviewAck:{source_sha256:'c'.repeat(64),report_sha256:'b'.repeat(64),before_sha256:'1'.repeat(64),after_sha256:'2'.repeat(64)}},[xmpOp]);
  assert.equal(calls.length,0);assert.equal(flow.snapshot().phase,'error');
});
test('XMP import receipts must preserve the explicit selection and omit original XML bytes',async()=>{
  for(const mismatch of [false,true]){const {flow,api}=fixture();api.read=async id=>{
    const source=xmpSummary();if(mismatch)source.source_sha256='c'.repeat(64);
    return {phase:'done',request_id:id,result:{protocol:1,request_id:id,action:'import',success:true,outcome_unknown:false,id:'xmp-p',path:'/saved.json',module_scope:[xmpOp],
      preset:{schema:'lrt.preset.v1',id:'xmp-p',name:'XMP',kind:'color',builtin:false,modules:xmpModules,xmp_import:source}}};};
    await flow.submit('import',{path:'/sample.xmp',xmpAck:{mode:XMP_MODE,source_sha256:'a'.repeat(64),report_sha256:'b'.repeat(64),selected:['exposure']}});
    assert.equal(flow.snapshot().phase,mismatch?'uncertain':'done');}
});

// AUTHORED / UNRUN: scalar spill transfer must retain actual target ownership.
test('spill preflight rejects missing or inconsistent effective source proof',()=>{
  const op='lnx.spill_removal.v1',opts={id:'spill',documentId:'doc-1'};
  const reply:PresetReply={protocol:1,request_id:'spill-review',action:'preflight',success:true,
    outcome_unknown:false,document_id:'doc-1',id:'spill',module_scope:[op],revision:'4',
    preflight_token:'1'.repeat(32),applies:{[op]:{enabled:true,strength:40}},
    source_proof:{asset_sha256:'a'.repeat(64),original_sha256:'a'.repeat(64),creative_source:null}};
  assert.doesNotThrow(()=>validatePresetReply(reply,'preflight',opts,'spill-review',[op]));
  assert.throws(()=>validatePresetReply({...reply,source_proof:undefined},'preflight',opts,'spill-review',[op]));
  assert.throws(()=>validatePresetReply({...reply,source_proof:{asset_sha256:'b'.repeat(64),
    original_sha256:'a'.repeat(64),creative_source:null}},'preflight',opts,'spill-review',[op]));
  assert.doesNotThrow(()=>validatePresetReply({...reply,source_proof:{asset_sha256:'b'.repeat(64),
    original_sha256:'a'.repeat(64),creative_source:{sha256:'b'.repeat(64),width:12,height:8}}},
    'preflight',opts,'spill-review',[op]));
});
