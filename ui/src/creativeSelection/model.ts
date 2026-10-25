// SPDX-License-Identifier: GPL-3.0-or-later
/** Replaceable UI contract. The host, not this editor, owns mask pixels and document history. */
export const SELECTION_PROTOCOL = 'lnx.creative-selection.v1' as const;
export const SELECTION_REFERENCE = 'https://www.pixcakeai.com/guide/158252';
export const SELECTION_LIMITS = {operations: 256, pointsPerGesture: 4096, totalPoints: 32768,
  imageBytes: 24 * 1024 * 1024, imageEdge: 4096, requestBytes: 2 * 1024 * 1024, undo: 64} as const;
export type SelectionPoint = [number, number];
export type SelectionCombine = 'new' | 'add' | 'subtract' | 'intersect';
export type SelectionMaskPolicy = 'create' | 'replace' | 'union' | 'subtract' | 'intersect';
export type SelectionTool = 'rectangle' | 'ellipse' | 'lasso' | 'brush';
export interface SelectionCanvas {width: number; height: number}
export type SelectionOperation =
  | {kind: 'rectangle' | 'ellipse'; combine: SelectionCombine; x0: number; y0: number; x1: number; y1: number}
  | {kind: 'lasso'; combine: SelectionCombine; points: SelectionPoint[]}
  | {kind: 'brush'; combine: 'add' | 'subtract'; points: SelectionPoint[]; diameter: number; hardness: number; opacity: number}
  | {kind: 'invert'};
export interface SelectionRecipe {
  version: 1; coordinate_space: 'canvas-pixel-edge-v1'; canvas: SelectionCanvas;
  feather_radius: number; operations: SelectionOperation[];
}
export interface SelectionBinding {
  document_id: string; source_uid: string; ownership_token: string; expected_revision: number; layer_id: string;
}
export interface SelectionProof extends SelectionBinding {
  asset_id: string; source_sha256: string; document_sha256: string; transform_sha256: string;
  existing_mask_id: string | null; existing_mask_sha256: string | null;
  canvas: SelectionCanvas; source: SelectionCanvas;
}
export interface SelectionPng {mime: 'image/png'; width: number; height: number; sha256: string; base64: string}
export interface SelectionContext {proof: SelectionProof; canvas_image: SelectionPng; existing_mask_image: SelectionPng | null}
export interface SelectionReview {
  proof: SelectionProof; preview_token: string; recipe: SelectionRecipe; recipe_sha256: string;
  mask_policy: SelectionMaskPolicy; output_mask_id: string; output_mask_sha256: string;
  before_mask: SelectionPng; after_mask: SelectionPng; before_composite: SelectionPng; after_composite: SelectionPng; ack: string;
}
export type SelectionImageRole = 'before_mask' | 'after_mask' | 'before_composite' | 'after_composite';
export const SELECTION_REVIEW_IMAGES: SelectionImageRole[] = ['before_mask', 'after_mask', 'before_composite', 'after_composite'];
interface RequestBase {request_id: string; source_uid: string}
export type SelectionContextRequest = RequestBase & SelectionBinding & {action: 'context'};
export type SelectionPreviewRequest = RequestBase & {action: 'preview'; proof: SelectionProof; recipe: SelectionRecipe; mask_policy: SelectionMaskPolicy};
export type SelectionApplyRequest = RequestBase & {action: 'apply'; proof: SelectionProof; preview_token: string; ack: string; reviewed: true};
export type SelectionCancelRequest = RequestBase & {action: 'cancel'; target_request_id: string; preview_token?: string};
export type SelectionRequest = SelectionContextRequest | SelectionPreviewRequest | SelectionApplyRequest | SelectionCancelRequest;
export interface SelectionReply extends RequestBase {
  event: 'creative_selection_result'; status: 'ready' | 'applied' | 'no_change' | 'rejected' | 'pending' | 'unknown' | 'cancelled';
  message?: string; context?: SelectionContext; review?: SelectionReview; proof?: SelectionProof;
  preview_token?: string; revision?: number; mask_id?: string; mask_sha256?: string; target_request_id?: string;
  success?: boolean; outcome_unknown?: boolean;
  /** Native-only evidence of an explicit authoritative project reopen, NOT proof of old write outcome. */
  workspace_reopened?: boolean;
  /** Opaque host snapshot: only the existing creative workspace adapter may publish it. */
  creative_state?: unknown;
}
export interface CreativeSelectionPort {
  protocol: typeof SELECTION_PROTOCOL;
  context?: (request: SelectionContextRequest) => Promise<SelectionReply>;
  preview?: (request: SelectionPreviewRequest) => Promise<SelectionReply>;
  apply?: (request: SelectionApplyRequest) => Promise<SelectionReply>;
  cancel?: (request: SelectionCancelRequest) => Promise<SelectionReply>;
  /** Query precisely this retained request. It MUST NOT re-submit it. */
  receipt?: (request: SelectionRequest) => Promise<SelectionReply>;
  /** Release native mailbox metadata only after a terminal result is retained. Never a cancellation. */
  release?: (request: SelectionRequest) => Promise<void>;
}

const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const exact = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const text = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 4096;
export const selectionHash = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const integer = (value: unknown, min: number, max: number): value is number => Number.isSafeInteger(value) && Number(value) >= min && Number(value) <= max;
export function selectionKey(value: unknown): string {
  // Stable comparison, not a substitute for the host's canonical recipe SHA.
  if (Array.isArray(value)) return '[' + value.map(selectionKey).join(',') + ']';
  if (object(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + selectionKey(value[key])).join(',') + '}';
  return JSON.stringify(value) ?? 'null';
}
export function freezeSelection<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.values(value).forEach(freezeSelection); Object.freeze(value);
  }
  return value;
}
export function validSelectionCanvas(value: unknown): value is SelectionCanvas {
  return object(value) && exact(value, ['width', 'height']) && integer(value.width, 1, 131072) && integer(value.height, 1, 131072) && value.width * value.height <= 100_000_000;
}
export function validSelectionBinding(value: unknown): value is SelectionBinding {
  return object(value) && text(value.document_id) && text(value.source_uid) && text(value.ownership_token)
    && integer(value.expected_revision, 0, Number.MAX_SAFE_INTEGER) && text(value.layer_id);
}
export function selectionBinding(value: SelectionBinding): SelectionBinding {
  return {document_id: value.document_id, source_uid: value.source_uid, ownership_token: value.ownership_token,
    expected_revision: value.expected_revision, layer_id: value.layer_id};
}
export function validSelectionProof(value: unknown): value is SelectionProof {
  return validSelectionBinding(value) && object(value) && text(value.asset_id) && selectionHash(value.source_sha256)
    && selectionHash(value.document_sha256) && selectionHash(value.transform_sha256) && validSelectionCanvas(value.canvas)
    && validSelectionCanvas(value.source) && ((value.existing_mask_id === null && value.existing_mask_sha256 === null)
      || (text(value.existing_mask_id) && selectionHash(value.existing_mask_sha256)));
}
export function validSelectionPng(value: unknown): value is SelectionPng {
  return object(value) && value.mime === 'image/png' && integer(value.width, 1, SELECTION_LIMITS.imageEdge)
    && integer(value.height, 1, SELECTION_LIMITS.imageEdge) && selectionHash(value.sha256) && typeof value.base64 === 'string'
    && value.base64.length >= 76 && value.base64.length <= Math.ceil(SELECTION_LIMITS.imageBytes / 3) * 4;
}
/** Whole-frame proxy, allowing only integer rounding of the declared full raster aspect. */
export function selectionWholeFrame(image: SelectionPng, full: SelectionCanvas): boolean {
  return image.width <= full.width && image.height <= full.height
    && Math.abs(image.width * full.height - image.height * full.width) <= Math.max(full.width, full.height);
}
export function validSelectionContext(value: unknown, request: SelectionContextRequest): value is SelectionContext {
  return object(value) && validSelectionProof(value.proof)
    && selectionKey(selectionBinding(value.proof)) === selectionKey(selectionBinding(request))
    && validSelectionPng(value.canvas_image) && selectionWholeFrame(value.canvas_image, value.proof.canvas)
    && (value.proof.existing_mask_id === null ? value.existing_mask_image === null
      : validSelectionPng(value.existing_mask_image) && selectionWholeFrame(value.existing_mask_image, value.proof.source));
}
export function emptySelectionRecipe(canvas: SelectionCanvas): SelectionRecipe {
  return {version: 1, coordinate_space: 'canvas-pixel-edge-v1', canvas: {...canvas}, feather_radius: 0, operations: []};
}
export function validSelectionRecipe(value: unknown): value is SelectionRecipe {
  if (!object(value) || !exact(value, ['version', 'coordinate_space', 'canvas', 'feather_radius', 'operations'])
    || value.version !== 1 || value.coordinate_space !== 'canvas-pixel-edge-v1' || !validSelectionCanvas(value.canvas)
    || !integer(value.feather_radius, 0, 256) || !Array.isArray(value.operations) || value.operations.length > SELECTION_LIMITS.operations) return false;
  const canvas = value.canvas; let total = 0;
  const point = (p: unknown): p is SelectionPoint => Array.isArray(p) && p.length === 2 && finite(p[0]) && finite(p[1])
    && p[0] >= 0 && p[0] <= canvas.width && p[1] >= 0 && p[1] <= canvas.height;
  return value.operations.every((op: unknown) => {
    if (!object(op)) return false;
    if (op.kind === 'invert') return Object.keys(op).length === 1;
    if (!['new', 'add', 'subtract', 'intersect'].includes(String(op.combine))) return false;
    if (op.kind === 'rectangle' || op.kind === 'ellipse') return exact(op, ['kind', 'combine', 'x0', 'y0', 'x1', 'y1'])
      && point([op.x0, op.y0]) && point([op.x1, op.y1])
      && Number(op.x1) > Number(op.x0) && Number(op.y1) > Number(op.y0);
    if (!['lasso', 'brush'].includes(String(op.kind)) || !exact(op, op.kind === 'brush' ? ['kind', 'combine', 'points', 'diameter', 'hardness', 'opacity'] : ['kind', 'combine', 'points'])
      || !Array.isArray(op.points) || !op.points.every(point)
      || op.points.length < (op.kind === 'lasso' ? 3 : 1) || op.points.length > SELECTION_LIMITS.pointsPerGesture) return false;
    total += op.points.length; if (total > SELECTION_LIMITS.totalPoints) return false;
    return op.kind === 'lasso' || (['add', 'subtract'].includes(String(op.combine)) && finite(op.diameter)
      && op.diameter >= 1 / 64 && op.diameter <= 262144 && finite(op.hardness) && op.hardness >= 0 && op.hardness <= 1
      && finite(op.opacity) && op.opacity >= 0 && op.opacity <= 1);
  });
}
export function validSelectionReview(value: unknown, request: SelectionPreviewRequest): value is SelectionReview {
  if (!object(value) || !validSelectionProof(value.proof) || selectionKey(value.proof) !== selectionKey(request.proof)
    || !text(value.preview_token) || !text(value.ack) || !validSelectionRecipe(value.recipe)
    || selectionKey(value.recipe) !== selectionKey(request.recipe) || value.mask_policy !== request.mask_policy
    || !selectionHash(value.recipe_sha256) || !text(value.output_mask_id) || !selectionHash(value.output_mask_sha256)) return false;
  return SELECTION_REVIEW_IMAGES.every(role => validSelectionPng(value[role])
    && selectionWholeFrame(value[role] as SelectionPng, role.endsWith('mask') ? request.proof.source : request.proof.canvas));
}
export function selectionReplyMatches(value: unknown, request: SelectionRequest): value is SelectionReply {
  return object(value) && value.event === 'creative_selection_result' && value.request_id === request.request_id
    && value.source_uid === request.source_uid && ['ready', 'applied', 'no_change', 'rejected', 'pending', 'unknown', 'cancelled'].includes(String(value.status))
    && (value.success === undefined || value.success === ['ready', 'applied', 'no_change'].includes(String(value.status)))
    && (value.outcome_unknown === undefined || value.outcome_unknown === (value.status === 'unknown'));
}
