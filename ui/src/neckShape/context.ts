// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
import {shoulderBinding} from '../shoulderShape/context';
/** Load identity is not persistent document identity. Both body views must agree. */
export function neckBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),neck=doc?.neck_shape?.binding;
 if(!shared)return null;
 if(neck&&(neck.document_id!==shared.document_id||neck.document_epoch!==shared.document_epoch||neck.asset_sha256!==shared.asset_sha256))return null;
 return neck??shared;
}
