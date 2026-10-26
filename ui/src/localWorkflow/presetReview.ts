// SPDX-License-Identifier: GPL-3.0-or-later
/** Exact workflow handoff DTOs. None of these helpers dispatch ordinary preset commands. */
export type ReviewSide = 'before' | 'after';
export type ReviewStep = 'open_target' | 'prepare_skin' | 'approve' | 'save_project' | 'return_target';
export interface PresetTarget {document_id: string; load_id: string; revision: string}
export interface PresetImage {mime: 'image/png'; width: number; height: number; sha256: string; byte_length: number; page_count: number}
export interface WorkflowPresetReview {
  schema: 'lrt.workflow-preset-review.v1'; review_id: string; review_sha256: string; target: PresetTarget;
  preset_id: string; preset_sha256: string; module_ids: string[]; before: PresetImage; after: PresetImage;
  source_proof: Record<string, unknown>; source_size: [number, number]; output_size: [number, number];
  before_state_sha256: string; candidate_state_sha256: string; people_sha256: string; repair_sha256: string;
  before_render_sha256: string; candidate_render_sha256: string;
  page_bytes: 65536; ttl_seconds: 900; approval_only: true; runtime_verified: false;
}
export interface WorkflowPresetHandoff {
  mode?: 'automatic';
  version: 1; operation_id: string; document_id: string; preset_id: string; preset_sha256: string;
  phase: 'awaiting_open' | 'awaiting_preparation' | 'reviewing' | 'authorized' | 'awaiting_save' | 'awaiting_return' | 'unknown';
  review: WorkflowPresetReview | null; message: string;
}
export interface ReviewImageInput {port_version: 1; run_id: string; operation_id: string; review_id: string; review_sha256: string; side: ReviewSide; sha256: string; page: number}
export interface ReviewImagePage extends PresetImage {
  review_id: string; review_sha256: string; target: PresetTarget; side: ReviewSide;
  page: number; page_bytes: 65536; offset: number; page_byte_length: number; page_sha256: string; base64: string;
}
export interface PresetReviewAck {
  review_id: string; review_sha256: string; target: PresetTarget; preset_id: string; preset_sha256: string;
  before_sha256: string; after_sha256: string; accepted: true;
}
export interface ReviewImages {
  key: string; loading: boolean; error: string; before: string | null; after: string | null;
  displayed: {before: boolean; after: boolean}; acknowledged: boolean;
}
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const exact = (value: unknown, keys: readonly string[]): value is Record<string, unknown> => object(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
const token = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9._:-]{1,128}$/.test(value);
const hash = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const integer = (value: unknown, low: number, high: number): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= low && value <= high;
const imageKeys = ['mime', 'width', 'height', 'sha256', 'byte_length', 'page_count'] as const;
function target(value: unknown): value is PresetTarget {
  return exact(value, ['document_id', 'load_id', 'revision']) && token(value.document_id) && token(value.load_id) &&
    typeof value.revision === 'string' && /^(0|[1-9][0-9]{0,19})$/.test(value.revision) && BigInt(value.revision) <= 18446744073709551615n;
}
function image(value: unknown): value is PresetImage {
  return exact(value, imageKeys) && value.mime === 'image/png' && hash(value.sha256) &&
    integer(value.width, 1, 4096) && integer(value.height, 1, 4096) && integer(value.byte_length, 33, 4 * 1024 * 1024) &&
    value.page_count === Math.ceil(value.byte_length / 65536);
}
function dimensions(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2 && value.every(n => integer(n, 1, 32_000_000)) && value[0] * value[1] <= 32_000_000;
}
export function checkedReview(value: unknown): WorkflowPresetReview | null {
  if (!exact(value, ['schema', 'review_id', 'target', 'preset_id', 'preset_sha256', 'module_ids', 'before', 'after', 'source_proof',
    'source_size', 'output_size', 'before_state_sha256', 'candidate_state_sha256', 'people_sha256', 'repair_sha256',
    'before_render_sha256', 'candidate_render_sha256', 'page_bytes', 'ttl_seconds', 'approval_only', 'runtime_verified', 'review_sha256']) ||
    value.schema !== 'lrt.workflow-preset-review.v1' || !token(value.review_id) || !target(value.target) || !token(value.preset_id) ||
    !['preset_sha256', 'review_sha256', 'before_state_sha256', 'candidate_state_sha256', 'people_sha256', 'repair_sha256', 'before_render_sha256', 'candidate_render_sha256'].every(key => hash(value[key])) ||
    !image(value.before) || !image(value.after) || value.before.width !== value.after.width || value.before.height !== value.after.height ||
    !dimensions(value.source_size) || !dimensions(value.output_size) || !object(value.source_proof) ||
    !Array.isArray(value.module_ids) || !value.module_ids.length || value.module_ids.length > 3 || new Set(value.module_ids).size !== value.module_ids.length ||
    !value.module_ids.every(id => id === 'lnx.exposure.v1' || id === 'lnx.white_balance.v1' || id === 'lnx.skin.v1') ||
    value.page_bytes !== 65536 || value.ttl_seconds !== 900 || value.approval_only !== true || value.runtime_verified !== false ||
    new TextEncoder().encode(JSON.stringify(value)).length > 256 * 1024) return null;
  return structuredClone(value) as unknown as WorkflowPresetReview;
}
export function checkedHandoff(value: unknown): WorkflowPresetHandoff | null {
  const automatic = object(value) && value.mode === 'automatic';
  if (!exact(value, ['version', 'operation_id', 'document_id', 'preset_id', 'preset_sha256', 'phase', 'review', 'message', ...(automatic ? ['mode'] : [])]) ||
    value.version !== 1 || !hash(value.operation_id) || !token(value.document_id) || !token(value.preset_id) || !hash(value.preset_sha256) ||
    !['awaiting_open', 'awaiting_preparation', 'reviewing', 'authorized', 'awaiting_save', 'awaiting_return', 'unknown'].includes(String(value.phase)) ||
    typeof value.message !== 'string' || value.message.length > 8192 || /[\u0000-\u001f\u007f]/.test(value.message)) return null;
  if (automatic && (value.review !== null || !['authorized', 'unknown'].includes(String(value.phase)))) return null;
  const review = value.review === null ? null : checkedReview(value.review);
  if ((value.review !== null && !review) || (value.phase === 'reviewing' && !review) ||
    (review && (review.target.document_id !== value.document_id || review.preset_id !== value.preset_id || review.preset_sha256 !== value.preset_sha256))) return null;
  return {...structuredClone(value), review} as unknown as WorkflowPresetHandoff;
}
export function reviewKey(runId: string, handoff: WorkflowPresetHandoff): string {
  // Bind every proof, including target revision and both byte sequences. A
  // delayed image callback cannot acknowledge a replacement report.
  return JSON.stringify([runId, handoff.operation_id, handoff.review]);
}
export function reviewAck(review: WorkflowPresetReview): PresetReviewAck {
  return {review_id: review.review_id, review_sha256: review.review_sha256, target: {...review.target}, preset_id: review.preset_id,
    preset_sha256: review.preset_sha256, before_sha256: review.before.sha256, after_sha256: review.after.sha256, accepted: true};
}
async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
function base64(bytes: Uint8Array): string {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 16384) binary += String.fromCharCode(...bytes.subarray(offset, offset + 16384));
  return btoa(binary);
}
export async function fetchReviewImage(runId: string, handoff: WorkflowPresetHandoff, side: ReviewSide,
  read: (input: ReviewImageInput) => Promise<unknown>, current: () => boolean): Promise<string> {
  const report = handoff.review;
  if (!report || !checkedReview(report)) throw Error('没有匹配的真实图像审核。');
  const metadata = report[side], bytes = new Uint8Array(metadata.byte_length);
  for (let page = 0; page < metadata.page_count; page += 1) {
    if (!current()) throw Error('审核内容已变化，旧图像不能继续用于批准。');
    const input: ReviewImageInput = {port_version: 1, run_id: runId, operation_id: handoff.operation_id, review_id: report.review_id,
      review_sha256: report.review_sha256, side, sha256: metadata.sha256, page};
    const value = await read(input);
    if (!current() || !exact(value, ['review_id', 'review_sha256', 'target', 'side', ...imageKeys, 'page', 'page_bytes', 'offset', 'page_byte_length', 'page_sha256', 'base64']) ||
      value.review_id !== report.review_id || value.review_sha256 !== report.review_sha256 || !target(value.target) ||
      value.target.document_id !== report.target.document_id || value.target.load_id !== report.target.load_id || value.target.revision !== report.target.revision ||
      value.side !== side || value.page !== page || value.page_bytes !== 65536 || value.offset !== page * 65536 ||
      !imageKeys.every(key => value[key] === metadata[key]) || !hash(value.page_sha256) ||
      typeof value.base64 !== 'string' || value.base64.length > 87384 ||
      value.page_byte_length !== Math.min(65536, metadata.byte_length - page * 65536)) throw Error('审核图像页面的身份或范围不匹配。');
    let chunk: Uint8Array;
    try {chunk = Uint8Array.from(atob(value.base64), char => char.charCodeAt(0));} catch {throw Error('审核图像页面编码无效。');}
    if (chunk.length !== value.page_byte_length || base64(chunk) !== value.base64 || await sha256(chunk) !== value.page_sha256 || !current())
      throw Error('审核图像页面 SHA-256 校验失败。');
    bytes.set(chunk, page * 65536);
  }
  if (!current() || await sha256(bytes) !== metadata.sha256) throw Error('完整审核图像 SHA-256 校验失败。');
  const header = new DataView(bytes.buffer);
  if ([137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82].some((n, index) => bytes[index] !== n) ||
    header.getUint32(16) !== metadata.width || header.getUint32(20) !== metadata.height ||
    bytes[24] !== 8 || bytes[25] !== 2 || bytes[26] !== 0 || bytes[27] !== 0 || bytes[28] !== 0) throw Error('审核 PNG 的真实尺寸或格式与报告不一致。');
  return `data:image/png;base64,${base64(bytes)}`;
}
