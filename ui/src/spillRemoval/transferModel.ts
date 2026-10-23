import {sourceProof} from '../cropTransfer/model.ts';
import type {EffectiveSourceProof} from '../people/transferProof';
import {spillRevision,verifySpillImage,type SpillImage,type SpillParameters} from './model.ts';

export const SPILL_TRANSFER_OP='lnx.spill_removal.v1';
export const SPILL_TRANSFER_LIMITS={targets:8,edge:256,base64:200000,dimension:4294967295} as const;
/** Display-only samples of each target's full-resolution canonical render. */
export type SpillTransferEvidence={
  version:1;document_id:string;revision:string;source_proof:EffectiveSourceProof;
  before_sha256:string;candidate_sha256:string;before_people_sha256:string;candidate_people_sha256:string;
  source_size:[number,number];before_output_size:[number,number];after_output_size:[number,number];
  parameters:SpillParameters;before:SpillImage;after:SpillImage;
};
export type SpillTransferAck={document_id:string;revision:string;before_sha256:string;after_sha256:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
// Presets use Engine load IDs, while batch rows are additionally UUID-checked by their workflow.
const documentId=(v:unknown):v is string=>typeof v==='string'&&v.length>0&&v.length<=128&&!/[\u0000-\u001f\u007f]/.test(v);
const dimension=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>0&&v<=SPILL_TRANSFER_LIMITS.dimension;
const size=(v:unknown):v is [number,number]=>Array.isArray(v)&&v.length===2&&v.every(dimension);
export function spillTransferParameters(v:unknown):v is SpillParameters{
  return object(v)&&keys(v,['enabled','strength'])&&typeof v.enabled==='boolean'
    &&typeof v.strength==='number'&&Number.isFinite(v.strength)&&v.strength>=0&&v.strength<=100;
}
export function sameSpillSourceProof(a:unknown,b:unknown):boolean{
  return sourceProof(a)&&sourceProof(b)&&a.asset_sha256===b.asset_sha256&&a.original_sha256===b.original_sha256
    &&(a.creative_source===null?b.creative_source===null:b.creative_source!==null
      &&a.creative_source.sha256===b.creative_source.sha256&&a.creative_source.width===b.creative_source.width
      &&a.creative_source.height===b.creative_source.height);
}
export function validSpillTransferImage(v:unknown):v is SpillImage{
  return object(v)&&keys(v,['mime','width','height','sha256','base64'])&&v.mime==='image/png'&&hash(v.sha256)
    &&dimension(v.width)&&dimension(v.height)&&v.width<=SPILL_TRANSFER_LIMITS.edge&&v.height<=SPILL_TRANSFER_LIMITS.edge
    &&typeof v.base64==='string'&&v.base64.length<=SPILL_TRANSFER_LIMITS.base64&&v.base64.length%4===0
    &&v.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);
}
function matchesOutput(image:SpillImage,output:[number,number]):boolean{
  return image.width<=output[0]&&image.height<=output[1]
    &&Math.abs(image.width*output[1]-image.height*output[0])<=Math.max(...output);
}
export function validSpillTransfer(v:unknown,id:string,revision:string|undefined,parameters:unknown,expectedSource:unknown):v is SpillTransferEvidence{
  if(!object(v)||!keys(v,['version','document_id','revision','source_proof','before_sha256','candidate_sha256',
    'before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size','parameters','before','after'])
    ||v.version!==1||!documentId(v.document_id)||v.document_id!==id||!spillRevision(v.revision)||v.revision!==revision
    ||!sourceProof(v.source_proof)||!sameSpillSourceProof(v.source_proof,expectedSource)
    ||!hash(v.before_sha256)||!hash(v.candidate_sha256)||!hash(v.before_people_sha256)||!hash(v.candidate_people_sha256)
    ||!size(v.source_size)||!size(v.before_output_size)||!size(v.after_output_size)
    ||!spillTransferParameters(v.parameters)||!spillTransferParameters(parameters)
    ||v.parameters.enabled!==parameters.enabled||v.parameters.strength!==parameters.strength
    ||!validSpillTransferImage(v.before)||!validSpillTransferImage(v.after))return false;
  const source=v.source_proof.creative_source;
  return (!source||source.width===v.source_size[0]&&source.height===v.source_size[1])
    &&matchesOutput(v.before,v.before_output_size)&&matchesOutput(v.after,v.after_output_size);
}
/** PNG bytes, signature and IHDR dimensions are checked before a browser load can qualify. */
export async function verifySpillTransferImage(image:SpillImage):Promise<boolean>{
  return validSpillTransferImage(image)&&await verifySpillImage(image);
}
export function spillTransferReviewKey(token:string,value:SpillTransferEvidence):string{
  const image=(v:SpillImage)=>({width:v.width,height:v.height,sha256:v.sha256});
  return JSON.stringify([token,value.document_id,value.revision,value.source_proof,value.before_sha256,value.candidate_sha256,
    value.before_people_sha256,value.candidate_people_sha256,value.source_size,value.before_output_size,value.after_output_size,
    value.parameters,image(value.before),image(value.after)]);
}
/** A true entry means both decoded images were verified and the user checked this target. */
export function spillTransferImagesReady(token:string,values:(SpillTransferEvidence|undefined)[],ready:Record<string,boolean>):boolean{
  return values.length<=SPILL_TRANSFER_LIMITS.targets&&values.every(value=>!!value&&ready[spillTransferReviewKey(token,value)]===true);
}
export function spillTransferAck(values:SpillTransferEvidence[]):SpillTransferAck[]{
  return values.map(value=>({document_id:value.document_id,revision:value.revision,before_sha256:value.before.sha256,after_sha256:value.after.sha256}));
}
export function validSpillTransferAck(value:unknown,reviews:SpillTransferEvidence[]):value is SpillTransferAck[]{
  if(!Array.isArray(value)||value.length!==reviews.length||value.length>SPILL_TRANSFER_LIMITS.targets)return false;
  const expected=new Map(reviews.map(review=>[review.document_id,review]));
  if(expected.size!==reviews.length)return false;
  for(const [index,item] of value.entries()){
    if(!object(item)||!keys(item,['document_id','revision','before_sha256','after_sha256'])
      ||!documentId(item.document_id)||!spillRevision(item.revision)||!hash(item.before_sha256)||!hash(item.after_sha256))return false;
    const review=expected.get(item.document_id);
    if(!review||item.document_id!==reviews[index].document_id||item.revision!==review.revision||item.before_sha256!==review.before.sha256||item.after_sha256!==review.after.sha256)return false;
    expected.delete(item.document_id);
  }
  return expected.size===0;
}
