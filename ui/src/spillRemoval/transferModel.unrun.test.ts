// AUTHORED / UNRUN. Protocol/PNG unit fixtures and source checks are not browser or photo QA.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {SPILL_TRANSFER_LIMITS,validSpillTransfer,validSpillTransferImage,verifySpillTransferImage,
  spillTransferReviewKey,spillTransferImagesReady,spillTransferAck,validSpillTransferAck,type SpillTransferEvidence} from './transferModel.ts';

const image={mime:'image/png' as const,width:1,height:1,sha256:'1'.repeat(64),
  base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII='};
const review=():SpillTransferEvidence=>({version:1,document_id:'a'.repeat(32),revision:'7',
  source_proof:{asset_sha256:'b'.repeat(64),original_sha256:'b'.repeat(64),creative_source:null},
  before_sha256:'c'.repeat(64),candidate_sha256:'d'.repeat(64),before_people_sha256:'e'.repeat(64),candidate_people_sha256:'e'.repeat(64),
  source_size:[1000,1000],before_output_size:[1000,1000],after_output_size:[1000,1000],
  parameters:{enabled:true,strength:40},before:{...image},after:{...image,sha256:'2'.repeat(64)}});
const valid=(value:unknown,expected=review())=>validSpillTransfer(value,expected.document_id,expected.revision,expected.parameters,expected.source_proof);

test('spill proof binds full target source, canonical revisions, parameters and exact fields',()=>{
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
  assert.equal(SPILL_TRANSFER_LIMITS.edge,256);assert.equal(SPILL_TRANSFER_LIMITS.base64,200000);
  for(const patch of [{mime:'image/svg+xml'},{width:256.5},{height:0},{source_mask:'foreign'},
    {base64:'iVBOR'+'A'.repeat(200003)},{base64:image.base64+'='},{base64:'data:image/png;base64,'+image.base64}]){
    assert.equal(validSpillTransferImage({...image,...patch}),false);
  }
});
test('actual PNG signature, canonical bytes, IHDR dimensions and SHA must all verify',async()=>{
  const sha256=createHash('sha256').update(Buffer.from(image.base64,'base64')).digest('hex');
  assert.equal(await verifySpillTransferImage({...image,sha256}),true);
  assert.equal(await verifySpillTransferImage(image),false);
  assert.equal(await verifySpillTransferImage({...image,sha256,width:2}),false);
  assert.equal(await verifySpillTransferImage({...image,sha256,base64:image.base64.slice(0,-4)+'AAAA'}),false);
  assert.equal(await verifySpillTransferImage({...image,sha256,base64:'iVBORw=='}),false);
});
test('compact review keys bind hashes, geometry and settings without retaining image bytes',()=>{
  const value=review(),key=spillTransferReviewKey('token',value);
  assert.equal(key.includes(image.base64),false);assert.ok(key.length<3000);
  assert.notEqual(key,spillTransferReviewKey('new-token',value));
  assert.notEqual(key,spillTransferReviewKey('token',{...value,revision:'8'}));
  assert.notEqual(key,spillTransferReviewKey('token',{...value,parameters:{enabled:true,strength:41}}));
  assert.notEqual(key,spillTransferReviewKey('token',{...value,after:{...value.after,sha256:'f'.repeat(64)}}));
});
test('every eligible target must be reviewed with the current plan key, never only the first images',()=>{
  const values=Array.from({length:8},(_,i)=>({...review(),document_id:String(i).repeat(32)}));
  const ready=Object.fromEntries(values.map(value=>[spillTransferReviewKey('token',value),true]));
  assert.equal(spillTransferImagesReady('token',values,ready),true);
  delete ready[spillTransferReviewKey('token',values[7])];assert.equal(spillTransferImagesReady('token',values,ready),false);
  ready[spillTransferReviewKey('token',values[7])]=true;
  assert.equal(spillTransferImagesReady('other-token',values,ready),false);
  assert.equal(spillTransferImagesReady('token',[...values,review()],ready),false);
  assert.equal(spillTransferImagesReady('token',[undefined],ready),false);
  assert.equal(spillTransferImagesReady('token',values,{}),false);
});
test('acknowledgments are the exact ordered eligible PNG pairs, not recipe hashes or a generic checkbox',()=>{
  const a=review(),b={...review(),document_id:'second-load-id'},values=[a,b],ack=spillTransferAck(values);
  assert.deepEqual(ack[0],{document_id:a.document_id,revision:a.revision,before_sha256:a.before.sha256,after_sha256:a.after.sha256});
  assert.equal(validSpillTransferAck(ack,values),true);
  assert.equal(validSpillTransferAck([...ack].reverse(),values),false);
  assert.equal(validSpillTransferAck(ack.slice(0,1),values),false);
  assert.equal(validSpillTransferAck([ack[0],ack[0]],values),false);
  assert.equal(validSpillTransferAck([{...ack[0],before_sha256:a.before_sha256},ack[1]],values),false);
  assert.equal(validSpillTransferAck([{...ack[0],reviewed:true},ack[1]],values),false);
  assert.equal(validSpillTransferAck(true,values),false);
});
test('review source keeps browser-load and explicit-view gates and invalidates payload changes before paint',()=>{
  const source=readFileSync(new URL('./SpillTransferReview.tsx',import.meta.url),'utf8');
  assert.match(source,/naturalWidth===expected.width&&image.naturalHeight===expected.height/);
  assert.match(source,/const confirmed=ready&&viewed.key===reviewKey&&viewed.checked/);
  assert.match(source,/type="checkbox" checked=\{confirmed\} disabled=\{disabled\|\|!ready\}/);
  assert.match(source,/useLayoutEffect\(\(\)=>\{/);
  assert.match(source,/return\(\)=>notify.current\(reviewKey,false\)/);
  assert.match(source,/\[reviewKey,value.before.base64,value.before.sha256,value.after.base64,value.after.sha256\]/);
  const hook=readFileSync(new URL('../presets/usePresetWorkflow.ts',import.meta.url),'utf8');
  assert.match(hook,/!cropReady\|\|!xmpReady\|\|!spillReady/);
  assert.match(hook,/review.preflight_token\}:\$\{review.request_id/);
  const batch=readFileSync(new URL('../batch/BatchReview.tsx',import.meta.url),'utf8');
  assert.match(batch,/state.plan\?\.preflight_token,state.plan\?\.request_id,open/);
  assert.match(batch,/spillTargets.map\(t=>t.spill_transfer\)/);
});
