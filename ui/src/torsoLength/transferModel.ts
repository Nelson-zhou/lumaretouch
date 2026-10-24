// SPDX-License-Identifier: GPL-3.0-or-later
// Preserve the torso protocol while sharing scalar proof/PNG validation, not ownership.
export const TORSO_TRANSFER_OP='lnx.torso_length.v1';
export {
  BODY_SCALAR_TRANSFER_LIMITS as TORSO_TRANSFER_LIMITS,
  bodyScalarTransferParameters as torsoTransferParameters,
  validBodyScalarBodyRef as validTorsoBodyRef,
  validBodyScalarFaceBinding as validTorsoFaceBinding,
  validBodyScalarTransferImage as validTorsoTransferImage,
  verifyBodyScalarTransferImage as verifyTorsoTransferImage,
  validBodyScalarTransfer as validTorsoTransfer,
  bodyScalarTransferReviewKey as torsoTransferReviewKey,
  bodyScalarTransferImagesReady as torsoTransferImagesReady,
  bodyScalarTransferAck as torsoTransferAck,
  sameBodyScalarTransferAck as sameTorsoTransferAck,
  validBodyScalarTransferAck as validTorsoTransferAck,
  type BodyScalarFaceBinding as TorsoFaceBinding,
  type BodyScalarTransferEvidence as TorsoTransferEvidence,
  type BodyScalarTransferAck as TorsoTransferAck,
} from '../bodyScalar/transferModel.ts';
