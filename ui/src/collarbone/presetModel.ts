// SPDX-License-Identifier: GPL-3.0-or-later
import {validEndpoint,validFaceRef,validCollarboneCoverage,sameFace,type PeopleEndpointProof,type CollarboneCoverage} from '../people/transferProof';
import type {FaceRef} from '../people/model';
import {sameSpillSourceProof} from '../spillRemoval/transferModel';
import {validCollarboneVisualForTarget,type CollarboneVisual} from './transferModel';
export {COLLARBONE_TRANSFER_OP as COLLARBONE_PRESET_OP} from './transferModel';
export type CollarbonePresetReview={version:1;preset_sha256:string;applies_sha256:string;load_id:string;owner:PeopleEndpointProof;face_ref:FaceRef;coverage:CollarboneCoverage;visual:CollarboneVisual};
export type CollarbonePresetAck={document_id:string;revision:string;before_sha256:string;after_sha256:string;coverage_sha256:string;preset_sha256:string;applies_sha256:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const keys=(v:Record<string,unknown>,names:string[])=>Object.keys(v).sort().join('|')===[...names].sort().join('|');
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function validCollarbonePreset(v:unknown,loadId:string,revision:unknown,sourceProof:unknown):v is CollarbonePresetReview{
 if(!object(v)||!keys(v,['version','preset_sha256','applies_sha256','load_id','owner','face_ref','coverage','visual'])||v.version!==1
  ||!hash(v.preset_sha256)||!hash(v.applies_sha256)||v.load_id!==loadId||!validEndpoint(v.owner)||!validFaceRef(v.face_ref)
  ||v.face_ref.asset_sha256!==v.owner.source_proof.asset_sha256||typeof revision!=='string'||String(v.owner.document.revision)!==revision
  ||!sameSpillSourceProof(v.owner.source_proof,sourceProof)||!validCollarboneCoverage(v.coverage,[v.face_ref]))return false;
 return validCollarboneVisualForTarget(v.visual,v.owner.document.document_id,revision,v.owner.source_proof)
  &&v.coverage.targets.length===1&&sameFace(v.coverage.targets[0].face_ref,v.face_ref);
}
export function collarbonePresetAck(v:CollarbonePresetReview):CollarbonePresetAck{return {
 document_id:v.visual.document_id,revision:v.visual.revision,before_sha256:v.visual.before.sha256,after_sha256:v.visual.after.sha256,
 coverage_sha256:v.visual.coverage_sha256,preset_sha256:v.preset_sha256,applies_sha256:v.applies_sha256};}
export function sameCollarbonePresetAck(value:unknown,expected:CollarbonePresetAck|undefined):value is CollarbonePresetAck{
 return !!expected&&object(value)&&keys(value,['document_id','revision','before_sha256','after_sha256','coverage_sha256','preset_sha256','applies_sha256'])
  &&Object.keys(value).every(key=>value[key]===expected[key as keyof CollarbonePresetAck]);
}
export function collarbonePresetKey(token:string,request:string,id:string,v:CollarbonePresetReview):string{
 return JSON.stringify(['preset:collarbone',token,request,id,v]);
}
