// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Measured dark narrow-furrow attenuation, not lip colour, material or broad smoothing. */
export const LIP_TEXTURE_OPERATION = 'lnx.lip_texture.v1';
export const LIP_TEXTURE_CONTROL_ID = 'LNX-REF-PC-32464-C-b6315c40ca';
export const LIP_TEXTURE_CONTROL_PATH = '面部祛瑕疵/唇纹修整';
export const LIP_TEXTURE_SOURCE = 'https://www.pixcakeai.com/guide/32464';
export type LipTextureRecipe = {version: 1; amount: number};
export type LipTextureCapability = {lip_texture_available?: boolean; lip_texture_reason?: string | null};
export const neutralLipTexture = (): LipTextureRecipe => ({version: 1, amount: 0});

const validAmount = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= 0 && value <= 1;
const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const owns = (values: object, id: string | null) => !!id && Object.prototype.hasOwnProperty.call(values, id);

export function checkLipTexture(value: unknown): LipTextureRecipe {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('唇纹修整配方无效。');
  const recipe = value as Record<string, unknown>;
  if (Object.keys(recipe).sort().join(',') !== 'amount,version' || recipe.version !== 1 || !validAmount(recipe.amount)) {
    throw Error('唇纹修整必须使用版本 1 与 0 到 1 的有限强度。');
  }
  return {version: 1, amount: recipe.amount};
}

export function lipTextureReadiness(capability?: LipTextureCapability | null): {available: boolean; reason?: string} {
  return capability?.lip_texture_available === true ? {available: true} : {available: false,
    reason: capability?.lip_texture_reason || '唇部窄暗纹淡化核心尚不可用，请使用包含该核心的完整版本。'};
}

export type LipTextureReading = {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
};
/** The selected face's effective amount is not the shared target's explicit intent. */
export function lipTextureReading(view: PeopleView | null | undefined): LipTextureReading {
  const path = '/amount', explicit = view?.editing_overrides[LIP_TEXTURE_OPERATION]?.[path];
  const override = validAmount(explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的唇纹修整强度。'};
  const resolved = view.resolved;
  if (!resolved || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256
    || !sameFace(resolved.face_ref, selected.face_ref) || !selected.face_ref.face_instance_id
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)
    || !revision(view.binding.document_revision) || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸、来源或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === LIP_TEXTURE_OPERATION)) {
    return {value: null, override, overridePresent, reason: '唇纹修整存在分组优先级冲突，请在人物栏确认范围并解决冲突。'};
  }
  const source = resolved.operations[LIP_TEXTURE_OPERATION]?.[path];
  if (!source || !validAmount(source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效唇纹修整读数；不会用中性占位值冒充实际强度。'};
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery requires current ownership, not available core, selected face or anatomy. */
export function lipTextureTargetReady(view: PeopleView | null | undefined): boolean {
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

/** A preview outside the target group or confirmed person cannot authorize an active edit. */
export function lipTextureSelectionMatches(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target, selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !target || !selected || !lipTextureTargetReady(view)) return false;
  if (selected.face_ref.asset_sha256 !== view.binding.asset_sha256 || !revision(selected.face_ref.analysis_revision)) return false;
  if (target.scope === 'face') return sameFace(selected.face_ref, target.face_ref);
  if (target.scope === 'all_people') return true;
  if (target.scope === 'group') return view.groups[target.target_id!].face_ids.includes(selected.face_ref.face_instance_id);
  if (target.scope !== 'person') return false;
  return view.links.some(link => link.person_id === target.target_id && link.face_instance_id === selected.face_ref.face_instance_id
    && link.state === 'confirmed' && link.confirmation_revision !== null && revision(link.confirmation_revision)
    && link.confirmation_revision <= view.association_revision);
}

export type LipTextureFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function lipTextureAccess(view: PeopleView | null | undefined,
  capability: LipTextureCapability | null | undefined, fences: LipTextureFences) {
  const reading = lipTextureReading(view), core = lipTextureReadiness(capability), targetReady = lipTextureTargetReady(view);
  const selectionMatches = lipTextureSelectionMatches(view);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain || fences.externalBusy || !targetReady;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  // No shared slider is prefilled from one preview face's inherited parameter.
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

/** Source, ownership, membership and authoritative state changes discard drafts and late callbacks. */
export function lipTextureBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    lipTextureTargetReady(view), view.selected_face_id, view.faces, view.groups, view.persons, view.links,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[LIP_TEXTURE_OPERATION], view.resolved?.conflicts,
    view.editing_overrides[LIP_TEXTURE_OPERATION], view.refusals]);
}
export function lipTexturePatch(value: number): ParameterPatch {
  if (!validAmount(value)) throw Error('唇纹修整强度必须是 0 到 1 的有限数值。');
  return {operation_id: LIP_TEXTURE_OPERATION, parameter_path: '/amount', unset: false, value};
}
/** Only this operation and this target: no inherited restore, makeup reset or support clearing. */
export function lipTextureResetPatches(): ParameterPatch[] {return [lipTexturePatch(0)];}
export function parseLipTextureChoice(text: string): number | null {
  const trimmed = text.trim();
  if (!/^[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const value = Number(trimmed) / 100;
  return validAmount(value) ? value : null;
}
