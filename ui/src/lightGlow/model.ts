// SPDX-License-Identifier: GPL-3.0-or-later
/** Independent creative:211524 contract. AUTHORED / UNRUN; not a lens-blur alias. */
export const GLOW_PROTOCOL = 1 as const;
export const GLOW_OPERATION = 'lnx.light_glow.v1' as const;
export const GLOW_MATH = 65537 as const;
export const GLOW_REFERENCE = 'https://www.pixcakeai.com/guide/211524';
export const GLOW_LIMITS = {imageEdge: 1280, imageBytes: 4 * 1024 * 1024, requestBytes: 32 * 1024} as const;
export const GLOW_MODES = ['black_mist', 'white_mist', 'glow'] as const;
export type GlowMode = typeof GLOW_MODES[number];
export const GLOW_MODE_LABELS: Record<GlowMode, string> = {black_mist: '黑柔', white_mist: '白柔', glow: '辉光'};
export type GlowPreset = 'eighth' | 'quarter' | 'half' | 'weak' | 'medium' | 'strong';
export const GLOW_PRESET_LABELS: Record<GlowPreset, string> = {eighth: '1/8', quarter: '1/4（默认）', half: '1/2', weak: '弱（默认）', medium: '中', strong: '强'};

export interface GlowRecipe {
  version: 1; operation_id: typeof GLOW_OPERATION; math_identity: typeof GLOW_MATH;
  mode: GlowMode; strength: number; radius_px: number; threshold: number;
  exposure_ev: number; scattering: number;
  tint: {hue_deg: number; saturation: number; lightness: number};
}
/** Numeric values are LumaRetouch's local calibration, NOT published vendor values. */
const PRESETS: Record<GlowMode, Partial<Record<GlowPreset, readonly [number, number, number, number]>>> = {
  black_mist: {eighth: [.15, 16, .72, 0], quarter: [.30, 24, .65, 0], half: [.50, 36, .58, 0]},
  white_mist: {eighth: [.20, 24, .58, .25], quarter: [.35, 36, .50, .50], half: [.55, 54, .42, .75]},
  glow: {weak: [.25, 24, .68, .25], medium: [.45, 36, .60, .50], strong: [.70, 54, .50, 1]},
};
export const glowPresets = (mode: GlowMode): GlowPreset[] => mode === 'glow' ? ['weak', 'medium', 'strong'] : ['eighth', 'quarter', 'half'];
export const defaultGlowPreset = (mode: GlowMode): GlowPreset => mode === 'glow' ? 'weak' : 'quarter';
export function glowPresetRecipe(mode: GlowMode, preset: GlowPreset = defaultGlowPreset(mode)): GlowRecipe | null {
  const values = PRESETS[mode]?.[preset];
  return values ? {version: 1, operation_id: GLOW_OPERATION, math_identity: GLOW_MATH, mode,
    strength: values[0], radius_px: values[1], threshold: values[2], exposure_ev: values[3], scattering: 0,
    tint: {hue_deg: 0, saturation: 0, lightness: 0}} : null;
}
export function matchingGlowPreset(recipe: GlowRecipe): GlowPreset | null {
  return glowPresets(recipe.mode).find(preset => glowKey(glowPresetRecipe(recipe.mode, preset)) === glowKey(recipe)) ?? null;
}

export interface GlowSource {sha256: string; width: number; height: number; orientation: 'exif_normalized_once'}
export interface GlowOwner {document_id: string; document_epoch: string; document_revision: string; source: GlowSource}
export interface GlowSourceEvidence {
  kind: 'current_full_edited_source'; capture_version: 3; original_sha256: string;
  people_graph_sha256: string; repair_stack_sha256: string; document_revision: string; load_id: string; capture_token: string;
}
export interface GlowPng {mime: 'image/png'; width: number; height: number; sha256: string; base64: string}
export interface GlowCapability {
  version: 1; operation_id: typeof GLOW_OPERATION; status: 'available' | 'unavailable';
  abi: 1; math_version: typeof GLOW_MATH; reason: string | null; modes: GlowMode[];
}
export interface GlowContext {
  version: 1; operation_id: typeof GLOW_OPERATION; session_id: string; owner: GlowOwner;
  source_evidence: GlowSourceEvidence; before: GlowPng; capability: GlowCapability; message: string;
}
export interface GlowPreviewCommand {
  version: 1; operation_id: typeof GLOW_OPERATION; action: 'preview'; request_id: string;
  session_id: string; owner: GlowOwner; recipe: GlowRecipe;
}
export interface GlowReview {
  version: 1; operation_id: typeof GLOW_OPERATION; request_id: string; session_id: string; owner: GlowOwner;
  source_evidence: GlowSourceEvidence; token: string; recipe: GlowRecipe; recipe_sha256: string;
  result_source_sha256: string; coverage_sha256: string; before: GlowPng; after: GlowPng; coverage: GlowPng;
  no_change: boolean; notes: string[];
}
export interface GlowApplyCommand {
  version: 1; operation_id: typeof GLOW_OPERATION; action: 'apply'; request_id: string; session_id: string; owner: GlowOwner;
  token: string; recipe_sha256: string; result_source_sha256: string; coverage_sha256: string;
  before_sha256: string; after_sha256: string; coverage_image_sha256: string; reviewed: true; return_mode: 'new_image';
}
export interface GlowCancelCommand {
  version: 1; operation_id: typeof GLOW_OPERATION; action: 'cancel'; request_id: string;
  session_id: string; owner: GlowOwner; token: string | null;
}
export type GlowWriteCommand = GlowApplyCommand | GlowCancelCommand;
interface ReceiptIdentity {
  version: 1; operation_id: typeof GLOW_OPERATION; request_id: string; session_id: string;
  action: GlowWriteCommand['action']; owner: GlowOwner; token: string | null; message: string;
}
export type GlowReceipt = ReceiptIdentity & (
  | {phase: 'pending' | 'unknown'; outcome_unknown: true}
  | {phase: 'done'; outcome_unknown: false; outcome: 'rejected' | 'cancelled'}
  | {phase: 'done'; outcome_unknown: false; outcome: 'applied'; result_document_id: string;
    copied_original_document_id: string; result_revision: string; result_source_sha256: string; no_change: boolean}
);
export type GlowCurrentReply = {event: 'light_glow_result'; request_id: string} & (
  | {status: 'ready'; context: GlowContext}
  | {status: 'pending' | 'unknown' | 'cancelled' | 'rejected'; message: string}
);

/** Real adapter required. The port owns request/receipt lifetime, not panel visibility. */
export interface LightGlowPort {
  readonly protocol: typeof GLOW_PROTOCOL;
  refreshCapability(): Promise<unknown>;
  acquireCurrent(requestId: string): Promise<unknown>;
  currentStatus(requestId: string): Promise<unknown>;
  cancelCurrent(requestId: string): Promise<void>;
  /** Resolve the inner review only; retain read identity after timeout and never resend it. */
  preview(command: GlowPreviewCommand): Promise<unknown>;
  submit(command: GlowWriteCommand): Promise<unknown>;
  receipt(command: GlowWriteCommand): Promise<unknown>;
  cancelReads(): Promise<void>;
  checkReads(): Promise<void>;
  pendingReads(): boolean;
  subscribe(listener: () => void): () => void;
  requestReconciliation?(command: GlowWriteCommand): void;
}

export const glowObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export const glowExact = (value: Record<string, unknown>, keys: readonly string[]): boolean => Object.keys(value).sort().join('|') === [...keys].sort().join('|');
export const glowHash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const glowId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const message = (value: unknown): value is string => typeof value === 'string' && value.length <= 4096 && !value.includes('\0');
const finite = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
const integer = (value: unknown, min: number, max: number): value is number => finite(value, min, max) && Number.isSafeInteger(value);
export const glowRevision = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(value) && BigInt(value) <= 18446744073709551615n;
export function glowKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(glowKey).join(',')}]`;
  if (glowObject(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${glowKey(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export function freezeGlow<T>(value: T): T {
  const copy = structuredClone(value);
  const freeze = (item: unknown): void => {if (item && typeof item === 'object') {Object.values(item).forEach(freeze); Object.freeze(item);}};
  freeze(copy); return copy;
}
export const sameGlowOwner = (a: GlowOwner, b: GlowOwner): boolean => glowKey(a) === glowKey(b);
export function glowRequestFits(value: unknown): boolean {
  try {return new TextEncoder().encode(JSON.stringify(value)).length <= GLOW_LIMITS.requestBytes;} catch {return false;}
}
export function validGlowRecipe(value: unknown): value is GlowRecipe {
  if (!glowObject(value) || !glowExact(value, ['version', 'operation_id', 'math_identity', 'mode', 'strength', 'radius_px', 'threshold', 'exposure_ev', 'scattering', 'tint'])
    || value.version !== 1 || value.operation_id !== GLOW_OPERATION || value.math_identity !== GLOW_MATH
    || !GLOW_MODES.includes(value.mode as GlowMode) || !finite(value.strength, 0, 1) || !integer(value.radius_px, 0, 512)
    || !finite(value.threshold, 0, 1) || !finite(value.exposure_ev, -4, 4) || !finite(value.scattering, 0, 1) || !glowObject(value.tint)) return false;
  return glowExact(value.tint, ['hue_deg', 'saturation', 'lightness']) && finite(value.tint.hue_deg, -180, 180)
    && finite(value.tint.saturation, -1, 1) && finite(value.tint.lightness, -1, 1);
}
export function validGlowSource(value: unknown): value is GlowSource {
  return glowObject(value) && glowExact(value, ['sha256', 'width', 'height', 'orientation']) && glowHash(value.sha256)
    && integer(value.width, 2, 1_000_000) && integer(value.height, 2, 1_000_000) && value.orientation === 'exif_normalized_once';
}
export function validGlowOwner(value: unknown): value is GlowOwner {
  return glowObject(value) && glowExact(value, ['document_id', 'document_epoch', 'document_revision', 'source'])
    && glowId(value.document_id) && glowId(value.document_epoch) && glowRevision(value.document_revision) && validGlowSource(value.source);
}
export function validGlowEvidence(value: unknown, owner: GlowOwner): value is GlowSourceEvidence {
  return glowObject(value) && glowExact(value, ['kind', 'capture_version', 'original_sha256', 'people_graph_sha256', 'repair_stack_sha256', 'document_revision', 'load_id', 'capture_token'])
    && value.kind === 'current_full_edited_source' && value.capture_version === 3 && glowHash(value.original_sha256)
    && glowHash(value.people_graph_sha256) && glowHash(value.repair_stack_sha256) && value.document_revision === owner.document_revision
    && glowId(value.load_id) && glowId(value.capture_token);
}
export function validGlowPng(value: unknown): value is GlowPng {
  return glowObject(value) && glowExact(value, ['mime', 'width', 'height', 'sha256', 'base64']) && value.mime === 'image/png'
    && integer(value.width, 2, GLOW_LIMITS.imageEdge) && integer(value.height, 2, GLOW_LIMITS.imageEdge) && glowHash(value.sha256)
    && typeof value.base64 === 'string' && value.base64.length > 32 && value.base64.length <= Math.ceil(GLOW_LIMITS.imageBytes / 3) * 4
    && value.base64.length % 4 === 0 && /^iVBOR[A-Za-z0-9+/]*={0,2}$/.test(value.base64);
}
export const glowWholeFrame = (image: GlowPng, source: GlowSource): boolean => image.width <= source.width && image.height <= source.height
  && Math.abs(image.width * source.height - image.height * source.width) <= Math.max(source.width, source.height);
export function validGlowCapability(value: unknown): value is GlowCapability {
  return glowObject(value) && glowExact(value, ['version', 'operation_id', 'status', 'abi', 'math_version', 'reason', 'modes'])
    && value.version === 1 && value.operation_id === GLOW_OPERATION && value.abi === 1 && value.math_version === GLOW_MATH
    && (value.reason === null || message(value.reason)) && ['available', 'unavailable'].includes(String(value.status))
    && Array.isArray(value.modes) && value.modes.length <= GLOW_MODES.length && new Set(value.modes).size === value.modes.length
    && value.modes.every(mode => GLOW_MODES.includes(mode as GlowMode))
    && (value.status === 'available' ? value.modes.length > 0 : value.modes.length === 0);
}
export const unavailableGlowCapability = (reason: string): GlowCapability => ({version: 1, operation_id: GLOW_OPERATION,
  status: 'unavailable', abi: 1, math_version: GLOW_MATH, reason: reason.slice(0, 4096), modes: []});
export function validGlowContext(value: unknown): value is GlowContext {
  return glowObject(value) && glowExact(value, ['version', 'operation_id', 'session_id', 'owner', 'source_evidence', 'before', 'capability', 'message'])
    && value.version === 1 && value.operation_id === GLOW_OPERATION && glowId(value.session_id) && validGlowOwner(value.owner)
    && validGlowEvidence(value.source_evidence, value.owner) && validGlowPng(value.before) && glowWholeFrame(value.before, value.owner.source)
    && validGlowCapability(value.capability) && message(value.message);
}
export function validGlowCurrentReply(value: unknown, requestId: string): value is GlowCurrentReply {
  if (!glowObject(value) || value.event !== 'light_glow_result' || value.request_id !== requestId) return false;
  return value.status === 'ready' ? glowExact(value, ['event', 'request_id', 'status', 'context']) && validGlowContext(value.context)
    : glowExact(value, ['event', 'request_id', 'status', 'message']) && ['pending', 'unknown', 'cancelled', 'rejected'].includes(String(value.status)) && message(value.message);
}
export function validGlowReview(value: unknown, command: GlowPreviewCommand, context: Pick<GlowContext, 'owner' | 'source_evidence'> & {before: Pick<GlowPng, 'sha256'>}): value is GlowReview {
  if (!glowObject(value) || !glowExact(value, ['version', 'operation_id', 'request_id', 'session_id', 'owner', 'source_evidence', 'token', 'recipe', 'recipe_sha256',
    'result_source_sha256', 'coverage_sha256', 'before', 'after', 'coverage', 'no_change', 'notes'])
    || value.version !== 1 || value.operation_id !== GLOW_OPERATION || value.request_id !== command.request_id || value.session_id !== command.session_id
    || !validGlowOwner(value.owner) || !sameGlowOwner(value.owner, command.owner) || !sameGlowOwner(value.owner, context.owner)
    || !validGlowEvidence(value.source_evidence, value.owner) || glowKey(value.source_evidence) !== glowKey(context.source_evidence)
    || !glowId(value.token) || !validGlowRecipe(value.recipe) || glowKey(value.recipe) !== glowKey(command.recipe)
    || !glowHash(value.recipe_sha256) || !glowHash(value.result_source_sha256) || !glowHash(value.coverage_sha256)
    || !validGlowPng(value.before) || !validGlowPng(value.after) || !validGlowPng(value.coverage)
    || value.before.sha256 !== context.before.sha256 || !glowWholeFrame(value.before, command.owner.source)
    || value.before.width !== value.after.width || value.before.height !== value.after.height
    || value.before.width !== value.coverage.width || value.before.height !== value.coverage.height
    || typeof value.no_change !== 'boolean' || value.no_change !== (value.result_source_sha256 === command.owner.source.sha256)) return false;
  return Array.isArray(value.notes) && value.notes.length <= 32 && value.notes.every(message);
}
export const glowReviewKey = (review: GlowReview): string => glowKey([review.session_id, review.owner, review.source_evidence, review.token,
  review.recipe, review.recipe_sha256, review.result_source_sha256, review.coverage_sha256, review.before.sha256, review.after.sha256, review.coverage.sha256]);
export function validGlowWriteCommand(value: unknown): value is GlowWriteCommand {
  if (!glowObject(value) || value.version !== 1 || value.operation_id !== GLOW_OPERATION || !glowId(value.request_id) || !glowId(value.session_id)
    || !validGlowOwner(value.owner) || !glowRequestFits(value)) return false;
  const base = ['version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'token'];
  if (value.action === 'cancel') return glowExact(value, base) && (value.token === null || glowId(value.token));
  return value.action === 'apply' && glowExact(value, [...base, 'recipe_sha256', 'result_source_sha256', 'coverage_sha256', 'before_sha256', 'after_sha256', 'coverage_image_sha256', 'reviewed', 'return_mode'])
    && glowId(value.token) && glowHash(value.recipe_sha256) && glowHash(value.result_source_sha256) && glowHash(value.coverage_sha256)
    && glowHash(value.before_sha256) && glowHash(value.after_sha256) && glowHash(value.coverage_image_sha256) && value.reviewed === true && value.return_mode === 'new_image';
}
export function validGlowReceipt(value: unknown, command: GlowWriteCommand): value is GlowReceipt {
  const base = ['version', 'operation_id', 'request_id', 'session_id', 'action', 'owner', 'token', 'message', 'phase', 'outcome_unknown'];
  if (!validGlowWriteCommand(command) || !glowObject(value) || value.version !== 1 || value.operation_id !== GLOW_OPERATION
    || value.request_id !== command.request_id || value.session_id !== command.session_id || value.action !== command.action
    || value.token !== command.token || !validGlowOwner(value.owner) || !sameGlowOwner(value.owner, command.owner) || !message(value.message)) return false;
  if (value.phase === 'pending' || value.phase === 'unknown') return glowExact(value, base) && value.outcome_unknown === true;
  if (value.phase !== 'done' || value.outcome_unknown !== false) return false;
  if (value.outcome === 'rejected' || value.outcome === 'cancelled') return glowExact(value, [...base, 'outcome']) && (value.outcome !== 'cancelled' || command.action === 'cancel');
  return value.outcome === 'applied' && command.action === 'apply' && glowExact(value, [...base, 'outcome', 'result_document_id', 'copied_original_document_id', 'result_revision', 'result_source_sha256', 'no_change'])
    && glowId(value.result_document_id) && value.result_document_id !== command.owner.document_id && value.copied_original_document_id === command.owner.document_id
    && glowRevision(value.result_revision) && value.result_source_sha256 === command.result_source_sha256
    && typeof value.no_change === 'boolean' && value.no_change === (command.result_source_sha256 === command.owner.source.sha256);
}
