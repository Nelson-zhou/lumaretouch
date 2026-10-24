// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Independent handbook leaves, not aliases of exposure, tint, blush or smoothing. */
export const SKIN_FINISH_OPERATION = 'lnx.skin_finish.v1';
export const SKIN_FINISH_KEYS = ['whitening', 'rosiness'] as const;
export type SkinFinishKey = typeof SKIN_FINISH_KEYS[number];
export type SkinFinishRecipe = {version: 1; whitening: number; rosiness: number};
export const SKIN_FINISH_CONTROL_IDS = {
  whitening: 'LNX-REF-PC-32465-C-d82f09f52f',
  rosiness: 'LNX-REF-PC-32465-C-60936d5259',
} as const;
export const SKIN_FINISH_LABELS = {whitening: '肤色美白', rosiness: '皮肤红润'} as const;
export type SkinFinishCapability = {skin_finish_available?: boolean; skin_finish_reason?: string | null};
export const neutralSkinFinish = (): SkinFinishRecipe => ({version: 1, whitening: 0, rosiness: 0});
export function skinFinishReadiness(capability?: SkinFinishCapability | null): {available: boolean; reason?: string} {
  return capability?.skin_finish_available === true ? {available: true} : {available: false,
    reason: capability?.skin_finish_reason || '美白与红润核心尚不可用，请使用包含该核心的完整版本。'};
}
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const unitValue = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 1;

/** A shared write target is not the effective value of the selected face. */
export function skinFinishReading(view: PeopleView | null | undefined, key: SkinFinishKey): {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
} {
  const path = `/${key}`, explicit = view?.editing_overrides[SKIN_FINISH_OPERATION]?.[path];
  const override = unitValue(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent, reason: '请选择人物，查看此脸实际生效的美白与红润参数。'};
  const resolved = view.resolved;
  if (!resolved || !sameFace(resolved.face_ref, selected.face_ref)
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === SKIN_FINISH_OPERATION && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: '此项存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[SKIN_FINISH_OPERATION]?.[path];
  if (!source || !unitValue(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效美白与红润参数；不会用中性占位值冒充实际读数。'};
  return {value: source.value, source, override, overridePresent};
}

/** Zero recovery keeps source/owner fences, without depending on the native effect. */
export function skinFinishTargetReady(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.groups, target.target_id ?? '');
  if (target.scope === 'person') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.persons, target.target_id ?? '');
  if (target.scope !== 'face') return false;
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return !!face && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}
export type SkinFinishFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function skinFinishAccess(view: PeopleView | null | undefined, key: SkinFinishKey,
  capability: SkinFinishCapability | null | undefined, fences: SkinFinishFences) {
  const reading = skinFinishReading(view, key), core = skinFinishReadiness(capability);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !skinFinishTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const changeDisabled = resetDisabled || !measuredFace || reading.value === null || !core.available;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !skinFinishTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, resetDisabled, changeDisabled, reason};
}
export function skinFinishBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    view.selected_face_id, view.resolved?.face_ref]);
}
export function skinFinishPatch(key: SkinFinishKey, value: number): ParameterPatch {
  if (!SKIN_FINISH_KEYS.includes(key) || !unitValue(value)) throw Error('美白与红润参数必须是 0 到 1 的有限数值。');
  return {operation_id: SKIN_FINISH_OPERATION, parameter_path: `/${key}`, unset: false, value};
}
