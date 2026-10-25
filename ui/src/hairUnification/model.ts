// SPDX-License-Identifier: GPL-3.0-or-later
import {peopleContext, type FaceRef, type PeopleContext, type PeopleView} from '../people/model';
import type {MaskObject} from '../localMasks/model';

export const OPERATION = 'lnx.hair_unification.v1' as const;
export const CONTROL_ID = 'LNX-REF-PC-32472-C-fb2fe59a22';
export const MAX_STROKES = 64, MAX_POINTS = 1024, MAX_TOTAL_POINTS = 8192;
export type Recipe = {version: 1; amount: number};
export type SampleBrush = Extract<MaskObject, {kind: 'brush'}>;
export type SampleObject = SampleBrush | Extract<MaskObject, {kind: 'radial'}>;
export type Sample = {version: 1; domain: 'source-normalized'; objects: SampleObject[]};
export type Source = {sha256: string; width: number; height: number};
export type ReferenceSide = 'roots' | 'tips';
export type Reference = {
  source: Source; face_ref: FaceRef; recipe: Recipe; root_sample: Sample; tip_sample: Sample;
  support_sha256: string | null; semantic_evidence_sha256: string | null;
  source_png: string; source_width: number; source_height: number;
  source_preview_width: number; source_preview_height: number; native_available: boolean; notice: string;
};
export type Review = {
  preview_id: string; review_token: string; preview_sha256: string; source: Source; face_ref: FaceRef;
  sample_asset_sha256: string;
  recipe: Recipe; root_sample: Sample; tip_sample: Sample; reference_side: ReferenceSide;
  before_png: string; after_png: string; support_png: string;
  before_sha256: string; after_sha256: string; support_sha256: string;
  source_width: number; source_height: number;
  before_width: number; before_height: number; after_width: number; after_height: number;
  support_width: number; support_height: number;
  sample_counts: {hair_pixels: number; root_pixels: number; tip_pixels: number; selected_pixels: number};
};
export type Draft = {recipe: Recipe; root_sample: Sample; tip_sample: Sample; ownership_confirmed: boolean};
export type Action = 'context' | 'preview' | 'presented' | 'commit' | 'clear';
export type Request = {cmd: 'hair_unification'; protocol: 1; operation_id: typeof OPERATION;
  request_id: string; action: Action; people_context: PeopleContext; payload: Record<string, unknown>};
export type Result = {event: 'hair_unification_result'; protocol: 1; operation_id: typeof OPERATION;
  request_id: string; action: Action; document_id: string; people_context: PeopleContext;
  request_payload: Record<string, unknown>; success: boolean; outcome_unknown: boolean; error?: string; payload: unknown; doc_state?: unknown;
  /** Native status ledger only, never an engine assertion or inferred context change. */
  workspace_reopened?: true};
export type Mailbox = {request_id: string; phase: 'pending' | 'done' | 'unavailable'; result?: Result; error?: string};
export type Binding = {key: string; context: PeopleContext | null; targetReady: boolean; measured: boolean; reason: string};
export const neutral = (): Recipe => ({version: 1, amount: 0});
export const emptySample = (): Sample => ({version: 1, domain: 'source-normalized', objects: []});
export const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const unit = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1;
const revision = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
const extent = (value: unknown): value is number => revision(value) && value > 0 && value <= 1000000;
const token = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 160;
export const digest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);
export const png = (value: unknown): value is string => typeof value === 'string' && value.length <= 8 * 1024 * 1024
  && /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value);
export const sameFace = (a: FaceRef | null | undefined, b: FaceRef | null | undefined): boolean => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export const sameSource = (a: Source, b: Source): boolean => a.sha256 === b.sha256 && a.width === b.width && a.height === b.height;
/** Deterministic comparison only. This is not a substitute for a native review digest. */
export function key(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(key).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(field => `${JSON.stringify(field)}:${key(value[field])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export function checkRecipe(value: unknown): Recipe {
  if (!object(value) || Object.keys(value).sort().join(',') !== 'amount,version' || value.version !== 1
    || typeof value.amount !== 'number' || !Number.isFinite(value.amount) || value.amount < -1 || value.amount > 1)
    throw Error('发色统一必须使用版本 1 与 −1 到 +1 的有限强度。');
  return {version: 1, amount: value.amount};
}
const point = (value: unknown): value is [number, number] => Array.isArray(value) && value.length === 2 && value.every(unit);
export function checkSample(value: unknown): Sample {
  if (!object(value) || Object.keys(value).sort().join(',') !== 'domain,objects,version'
    || value.version !== 1 || value.domain !== 'source-normalized' || !Array.isArray(value.objects)
    || value.objects.length > MAX_STROKES) throw Error('参考样本必须是有界的源图归一化画笔。');
  let total = 0;
  const ids = new Set<string>();
  for (const item of value.objects) {
    if (!object(item) || typeof item.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(item.id) || ids.has(item.id)
      || typeof item.name !== 'string' || !item.name.trim() || item.name.length > 80 || /[\x00-\x1f]/.test(item.name)
      || typeof item.enabled !== 'boolean' || !['add', 'subtract'].includes(String(item.operation)) || !unit(item.opacity)
      || typeof item.feather !== 'number' || !Number.isFinite(item.feather) || item.feather < 0 || item.feather > 100
      || !Array.isArray(item.axes) || item.axes.length !== 2 || item.axes.some(axis => !Array.isArray(axis) || axis.length !== 2
        || axis.some(n => typeof n !== 'number' || !Number.isFinite(n) || Math.abs(n) > 4))) throw Error('参考样本笔迹无效。');
    const axes = item.axes as [[number, number], [number, number]];
    const expected = item.kind === 'brush' ? 'axes,enabled,feather,id,kind,name,opacity,operation,points'
      : 'axes,center,enabled,feather,id,kind,name,opacity,operation';
    if (Object.keys(item).sort().join(',') !== expected) throw Error('参考样本含未知字段。');
    if (Math.abs(axes[0][0] * axes[1][1] - axes[0][1] * axes[1][0]) < 1e-12) throw Error('参考样本笔刷不能退化。');
    if (item.kind === 'brush') {
      if (!Array.isArray(item.points) || !item.points.length || item.points.length > MAX_POINTS || !item.points.every(point))
        throw Error('参考样本路径超出范围或点数预算。');
      total += item.points.length;
    } else if (item.kind !== 'radial' || !point(item.center)) throw Error('参考样本只接受源图画笔或椭圆，不接受屏幕蒙版。');
    ids.add(item.id);
  }
  if (total > MAX_TOTAL_POINTS) throw Error('参考样本超过总点数预算。');
  return structuredClone(value) as Sample;
}
export function checkDraft(value: Draft): Draft {
  if (typeof value.ownership_confirmed !== 'boolean') throw Error('缺少本人样本归属确认。');
  return {recipe: checkRecipe(value.recipe), root_sample: checkSample(value.root_sample),
    tip_sample: checkSample(value.tip_sample), ownership_confirmed: value.ownership_confirmed};
}
export function hasSample(value: Sample): boolean {return value.objects.some(item => item.enabled && item.operation === 'add' && item.opacity > 0);}
/** Neutral UI ownership does not require NEW sample measurement or this colour core.
 * The engine still validates the original source and any other retained effects/analysis. */
export function binding(view: PeopleView | null | undefined): Binding {
  const context = peopleContext(view) ?? null, target = context?.target;
  const face = view?.faces.find(item => item.face_ref.face_instance_id === view.selected_face_id);
  const ready = !!view && !!context && token(context.document_id) && token(context.document_epoch)
    && [context.document_revision, context.state_revision, context.association_revision].every(revision)
    && digest(view.binding.asset_sha256) && target?.scope === 'face' && target.target_id === view.selected_face_id
    && !!face && face.face_ref.asset_sha256 === view.binding.asset_sha256 && revision(face.face_ref.analysis_revision)
    && token(face.face_ref.face_instance_id) && sameFace(face.face_ref, target.face_ref);
  const measured = ready && face?.enabled === true && face.analysis_status === 'verified';
  return {key: key([context, view?.binding.asset_sha256, view?.selected_face_id, face?.enabled, face?.analysis_status]),
    context, targetReady: ready, measured,
    reason: !ready ? '请在当前照片选择所需人物的“人物独立覆盖”；本项不支持关联、分组或批量。'
      : !measured ? '当前人物尚未启用或没有真实分析；可请求本项归零，但原片及其他已保留效果所需分析仍须由引擎核对。' : ''};
}
function source(value: unknown, context: PeopleContext): Source {
  if (!object(value) || !digest(value.sha256) || !extent(value.width) || !extent(value.height)
    || value.sha256 !== context.target.face_ref?.asset_sha256) throw Error('参考图来源与当前人物不一致。');
  return value as Source;
}
function boundedImage(raw: Record<string, unknown>, prefix: string): void {
  if (!png(raw[`${prefix}_png`]) || ![raw[`${prefix}_width`], raw[`${prefix}_height`]].every(n => extent(n) && n <= 1024))
    throw Error('审核图缺失或超过完整缩小图预算。');
}
export function readReference(value: unknown, context: PeopleContext): Reference {
  if (!object(value) || !object(value.face_ref) || !sameFace(value.face_ref as FaceRef, context.target.face_ref)
    || typeof value.native_available !== 'boolean' || typeof value.notice !== 'string' || value.notice.length > 4096
    || !(value.support_sha256 === null || digest(value.support_sha256))
    || !(value.semantic_evidence_sha256 === null || digest(value.semantic_evidence_sha256))) throw Error('发色统一来源回执不完整。');
  const owned = source(value.source, context);
  if (value.source_width !== owned.width || value.source_height !== owned.height || !png(value.source_png)
    || ![value.source_preview_width, value.source_preview_height].every(n => extent(n) && n <= 1024))
    throw Error('源图尺寸或完整来源图无效。');
  return {...value, source: owned, recipe: checkRecipe(value.recipe), root_sample: checkSample(value.root_sample),
    tip_sample: checkSample(value.tip_sample)} as Reference;
}
export function readReview(value: unknown, reference: Reference, draft: Draft): Review {
  if (!object(value) || typeof value.preview_id !== 'string' || !/^[0-9a-f]{32}$/.test(value.preview_id)
    || !digest(value.review_token) || value.preview_sha256 !== value.review_token || !digest(value.sample_asset_sha256)
    || !object(value.source) || !sameSource(value.source as Source, reference.source)
    || !object(value.face_ref) || !sameFace(value.face_ref as FaceRef, reference.face_ref)
    || value.source_width !== reference.source.width || value.source_height !== reference.source.height
    || key(checkRecipe(value.recipe)) !== key(draft.recipe) || key(checkSample(value.root_sample)) !== key(draft.root_sample)
    || key(checkSample(value.tip_sample)) !== key(draft.tip_sample)
    || value.reference_side !== (draft.recipe.amount < 0 ? 'tips' : 'roots')
    || ![value.before_sha256, value.after_sha256, value.support_sha256].every(digest)
    || !object(value.sample_counts) || !['hair_pixels', 'root_pixels', 'tip_pixels', 'selected_pixels'].every(field => revision((value.sample_counts as Record<string, unknown>)[field])))
    throw Error('发色统一候选与所选人物、样本或本次程度不一致。');
  for (const side of ['before', 'after', 'support']) boundedImage(value, side);
  if (value.before_width !== value.after_width || value.before_height !== value.after_height
    || Number(value.sample_counts.hair_pixels) <= 0 || Number(value.sample_counts.selected_pixels) <= 0
    || value.sample_counts.selected_pixels !== value.sample_counts[draft.recipe.amount < 0 ? 'tip_pixels' : 'root_pixels']
    || Number(value.sample_counts.root_pixels) > Number(value.sample_counts.hair_pixels)
    || Number(value.sample_counts.tip_pixels) > Number(value.sample_counts.hair_pixels)
    || Number(value.sample_counts.hair_pixels) > reference.source.width * reference.source.height)
    throw Error('缺少真实、同尺寸的前后对照或有效本人头发样本。');
  return value as unknown as Review;
}
function correlatedResult(raw: unknown, request: Request): Result {
  if (!object(raw) || raw.event !== 'hair_unification_result' || raw.protocol !== 1 || raw.operation_id !== OPERATION
    || raw.request_id !== request.request_id || raw.action !== request.action || raw.document_id !== request.people_context.document_id
    || key(raw.people_context) !== key(request.people_context) || key(raw.request_payload) !== key(request.payload) || typeof raw.success !== 'boolean'
    || typeof raw.outcome_unknown !== 'boolean')
    throw Error('原发色统一回执身份不匹配；只查询原请求，不重复提交。');
  return raw as unknown as Result;
}
/** Ordinary terminals never turn a reopen marker or an unknown write into success/refusal. */
export function readResult(raw: unknown, request: Request): Result {
  const result = correlatedResult(raw, request);
  if (result.outcome_unknown || result.workspace_reopened !== undefined)
    throw Error('原发色统一结果仍未知；只查询原请求，不重复提交。');
  return result;
}
/** Only an exact native receipt proving a real saved-project reopen can offer explicit retirement.
 * Native rejects engine-supplied markers. A timeout, navigation or epoch change is not this proof. */
export function readWorkspaceReopened(raw: unknown, request: Request): Result | null {
  if (!object(raw) || raw.workspace_reopened === undefined) return null;
  const result = correlatedResult(raw, request);
  if (raw.workspace_reopened !== true || result.success !== false || result.outcome_unknown !== true)
    throw Error('旧工程恢复标记不符合原未知操作回执；继续保留操作锁。');
  return result;
}
export function reviewAck(review: Review): Record<string, unknown> {
  return {preview_id: review.preview_id, review_token: review.review_token,
    before_sha256: review.before_sha256, after_sha256: review.after_sha256, support_sha256: review.support_sha256};
}
export function readPresented(raw: unknown, review: Review): void {
  const expected = reviewAck(review);
  if (!object(raw) || raw.kind !== 'presented' || raw.presented !== true
    || Object.keys(expected).some(field => raw[field] !== expected[field])) throw Error('已显示图片的确认回执不匹配；不能应用。');
}
/** Hash the actual delivered PNG bytes, not a URL, raw RGB array or a local draft. */
export async function imageDigest(url: string): Promise<string> {
  if (!png(url)) throw Error('审核图片不是有效的有界 PNG。');
  const binary = atob(url.slice(url.indexOf(',') + 1)), bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(hash), n => n.toString(16).padStart(2, '0')).join('');
}
