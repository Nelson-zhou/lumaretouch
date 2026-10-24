// AUTHORED / UNRUN. No test runner, product imports or typecheck executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validatePresetReply,createPresetWorkflow,type PresetReply} from '../presets/presetWorkflow';
import {eyeBagFixture} from './presetFixture';
import {EYE_BAG_PRESET_OP,eyeBagPresetAck,validEyeBagPreset,sameEyeBagPresetAck} from './presetModel';
function preflight(){const proof=eyeBagFixture(),ops=[EYE_BAG_PRESET_OP,'lnx.hsl.v1'];
 const result:PresetReply={protocol:1,request_id:'review',action:'preflight',success:true,outcome_unknown:false,id:'preset',document_id:proof.load_id,
  revision:proof.visual.revision,preflight_token:'f'.repeat(32),module_scope:ops,applies:{[EYE_BAG_PRESET_OP]:{recipe:{version:2,amount:.5,preserve:1}},'lnx.hsl.v1':{}},
  source_proof:proof.owner.source_proof,eye_bag_preset:proof,eye_bag_replace_legacy:false};
 return {result,ops,opts:{id:result.id,documentId:proof.load_id,eyeBagReplaceLegacy:false}};}
test('separate eye coverage and explicit replacement bind the complete preflight',()=>{
 const {result,ops,opts}=preflight();assert.doesNotThrow(()=>validatePresetReply(result,'preflight',opts,'review',ops));
 for(const patch of [{eye_bag_preset:undefined},{eye_bag_replace_legacy:true},{eye_bag_preset:{...result.eye_bag_preset!,replace_legacy:true}}])
  assert.throws(()=>validatePresetReply({...result,...patch},'preflight',opts,'review',ops));
});
test('donor support, unknown eyes and foreign face fail exact coverage grammar',()=>{
 for(const mutate of [(v:any)=>{v.coverage.support_transfer='copy';},(v:any)=>{v.coverage.targets[0].sides=['invented'];},(v:any)=>{v.coverage.targets[0].face_ref={...v.face_ref,analysis_revision:999};},(v:any)=>{v.coverage.targets[0].source_mask=[];},(v:any)=>{v.replace_legacy=undefined;}]){
  const v=structuredClone(eyeBagFixture());mutate(v);assert.equal(validEyeBagPreset(v,v.load_id,v.visual.revision,v.owner.source_proof,false),false);
 }
});
test('neutral target makes no invented active support claim',()=>{
 const v=eyeBagFixture();v.coverage.targets[0]={face_ref:v.face_ref,scope:'neutral-no-effect',ridge_sha256:null,sides:[]};
 assert.ok(validEyeBagPreset(v,v.load_id,v.visual.revision,v.owner.source_proof,false));v.coverage.targets[0].sides=['left'];
 assert.equal(validEyeBagPreset(v,v.load_id,v.visual.revision,v.owner.source_proof,false),false);
});
test('direct active preset apply without exact frozen image review never dispatches',async()=>{
 let calls=0;const flow=createPresetWorkflow({request:async()=>{calls++;return {requested:true};},read:async id=>({phase:'pending',request_id:id})},()=>{});
 flow.updateContext({enabled:true,editable:true,documentId:'current-load-session'});await flow.submit('apply',{id:'preset'},[EYE_BAG_PRESET_OP]);assert.equal(calls,0);
});
test('uncertain writes retain exact original token and replacement ACK',()=>{
 const {result,ops,opts}=preflight(),ack=eyeBagPresetAck(result.eye_bag_preset!);
 const request={id:opts.id,documentId:opts.documentId,preflightToken:result.preflight_token,eyeBagPresetAck:ack};
 const reply:PresetReply={protocol:1,request_id:'write',action:'apply',id:result.id,document_id:opts.documentId,success:false,outcome_unknown:true,
  module_scope:ops,preflight_token:result.preflight_token,eye_bag_preset_ack:ack,error:'query only'};
 assert.doesNotThrow(()=>validatePresetReply(reply,'apply',request,'write',ops));
 for(const patch of [{eye_bag_preset_ack:undefined},{eye_bag_preset_ack:{...ack,replace_legacy:true}},{preflight_token:'wrong'},{module_scope:[EYE_BAG_PRESET_OP]}])
  assert.throws(()=>validatePresetReply({...reply,...patch},'apply',request,'write',ops));
 assert.equal(sameEyeBagPresetAck([ack],ack),false);
});
test('image namespace, content verification and query-only uncertainty are connected',()=>{
 const read=(p:string)=>readFileSync(new URL(p,import.meta.url),'utf8');
 assert.ok(read('../native.ts').includes("action:'eye_bag_visual'"));
 assert.ok(read('./presetTransport.ts').includes('await verifyCollarboneImage(r.image)'));
 assert.ok(read('./EyeBagPresetReview.tsx').includes('await verifyEyeBagCoverage(value)'));
 assert.ok(read('../presets/presetWorkflow.ts').includes('pending?.options.eyeBagPresetAck!==undefined'));
 assert.ok(read('../presets/PresetPanel.tsx').includes('!w.eyeBagReady'));
});

test('generic zero reset requires no eye support, replacement choice or visual ACK',()=>{
 const {result,opts,ops}=preflight();const neutral={...result,eye_bag_preset:undefined,eye_bag_replace_legacy:undefined,
  applies:{...result.applies,[EYE_BAG_PRESET_OP]:{recipe:{version:2,amount:0,preserve:1}}}};
 assert.doesNotThrow(()=>validatePresetReply(neutral,'preflight',{id:opts.id,documentId:opts.documentId,eyeBagNeutral:true},'review',ops));
 const active={...neutral,applies:result.applies};
 assert.throws(()=>validatePresetReply(active,'preflight',{id:opts.id,documentId:opts.documentId,eyeBagNeutral:true},'review',ops));
});

test('replacement policy round trips discard the old review while pending writes stay fenced',()=>{
 const hook=readFileSync(new URL('../presets/usePresetWorkflow.ts',import.meta.url),'utf8');
 const start=hook.indexOf('function changeEyeBagReplaceLegacy('),end=hook.indexOf('async function refresh()',start),body=hook.slice(start,end);
 assert.ok(body.includes('if(locked()||value===latest.current.eyeBagReplaceLegacy)return;'));
 assert.ok(body.includes("current()?.dismissReview();setEyeBagImage({key:'',ready:false});"));
 assert.ok(body.indexOf('dismissReview()')<body.indexOf('setEyeBagReplaceLegacy(value)'));
 assert.ok(hook.includes('setEyeBagReplaceLegacy:changeEyeBagReplaceLegacy'));
});

test('neutral direct apply omits module scope and eye wire fields while retaining local receipt scope',()=>{
 const hook=readFileSync(new URL('../presets/usePresetWorkflow.ts',import.meta.url),'utf8');
 const native=readFileSync(new URL('../native.ts',import.meta.url),'utf8');
 assert.ok(hook.includes("...(action==='preflight'?(ops.includes(HEAD_TRANSFER_OP)?{moduleScope:[HEAD_TRANSFER_OP]}"));
 assert.ok(hook.includes('eyeBagActive?{eyeBagReplaceLegacy:value.eyeBagReplaceLegacy as boolean}:eyeBagNeutral?{eyeBagNeutral:true}:{}'));
 assert.ok(hook.includes('},ops);'));
 const start=native.indexOf('export const runPreset ='),end=native.indexOf('export const requestEyeBagPresetImage=',start),transport=native.slice(start,end);
 assert.ok(!transport.includes('eyeBagNeutral'));
 assert.ok(transport.includes('eyeBagReplaceLegacy:opts.eyeBagReplaceLegacy'));
 assert.ok(transport.includes('eyeBagPresetAck:opts.eyeBagPresetAck'));
});
