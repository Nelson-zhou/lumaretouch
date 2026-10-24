// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';
import {clavicleApplicabilityConflict} from './clavicleReview';
import {skinBodyAttached, skinBodyReport} from '../skinColour/bodyReviewModel';

/** Reviewed observed-source clavicle light/shadow; never reconstructed anatomy or copied traces. */
export const COLLARBONE_OPERATION = 'lnx.collarbone.v1';
export const COLLARBONE_CONTROL_ID = 'LNX-REF-PC-32465-C-abf0a5c8c9';
export const COLLARBONE_CONTROL_PATH = '锁骨增强';
export const COLLARBONE_SOURCE = 'https://www.pixcakeai.com/guide/32465';
export const COLLARBONE_LABEL = '锁骨现有明暗增强（手绘审核）';
export type CollarboneRecipe = {version: 1; amount: number};
export type CollarboneCapability = {collarbone_available?: boolean; collarbone_reason?: string | null};
export const neutralCollarbone = (): CollarboneRecipe => ({version: 1, amount: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const owns = (values: object, id: string | null) => !!id && Object.prototype.hasOwnProperty.call(values, id);

export function checkCollarbone(value: unknown): CollarboneRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('锁骨现有明暗增强配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'amount,version' || recipe.version !== 1 || !validAmount(recipe.amount)) {
    throw Error('锁骨现有明暗增强必须使用版本 1 与 0 到 1 的有限强度。');
  }
  return {version: 1, amount: recipe.amount};
}

export function collarboneReadiness(capability?: CollarboneCapability | null): {available: boolean; reason?: string} {
  return capability?.collarbone_available === true ? {available: true} : {available: false,
    reason: capability?.collarbone_reason || '锁骨现有明暗增强核心尚不可用，请使用包含该核心的完整版本。'};
}

function confirmedMember(view: PeopleView, personId: string | null, faceId: string): boolean {
  return owns(view.persons, personId) && view.links.some(link => link.person_id === personId
    && link.face_instance_id === faceId && link.state === 'confirmed'
    && link.confirmation_revision !== null && revision(link.confirmation_revision)
    && link.confirmation_revision <= view.association_revision);
}

/** Resolved provenance must also belong to this source and face; never relabel local intent as authority. */
function sourceMatches(view: PeopleView, face: FaceRef, source: ResolvedParameter): boolean {
  const belongs = (targetId: string | null) => {
    if (source.scope === 'default') return targetId === null;
    if (source.scope === 'all_people') return targetId === view.binding.asset_sha256;
    if (source.scope === 'face') return targetId === face.face_instance_id;
    if (source.scope === 'group') return owns(view.groups, targetId)
      && view.groups[targetId!].face_ids.includes(face.face_instance_id);
    if (source.scope === 'person') return confirmedMember(view, targetId, face.face_instance_id);
    return false;
  };
  return belongs(source.target_id) && (!source.contributing_targets || source.contributing_targets.every(belongs));
}

export type CollarboneReading = {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
};
/** Effective selected-face value, its provenance and explicit shared intent remain separate. */
export function collarboneReading(view: PeopleView | null | undefined): CollarboneReading {
  const path = '/amount', explicit = view?.editing_overrides[COLLARBONE_OPERATION]?.[path];
  const override = validAmount(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此人物实际生效的锁骨现有明暗增强强度。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === COLLARBONE_OPERATION)) {
    return {value: null, override, overridePresent, reason: '锁骨现有明暗增强存在分组优先级冲突，请在人物栏确认范围并解决冲突。'};
  }
  const source = resolved.operations[COLLARBONE_OPERATION]?.[path];
  if (!source || !validAmount(source.value) || !sourceMatches(view, selected.face_ref, source)) {
    return {value: null, override, overridePresent,
      reason: '引擎尚未提供此人物的有效锁骨现有明暗增强读数与所属来源；不会用中性占位值冒充实际强度。'};
  }
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery depends on current ownership, not a selected preview, anatomy or available core. */
export function collarboneTargetReady(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && owns(view.groups, target.target_id);
  if (target.scope === 'person') return target.face_ref === null && owns(view.persons, target.target_id);
  if (target.scope !== 'face') return false;
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return !!face && !!face.face_ref.face_instance_id && revision(face.face_ref.analysis_revision)
    && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}

/** Sharing an amount never borrows a selected person's body mask or colour reference. */
export function collarboneSelectionMatches(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target, selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !target || !selected || !collarboneTargetReady(view)) return false;
  if (selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)) return false;
  if (target.scope === 'face') return sameFace(selected.face_ref, target.face_ref);
  if (target.scope === 'all_people') return true;
  if (target.scope === 'group') return view.groups[target.target_id!].face_ids.includes(selected.face_ref.face_instance_id);
  return target.scope === 'person' && confirmedMember(view, target.target_id, selected.face_ref.face_instance_id);
}

export type CollarboneFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
/** Selected-person status is not evidence that every member of a shared target has support. */
export function collarboneReviewed(view: PeopleView | null | undefined): boolean {
  const report = skinBodyReport(view, 'collarbone');
  return skinBodyAttached(view, 'collarbone') === true && report?.needs_review === false;
}
export function collarboneAccess(view: PeopleView | null | undefined,
  capability: CollarboneCapability | null | undefined, fences: CollarboneFences) {
  const reading = collarboneReading(view), core = collarboneReadiness(capability), targetReady = collarboneTargetReady(view);
  const selectionMatches = collarboneSelectionMatches(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const applicabilityReason = clavicleApplicabilityConflict(selected?.labels);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const editValue = !targetReady || !selectionMatches ? null : reading.overridePresent ? reading.override
    : view?.editing_target?.scope === 'face' ? reading.value : null;
  const reviewed = collarboneReviewed(view);
  // The first review stages an explicit local amount; never persist active amount without support.
  const reviewDisabled = !!applicabilityReason || resetDisabled || !selectionMatches || !measuredFace || reading.value === null || !core.available;
  const changeDisabled = reviewDisabled || !reviewed;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !targetReady ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectionMatches ? '所选人脸不属于当前编辑目标或已确认关联，请重新选择人物或范围。'
    : applicabilityReason ?? reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人物尚未启用或未完成真实分析。' : core.reason)
      ?? (!reviewed ? '请先为锁骨现有明暗增强独立手绘并审核此人物的身体皮肤与可见锁骨曲线，并确认适用类别；其他功能的审核不能授权本功能。' : undefined);
  return {reading, core, editValue, resetDisabled, changeDisabled, reviewDisabled, reviewed, reason};
}

/** Source, owner, membership and authoritative state changes discard drafts and late callbacks. */
export function collarboneBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    collarboneTargetReady(view), view.selected_face_id, view.faces, view.groups, view.persons, view.links,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[COLLARBONE_OPERATION], view.resolved?.conflicts,
    view.editing_overrides[COLLARBONE_OPERATION], view.collarbone, view.refusals]);
}
export function collarbonePatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('锁骨现有明暗增强强度必须是 0 到 1 的有限数值。');
  return {operation_id: COLLARBONE_OPERATION, parameter_path: '/amount', unset: false, value};
}
/** Exactly this operation and target, not inheritance restore or any old-smoothing change. */
export function collarboneResetPatches(): ParameterPatch[] {return [collarbonePatch(0)];}
export function parseCollarboneChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
