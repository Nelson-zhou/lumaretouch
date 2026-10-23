// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
import {shoulderBinding} from '../shoulderShape/context';
/** Load identity is not persistent document identity. Both body views must agree. */
export function legBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),leg=doc?.leg_shape?.binding;
 if(!shared)return null;
 if(leg&&(leg.document_id!==shared.document_id||leg.document_epoch!==shared.document_epoch||leg.asset_sha256!==shared.asset_sha256))return null;
 return leg??shared;
}
