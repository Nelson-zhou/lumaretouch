// SPDX-License-Identifier: GPL-3.0-or-later
import {validEndpoint,validFaceRef,sameFace,documentId,type PeopleEndpointProof,type EffectiveSourceProof} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {sourceProof} from '../cropTransfer/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneVisualForTarget,collarboneAck,sameCollarboneAck,type CollarboneVisual,type CollarboneAck} from '../collarbone/transferModel';
import {canonical,OP} from './model';
export {OP};
export type DecorationCoverage={version:1;support_transfer:'none';targets:{face_ref:FaceRef;scope:'target-reviewed-visible-skin'|'neutral-no-effect';visibility_sha256:string|null;recipe_sha256:string}[]};
export type DecorationVisual=CollarboneVisual;
export type DecorationAck=CollarboneAck;
type DecorationPresetBase={preset_sha256:string;applies_sha256:string;load_id:string;owner:PeopleEndpointProof;face_ref:FaceRef;coverage:DecorationCoverage;visual:DecorationVisual};
export type DecorationPresetMember={path:string;role:'active'|'sibling';visual:DecorationVisual};
export type DecorationPresetV1=DecorationPresetBase&{version:1};
export type DecorationPresetV2=DecorationPresetBase&{version:2;members:DecorationPresetMember[];review_sha256:string;before_bank_sha256:string};
export type DecorationPreset=DecorationPresetV1|DecorationPresetV2;
export type DecorationPresetSingleAck=DecorationAck&{preset_sha256:string;applies_sha256:string};
export type DecorationPresetAliasAck={review_sha256:string;preset_sha256:string;applies_sha256:string;members:DecorationAck[]};
export type DecorationPresetAck=DecorationPresetSingleAck|DecorationPresetAliasAck;
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function validDecorationCoverage(v:unknown,source:EffectiveSourceProof):v is DecorationCoverage{
 if(!object(v)||!keys(v,['version','support_transfer','targets'])||v.version!==1||v.support_transfer!=='none'||!Array.isArray(v.targets)||!v.targets.length||v.targets.length>64)return false;
 let previous='';
 return v.targets.every(row=>{
  if(!object(row)||!keys(row,['face_ref','scope','visibility_sha256','recipe_sha256'])||!validFaceRef(row.face_ref)||row.face_ref.asset_sha256!==source.asset_sha256||!hash(row.recipe_sha256)||row.face_ref.face_instance_id<=previous)return false;
  previous=row.face_ref.face_instance_id;
  return row.scope==='neutral-no-effect'?row.visibility_sha256===null:row.scope==='target-reviewed-visible-skin'&&hash(row.visibility_sha256);
 });
}
export function validDecorationEvidence(v:unknown,document:string,revision:string,source:EffectiveSourceProof):v is {face_decoration_coverage:DecorationCoverage;face_decoration_visual:DecorationVisual}{
 return object(v)&&validDecorationCoverage(v.face_decoration_coverage,source)&&validCollarboneVisualForTarget(v.face_decoration_visual,document,revision,source);
}
export async function verifyDecorationCoverage(visual:DecorationVisual,coverage:DecorationCoverage):Promise<boolean>{try{
 const bytes=new TextEncoder().encode(canonical(coverage));
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
 return digest===visual.coverage_sha256;
}catch{return false;}}
export const decorationAck=(values:DecorationVisual[]):DecorationAck[]=>collarboneAck(values);
export const sameDecorationAck=(v:unknown,expected:DecorationAck[]|undefined):v is DecorationAck[]=>sameCollarboneAck(v,expected);
export const decorationKey=(token:string,value:DecorationVisual)=>JSON.stringify([OP,token,value]);
export function decorationImagesReady(token:string,values:(DecorationVisual|undefined)[],ready:Record<string,boolean>):boolean{return values.length>0&&values.length<=16&&values.every(v=>!!v&&ready[decorationKey(token,v)]===true);}
export function validDecorationPreset(v:unknown,loadId:string,currentRevision:unknown,source:unknown):v is DecorationPreset{
 if(!object(v)||!keys(v,['version','preset_sha256','applies_sha256','load_id','owner','face_ref','coverage','visual',...(v.version===2?['members','review_sha256','before_bank_sha256']:[])])||(v.version!==1&&v.version!==2)
  ||!hash(v.preset_sha256)||!hash(v.applies_sha256)||v.load_id!==loadId||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)||typeof currentRevision!=='string'
  ||String(v.owner.document.revision)!==currentRevision||!sameSpillSourceProof(v.owner.source_proof,source)||!validDecorationCoverage(v.coverage,v.owner.source_proof)
  ||v.face_ref.asset_sha256!==v.owner.source_proof.asset_sha256||!v.coverage.targets.some(row=>sameFace(row.face_ref,v.face_ref))
  ||!validCollarboneVisualForTarget(v.visual,v.owner.document.document_id,currentRevision,v.owner.source_proof))return false;
 if(v.version===1)return true;
 if(v.owner.people_scope!=='project'||!hash(v.review_sha256)||!hash(v.before_bank_sha256)||!Array.isArray(v.members)||v.members.length<2||v.members.length>16)return false;
 const ids=new Set<string>(),visual=v.visual,owner=v.owner;
 return v.members.every((member,index)=>{
  if(!object(member)||!keys(member,['path','role','visual'])||typeof member.path!=='string'||!member.path.trim()||member.path.includes('\0')||new TextEncoder().encode(member.path).length>4096
   ||member.role!==(index===0?'active':'sibling')||!object(member.visual)||!documentId(member.visual.document_id)||typeof member.visual.revision!=='string'
   ||!/^(0|[1-9]\d{0,15})$/.test(member.visual.revision)||BigInt(member.visual.revision)>=BigInt(Number.MAX_SAFE_INTEGER)||!sourceProof(member.visual.source_proof)
   ||!validCollarboneVisualForTarget(member.visual,member.visual.document_id,member.visual.revision,member.visual.source_proof)||ids.has(member.visual.document_id)
   ||member.visual.source_proof.asset_sha256!==owner.source_proof.asset_sha256||canonical(member.visual.source_size)!==canonical(visual.source_size)
   ||member.visual.coverage_sha256!==visual.coverage_sha256||member.visual.before_people_sha256!==visual.before_people_sha256||member.visual.candidate_people_sha256!==visual.candidate_people_sha256
   ||(index===0?canonical(member.visual)!==canonical(visual):member.visual.before_state_sha256!==member.visual.candidate_state_sha256||canonical(member.visual.before_output_size)!==canonical(member.visual.after_output_size)))return false;
  ids.add(member.visual.document_id);return true;
 });
}
export const decorationPresetMembers=(v:DecorationPreset):DecorationPresetMember[]=>v.version===2?v.members:[{path:'',role:'active',visual:v.visual}];
export function decorationPresetAck(v:DecorationPreset):DecorationPresetAck{return v.version===2
 ?{review_sha256:v.review_sha256,preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256,members:decorationAck(v.members.map(member=>member.visual))}
 :{...decorationAck([v.visual])[0],preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256};}
export function sameDecorationPresetAck(v:unknown,expected:DecorationPresetAck|undefined):v is DecorationPresetAck{
 if(!expected||!object(v)||!keys(v,Object.keys(expected)))return false;
 if('members'in expected)return v.review_sha256===expected.review_sha256&&v.preset_sha256===expected.preset_sha256&&v.applies_sha256===expected.applies_sha256&&sameDecorationAck(v.members,expected.members);
 return Object.keys(v).every(k=>v[k]===expected[k as keyof DecorationPresetSingleAck]);
}
export const decorationPresetKey=(token:string,request:string,id:string,v:DecorationPreset)=>JSON.stringify(['preset:face-decoration',token,request,id,v]);
export const decorationPresetMemberKey=(reviewKey:string,member:DecorationPresetMember)=>JSON.stringify([reviewKey,member]);
export async function verifyDecorationPreset(v:DecorationPreset):Promise<boolean>{try{
 if(!await verifyDecorationCoverage(v.visual,v.coverage)||decorationPresetMembers(v).some(member=>member.visual.coverage_sha256!==v.visual.coverage_sha256))return false;
 if(v.version===1)return true;
 const {review_sha256,...review}=v,bytes=new TextEncoder().encode(canonical(review));
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
 return digest===review_sha256;
}catch{return false;}}

/** Independent support proofs may differ; complete image/state/source proofs may not. */
export function sameDecorationRender(left:DecorationVisual,right:DecorationVisual):boolean{
 const {coverage_sha256:_a,...a}=left,{coverage_sha256:_b,...b}=right;return canonical(a)===canonical(b);
}
