// SPDX-License-Identifier: GPL-3.0-or-later
import type {BodyRef,FaceRef,Box,TorsoLengthRecipe} from './model';
import {sourceProof} from '../cropTransfer/model.ts';
import type {EffectiveSourceProof} from '../people/transferProof';
import {spillRevision,type SpillImage} from '../spillRemoval/model.ts';
import {sameShadowSourceProof,validShadowTransferImage,verifyShadowTransferImage} from '../originalShadow/transferModel.ts';

export const TORSO_TRANSFER_OP='lnx.torso_length.v1';
export const TORSO_TRANSFER_LIMITS={targets:8,edge:256,base64:200000,dimension:4294967295} as const;
export type TorsoFaceBinding={associated_face_ref:FaceRef;associated_face_box:Box;associated_face_evidence_sha256:string};
/** Display-only samples of this target's full canonical render, not copied source support. */
export type TorsoTransferEvidence={
  version:1;document_id:string;revision:string;source_proof:EffectiveSourceProof;
  before_sha256:string;candidate_sha256:string;before_people_sha256:string;candidate_people_sha256:string;
  source_size:[number,number];before_output_size:[number,number];after_output_size:[number,number];
  parameters:TorsoLengthRecipe;body_ref:BodyRef;associated_face:TorsoFaceBinding;
  body_support_sha256:string;body_review_sha256:string;before_bank_sha256:string;candidate_bank_sha256:string;
  before:SpillImage;after:SpillImage;
};
export type TorsoTransferAck={document_id:string;revision:string;before_sha256:string;after_sha256:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const documentId=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.length<=128&&!/[\u0000-\u001f\u007f]/.test(v);
const refId=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.length<=128&&/^[A-Za-z0-9_.:-]+$/.test(v);
const revision=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
const dimension=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>0&&v<=TORSO_TRANSFER_LIMITS.dimension;
const size=(v:unknown):v is [number,number]=>Array.isArray(v)&&v.length===2&&v.every(dimension);
export function torsoTransferParameters(v:unknown):v is TorsoLengthRecipe{
  return object(v)&&keys(v,['version','amount'])&&v.version===1&&typeof v.amount==='number'&&Number.isFinite(v.amount)&&Math.abs(v.amount)<=1;
}
export function validTorsoBodyRef(v:unknown,asset:string):v is BodyRef{
  return object(v)&&keys(v,['asset_sha256','body_instance_id','analysis_revision'])&&v.asset_sha256===asset&&hash(v.asset_sha256)&&refId(v.body_instance_id)&&revision(v.analysis_revision);
}
export function validTorsoFaceBinding(v:unknown,asset:string):v is TorsoFaceBinding{
  if(!object(v)||!keys(v,['associated_face_ref','associated_face_box','associated_face_evidence_sha256'])||!hash(v.associated_face_evidence_sha256))return false;
  const ref=v.associated_face_ref,box=v.associated_face_box;
  return object(ref)&&keys(ref,['asset_sha256','face_instance_id','analysis_revision'])&&ref.asset_sha256===asset&&hash(ref.asset_sha256)&&refId(ref.face_instance_id)&&revision(ref.analysis_revision)
    &&Array.isArray(box)&&box.length===4&&box.every(n=>typeof n==='number'&&Number.isFinite(n)&&n>0&&n<1)&&box[0]<box[2]&&box[1]<box[3];
}
export const validTorsoTransferImage=validShadowTransferImage;
export const verifyTorsoTransferImage=verifyShadowTransferImage;
function matchesOutput(image:SpillImage,output:[number,number]):boolean{
  return image.width<=output[0]&&image.height<=output[1]&&Math.abs(image.width*output[1]-image.height*output[0])<=Math.max(...output);
}
export function validTorsoTransfer(v:unknown,id:string,rev:string|undefined,parameters:unknown,expectedSource:unknown):v is TorsoTransferEvidence{
  if(!object(v)||!keys(v,['version','document_id','revision','source_proof','before_sha256','candidate_sha256','before_people_sha256','candidate_people_sha256',
    'source_size','before_output_size','after_output_size','parameters','body_ref','associated_face','body_support_sha256','body_review_sha256','before_bank_sha256','candidate_bank_sha256','before','after'])
    ||v.version!==1||!documentId(v.document_id)||v.document_id!==id||!spillRevision(v.revision)||v.revision!==rev
    ||!sourceProof(v.source_proof)||!sameShadowSourceProof(v.source_proof,expectedSource)
    ||!['before_sha256','candidate_sha256','before_people_sha256','candidate_people_sha256','body_support_sha256','body_review_sha256','before_bank_sha256','candidate_bank_sha256'].every(key=>hash(v[key]))
    ||!size(v.source_size)||!size(v.before_output_size)||!size(v.after_output_size)
    ||!torsoTransferParameters(v.parameters)||!torsoTransferParameters(parameters)||v.parameters.amount!==parameters.amount
    ||!validTorsoBodyRef(v.body_ref,v.source_proof.asset_sha256)||!validTorsoFaceBinding(v.associated_face,v.source_proof.asset_sha256)
    ||!validTorsoTransferImage(v.before)||!validTorsoTransferImage(v.after))return false;
  const source=v.source_proof.creative_source;
  return (!source||source.width===v.source_size[0]&&source.height===v.source_size[1])&&matchesOutput(v.before,v.before_output_size)&&matchesOutput(v.after,v.after_output_size);
}
export function torsoTransferReviewKey(token:string,value:TorsoTransferEvidence):string{
  const image=(v:SpillImage)=>({width:v.width,height:v.height,sha256:v.sha256});
  return JSON.stringify([token,value.document_id,value.revision,value.source_proof,value.before_sha256,value.candidate_sha256,
    value.before_people_sha256,value.candidate_people_sha256,value.source_size,value.before_output_size,value.after_output_size,value.parameters,
    value.body_ref,value.associated_face,value.body_support_sha256,value.body_review_sha256,value.before_bank_sha256,value.candidate_bank_sha256,image(value.before),image(value.after)]);
}
/** A true entry requires verification, both image loads, and this target's explicit checkbox. */
export function torsoTransferImagesReady(token:string,values:(TorsoTransferEvidence|undefined)[],ready:Record<string,boolean>):boolean{
  return values.length<=TORSO_TRANSFER_LIMITS.targets&&values.every(value=>!!value&&ready[torsoTransferReviewKey(token,value)]===true);
}
export function torsoTransferAck(values:TorsoTransferEvidence[]):TorsoTransferAck[]{
  return values.map(value=>({document_id:value.document_id,revision:value.revision,before_sha256:value.before.sha256,after_sha256:value.after.sha256}));
}
export function sameTorsoTransferAck(value:unknown,expected:TorsoTransferAck[]|undefined):value is TorsoTransferAck[]{
  if(!Array.isArray(value)||!expected||value.length!==expected.length||value.length>TORSO_TRANSFER_LIMITS.targets)return false;
  const seen=new Set<string>();
  return value.every((item,index)=>{
    if(!object(item)||!keys(item,['document_id','revision','before_sha256','after_sha256'])||!documentId(item.document_id)||!spillRevision(item.revision)||!hash(item.before_sha256)||!hash(item.after_sha256)||seen.has(item.document_id))return false;
    seen.add(item.document_id);const target=expected[index];
    return item.document_id===target.document_id&&item.revision===target.revision&&item.before_sha256===target.before_sha256&&item.after_sha256===target.after_sha256;
  });
}
export function validTorsoTransferAck(value:unknown,reviews:TorsoTransferEvidence[]):value is TorsoTransferAck[]{
  if(!Array.isArray(value)||value.length!==reviews.length||value.length>TORSO_TRANSFER_LIMITS.targets)return false;
  const expected=new Map(reviews.map(review=>[review.document_id,review]));
  if(expected.size!==reviews.length)return false;
  for(const [index,item] of value.entries()){
    if(!object(item)||!keys(item,['document_id','revision','before_sha256','after_sha256'])||!documentId(item.document_id)||!spillRevision(item.revision)||!hash(item.before_sha256)||!hash(item.after_sha256))return false;
    const review=expected.get(item.document_id);
    if(!review||item.document_id!==reviews[index].document_id||item.revision!==review.revision||item.before_sha256!==review.before.sha256||item.after_sha256!==review.after.sha256)return false;
    expected.delete(item.document_id);
  }
  return expected.size===0;
}
