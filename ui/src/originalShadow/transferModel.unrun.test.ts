// AUTHORED / UNRUN. Protocol/PNG unit fixtures and source checks are not browser or photo QA.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {SHADOW_TRANSFER_LIMITS,validShadowTransfer,validShadowTransferImage,verifyShadowTransferImage,
  shadowTransferReviewKey,shadowTransferImagesReady,shadowTransferAck,validShadowTransferAck,type ShadowTransferEvidence} from './transferModel.ts';

const image={mime:'image/png' as const,width:1,height:1,sha256:'1'.repeat(64),
  base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII='};
const review=():ShadowTransferEvidence=>({version:1,document_id:'a'.repeat(32),revision:'7',
  source_proof:{asset_sha256:'b'.repeat(64),original_sha256:'b'.repeat(64),creative_source:null},
  before_sha256:'c'.repeat(64),candidate_sha256:'d'.repeat(64),before_people_sha256:'e'.repeat(64),candidate_people_sha256:'e'.repeat(64),
  source_size:[1000,1000],before_output_size:[1000,1000],after_output_size:[1000,1000],
  parameters:{enabled:true,strength:40,blend:'normal'},before:{...image},after:{...image,sha256:'2'.repeat(64)}});
const valid=(value:unknown,expected=review())=>validShadowTransfer(value,expected.document_id,expected.revision,expected.parameters,expected.source_proof);

test('shadow proof binds full target source, canonical revisions, parameters and exact fields',()=>{
  assert.equal(valid(review()),true);
  const changes:Array<(value:Record<string,unknown>)=>void>=[
    value=>{value.version=2;},value=>{value.document_id='foreign';},value=>{value.revision='07';},
    value=>{value.revision='18446744073709551616';},value=>{value.candidate_sha256='Z'.repeat(64);},
    value=>{value.before_people_sha256='';},value=>{value.candidate_people_sha256=null;},
    value=>{value.parameters={enabled:true,strength:41};},value=>{value.parameters={enabled:true,strength:40,coverage:null};},
    value=>{value.parameters={enabled:true,strength:NaN};},value=>{value.parameters={enabled:1,strength:40};},
    value=>{value.source_proof={...review().source_proof,original_sha256:'f'.repeat(64)};},
    value=>{value.source_size=[0,1000];},value=>{value.before_output_size=[1000,Infinity];},
    value=>{value.after_output_size=[4294967296,1000];},value=>{value.source_mask={};},
    value=>{delete value.before;},value=>{value.before={...image,sha256:'short'};},
  ];
  for(const change of changes){const value=structuredClone(review()) as unknown as Record<string,unknown>;change(value);assert.equal(valid(value),false);}
  const loaded={...review(),document_id:'engine-load-id'};
  assert.equal(valid(loaded,loaded),true);
  assert.equal(valid({...loaded,document_id:'x'.repeat(129)},{...loaded,document_id:'x'.repeat(129)}),false);
});
test('derived source dimensions are target-owned and crop may change the output geometry',()=>{
  const value=review();value.source_proof={asset_sha256:'f'.repeat(64),original_sha256:'b'.repeat(64),creative_source:{sha256:'f'.repeat(64),width:1000,height:1000}};
  value.after_output_size=[800,600];value.after={...image,width:256,height:192};
  assert.equal(valid(value,value),true);
  assert.equal(valid({...value,source_size:[800,600]},value),false);
  assert.equal(valid({...value,after:{...value.after,height:100}},value),false);
  assert.equal(valid({...value,before:{...value.before,width:257}},value),false);
  assert.equal(valid({...value,after_output_size:[128,96]},value),false);
});
test('display payload bounds cannot be expanded with extra fields or malformed encoding',()=>{
  assert.equal(SHADOW_TRANSFER_LIMITS.edge,256);assert.equal(SHADOW_TRANSFER_LIMITS.base64,200000);
  for(const patch of [{mime:'image/svg+xml'},{width:256.5},{height:0},{source_mask:'foreign'},
    {base64:'iVBOR'+'A'.repeat(200003)},{base64:image.base64+'='},{base64:'data:image/png;base64,'+image.base64}]){
    assert.equal(validShadowTransferImage({...image,...patch}),false);
  }
});
test('actual PNG signature, canonical bytes, IHDR dimensions and SHA must all verify',async()=>{
  const sha256=createHash('sha256').update(Buffer.from(image.base64,'base64')).digest('hex');
  assert.equal(await verifyShadowTransferImage({...image,sha256}),true);
  assert.equal(await verifyShadowTransferImage(image),false);
  assert.equal(await verifyShadowTransferImage({...image,sha256,width:2}),false);
  assert.equal(await verifyShadowTransferImage({...image,sha256,base64:image.base64.slice(0,-4)+'AAAA'}),false);
  assert.equal(await verifyShadowTransferImage({...image,sha256,base64:'iVBORw=='}),false);
});
test('compact review keys bind hashes, geometry and settings without retaining image bytes',()=>{
  const value=review(),key=shadowTransferReviewKey('token',value);
  assert.equal(key.includes(image.base64),false);assert.ok(key.length<3000);
  assert.notEqual(key,shadowTransferReviewKey('new-token',value));
  assert.notEqual(key,shadowTransferReviewKey('token',{...value,revision:'8'}));
  assert.notEqual(key,shadowTransferReviewKey('token',{...value,parameters:{enabled:true,strength:41,blend:'normal'}}));
  assert.notEqual(key,shadowTransferReviewKey('token',{...value,after:{...value.after,sha256:'f'.repeat(64)}}));
});
test('every eligible target must be reviewed with the current plan key, never only the first images',()=>{
  const values=Array.from({length:8},(_,i)=>({...review(),document_id:String(i).repeat(32)}));
  const ready=Object.fromEntries(values.map(value=>[shadowTransferReviewKey('token',value),true]));
  assert.equal(shadowTransferImagesReady('token',values,ready),true);
  delete ready[shadowTransferReviewKey('token',values[7])];assert.equal(shadowTransferImagesReady('token',values,ready),false);
  ready[shadowTransferReviewKey('token',values[7])]=true;
  assert.equal(shadowTransferImagesReady('other-token',values,ready),false);
  assert.equal(shadowTransferImagesReady('token',[...values,review()],ready),false);
  assert.equal(shadowTransferImagesReady('token',[undefined],ready),false);
  assert.equal(shadowTransferImagesReady('token',values,{}),false);
});
test('acknowledgments are the exact ordered eligible PNG pairs, not recipe hashes or a generic checkbox',()=>{
  const a=review(),b={...review(),document_id:'second-load-id'},values=[a,b],ack=shadowTransferAck(values);
  assert.deepEqual(ack[0],{document_id:a.document_id,revision:a.revision,before_sha256:a.before.sha256,after_sha256:a.after.sha256});
  assert.equal(validShadowTransferAck(ack,values),true);
  assert.equal(validShadowTransferAck([...ack].reverse(),values),false);
  assert.equal(validShadowTransferAck(ack.slice(0,1),values),false);
  assert.equal(validShadowTransferAck([ack[0],ack[0]],values),false);
  assert.equal(validShadowTransferAck([{...ack[0],before_sha256:a.before_sha256},ack[1]],values),false);
  assert.equal(validShadowTransferAck([{...ack[0],reviewed:true},ack[1]],values),false);
  assert.equal(validShadowTransferAck(true,values),false);
});

test('shadow scalar contract rejects sample transfer and binds blend',()=>{
 const value=review();
 assert.equal(valid({...value,parameters:{...value.parameters,blend:'multiply'}}),false);
 assert.equal(valid({...value,parameters:{...value.parameters,lit_floor:null}}),false);
 assert.equal(valid({...value,parameters:{...value.parameters,blend:'screen'}}),false);
});
