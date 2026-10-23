// AUTHORED, UNRUN: no build, typecheck, test runner, app or inference executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import type {MaskObject} from '../localMasks/model.ts';
import {manualSpillObject,spillApplyFields,spillNotSent,spillPaintSourceKey,spillRequestFits,spillReviewKey,spillSourceDisplaySize,spillSourcePoint,validSpillPaint,validSpillPaintSource,validSpillPreviewFields,validSpillReview,verifySpillImage,type SpillReview,type SpillPaintSource,type SpillStroke} from './model.ts';
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
const stroke=():SpillStroke=>({id:'brush-edge-1',mode:'erase',points:[[.25,.5],[.75,.5]],radius:.025,opacity:.5,feather:25});
const source=():SpillPaintSource=>({version:1,token:'e'.repeat(32),...fence,source:{sha256:'c'.repeat(64),width:6000,height:4000},domain:'source-normalized',image:{...image,width:512,height:341},coverage:{...image,width:512,height:341}});
test('paint source shape binds full-source display dimensions, exact domain and immutable source metadata',()=>{
 assert.deepEqual(spillSourceDisplaySize(6000,4000),[512,341]);assert.deepEqual(spillSourceDisplaySize(4000,6000),[341,512]);assert.deepEqual(spillSourceDisplaySize(1,1000000),[1,512]);
 assert.equal(validSpillPaintSource(source(),fence),true);
 assert.equal(validSpillPaintSource({...source(),domain:'output-normalized'},fence),false);
 assert.equal(validSpillPaintSource({...source(),coverage:{...source().coverage,width:511}},fence),false);
 assert.equal(validSpillPaintSource({...source(),image:{...source().image,width:640}},fence),false);
 assert.equal(validSpillPaintSource({...source(),source:{...source().source,foreign:'other'}},fence),false);
 assert.equal(validSpillPaintSource(source(),{...fence,recipe_revision:'8'}),false);
 assert.notEqual(spillPaintSourceKey(source()),spillPaintSourceKey({...source(),source:{...source().source,sha256:'f'.repeat(64)}}));
});
test('paint DTO is bounded, exact, independently reviewed and never mixed with existing object selection',()=>{
 const paint={token:'e'.repeat(32),strokes:[stroke()]},parameters={enabled:true,strength:50};
 assert.equal(validSpillPaint(paint),true);
 assert.equal(validSpillPreviewFields({parameters,coverage_ids:null,coverage_reviewed:true,paint}),true);
 assert.equal(validSpillPreviewFields({parameters,coverage_ids:[],coverage_reviewed:true,paint}),false);
 assert.equal(validSpillPreviewFields({parameters,coverage_ids:null,coverage_reviewed:false,paint}),false);
 for(const patch of [{mode:'add'},{radius:.00009},{radius:.50001},{opacity:1.01},{feather:101},{points:[[NaN,0]]},{points:[[1.01,0]]},{points:[]},{extra:true}])assert.equal(validSpillPaint({...paint,strokes:[{...stroke(),...patch}]}),false);
 assert.equal(validSpillPaint({...paint,strokes:[stroke(),stroke()]}),false);
 assert.equal(validSpillPaint({...paint,strokes:[{...stroke(),points:Array.from({length:1025},()=>[.5,.5])}]}),false);
 assert.equal(validSpillPaint({...paint,strokes:Array.from({length:64},(_,i)=>({...stroke(),id:`stroke-${i}`}))}),false);
 assert.equal(validSpillPaint({...paint,strokes:Array.from({length:9},(_,i)=>({...stroke(),id:`stroke-${i}`,points:Array.from({length:1024},()=>[.5,.5])}))}),false);
 assert.equal(spillRequestFits({paint}),true);assert.equal(spillRequestFits({paint,padding:'x'.repeat(65536)}),false);
});
test('source pointer mapping uses the whole actual stage and rejects letterbox/outside/nonfinite geometry',()=>{
 const rect={left:100,top:200,width:600,height:400};
 assert.deepEqual(spillSourcePoint(400,400,rect),[.5,.5]);assert.deepEqual(spillSourcePoint(700,600,rect),[1,1]);
 assert.equal(spillSourcePoint(99,400,rect),null);assert.equal(spillSourcePoint(400,601,rect),null);
 assert.equal(spillSourcePoint(400,400,{...rect,width:0}),null);assert.equal(spillSourcePoint(400,400,{...rect,width:Infinity}),null);
 assert.deepEqual(spillSourcePoint(700,600,{...rect,width:1200,height:800}),[.5,.5]);
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
