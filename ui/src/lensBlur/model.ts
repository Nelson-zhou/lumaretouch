// SPDX-License-Identifier: GPL-3.0-or-later
/** Source-only v2 new-copy wire contract; recipe/depth formats remain v1. */
export const LENS_PROTOCOL = 2 as const;
export const LENS_OPERATION = 'lnx.lens_blur.v1' as const;
export const LENS_LIMITS = {imageEdge: 1280, imageBytes: 4 * 1024 * 1024, depthEdge: 1024,
  strokes: 64, points: 8192, pointsPerStroke: 2048, requestBytes: 512 * 1024} as const;
export const LENS_APERTURES = ['circular_disk', 'rim_weighted_disk', 'regular_pentagon', 'regular_octagon', 'cat_eye_intersection'] as const;
export type LensAperture = typeof LENS_APERTURES[number];
export const LENS_APERTURE_LABELS: Record<LensAperture, string> = {
  circular_disk: '圆盘', rim_weighted_disk: '环缘加权圆盘', regular_pentagon: '正五边形',
  regular_octagon: '正八边形', cat_eye_intersection: '猫眼交叠',
};
export interface LensCapability {
  version: 1; operation_id: typeof LENS_OPERATION; status: 'available' | 'unavailable';
  kernels: LensAperture[]; reason: string;
}
export interface LensSource {sha256: string; width: number; height: number; orientation: 'exif_normalized_once'}
export interface LensOwner {document_id: string; document_epoch: string; document_revision: string; source: LensSource}
export interface LensPng {mime: 'image/png'; width: number; height: number; sha256: string; base64: string}
export type LensDepthProvenance =
  | {kind: 'model'; model_id: string; model_sha256: string; inference_id: string}
  | {kind: 'manual'; method: 'user_supplied_depth'}
  | {kind: 'manual'; method: 'user_defined_plane'; depth_value: number; acknowledgement_id: string};
export interface LensDepthRaster {format: 'u16-le'; width: number; height: number; sha256: string; base64: string}
export interface LensDepthAsset {
  version: 1; token: string; owner: LensOwner; convention: 'near-zero-far-one';
  mapping: 'normalized_full_frame_pixel_centres'; orientation: 'exif_normalized_once';
  raster: LensDepthRaster; provenance: LensDepthProvenance;
  subject_focus: {near: number; far: number; mask_sha256: string} | null;
}
/** x/y are normalized SOURCE pixel centres, not crop edges or depth-array indices. */
export interface LensPoint {x: number; y: number}
export interface LensStroke {
  id: string; mode: 'clear' | 'blur'; amount: number; flow: number; feather: number;
  radius: number; points: LensPoint[];
}
export interface LensFocus {mode: 'interval' | 'point' | 'subject'; near: number; far: number; point: LensPoint | null}
export interface LensRecipe {
  version: 1; operation_id: typeof LENS_OPERATION; source: LensSource;
  depth: {token: string; sha256: string; provenance: LensDepthProvenance};
  aperture: LensAperture; max_radius_px: number; focus: LensFocus;
  depth_falloff: number; occlusion_tolerance: number; rotation_radians: number;
  refinements: LensStroke[];
}
export interface LensContext {
  session_id: string; owner: LensOwner; source_image: LensPng;
  depth: LensDepthAsset | null;
  depth_status: 'ready' | 'pending' | 'missing-model' | 'manual-required' | 'failed';
  message: string;
}
export interface LensPreviewCommand {version: 2; action: 'preview'; request_id: string; session_id: string; owner: LensOwner; recipe: LensRecipe}
export interface LensManualPlaneCommand {
  version: 2; action: 'prepare_manual_plane'; request_id: string; session_id: string; owner: LensOwner;
  depth_value: number; acknowledged_manual: true;
}
export interface LensReview {
  version: 2; request_id: string; session_id: string; token: string; owner: LensOwner;
  recipe: LensRecipe; recipe_sha256: string; before: LensPng; after: LensPng; notes: string[];
  /** Canonical full-resolution output asset identity, NOT the display PNG hash. */
  result_source_sha256: string;
}
export interface LensApplyCommand {
  version: 2; action: 'apply'; request_id: string; session_id: string; owner: LensOwner;
  token: string; recipe_sha256: string; before_sha256: string; after_sha256: string; reviewed: true;
  return_mode: 'new_image'; result_source_sha256: string;
}
export interface LensCancelCommand {version: 2; action: 'cancel'; request_id: string; session_id: string; owner: LensOwner; token: string | null}
export type LensWriteCommand = LensApplyCommand | LensCancelCommand;
interface ReceiptIdentity {version: 2; request_id: string; session_id: string; action: 'apply' | 'cancel'; owner: LensOwner; token: string | null}
export type LensReceipt = ReceiptIdentity & (
  | {phase: 'pending' | 'unknown'; outcome_unknown: true; message: string}
  | {phase: 'done'; outcome_unknown: false; outcome: 'rejected' | 'cancelled'; message: string}
  | {phase: 'done'; outcome_unknown: false; outcome: 'applied'; message: string;
    recipe_sha256: string; before_sha256: string; after_sha256: string;
    return_mode: 'new_image'; copied_original_document_id: string; result_document_id: string;
    result_revision: string; result_source_sha256: string; no_change: boolean}
);
export interface LensBlurPort {
  readonly protocol: typeof LENS_PROTOCOL;
  /** Optional read-only preparation, exclusively after the explicit manual-baseline user action. */
  prepareManualPlane?(command: LensManualPlaneCommand): Promise<unknown>;
  /** A preview must NEVER mutate the document or append history. */
  preview(command: LensPreviewCommand): Promise<unknown>;
  /** Host must persist the original command/receipt outside the mounted workspace. */
  submit(command: LensWriteCommand): Promise<unknown>;
  receipt(command: LensWriteCommand): Promise<unknown>;
}

export const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: Record<string, unknown>, keys: string[]) => Object.keys(v).sort().join('|') === [...keys].sort().join('|');
export const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
export const token = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length <= 4096 && !v.includes('\0');
const integer = (v: unknown, min: number, max: number): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max;
export const unit = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 1;
export const revision = (v: unknown): v is string => typeof v === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(v) && BigInt(v) <= 18446744073709551615n;
export function validLensCapability(v: unknown): v is LensCapability {
  return object(v) && exact(v, ['version', 'operation_id', 'status', 'kernels', 'reason'])
    && v.version === 1 && v.operation_id === LENS_OPERATION && ['available', 'unavailable'].includes(v.status as string)
    && Array.isArray(v.kernels) && v.kernels.length <= LENS_APERTURES.length && new Set(v.kernels).size === v.kernels.length
    && v.kernels.every(k => LENS_APERTURES.includes(k as LensAperture)) && text(v.reason)
    && (v.status === 'available' ? v.kernels.length > 0 : v.kernels.length === 0);
}
export function validLensSource(v: unknown): v is LensSource {
  return object(v) && exact(v, ['sha256', 'width', 'height', 'orientation']) && hash(v.sha256)
    && integer(v.width, 2, 1000000) && integer(v.height, 2, 1000000) && v.orientation === 'exif_normalized_once';
}
export function validLensOwner(v: unknown): v is LensOwner {
  return object(v) && exact(v, ['document_id', 'document_epoch', 'document_revision', 'source'])
    && token(v.document_id) && token(v.document_epoch) && revision(v.document_revision) && validLensSource(v.source);
}
/** Canonical comparison is property-order independent; it is not an authenticity proof. */
export function lensKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(lensKey).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${lensKey(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export const sameLensOwner = (a: LensOwner, b: LensOwner) => lensKey(a) === lensKey(b);
export function lensRequestFits(value: unknown): boolean {
  try {return new TextEncoder().encode(JSON.stringify(value)).length <= LENS_LIMITS.requestBytes;} catch {return false;}
}
export function validLensPng(v: unknown): v is LensPng {
  return object(v) && exact(v, ['mime', 'width', 'height', 'sha256', 'base64']) && v.mime === 'image/png'
    && integer(v.width, 2, LENS_LIMITS.imageEdge) && integer(v.height, 2, LENS_LIMITS.imageEdge) && hash(v.sha256)
    && typeof v.base64 === 'string' && v.base64.length <= Math.ceil(LENS_LIMITS.imageBytes / 3) * 4
    && v.base64.length % 4 === 0 && /^iVBOR[A-Za-z0-9+/]*={0,2}$/.test(v.base64);
}
export function wholeFrameSize(width: number, height: number, source: LensSource): boolean {
  return width <= source.width && height <= source.height && Math.abs(width * source.height - height * source.width) <= Math.max(source.width, source.height);
}
export function validLensProvenance(v: unknown): v is LensDepthProvenance {
  return object(v) && (v.kind === 'manual' ? (v.method === 'user_supplied_depth' ? exact(v, ['kind', 'method'])
    : v.method === 'user_defined_plane' && exact(v, ['kind', 'method', 'depth_value', 'acknowledgement_id']) && unit(v.depth_value) && token(v.acknowledgement_id))
    : v.kind === 'model' && exact(v, ['kind', 'model_id', 'model_sha256', 'inference_id'])
      && token(v.model_id) && hash(v.model_sha256) && token(v.inference_id));
}
export function validLensDepth(v: unknown, owner: LensOwner): v is LensDepthAsset {
  if (!object(v) || !exact(v, ['version', 'token', 'owner', 'convention', 'mapping', 'orientation', 'raster', 'provenance', 'subject_focus'])
    || v.version !== 1 || !token(v.token) || !validLensOwner(v.owner) || !sameLensOwner(v.owner, owner)
    || v.convention !== 'near-zero-far-one' || v.mapping !== 'normalized_full_frame_pixel_centres'
    || v.orientation !== 'exif_normalized_once' || !validLensProvenance(v.provenance) || !object(v.raster)) return false;
  const r = v.raster;
  if (!exact(r, ['format', 'width', 'height', 'sha256', 'base64']) || r.format !== 'u16-le'
    || !integer(r.width, 2, LENS_LIMITS.depthEdge) || !integer(r.height, 2, LENS_LIMITS.depthEdge)
    || !wholeFrameSize(r.width, r.height, owner.source) || !hash(r.sha256)
    || typeof r.base64 !== 'string' || r.base64.length !== Math.ceil(r.width * r.height * 2 / 3) * 4
    || !/^[A-Za-z0-9+/]+={0,2}$/.test(r.base64)) return false;
  const f = v.subject_focus;
  return f === null || v.provenance.kind === 'model' && object(f) && exact(f, ['near', 'far', 'mask_sha256'])
    && unit(f.near) && unit(f.far) && f.near <= f.far && hash(f.mask_sha256);
}
export function validLensContext(v: unknown): v is LensContext {
  return object(v) && exact(v, ['session_id', 'owner', 'source_image', 'depth', 'depth_status', 'message'])
    && token(v.session_id) && validLensOwner(v.owner) && validLensPng(v.source_image)
    && wholeFrameSize(v.source_image.width, v.source_image.height, v.owner.source)
    && text(v.message) && ['ready', 'pending', 'missing-model', 'manual-required', 'failed'].includes(v.depth_status as string)
    && (v.depth_status === 'ready' ? validLensDepth(v.depth, v.owner) : v.depth === null);
}
export function validLensPoint(v: unknown): v is LensPoint {
  return object(v) && exact(v, ['x', 'y']) && unit(v.x) && unit(v.y);
}
export function validLensStroke(v: unknown): v is LensStroke {
  return object(v) && exact(v, ['id', 'mode', 'amount', 'flow', 'feather', 'radius', 'points']) && token(v.id)
    && (v.mode === 'clear' || v.mode === 'blur') && unit(v.amount) && unit(v.flow) && unit(v.feather)
    && typeof v.radius === 'number' && Number.isFinite(v.radius) && v.radius > 0 && v.radius <= .25
    && Array.isArray(v.points) && v.points.length > 0 && v.points.length <= LENS_LIMITS.pointsPerStroke && v.points.every(validLensPoint);
}
export function validLensRecipe(v: unknown, depth?: LensDepthAsset): v is LensRecipe {
  if (!object(v) || !exact(v, ['version', 'operation_id', 'source', 'depth', 'aperture', 'max_radius_px', 'focus', 'depth_falloff', 'occlusion_tolerance', 'rotation_radians', 'refinements'])
    || v.version !== 1 || v.operation_id !== LENS_OPERATION || !validLensSource(v.source)
    || !object(v.depth) || !exact(v.depth, ['token', 'sha256', 'provenance']) || !token(v.depth.token)
    || !hash(v.depth.sha256) || !validLensProvenance(v.depth.provenance)
    || !LENS_APERTURES.includes(v.aperture as LensAperture) || typeof v.max_radius_px !== 'number'
    || !Number.isFinite(v.max_radius_px) || v.max_radius_px < 0 || v.max_radius_px > 128
    || !unit(v.depth_falloff) || v.depth_falloff <= 0 || !unit(v.occlusion_tolerance)
    || typeof v.rotation_radians !== 'number' || !Number.isFinite(v.rotation_radians) || Math.abs(v.rotation_radians) > Math.PI
    || !object(v.focus) || !exact(v.focus, ['mode', 'near', 'far', 'point']) || !unit(v.focus.near) || !unit(v.focus.far)
    || v.focus.near > v.focus.far || !['point', 'interval', 'subject'].includes(v.focus.mode as string)
    || (v.focus.mode === 'point' ? !validLensPoint(v.focus.point) : v.focus.point !== null)
    || !Array.isArray(v.refinements) || v.refinements.length > LENS_LIMITS.strokes || !v.refinements.every(validLensStroke)) return false;
  const strokes = v.refinements as LensStroke[];
  if (new Set(strokes.map(s => s.id)).size !== strokes.length || strokes.reduce((n, s) => n + s.points.length, 0) > LENS_LIMITS.points) return false;
  if (depth && (lensKey(v.source) !== lensKey(depth.owner.source) || v.depth.token !== depth.token
    || v.depth.sha256 !== depth.raster.sha256 || lensKey(v.depth.provenance) !== lensKey(depth.provenance)
    || v.focus.mode === 'subject' && (!depth.subject_focus || v.focus.near !== depth.subject_focus.near || v.focus.far !== depth.subject_focus.far))) return false;
  return lensRequestFits(v);
}
export function initialLensRecipe(depth: LensDepthAsset): LensRecipe {
  const f = depth.subject_focus;
  return {version: 1, operation_id: LENS_OPERATION, source: {...depth.owner.source},
    depth: {token: depth.token, sha256: depth.raster.sha256, provenance: {...depth.provenance}},
    aperture: 'circular_disk', max_radius_px: 0,
    focus: {mode: f ? 'subject' : 'interval', near: f?.near ?? 0, far: f?.far ?? 1, point: null},
    depth_falloff: .2, occlusion_tolerance: .02, rotation_radians: 0, refinements: []};
}
export function validLensReview(v: unknown, command: LensPreviewCommand): v is LensReview {
  return object(v) && exact(v, ['version', 'request_id', 'session_id', 'token', 'owner', 'recipe', 'recipe_sha256', 'before', 'after', 'notes', 'result_source_sha256'])
    && command.version === LENS_PROTOCOL && v.version === LENS_PROTOCOL && v.request_id === command.request_id && v.session_id === command.session_id && token(v.token)
    && validLensOwner(v.owner) && sameLensOwner(v.owner, command.owner) && validLensRecipe(v.recipe)
    && lensKey(v.recipe) === lensKey(command.recipe) && hash(v.recipe_sha256) && hash(v.result_source_sha256)
    && validLensPng(v.before) && validLensPng(v.after) && v.before.width === v.after.width && v.before.height === v.after.height
    && wholeFrameSize(v.before.width, v.before.height, command.owner.source)
    && Array.isArray(v.notes) && v.notes.length <= 32 && v.notes.every(text);
}
export function lensReviewKey(v: LensReview): string {
  return lensKey([v.version, v.session_id, v.token, v.owner, v.recipe, v.recipe_sha256, v.before.sha256, v.after.sha256, v.result_source_sha256]);
}
export function validLensWriteCommand(v: unknown): v is LensWriteCommand {
  if (!object(v) || v.version !== LENS_PROTOCOL || !token(v.request_id) || !token(v.session_id)
    || !validLensOwner(v.owner) || !lensRequestFits(v)) return false;
  const base = ['version', 'action', 'request_id', 'session_id', 'owner', 'token'];
  if (v.action === 'cancel') return exact(v, base) && (v.token === null || token(v.token));
  return v.action === 'apply' && exact(v, [...base, 'recipe_sha256', 'before_sha256', 'after_sha256', 'reviewed', 'return_mode', 'result_source_sha256'])
    && token(v.token) && hash(v.recipe_sha256) && hash(v.before_sha256) && hash(v.after_sha256)
    && v.reviewed === true && v.return_mode === 'new_image' && hash(v.result_source_sha256);
}
export function validLensReceipt(v: unknown, command: LensWriteCommand): v is LensReceipt {
  if (!validLensWriteCommand(command) || !object(v) || v.version !== LENS_PROTOCOL || v.request_id !== command.request_id || v.session_id !== command.session_id
    || v.action !== command.action || !validLensOwner(v.owner) || !sameLensOwner(v.owner, command.owner)
    || v.token !== command.token || !text(v.message)) return false;
  const base = ['version', 'request_id', 'session_id', 'action', 'owner', 'token', 'phase', 'outcome_unknown', 'message'];
  if (v.phase === 'pending' || v.phase === 'unknown') return exact(v, base) && v.outcome_unknown === true;
  if (v.phase !== 'done' || v.outcome_unknown !== false) return false;
  if (v.outcome === 'rejected' || v.outcome === 'cancelled') return exact(v, [...base, 'outcome']) && (v.outcome !== 'cancelled' || command.action === 'cancel');
  if (v.outcome !== 'applied' || command.action !== 'apply'
    || !exact(v, [...base, 'outcome', 'recipe_sha256', 'before_sha256', 'after_sha256', 'return_mode', 'copied_original_document_id', 'result_document_id', 'result_revision', 'result_source_sha256', 'no_change'])
    || v.recipe_sha256 !== command.recipe_sha256 || v.before_sha256 !== command.before_sha256 || v.after_sha256 !== command.after_sha256
    || v.return_mode !== command.return_mode || v.result_source_sha256 !== command.result_source_sha256
    || v.copied_original_document_id !== command.owner.document_id || !token(v.result_document_id)
    || v.result_document_id === v.copied_original_document_id || !revision(v.result_revision) || typeof v.no_change !== 'boolean') return false;
  // Neutral pixels still create a distinct new document. No source history entry exists for this return path.
  return v.no_change === (v.result_source_sha256 === command.owner.source.sha256);
}
