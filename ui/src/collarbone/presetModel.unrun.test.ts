// AUTHORED / UNRUN. No imports, tests, compiler, model or application executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {presetFixture} from './presetFixture';
import {validCollarbonePreset,collarbonePresetAck,sameCollarbonePresetAck,collarbonePresetKey} from './presetModel';
test('zero amount still binds one actual target and logical document distinct from load session',()=>{
 const v=presetFixture();assert.notEqual(v.load_id,v.visual.document_id);
 assert.ok(validCollarbonePreset(v,v.load_id,v.visual.revision,v.owner.source_proof));
 assert.equal(validCollarbonePreset(v,v.visual.document_id,v.visual.revision,v.owner.source_proof),false);
});
test('foreign source, FaceRef, revision, coverage, document and schema refuse',()=>{
 for(const mutate of [(v:any)=>{v.face_ref.asset_sha256='f'.repeat(64);},(v:any)=>{v.owner.document.revision++;},
  (v:any)=>{v.visual.document_id='wrong';},(v:any)=>{v.coverage.targets=[];},(v:any)=>{v.coverage.targets.push(v.coverage.targets[0]);},
  (v:any)=>{v.source_masks=[];},(v:any)=>{v.preset_sha256='invalid';},(v:any)=>{v.visual.source_proof.asset_sha256='e'.repeat(64);}]){
  const v=structuredClone(presetFixture()),source=structuredClone(v.owner.source_proof),revision=v.visual.revision;mutate(v);
  assert.equal(validCollarbonePreset(v,v.load_id,revision,source),false);
 }
});
test('single preset acknowledgment cannot be replaced by batch arrays or stale recipe proof',()=>{
 const v=presetFixture(),ack=collarbonePresetAck(v);assert.ok(sameCollarbonePresetAck(ack,ack));assert.equal(sameCollarbonePresetAck([ack],ack),false);
 for(const field of Object.keys(ack))assert.equal(sameCollarbonePresetAck({...ack,[field]:'wrong'},ack),false);
 assert.equal(sameCollarbonePresetAck({...ack,source_mask:'copy'},ack),false);
});
test('display confirmation changes for request, preset, token and any frozen proof',()=>{
 const v=presetFixture(),key=collarbonePresetKey('token','request','preset',v);
 assert.notEqual(key,collarbonePresetKey('other','request','preset',v));assert.notEqual(key,collarbonePresetKey('token','other','preset',v));
 assert.notEqual(key,collarbonePresetKey('token','request','other',v));assert.notEqual(key,collarbonePresetKey('token','request','preset',{...v,applies_sha256:'c'.repeat(64)}));
});
test('derived preset proof keeps original provenance separate from actual target pixels',()=>{
 const v=structuredClone(presetFixture()),asset='e'.repeat(64),original=v.owner.source_proof.original_sha256;
 const proof={asset_sha256:asset,original_sha256:original,creative_source:{sha256:asset,width:1,height:1}};
 v.owner.source_proof=proof;v.visual.source_proof=structuredClone(proof);
 v.face_ref.asset_sha256=asset;v.coverage.targets[0].face_ref.asset_sha256=asset;
 assert.ok(validCollarbonePreset(v,v.load_id,v.visual.revision,proof));
 const stale=structuredClone(v);stale.face_ref.asset_sha256=original;
 assert.equal(validCollarbonePreset(stale,v.load_id,v.visual.revision,proof),false);
 const wrong=structuredClone(v);wrong.visual.source_proof.creative_source!.sha256='f'.repeat(64);
 assert.equal(validCollarbonePreset(wrong,v.load_id,v.visual.revision,proof),false);
});
