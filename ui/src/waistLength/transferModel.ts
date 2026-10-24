// SPDX-License-Identifier: GPL-3.0-or-later
import {bodyScalarTransferReviewKey,BODY_SCALAR_TRANSFER_LIMITS,type BodyScalarTransferEvidence} from '../bodyScalar/transferModel.ts';
export const WAIST_TRANSFER_OP='lnx.waist_length.v1';
export {
  BODY_SCALAR_TRANSFER_LIMITS as WAIST_TRANSFER_LIMITS,
  bodyScalarTransferParameters as waistTransferParameters,
  validBodyScalarBodyRef as validWaistBodyRef,
  validBodyScalarFaceBinding as validWaistFaceBinding,
  validBodyScalarTransferImage as validWaistTransferImage,
  verifyBodyScalarTransferImage as verifyWaistTransferImage,
  validBodyScalarTransfer as validWaistTransfer,
  bodyScalarTransferAck as waistTransferAck,
  sameBodyScalarTransferAck as sameWaistTransferAck,
  validBodyScalarTransferAck as validWaistTransferAck,
  type BodyScalarFaceBinding as WaistFaceBinding,
  type BodyScalarTransferEvidence as WaistTransferEvidence,
  type BodyScalarTransferAck as WaistTransferAck,
} from '../bodyScalar/transferModel.ts';
/** The operation namespace prevents a torso checkbox from authorizing a waist pair. */
export function waistTransferReviewKey(token:string,value:BodyScalarTransferEvidence):string{
  return bodyScalarTransferReviewKey(`${WAIST_TRANSFER_OP}:${token}`,value);
}
export function waistTransferImagesReady(token:string,values:(BodyScalarTransferEvidence|undefined)[],ready:Record<string,boolean>):boolean{
  return values.length<=BODY_SCALAR_TRANSFER_LIMITS.targets&&values.every(value=>!!value&&ready[waistTransferReviewKey(token,value)]===true);
}
