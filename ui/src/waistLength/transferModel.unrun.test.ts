// AUTHORED / UNRUN. Metadata/PNG fixtures are not real-photo or browser acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {WAIST_TRANSFER_LIMITS,waistTransferParameters,validWaistTransfer,validWaistTransferImage,verifyWaistTransferImage,
  waistTransferReviewKey,waistTransferImagesReady,waistTransferAck,validWaistTransferAck,sameWaistTransferAck,type WaistTransferEvidence} from './transferModel.ts';
import {torsoTransferReviewKey} from '../torsoLength/transferModel.ts';
import {bodyScalarNoWriteRejection} from '../bodyScalar/transferModel.ts';

const image={mime:'image/png' as const,width:1,height:1,sha256:'1'.repeat(64),base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII='};
const review=():WaistTransferEvidence=>({version:1,document_id:'a'.repeat(32),revision:'7',
  source_proof:{asset_sha256:'b'.repeat(64),original_sha256:'b'.repeat(64),creative_source:null},
  before_sha256:'c'.repeat(64),candidate_sha256:'d'.repeat(64),before_people_sha256:'e'.repeat(64),candidate_people_sha256:'e'.repeat(64),
  source_size:[1000,1000],before_output_size:[1000,1000],after_output_size:[1000,1000],parameters:{version:1,amount:.25},
  body_ref:{asset_sha256:'b'.repeat(64),body_instance_id:'body:actual',analysis_revision:3},
  associated_face:{associated_face_ref:{asset_sha256:'b'.repeat(64),face_instance_id:'face:actual',analysis_revision:4},associated_face_box:[.3,.1,.7,.3],associated_face_evidence_sha256:'9'.repeat(64)},
  body_support_sha256:'5'.repeat(64),body_review_sha256:'6'.repeat(64),before_bank_sha256:'7'.repeat(64),candidate_bank_sha256:'8'.repeat(64),
  before:{...image},after:{...image,sha256:'2'.repeat(64)}});
const valid=(value:unknown,expected=review())=>validWaistTransfer(value,expected.document_id,expected.revision,expected.parameters,expected.source_proof);
test('waist proof is exact, target owned and scalar only, including zero',()=>{
  assert.equal(valid(review()),true);
  const zero=review();zero.parameters.amount=0;assert.equal(valid(zero,zero),true);
  const changes:Array<(v:Record<string,unknown>)=>void>=[
    v=>{v.document_id='other';},v=>{v.revision='07';},v=>{v.revision='18446744073709551616';},
    v=>{v.parameters={version:1,amount:.26};},v=>{v.parameters={version:1,amount:.25,support:{}};},
    v=>{v.body_ref={...review().body_ref,asset_sha256:'f'.repeat(64)};},v=>{v.body_ref=review().associated_face.associated_face_ref;},
    v=>{v.associated_face={...review().associated_face,associated_face_ref:{...review().associated_face.associated_face_ref,asset_sha256:'f'.repeat(64)}};},
    v=>{v.associated_face={...review().associated_face,associated_face_box:[0,.1,.7,.3]};},
    v=>{v.associated_face={...review().associated_face,associated_face_box:[.3,.1,1,.3]};},
    v=>{v.body_support_sha256=null;},v=>{v.body_review_sha256='';},v=>{v.before_bank_sha256='bad';},v=>{v.candidate_bank_sha256='Z'.repeat(64);},
    v=>{v.source_support={};},v=>{v.after={...image,width:257};},v=>{v.source_proof={...review().source_proof,original_sha256:'f'.repeat(64)};},
  ];
  for(const change of changes){const value=structuredClone(review()) as unknown as Record<string,unknown>;change(value);assert.equal(valid(value),false);}
  for(const key of Object.keys(review())){const value=review() as unknown as Record<string,unknown>;delete value[key];assert.equal(valid(value),false,key);}
  for(const value of [{version:1,amount:true},{version:1,amount:NaN},{version:2,amount:0},{version:1,amount:1.01},{version:1,amount:0,body_ref:{}}])assert.equal(waistTransferParameters(value),false);
});
test('display payload bytes must verify, not only hashes and source-sized metadata',async()=>{
  const sha256=createHash('sha256').update(Buffer.from(image.base64,'base64')).digest('hex');
  assert.equal(await verifyWaistTransferImage({...image,sha256}),true);
  assert.equal(await verifyWaistTransferImage(image),false);
  assert.equal(await verifyWaistTransferImage({...image,sha256,width:2}),false);
  for(const patch of [{base64:'iVBOR'+'A'.repeat(200003)},{width:257},{mime:'image/svg+xml'},{unrequested:true}])assert.equal(validWaistTransferImage({...image,...patch}),false);
  assert.equal(WAIST_TRANSFER_LIMITS.targets,8);
});
test('every target needs current token, body/face/support/bank identity and both images',()=>{
  const value=review(),key=waistTransferReviewKey('token',value);
  assert.equal(key.includes(image.base64),false);
  for(const changed of [{...value,body_ref:{...value.body_ref,analysis_revision:4}},
    {...value,associated_face:{...value.associated_face,associated_face_evidence_sha256:'a'.repeat(64)}},
    {...value,body_review_sha256:'a'.repeat(64)},{...value,candidate_bank_sha256:'a'.repeat(64)}])assert.notEqual(waistTransferReviewKey('token',changed),key);
  const values=Array.from({length:8},(_,i)=>({...review(),document_id:`target-${i}`}));
  const ready=Object.fromEntries(values.map(v=>[waistTransferReviewKey('token',v),true]));
  assert.equal(waistTransferImagesReady('token',values,ready),true);
  assert.equal(waistTransferImagesReady('changed',values,ready),false);
  delete ready[waistTransferReviewKey('token',values[7])];assert.equal(waistTransferImagesReady('token',values,ready),false);
  assert.equal(waistTransferImagesReady('token',[undefined],ready),false);
  assert.equal(waistTransferImagesReady('token',[...values,review()],ready),false);
});
test('ack binds exact ordered PNG hashes and retains the reviewed revision',()=>{
  const values=[review(),{...review(),document_id:'other'}],ack=waistTransferAck(values);
  assert.equal(validWaistTransferAck(ack,values),true);assert.equal(sameWaistTransferAck(ack,ack),true);
  for(const changed of [[...ack].reverse(),ack.slice(0,1),[ack[0],ack[0]],
    [{...ack[0],before_sha256:values[0].before_sha256},ack[1]],[{...ack[0],reviewed:true},ack[1]],[{...ack[0],revision:'8'},ack[1]]]){
    assert.equal(validWaistTransferAck(changed,values),false);assert.equal(sameWaistTransferAck(changed,ack),false);
  }
});
test('source review gate requires PNG verification, decoded dimensions and explicit per-target checkbox',()=>{
  const source=readFileSync(new URL('../bodyScalar/BodyScalarTransferReview.tsx',import.meta.url),'utf8');
  for(const text of ['useLayoutEffect','verifyBodyScalarTransferImage(value.before)','verifyBodyScalarTransferImage(value.after)','image.naturalWidth===expected.width','image.naturalHeight===expected.height','disabled={disabled||!ready}','viewed.checked','notify.current(reviewKey,false)'])assert.ok(source.includes(text),text);
  const wrapper=readFileSync(new URL('./WaistTransferReview.tsx',import.meta.url),'utf8');assert.ok(wrapper.includes('BodyScalarTransferReview'));assert.ok(wrapper.includes('四个腰部标记'));
  const hook=readFileSync(new URL('../batch/useBatchWorkflow.ts',import.meta.url),'utf8');assert.ok(hook.includes('commit(ack,shadowAck,torsoAck,waistAck)'));
});
test('waist review keys cannot reuse a torso checkbox even with identical proof metadata',()=>{
  const value=review(),torsoKey=torsoTransferReviewKey('token:request',value);
  assert.notEqual(waistTransferReviewKey('token:request',value),torsoKey);
  assert.equal(waistTransferImagesReady('token:request',[value],{[torsoKey]:true}),false);
});
test('derived sources bind their own source dimensions and reject original/derived substitution',()=>{
  const value=review();value.source_size=[640,480];value.before_output_size=[640,480];value.after_output_size=[640,480];
  value.source_proof={asset_sha256:'b'.repeat(64),original_sha256:'c'.repeat(64),creative_source:{sha256:'b'.repeat(64),width:640,height:480}};
  // A one-pixel metadata sample is not a real render; this checks source geometry only.
  assert.equal(valid(value,value),true);
  assert.equal(valid({...value,source_size:[1000,1000]},value),false);
  assert.equal(valid(value,review()),false);
});
test('only explicit pre-claim no-write rejection can omit accepted identity',()=>{
  const value={success:false,outcome_unknown:false,error:'Claim rejected',preflight_token:'token',target_outcomes:[]};
  assert.equal(bodyScalarNoWriteRejection(value,'token'),true);
  for(const patch of [{success:true},{outcome_unknown:true},{outcome_unknown:undefined},{error:''},{preflight_token:'other'},
    {waist_review_ack:[]},{waist_review_ack:null},{module_scope:null},{module_scope:['lnx.waist_length.v1']},{after:{}},{doc_state:{}},{operation_committed:true},
    {target_outcomes:[{outcome:'applied'}]},{target_outcomes:[{outcome:'not_applied',result_revision:'9'}]}])assert.equal(bodyScalarNoWriteRejection({...value,...patch},'token'),false);
});
