// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';
import {FACE_CONTOUR_KEYS, FACE_CONTOUR_OPERATION, FACE_CONTOUR_SIDES, faceContourBindingKey,
  faceContourReading, faceContourReadiness, faceContourTargetReady,
  type FaceContourCapability, type FaceContourFences} from '../faceContour/model';

/** Corrected measured-oval intent. Never reinterprets the historical deformation recipe. */
export const SLIM_FACE_OPERATION = 'lnx.slim_face.v2';
export const LEGACY_SLIM_FACE_OPERATION = 'lnx.deform.v1';
export const SLIM_FACE_CONTROL_ID = 'LNX-REF-PC-32466-C-da1d54e292';
export const SLIM_FACE_CONTROL_PATH = '脸型/瘦脸';
export const SLIM_FACE_SOURCE = 'https://wiki.pixcakeai.com/guide/9405.html';
export const SLIM_FACE_SIDES = ['left', 'right'] as const;
export type SlimFaceSide = typeof SLIM_FACE_SIDES[number];
export type SlimFaceRecipe = {version: 2; linked: boolean; left: number; right: number};
export type SlimFaceCapability = FaceContourCapability;
export type SlimFaceFences = FaceContourFences;
export const neutralSlimFace = (): SlimFaceRecipe => ({version: 2, linked: true, left: 0, right: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const validLinked = (value: unknown): value is boolean => typeof value === 'boolean';
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function checkSlimFace(value: unknown): SlimFaceRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('瘦脸配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'left,linked,right,version' || recipe.version !== 2
    || !validLinked(recipe.linked) || !validAmount(recipe.left) || !validAmount(recipe.right)) {
    throw Error('瘦脸必须使用版本 2、布尔联动与人物自身左右侧 -1 到 1 的有限数值。');
  }
  return {version: 2, linked: recipe.linked, left: recipe.left, right: recipe.right};
}

export type SlimFaceReading<T> = {
  value: T | null; source?: ResolvedParameter; override: T | null; overridePresent: boolean; reason?: string;
};
function readLeaf<T extends number | boolean>(view: PeopleView | null | undefined, operation: string,
  path: string, valid: (value: unknown) => value is T): SlimFaceReading<T> {
  const explicit = view?.editing_overrides[operation]?.[path];
  const override = valid(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的新旧瘦脸参数。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === operation && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: '此项存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[operation]?.[path];
  if (!source || !valid(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供有效的新旧瘦脸读数；不会用中性占位值冒充实际参数。'};
  return {value: source.value, source, override, overridePresent};
}

export function slimFaceReading(view: PeopleView | null | undefined) {
  return {left: readLeaf(view, SLIM_FACE_OPERATION, '/left', validAmount),
    right: readLeaf(view, SLIM_FACE_OPERATION, '/right', validAmount),
    linked: readLeaf(view, SLIM_FACE_OPERATION, '/linked', validLinked),
    legacy: readLeaf(view, LEGACY_SLIM_FACE_OPERATION, '/slim_face', validAmount)};
}

/** Null means unknown, not neutral. Backend checks every affected face, not just this preview face. */
export function slimFaceAccess(view: PeopleView | null | undefined,
  capability: SlimFaceCapability | null | undefined, fences: SlimFaceFences) {
  const reading = slimFaceReading(view), core = faceContourReadiness(capability);
  const contour = FACE_CONTOUR_KEYS.flatMap(key => {
    const part = faceContourReading(view, key);
    return FACE_CONTOUR_SIDES.map(side => part[side]);
  });
  const legacyActive = reading.legacy.value === null ? null : reading.legacy.value !== 0;
  const active = reading.left.value === null || reading.right.value === null ? null
    : reading.left.value !== 0 || reading.right.value !== 0;
  const contourActive = contour.some(item => item.value === null) ? null : contour.some(item => item.value !== 0);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !faceContourTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target;
  const selectedTargetMatches = target?.scope !== 'face' || sameFace(selected?.face_ref, target.face_ref);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const writeLinked = reading.linked.overridePresent ? reading.linked.override
    : target?.scope === 'face' && selectedTargetMatches ? reading.linked.value : null;
  const familyConflict = !!view?.resolved?.conflicts.some(conflict => conflict.operation_id === SLIM_FACE_OPERATION
    || conflict.operation_id === FACE_CONTOUR_OPERATION
    || (conflict.operation_id === LEGACY_SLIM_FACE_OPERATION && conflict.parameter_path === '/slim_face'));
  const readReason = reading.left.reason ?? reading.right.reason ?? reading.linked.reason
    ?? reading.legacy.reason ?? contour.find(item => item.reason)?.reason;
  const ownerReason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !faceContourTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。' : undefined;
  const baseReason = ownerReason
    ?? (!selectedTargetMatches ? '所选人脸不是当前独立编辑目标，请重新选择人物。' : undefined)
    ?? readReason
    ?? (familyConflict ? '新旧瘦脸或独立轮廓存在分组冲突，请先解决冲突或归零。' : undefined)
    ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : undefined)
    ?? core.reason
    ?? (writeLinked === null ? '共享范围没有明确的联动设置，请先选择联动或独立，不能用某一张脸替其他人物决定。' : undefined)
    ?? (contourActive !== false ? '太阳穴、颧骨或下颌仍有独立二维轮廓调整；请先处理该效果，不能叠加新版瘦脸。' : undefined);
  const baseDisabled = resetDisabled || !selectedTargetMatches || !measuredFace || !core.available
    || familyConflict || !!readReason || writeLinked === null || contourActive !== false;
  const changeDisabled = baseDisabled || legacyActive !== false;
  const replacementDisabled = baseDisabled || legacyActive !== true;
  // Historical editing is independent of the corrected core, but cannot coexist with active v2.
  const legacyChangeDisabled = resetDisabled || !selectedTargetMatches || !measuredFace
    || reading.legacy.value === null || active !== false;
  const legacyReason = ownerReason
    ?? (!selectedTargetMatches ? '所选人脸不是当前独立编辑目标。' : undefined)
    ?? reading.legacy.reason ?? reading.left.reason ?? reading.right.reason
    ?? (!measuredFace ? fences.faceWhy || '所选人脸没有可用分析。' : undefined)
    ?? (active !== false ? '请先归零当前生效的新版瘦脸，不能同时叠加旧版。' : undefined);
  return {reading, core, contourActive, legacyActive, active, writeLinked, resetDisabled, changeDisabled,
    replacementDisabled, legacyChangeDisabled, legacyReason,
    reason: baseReason ?? (legacyActive !== false ? '旧版瘦脸仍在生效。可保留旧效果，或在下方明确选择新数值后一次替换；不会自动转换。' : undefined),
    replacementReason: baseReason ?? (legacyActive !== true ? '当前所选人脸没有可确认的旧版瘦脸效果需要替换。' : undefined)};
}

/** Includes legacy provenance/conflicts, so a replacement draft can never migrate another source or face. */
export function slimFaceBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([faceContourBindingKey(view), faceContourTargetReady(view),
    view.resolved?.operations[SLIM_FACE_OPERATION], view.resolved?.operations[LEGACY_SLIM_FACE_OPERATION],
    view.resolved?.conflicts, view.editing_overrides[SLIM_FACE_OPERATION],
    view.editing_overrides[LEGACY_SLIM_FACE_OPERATION]]);
}
export function slimFaceAmountPatch(side: SlimFaceSide, value: number): ParameterPatch {
  if (!SLIM_FACE_SIDES.includes(side) || !validAmount(value)) throw Error('请选择人物自身左右侧与 -1 到 1 的有限瘦脸数值。');
  return {operation_id: SLIM_FACE_OPERATION, parameter_path: `/${side}`, unset: false, value};
}
export function slimFaceAdjustPatches(side: SlimFaceSide, value: number, linked: boolean): ParameterPatch[] {
  const patch = slimFaceAmountPatch(side, value);
  if (!validLinked(linked)) throw Error('请先明确当前范围的联动设置。');
  return linked ? SLIM_FACE_SIDES.map(item => slimFaceAmountPatch(item, value)) : [patch];
}
/** Flag-only. Unequal values are retained until the user's next linked numeric edit. */
export function slimFaceLinkPatch(linked: boolean): ParameterPatch {
  if (!validLinked(linked)) throw Error('瘦脸联动设置必须为布尔值。');
  return {operation_id: SLIM_FACE_OPERATION, parameter_path: '/linked', unset: false, value: linked};
}
export function slimFaceResetPatches(): ParameterPatch[] {
  return SLIM_FACE_SIDES.map(side => slimFaceAmountPatch(side, 0));
}
export function legacySlimFacePatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('旧版瘦脸数值必须是 -1 到 1 的有限数值。');
  return {operation_id: LEGACY_SLIM_FACE_OPERATION, parameter_path: '/slim_face', unset: false, value};
}
/** One transaction; explicit zero suppresses inherited legacy at this target. Never unsets or converts it. */
export function replaceLegacySlimFacePatches(left: number, right: number, linked: boolean): ParameterPatch[] {
  if (!validLinked(linked) || (linked && left !== right)) throw Error('联动替换必须明确选择同一个左右数值。');
  return [legacySlimFacePatch(0), slimFaceAmountPatch('left', left), slimFaceAmountPatch('right', right)];
}
/** Blank is deliberately not zero; replacement always needs a user-chosen finite display value. */
export function parseSlimFaceChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
