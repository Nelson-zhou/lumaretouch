// AUTHORED, UNRUN. No product import, test runner, compiler, build or image render executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {deflateSync} from 'node:zlib';
import {editable,type Recipe} from '../idBackground/model.ts';
import type {MaskObject} from '../localMasks/model.ts';
import {originalShadowActive,originalShadowApplyFields,originalShadowManualObject,originalShadowNotSent,originalShadowRequestFits,originalShadowReviewKey,originalShadowSubjectEligible,validOriginalShadowImage,validOriginalShadowPreviewFields,validOriginalShadowReview,verifyOriginalShadowImage,type OriginalShadowBinding,type OriginalShadowImage,type OriginalShadowPreviewFields,type OriginalShadowRecipe,type OriginalShadowReview} from './model.ts';

const fence={recipe_document_id:'a'.repeat(32),recipe_revision:'7'};
const source={sha256:'b'.repeat(64),width:6000,height:4000};
function crc32(bytes:Uint8Array){let c=0xffffffff;for(const n of bytes){c^=n;for(let bit=0;bit<8;bit++)c=(c>>>1)^((c&1)?0xedb88320:0);}return (c^0xffffffff)>>>0;}
function chunk(name:string,bytes:Uint8Array){const body=Buffer.concat([Buffer.from(name,'ascii'),bytes]),length=Buffer.alloc(4),crc=Buffer.alloc(4);length.writeUInt32BE(bytes.length);crc.writeUInt32BE(crc32(body));return Buffer.concat([length,body,crc]);}
function image(extra:{beforeData?:Buffer[];afterData?:Buffer[];color?:number;bitDepth?:number;idat?:Buffer[]}={}):OriginalShadowImage{
 const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(1,0);ihdr.writeUInt32BE(1,4);ihdr[8]=extra.bitDepth??8;ihdr[9]=extra.color??2;
 const compressed=deflateSync(Buffer.from([0,32,64,96]));
 const raw=Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',ihdr),...(extra.beforeData??[]),...(extra.idat??[chunk('IDAT',compressed)]),...(extra.afterData??[]),chunk('IEND',Buffer.alloc(0))]);
 return {mime:'image/png',width:1,height:1,base64:raw.toString('base64'),sha256:createHash('sha256').update(raw).digest('hex')};
}
const review=():OriginalShadowReview=>({version:1,token:'c'.repeat(32),...fence,source:{...source},candidate_sha256:'d'.repeat(64),before:image(),after:image(),boundaries:[]});
const fields=():OriginalShadowPreviewFields=>({parameters:{enabled:true,strength:100,blend:'normal'},lit_ids:['lit-1'],retention_ids:['shadow-1'],samples_reviewed:true,uniform_floor_confirmed:true});
const object=(kind:string,extra:Record<string,unknown>={})=>({id:'mask-1',kind,enabled:true,operation:'add',opacity:1,feather:0,name:'Fixture',...extra}) as MaskObject;
const binding=(objects:MaskObject[]):OriginalShadowBinding=>({version:1,reviewed:true,recipe_sha256:'e'.repeat(64),mask:{source,semantic_owner:null,recipe:{version:1,domain:'source-normalized',objects}}});
const intent=():OriginalShadowRecipe=>({version:1,algorithm:'lrt-original-shadow-uniform-floor-v1',enabled:false,strength:100,blend:'normal',uniform_floor_confirmed:false,lit_floor:null,retention:null});

test('v1 and v2 JSON are never upgraded by ordinary editable; v3 bindings remain private to review actions',()=>{
 const base={enabled:false,source:null,background:{},support:{subject:null,contact:null,all:null},selected_support:'subject',edge:0,opacity:1,shadow:{},favourites:[]};
 for(const version of [1,2,3]){
  const recipe={...base,version,...(version>1?{spill:{version:1,algorithm:'lrt-spill-removal-v1',enabled:false,strength:50,coverage:null}}:{}),...(version===3?{original_shadow:intent()}:{} )} as unknown as Recipe;
  const before=JSON.stringify(recipe),edit=editable(recipe);
  assert.equal(JSON.stringify(recipe),before);
  assert.deepEqual(Object.keys(edit).sort(),['background','edge','enabled','favourites','opacity','selected_support','shadow']);
 }
});
test('separate independent nonempty groups, null-preserve roles, explicit review and uniform-floor declaration',()=>{
 assert.equal(validOriginalShadowPreviewFields(fields()),true);
 assert.equal(validOriginalShadowPreviewFields({...fields(),lit_ids:null}),true);
 assert.equal(validOriginalShadowPreviewFields({...fields(),lit_ids:null,retention_ids:null,samples_reviewed:false}),true);
 for(const patch of [{lit_ids:[]},{retention_ids:[]},{lit_ids:['lit-1','lit-1']},{retention_ids:['lit-1']},{samples_reviewed:false},{uniform_floor_confirmed:false},{lit_ids:['bad id']},{lit_ids:Array.from({length:65},(_,i)=>`lit-${i}`)},{extra:true}])assert.equal(validOriginalShadowPreviewFields({...fields(),...patch}),false);
 assert.equal(validOriginalShadowPreviewFields({...fields(),lit_ids:null,retention_ids:null,samples_reviewed:true}),false);
 assert.equal(validOriginalShadowPreviewFields({...fields(),parameters:{...fields().parameters,enabled:false},uniform_floor_confirmed:false}),true);
 for(const blend of ['normal','multiply','softlight'])assert.equal(validOriginalShadowPreviewFields({...fields(),parameters:{enabled:true,strength:0,blend}}),true);
 for(const patch of [{enabled:'true'},{strength:-1},{strength:101},{strength:NaN},{strength:Infinity},{strength:true},{blend:'screen'},{ai:true}])assert.equal(validOriginalShadowPreviewFields({...fields(),parameters:{...fields().parameters,...patch}}),false);
});
test('only current geometric masks and full-source geometric subject support qualify for this method',()=>{
 assert.equal(originalShadowManualObject(object('brush',{points:[[.5,.5]]})),true);
 assert.equal(originalShadowManualObject(object('brush',{points:[]})),false);
 assert.equal(originalShadowManualObject(object('radial',{enabled:false})),false);
 for(const kind of ['linear','radial'])assert.equal(originalShadowManualObject(object(kind)),true);
 for(const kind of ['prompted','semantic','full','color_range','luminance_range']){
  assert.equal(originalShadowManualObject(object(kind)),false);
  assert.equal(originalShadowSubjectEligible(binding([object('linear'),object(kind)])),false);
 }
 assert.equal(originalShadowSubjectEligible(binding([object('brush',{points:[[.2,.3]]}),object('radial')])),true);
 assert.equal(originalShadowSubjectEligible(binding([])),false);assert.equal(originalShadowSubjectEligible({}),false);assert.equal(originalShadowSubjectEligible(null),false);
});
test('original intent is independent of spill and projected shadows; strength zero is neutral',()=>{
 assert.equal(originalShadowActive(intent()),false);assert.equal(originalShadowActive({...intent(),enabled:true,strength:0}),false);
 assert.equal(originalShadowActive({...intent(),enabled:true,strength:1}),true);assert.equal(originalShadowActive(null),false);
});
test('review identity binds its exact recipe and completed output geometry, not immutable-source aspect',()=>{
 const value=review();assert.equal(validOriginalShadowReview(value,fence),true);
 // A square output from a 6000x4000 source may legitimately include a crop.
 assert.equal(value.before.width/value.before.height,value.after.width/value.after.height);
 assert.equal(validOriginalShadowReview(value,{...fence,recipe_revision:'8'}),false);
 for(const patch of [{version:2},{token:'0'.repeat(32)},{recipe_revision:'07'},{recipe_revision:'18446744073709551616'},{source:{...source,borrowed_from:'other'}},{boundaries:['bad\0boundary']},{review:value},{after:{...value.after,width:2}},{before:{...value.before,width:513},after:{...value.after,width:513}}])assert.equal(validOriginalShadowReview({...value,...patch},fence),false);
 assert.equal(validOriginalShadowImage({...value.before,base64:'not-a-png'}),false);
 assert.equal(validOriginalShadowImage({...value.before,base64:'iVBOR'+'A'.repeat(1398104)}),false);
});
test('apply acknowledges the actual PNG hashes, never a spill or candidate hash',()=>{
 const value=review();assert.deepEqual(originalShadowApplyFields(value),{token:value.token,reviewed:true,before_sha256:value.before.sha256,after_sha256:value.after.sha256});
 assert.notEqual(originalShadowReviewKey(value),originalShadowReviewKey({...value,after:{...value.after,sha256:'f'.repeat(64)}}));
 assert.notEqual(originalShadowReviewKey(value),originalShadowReviewKey({...value,source:{...source,sha256:'f'.repeat(64)}}));
});
test('only exact correlated native no-send proof permits rejection recovery; request limit includes envelope',()=>{
 const expected={action:'id_original_shadow_apply',request_id:'apply-1',document_id:'photo-1'},result={...expected,requested:false,not_sent:true,protocol:1,error:'budget full'};
 assert.equal(originalShadowNotSent(result,expected),true);
 for(const patch of [{action:'id_spill_apply'},{request_id:'other'},{document_id:'other'},{not_sent:false},{requested:true},{protocol:2},{error:''},{extra:true}])assert.equal(originalShadowNotSent({...result,...patch},expected),false);
 assert.equal(originalShadowRequestFits({...fields(),...fence}),true);assert.equal(originalShadowRequestFits({padding:'x'.repeat(65536)}),false);
});
test('PNG byte verification requires canonical data, CRCs, SHA256, dimensions and a nonanimated RGB8 envelope',async()=>{
 const good=image();assert.equal(await verifyOriginalShadowImage(good),true);
 assert.equal(await verifyOriginalShadowImage({...good,sha256:'0'.repeat(64)}),false);
 assert.equal(await verifyOriginalShadowImage({...good,width:2}),false);
 assert.equal(await verifyOriginalShadowImage({...good,base64:good.base64+'AAAA'}),false);
 const broken=Buffer.from(good.base64,'base64');broken[29]^=1;
 assert.equal(await verifyOriginalShadowImage({...good,base64:broken.toString('base64'),sha256:createHash('sha256').update(broken).digest('hex')}),false);
 for(const name of ['acTL','fcTL','fdAT','ABCD','abcd'])assert.equal(await verifyOriginalShadowImage(image({beforeData:[chunk(name,Buffer.from([1]))]})),false);
 assert.equal(await verifyOriginalShadowImage(image({color:0})),false);assert.equal(await verifyOriginalShadowImage(image({bitDepth:16})),false);
 assert.equal(await verifyOriginalShadowImage(image({idat:[chunk('IDAT',Buffer.alloc(0))]})),false);
 assert.equal(await verifyOriginalShadowImage(image({idat:[chunk('IDAT',Buffer.from([1])),chunk('tEXt',Buffer.from([1])),chunk('IDAT',Buffer.from([2]))]})),false);
});
