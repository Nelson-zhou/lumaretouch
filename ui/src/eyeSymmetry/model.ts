// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';
import type {EyeSymmetryRecipe, EyeSymmetryReference} from '../native';
export type {EyeSymmetryRecipe, EyeSymmetryReference} from '../native';

export const EYE_SYMMETRY_OPERATION = 'lnx.eye_symmetry.v1';
export const EYE_SYMMETRY_KEYS = ['horizontal', 'size', 'reference'] as const;
export type EyeSymmetryKey = typeof EYE_SYMMETRY_KEYS[number];
export type EyeSymmetryScalar = Exclude<EyeSymmetryKey, 'reference'>;
export const EYE_SYMMETRY_CONTROL_IDS = {
  family: 'LNX-REF-PC-32470-C-2745ac86f5', horizontal: 'LNX-REF-PC-32470-C-a86e5c0175',
  size: 'LNX-REF-PC-32470-C-4601eb7797', reference: 'LNX-REF-PC-32470-C-118aa67e04',
} as const;
export const EYE_SYMMETRY_CONTROL_PATHS = {
  family: '眼睛对称', horizontal: '眼睛对称/水平对称', size: '眼睛对称/大小对称', reference: '眼睛对称/参考眼选择',
} as const;
export const EYE_SYMMETRY_SOURCE = 'https://www.pixcakeai.com/guide/32470';
export const EYE_SYMMETRY_LABELS = {horizontal: '水平对称', size: '大小对称', reference: '参考眼选择（仅大小对称）'} as const;
export const EYE_SYMMETRY_REFERENCE_LABELS = {auto: '自动：每个目标实测面积较大的眼', left: '人物左眼', right: '人物右眼'} as const;
export type EyeSymmetryCapability = {eye_symmetry_available?: boolean; eye_symmetry_reason?: string | null};
export const neutralEyeSymmetry = (): EyeSymmetryRecipe => ({version: 1, horizontal: 0, size: 0, reference: 'auto'});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 1;
export const validEyeSymmetryReference = (value: unknown): value is EyeSymmetryReference =>
  value === 'auto' || value === 'left' || value === 'right';
function validLeaf<K extends EyeSymmetryKey>(key: K, value: unknown): value is EyeSymmetryRecipe[K] {
  return key === 'reference' ? validEyeSymmetryReference(value) : validAmount(value);
}
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function checkEyeSymmetry(value: unknown): EyeSymmetryRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('眼睛对称配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'horizontal,reference,size,version' || recipe.version !== 1
    || !validAmount(recipe.horizontal) || !validAmount(recipe.size) || !validEyeSymmetryReference(recipe.reference)) {
    throw Error('眼睛对称必须使用版本 1、0 到 1 的有限水平与大小强度，以及 auto、left 或 right 参考眼。');
  }
  return {version: 1, horizontal: recipe.horizontal, size: recipe.size, reference: recipe.reference};
}
/** A manual reference alone has no geometric effect when both strengths are zero. */
export function eyeSymmetryNeutral(recipe: EyeSymmetryRecipe): boolean {
  return checkEyeSymmetry(recipe).horizontal === 0 && recipe.size === 0;
}
export function eyeSymmetryReadiness(capability?: EyeSymmetryCapability | null): {available: boolean; reason?: string} {
  return capability?.eye_symmetry_available === true ? {available: true} : {available: false,
    reason: capability?.eye_symmetry_reason || '眼睛对称核心尚不可用，请使用包含该核心的完整版本。'};
}

export type EyeSymmetryReading<K extends EyeSymmetryKey> = {
  value: EyeSymmetryRecipe[K] | null; source?: ResolvedParameter;
  override: EyeSymmetryRecipe[K] | null; overridePresent: boolean; reason?: string;
};
/** Selected-face authority is not a shared-target default. Unknown readings remain unknown. */
export function eyeSymmetryReading<K extends EyeSymmetryKey>(view: PeopleView | null | undefined, key: K): EyeSymmetryReading<K> {
  const explicit = view?.editing_overrides[EYE_SYMMETRY_OPERATION]?.[`/${key}`];
  const override = validLeaf(key, explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的眼睛对称参数。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === EYE_SYMMETRY_OPERATION)) {
    return {value: null, override, overridePresent, reason: '眼睛对称存在分组优先级冲突，请在人物栏解决冲突。'};
  }
  const source = resolved.operations[EYE_SYMMETRY_OPERATION]?.[`/${key}`];
  if (!source || !validLeaf(key, source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此项有效读数；不会用 0 或自动参考眼冒充实际参数。'};
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery needs current source/target authority, not anatomy or a native core. */
export function eyeSymmetryTargetReady(view: PeopleView | null | undefined): boolean {
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
export type EyeSymmetryFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function eyeSymmetryAccess<K extends EyeSymmetryKey>(view: PeopleView | null | undefined, key: K,
  capability: EyeSymmetryCapability | null | undefined, fences: EyeSymmetryFences) {
  const reading = eyeSymmetryReading(view, key), core = eyeSymmetryReadiness(capability), targetReady = eyeSymmetryTargetReady(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target;
  const selectedTargetMatches = target?.scope !== 'face' || sameFace(selected?.face_ref, target.face_ref);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
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

/** Source identity, membership and all three leaves invalidate drafts, including reference-only edits. */
export function eyeSymmetryBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    eyeSymmetryTargetReady(view), view.groups, view.persons, view.links, view.faces,
    view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[EYE_SYMMETRY_OPERATION], view.resolved?.conflicts,
    view.editing_overrides[EYE_SYMMETRY_OPERATION], view.refusals]);
}
export function eyeSymmetryPatch<K extends EyeSymmetryKey>(key: K, value: EyeSymmetryRecipe[K]): ParameterPatch {
  if (!EYE_SYMMETRY_KEYS.includes(key) || !validLeaf(key, value)) throw Error('眼睛对称参数无效。');
  return {operation_id: EYE_SYMMETRY_OPERATION, parameter_path: `/${key}`, unset: false, value};
}
/** A deliberate size/reference choice is one owner transaction, not two partially applied requests. */
export function eyeSymmetrySizePatches(size: number, reference: EyeSymmetryReference): ParameterPatch[] {
  return [eyeSymmetryPatch('size', size), eyeSymmetryPatch('reference', reference)];
}
/** One atomic reset. It neither unsets inheritance nor clears any neighboring operation. */
export function eyeSymmetryResetPatches(): ParameterPatch[] {
  return [eyeSymmetryPatch('horizontal', 0), ...eyeSymmetrySizePatches(0, 'auto')];
}
export function parseEyeSymmetryChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
