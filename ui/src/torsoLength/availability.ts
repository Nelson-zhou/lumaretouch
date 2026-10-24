// SPDX-License-Identifier: GPL-3.0-or-later
import type {EngineStatus} from '../native';
import {check,type Action,type TorsoLengthRecipe} from './model';
/** Protocol availability is independent of the optional native deformation core.
 * No preview-only or JavaScript deformation fallback is ever advertised. */
export function torsoAvailability(status:Pick<EngineStatus,'ready_caps'>|null){
 const caps=status?.ready_caps,supported=caps?.torso_length_protocol===1;
 return {supported,coreAvailable:supported&&caps?.torso_length_available===true,unavailableReason:caps?.torso_length_unavailable_reason??'配套上身长度原生核心未就绪，非零调整不可用；仍可查询、停用或重置为 0。'};
}
export function recoveryWithoutCore(action:Action,payload:Record<string,unknown>):boolean{
 if(action==='operation_status')return payload.enabled===false;
 if(action!=='recipe')return false;
 try{return check(payload.recipe as TorsoLengthRecipe).amount===0;}catch{return false;}
}
