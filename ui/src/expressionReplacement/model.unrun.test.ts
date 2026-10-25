// SPDX-License-Identifier: GPL-3.0-or-later
// AUTHORED UNRUN. Contract fixtures only; placeholder image data is not photograph evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {CONFIRMATION_KEYS,OPERATION_ID,emptyFusion,freeze,packet,parseReceipt,previewCommand,validCurrent,validFace,validFusion,verifyImage,type ApplyCommand,type Confirmations,type Current,type Face,type Photograph,type PreviewCommand,type Source} from './model.ts';
import {H,command,current,photograph,ready} from './fixtures.unrun.ts';
test('source and FaceRef remain independently owned; unavailable pose angles are not accepted',()=>{
  const c=current();assert.equal(validCurrent(c),true);
  assert.equal(validFace({...c.photo.faces[0],face_ref:{...c.photo.faces[0].face_ref,asset_sha256:H('b')}},c.photo.source),false);
  assert.equal(validFace({...c.photo.faces[0],pose:{yaw:0,pitch:0,roll:0}},c.photo.source),false);
  assert.equal(validFace({...c.photo.faces[0],landmarks_count:0},c.photo.source),false);
});
test('empty/outside/over-budget fusion and missing human confirmation cannot preview',()=>{
  const c=command();assert.throws(()=>previewCommand({...c,fusion:emptyFusion()}));
  assert.equal(validFusion({...c.fusion,strokes:[{mode:'add',radius_px:12,points:[[0,0]]}]},c.target.source,c.target.face),false);
  assert.throws(()=>previewCommand({...c,confirmations:{...c.confirmations,same_person:false} as unknown as Confirmations}));
  assert.throws(()=>previewCommand({...c,donor:c.target}));
});
test('frozen packet is detached from caller buffers and canonical SHA includes full mask',async()=>{
  const raw=structuredClone(command()),p=await packet(raw);(raw.fusion.strokes[0].points[0] as [number,number])[0]=.7;
  assert.notEqual(p.command.fusion.strokes[0].points[0][0],.7);assert.deepEqual(JSON.parse(p.command_json),p.command);assert.equal(Object.isFrozen(p.command.donor.face.face_ref),true);
  assert.notEqual(p.command_sha256,(await packet({...command(),settings:{density:.5,pyramid_levels:3,colour_match_strength:0}})).command_sha256);
});
test('candidate receipt cannot substitute source, crop output, request or extra write claims',async()=>{
  const p=await packet(command()),r=ready(p);assert.ok(parseReceipt(r,p));
  assert.equal(parseReceipt({...r,command_sha256:H('9')},p),null);
  assert.equal(parseReceipt({...r,applied:true},p),null);
  assert.equal(parseReceipt({...r,preview:{...r.preview,output_width:200}},p),null);
  assert.equal(parseReceipt({...r,preview:{...r.preview,fusion_image:{...r.preview.fusion_image,source_sha256:H('b')}}},p),null);
});
test('fake fixture PNG cannot qualify as visual evidence',async()=>{const p=photograph();assert.equal(await verifyImage(p.image,p.source),false);});
test('save-copy receipt must name a distinct result source and must not mutate original',async()=>{
  const p=await packet(command()),r=ready(p);
  const apply:ApplyCommand=freeze({version:1,operation_id:OPERATION_ID,action:'apply',request_id:'apply-1',binding:p.command.binding,return_mode:'new_image',
    preview_request_id:p.command.request_id,preview_command_sha256:p.command_sha256,preview_token:r.preview.preview_token,candidate_sha256:r.preview.candidate_sha256,
    fusion_mask_sha256:r.preview.fusion_mask_sha256,before_image_sha256:r.preview.before.sha256,after_image_sha256:r.preview.after.sha256,fusion_image_sha256:r.preview.fusion_image.sha256,review:'full_before_after_and_fusion_confirmed'});
  const sent=await packet(apply),receipt={version:1,operation_id:OPERATION_ID,request_id:'apply-1',command_sha256:sent.command_sha256,action:'apply',binding:apply.binding,phase:'committed',preview_token:apply.preview_token,candidate_sha256:apply.candidate_sha256,fusion_mask_sha256:apply.fusion_mask_sha256,result_document_id:'result-copy-1',copied_original_document_id:apply.binding.document_id,result_source_sha256:apply.candidate_sha256,result_revision:0,no_change:false};
  assert.ok(parseReceipt(receipt,sent));assert.equal(parseReceipt({...receipt,result_document_id:apply.binding.document_id},sent),null);
  assert.equal(parseReceipt({...receipt,result_source_sha256:H('8')},sent),null);assert.equal(parseReceipt({...receipt,candidate_sha256:H('9')},sent),null);
});
