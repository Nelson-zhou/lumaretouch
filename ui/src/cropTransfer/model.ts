import type {EffectiveSourceProof} from '../people/transferProof';

export const CROP_OP = 'lnx.crop.v1';
export const CROP_LIMITS = {targets: 16, edge: 320, base64: 400000} as const;
export type CropParameters = {rect_normalized: [number, number, number, number]; rotation_degrees: number};
export type CropReview = {
  version: 1; document_id: string; revision: string; source_proof: EffectiveSourceProof;
  candidate_sha256: string; people_sha256: string; crop: CropParameters;
  source_size: [number, number]; output_size: [number, number];
  preview: {mime: 'image/png'; base64: string; width: number; height: number; sha256: string};
};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const keys = (v: Record<string, unknown>, expected: string[]) => Object.keys(v).sort().join('|') === [...expected].sort().join('|');
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const positive = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v > 0;
const size = (v: unknown): v is [number, number] => Array.isArray(v) && v.length === 2 && v.every(positive);
function sourceProof(v: unknown): v is EffectiveSourceProof {
  if (!object(v) || !keys(v, ['asset_sha256', 'original_sha256', 'creative_source']) || !hash(v.asset_sha256) || !hash(v.original_sha256)) return false;
  const c = v.creative_source;
  return c === null ? v.asset_sha256 === v.original_sha256 : object(c) && keys(c, ['sha256', 'width', 'height'])
    && c.sha256 === v.asset_sha256 && positive(c.width) && positive(c.height);
}
export function cropParameters(v: unknown): v is CropParameters {
  if (!object(v) || !keys(v, ['rect_normalized', 'rotation_degrees']) || !Array.isArray(v.rect_normalized) || v.rect_normalized.length !== 4) return false;
  const r = v.rect_normalized;
  return r.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)
    && r[0] < r[2] && r[1] < r[3] && typeof v.rotation_degrees === 'number'
    && Number.isFinite(v.rotation_degrees) && Math.abs(v.rotation_degrees) <= 180;
}
export function validCropReview(v: unknown, documentId: string, revision: string | undefined, parameters: unknown): v is CropReview {
  if (!object(v) || !keys(v, ['version', 'document_id', 'revision', 'source_proof', 'candidate_sha256', 'people_sha256', 'crop', 'source_size', 'output_size', 'preview'])
    || v.version !== 1 || v.document_id !== documentId || typeof v.revision !== 'string' || !/^\d{1,20}$/.test(v.revision)
    || BigInt(v.revision) > 18446744073709551615n || v.revision !== revision || !sourceProof(v.source_proof)
    || !hash(v.candidate_sha256) || !hash(v.people_sha256) || !cropParameters(v.crop) || !cropParameters(parameters)
    || v.crop.rotation_degrees !== parameters.rotation_degrees || !v.crop.rect_normalized.every((n, i) => n === parameters.rect_normalized[i])
    || !size(v.source_size) || !size(v.output_size)) return false;
  const c = v.source_proof.creative_source;
  if (c && (c.width !== v.source_size[0] || c.height !== v.source_size[1])) return false;
  const p = v.preview;
  return object(p) && keys(p, ['mime', 'base64', 'width', 'height', 'sha256']) && p.mime === 'image/png'
    && positive(p.width) && positive(p.height) && p.width <= CROP_LIMITS.edge && p.height <= CROP_LIMITS.edge
    && p.width <= v.output_size[0] && p.height <= v.output_size[1]
    && Math.abs(p.width * v.output_size[1] - p.height * v.output_size[0]) <= Math.max(...v.output_size)
    && typeof p.base64 === 'string' && p.base64.length <= CROP_LIMITS.base64 && p.base64.startsWith('iVBOR')
    && p.base64.length % 4 === 0 && /^[A-Za-z0-9+/]+={0,2}$/.test(p.base64) && hash(p.sha256);
}
export function cropReviewKey(token: string, value: CropReview): string {
  return JSON.stringify([token, value.document_id, value.revision, value.source_proof, value.candidate_sha256,
    value.people_sha256, value.crop, value.source_size, value.output_size, value.preview]);
}

/** All admitted targets must finish their own image verification; no first-N shortcut. */
export function cropImagesReady(token: string, values: (CropReview | undefined)[], ready: Record<string, boolean>): boolean {
  return values.every(value => !!value && ready[cropReviewKey(token, value)] === true);
}
