// SPDX-License-Identifier: GPL-3.0-or-later
import {bodyScalarTransferParameters,validBodyScalarTransfer,bodyScalarTransferReviewKey,BODY_SCALAR_TRANSFER_LIMITS,type BodyScalarTransferEvidence} from '../bodyScalar/transferModel.ts';
import type {HeadSizeRecipe} from './model';
export const HEAD_TRANSFER_OP='lnx.head_size.v1';
export {
  BODY_SCALAR_TRANSFER_LIMITS as HEAD_TRANSFER_LIMITS,
  validBodyScalarBodyRef as validHeadBodyRef,
  validBodyScalarFaceBinding as validHeadFaceBinding,
  validBodyScalarTransferImage as validHeadTransferImage,
  verifyBodyScalarTransferImage as verifyHeadTransferImage,
  bodyScalarTransferAck as headTransferAck,
  sameBodyScalarTransferAck as sameHeadTransferAck,
  validBodyScalarTransferAck as validHeadTransferAck,
  type BodyScalarFaceBinding as HeadFaceBinding,
  type BodyScalarTransferEvidence as HeadTransferEvidence,
  type BodyScalarTransferAck as HeadTransferAck,
} from '../bodyScalar/transferModel.ts';
/** Complete-head shrink only. Never inherit signed torso/waist length semantics. */
export function headTransferParameters(value:unknown):value is HeadSizeRecipe{
  return bodyScalarTransferParameters(value)&&value.amount>=0;
}
export function validHeadTransfer(value:unknown,id:string,revision:string|undefined,parameters:unknown,source:unknown):value is BodyScalarTransferEvidence{
  return headTransferParameters(parameters)&&validBodyScalarTransfer(value,id,revision,parameters,source)&&headTransferParameters(value.parameters);
}
/** Exact operation + frozen token/request namespace; a length review cannot authorize head size. */
export function headTransferReviewKey(token:string,value:BodyScalarTransferEvidence):string{
  return bodyScalarTransferReviewKey(`${HEAD_TRANSFER_OP}:${token}`,value);
}
export function headTransferImagesReady(token:string,values:(BodyScalarTransferEvidence|undefined)[],ready:Record<string,boolean>):boolean{
  return values.length<=BODY_SCALAR_TRANSFER_LIMITS.targets&&values.every(value=>!!value&&ready[headTransferReviewKey(token,value)]===true);
}
