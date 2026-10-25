// SPDX-License-Identifier: GPL-3.0-or-later
/** Stable source entrypoint. No registration, native loading, side effects or fallback transport. */
export {ExpressionReplacementPanel} from './ExpressionReplacementPanel';
export {ExpressionController} from './controller';
export {OPERATION_ID,PORT_VERSION,REQUIREMENT_ID} from './model';
export type {ExpressionPort,ExpressionCapability,Current,Photograph,Source,Face,FaceRef,Binding,PreviewCommand,DonorCommand,CancelRequest,ApplyCommand,Packet,Receipt} from './model';
