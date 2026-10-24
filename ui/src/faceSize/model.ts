// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Whole-face local scale, not contour narrowing, separate features or image resizing. */
export const FACE_SIZE_OPERATION = 'lnx.face_size.v1';
export const FACE_SIZE_CONTROL_ID = 'LNX-REF-PC-32466-C-728fc62cdd';
export const FACE_SIZE_CONTROL_PATH = '脸型/小脸';
export const FACE_SIZE_SOURCE = 'https://wiki.pixcakeai.com/guide/9405.html';
export const FACE_SIZE_FROZEN_SOURCE = 'https://www.pixcakeai.com/guide/32466';
export type FaceSizeRecipe = {version: 1; amount: number};
export type FaceSizeCapability = {face_size_available?: boolean; face_size_reason?: string | null};
export const neutralFaceSize = (): FaceSizeRecipe => ({version: 1, amount: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function checkFaceSize(value: unknown): FaceSizeRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('小脸配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'amount,version' || recipe.version !== 1 || !validAmount(recipe.amount)) {
    throw Error('小脸必须使用版本 1 与 -1 到 1 的有限整体大小数值。');
  }
  return {version: 1, amount: recipe.amount};
}

/** Product-local magnitude, not a handbook-prescribed range or quality guarantee. */
export function faceSizeLocalScale(amount: number): number {
  if (!validAmount(amount)) throw Error('小脸参数必须是 -1 到 1 的有限数值。');
  return 1 - .06 * amount;
}

export function faceSizeReadiness(capability?: FaceSizeCapability | null): {available: boolean; reason?: string} {
  return capability?.face_size_available === true ? {available: true} : {available: false,
    reason: capability?.face_size_reason || '局部整脸大小核心尚不可用，请使用包含该核心的完整版本。'};
}

export type FaceSizeReading = {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
};
/** A selected face's effective value is evidence, never a shared target's implicit edit value. */
export function faceSizeReading(view: PeopleView | null | undefined): FaceSizeReading {
  const explicit = view?.editing_overrides[FACE_SIZE_OPERATION]?.['/amount'];
  const override = validAmount(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的整脸大小参数。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === FACE_SIZE_OPERATION)) {
    return {value: null, override, overridePresent, reason: '小脸存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[FACE_SIZE_OPERATION]?.['/amount'];
  if (!source || !validAmount(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效小脸读数；不会用中性占位值冒充实际参数。'};
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery retains owner/source/target fences without requiring native code or anatomy. */
export function faceSizeTargetReady(view: PeopleView | null | undefined): boolean {
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

export type FaceSizeFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function faceSizeAccess(view: PeopleView | null | undefined,
  capability: FaceSizeCapability | null | undefined, fences: FaceSizeFences) {
  const reading = faceSizeReading(view), core = faceSizeReadiness(capability);
  const targetReady = faceSizeTargetReady(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target;
  const selectedTargetMatches = target?.scope !== 'face' || sameFace(selected?.face_ref, target.face_ref);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  // Shared edits start from their own explicit amount or an empty user choice, never selected-face inheritance.
  const editValue = !targetReady || !selectedTargetMatches ? null : reading.overridePresent ? reading.override
    : target?.scope === 'face' ? reading.value : null;
  const changeDisabled = resetDisabled || !selectedTargetMatches || !measuredFace || !core.available || reading.value === null;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !targetReady ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectedTargetMatches ? '所选人脸不是当前独立编辑目标，请重新选择人物。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, editValue, resetDisabled, changeDisabled, reason};
}

/** Old events and drafts cannot cross source, revision, target, selected face or authority changes. */
export function faceSizeBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    faceSizeTargetReady(view), view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[FACE_SIZE_OPERATION], view.resolved?.conflicts, view.editing_overrides[FACE_SIZE_OPERATION],
    view.refusals]);
}

export function faceSizePatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('小脸参数必须是 -1 到 1 的有限数值。');
  return {operation_id: FACE_SIZE_OPERATION, parameter_path: '/amount', unset: false, value};
}
export function faceSizeResetPatches(): ParameterPatch[] {
  return [faceSizePatch(0)];
}
/** Empty input is unknown, not a zero amount or permission to copy any other face. */
export function parseFaceSizeChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
