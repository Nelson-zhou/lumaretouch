// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Source-measured below-all-lips length, never a conversion of historical small_chin. */
export const CHIN_LENGTH_OPERATION = 'lnx.chin_length.v1';
export const LEGACY_SMALL_CHIN_OPERATION = 'lnx.deform.v1';
export const CHIN_LENGTH_CONTROL_ID = 'LNX-REF-PC-32466-C-44a42baef4';
export const CHIN_LENGTH_CONTROL_PATH = '脸型/下巴长短';
export const CHIN_LENGTH_SOURCE = 'https://wiki.pixcakeai.com/guide/9405.html';
export const CHIN_LENGTH_FROZEN_SOURCE = 'https://www.pixcakeai.com/guide/32466';
export type ChinLengthRecipe = {version: 1; amount: number};
export type ChinLengthCapability = {chin_length_available?: boolean; chin_length_reason?: string | null};
export const neutralChinLength = (): ChinLengthRecipe => ({version: 1, amount: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;

export function checkChinLength(value: unknown): ChinLengthRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('下巴长短配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'amount,version' || recipe.version !== 1 || !validAmount(recipe.amount)) {
    throw Error('下巴长短必须使用版本 1 与 -1 到 1 的有限数值。');
  }
  return {version: 1, amount: recipe.amount};
}

export function chinLengthReadiness(capability?: ChinLengthCapability | null): {available: boolean; reason?: string} {
  return capability?.chin_length_available === true ? {available: true} : {available: false,
    reason: capability?.chin_length_reason || '下巴长短局部纵向调整核心尚不可用，请使用包含该核心的完整版本。'};
}

export type ChinLengthReading = {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
};
function readLeaf(view: PeopleView | null | undefined, operation: string, path: string, label: string): ChinLengthReading {
  const explicit = view?.editing_overrides[operation]?.[path];
  const override = validAmount(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: `请选择人物，查看此脸实际生效的${label}参数。`};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === operation && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: `${label}存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。`};
  }
  const source = resolved.operations[operation]?.[path];
  if (!source || !validAmount(source.value)) return {value: null, override, overridePresent,
    reason: `引擎尚未提供此脸的有效${label}读数；不会用中性占位值冒充实际参数。`};
  return {value: source.value, source, override, overridePresent};
}
export function chinLengthReading(view: PeopleView | null | undefined) {
  return {amount: readLeaf(view, CHIN_LENGTH_OPERATION, '/amount', '下巴长短'),
    legacy: readLeaf(view, LEGACY_SMALL_CHIN_OPERATION, '/small_chin', '旧版小下巴')};
}

/** Neutral recovery keeps ownership fences but does not require native readiness or anatomy. */
export function chinLengthTargetReady(view: PeopleView | null | undefined): boolean {
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

export type ChinLengthFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function chinLengthAccess(view: PeopleView | null | undefined,
  capability: ChinLengthCapability | null | undefined, fences: ChinLengthFences) {
  const reading = chinLengthReading(view), core = chinLengthReadiness(capability), targetReady = chinLengthTargetReady(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const target = view?.editing_target;
  const selectedTargetMatches = target?.scope !== 'face' || sameFace(selected?.face_ref, target.face_ref);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  // Each shared edit uses that target's own explicit intent or a blank user choice, never preview inheritance.
  const editable = (item: ChinLengthReading): number | null => !targetReady || !selectedTargetMatches ? null
    : item.overridePresent ? item.override : target?.scope === 'face' ? item.value : null;
  const editValue = editable(reading.amount), legacyEditValue = editable(reading.legacy);
  const active = reading.amount.value === null ? null : reading.amount.value !== 0;
  const legacyActive = reading.legacy.value === null ? null : reading.legacy.value !== 0;
  const targetActive = reading.amount.overridePresent ? reading.amount.override === null ? null : reading.amount.override !== 0 : false;
  const targetLegacyActive = reading.legacy.overridePresent ? reading.legacy.override === null ? null : reading.legacy.override !== 0 : false;
  const replacementNeeded = legacyActive === true || targetLegacyActive === true;
  const readReason = reading.amount.reason ?? reading.legacy.reason;
  const ownerReason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !targetReady ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectedTargetMatches ? '所选人脸不是当前独立编辑目标，请重新选择人物。' : undefined;
  const baseReason = ownerReason ?? readReason
    ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : undefined);
  const baseDisabled = resetDisabled || !selectedTargetMatches || !measuredFace
    || reading.amount.value === null || reading.legacy.value === null;
  const legacyConflict = legacyActive !== false || targetLegacyActive !== false;
  const newConflict = active !== false || targetActive !== false;
  const changeDisabled = baseDisabled || !core.available || legacyConflict;
  const replacementDisabled = baseDisabled || !core.available || !replacementNeeded;
  // Historical edits are not gated on the new native capability, but both intents must remain distinct.
  const legacyChangeDisabled = baseDisabled || newConflict;
  return {reading, core, editValue, legacyEditValue, active, legacyActive, targetActive, targetLegacyActive,
    replacementNeeded, resetDisabled, changeDisabled, replacementDisabled, legacyChangeDisabled,
    reason: baseReason ?? core.reason ?? (targetLegacyActive === null
      ? '当前范围的旧版显式数值无效，请先明确处理旧版设置；不会将未知数值当成 0。' : undefined) ?? (legacyConflict
      ? '旧版小下巴仍在所选人脸或当前范围的显式设置中生效。可保留旧效果，或明确选择新版数值后一次替换；不会自动换算。' : undefined),
    replacementReason: baseReason ?? core.reason ?? (!replacementNeeded ? '没有可确认的旧版效果或当前范围的旧版非零显式值需要替换。' : undefined),
    legacyReason: baseReason ?? (targetActive === null
      ? '当前范围的新版显式数值无效，请先明确处理新版设置；不会将未知数值当成 0。' : undefined)
      ?? (newConflict ? '请先归零当前生效或当前范围显式设置的新版下巴长短，不能与旧版小下巴同时启用。' : undefined)};
}

/** Includes both operations' provenance/overrides and membership, so replacement drafts cannot migrate. */
export function chinLengthBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    chinLengthTargetReady(view), view.groups, view.persons, view.links,
    view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[CHIN_LENGTH_OPERATION], view.resolved?.operations[LEGACY_SMALL_CHIN_OPERATION],
    view.resolved?.conflicts, view.editing_overrides[CHIN_LENGTH_OPERATION],
    view.editing_overrides[LEGACY_SMALL_CHIN_OPERATION], view.refusals]);
}
export function chinLengthPatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('下巴长短参数必须是 -1 到 1 的有限数值。');
  return {operation_id: CHIN_LENGTH_OPERATION, parameter_path: '/amount', unset: false, value};
}
export function legacySmallChinPatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('旧版小下巴参数必须是 -1 到 1 的有限数值。');
  return {operation_id: LEGACY_SMALL_CHIN_OPERATION, parameter_path: '/small_chin', unset: false, value};
}
/** A new neutral amount never clears legacy, migrates state or restores inheritance. */
export function chinLengthResetPatches(): ParameterPatch[] {return [chinLengthPatch(0)];}
/** Explicit opt-in only: one transaction, exactly old zero plus the user's new amount. No conversion. */
export function replaceLegacySmallChinPatches(value: number): ParameterPatch[] {
  return [legacySmallChinPatch(0), chinLengthPatch(value)];
}
/** Blank and malformed values are unknown, not consent to zero either recipe. */
export function parseChinLengthChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
