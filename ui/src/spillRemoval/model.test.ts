// AUTHORED, UNRUN: no build, typecheck, test runner, app or inference executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import type {MaskObject} from '../localMasks/model.ts';
import {manualSpillObject,spillApplyFields,spillNotSent,spillReviewKey,validSpillPreviewFields,validSpillReview,verifySpillImage,type SpillReview} from './model.ts';
const fence={recipe_document_id:'a'.repeat(32),recipe_revision:'7'};
const image={mime:'image/png' as const,width:1,height:1,sha256:'1'.repeat(64),base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII='};
const review=():SpillReview=>({version:1,token:'b'.repeat(32),...fence,source:{sha256:'c'.repeat(64),width:6000,height:4000},candidate_sha256:'d'.repeat(64),before:{...image},after:{...image,sha256:'2'.repeat(64)},boundaries:[]});
test('only a correlated native not-sent result unlocks a rejected admission',()=>{
  const expected={action:'id_spill_apply',request_id:'apply-1',document_id:'photo'};
  const result={...expected,requested:false,not_sent:true,protocol:1,error:'budget full'};
  assert.equal(spillNotSent(result,expected),true);
  assert.equal(spillNotSent({...result,request_id:'other'},expected),false);
  assert.equal(spillNotSent({...result,not_sent:false},expected),false);
  assert.equal(spillNotSent({...result,requested:true},expected),false);
  assert.equal(spillNotSent('not sent',expected),false);
 });
test('separates retaining, clearing, and explicitly reviewed owned manual coverage',()=>{
  const parameters={enabled:true,strength:50};
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:null,coverage_reviewed:false}),true);
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:[],coverage_reviewed:false}),true);
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:['a'.repeat(32)],coverage_reviewed:true}),true);
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:['brush_edge-1'],coverage_reviewed:true}),true);
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:['a'.repeat(32)],coverage_reviewed:false}),false);
  assert.equal(validSpillPreviewFields({parameters,coverage_ids:['a'.repeat(32),'a'.repeat(32)],coverage_reviewed:true}),false);
  assert.equal(validSpillPreviewFields({parameters:{enabled:true,strength:NaN},coverage_ids:null,coverage_reviewed:false}),false);
 });
test('binds a real bounded same-size pair to the precise recipe fence',()=>{
  assert.equal(validSpillReview(review(),fence),true);
  assert.equal(validSpillReview(review(),{...fence,recipe_revision:'8'}),false);
  assert.equal(validSpillReview({...review(),recipe_revision:'07'},fence),false);
  assert.equal(validSpillReview({...review(),source:{...review().source,transferred_from:'other'}},fence),false);
  assert.equal(validSpillReview({...review(),after:{...image,width:2}},fence),false);
  assert.equal(validSpillReview({...review(),before:{...image,width:641},after:{...image,width:641}},fence),false);
 });
test('application acknowledges PNG hashes, never substitutes candidate-recipe hash',()=>{
  const value=review();assert.deepEqual(spillApplyFields(value),{token:value.token,reviewed:true,before_sha256:value.before.sha256,after_sha256:value.after.sha256});
  assert.notEqual(spillReviewKey({...value,after:{...value.after,sha256:'f'.repeat(64)}}),spillReviewKey(value));
 });
test('verifies actual PNG bytes independently of metadata and load events',async()=>{
  const sha256=createHash('sha256').update(Buffer.from(image.base64,'base64')).digest('hex');
  assert.equal(await verifySpillImage({...image,sha256}),true);
  assert.equal(await verifySpillImage(image),false);
  assert.equal(await verifySpillImage({...image,base64:image.base64+'AAAA'}),false);
 });
test('selects drawn source vectors, never semantic, full-frame, prompted or value-range objects',()=>{
  const object=(kind:string,extra:Record<string,unknown>={})=>({id:'a'.repeat(32),enabled:true,kind,...extra}) as MaskObject;
  assert.equal(manualSpillObject(object('brush',{points:[[.5,.5]]})),true);
  assert.equal(manualSpillObject(object('brush',{points:[]})),false);
  assert.equal(manualSpillObject(object('linear')),true);
  assert.equal(manualSpillObject(object('radial')),true);
  for(const kind of ['semantic','full','prompted','color_range','luminance_range'])assert.equal(manualSpillObject(object(kind)),false);
 });
