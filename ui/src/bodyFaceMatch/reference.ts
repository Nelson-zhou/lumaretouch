// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef} from '../people/model';
export type ReferenceSourceStage = 'immutable-source' | 'verified-repair-base';
export const validReferenceSourceStage = (value: unknown): value is ReferenceSourceStage => value === 'immutable-source' || value === 'verified-repair-base';

export type FaceSkinObservation = {contract: 'mediapipe-face-skin-edit-weight-v1'; source_sha256: string;
  semantic_model_sha256: string; producer_width: number; producer_height: number};
/** Identity metadata, not transferable sampled colours, pixels, masks or render-quality proof. */
export type OwnFaceReference = {face_ref: FaceRef; face_skin_observation: FaceSkinObservation;
  landmark_digest: string; reference_method: 'effective-source-stage-own-face-robust-log-chroma'};
export type OwnFaceReferenceSupport = {
  face_ref: FaceRef; source: {sha256: string; width: number; height: number}; face_skin_observation: FaceSkinObservation;
  scope: 'selected-own-face-effective-source-reference'; reference_method: 'effective-source-stage-own-face-robust-log-chroma';
  source_window: [number, number, number, number]; support_pixels: number; reference_samples: number;
  protected_face_boxes: number; runtime_quality_accepted: false;
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: string[]) => Object.keys(v).sort().join('|') === [...expected].sort().join('|');
const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): v is number => typeof v === 'number'
  && Number.isSafeInteger(v) && v >= min && v <= max;
function exactFace(v: unknown, face: FaceRef): boolean {
  return object(v) && keys(v, ['asset_sha256', 'face_instance_id', 'analysis_revision'])
    && digest(v.asset_sha256) && typeof v.face_instance_id === 'string' && v.face_instance_id.length > 0
    && v.face_instance_id.length <= 128 && integer(v.analysis_revision)
    && v.asset_sha256 === face.asset_sha256 && v.face_instance_id === face.face_instance_id && v.analysis_revision === face.analysis_revision;
}
export function validFaceSkinObservation(v: unknown, sourceSha256: string): v is FaceSkinObservation {
  return object(v) && keys(v, ['contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'])
    && v.contract === 'mediapipe-face-skin-edit-weight-v1' && digest(v.source_sha256) && v.source_sha256 === sourceSha256
    && digest(v.semantic_model_sha256) && integer(v.producer_width, 1, 1_000_000) && integer(v.producer_height, 1, 1_000_000);
}
export function validOwnFaceReference(value: unknown, face: FaceRef): value is OwnFaceReference {
  return object(value) && keys(value, ['face_ref', 'face_skin_observation', 'landmark_digest', 'reference_method'])
    && exactFace(value.face_ref, face) && validFaceSkinObservation(value.face_skin_observation, face.asset_sha256)
    && digest(value.landmark_digest) && value.reference_method === 'effective-source-stage-own-face-robust-log-chroma';
}
/** The source window is in the actual decoded source grid, not the durable full-resolution grid. */
export function validOwnFaceReferenceSupport(value: unknown, face: FaceRef,
  source: {sha256: string; width: number; height: number}, decoded: {width: number; height: number}): value is OwnFaceReferenceSupport {
  if (!object(value) || !keys(value, ['face_ref', 'source', 'face_skin_observation', 'scope', 'reference_method',
    'source_window', 'support_pixels', 'reference_samples', 'protected_face_boxes', 'runtime_quality_accepted'])
    || !exactFace(value.face_ref, face) || !object(value.source) || !keys(value.source, ['sha256', 'width', 'height'])
    || !digest(source.sha256) || !integer(source.width, 2, 1_000_000) || !integer(source.height, 2, 1_000_000)
    || source.sha256 !== face.asset_sha256 || value.source.sha256 !== source.sha256
    || value.source.width !== source.width || value.source.height !== source.height
    || !validFaceSkinObservation(value.face_skin_observation, source.sha256)
    || value.scope !== 'selected-own-face-effective-source-reference'
    || value.reference_method !== 'effective-source-stage-own-face-robust-log-chroma' || value.runtime_quality_accepted !== false
    || !integer(decoded.width, 2, 1_000_000) || !integer(decoded.height, 2, 1_000_000)
    || !Array.isArray(value.source_window) || value.source_window.length !== 4
    || !value.source_window.every(n => integer(n)) || !integer(value.protected_face_boxes)
    || !integer(value.support_pixels, 1) || !integer(value.reference_samples, 64)) return false;
  const [y, x, h, w] = value.source_window as number[];
  return h >= 2 && w >= 2 && y + h <= decoded.height && x + w <= decoded.width
    && value.support_pixels <= h * w && value.reference_samples <= value.support_pixels;
}
