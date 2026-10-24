// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Independent existing-detail controls, never aliases of legacy smoothing or whole-image sharpening. */
export const SKIN_TEXTURE_OPERATION = 'lnx.skin_texture.v1';
export const SKIN_TEXTURE_KEYS = ['texture', 'clarity'] as const;
export type SkinTextureKey = typeof SKIN_TEXTURE_KEYS[number];
export type SkinTextureRecipe = {version: 1; texture: number; clarity: number};
export const SKIN_TEXTURE_CONTROL_IDS = {
  texture: 'LNX-REF-PC-32465-C-1c80d411ce',
  clarity: 'LNX-REF-PC-32465-C-46e0c819b6',
} as const;
export const SKIN_TEXTURE_CONTROL_PATHS = {texture: '皮肤质感/纹理度', clarity: '皮肤质感/清晰度'} as const;
export const SKIN_TEXTURE_LABELS = {texture: '纹理度（面部已有细节）', clarity: '清晰度（面部皮肤锐化）'} as const;
export const SKIN_TEXTURE_SOURCE = 'https://www.pixcakeai.com/guide/32465';
export type SkinTextureCapability = {skin_texture_available?: boolean; skin_texture_reason?: string | null};
export const neutralSkinTexture = (): SkinTextureRecipe => ({version: 1, texture: 0, clarity: 0});

const revision = (value: number) => Number.isSafeInteger(value) && value >= 0;
const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const validValue = (key: SkinTextureKey, value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= (key === 'texture' ? -1 : 0) && value <= 1;

export function skinTextureReadiness(capability?: SkinTextureCapability | null): {available: boolean; reason?: string} {
  return capability?.skin_texture_available === true ? {available: true} : {available: false,
    reason: capability?.skin_texture_reason || '面部纹理度与清晰度核心尚不可用，请使用包含该核心的完整版本。'};
}

/** Only matching engine readback describes the selected face; a shared write target does not. */
export function skinTextureReading(view: PeopleView | null | undefined, key: SkinTextureKey): {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
} {
  const path = `/${key}`, explicit = view?.editing_overrides[SKIN_TEXTURE_OPERATION]?.[path];
  const override = validValue(key, explicit) ? explicit : null, overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent,
    reason: '请选择人物，查看此脸实际生效的纹理度与清晰度参数。'};
  const resolved = view.resolved;
  if (!resolved || !sameFace(resolved.face_ref, selected.face_ref)
    || !selected.face_ref.face_instance_id || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || !revision(selected.face_ref.analysis_revision) || !revision(view.binding.document_revision)
    || !revision(view.revision) || !revision(view.association_revision)
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === SKIN_TEXTURE_OPERATION && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: '此项存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[SKIN_TEXTURE_OPERATION]?.[path];
  if (!source || !validValue(key, source.value)) return {value: null, override, overridePresent,
    reason: '引擎尚未提供此脸的有效纹理度与清晰度参数；不会用中性占位值冒充实际读数。'};
  return {value: source.value, source, override, overridePresent};
}

/** Neutral recovery preserves source/owner fences, without requiring available core or usable anatomy. */
export function skinTextureTargetReady(view: PeopleView | null | undefined): boolean {
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
export type SkinTextureFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean; faceOk: boolean; faceWhy?: string;
};
export function skinTextureAccess(view: PeopleView | null | undefined, key: SkinTextureKey,
  capability: SkinTextureCapability | null | undefined, fences: SkinTextureFences) {
  const reading = skinTextureReading(view, key), core = skinTextureReadiness(capability);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !skinTextureTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const changeDisabled = resetDisabled || !measuredFace || reading.value === null || !core.available;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !skinTextureTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, resetDisabled, changeDisabled, reason};
}

/** Changes of source, face, target or authoritative readback discard drafts rather than retarget them. */
export function skinTextureBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  const selected = view.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    view.selected_face_id, selected?.face_ref, selected?.enabled, selected?.analysis_status,
    view.resolved?.face_ref, view.resolved?.state_revision, view.resolved?.association_revision,
    view.resolved?.operations[SKIN_TEXTURE_OPERATION],
    view.resolved?.conflicts.filter(conflict => conflict.operation_id === SKIN_TEXTURE_OPERATION),
    view.editing_overrides[SKIN_TEXTURE_OPERATION]]);
}
export function skinTexturePatch(key: SkinTextureKey, value: number): ParameterPatch {
  if (!SKIN_TEXTURE_KEYS.includes(key) || !validValue(key, value)) {
    throw Error('纹理度必须是 -1 到 1、清晰度必须是 0 到 1 的有限数值。');
  }
  return {operation_id: SKIN_TEXTURE_OPERATION, parameter_path: `/${key}`, unset: false, value};
}

/** One owner call submits both neutral leaves atomically, never two independent requests. */
export function skinTextureResetPatches(): ParameterPatch[] {
  return SKIN_TEXTURE_KEYS.map(key => skinTexturePatch(key, 0));
}
