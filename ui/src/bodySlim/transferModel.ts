// SPDX-License-Identifier: GPL-3.0-or-later
// Preserve the bodySlim protocol while sharing scalar proof/PNG validation, not ownership.
export const BODY_SLIM_TRANSFER_OP='lnx.body_slim.v1';
export {
  BODY_SCALAR_TRANSFER_LIMITS as BODY_SLIM_TRANSFER_LIMITS,
  bodyScalarTransferParameters as bodySlimTransferParameters,
  validBodyScalarBodyRef as validBodySlimBodyRef,
  validBodyScalarFaceBinding as validBodySlimFaceBinding,
  validBodyScalarTransferImage as validBodySlimTransferImage,
  verifyBodyScalarTransferImage as verifyBodySlimTransferImage,
  validBodyScalarTransfer as validBodySlimTransfer,
  bodyScalarTransferReviewKey as bodySlimTransferReviewKey,
  bodyScalarTransferImagesReady as bodySlimTransferImagesReady,
  bodyScalarTransferAck as bodySlimTransferAck,
  sameBodyScalarTransferAck as sameBodySlimTransferAck,
  validBodyScalarTransferAck as validBodySlimTransferAck,
  type BodyScalarFaceBinding as BodySlimFaceBinding,
  type BodyScalarTransferEvidence as BodySlimTransferEvidence,
  type BodyScalarTransferAck as BodySlimTransferAck,
} from '../bodyScalar/transferModel.ts';
