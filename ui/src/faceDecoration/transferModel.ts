// SPDX-License-Identifier: GPL-3.0-or-later
import {validEndpoint,validFaceRef,sameFace,type PeopleEndpointProof,type EffectiveSourceProof} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneVisualForTarget,collarboneAck,sameCollarboneAck,type CollarboneVisual,type CollarboneAck} from '../collarbone/transferModel';
import {canonical,OP} from './model';
export {OP};
export type DecorationCoverage={version:1;support_transfer:'none';targets:{face_ref:FaceRef;scope:'target-reviewed-visible-skin'|'neutral-no-effect';visibility_sha256:string|null;recipe_sha256:string}[]};
export type DecorationVisual=CollarboneVisual;
export type DecorationAck=CollarboneAck;
export type DecorationPreset={version:1;preset_sha256:string;applies_sha256:string;load_id:string;owner:PeopleEndpointProof;face_ref:FaceRef;coverage:DecorationCoverage;visual:DecorationVisual};
export type DecorationPresetAck=DecorationAck&{preset_sha256:string;applies_sha256:string};
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
export function validDecorationPreset(v:unknown,loadId:string,revision:unknown,source:unknown):v is DecorationPreset{
 if(!object(v)||!keys(v,['version','preset_sha256','applies_sha256','load_id','owner','face_ref','coverage','visual'])||v.version!==1||!hash(v.preset_sha256)||!hash(v.applies_sha256)||v.load_id!==loadId||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)||typeof revision!=='string'||String(v.owner.document.revision)!==revision||!sameSpillSourceProof(v.owner.source_proof,source)||!validDecorationCoverage(v.coverage,v.owner.source_proof))return false;
 return v.face_ref.asset_sha256===v.owner.source_proof.asset_sha256&&v.coverage.targets.some(row=>sameFace(row.face_ref,v.face_ref))&&validCollarboneVisualForTarget(v.visual,v.owner.document.document_id,revision,v.owner.source_proof);
}
export function decorationPresetAck(v:DecorationPreset):DecorationPresetAck{return {...decorationAck([v.visual])[0],preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256};}
export function sameDecorationPresetAck(v:unknown,expected:DecorationPresetAck|undefined):v is DecorationPresetAck{return !!expected&&object(v)&&keys(v,['document_id','revision','before_sha256','after_sha256','coverage_sha256','preset_sha256','applies_sha256'])&&Object.keys(v).every(k=>v[k]===expected[k as keyof DecorationPresetAck]);}
export const decorationPresetKey=(token:string,request:string,id:string,v:DecorationPreset)=>JSON.stringify(['preset:face-decoration',token,request,id,v]);

/** Independent support proofs may differ; complete image/state/source proofs may not. */
export function sameDecorationRender(left:DecorationVisual,right:DecorationVisual):boolean{
 const {coverage_sha256:_a,...a}=left,{coverage_sha256:_b,...b}=right;return canonical(a)===canonical(b);
}
