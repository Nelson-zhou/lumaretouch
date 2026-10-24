// SPDX-License-Identifier: GPL-3.0-or-later
import {validCollarboneVisualForTarget,type CollarboneImage} from '../collarbone/transferModel';
import {sourceProof} from '../cropTransfer/model';
import {validFaceRef} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import type {FaceStyleVisual} from '../faceStyle/model';
import type {RecoveryAliasMarker} from './aliasHistoryRegistry';
export type RecoveryAliasMember={path:string;visual:FaceStyleVisual};
export type RecoveryAliasReview={version:2;token:string;target:'eye_bag_preserve';face_ref:FaceRef;
  before_recovery_sha256:string|null;recovery_sha256:string|null;visual:FaceStyleVisual;members:RecoveryAliasMember[];review_sha256:string};
export type RecoveryAliasAck={review_sha256:string;members:{document_id:string;revision:string;before_sha256:string;after_sha256:string}[]};
export type RecoveryAliasImageRequest={previewId:string;captureId:string;ticket:string;requestId:string;reviewSha256:string;
  memberDocumentId:string;memberRevision:string;side:'before'|'after';sha256:string};
export const recoveryObject=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const identity=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
export const recoveryRevision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9]\d{0,15})$/.test(v)&&BigInt(v)<BigInt(Number.MAX_SAFE_INTEGER);
const resultRevision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9]\d{0,15})$/.test(v)&&BigInt(v)<=BigInt(Number.MAX_SAFE_INTEGER);
export function recoveryCanonical(v:unknown):string{if(Array.isArray(v))return '['+v.map(recoveryCanonical).join(',')+']';
  if(recoveryObject(v))return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+recoveryCanonical(v[k])).join(',')+'}';
  const s=JSON.stringify(v);if(typeof s!=='string')throw Error('Invalid recovery review');return s;}
function validVisual(v:unknown):v is FaceStyleVisual{
  if(!recoveryObject(v)||!keys(v,['version','document_id','revision','source_proof','before_state_sha256','candidate_state_sha256',
    'before_people_sha256','candidate_people_sha256','source_size','before_output_size','after_output_size','before','after'])
    ||!identity(v.document_id)||!recoveryRevision(v.revision)||!sourceProof(v.source_proof))return false;
  return validCollarboneVisualForTarget({...v,coverage_sha256:'0'.repeat(64)},v.document_id,v.revision,v.source_proof)
    &&v.before_state_sha256===v.candidate_state_sha256&&recoveryCanonical(v.before_output_size)===recoveryCanonical(v.after_output_size);
}
/** All members retain their own recipe/geometry, and only the same shared people graph changes. */
export function validRecoveryAliasReview(v:unknown,documentId:string):v is RecoveryAliasReview{
  if(!recoveryObject(v)||!keys(v,['version','token','target','face_ref','before_recovery_sha256','recovery_sha256','visual','members','review_sha256'])
    ||v.version!==2||!identity(v.token)||v.target!=='eye_bag_preserve'||!validFaceRef(v.face_ref)||!hash(v.review_sha256)
    ||!(v.before_recovery_sha256===null||hash(v.before_recovery_sha256))||!(v.recovery_sha256===null||hash(v.recovery_sha256))
    ||!validVisual(v.visual)||v.visual.document_id!==documentId||v.face_ref.asset_sha256!==v.visual.source_proof.asset_sha256
    ||!Array.isArray(v.members)||v.members.length<2||v.members.length>16)return false;
  const seen=new Set<string>(),visual=v.visual;
  return v.members.every((member,index)=>{if(!recoveryObject(member)||!keys(member,['path','visual'])||typeof member.path!=='string'
    ||!member.path.trim()||/[\u0000-\u001f\u007f]/.test(member.path)||new TextEncoder().encode(member.path).length>4096||!validVisual(member.visual)
    ||seen.has(member.visual.document_id)||member.visual.source_proof.asset_sha256!==visual.source_proof.asset_sha256
    ||recoveryCanonical(member.visual.source_size)!==recoveryCanonical(visual.source_size)
    ||member.visual.before_people_sha256!==visual.before_people_sha256||member.visual.candidate_people_sha256!==visual.candidate_people_sha256
    ||index===0&&recoveryCanonical(member.visual)!==recoveryCanonical(visual))return false;
    seen.add(member.visual.document_id);return true;});
}
export async function verifyRecoveryAliasReview(review:RecoveryAliasReview):Promise<boolean>{try{const {review_sha256,...body}=review;
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(recoveryCanonical(body)));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('')===review_sha256;}catch{return false;}}
export const recoveryAliasAck=(review:RecoveryAliasReview):RecoveryAliasAck=>({review_sha256:review.review_sha256,
  members:review.members.map(({visual})=>({document_id:visual.document_id,revision:visual.revision,before_sha256:visual.before.sha256,after_sha256:visual.after.sha256}))});
export const sameRecoveryAliasAck=(v:unknown,expected:RecoveryAliasAck)=>recoveryCanonical(v)===recoveryCanonical(expected);
export const recoveryAliasMarker=(review:RecoveryAliasReview):RecoveryAliasMarker=>({version:1,review_sha256:review.review_sha256,member_count:review.members.length});
export const recoveryAliasMemberKey=(preview:string,review:RecoveryAliasReview,member:RecoveryAliasMember)=>recoveryCanonical([preview,review.review_sha256,member]);
export function validRecoveryAliasMembers(value:unknown,review:RecoveryAliasReview):boolean{return Array.isArray(value)&&value.length===review.members.length
  &&value.every((member,index)=>{const visual=review.members[index].visual;return recoveryObject(member)&&keys(member,['document_id','expected_revision','result_revision'])
    &&member.document_id===visual.document_id&&member.expected_revision===visual.revision&&resultRevision(member.result_revision)
    &&BigInt(member.result_revision)===BigInt(visual.revision)+1n;});}
export type RecoveryAliasExpectedImage=CollarboneImage;
