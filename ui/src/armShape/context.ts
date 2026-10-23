// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import {shoulderBinding} from '../shoulderShape/context';
import type {Binding} from './model';
export function armBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),arm=doc?.arm_shape?.binding,leg=doc?.leg_shape?.binding;
 if(!shared)return null;
 for(const other of [arm,leg])if(other&&(other.document_id!==shared.document_id||other.document_epoch!==shared.document_epoch||other.asset_sha256!==shared.asset_sha256))return null;
 return arm??shared;
}
