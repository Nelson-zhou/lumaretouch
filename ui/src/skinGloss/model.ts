// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Existing face-skin highlights only; not smoothing, colour, makeup or body support. */
export const SKIN_GLOSS_OPERATION = 'lnx.skin_gloss.v1';
export const SKIN_GLOSS_CONTROL_ID = 'LNX-REF-PC-32465-C-1eed7cf9a9';
export const SKIN_GLOSS_CONTROL_PATH = '皮肤质感/光泽度';
export const SKIN_GLOSS_SOURCE = 'https://www.pixcakeai.com/guide/32465';
export type SkinGlossRecipe = {version: 1; amount: number};
export type SkinGlossCapability = {skin_gloss_available?: boolean; skin_gloss_reason?: string | null};
export const neutralSkinGloss = (): SkinGlossRecipe => ({version: 1, amount: 0});

const signedValue = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function skinGlossReadiness(capability?: SkinGlossCapability | null): {available: boolean; reason?: string} {
  return capability?.skin_gloss_available === true ? {available: true} : {available: false,
    reason: capability?.skin_gloss_reason || '面部光泽度核心尚不可用，请使用包含该核心的完整版本。'};
}

/** A shared write target is not the effective amount of the selected face. */
export function skinGlossReading(view: PeopleView | null | undefined): {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
} {
  const explicit = view?.editing_overrides[SKIN_GLOSS_OPERATION]?.['/amount'];
  const override = signedValue(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的光泽度参数。'};
  const resolved = view.resolved;
  if (!resolved || !sameFace(resolved.face_ref, selected.face_ref)
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || !revision(selected.face_ref.analysis_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === SKIN_GLOSS_OPERATION && conflict.parameter_path === '/amount')) {
    return {value: null, override, overridePresent, reason: '光泽度存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[SKIN_GLOSS_OPERATION]?.['/amount'];
  if (!source || !signedValue(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效光泽度参数；不会用中性占位值冒充实际读数。'};
  return {value: source.value, source, override, overridePresent};
}

/** Recovery needs a current owned target, but not working anatomy, highlights or core. */
export function skinGlossTargetReady(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.groups, target.target_id ?? '');
  if (target.scope === 'person') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.persons, target.target_id ?? '');
  if (target.scope !== 'face') return false;
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return !!face && !!face.face_ref.face_instance_id && revision(face.face_ref.analysis_revision)
    && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}
export type SkinGlossFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function skinGlossAccess(view: PeopleView | null | undefined,
  capability: SkinGlossCapability | null | undefined, fences: SkinGlossFences) {
  const reading = skinGlossReading(view), core = skinGlossReadiness(capability);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !skinGlossTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const changeDisabled = resetDisabled || !measuredFace || reading.value === null || !core.available;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !skinGlossTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, resetDisabled, changeDisabled, reason};
}

/** Discard stale input drafts when document, selected face, readback or write target changes. */
export function skinGlossBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status, view.resolved?.face_ref]);
}
export function skinGlossPatch(value: number): ParameterPatch {
  if (!signedValue(value)) throw Error('光泽度参数必须是 -1 到 1 的有限数值。');
  return {operation_id: SKIN_GLOSS_OPERATION, parameter_path: '/amount', unset: false, value};
}
