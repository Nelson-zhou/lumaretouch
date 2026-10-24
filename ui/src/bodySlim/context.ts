// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
import {shoulderBinding} from '../shoulderShape/context';
/** The loaded image and the canonical body/people document must agree. */
export function bodySlimBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),bodySlim=doc?.body_slim?.binding;
 if(!shared)return null;
 if(bodySlim&&(bodySlim.document_id!==shared.document_id||bodySlim.document_epoch!==shared.document_epoch||bodySlim.asset_sha256!==shared.asset_sha256))return null;
 return bodySlim??shared;
}
