// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Measured visible 2D contour intent, independent of legacy slim-face geometry. */
export const FACE_CONTOUR_OPERATION = 'lnx.face_contour.v1';
export const FACE_CONTOUR_KEYS = ['temple', 'cheekbone', 'jaw'] as const;
export const FACE_CONTOUR_SIDES = ['left', 'right'] as const;
export type FaceContourKey = typeof FACE_CONTOUR_KEYS[number];
export type FaceContourSide = typeof FACE_CONTOUR_SIDES[number];
export type FaceContourBilateral = {linked: boolean; left: number; right: number};
export type FaceContourRecipe = {version: 1} & Record<FaceContourKey, FaceContourBilateral>;
export const FACE_CONTOUR_CONTROL_IDS = {
  temple: 'LNX-REF-PC-32466-C-94bf91612d',
  cheekbone: 'LNX-REF-PC-32466-C-d24d97d234',
  jaw: 'LNX-REF-PC-32466-C-3bc7e245b7',
} as const;
export const FACE_CONTOUR_CONTROL_PATHS = {temple: '脸型/太阳穴', cheekbone: '脸型/颧骨', jaw: '脸型/下颌'} as const;
export const FACE_CONTOUR_LABELS = {temple: '太阳穴', cheekbone: '颧骨', jaw: '下颌'} as const;
export const FACE_CONTOUR_SOURCE = 'https://wiki.pixcakeai.com/guide/9405.html';
export type FaceContourCapability = {face_contour_available?: boolean; face_contour_reason?: string | null};
export const neutralFaceContour = (): FaceContourRecipe => ({version: 1,
  temple: {linked: true, left: 0, right: 0}, cheekbone: {linked: true, left: 0, right: 0},
  jaw: {linked: true, left: 0, right: 0}});

const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const validLinked = (value: unknown): value is boolean => typeof value === 'boolean';
const validKey = (key: FaceContourKey) => FACE_CONTOUR_KEYS.includes(key);

export function checkFaceContour(value: unknown): FaceContourRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('面部轮廓配方无效。');
  const recipe = value as Record<string, unknown>;
  if (recipe.version !== 1 || Object.keys(recipe).sort().join(',') !== ['version', ...FACE_CONTOUR_KEYS].sort().join(',')) {
    throw Error('面部轮廓配方版本或字段无效。');
  }
  const out = neutralFaceContour();
  for (const key of FACE_CONTOUR_KEYS) {
    const item = recipe[key] as FaceContourBilateral | undefined;
    if (!item || typeof item !== 'object' || Array.isArray(item)
      || Object.keys(item).sort().join(',') !== 'left,linked,right'
      || !validLinked(item.linked) || !validAmount(item.left) || !validAmount(item.right)) {
      throw Error('面部轮廓双侧数值必须是 -1 到 1 的有限数值，联动必须为布尔值。');
    }
    out[key] = {...item};
  }
  return out;
}

export function faceContourReadiness(capability?: FaceContourCapability | null): {available: boolean; reason?: string} {
  return capability?.face_contour_available === true ? {available: true} : {available: false,
    reason: capability?.face_contour_reason || '二维面部轮廓核心尚不可用，请使用包含该核心的完整版本。'};
}

type Reading<T> = {value: T | null; source?: ResolvedParameter; override: T | null; overridePresent: boolean; reason?: string};
function readLeaf<T extends number | boolean>(view: PeopleView | null | undefined, path: string,
  valid: (value: unknown) => value is T): Reading<T> {
  const explicit = view?.editing_overrides[FACE_CONTOUR_OPERATION]?.[path];
  const override = valid(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的二维轮廓参数。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref)
    || !selected.face_ref.face_instance_id || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || !revision(selected.face_ref.analysis_revision) || !revision(view.binding.document_revision)
    || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === FACE_CONTOUR_OPERATION && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: '此项存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[FACE_CONTOUR_OPERATION]?.[path];
  if (!source || !valid(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效二维轮廓参数；不会用中性占位值冒充实际读数。'};
  return {value: source.value, source, override, overridePresent};
}

export function faceContourReading(view: PeopleView | null | undefined, key: FaceContourKey) {
  return {left: readLeaf(view, `/${key}/left`, validAmount), right: readLeaf(view, `/${key}/right`, validAmount),
    linked: readLeaf(view, `/${key}/linked`, validLinked)};
}

/** Neutral recovery retains exact source/target fences, without requiring anatomy or a working core. */
export function faceContourTargetReady(view: PeopleView | null | undefined): boolean {
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
export type FaceContourFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function faceContourAccess(view: PeopleView | null | undefined, key: FaceContourKey,
  capability: FaceContourCapability | null | undefined, fences: FaceContourFences) {
  const reading = faceContourReading(view, key), core = faceContourReadiness(capability);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !faceContourTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target;
  const selectedTargetMatches = target?.scope !== 'face' || sameFace(selected?.face_ref, target.face_ref);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  // A selected face's inherited link must never silently choose another scope's edit semantics.
  const writeLinked = reading.linked.overridePresent ? reading.linked.override
    : target?.scope === 'face' && selectedTargetMatches ? reading.linked.value : null;
  const readReason = reading.left.reason ?? reading.right.reason ?? reading.linked.reason;
  const familyConflict = !!view?.resolved?.conflicts.some(conflict => conflict.operation_id === FACE_CONTOUR_OPERATION);
  const changeDisabled = resetDisabled || !measuredFace || !selectedTargetMatches || !core.available
    || familyConflict || reading.left.value === null || reading.right.value === null || reading.linked.value === null || writeLinked === null;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !faceContourTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectedTargetMatches ? '所选人脸不是当前独立编辑目标，请重新选择人物。'
    : readReason ?? (familyConflict ? '二维轮廓其他参数存在分组优先级冲突，请先解决冲突或归零。'
      : !measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。'
      : core.reason ?? (writeLinked === null ? '共享范围没有明确的联动设置，请先选择联动或独立；不会用某一张脸的继承值替其他人物决定。' : undefined));
  return {reading, core, writeLinked, resetDisabled, changeDisabled, reason};
}

/** Source, target and authoritative changes discard drafts; no draft follows a different person. */
export function faceContourBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[FACE_CONTOUR_OPERATION],
    view.resolved?.conflicts.filter(conflict => conflict.operation_id === FACE_CONTOUR_OPERATION),
    view.editing_overrides[FACE_CONTOUR_OPERATION], view.refusals]);
}
export function faceContourAmountPatch(key: FaceContourKey, side: FaceContourSide, value: number): ParameterPatch {
  if (!validKey(key) || !FACE_CONTOUR_SIDES.includes(side) || !validAmount(value)) {
    throw Error('面部轮廓参数必须是有效部位、人物自身左右侧与 -1 到 1 的有限数值。');
  }
  return {operation_id: FACE_CONTOUR_OPERATION, parameter_path: `/${key}/${side}`, unset: false, value};
}
/** A linked numeric edit has two leaves in one owner transaction; it never pins inherited link flags. */
export function faceContourAdjustPatches(key: FaceContourKey, side: FaceContourSide, value: number, linked: boolean): ParameterPatch[] {
  const patch = faceContourAmountPatch(key, side, value);
  if (!validLinked(linked)) throw Error('请先明确当前范围的联动设置。');
  return linked ? FACE_CONTOUR_SIDES.map(item => faceContourAmountPatch(key, item, value)) : [patch];
}
/** Toggling link does not average, copy, synchronize or otherwise change either numeric side. */
export function faceContourLinkPatch(key: FaceContourKey, linked: boolean): ParameterPatch {
  if (!validKey(key) || !validLinked(linked)) throw Error('面部轮廓联动设置无效。');
  return {operation_id: FACE_CONTOUR_OPERATION, parameter_path: `/${key}/linked`, unset: false, value: linked};
}
/** Exactly six neutral numeric leaves (or one pair); every linked flag keeps its prior inheritance. */
export function faceContourResetPatches(key?: FaceContourKey): ParameterPatch[] {
  if (key !== undefined && !validKey(key)) throw Error('面部轮廓部位无效。');
  return (key === undefined ? FACE_CONTOUR_KEYS : [key]).flatMap(item =>
    FACE_CONTOUR_SIDES.map(side => faceContourAmountPatch(item, side, 0)));
}
