// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleAction, PeopleResult, PeopleView} from '../people/model';
import {previewImage, type SourceImage, type SourcePreview} from '../legShape/sourcePreview';
export const OP = 'lnx.facial_sculpt.v1';
export const KEYS = ['highlight', 'shadow'] as const;
export type Key = typeof KEYS[number];
export const CONTROL_IDS = {highlight: 'LNX-REF-PC-32471-C-8f773e9125', shadow: 'LNX-REF-PC-32471-C-01b2ee2d32'} as const;
export type Recipe = {version: 1; highlight: number; shadow: number};
export type Source = {sha256: string; width: number; height: number};
export type ReferenceProof = {source: Source; face_ref: FaceRef; landmark_digest: string; preview_sha256: string; reference_request_id: string};
export type Preview = SourcePreview & {sha256: string};
export type FacialSculptView = {recipe: Recipe; facts: {reason?: string | null; changed_pixels?: number;
  positive_structure_pixels?: number; negative_structure_pixels?: number}; source: Source; face_ref: FaceRef | null;
  reviewed: boolean; source_preview: Preview | null; reference_proof: ReferenceProof | null;
  landmark_digest: string | null; support_sha256: string | null; native_available: boolean;
  support_available: boolean; support_reason: string | null; suspended: string | null;
  alias_required: boolean; alias_reason: string | null};
export type View = PeopleView & {facial_sculpt?: FacialSculptView};
export type Capability = {facial_sculpt_protocol?: number; facial_sculpt_available?: boolean; facial_sculpt_reason?: string | null};
export type ActionName = 'facial_sculpt_reference' | 'facial_sculpt_review';
export type Action = Omit<PeopleAction, 'action'> & {action: ActionName};
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const token = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9_.:-]{1,128}$/.test(v);
const revision = (v: number) => Number.isSafeInteger(v) && v >= 0;
export const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b && a.asset_sha256 === b.asset_sha256
  && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}
export const neutral = (): Recipe => ({version: 1, highlight: 0, shadow: 0});
export function check(value: unknown): Recipe {
  if (!object(value) || Object.keys(value).sort().join(',') !== 'highlight,shadow,version' || value.version !== 1
    || KEYS.some(key => typeof value[key] !== 'number' || !Number.isFinite(value[key]) || (value[key] as number) < 0 || (value[key] as number) > 1))
    throw Error('面部立体只接受版本与 0–1 的两项有限强度。');
  return {version: 1, highlight: value.highlight as number, shadow: value.shadow as number};
}
export function patch(key: Key, amount: number): ParameterPatch {
  if (!KEYS.includes(key)) throw Error('未知面部立体参数。');
  const recipe = check({...neutral(), [key]: amount});
  return {operation_id: OP, parameter_path: `/${key}`, unset: false, value: recipe[key]};
}
export function parseChoice(value: string): number | null {
  if (value.trim() === '') return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 && amount <= 100 ? amount/100 : null;
}
export function sourceValid(source: Source | null | undefined): source is Source {
  return !!source && hash(source.sha256) && [source.width, source.height].every(n => Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000);
}
export function proofValid(value: unknown): value is ReferenceProof {
  if (!object(value) || Object.keys(value).sort().join(',') !== 'face_ref,landmark_digest,preview_sha256,reference_request_id,source') return false;
  const p = value as unknown as ReferenceProof;
  return sourceValid(p.source) && Object.keys(p.source).sort().join(',') === 'height,sha256,width'
    && !!p.face_ref && Object.keys(p.face_ref).sort().join(',') === 'analysis_revision,asset_sha256,face_instance_id'
    && p.face_ref.asset_sha256 === p.source.sha256 && token(p.face_ref.face_instance_id) && revision(p.face_ref.analysis_revision)
    && hash(p.landmark_digest) && hash(p.preview_sha256) && token(p.reference_request_id);
}
export function targetReady(view: View | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !hash(view.binding.asset_sha256)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && Object.hasOwn(view.groups, target.target_id ?? '');
  if (target.scope === 'person') return target.face_ref === null && Object.hasOwn(view.persons, target.target_id ?? '');
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return target.scope === 'face' && !!face && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}
export function bindingKey(view: View | null | undefined): string {
  return view ? canonical([view.binding, view.revision, view.association_revision, view.editing_target, view.selected_face_id,
    view.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id)?.face_ref,
    view.facial_sculpt?.source, view.facial_sculpt?.landmark_digest]) : 'unavailable';
}
export function reading(view: View | null | undefined): Recipe | null {
  const report = view?.facial_sculpt, face = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  const resolved = view?.resolved;
  if (!view || !report || !face || !resolved || !sourceValid(report.source)
    || report.source.sha256 !== view.binding.asset_sha256 || !sameFace(report.face_ref, face.face_ref)
    || !sameFace(resolved.face_ref, face.face_ref) || resolved.state_revision !== view.revision
    || resolved.association_revision !== view.association_revision || resolved.conflicts.some(c => c.operation_id === OP)) return null;
  try {
    const recipe = check(report.recipe), leaves = resolved.operations[OP];
    return leaves && KEYS.every(key => leaves[`/${key}`]?.value === recipe[key]) ? recipe : null;
  } catch {return null;}
}
export function access(view: View | null | undefined, capability: Capability | null | undefined, fences: {
  enabled: boolean; pending: boolean; uncertain: boolean; blocked: boolean; faceOk: boolean; faceWhy?: string;
}) {
  const report = view?.facial_sculpt, face = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  const recipe = reading(view), busy = fences.pending || fences.uncertain || fences.blocked;
  const resetDisabled = !fences.enabled || busy || !targetReady(view) || capability?.facial_sculpt_protocol !== 1 || report?.alias_required === true;
  const measured = face?.enabled === true && face.analysis_status === 'verified' && fences.faceOk;
  const core = capability?.facial_sculpt_available === true && report?.native_available === true;
  const reviewDisabled = resetDisabled || !measured || view?.editing_target?.scope !== 'face'
    || view.editing_target.target_id !== view.selected_face_id;
  const changeDisabled = resetDisabled || !recipe || !measured || !core || report?.support_available !== true || report.reviewed !== true;
  const reason = report?.alias_required ? report.alias_reason : fences.uncertain ? '原请求结果未确认，请查询，不要重发。'
    : busy ? '等待当前修改完成。' : !recipe ? '等待与当前来源和人物匹配的面部立体读数。'
    : !measured ? fences.faceWhy || '当前人物缺少真实已验证分析。' : !core ? capability?.facial_sculpt_reason || '面部立体内核不可用。'
    : report?.support_reason || report?.suspended;
  return {recipe, resetDisabled, changeDisabled, reviewDisabled, reason};
}
export function command(view: View, action: ActionName, requestId: string, payload: Record<string, unknown>): Action {
  if (!targetReady(view) || view.editing_target?.scope !== 'face' || view.editing_target.target_id !== view.selected_face_id)
    throw Error('面部立体审核需要当前人物独立范围。');
  return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch,
    document_revision: view.binding.document_revision, state_revision: view.revision, association_revision: view.association_revision,
    request_id: requestId, target: structuredClone(view.editing_target), action, payload};
}
export function referenceCurrent(request: Action, view: View | null | undefined): boolean {
  const report = view?.facial_sculpt, proof = report?.reference_proof;
  return !!view && targetReady(view) && request.action === 'facial_sculpt_reference'
    && request.document_id === view.binding.document_id && request.document_epoch === view.binding.document_epoch
    && request.document_revision === view.binding.document_revision && request.state_revision === view.revision
    && request.association_revision === view.association_revision && canonical(request.target) === canonical(view.editing_target)
    && request.target.scope === 'face' && request.target.target_id === view.selected_face_id
    && !!report && proofValid(proof) && proof.reference_request_id === request.request_id
    && sameFace(proof.face_ref, request.target.face_ref) && sameFace(report.face_ref, proof.face_ref)
    && canonical(proof.source) === canonical(report.source) && proof.landmark_digest === report.landmark_digest
    && !!report.source_preview && report.source_preview.sha256 === proof.preview_sha256;
}
export function echoMatches(request: Action, result: PeopleResult): boolean {
  const {request_id: _id, ...expected} = request;
  const raw = result as unknown as {facial_sculpt_request?: unknown};
  return result.protocol === 1 && typeof result.success === 'boolean' && typeof result.outcome_unknown === 'boolean'
    && canonical(raw.facial_sculpt_request) === canonical(expected);
}
export function referenceReceiptValid(request: Action, result: PeopleResult): boolean {
  const view = result.doc_state?.people as View | undefined;
  return object(result.payload) && Object.keys(result.payload).sort().join(',') === 'kind,reference_proof'
    && result.payload.kind === 'facial_sculpt_reference' && referenceCurrent(request, view)
    && canonical(result.payload.reference_proof) === canonical(view?.facial_sculpt?.reference_proof);
}
export function reviewReceiptValid(request: Action, result: PeopleResult): boolean {
  const next = result.doc_state?.people as View | undefined, proof = request.payload.reference_proof, payload = result.payload;
  if (!proofValid(proof) || !object(payload) || Object.keys(payload).sort().join(',') !== 'kind,reference_proof,support_sha256'
    || payload.kind !== 'facial_sculpt_review' || canonical(payload.reference_proof) !== canonical(proof)
    || !hash(payload.support_sha256) || !next || next.revision <= request.state_revision) return false;
  const report = next.facial_sculpt;
  return !!report && sameFace(report.face_ref, proof.face_ref) && canonical(report.source) === canonical(proof.source)
    && report.landmark_digest === proof.landmark_digest && report.reviewed === true && report.support_sha256 === payload.support_sha256;
}
export function releasedReferenceReceiptValid(request: Action, result: PeopleResult): boolean {
  const raw = result as unknown as Record<string, unknown>;
  return request.action === 'facial_sculpt_reference' && canonical(request.payload) === '{}'
    && request.target.scope === 'face' && result.action === request.action && result.request_id === request.request_id
    && result.document_id === request.document_id && echoMatches(request, result)
    && Object.keys(raw).sort().join(',') === 'action,batch_id,created_id,document_id,error,event,facial_sculpt_request,frame_emitted,outcome_unknown,payload_released,protocol,request_id,success'
    && raw.event === 'people_result' && raw.frame_emitted === false && raw.error === null && raw.created_id === null
    && raw.batch_id === null && result.success === true && result.outcome_unknown === false && result.payload_released === true;
}
export async function verifiedImage(preview: Preview | null, proof: ReferenceProof | null): Promise<SourceImage> {
  if (!proofValid(proof) || !preview || preview.sha256 !== proof.preview_sha256 || preview.source_sha256 !== proof.source.sha256
    || preview.source_width !== proof.source.width || preview.source_height !== proof.source.height
    || preview.base64.length > 6_990_508 || preview.base64.length % 4 !== 0
    || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(preview.base64)) throw Error('当前源图参考缺少完整匹配的图像证明。');
  const image = previewImage(preview);
  if (!image) throw Error('当前来源参考的全图映射无效。');
  const bytes = Uint8Array.from(atob(preview.base64), c => c.charCodeAt(0));
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(v => v.toString(16).padStart(2, '0')).join('');
  if (digest !== proof.preview_sha256) throw Error('当前来源参考 PNG 字节摘要不匹配。');
  return image;
}
