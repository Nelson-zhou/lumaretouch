// SPDX-License-Identifier: GPL-3.0-or-later
/** Independent AI native-dimension restoration contract. AUTHORED / UNRUN; not a lens-blur alias. */
export const UPSCALE_PROTOCOL = 1 as const;
export const UPSCALE_OPERATION = 'lnx.upscale_restore.v1' as const;
export const UPSCALE_MODEL = 'Swin2SR-classical-sr-x2-64' as const;
export const UPSCALE_LIMITS = {imageEdge: 1280, imageBytes: 4 * 1024 * 1024, requestBytes: 32 * 1024} as const;
export interface UpscaleRecipe {version: 1; model_id: typeof UPSCALE_MODEL}
export const upscaleDefaultRecipe = (): UpscaleRecipe => ({version: 1, model_id: UPSCALE_MODEL});

export interface UpscaleSource {sha256: string; width: number; height: number; orientation: 'exif_normalized_once'}
export interface UpscaleOwner {document_id: string; document_epoch: string; document_revision: string; source: UpscaleSource}
export interface UpscaleSourceEvidence {
  kind: 'current_full_edited_source'; capture_version: 3; original_sha256: string;
  people_graph_sha256: string; repair_stack_sha256: string; document_revision: string; load_id: string; capture_token: string;
}
export interface UpscalePng {mime: 'image/png'; width: number; height: number; sha256: string; base64: string}
export interface UpscaleCapability {
  version: 1; operation_id: typeof UPSCALE_OPERATION; status: 'available' | 'unavailable';
  reason: string | null; model_id: typeof UPSCALE_MODEL; acceptance: 'unrun'; output_mode: 'restore_native_dimensions';
}
export interface UpscaleContext {
  version: 1; operation_id: typeof UPSCALE_OPERATION; session_id: string; owner: UpscaleOwner;
  source_evidence: UpscaleSourceEvidence; before: UpscalePng; capability: UpscaleCapability; message: string;
}
export interface UpscalePreviewCommand {
  version: 1; operation_id: typeof UPSCALE_OPERATION; action: 'preview'; request_id: string;
  session_id: string; owner: UpscaleOwner; recipe: UpscaleRecipe;
}
export interface UpscaleReview {
  version: 1; operation_id: typeof UPSCALE_OPERATION; request_id: string; session_id: string; owner: UpscaleOwner;
  source_evidence: UpscaleSourceEvidence; token: string; recipe: UpscaleRecipe; recipe_sha256: string;
  result_source_sha256: string; before: UpscalePng; after: UpscalePng;
  no_change: boolean; notes: string[];
}
export interface UpscaleApplyCommand {
  version: 1; operation_id: typeof UPSCALE_OPERATION; action: 'apply'; request_id: string; session_id: string; owner: UpscaleOwner;
  token: string; recipe_sha256: string; result_source_sha256: string;
  before_sha256: string; after_sha256: string; reviewed: true; return_mode: 'new_image';
}
export interface UpscaleCancelCommand {
  version: 1; operation_id: typeof UPSCALE_OPERATION; action: 'cancel'; request_id: string;
  session_id: string; owner: UpscaleOwner; token: string | null;
}
export type UpscaleWriteCommand = UpscaleApplyCommand | UpscaleCancelCommand;
interface ReceiptIdentity {
  version: 1; operation_id: typeof UPSCALE_OPERATION; request_id: string; session_id: string;
  action: UpscaleWriteCommand['action']; owner: UpscaleOwner; token: string | null; message: string;
}
export type UpscaleReceipt = ReceiptIdentity & (
  | {phase: 'pending' | 'unknown'; outcome_unknown: true}
  | {phase: 'done'; outcome_unknown: false; outcome: 'rejected' | 'cancelled'}
  | {phase: 'done'; outcome_unknown: false; outcome: 'applied'; result_document_id: string;
    copied_original_document_id: string; result_revision: string; result_source_sha256: string; no_change: boolean}
);
export type UpscaleCurrentReply = {event: 'upscale_restore_result'; request_id: string} & (
  | {status: 'ready'; context: UpscaleContext}
  | {status: 'pending' | 'unknown' | 'cancelled' | 'rejected'; message: string}
);

/** Real adapter required. The port owns request/receipt lifetime, not panel visibility. */
export interface UpscaleRestorePort {
  readonly protocol: typeof UPSCALE_PROTOCOL;
  refreshCapability(): Promise<unknown>;
  acquireCurrent(requestId: string): Promise<unknown>;
  currentStatus(requestId: string): Promise<unknown>;
  cancelCurrent(requestId: string): Promise<void>;
  /** Resolve the inner review only; retain read identity after timeout and never resend it. */
  preview(command: UpscalePreviewCommand): Promise<unknown>;
  submit(command: UpscaleWriteCommand): Promise<unknown>;
  receipt(command: UpscaleWriteCommand): Promise<unknown>;
  cancelReads(): Promise<void>;
  checkReads(): Promise<void>;
  pendingReads(): boolean;
  subscribe(listener: () => void): () => void;
  requestReconciliation?(command: UpscaleWriteCommand): void;
}

export const upscaleObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export const upscaleExact = (value: Record<string, unknown>, keys: readonly string[]): boolean => Object.keys(value).sort().join('|') === [...keys].sort().join('|');
export const upscaleHash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export const upscaleId = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value);
const message = (value: unknown): value is string => typeof value === 'string' && value.length <= 4096 && !value.includes('\0');
const finite = (value: unknown, min: number, max: number): value is number => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
const integer = (value: unknown, min: number, max: number): value is number => finite(value, min, max) && Number.isSafeInteger(value);
export const upscaleRevision = (value: unknown): value is string => typeof value === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(value) && BigInt(value) <= 18446744073709551615n;
export function upscaleKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(upscaleKey).join(',')}]`;
  if (upscaleObject(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${upscaleKey(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export function freezeUpscale<T>(value: T): T {
  const copy = structuredClone(value);
  const freeze = (item: unknown): void => {if (item && typeof item === 'object') {Object.values(item).forEach(freeze); Object.freeze(item);}};
  freeze(copy); return copy;
}
export const sameUpscaleOwner = (a: UpscaleOwner, b: UpscaleOwner): boolean => upscaleKey(a) === upscaleKey(b);
export function upscaleRequestFits(value: unknown): boolean {
  try {return new TextEncoder().encode(JSON.stringify(value)).length <= UPSCALE_LIMITS.requestBytes;} catch {return false;}
}
export function validUpscaleRecipe(value: unknown): value is UpscaleRecipe {
  return upscaleObject(value) && upscaleExact(value, ['version', 'model_id']) && value.version === 1 && value.model_id === UPSCALE_MODEL;
}
export function validUpscaleSource(value: unknown): value is UpscaleSource {
  return upscaleObject(value) && upscaleExact(value, ['sha256', 'width', 'height', 'orientation']) && upscaleHash(value.sha256)
    && integer(value.width, 16, 1024) && integer(value.height, 16, 1024) && value.width * value.height <= 1_048_576 && value.orientation === 'exif_normalized_once';
}
export function validUpscaleOwner(value: unknown): value is UpscaleOwner {
  return upscaleObject(value) && upscaleExact(value, ['document_id', 'document_epoch', 'document_revision', 'source'])
    && upscaleId(value.document_id) && upscaleId(value.document_epoch) && upscaleRevision(value.document_revision) && validUpscaleSource(value.source);
}
export function validUpscaleEvidence(value: unknown, owner: UpscaleOwner): value is UpscaleSourceEvidence {
  return upscaleObject(value) && upscaleExact(value, ['kind', 'capture_version', 'original_sha256', 'people_graph_sha256', 'repair_stack_sha256', 'document_revision', 'load_id', 'capture_token'])
    && value.kind === 'current_full_edited_source' && value.capture_version === 3 && upscaleHash(value.original_sha256)
    && upscaleHash(value.people_graph_sha256) && upscaleHash(value.repair_stack_sha256) && value.document_revision === owner.document_revision
    && upscaleId(value.load_id) && upscaleId(value.capture_token);
}
export function validUpscalePng(value: unknown): value is UpscalePng {
  return upscaleObject(value) && upscaleExact(value, ['mime', 'width', 'height', 'sha256', 'base64']) && value.mime === 'image/png'
    && integer(value.width, 2, UPSCALE_LIMITS.imageEdge) && integer(value.height, 2, UPSCALE_LIMITS.imageEdge) && upscaleHash(value.sha256)
    && typeof value.base64 === 'string' && value.base64.length > 32 && value.base64.length <= Math.ceil(UPSCALE_LIMITS.imageBytes / 3) * 4
    && value.base64.length % 4 === 0 && /^iVBOR[A-Za-z0-9+/]*={0,2}$/.test(value.base64);
}
export const upscaleWholeFrame = (image: UpscalePng, source: UpscaleSource): boolean => image.width <= source.width && image.height <= source.height
  && Math.abs(image.width * source.height - image.height * source.width) <= Math.max(source.width, source.height);
export function validUpscaleCapability(value: unknown): value is UpscaleCapability {
  return upscaleObject(value) && upscaleExact(value, ['version', 'operation_id', 'status', 'reason', 'model_id', 'acceptance', 'output_mode'])
    && value.version === 1 && value.operation_id === UPSCALE_OPERATION && value.model_id === UPSCALE_MODEL && value.acceptance === 'unrun' && value.output_mode === 'restore_native_dimensions'
    && (value.reason === null || message(value.reason)) && ['available', 'unavailable'].includes(String(value.status));
}
export const unavailableUpscaleCapability = (reason: string): UpscaleCapability => ({version: 1, operation_id: UPSCALE_OPERATION,
  status: 'unavailable', model_id: UPSCALE_MODEL, acceptance: 'unrun', output_mode: 'restore_native_dimensions', reason: reason.slice(0, 4096)});
export function validUpscaleContext(value: unknown): value is UpscaleContext {
  return upscaleObject(value) && upscaleExact(value, ['version', 'operation_id', 'session_id', 'owner', 'source_evidence', 'before', 'capability', 'message'])
    && value.version === 1 && value.operation_id === UPSCALE_OPERATION && upscaleId(value.session_id) && validUpscaleOwner(value.owner)
    && validUpscaleEvidence(value.source_evidence, value.owner) && validUpscalePng(value.before) && upscaleWholeFrame(value.before, value.owner.source)
    && validUpscaleCapability(value.capability) && message(value.message);
}
export function validUpscaleCurrentReply(value: unknown, requestId: string): value is UpscaleCurrentReply {
  if (!upscaleObject(value) || value.event !== 'upscale_restore_result' || value.request_id !== requestId) return false;
  return value.status === 'ready' ? upscaleExact(value, ['event', 'request_id', 'status', 'context']) && validUpscaleContext(value.context)
    : upscaleExact(value, ['event', 'request_id', 'status', 'message']) && ['pending', 'unknown', 'cancelled', 'rejected'].includes(String(value.status)) && message(value.message);
}
export function validUpscaleReview(value: unknown, command: UpscalePreviewCommand, context: Pick<UpscaleContext, 'owner' | 'source_evidence'> & {before: Pick<UpscalePng, 'sha256'>}): value is UpscaleReview {
  if (!upscaleObject(value) || !upscaleExact(value, ['version', 'operation_id', 'request_id', 'session_id', 'owner', 'source_evidence', 'token', 'recipe', 'recipe_sha256',
    'result_source_sha256', 'before', 'after', 'no_change', 'notes'])
    || value.version !== 1 || value.operation_id !== UPSCALE_OPERATION || value.request_id !== command.request_id || value.session_id !== command.session_id
    || !validUpscaleOwner(value.owner) || !sameUpscaleOwner(value.owner, command.owner) || !sameUpscaleOwner(value.owner, context.owner)
    || !validUpscaleEvidence(value.source_evidence, value.owner) || upscaleKey(value.source_evidence) !== upscaleKey(context.source_evidence)
    || !upscaleId(value.token) || !validUpscaleRecipe(value.recipe) || upscaleKey(value.recipe) !== upscaleKey(command.recipe)
    || !upscaleHash(value.recipe_sha256) || !upscaleHash(value.result_source_sha256)
    || !validUpscalePng(value.before) || !validUpscalePng(value.after)
    || value.before.sha256 !== context.before.sha256 || !upscaleWholeFrame(value.before, command.owner.source)
    || value.before.width !== value.after.width || value.before.height !== value.after.height
    || typeof value.no_change !== 'boolean' || value.no_change !== (value.result_source_sha256 === command.owner.source.sha256)) return false;
  return Array.isArray(value.notes) && value.notes.length <= 32 && value.notes.every(message);
}
export const upscaleReviewKey = (review: UpscaleReview): string => upscaleKey([review.session_id, review.owner, review.source_evidence, review.token,
  review.recipe, review.recipe_sha256, review.result_source_sha256, review.before.sha256, review.after.sha256]);
export function validUpscaleWriteCommand(value: unknown): value is UpscaleWriteCommand {
  if (!upscaleObject(value) || value.version !== 1 || value.operation_id !== UPSCALE_OPERATION || !upscaleId(value.request_id) || !upscaleId(value.session_id)
    || !validUpscaleOwner(value.owner) || !upscaleRequestFits(value)) return false;
  const base = ['version', 'operation_id', 'action', 'request_id', 'session_id', 'owner', 'token'];
  if (value.action === 'cancel') return upscaleExact(value, base) && (value.token === null || upscaleId(value.token));
  return value.action === 'apply' && upscaleExact(value, [...base, 'recipe_sha256', 'result_source_sha256', 'before_sha256', 'after_sha256', 'reviewed', 'return_mode'])
    && upscaleId(value.token) && upscaleHash(value.recipe_sha256) && upscaleHash(value.result_source_sha256)
    && upscaleHash(value.before_sha256) && upscaleHash(value.after_sha256) && value.reviewed === true && value.return_mode === 'new_image';
}
export function validUpscaleReceipt(value: unknown, command: UpscaleWriteCommand): value is UpscaleReceipt {
  const base = ['version', 'operation_id', 'request_id', 'session_id', 'action', 'owner', 'token', 'message', 'phase', 'outcome_unknown'];
  if (!validUpscaleWriteCommand(command) || !upscaleObject(value) || value.version !== 1 || value.operation_id !== UPSCALE_OPERATION
    || value.request_id !== command.request_id || value.session_id !== command.session_id || value.action !== command.action
    || value.token !== command.token || !validUpscaleOwner(value.owner) || !sameUpscaleOwner(value.owner, command.owner) || !message(value.message)) return false;
  if (value.phase === 'pending' || value.phase === 'unknown') return upscaleExact(value, base) && value.outcome_unknown === true;
  if (value.phase !== 'done' || value.outcome_unknown !== false) return false;
  if (value.outcome === 'rejected' || value.outcome === 'cancelled') return upscaleExact(value, [...base, 'outcome']) && (value.outcome !== 'cancelled' || command.action === 'cancel');
  return value.outcome === 'applied' && command.action === 'apply' && upscaleExact(value, [...base, 'outcome', 'result_document_id', 'copied_original_document_id', 'result_revision', 'result_source_sha256', 'no_change'])
    && upscaleId(value.result_document_id) && value.result_document_id !== command.owner.document_id && value.copied_original_document_id === command.owner.document_id
    && upscaleRevision(value.result_revision) && value.result_source_sha256 === command.result_source_sha256
    && typeof value.no_change === 'boolean' && value.no_change === (command.result_source_sha256 === command.owner.source.sha256);
}
