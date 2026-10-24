// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
import {shoulderBinding} from '../shoulderShape/context';
/** The loaded image and the canonical body/people document must agree. */
export function torsoLengthBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),torso=doc?.torso_length?.binding;
 if(!shared)return null;
 if(torso&&(torso.document_id!==shared.document_id||torso.document_epoch!==shared.document_epoch||torso.asset_sha256!==shared.asset_sha256))return null;
 return torso??shared;
}
