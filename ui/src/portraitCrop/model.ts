// SPDX-License-Identifier: GPL-3.0-or-later
/** Portrait composition protocol only. The host owns capture, rendering and history. */
export const PORTRAIT_CROP_CONTROLS = {
  workspace: 'control:PC-32478:9', headroom: 'control:PC-32478:15',
  headFraction: 'control:PC-32478:16', facePosition: 'control:PC-32478:17',
  presets: 'control:PC-32478:18',
} as const;
export type Point = [number, number];
export type AnchorName = 'crown' | 'chin' | 'face_center';
export type Anchors = {version: 1; crown: Point; chin: Point; face_center: Point};
export type Rules = {version: 1; aspect_ratio: number; headroom_fraction: number; head_fraction: number; horizontal_position: number};
export type RuleDraft = Record<Exclude<keyof Rules, 'version'>, string>;
export const emptyRules = (): RuleDraft => ({aspect_ratio: '', headroom_fraction: '', head_fraction: '', horizontal_position: ''});
export type ImageProof = {
  mime: 'image/png'; width: number; height: number; sha256: string; base64: string;
  source_width: number; source_height: number; mapping: 'normalized_full_frame';
};
export type FaceProposal = {face_id: string; landmarks_sha256: string; bbox: [number, number, number, number]; chin_proposal: Point; center_proposal: Point};
export type Binding = {
  document_id: string; revision: string | number; document_epoch: string | number; load_id: string;
  original_sha256: string; source_proof: Record<string, unknown>; state_sha256: string;
  non_crop_sha256: string; people_sha256: string; repair_sha256: string; uncropped_sha256: string;
};
export type Current = {
  session_id: string; capture_sha256: string; binding: Binding;
  source: {width: number; height: number; orientation: 'exif_normalized_once'; mapping: 'source_edge_pixels';
    source_sha256: string; analysis_sha256: string; model_sha256: string; semantic_model_sha256: string;
    proxy_sha256: string; proxy_size: [number, number]; inference: 'fresh_whole_frame_display_proxy'; image: ImageProof; faces: FaceProposal[]};
  before: ImageProof;
};
export type Measurements = {aspect_ratio: number; headroom_fraction: number; head_fraction: number; horizontal_position: number; vertical_position: number};
export type Plan = {
  version: 1; convention: 'lrt.portrait-crop.source-edge-pixels.v1'; operation_id: 'lnx.crop.v1'; rotation_degrees: 0;
  source_size: [number, number]; anchors: Anchors; rules: Rules;
  continuous_rect_pixels: [number, number, number, number]; rect_normalized: [number, number, number, number];
  pixel_bounds: [number, number, number, number]; output_size: [number, number];
  requested: Measurements; achieved: Measurements & {head_height_pixels: number};
  is_full_frame: boolean; backend: 'rust-portrait-crop-v1';
};
export type Preview = {preview_token: string; capture_sha256: string; candidate_sha256: string; preview_request_id: string; plan: Plan; before: ImageProof; after: ImageProof};
export type Action = 'capability' | 'current' | 'preview' | 'apply' | 'status' | 'cancel';
export type Request = {cmd: 'portrait_crop'; action: Action; request_id: string} & Record<string, unknown>;
export type Receipt = {
  event: 'portrait_crop_result'; version: 1; request_id: string; action: Action; command_sha256: string;
  original_request: Request;
  phase: 'working' | 'capability' | 'current_ready' | 'ready' | 'committed' | 'cancelled' | 'rejected' | 'unknown' | 'status';
  no_write?: boolean; outcome_unknown?: boolean; original_request_id?: string; message?: string; error?: string;
  current?: Current; preview?: Preview; receipt?: Receipt;
  capability?: {available: boolean; reason: string | null; version: 1; operation_id: 'lnx.crop.v1'; supported_rotation_degrees: number[]};
  result?: {status: 'applied' | 'no_change'; document_id: string; revision: string | number};
  preview_token?: string; candidate_sha256?: string;
};
export type Transport = {
  /** Send exactly once; progress is optional. Do not manufacture a receipt after a timeout. */
  send: (request: Request, onReceipt?: (receipt: unknown) => void) => Promise<unknown>;
  /** Query the ORIGINAL immutable request. A missing mailbox is not a no-write result. */
  status: (original: Request) => Promise<unknown>;
  cancelRead?: (original: Request, commandSha256: string) => Promise<unknown>;
};
export const record = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
export const digest = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const token = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 256;
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const extent = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) > 0 && Number(v) <= 1_000_000;
const revision = (v: unknown): boolean => (typeof v === 'string' && /^\d{1,20}$/.test(v)) || (Number.isSafeInteger(v) && Number(v) >= 0);
/** Structural wire equality, not a false claim of Python JSON byte equivalence. */
export function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => equal(v, b[i]));
  if (!record(a) || !record(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.hasOwn(b, key) && equal(a[key], b[key]));
}
export function point(v: unknown, width: number, height: number): v is Point {
  return Array.isArray(v) && v.length === 2 && finite(v[0]) && finite(v[1]) && v[0] >= 0 && v[0] <= width && v[1] >= 0 && v[1] <= height;
}
export function checkedAnchors(value: Partial<Anchors>, width: number, height: number): Anchors {
  if (!point(value.crown, width, height) || !point(value.chin, width, height) || !point(value.face_center, width, height)) throw Error('请在当前完整照片上填写三项来源像素坐标。');
  if (value.crown[1] >= value.chin[1] || value.face_center[1] < value.crown[1] || value.face_center[1] > value.chin[1]) throw Error('头顶必须高于下巴，所选人脸中心须位于两者之间。');
  return {version: 1, crown: [...value.crown], chin: [...value.chin], face_center: [...value.face_center]};
}
/** These are local geometric limits, never undisclosed PixCake defaults or ranges. */
export function checkedRules(draft: RuleDraft): Rules {
  const read = (key: keyof RuleDraft) => {
    const text = draft[key].trim();
    if (!text || text.length > 32) throw Error('请明确输入全部构图比例，不会采用隐藏默认值。');
    if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(text)) throw Error('请输入十进制数字比例。');
    const value = Number(text); if (!Number.isFinite(value)) throw Error('构图比例必须是有限数字。'); return value;
  };
  const value: Rules = {version: 1, aspect_ratio: read('aspect_ratio'), headroom_fraction: read('headroom_fraction'), head_fraction: read('head_fraction'), horizontal_position: read('horizontal_position')};
  if (value.aspect_ratio < 0.001 || value.aspect_ratio > 1000) throw Error('本地宽高比输入范围为 0.001–1000（宽 ÷ 高），不是官方范围。');
  if (value.headroom_fraction < 0 || value.headroom_fraction > 1 || value.head_fraction <= 0 || value.head_fraction > 1 || value.horizontal_position < 0 || value.horizontal_position > 1) throw Error('比例使用 0–1；头部占比必须大于 0。');
  if (value.headroom_fraction + value.head_fraction > 1) throw Error('头顶留白与头部占比之和不能超过 1。');
  return value;
}
export function validImage(value: unknown): value is ImageProof {
  if (!record(value) || value.mime !== 'image/png' || value.mapping !== 'normalized_full_frame' || !extent(value.width) || !extent(value.height) || !extent(value.source_width) || !extent(value.source_height) || !digest(value.sha256)) return false;
  if (value.width > value.source_width || value.height > value.source_height || Math.abs(value.width * value.source_height - value.height * value.source_width) > Math.max(value.source_width, value.source_height)) return false;
  return typeof value.base64 === 'string' && value.base64.length > 0 && value.base64.length <= 12_000_000 && value.base64.length % 4 === 0 && value.base64.startsWith('iVBOR') && /^[A-Za-z0-9+/]+={0,2}$/.test(value.base64);
}
export function checkedCurrent(value: unknown): Current {
  if (!record(value) || !token(value.session_id) || !digest(value.capture_sha256) || !record(value.binding) || !record(value.source) || !validImage(value.before)) throw Error('当前照片捕获凭据不完整，不能测量。');
  const b = value.binding, s = value.source;
  if (!token(b.document_id) || !token(b.load_id) || !revision(b.revision) || !(token(b.document_epoch) || revision(b.document_epoch)) || !record(b.source_proof) || ['original_sha256', 'state_sha256', 'non_crop_sha256', 'people_sha256', 'repair_sha256', 'uncropped_sha256'].some(k => !digest(b[k]))) throw Error('来源、文档、编辑或修复绑定不完整。');
  if (s.source_sha256 !== b.uncropped_sha256 || !extent(s.width) || !extent(s.height) || s.orientation !== 'exif_normalized_once' || s.mapping !== 'source_edge_pixels' || ['source_sha256', 'analysis_sha256', 'model_sha256', 'semantic_model_sha256', 'proxy_sha256'].some(k => !digest(s[k])) || s.inference !== 'fresh_whole_frame_display_proxy' || !Array.isArray(s.proxy_size) || !equal(s.proxy_size, [s.image && record(s.image) ? s.image.width : null, s.image && record(s.image) ? s.image.height : null]) || !validImage(s.image) || s.image.source_width !== s.width || s.image.source_height !== s.height || !Array.isArray(s.faces) || s.faces.length > 128) throw Error('缺少当前完整编辑照片的真实像素映射和人脸分析。');
  const proof = b.source_proof;
  if (proof.original_sha256 !== b.original_sha256 || !digest(proof.asset_sha256) || !(proof.creative_source === null || (record(proof.creative_source) && proof.creative_source.sha256 === proof.asset_sha256 && proof.creative_source.width === s.width && proof.creative_source.height === s.height))) throw Error('原始或派生来源证明与完整像素网格不一致。');
  if (proof.creative_source === null && proof.asset_sha256 !== proof.original_sha256) throw Error('原始来源证明哈希不一致。');
  const ids = new Set<string>();
  for (const face of s.faces) {
    if (!record(face) || !token(face.face_id) || ids.has(face.face_id) || !digest(face.landmarks_sha256) || !point(face.chin_proposal, s.width, s.height) || !point(face.center_proposal, s.width, s.height) || !Array.isArray(face.bbox) || face.bbox.length !== 4 || !point(face.bbox.slice(0, 2), s.width, s.height) || !point(face.bbox.slice(2, 4), s.width, s.height) || face.bbox[0] >= face.bbox[2] || face.bbox[1] >= face.bbox[3]) throw Error('当前人脸提议的来源像素坐标或身份不可靠。');
    ids.add(face.face_id);
  }
  return structuredClone(value) as unknown as Current;
}
function measures(v: unknown): v is Measurements {
  return record(v) && ['aspect_ratio', 'headroom_fraction', 'head_fraction', 'horizontal_position', 'vertical_position'].every(k => finite(v[k]));
}
export function checkedPreview(value: unknown, current: Current, request: Request): Preview {
  if (!record(value) || !token(value.preview_token) || value.capture_sha256 !== current.capture_sha256 || !digest(value.candidate_sha256) || value.preview_request_id !== request.request_id || !validImage(value.before) || !validImage(value.after) || !equal(value.before, current.before) || !record(value.plan)) throw Error('候选预览不属于本次完整照片和原始构图请求。');
  const p = value.plan, w = current.source.width, h = current.source.height;
  if (p.version !== 1 || p.convention !== 'lrt.portrait-crop.source-edge-pixels.v1' || p.operation_id !== 'lnx.crop.v1' || p.backend !== 'rust-portrait-crop-v1' || p.rotation_degrees !== 0 || !equal(p.source_size, [w, h]) || !equal(p.anchors, request.anchors) || !equal(p.rules, request.rules) || !measures(p.requested) || !measures(p.achieved) || !record(p.achieved) || !finite(p.achieved.head_height_pixels) || typeof p.is_full_frame !== 'boolean') throw Error('裁剪计算结果的请求回显、旋转或来源尺寸不一致。');
  const achieved = p.achieved, requested = p.requested;
  const r = p.pixel_bounds, n = p.rect_normalized, c = p.continuous_rect_pixels;
  if (!Array.isArray(r) || r.length !== 4 || !r.every(Number.isSafeInteger) || r[0] < 0 || r[1] < 0 || r[2] > w || r[3] > h || r[0] >= r[2] || r[1] >= r[3] || !equal(p.output_size, [r[2] - r[0], r[3] - r[1]]) || !Array.isArray(n) || !equal(n, [r[0] / w, r[1] / h, r[2] / w, r[3] / h]) || !Array.isArray(c) || c.length !== 4 || !c.every(finite)) throw Error('候选必须具有真实整数像素边界，不能以 CSS 或中心框代替。');
  if (value.after.source_width !== r[2] - r[0] || value.after.source_height !== r[3] - r[1]) throw Error('候选图片尺寸与实际裁剪输出不一致。');
  const a = request.anchors as Anchors;
  if ([a.crown, a.chin, a.face_center].some(pt => pt[0] < r[0] || pt[0] > r[2] || pt[1] < r[1] || pt[1] > r[3])) throw Error('像素舍入后的裁剪排除了已确认的头部锚点。');
  if (c[0] < 0 || c[1] < 0 || c[2] > w || c[3] > h || c[0] >= c[2] || c[1] >= c[3] || c.some((v, i) => Math.abs(v - r[i]) > 0.500000001)) throw Error('连续构图与实际像素舍入边界不一致。');
  const rules = request.rules as Rules, head = a.chin[1] - a.crown[1], outputWidth = r[2] - r[0], outputHeight = r[3] - r[1];
  const near = (x: number, y: number) => Math.abs(x - y) <= 1e-9 * Math.max(1, Math.abs(x), Math.abs(y));
  const expected: Measurements = {aspect_ratio: outputWidth / outputHeight,
    headroom_fraction: (a.crown[1] - r[1]) / outputHeight, head_fraction: head / outputHeight,
    horizontal_position: (a.face_center[0] - r[0]) / outputWidth, vertical_position: (a.face_center[1] - r[1]) / outputHeight};
  if ((Object.keys(expected) as (keyof Measurements)[]).some(key => !near(achieved[key], expected[key])) || !near(achieved.head_height_pixels, head) || p.is_full_frame !== equal(r, [0, 0, w, h])) throw Error('实际达到的构图比例与整数裁剪边界不一致。');
  if (Object.keys(rules).filter(key => key !== 'version').some(key => !near((requested as unknown as Record<string, number>)[key], (rules as unknown as Record<string, number>)[key])) || !near(requested.vertical_position, rules.headroom_fraction + (a.face_center[1] - a.crown[1]) / head * rules.head_fraction)) throw Error('请求比例回显与本地垂直位置约定不一致。');
  return structuredClone(value) as unknown as Preview;
}
export function checkedReceipt(value: unknown, original: Request, pinnedHash: string | null): Receipt {
  if (!record(value) || value.event !== 'portrait_crop_result' || value.version !== 1 || value.request_id !== original.request_id || value.action !== original.action || !digest(value.command_sha256) || (pinnedHash !== null && value.command_sha256 !== pinnedHash) || !equal(value.original_request, original) || typeof value.phase !== 'string' || !['working', 'capability', 'current_ready', 'ready', 'committed', 'cancelled', 'rejected', 'unknown', 'status'].includes(value.phase)) throw Error('回执与原始请求不一致；保留原请求，禁止重新提交。');
  return value as unknown as Receipt;
}
export const imageKey = (v: ImageProof): string => `${v.sha256}:${v.width}:${v.height}:${v.source_width}:${v.source_height}`;
export const imageUrl = (v: ImageProof): string => `data:image/png;base64,${v.base64}`;
/** Only thrown before native enqueue; it must never wrap an invoke failure. */
export class PortraitCropNotSentError extends Error {
  readonly notSent = true;
  constructor(message: string) {super(message); this.name = 'PortraitCropNotSentError';}
}
/** Native recovery provenance, explicitly NOT a portrait_crop_result receipt. */
export type WorkspaceReopened = {
  workspace_reopened: true; authority: 'native_verified_project_reopen_v1'; original_request: Request;
  outcome_unknown: true; authoritative_event: Record<string, unknown> & {
    event: 'project_opened' | 'project_created'; open: true; path: string; project_id: string; docs: number; dirty: boolean;
  }; message: string;
};
export function checkedWorkspaceReopened(value: unknown, original: Request): WorkspaceReopened {
  if (!record(value) || !equal(Object.keys(value).sort(), ['workspace_reopened', 'authority', 'original_request', 'outcome_unknown', 'authoritative_event', 'message'].sort()) ||
    value.workspace_reopened !== true || value.authority !== 'native_verified_project_reopen_v1' || value.outcome_unknown !== true || !equal(value.original_request, original) ||
    typeof value.message !== 'string' || value.message.length > 8192 || !record(value.authoritative_event)) throw Error('工程重开证据与原请求不一致；不能解除待核对状态。');
  const event = value.authoritative_event;
  if (!['project_opened', 'project_created'].includes(String(event.event)) || event.open !== true || typeof event.path !== 'string' || !event.path || event.path.length > 8192 || event.path.includes('\0') ||
    typeof event.project_id !== 'string' || !/^[A-Za-z0-9_.:-]{1,128}$/.test(event.project_id) || !Number.isSafeInteger(event.docs) || Number(event.docs) < 0 || typeof event.dirty !== 'boolean' ||
    event.success === false || event.outcome_unknown === true || Object.hasOwn(event, 'error') || event.requires_reload === true || event.requires_readback === true) throw Error('缺少原生已核验的完整工程重开结果；仍保留原请求。');
  return structuredClone(value) as unknown as WorkspaceReopened;
}
