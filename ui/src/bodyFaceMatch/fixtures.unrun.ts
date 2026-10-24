// AUTHORED / UNRUN. Data builders only; no fixture or product imports were executed while authoring.
import type {FaceRef} from '../people/model.ts';
import type {OwnFaceReference, OwnFaceReferenceSupport} from './reference.ts';
export const faceFixture: FaceRef = {asset_sha256: 'a'.repeat(64), face_instance_id: 'face-a', analysis_revision: 2};
export function ownFaceReferenceFixture(face: FaceRef = faceFixture): OwnFaceReference {
  return {face_ref: {...face}, face_skin_observation: {contract: 'mediapipe-face-skin-edit-weight-v1',
    source_sha256: face.asset_sha256, semantic_model_sha256: 'd'.repeat(64), producer_width: 600, producer_height: 800},
    landmark_digest: 'e'.repeat(64), reference_method: 'effective-source-stage-own-face-robust-log-chroma'};
}
export function ownFaceSupportFixture(face: FaceRef = faceFixture): OwnFaceReferenceSupport {
  return {face_ref: {...face}, source: {sha256: face.asset_sha256, width: 600, height: 800},
    face_skin_observation: ownFaceReferenceFixture(face).face_skin_observation,
    scope: 'selected-own-face-effective-source-reference', reference_method: 'effective-source-stage-own-face-robust-log-chroma',
    source_window: [80, 60, 120, 100], support_pixels: 800, reference_samples: 700,
    protected_face_boxes: 1, runtime_quality_accepted: false};
}
