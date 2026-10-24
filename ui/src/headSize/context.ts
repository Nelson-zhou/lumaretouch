// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState,EngineStatus} from '../native';
import type {Binding} from './model';
import {shoulderBinding} from '../shoulderShape/context';
/** Shares the canonical body/people document, never an independent face owner. */
export function headSizeBinding(status:EngineStatus|null,doc:DocState|null):Binding|null{
 const shared=shoulderBinding(status,doc),head=doc?.head_size?.binding;
 if(!shared)return null;
 if(head&&(head.document_id!==shared.document_id||head.document_epoch!==shared.document_epoch||head.asset_sha256!==shared.asset_sha256))return null;
 return head??shared;
}
