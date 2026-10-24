// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Same-face measured low-frequency chroma, never a legacy smoothing gain or shared colour target. */
export const SKIN_EVENNESS_OPERATION = 'lnx.skin_evenness.v1';
export const SKIN_EVENNESS_CONTROL_ID = 'LNX-REF-PC-32465-C-60b7c0e3d1';
export const SKIN_EVENNESS_CONTROL_PATH = 'AI肤色统一（脸部）';
export const SKIN_EVENNESS_SOURCE = 'https://www.pixcakeai.com/guide/32465';
export const SKIN_EVENNESS_LABEL = '脸部色度均匀（原片自参考）';
export type SkinEvennessRecipe = {version: 1; amount: number};
export type SkinEvennessCapability = {skin_evenness_available?: boolean; skin_evenness_reason?: string | null};
export const neutralSkinEvenness = (): SkinEvennessRecipe => ({version: 1, amount: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const owns = (values: object, id: string | null) => !!id && Object.prototype.hasOwnProperty.call(values, id);

export function checkSkinEvenness(value: unknown): SkinEvennessRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('脸部色度均匀配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'amount,version' || recipe.version !== 1 || !validAmount(recipe.amount)) {
    throw Error('脸部色度均匀必须使用版本 1 与 0 到 1 的有限强度。');
  }
  return {version: 1, amount: recipe.amount};
}

export function skinEvennessReadiness(capability?: SkinEvennessCapability | null): {available: boolean; reason?: string} {
  return capability?.skin_evenness_available === true ? {available: true} : {available: false,
    reason: capability?.skin_evenness_reason || '脸部色度均匀核心尚不可用，请使用包含该核心的完整版本。'};
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

export type SkinEvennessReading = {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
};
/** Effective selected-face value, its provenance and explicit shared intent remain separate. */
export function skinEvennessReading(view: PeopleView | null | undefined): SkinEvennessReading {
  const path = '/amount', explicit = view?.editing_overrides[SKIN_EVENNESS_OPERATION]?.[path];
  const override = validAmount(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的色度均匀强度。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === SKIN_EVENNESS_OPERATION)) {
    return {value: null, override, overridePresent, reason: '脸部色度均匀存在分组优先级冲突，请在人物栏确认范围并解决冲突。'};
  }
  const source = resolved.operations[SKIN_EVENNESS_OPERATION]?.[path];
  if (!source || !validAmount(source.value) || !sourceMatches(view, selected.face_ref, source)) {
    return {value: null, override, overridePresent,
      reason: '引擎尚未提供此脸的有效色度均匀读数与所属来源；不会用中性占位值冒充实际强度。'};
  }
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery depends on current ownership, not a selected preview, anatomy or available core. */
export function skinEvennessTargetReady(view: PeopleView | null | undefined): boolean {
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

/** Sharing an amount never borrows the selected face's colour reference for another face. */
export function skinEvennessSelectionMatches(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target, selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !target || !selected || !skinEvennessTargetReady(view)) return false;
  if (selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)) return false;
  if (target.scope === 'face') return sameFace(selected.face_ref, target.face_ref);
  if (target.scope === 'all_people') return true;
  if (target.scope === 'group') return view.groups[target.target_id!].face_ids.includes(selected.face_ref.face_instance_id);
  return target.scope === 'person' && confirmedMember(view, target.target_id, selected.face_ref.face_instance_id);
}

export type SkinEvennessFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function skinEvennessAccess(view: PeopleView | null | undefined,
  capability: SkinEvennessCapability | null | undefined, fences: SkinEvennessFences) {
  const reading = skinEvennessReading(view), core = skinEvennessReadiness(capability), targetReady = skinEvennessTargetReady(view);
  const selectionMatches = skinEvennessSelectionMatches(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const editValue = !targetReady || !selectionMatches ? null : reading.overridePresent ? reading.override
    : view?.editing_target?.scope === 'face' ? reading.value : null;
  const changeDisabled = resetDisabled || !selectionMatches || !measuredFace || reading.value === null || !core.available;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !targetReady ? '请在人物栏选择当前照片的有效编辑范围。'
    : !selectionMatches ? '所选人脸不属于当前编辑目标或已确认关联，请重新选择人物或范围。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, editValue, resetDisabled, changeDisabled, reason};
}

/** Source, owner, membership and authoritative state changes discard drafts and late callbacks. */
export function skinEvennessBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    skinEvennessTargetReady(view), view.selected_face_id, view.faces, view.groups, view.persons, view.links,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[SKIN_EVENNESS_OPERATION], view.resolved?.conflicts,
    view.editing_overrides[SKIN_EVENNESS_OPERATION], view.refusals]);
}
export function skinEvennessPatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('脸部色度均匀强度必须是 0 到 1 的有限数值。');
  return {operation_id: SKIN_EVENNESS_OPERATION, parameter_path: '/amount', unset: false, value};
}
/** Exactly this operation and target, not inheritance restore or any old-smoothing change. */
export function skinEvennessResetPatches(): ParameterPatch[] {return [skinEvennessPatch(0)];}
export function parseSkinEvennessChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
