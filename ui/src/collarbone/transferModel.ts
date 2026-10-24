// SPDX-License-Identifier: GPL-3.0-or-later
import type {PeopleTransferReview,EffectiveSourceProof,CollarboneCoverage} from '../people/transferProof';
import type {SpillImage} from '../spillRemoval/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
export const COLLARBONE_TRANSFER_OP='lnx.collarbone.v1';
export const COLLARBONE_VISUAL_LIMITS={targets:16,edge:1024,pngBytes:4194304,base64:5592408} as const;
export type CollarboneImage=Omit<SpillImage,'base64'>;
export type CollarboneVisual={version:1;document_id:string;revision:string;source_proof:EffectiveSourceProof;
  before_state_sha256:string;candidate_state_sha256:string;before_people_sha256:string;candidate_people_sha256:string;
  source_size:[number,number];before_output_size:[number,number];after_output_size:[number,number];coverage_sha256:string;before:CollarboneImage;after:CollarboneImage};
export type CollarboneAck={document_id:string;revision:string;before_sha256:string;after_sha256:string;coverage_sha256:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const size=(v:unknown):v is [number,number]=>Array.isArray(v)&&v.length===2&&v.every(n=>Number.isSafeInteger(n)&&n>0&&n<=4294967295);
export function validCollarboneImageMetadata(v:unknown):v is CollarboneImage{return object(v)&&keys(v,['mime','width','height','sha256'])&&v.mime==='image/png'&&hash(v.sha256)&&size([v.width,v.height])&&(v.width as number)<=1024&&(v.height as number)<=1024;}
export function validCollarboneImage(v:unknown):v is SpillImage{return object(v)&&keys(v,['mime','width','height','sha256','base64'])&&v.mime==='image/png'&&hash(v.sha256)
  &&size([v.width,v.height])&&(v.width as number)<=1024&&(v.height as number)<=1024&&typeof v.base64==='string'&&v.base64.length<=COLLARBONE_VISUAL_LIMITS.base64
  &&v.base64.length%4===0&&v.base64.startsWith('iVBOR')&&/^[A-Za-z0-9+/]+={0,2}$/.test(v.base64);}
export function validCollarboneVisualForTarget(v:unknown,documentId:string,revision:string,sourceProof:EffectiveSourceProof):v is CollarboneVisual{
  if(!object(v)||!keys(v,['version','document_id','revision','source_proof','before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size','coverage_sha256','before','after'])
    ||v.version!==1||v.document_id!==documentId||v.revision!==revision
    ||!sameSpillSourceProof(v.source_proof,sourceProof)
    ||!['before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256','coverage_sha256'].every(key=>hash(v[key]))
    ||!size(v.source_size)||!size(v.before_output_size)||!size(v.after_output_size)||!validCollarboneImageMetadata(v.before)||!validCollarboneImageMetadata(v.after))return false;
  // Integer products stay below 2^42, exactly representable in JS. Match native/Python ties-to-even.
  const extent=(n:number,edge:number)=>{if(edge<=1024)return n;const product=n*1024,q=Math.floor(product/edge),r=product-q*edge;return Math.max(1,q+(r*2>edge||r*2===edge&&q%2===1?1:0));};
  const matches=(image:CollarboneImage,output:[number,number])=>{const edge=Math.max(...output);return image.width===extent(output[0],edge)&&image.height===extent(output[1],edge);};
  const source=sourceProof.creative_source;
  return (!source||source.width===v.source_size[0]&&source.height===v.source_size[1])&&matches(v.before,v.before_output_size)&&matches(v.after,v.after_output_size);
}
export function validCollarboneVisual(v:unknown,review:PeopleTransferReview):v is CollarboneVisual{return validCollarboneVisualForTarget(v,review.target_document.document_id,String(review.target_document.revision),review.target_owner.source_proof);}
const digest=async(bytes:Uint8Array)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
export async function verifyCollarboneImage(v:SpillImage):Promise<boolean>{try{
  if(!validCollarboneImage(v))return false;const raw=atob(v.base64);if(btoa(raw)!==v.base64||raw.length<33||raw.length>COLLARBONE_VISUAL_LIMITS.pngBytes)return false;
  const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0)),view=new DataView(bytes.buffer);
  return [137,80,78,71,13,10,26,10].every((n,i)=>bytes[i]===n)&&view.getUint32(8)===13&&view.getUint32(12)===0x49484452
    &&view.getUint32(16)===v.width&&view.getUint32(20)===v.height&&await digest(bytes)===v.sha256;
}catch{return false;}}
function canonical(v:unknown):string{if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(object(v))return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';const encoded=JSON.stringify(v);if(typeof encoded!=='string')throw Error('Invalid coverage value');return encoded;}
export async function verifyCollarboneCoverage(v:CollarboneVisual,coverage:CollarboneCoverage):Promise<boolean>{try{return await digest(new TextEncoder().encode(canonical(coverage)))===v.coverage_sha256;}catch{return false;}}
export function collarboneReviewKey(token:string,v:CollarboneVisual):string{return JSON.stringify([COLLARBONE_TRANSFER_OP,token,{...v,before:{...v.before,base64:undefined},after:{...v.after,base64:undefined}}]);}
export function collarboneImagesReady(token:string,values:(CollarboneVisual|undefined)[],ready:Record<string,boolean>):boolean{return values.length<=16&&values.every(v=>!!v&&ready[collarboneReviewKey(token,v)]===true);}
export function collarboneAck(values:CollarboneVisual[]):CollarboneAck[]{return values.map(v=>({document_id:v.document_id,revision:v.revision,before_sha256:v.before.sha256,after_sha256:v.after.sha256,coverage_sha256:v.coverage_sha256}));}
export function sameCollarboneAck(v:unknown,expected:CollarboneAck[]|undefined):v is CollarboneAck[]{
  if(!Array.isArray(v)||!expected||v.length!==expected.length||v.length>16||new Set(expected.map(x=>x.document_id)).size!==expected.length)return false;
  return v.every((row,i)=>object(row)&&keys(row,['document_id','revision','before_sha256','after_sha256','coverage_sha256'])&&Object.keys(row).every(k=>row[k]===expected[i][k as keyof CollarboneAck]));
}
export const validCollarboneAck=(v:unknown,reviews:CollarboneVisual[])=>sameCollarboneAck(v,collarboneAck(reviews));
