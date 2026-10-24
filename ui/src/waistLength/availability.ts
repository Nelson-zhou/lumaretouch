// SPDX-License-Identifier: GPL-3.0-or-later
import type {EngineStatus} from '../native';
import {ANCHORS,check,checkReviewSupport,type Action,type ReviewSupport,type WaistLengthRecipe} from './model.ts';
/** Protocol availability is independent of the optional native deformation core.
 * No preview-only or JavaScript deformation fallback is ever advertised. */
export function waistLengthAvailability(status:Pick<EngineStatus,'ready_caps'>|null){
 const caps=status?.ready_caps,supported=caps?.waist_length_protocol===1;
 return {supported,coreAvailable:supported&&caps?.waist_length_available===true,unavailableReason:caps?.waist_length_unavailable_reason??'配套腰部长度原生核心未就绪，非零调整不可用；仍可复核来源图、查询、停用或重置为 0。'};
}
export function recoveryWithoutCore(action:Action,payload:Record<string,unknown>):boolean{
 if(action==='support_review'){
  try{return Object.keys(payload).sort().join(',')==='data,ownership_confirmed,points_sha256,visible_anchors'&&!!checkReviewSupport(payload.data as ReviewSupport)&&payload.ownership_confirmed===true&&typeof payload.points_sha256==='string'&&/^[a-f0-9]{64}$/.test(payload.points_sha256)&&Array.isArray(payload.visible_anchors)&&payload.visible_anchors.length===ANCHORS.length&&ANCHORS.every((value,index)=>(payload.visible_anchors as unknown[])[index]===value);}catch{return false;}
 }
 if(action==='operation_status')return payload.enabled===false;
 if(action!=='recipe')return false;
 try{return check(payload.recipe as WaistLengthRecipe).amount===0;}catch{return false;}
}
