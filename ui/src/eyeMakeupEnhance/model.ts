// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleAction, PeopleResult, PeopleView} from '../people/model';
export const OP = 'lnx.eye_makeup_enhance.v1';
export const CONTROLS = ['amount', 'saturation', 'brightness', 'structure'] as const;
export const SIDES = ['left', 'right'] as const;
export type Control = typeof CONTROLS[number];
export type Side = typeof SIDES[number];
export type Bilateral = {linked: boolean; left: number; right: number};
export type Recipe = {version: 1} & Record<Control, Bilateral>;
export const CONTROL_IDS: Record<Control, string> = {amount: 'LNX-REF-PC-32471-C-ee9394fa95',
  saturation: 'LNX-REF-PC-32471-C-707956d003', brightness: 'LNX-REF-PC-32471-C-0985fdcfb9', structure: 'LNX-REF-PC-32471-C-e3b5569011'};
export const LABELS = {amount: '原有眼妆增强 / 减淡', saturation: '眼妆饱和度', brightness: '眼妆明度', structure: '眼妆立体度'};
export type Capability = {eye_makeup_enhance_protocol?: number; eye_makeup_enhance_available?: boolean; eye_makeup_enhance_reason?: string | null};
export type Source = {sha256: string; width: number; height: number};
export type ReferenceProof = {source: Source; face_ref: FaceRef; landmark_digest: string; preview_sha256: string; reference_request_id: string};
export type SourcePreview = {mime: 'image/png'; base64: string; sha256: string; source: Source; width: number; height: number;
  view_box: [number, number, number, number]; mapping: 'source_pixel_centre_periocular_crop'; minimum_eye_width: number};
export type SourceImage = {url: string; width: number; height: number; viewBox: string};
export type EyeMakeupEnhanceView = {recipe: Recipe; facts: {changed_pixels?: number; limitations?: string[]};
  source: Source; face_ref: FaceRef | null; landmark_digest: string | null; reviewed: boolean; support_sha256: string | null;
  sides: Partial<Record<Side, {reviewed: boolean; reference_reviewed: boolean}>>; source_preview: SourcePreview | null;
  reference_proof: ReferenceProof | null; native_available: boolean; support_available: boolean; support_reason: string | null; suspended: string | null};
export type View = PeopleView & {eye_makeup_enhance?: EyeMakeupEnhanceView | null};
export type Point = [number, number];
export type EyeReview = {makeup: Point[]; exclusions: Point[][]; reference_a: Point[] | null; reference_b: Point[] | null;
  reference_confirmed: boolean; visible_makeup: boolean; unoccluded: boolean; ownership_confirmed: boolean; globe_lashes_brows_excluded: boolean};
export type Review = Partial<Record<Side, EyeReview>>;
export type Action = 'eye_makeup_enhance_reference' | 'eye_makeup_enhance_review';
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const revision = (v: number) => Number.isSafeInteger(v) && v >= 0;
export const validAmount = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v) && v >= -1 && v <= 1;
export const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b && a.asset_sha256 === b.asset_sha256
  && a.face_instance_id === b.face_instance_id && a.analysis_revision === b.analysis_revision;
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (object(v)) return `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;
  return JSON.stringify(v) ?? 'undefined';
}
export function neutral(): Recipe {
  return {version: 1, amount: {linked: true, left: 0, right: 0}, saturation: {linked: true, left: 0, right: 0},
    brightness: {linked: true, left: 0, right: 0}, structure: {linked: true, left: 0, right: 0}};
}
export function check(v: unknown): Recipe {
  if (!object(v) || Object.keys(v).sort().join(',') !== 'amount,brightness,saturation,structure,version' || v.version !== 1) throw Error('眼妆配方版本或字段无效。');
  const out = neutral();
  for (const key of CONTROLS) {
    const row = v[key];
    if (!object(row) || Object.keys(row).sort().join(',') !== 'left,linked,right' || typeof row.linked !== 'boolean'
      || !validAmount(row.left) || !validAmount(row.right) || row.linked && row.left !== row.right) throw Error('每项眼妆控件须有独立联动及 -1 到 1 左右数值，联动时必须相同。');
    out[key] = {linked: row.linked, left: row.left, right: row.right};
  }
  return out;
}
export function amountPatch(control: Control, side: Side, value: number): ParameterPatch {
  if (!CONTROLS.includes(control) || !SIDES.includes(side) || !validAmount(value)) throw Error('眼妆数值或人物侧别无效。');
  return {operation_id: OP, parameter_path: `/${control}/${side}`, value, unset: false};
}
export function adjustPatches(control: Control, side: Side, value: number, linked: boolean): ParameterPatch[] {
  if (typeof linked !== 'boolean') throw Error('联动状态尚未确认。');
  return linked ? SIDES.map(s => amountPatch(control, s, value)) : [amountPatch(control, side, value)];
}
export function unlockPatch(control: Control): ParameterPatch {
  if (!CONTROLS.includes(control)) throw Error('未知眼妆控件。');
  return {operation_id: OP, parameter_path: `/${control}/linked`, value: false, unset: false};
}
export function linkPatches(control: Control, value: number): ParameterPatch[] {
  return [{...unlockPatch(control), value: true}, ...adjustPatches(control, 'left', value, true)];
}
export function resetPatches(control?: Control): ParameterPatch[] {
  return (control ? [control] : CONTROLS).flatMap(k => SIDES.map(side => amountPatch(k, side, 0)));
}
export function zeroSidePatches(control: Control, side: Side): ParameterPatch[] {return [unlockPatch(control), amountPatch(control, side, 0)];}
export function parseChoice(text: string): number | null {
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(text.trim())) return null;
  const value = Number(text.trim()) / 100; return validAmount(value) ? value : null;
}
export function targetReady(view: View | null | undefined): boolean {
  const target = view?.editing_target, face = view?.faces.find(f => f.face_ref.face_instance_id === target?.target_id);
  // Current-photo minimum path: never borrow a preview face's parameters for a shared target.
  return !!view && !!target && target.scope === 'face' && !!face && target.target_id === view.selected_face_id
    && sameFace(face.face_ref, target.face_ref) && face.face_ref.asset_sha256 === view.binding.asset_sha256
    && hash(view.binding.asset_sha256) && !!view.binding.document_id && !!view.binding.document_epoch
    && revision(view.binding.document_revision) && revision(view.revision) && revision(view.association_revision) && revision(face.face_ref.analysis_revision);
}
export function bindingKey(view: View | null | undefined): string {
  return view ? canonical([view.binding, view.revision, view.association_revision, view.editing_target, view.selected_face_id,
    view.faces, view.resolved?.face_ref, view.resolved?.operations[OP], view.resolved?.conflicts,
    view.eye_makeup_enhance?.source, view.eye_makeup_enhance?.landmark_digest, view.eye_makeup_enhance?.support_sha256]) : 'unavailable';
}
export function reading(view: View | null | undefined): {recipe: Recipe | null; reason?: string} {
  const face = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id), resolved = view?.resolved, report = view?.eye_makeup_enhance;
  if (!view || !face || !resolved || !report || !sameFace(face.face_ref, resolved.face_ref) || !sameFace(report.face_ref, face.face_ref)
    || report.source.sha256 !== view.binding.asset_sha256 || face.face_ref.asset_sha256 !== view.binding.asset_sha256
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision)
    return {recipe: null, reason: '等待当前人物、有效来源和四项控件一致的权威读数。'};
  if (resolved.conflicts.some(c => c.operation_id === OP)) return {recipe: null, reason: '眼妆参数存在分组继承冲突，请先解决。'};
  try {
    const recipe = check(report.recipe);
    for (const control of CONTROLS) for (const field of ['linked', ...SIDES] as const)
      if (resolved.operations[OP]?.[`/${control}/${field}`]?.value !== recipe[control][field]) throw Error('report mismatch');
    return {recipe};
  } catch {return {recipe: null, reason: '眼妆报告与有效参数不一致，不会用中性值冒充实际读数。'};}
}
export type Fences = {enabled: boolean; pending: boolean; uncertain: boolean; blocked: boolean; faceOk: boolean; faceWhy?: string};
export function access(view: View | null | undefined, capability: Capability | null | undefined, fences: Fences) {
  const read = reading(view), report = view?.eye_makeup_enhance, face = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  const busy = fences.pending || fences.uncertain || fences.blocked;
  const resetDisabled = busy || !fences.enabled || !targetReady(view) || capability?.eye_makeup_enhance_protocol !== 1;
  const measured = !!face?.enabled && face.analysis_status === 'verified' && fences.faceOk;
  const reviewDisabled = resetDisabled || !measured || !report || !hash(report.landmark_digest);
  const core = capability?.eye_makeup_enhance_available === true && report?.native_available === true;
  const changeDisabled = resetDisabled || !read.recipe || !measured || !core || !report?.support_available;
  const sideReady = (control: Control, side: Side) => report?.sides[side]?.reviewed === true
    && (control !== 'amount' || report.sides[side]?.reference_reviewed === true);
  const permitted = (control: Control, side: Side, value: number, linked: boolean) => value === 0 ? !resetDisabled
    : !changeDisabled && (linked ? SIDES.every(s => sideReady(control, s)) : sideReady(control, side));
  const reason = fences.uncertain ? '上一请求结果不明，请查询原请求，不要重发。' : busy ? '请等待当前编辑回执。'
    : !targetReady(view) ? '当前入口只编辑所选人物独立范围，不借用共享范围或另一人物的审核。'
    : read.reason ?? (!measured ? fences.faceWhy || '人物尚未启用或缺少真实分析。' : !core ? capability?.eye_makeup_enhance_reason || '已有眼妆 Rust 核心尚不可用。'
    : report?.support_reason || report?.suspended || undefined);
  return {...read, resetDisabled, reviewDisabled, changeDisabled, permitted, reason};
}
export function sourceValid(v: unknown): v is Source {
  return object(v) && Object.keys(v).sort().join(',') === 'height,sha256,width' && hash(v.sha256)
    && [v.width,v.height].every(n => typeof n === 'number' && Number.isSafeInteger(n) && n >= 2 && n <= 1_000_000);
}
export function proofValid(v: unknown): v is ReferenceProof {
  if (!object(v) || Object.keys(v).sort().join(',') !== 'face_ref,landmark_digest,preview_sha256,reference_request_id,source' || !sourceValid(v.source) || !object(v.face_ref)) return false;
  const ref = v.face_ref;
  return Object.keys(ref).sort().join(',') === 'analysis_revision,asset_sha256,face_instance_id' && ref.asset_sha256 === v.source.sha256
    && typeof ref.face_instance_id === 'string' && ref.face_instance_id.length > 0 && ref.face_instance_id.length <= 256
    && typeof ref.analysis_revision === 'number' && revision(ref.analysis_revision) && hash(v.landmark_digest) && hash(v.preview_sha256)
    && typeof v.reference_request_id === 'string' && v.reference_request_id.length > 0 && v.reference_request_id.length <= 256;
}
export function command(view: View, action: Action, requestId: string, payload: Record<string, unknown>): PeopleAction {
  if (!targetReady(view)) throw Error('眼妆审核需要当前人物独立编辑范围。');
  return {document_id: view.binding.document_id, document_epoch: view.binding.document_epoch, document_revision: view.binding.document_revision,
    state_revision: view.revision, association_revision: view.association_revision, request_id: requestId,
    target: structuredClone(view.editing_target!), action, payload};
}
export function commandCurrent(request: PeopleAction, view: View | null | undefined): boolean {
  return !!view && targetReady(view) && request.document_id === view.binding.document_id && request.document_epoch === view.binding.document_epoch
    && request.document_revision === view.binding.document_revision && request.state_revision === view.revision
    && request.association_revision === view.association_revision && canonical(request.target) === canonical(view.editing_target);
}
export function referenceCurrent(request: PeopleAction, view: View | null | undefined): boolean {
  const report = view?.eye_makeup_enhance, proof = report?.reference_proof;
  return request.action === 'eye_makeup_enhance_reference' && commandCurrent(request, view) && !!report && proofValid(proof)
    && proof.reference_request_id === request.request_id && sameFace(proof.face_ref, request.target.face_ref)
    && sameFace(report.face_ref, proof.face_ref) && canonical(report.source) === canonical(proof.source)
    && report.landmark_digest === proof.landmark_digest && report.source_preview?.sha256 === proof.preview_sha256;
}
export function echoMatches(request: PeopleAction, result: PeopleResult): boolean {
  const {request_id: _id, ...expected} = request;
  const actual = result as PeopleResult & {eye_makeup_enhance_request?: Omit<PeopleAction, 'request_id'>};
  return result.protocol === 1 && typeof result.success === 'boolean' && typeof result.outcome_unknown === 'boolean'
    && canonical(actual.eye_makeup_enhance_request) === canonical(expected);
}
export function referenceReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  if (!object(result.payload) || Object.keys(result.payload).sort().join(',') !== 'kind,reference_proof'
    || result.payload.kind !== 'eye_makeup_enhance_reference' || !referenceCurrent(request, result.doc_state?.people)) return false;
  return canonical(result.payload.reference_proof) === canonical((result.doc_state!.people as View).eye_makeup_enhance!.reference_proof);
}
const fields = (value: unknown, names: readonly string[]): value is Record<string, unknown> => object(value)
  && Object.keys(value).length === names.length && names.every(key => Object.hasOwn(value, key));
const boundedNumber = (value: unknown, low: number, high: number): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= low && value <= high;
const integer = (value: unknown, low: number, high: number): value is number => boundedNumber(value, low, high) && Number.isSafeInteger(value);
const diagnostic = (value: unknown) => value === null || typeof value === 'string' && value.trim().length > 0
  && new TextEncoder().encode(value).length <= 4096 && !value.includes('\0');
const dimensions = (value: unknown): value is [number, number] => Array.isArray(value) && value.length === 2
  && value.every(n => integer(n, 1, 1_000_000));
/** Native report parity for bounded diagnostics, not proof that rendering ran. */
function reviewFactsValid(value: unknown, report: EyeMakeupEnhanceView): boolean {
  if (fields(value, [])) return true;
  if (!fields(value, ['recipe', 'review_sha256', 'face_ref', 'sides', 'landmark_digest', 'face_skin_observation',
    'changed_pixels', 'native_solver', 'source_dimensions', 'render_dimensions', 'protected_face_boxes', 'limitations'])
    || canonical(value.recipe) !== canonical(report.recipe) || canonical(value.face_ref) !== canonical(report.face_ref)
    || value.landmark_digest !== report.landmark_digest || !hash(value.review_sha256) || value.review_sha256 !== report.support_sha256
    || !dimensions(value.source_dimensions) || !dimensions(value.render_dimensions)
    || value.source_dimensions[0] !== report.source.width || value.source_dimensions[1] !== report.source.height
    || !integer(value.changed_pixels, 0, 8_000_000) || !integer(value.protected_face_boxes, 0, 4096)
    || value.native_solver !== 'rust-eye-makeup-enhance-v1'
    || canonical(value.limitations) !== canonical(['user-reviewed-visible-makeup-not-cosmetic-segmentation',
      'paired-nearby-skin-reference-not-known-underlying-skin', 'bounded-appearance-fading-not-makeup-removal',
      'no-pigment-pattern-generation-or-hidden-anatomy', 'authored-unrun-no-photo-quality-acceptance'])) return false;
  const observation = value.face_skin_observation;
  if (!fields(observation, ['contract', 'source_sha256', 'semantic_model_sha256', 'producer_width', 'producer_height'])
    || observation.contract !== 'mediapipe-face-skin-edit-weight-v1' || observation.source_sha256 !== report.source.sha256
    || !hash(observation.semantic_model_sha256) || !integer(observation.producer_width, 1, 1_000_000)
    || !integer(observation.producer_height, 1, 1_000_000) || !object(value.sides) || !Object.keys(value.sides).length
    || Object.keys(value.sides).some(side => !SIDES.includes(side as Side))) return false;
  let changed = 0;
  for (const side of SIDES) {
    const active = CONTROLS.some(control => report.recipe[control][side] !== 0);
    if (Object.hasOwn(value.sides, side) !== active) return false;
    if (!active) continue;
    const row = value.sides[side];
    if (!fields(row, ['reviewed_makeup_pixels', 'permitted_makeup_pixels', 'reference_pixels', 'measured_eye_width', 'radius', 'controls', 'changed_pixels', 'reason'])
      || !integer(row.reviewed_makeup_pixels, 32, 4_000_000) || !integer(row.permitted_makeup_pixels, 32, 4_000_000)
      || row.permitted_makeup_pixels > row.reviewed_makeup_pixels || row.permitted_makeup_pixels * 10 < row.reviewed_makeup_pixels * 7
      || !integer(row.changed_pixels, 0, 4_000_000) || !boundedNumber(row.measured_eye_width, 32, 1_500_000)
      || !integer(row.radius, 1, 64) || !fields(row.controls, CONTROLS)
      || !Array.isArray(row.reference_pixels) || row.reference_pixels.length !== 2) return false;
    const controls = row.controls;
    if (!CONTROLS.every(control => validAmount(controls[control]) && controls[control] === report.recipe[control][side])
      || !row.reference_pixels.every(n => integer(n, 0, 4_000_000) && (controls.amount !== 0 ? n >= 16 : n === 0))
      || (row.changed_pixels === 0 ? row.reason !== 'no_measurable_change' : row.reason !== null)) return false;
    changed += row.changed_pixels;
  }
  return changed === value.changed_pixels;
}
export function reviewReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  const payload = result.payload, next = result.doc_state?.people as View | undefined, proof = request.payload.reference_proof, eyes = request.payload.eyes;
  if (request.action !== 'eye_makeup_enhance_review' || !proofValid(proof) || request.target.scope !== 'face'
    || canonical(request.target.face_ref) !== canonical(proof.face_ref) || request.target.target_id !== proof.face_ref.face_instance_id
    || !integer(request.association_revision, 0, Number.MAX_SAFE_INTEGER) || !object(eyes) || !Object.keys(eyes).length
    || Object.keys(eyes).some(side => !SIDES.includes(side as Side))
    || !Object.values(eyes).every(eye => object(eye) && typeof eye.reference_confirmed === 'boolean')
    || !object(payload) || Object.keys(payload).sort().join(',') !== 'kind,reference_proof,support_sha256'
    || payload.kind !== 'eye_makeup_enhance_review' || canonical(payload.reference_proof) !== canonical(proof)
    || !hash(payload.support_sha256) || !next || !object(next.binding) || !object(next.resolved)
    || !integer(request.document_revision, 0, Number.MAX_SAFE_INTEGER - 1) || !integer(request.state_revision, 0, Number.MAX_SAFE_INTEGER - 1)
    || next.binding.document_id !== request.document_id || next.binding.document_epoch !== request.document_epoch
    || next.binding.asset_sha256 !== proof.source.sha256 || next.binding.document_revision !== request.document_revision + 1
    || next.revision !== request.state_revision + 1 || next.association_revision !== request.association_revision
    || next.selected_face_id !== request.target.target_id || canonical(next.editing_target) !== canonical(request.target)
    || canonical(next.resolved.face_ref) !== canonical(proof.face_ref) || next.resolved.state_revision !== next.revision
    || next.resolved.association_revision !== next.association_revision || !object(next.resolved.operations)) return false;
  const report = next.eye_makeup_enhance;
  if (!fields(report, ['recipe', 'facts', 'source', 'face_ref', 'landmark_digest', 'reviewed', 'source_preview', 'reference_proof',
    'support_sha256', 'sides', 'native_available', 'support_available', 'support_reason', 'suspended'])
    || canonical(report.face_ref) !== canonical(proof.face_ref) || canonical(report.source) !== canonical(proof.source)
    || report.landmark_digest !== proof.landmark_digest || report.reviewed !== true || report.support_sha256 !== payload.support_sha256
    || report.source_preview !== null || report.reference_proof !== null || typeof report.native_available !== 'boolean'
    || typeof report.support_available !== 'boolean' || !diagnostic(report.support_reason) || !diagnostic(report.suspended)
    || !object(report.sides) || Object.keys(report.sides).some(side => !SIDES.includes(side as Side))
    || !Object.values(report.sides).every(side => fields(side, ['reviewed', 'reference_reviewed'])
      && side.reviewed === true && typeof side.reference_reviewed === 'boolean')) return false;
  try {
    const recipe = check(report.recipe), operation = next.resolved.operations[OP];
    if (!object(operation) || !CONTROLS.every(control => (['linked', ...SIDES] as const).every(field =>
      operation[`/${control}/${field}`]?.value === recipe[control][field])) || !reviewFactsValid(report.facts, report)) return false;
  } catch {return false;}
  // Live analysis may disappear after review. Retained support is still a known
  // write outcome, but unavailable sides must not acquire invented authority.
  return !report.support_available || Object.keys(report.sides).length > 0 && Object.entries(eyes).every(([side, eye]) =>
    report.sides[side as Side]?.reviewed === true && report.sides[side as Side]?.reference_reviewed === (eye as Record<string, unknown>).reference_confirmed);
}
export function releasedReferenceReceiptValid(request: PeopleAction, result: PeopleResult): boolean {
  const raw = result as unknown as Record<string, unknown>;
  return request.action === 'eye_makeup_enhance_reference' && request.target.scope === 'face' && canonical(request.payload) === '{}'
    && result.action === request.action && result.request_id === request.request_id && result.document_id === request.document_id
    && Object.keys(raw).sort().join(',') === 'action,batch_id,created_id,document_id,error,event,eye_makeup_enhance_request,frame_emitted,outcome_unknown,payload_released,protocol,request_id,success'
    && echoMatches(request, result) && raw.event === 'people_result' && raw.frame_emitted === false && raw.error === null
    && raw.created_id === null && raw.batch_id === null && result.success === true && result.outcome_unknown === false
    && result.payload_released === true && result.doc_state === undefined && result.payload === undefined;
}
export async function verifiedImage(preview: SourcePreview | null, proof: ReferenceProof | null): Promise<SourceImage> {
  if (!proofValid(proof) || !preview || preview.mime !== 'image/png' || preview.mapping !== 'source_pixel_centre_periocular_crop'
    || preview.sha256 !== proof.preview_sha256 || canonical(preview.source) !== canonical(proof.source)
    || ![preview.width,preview.height].every(n => Number.isSafeInteger(n) && n >= 2 && n <= 1280)
    || !Number.isFinite(preview.minimum_eye_width) || preview.minimum_eye_width < 40
    || !Array.isArray(preview.view_box) || preview.view_box.length !== 4 || !preview.view_box.every(Number.isFinite)
    || preview.view_box[2] <= 0 || preview.view_box[3] <= 0 || preview.view_box[2] > proof.source.width * 1.01 || preview.view_box[3] > proof.source.height * 1.01
    || preview.base64.length > 6_990_508 || preview.base64.length % 4 !== 0 || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(preview.base64)) throw Error('眼妆来源裁切缺少完整图像证明。');
  const bytes = Uint8Array.from(atob(preview.base64), c => c.charCodeAt(0));
  const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), n => n.toString(16).padStart(2, '0')).join('');
  if (actual !== proof.preview_sha256) throw Error('眼妆源 PNG 字节校验失败，不能审核。');
  return {url: `data:image/png;base64,${preview.base64}`, width: preview.width, height: preview.height, viewBox: preview.view_box.join(' ')};
}
