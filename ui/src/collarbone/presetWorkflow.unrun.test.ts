// AUTHORED / UNRUN: no product imports, test runner, typecheck or build executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validatePresetReply,createPresetWorkflow,type PresetReply} from '../presets/presetWorkflow';
import {presetFixture} from './presetFixture';
import {COLLARBONE_PRESET_OP,collarbonePresetAck} from './presetModel';
function preflight(){
 const proof=presetFixture(),ops=[COLLARBONE_PRESET_OP,'lnx.hsl.v1'];
 const result:PresetReply={protocol:1,request_id:'review-1',action:'preflight',success:true,outcome_unknown:false,id:'preset-1',
  document_id:proof.load_id,revision:proof.visual.revision,preflight_token:'f'.repeat(32),module_scope:ops,
  applies:{[COLLARBONE_PRESET_OP]:{version:1,amount:0},'lnx.hsl.v1':{version:1}},source_proof:proof.owner.source_proof,collarbone_preset:proof};
 return {result,ops,opts:{id:result.id,documentId:proof.load_id}};
}
test('complete mixed preset and collarbone-only zero require target proof',()=>{
 const {result,opts,ops}=preflight();assert.doesNotThrow(()=>validatePresetReply(result,'preflight',opts,result.request_id,ops));
 const single={...result,module_scope:[COLLARBONE_PRESET_OP],applies:{[COLLARBONE_PRESET_OP]:{version:1,amount:0}}};
 assert.doesNotThrow(()=>validatePresetReply(single,'preflight',opts,result.request_id,single.module_scope));
 assert.throws(()=>validatePresetReply({...result,collarbone_preset:undefined},'preflight',opts,result.request_id,ops));
});
test('direct apply without matching frozen visual review never reaches transport',async()=>{
 let sent=0;const flow=createPresetWorkflow({request:async()=>{sent++;return {requested:true};},read:async id=>({phase:'pending',request_id:id})},()=>{});
 flow.updateContext({enabled:true,editable:true,documentId:'current-load-session'});
 await flow.submit('apply',{id:'preset-1'},[COLLARBONE_PRESET_OP]);assert.equal(sent,0);
});
test('uncertain mutation requires same accepted token and exact single acknowledgment',()=>{
 const {result,opts,ops}=preflight(),ack=collarbonePresetAck(result.collarbone_preset!);
 const request={...opts,preflightToken:result.preflight_token,collarbonePresetAck:ack};
 const reply:PresetReply={protocol:1,request_id:'apply-1',id:result.id,action:'apply',success:false,outcome_unknown:true,document_id:opts.documentId,
  module_scope:ops,preflight_token:result.preflight_token,collarbone_preset_ack:ack,error:'read back original request'};
 assert.doesNotThrow(()=>validatePresetReply(reply,'apply',request,'apply-1',ops));
 for(const patch of [{id:'other-preset'},{module_scope:[COLLARBONE_PRESET_OP]},{preflight_token:'wrong'},{collarbone_preset_ack:undefined},{collarbone_preset_ack:[ack]},{collarbone_preset_ack:{...ack,preset_sha256:'bad'}}])
  assert.throws(()=>validatePresetReply({...reply,...patch} as PresetReply,'apply',request,'apply-1',ops));
});
test('UI/native keep independent read namespace, full graph display, and unknown apply fence',()=>{
 const read=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
 const native=read('../native.ts'),workflow=read('../presets/presetWorkflow.ts'),panel=read('../presets/PresetPanel.tsx'),hook=read('../presets/usePresetWorkflow.ts');
 assert.ok(native.includes("invoke('preset',{action:'collarbone_visual',...value})"));assert.ok(native.includes("invoke('preset_result',{requestId})"));
 assert.ok(workflow.includes('pending?.options.collarbonePresetAck!==undefined'));assert.ok(panel.includes('!w.collarboneReady'));
 assert.ok(hook.includes('collarbonePresetAck(review.collarbone_preset)'));assert.ok(hook.includes('COLLARBONE_PRESET_OP].includes(op)'));
 assert.ok(read('./CollarbonePresetReview.tsx').includes('imageLoader={load} preset'));
});
