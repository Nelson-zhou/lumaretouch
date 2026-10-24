// SPDX-License-Identifier: GPL-3.0-or-later
import {validEndpoint,validFaceRef,sameFace,documentId,type PeopleEndpointProof} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {sourceProof} from '../cropTransfer/model';
// Reuse bounded PNG/full-render geometry primitives, not collarbone coverage semantics.
import {validCollarboneVisualForTarget,sameCollarboneAck,type CollarboneVisual,type CollarboneAck} from '../collarbone/transferModel';
export const EYE_BAG_PRESET_OP='lnx.eye_bags.v2';
export type EyeBagPresetCoverage={version:1;support_transfer:'none';targets:{face_ref:FaceRef;scope:'target-reviewed-ridge'|'neutral-no-effect';ridge_sha256:string|null;sides:('left'|'right')[]}[]};
type ReviewBase={preset_sha256:string;applies_sha256:string;load_id:string;owner:PeopleEndpointProof;face_ref:FaceRef;coverage:EyeBagPresetCoverage;visual:CollarboneVisual;replace_legacy:boolean};
export type EyeBagPresetMember={path:string;role:'active'|'sibling';visual:CollarboneVisual};
export type EyeBagPresetReviewV1=ReviewBase&{version:1};
export type EyeBagPresetReviewV2=ReviewBase&{version:2;members:EyeBagPresetMember[];review_sha256:string};
export type EyeBagPresetReview=EyeBagPresetReviewV1|EyeBagPresetReviewV2;
export type EyeBagPresetSingleAck=CollarboneAck&{preset_sha256:string;applies_sha256:string;replace_legacy:boolean};
export type EyeBagPresetAliasAck={review_sha256:string;preset_sha256:string;applies_sha256:string;replace_legacy:boolean;members:CollarboneAck[]};
export type EyeBagPresetAck=EyeBagPresetSingleAck|EyeBagPresetAliasAck;
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const revision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9]\d{0,15})$/.test(v)&&BigInt(v)<BigInt(Number.MAX_SAFE_INTEGER);
export function validEyeBagCoverage(v:unknown,ref:FaceRef):v is EyeBagPresetCoverage{
 if(!object(v)||!keys(v,['version','support_transfer','targets'])||v.version!==1||v.support_transfer!=='none'||!Array.isArray(v.targets)||v.targets.length!==1)return false;
 const row=v.targets[0];if(!object(row)||!keys(row,['face_ref','scope','ridge_sha256','sides'])||!validFaceRef(row.face_ref)||!sameFace(row.face_ref,ref)||!Array.isArray(row.sides)||new Set(row.sides).size!==row.sides.length||row.sides.join('|')!==[...row.sides].sort().join('|')||row.sides.some(side=>side!=='left'&&side!=='right'))return false;
 return row.scope==='neutral-no-effect'?row.ridge_sha256===null&&row.sides.length===0:row.scope==='target-reviewed-ridge'&&hash(row.ridge_sha256)&&row.sides.length>=1&&row.sides.length<=2;
}
export function validEyeBagPreset(v:unknown,loadId:string,currentRevision:unknown,currentSourceProof:unknown,replaceLegacy:unknown):v is EyeBagPresetReview{
 if(!object(v)||!keys(v,['version','preset_sha256','applies_sha256','load_id','owner','face_ref','coverage','visual','replace_legacy',...(v.version===2?['members','review_sha256']:[])])||(v.version!==1&&v.version!==2)
  ||typeof v.replace_legacy!=='boolean'||v.replace_legacy!==replaceLegacy||!hash(v.preset_sha256)||!hash(v.applies_sha256)||v.load_id!==loadId||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)
  ||v.face_ref.asset_sha256!==v.owner.source_proof.asset_sha256||typeof currentRevision!=='string'||String(v.owner.document.revision)!==currentRevision
  ||!sameSpillSourceProof(v.owner.source_proof,currentSourceProof)||!validEyeBagCoverage(v.coverage,v.face_ref)
  ||!validCollarboneVisualForTarget(v.visual,v.owner.document.document_id,currentRevision,v.owner.source_proof))return false;
 if(v.version===1)return true;
 if(v.owner.people_scope!=='project'||!hash(v.review_sha256)||!Array.isArray(v.members)||v.members.length<2||v.members.length>16)return false;
 const ids=new Set<string>(),visual=v.visual,owner=v.owner;
 return v.members.every((member,index)=>{
  if(!object(member)||!keys(member,['path','role','visual'])||typeof member.path!=='string'||!member.path.trim()||member.path.includes('\0')||new TextEncoder().encode(member.path).length>4096
   ||member.role!==(index===0?'active':'sibling')||!object(member.visual)||!documentId(member.visual.document_id)||!revision(member.visual.revision)||!sourceProof(member.visual.source_proof)
   ||!validCollarboneVisualForTarget(member.visual,member.visual.document_id,member.visual.revision,member.visual.source_proof)||ids.has(member.visual.document_id)
   ||member.visual.source_proof.asset_sha256!==owner.source_proof.asset_sha256||canonical(member.visual.source_size)!==canonical(visual.source_size)
   ||member.visual.coverage_sha256!==visual.coverage_sha256||member.visual.before_people_sha256!==visual.before_people_sha256||member.visual.candidate_people_sha256!==visual.candidate_people_sha256
   ||(index===0?canonical(member.visual)!==canonical(visual):member.visual.before_state_sha256!==member.visual.candidate_state_sha256||canonical(member.visual.before_output_size)!==canonical(member.visual.after_output_size)))return false;
  ids.add(member.visual.document_id);return true;
 });
}
export const eyeBagPresetMembers=(v:EyeBagPresetReview):EyeBagPresetMember[]=>v.version===2?v.members:[{path:'',role:'active',visual:v.visual}];
const visualAck=(v:CollarboneVisual):CollarboneAck=>({document_id:v.document_id,revision:v.revision,before_sha256:v.before.sha256,after_sha256:v.after.sha256,coverage_sha256:v.coverage_sha256});
export function eyeBagPresetAck(v:EyeBagPresetReview):EyeBagPresetAck{return v.version===2
 ?{review_sha256:v.review_sha256,preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256,replace_legacy:v.replace_legacy,members:v.members.map(({visual})=>visualAck(visual))}
 :{...visualAck(v.visual),preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256,replace_legacy:v.replace_legacy};}
export function sameEyeBagPresetAck(v:unknown,expected:EyeBagPresetAck|undefined):v is EyeBagPresetAck{
 if(!expected||!object(v)||!keys(v,Object.keys(expected)))return false;
 if('members'in expected)return v.review_sha256===expected.review_sha256&&v.preset_sha256===expected.preset_sha256&&v.applies_sha256===expected.applies_sha256&&v.replace_legacy===expected.replace_legacy&&sameCollarboneAck(v.members,expected.members);
 return Object.keys(v).every(key=>v[key]===expected[key as keyof EyeBagPresetSingleAck]);
}
export const eyeBagPresetKey=(token:string,request:string,id:string,v:EyeBagPresetReview)=>JSON.stringify(['preset:eye-bag-v2',token,request,id,v]);
export const eyeBagPresetMemberKey=(reviewKey:string,member:EyeBagPresetMember)=>JSON.stringify([reviewKey,member]);
function canonical(v:unknown):string{if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(object(v))return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';const s=JSON.stringify(v);if(typeof s!=='string')throw Error('Invalid coverage');return s;}
const digest=async(v:unknown)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(v)))),b=>b.toString(16).padStart(2,'0')).join('');
export async function verifyEyeBagCoverage(v:EyeBagPresetReview):Promise<boolean>{try{
 if(await digest(v.coverage)!==v.visual.coverage_sha256||eyeBagPresetMembers(v).some(member=>member.visual.coverage_sha256!==v.visual.coverage_sha256))return false;
 if(v.version===1)return true;
 const {review_sha256,...review}=v;return await digest(review)===review_sha256;
}catch{return false;}}
/** Exact portable neutral recipe only; never trusts a caller-supplied active flag. */
export function neutralEyeBagPreset(v:unknown):boolean{return object(v)&&keys(v,['recipe'])&&object(v.recipe)&&keys(v.recipe,['version','amount','preserve'])&&v.recipe.version===2&&v.recipe.amount===0&&typeof v.recipe.preserve==='number'&&Number.isFinite(v.recipe.preserve)&&v.recipe.preserve>=0&&v.recipe.preserve<=1;}
