// SPDX-License-Identifier: GPL-3.0-or-later
import {validEndpoint,validFaceRef,sameFace,type PeopleEndpointProof} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
// Reuse bounded PNG/full-render geometry primitives, not collarbone coverage semantics.
import {validCollarboneVisualForTarget,type CollarboneVisual} from '../collarbone/transferModel';
export const EYE_BAG_PRESET_OP='lnx.eye_bags.v2';
export type EyeBagPresetCoverage={version:1;support_transfer:'none';targets:{face_ref:FaceRef;scope:'target-reviewed-ridge'|'neutral-no-effect';ridge_sha256:string|null;sides:('left'|'right')[]}[]};
export type EyeBagPresetReview={version:1;preset_sha256:string;applies_sha256:string;load_id:string;owner:PeopleEndpointProof;face_ref:FaceRef;coverage:EyeBagPresetCoverage;visual:CollarboneVisual;replace_legacy:boolean};
export type EyeBagPresetAck={document_id:string;revision:string;before_sha256:string;after_sha256:string;coverage_sha256:string;preset_sha256:string;applies_sha256:string;replace_legacy:boolean};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function validEyeBagCoverage(v:unknown,ref:FaceRef):v is EyeBagPresetCoverage{
 if(!object(v)||!keys(v,['version','support_transfer','targets'])||v.version!==1||v.support_transfer!=='none'||!Array.isArray(v.targets)||v.targets.length!==1)return false;
 const row=v.targets[0];if(!object(row)||!keys(row,['face_ref','scope','ridge_sha256','sides'])||!validFaceRef(row.face_ref)||!sameFace(row.face_ref,ref)||!Array.isArray(row.sides)||new Set(row.sides).size!==row.sides.length||row.sides.join('|')!==[...row.sides].sort().join('|')||row.sides.some(side=>side!=='left'&&side!=='right'))return false;
 return row.scope==='neutral-no-effect'?row.ridge_sha256===null&&row.sides.length===0:row.scope==='target-reviewed-ridge'&&hash(row.ridge_sha256)&&row.sides.length>=1&&row.sides.length<=2;
}
export function validEyeBagPreset(v:unknown,loadId:string,revision:unknown,sourceProof:unknown,replaceLegacy:unknown):v is EyeBagPresetReview{
 if(!object(v)||!keys(v,['version','preset_sha256','applies_sha256','load_id','owner','face_ref','coverage','visual','replace_legacy'])||v.version!==1
  ||typeof v.replace_legacy!=='boolean'||v.replace_legacy!==replaceLegacy||!hash(v.preset_sha256)||!hash(v.applies_sha256)||v.load_id!==loadId||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)
  ||v.face_ref.asset_sha256!==v.owner.source_proof.asset_sha256||typeof revision!=='string'||String(v.owner.document.revision)!==revision
  ||!sameSpillSourceProof(v.owner.source_proof,sourceProof)||!validEyeBagCoverage(v.coverage,v.face_ref))return false;
 return validCollarboneVisualForTarget(v.visual,v.owner.document.document_id,revision,v.owner.source_proof);
}
export function eyeBagPresetAck(v:EyeBagPresetReview):EyeBagPresetAck{return {document_id:v.visual.document_id,revision:v.visual.revision,before_sha256:v.visual.before.sha256,after_sha256:v.visual.after.sha256,
 coverage_sha256:v.visual.coverage_sha256,preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256,replace_legacy:v.replace_legacy};}
export function sameEyeBagPresetAck(v:unknown,expected:EyeBagPresetAck|undefined):v is EyeBagPresetAck{return !!expected&&object(v)&&keys(v,Object.keys(expected))&&Object.keys(v).every(key=>v[key]===expected[key as keyof EyeBagPresetAck]);}
export const eyeBagPresetKey=(token:string,request:string,id:string,v:EyeBagPresetReview)=>JSON.stringify(['preset:eye-bag-v2',token,request,id,v]);
function canonical(v:unknown):string{if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(object(v))return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';const s=JSON.stringify(v);if(typeof s!=='string')throw Error('Invalid coverage');return s;}
export async function verifyEyeBagCoverage(v:EyeBagPresetReview):Promise<boolean>{try{return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(v.coverage)))),b=>b.toString(16).padStart(2,'0')).join('')===v.visual.coverage_sha256;}catch{return false;}}

/** Exact portable neutral recipe only; never trusts a caller-supplied active flag. */
export function neutralEyeBagPreset(v:unknown):boolean{return object(v)&&keys(v,['recipe'])&&object(v.recipe)&&keys(v.recipe,['version','amount','preserve'])&&v.recipe.version===2&&v.recipe.amount===0&&typeof v.recipe.preserve==='number'&&Number.isFinite(v.recipe.preserve)&&v.recipe.preserve>=0&&v.recipe.preserve<=1;}
