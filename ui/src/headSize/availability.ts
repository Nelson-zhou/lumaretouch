// SPDX-License-Identifier: GPL-3.0-or-later
import type {EngineStatus} from '../native';
import {ANCHORS,check,checkReviewSupport,type Action,type HeadSizeRecipe,type ReviewSupport} from './model.ts';
/** Review persistence is distinct from actual native image publication. */
export function headSizeAvailability(status:Pick<EngineStatus,'ready_caps'>|null){
 const caps=status?.ready_caps,supported=caps?.head_size_protocol===1;
 return {supported,coreAvailable:supported&&caps?.head_size_available===true,unavailableReason:caps?.head_size_unavailable_reason??'配套小头原生核心未就绪。可独立复核、查询、停用或归零；非零调整与启用不可用。'};
}
export function recoveryWithoutCore(action:Action,payload:Record<string,unknown>):boolean{
 if(action==='support_review'){
  try{return Object.keys(payload).sort().join(',')==='data,ownership_confirmed,points_sha256,visible_anchors'&&!!checkReviewSupport(payload.data as ReviewSupport)&&payload.ownership_confirmed===true&&typeof payload.points_sha256==='string'&&/^[a-f0-9]{64}$/.test(payload.points_sha256)&&Array.isArray(payload.visible_anchors)&&payload.visible_anchors.length===ANCHORS.length&&ANCHORS.every((value,index)=>(payload.visible_anchors as unknown[])[index]===value);}catch{return false;}
 }
 if(action==='operation_status')return Object.keys(payload).join(',')==='enabled'&&payload.enabled===false;
 if(action!=='recipe')return false;
 try{return check(payload.recipe as HeadSizeRecipe).amount===0;}catch{return false;}
}
