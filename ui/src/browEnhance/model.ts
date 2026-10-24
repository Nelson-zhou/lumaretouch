// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Existing source-measured dark-brow contrast, not brow material, shape or hair generation. */
export const BROW_ENHANCE_OPERATION = 'lnx.brow_enhance.v1';
export const BROW_ENHANCE_CONTROL_ID = 'LNX-REF-PC-32471-C-18765fa8ea';
export const BROW_ENHANCE_CONTROL_PATH = '眉毛增强';
export const BROW_ENHANCE_SOURCE = 'https://www.pixcakeai.com/guide/32471';
export const BROW_ENHANCE_SIDES = ['left', 'right'] as const;
export type BrowEnhanceSide = typeof BROW_ENHANCE_SIDES[number];
export type BrowEnhanceRecipe = {version: 1; linked: boolean; left: number; right: number};
export type BrowEnhanceCapability = {brow_enhance_available?: boolean; brow_enhance_reason?: string | null};
export const neutralBrowEnhance = (): BrowEnhanceRecipe => ({version: 1, linked: true, left: 0, right: 0});
const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const validLinked = (value: unknown): value is boolean => typeof value === 'boolean';
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function checkBrowEnhance(value: unknown): BrowEnhanceRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('眉毛增强配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'left,linked,right,version' || recipe.version !== 1
    || !validLinked(recipe.linked) || !validAmount(recipe.left) || !validAmount(recipe.right)
    || (recipe.linked && recipe.left !== recipe.right)) {
    throw Error('眉毛增强必须使用版本 1、布尔联动与 -1 到 1 的有限左右值；联动时左右值必须相同。');
  }
  return {version: 1, linked: recipe.linked, left: recipe.left, right: recipe.right};
}

export function browEnhanceReadiness(capability?: BrowEnhanceCapability | null): {available: boolean; reason?: string} {
  return capability?.brow_enhance_available === true ? {available: true} : {available: false,
    reason: capability?.brow_enhance_reason || '已有眉毛对比增强核心尚不可用，请使用包含该核心的完整版本。'};
}
export type BrowEnhanceReading<T> = {
  value: T | null; source?: ResolvedParameter; override: T | null; overridePresent: boolean; reason?: string;
};
function readLeaf<T extends number | boolean>(view: PeopleView | null | undefined,
  path: string, valid: (value: unknown) => value is T): BrowEnhanceReading<T> {
  const explicit = view?.editing_overrides[BROW_ENHANCE_OPERATION]?.[path];
  const override = valid(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的眉毛增强参数。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === BROW_ENHANCE_OPERATION)) {
    return {value: null, override, overridePresent, reason: '眉毛增强存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[BROW_ENHANCE_OPERATION]?.[path];
  if (!source || !valid(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效眉毛增强读数；不会用中性占位值冒充实际参数。'};
  return {value: source.value, source, override, overridePresent};
}

export function browEnhanceReading(view: PeopleView | null | undefined) {
  const left = readLeaf(view, '/left', validAmount), right = readLeaf(view, '/right', validAmount);
  const linked = readLeaf(view, '/linked', validLinked);
  if (linked.value === true && left.value !== null && right.value !== null && left.value !== right.value) {
    const reason = '引擎返回的眉毛增强联动左右值不一致，请等待有效读数或归零当前范围。';
    return {left: {...left, value: null, source: undefined, reason},
      right: {...right, value: null, source: undefined, reason},
      linked: {...linked, value: null, source: undefined, reason}};
  }
  return {left, right, linked};
}

/** Neutral recovery requires current ownership, not native availability or anatomy. */
export function browEnhanceTargetReady(view: PeopleView | null | undefined): boolean {
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
/** A preview face outside the current group or confirmed person is not an editing reference. */
function selectedTargetMatches(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target, selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !target || !selected) return false;
  if (target.scope === 'face') return sameFace(selected.face_ref, target.face_ref);
  if (target.scope === 'all_people') return target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return !!view.groups[target.target_id ?? '']?.face_ids.includes(selected.face_ref.face_instance_id);
  return view.links.some(link => link.person_id === target.target_id && link.face_instance_id === selected.face_ref.face_instance_id
    && link.state === 'confirmed' && link.confirmation_revision !== null && revision(link.confirmation_revision)
    && link.confirmation_revision <= view.association_revision);
}
export type BrowEnhanceFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function browEnhanceAccess(view: PeopleView | null | undefined,
  capability: BrowEnhanceCapability | null | undefined, fences: BrowEnhanceFences) {
  const reading = browEnhanceReading(view), core = browEnhanceReadiness(capability), targetReady = browEnhanceTargetReady(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target, selectionMatches = selectedTargetMatches(view);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  // Shared scopes never borrow the selected preview face's inherited mode or numbers.
  const editable = <T,>(item: BrowEnhanceReading<T>): T | null => !targetReady || !selectionMatches ? null
    : item.overridePresent ? item.override : target?.scope === 'face' ? item.value : null;
  const writeLinked = editable(reading.linked), editLeft = editable(reading.left), editRight = editable(reading.right);
  const readReason = reading.left.reason ?? reading.right.reason ?? reading.linked.reason;
  const changeDisabled = resetDisabled || !selectionMatches || !measuredFace || !core.available
    || reading.left.value === null || reading.right.value === null || reading.linked.value === null;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !targetReady ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectionMatches ? '所选人脸不属于当前编辑目标或已确认关联，请重新选择人物或范围。'
    : readReason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, writeLinked, editLeft, editRight, resetDisabled, changeDisabled, reason};
}

/** Discard drafts and callbacks on source, owner, target, membership, selection or authority changes. */
export function browEnhanceBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    browEnhanceTargetReady(view), view.selected_face_id, view.faces, view.groups, view.persons, view.links,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[BROW_ENHANCE_OPERATION], view.resolved?.conflicts,
    view.editing_overrides[BROW_ENHANCE_OPERATION], view.refusals]);
}
export function browEnhanceAmountPatch(side: BrowEnhanceSide, value: number): ParameterPatch {
  if (!BROW_ENHANCE_SIDES.includes(side) || !validAmount(value)) throw Error('请选择人物自身左右侧与 -1 到 1 的有限眉毛增强数值。');
  return {operation_id: BROW_ENHANCE_OPERATION, parameter_path: `/${side}`, unset: false, value};
}
export function browEnhanceAdjustPatches(side: BrowEnhanceSide, value: number, linked: boolean): ParameterPatch[] {
  const patch = browEnhanceAmountPatch(side, value);
  if (!validLinked(linked)) throw Error('请先明确当前范围的联动设置。');
  return linked ? BROW_ENHANCE_SIDES.map(item => browEnhanceAmountPatch(item, value)) : [patch];
}
/** Relinking is atomic and requires a deliberate common number; never copy or average existing sides. */
export function browEnhanceLinkedPatches(value: number): ParameterPatch[] {
  const sides = browEnhanceAdjustPatches('left', value, true);
  return [{operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/linked', unset: false, value: true}, ...sides];
}
export function browEnhanceUnlockPatch(): ParameterPatch {
  return {operation_id: BROW_ENHANCE_OPERATION, parameter_path: '/linked', unset: false, value: false};
}
/** Explicit one-sided recovery is atomic: unlock and zero the chosen side, never silently skip it. */
export function browEnhanceZeroSidePatches(side: BrowEnhanceSide): ParameterPatch[] {
  return [browEnhanceUnlockPatch(), browEnhanceAmountPatch(side, 0)];
}
export function browEnhanceResetPatches(): ParameterPatch[] {
  return BROW_ENHANCE_SIDES.map(side => browEnhanceAmountPatch(side, 0));
}
/** Blank and malformed text are unknown, never a zero or inherited default. */
export function parseBrowEnhanceChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
