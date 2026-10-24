// AUTHORED / UNRUN. Source-contract fixtures, not runtime or photographic evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {presetFixture} from '../collarbone/presetFixture';
import {OP,validDecorationCoverage,validDecorationPreset,decorationPresetAck,sameDecorationPresetAck,decorationPresetKey,type DecorationPreset} from './transferModel';
import {validatePresetReply,createPresetWorkflow,type PresetReply} from '../presets/presetWorkflow';
function fixture():DecorationPreset{
 const base=presetFixture();return {...base,coverage:{version:1,support_transfer:'none',targets:[{face_ref:base.face_ref,scope:'target-reviewed-visible-skin',visibility_sha256:'c'.repeat(64),recipe_sha256:'d'.repeat(64)}]}};
}
test('preset binds logical owner separately from load identity, with independent skin evidence',()=>{
 const v=fixture();assert.ok(validDecorationPreset(v,v.load_id,v.visual.revision,v.owner.source_proof));
 assert.equal(validDecorationPreset(v,v.visual.document_id,v.visual.revision,v.owner.source_proof),false);
 for(const mutate of [(x:any)=>{x.coverage.targets[0].face_ref.asset_sha256='e'.repeat(64);},(x:any)=>{x.coverage.targets[0].visibility_sha256=null;},(x:any)=>{x.coverage.targets[0].recipe_sha256='wrong';},(x:any)=>{x.coverage.targets.push(x.coverage.targets[0]);},(x:any)=>{x.coverage.targets[0].body_review_sha256='f'.repeat(64);},(x:any)=>{x.visual.candidate_people_sha256='bad';}]){
  const x=structuredClone(v),proof=structuredClone(v.owner.source_proof);mutate(x);assert.equal(validDecorationPreset(x,v.load_id,v.visual.revision,proof),false);
 }
});
test('neutral recipe remains reviewed and no donor masks are portable',()=>{
 const v=fixture();v.coverage.targets[0].scope='neutral-no-effect';v.coverage.targets[0].visibility_sha256=null;
 assert.ok(validDecorationCoverage(v.coverage,v.owner.source_proof));
 assert.equal(validDecorationCoverage({...v.coverage,support_transfer:'copied'},v.owner.source_proof),false);
 const ack=decorationPresetAck(v);assert.ok(sameDecorationPresetAck(ack,ack));
 for(const field of Object.keys(ack))assert.equal(sameDecorationPresetAck({...ack,[field]:'wrong'},ack),false);
 assert.equal(sameDecorationPresetAck([ack],ack),false);
 assert.notEqual(decorationPresetKey('token','read','p',v),decorationPresetKey('token','new-read','p',v));
});
test('retained active decorations require evidence even when absent from selected scope',()=>{
 const v=fixture(),module_scope=['lnx.hsl.v1'];
 const reply:PresetReply={protocol:1,request_id:'preflight',action:'preflight',success:true,outcome_unknown:false,id:'p',document_id:v.load_id,revision:v.visual.revision,preflight_token:'f'.repeat(32),module_scope,applies:{'lnx.hsl.v1':{version:1}},source_proof:v.owner.source_proof,face_decoration_visual_required:true,face_decoration_preset:v};
 const opts={id:'p',documentId:v.load_id};
 assert.doesNotThrow(()=>validatePresetReply(reply,'preflight',opts,'preflight',module_scope));
 assert.throws(()=>validatePresetReply({...reply,face_decoration_preset:undefined},'preflight',opts,'preflight',module_scope));
 assert.throws(()=>validatePresetReply({...reply,face_decoration_visual_required:false},'preflight',opts,'preflight',module_scope));
});
test('selected decoration direct apply without frozen full review never sends',async()=>{
 let sends=0;const flow=createPresetWorkflow({request:async()=>{sends++;return {requested:true};},read:async request_id=>({phase:'pending',request_id})},()=>{});
 flow.updateContext({enabled:true,editable:true,documentId:'load'});await flow.submit('apply',{id:'p'},[OP]);assert.equal(sends,0);
});
