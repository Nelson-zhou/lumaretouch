// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {previewImage, type SourceImage, type SourcePreview} from '../legShape/sourcePreview.ts';
import {PATTERNS} from './catalogue.ts';
export {PATTERNS} from './catalogue.ts';
export const OP = 'lnx.face_decoration.v1';
export const CONTROL_ID = 'LNX-REF-PC-32471-C-dd14134407';
export const CONTROL_PATH = '局部妆容/脸部装饰';
export type Pattern = typeof PATTERNS[number]['id'];
export type Recipe = {version: 1; pattern: Pattern; strength: number};
export type Source = {sha256: string; width: number; height: number};
export type ReferenceProof = {source: Source; face_ref: FaceRef; landmark_digest: string;
  preview_sha256: string; reference_request_id: string};
export type DecorationPreview = SourcePreview & {sha256: string};
export type FaceDecorationView = {recipe: Recipe; facts: {changed_pixels?: number; reason?: string; limitation?: string};
  source: Source; face_ref: FaceRef | null; reviewed: boolean; source_preview: DecorationPreview | null;
  reference_proof: ReferenceProof | null; landmark_digest: string | null; support_sha256: string | null;
  alias_required?: boolean; alias_member_count?: number; alias_reason?: string | null; alias_review?: import('./aliasModel').DecorationAliasReview | null;
  support_alias_reason?: string | null; support_alias_review?: import('./supportAliasModel').SupportAliasReview | null;
  native_available: boolean; support_available: boolean; support_reason: string | null; suspended: string | null};
export type Capability = {face_decoration_protocol?: number; face_decoration_support_alias_protocol?: number; face_decoration_available?: boolean; face_decoration_reason?: string | null};
export const neutral = (): Recipe => ({version: 1, pattern: 'freckle_dust', strength: 0});
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const revision = (v: number) => Number.isSafeInteger(v) && v >= 0;
export const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export function check(raw: unknown): Recipe {
  if (!object(raw) || Object.keys(raw).sort().join(',') !== 'pattern,strength,version' || raw.version !== 1
    || !PATTERNS.some(p => p.id === raw.pattern) || typeof raw.strength !== 'number'
    || !Number.isFinite(raw.strength) || raw.strength < 0 || raw.strength > 1) throw Error('脸部装饰配方需要有效图案和 0–1 的有限程度。');
  return {version: 1, pattern: raw.pattern as Pattern, strength: raw.strength};
}
/** Only the leaf the user changed is written to the current scope. */
export function patches(value: Recipe, keys: ('pattern' | 'strength')[] = ['pattern', 'strength']): ParameterPatch[] {
  const recipe = check(value);
  return keys.map(key => ({operation_id: OP, parameter_path: `/${key}`, unset: false, value: recipe[key]}));
}
export function sourceValid(source: Source | null | undefined): source is Source {
  return !!source && hash(source.sha256) && [source.width, source.height].every(n => Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000);
}
export function proofValid(value: unknown): value is ReferenceProof {
  if (!object(value) || Object.keys(value).sort().join(',') !== 'face_ref,landmark_digest,preview_sha256,reference_request_id,source') return false;
  const p = value as unknown as ReferenceProof;
  return sourceValid(p.source) && Object.keys(p.source).sort().join(',') === 'height,sha256,width'
    && !!p.face_ref && Object.keys(p.face_ref).sort().join(',') === 'analysis_revision,asset_sha256,face_instance_id'
    && p.face_ref.asset_sha256 === p.source.sha256 && typeof p.face_ref.face_instance_id === 'string'
    && p.face_ref.face_instance_id.length > 0 && p.face_ref.face_instance_id.length <= 256 && revision(p.face_ref.analysis_revision)
    && hash(p.landmark_digest) && hash(p.preview_sha256) && typeof p.reference_request_id === 'string'
    && p.reference_request_id.length > 0 && p.reference_request_id.length <= 256;
}
/** Structural ownership check, never a guess from a matching image hash alone. */
export function targetReady(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !hash(view.binding.asset_sha256)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && Object.hasOwn(view.groups, target.target_id ?? '');
  if (target.scope === 'person') return target.face_ref === null && Object.hasOwn(view.persons, target.target_id ?? '');
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return target.scope === 'face' && !!face && revision(face.face_ref.analysis_revision)
    && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}
export function bindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  return canonical([view.binding, view.revision, view.association_revision, view.editing_target, view.selected_face_id,
    selected?.face_ref, selected?.enabled, selected?.analysis_status, view.face_decoration?.source, view.face_decoration?.landmark_digest]);
}
export function reading(view: PeopleView | null | undefined): {recipe: Recipe | null; reason?: string} {
  const report = view?.face_decoration, selected = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected || !report) return {recipe: null, reason: '请选择人物，等待此脸的装饰状态。'};
  const resolved = view.resolved;
  if (!sourceValid(report.source) || report.source.sha256 !== view.binding.asset_sha256 || !sameFace(report.face_ref, selected.face_ref)
    || !resolved || !sameFace(resolved.face_ref, selected.face_ref) || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision)
    return {recipe: null, reason: '人物或来源已变化，等待匹配的脸部装饰读数。'};
  if (resolved.conflicts.some(c => c.operation_id === OP)) return {recipe: null, reason: '脸部装饰存在分组优先级冲突，请先在人物栏解决。'};
  try {
    const recipe = check(report.recipe), parameters = resolved.operations[OP];
    if (!parameters || parameters['/pattern']?.value !== recipe.pattern || parameters['/strength']?.value !== recipe.strength)
      return {recipe: null, reason: '装饰报告与人物有效参数不一致，请刷新。'};
    return {recipe};
  } catch {return {recipe: null, reason: '引擎返回的装饰配方无效，未用中性占位值替代。'};}
}
export type Fences = {enabled: boolean; pending: boolean; uncertain: boolean; blocked: boolean; faceOk: boolean; faceWhy?: string};
export function access(view: PeopleView | null | undefined, capability: Capability | null | undefined, fences: Fences) {
  const state = reading(view), report = view?.face_decoration;
  const selected = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  const busy = fences.pending || fences.uncertain || fences.blocked;
  const resetDisabled = busy || !fences.enabled || capability?.face_decoration_protocol !== 1 || !targetReady(view);
  const measured = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const core = capability?.face_decoration_protocol === 1 && capability.face_decoration_available === true && report?.native_available === true;
  const changeDisabled = resetDisabled || !state.recipe || !measured || !core || report?.reviewed !== true || report.support_available !== true;
  const patternDisabled = resetDisabled || !state.recipe || state.recipe.strength > 0 && changeDisabled;
  const target = view?.editing_target;
  const reviewDisabled = resetDisabled || !measured || capability?.face_decoration_protocol !== 1 || !report
    || !sourceValid(report.source) || !hash(report.landmark_digest) || target?.scope !== 'face'
    || target.target_id !== view?.selected_face_id || !sameFace(target.face_ref, selected?.face_ref);
  const reason = fences.uncertain ? '上一请求结果未知，请查询原请求，不要重复提交。'
    : busy ? '正在等待当前编辑回执，尚未确认应用。'
    : !fences.enabled ? '当前人物编辑不可用。'
    : !targetReady(view) ? '请在人物栏明确选择有效编辑范围。'
    : state.reason ?? (!measured ? fences.faceWhy || '此脸未启用或缺少真实分析。'
    : !core ? capability?.face_decoration_reason || '脸部装饰原生核心尚不可用；不会使用模拟效果。'
    : report?.support_reason || (report?.reviewed !== true ? '请先独立审核此人物的可见皮肤范围。' : report?.suspended || undefined));
  return {...state, core, resetDisabled, patternDisabled, changeDisabled, reviewDisabled, reason};
}
export function command(view: PeopleView, action: 'face_decoration_reference' | 'face_decoration_review' | import('./aliasModel').DecorationAliasAction | import('./supportAliasModel').SupportAliasAction, requestId: string, payload: Record<string, unknown>): PeopleAction {
  if (!targetReady(view) || view.editing_target?.scope !== 'face' || view.editing_target.target_id !== view.selected_face_id)
    throw Error('脸部装饰审核需要当前人物独立编辑范围。');
  return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch,
    document_revision: view.binding.document_revision, state_revision: view.revision, association_revision: view.association_revision,
    request_id: requestId, target: structuredClone(view.editing_target), action, payload};
}
export function commandCurrent(request: PeopleAction, view: PeopleView | null | undefined): boolean {
  return !!view && targetReady(view) && request.document_id === view.binding.document_id && request.document_epoch === view.binding.document_epoch
    && request.document_revision === view.binding.document_revision && request.state_revision === view.revision
    && request.association_revision === view.association_revision && canonical(request.target) === canonical(view.editing_target)
    && request.target.scope === 'face' && request.target.target_id === view.selected_face_id;
}
export function referenceCurrent(request: PeopleAction, view: PeopleView | null | undefined): boolean {
  const report = view?.face_decoration, proof = report?.reference_proof;
  return request.action === 'face_decoration_reference' && commandCurrent(request, view) && !!report && proofValid(proof)
    && proof.reference_request_id === request.request_id && sameFace(proof.face_ref, request.target.face_ref) && sameFace(report.face_ref, proof.face_ref)
    && canonical(proof.source) === canonical(report.source) && proof.landmark_digest === report.landmark_digest
    && !!report.source_preview && report.source_preview.sha256 === proof.preview_sha256;
}
export function echoMatches(request: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _id, ...expected} = request;
  return result.protocol === 1 && typeof result.success === 'boolean' && typeof result.outcome_unknown === 'boolean'
    && canonical(result.face_decoration_request) === canonical(expected);
}
/** A completed read may expire its display bytes without rewriting the original successful outcome. */
export function releasedReferenceReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  const raw = result as unknown as Record<string, unknown>;
  return request.action === 'face_decoration_reference' && request.target.scope === 'face' && canonical(request.payload) === '{}'
    && result.action === request.action && result.request_id === request.request_id && result.document_id === request.document_id && echoMatches(request, result)
    && Object.keys(raw).sort().join(',') === 'action,batch_id,created_id,document_id,error,event,face_decoration_request,frame_emitted,outcome_unknown,payload_released,protocol,request_id,success'
    && raw.event === 'people_result' && raw.frame_emitted === false && raw.error === null
    && raw.created_id === null && raw.batch_id === null && result.success === true
    && result.outcome_unknown === false && result.payload_released === true;
}
export function referenceReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  if (!object(result.payload) || Object.keys(result.payload).sort().join(',') !== 'kind,reference_proof'
    || result.payload.kind !== 'face_decoration_reference' || !referenceCurrent(request, result.doc_state?.people)) return false;
  const report = result.doc_state!.people!.face_decoration!;
  return canonical(result.payload.reference_proof) === canonical(report.reference_proof);
}
export function reviewReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  const payload = result.payload, next = result.doc_state?.people, proof = request.payload.reference_proof;
  if (!proofValid(proof) || !object(payload) || Object.keys(payload).sort().join(',') !== 'kind,reference_proof,support_sha256'
    || payload.kind !== 'face_decoration_review' || canonical(payload.reference_proof) !== canonical(proof)
    || !hash(payload.support_sha256) || !next || next.revision <= request.state_revision) return false;
  const report = next.face_decoration;
  return !!report && sameFace(report.face_ref, proof.face_ref) && canonical(report.source) === canonical(proof.source)
    && report.landmark_digest === proof.landmark_digest && report.reviewed === true && report.support_sha256 === payload.support_sha256;
}
/** Digest actual displayed PNG bytes, not a URL or a server hash string. Decode is checked by the img element separately. */
export async function verifiedImage(preview: DecorationPreview | null, proof: ReferenceProof | null): Promise<SourceImage> {
  if (!proofValid(proof) || !preview || preview.sha256 !== proof.preview_sha256 || preview.source_sha256 !== proof.source.sha256
    || preview.source_width !== proof.source.width || preview.source_height !== proof.source.height
    || preview.base64.length > 6_990_508 || preview.base64.length % 4 !== 0
    || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(preview.base64)) throw Error('当前源图参考缺少完整匹配的图像证明。');
  const image = previewImage(preview);
  if (!image) throw Error('当前源图参考尺寸或全图坐标映射无效。');
  const bytes = Uint8Array.from(atob(preview.base64), c => c.charCodeAt(0));
  const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
  if (actual !== proof.preview_sha256) throw Error('当前源图 PNG 校验失败，不能确认归属或保存范围。');
  return image;
}
