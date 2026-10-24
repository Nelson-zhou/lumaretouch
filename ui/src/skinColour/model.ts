// SPDX-License-Identifier: GPL-3.0-or-later
import type {FaceRef, ParameterPatch, PeopleView, ResolvedParameter} from '../people/model';

/** Two handbook leaves only. The signed unit range is a local product policy. */
export const SKIN_COLOUR_OPERATION = 'lnx.skin_colour.v1';
export const SKIN_COLOUR_KEYS = ['temperature', 'tint'] as const;
export type SkinColourKey = typeof SKIN_COLOUR_KEYS[number];
export const SKIN_COLOUR_CONTROL_IDS = {
  temperature: 'LNX-REF-PC-32465-C-f0ba809461',
  tint: 'LNX-REF-PC-32465-C-0146f740bd',
} as const;
export const SKIN_COLOUR_LABELS = {temperature: '肤色色温', tint: '肤色色调'} as const;
export type SkinColourCapability = {
  skin_colour_available?: boolean;
  skin_colour_reason?: string | null;
};

export function skinColourReadiness(capability?: SkinColourCapability | null): {available: boolean; reason?: string} {
  if (capability?.skin_colour_available === true) return {available: true};
  return {available: false, reason: capability?.skin_colour_reason
    || '面部肤色调整核心尚不可用，请使用包含该核心的完整版本。'};
}

const sameFace = (a?: FaceRef | null, b?: FaceRef | null) => !!a && !!b
  && a.asset_sha256 === b.asset_sha256 && a.face_instance_id === b.face_instance_id
  && a.analysis_revision === b.analysis_revision;
const signedValue = (value: unknown): value is number => typeof value === 'number'
  && Number.isFinite(value) && value >= -1 && value <= 1;

/** Resolved preview and current target override are different facts, never aliases. */
export function skinColourReading(view: PeopleView | null | undefined, key: SkinColourKey): {
  value: number | null; source?: ResolvedParameter; override: number | null; overridePresent: boolean; reason?: string;
} {
  const path = `/${key}`, explicit = view?.editing_overrides[SKIN_COLOUR_OPERATION]?.[path];
  const override = signedValue(explicit) ? explicit : null;
  const overridePresent = explicit !== undefined;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  if (!view || !selected) return {value: null, override, overridePresent, reason: '请选择人物，查看此脸实际生效的肤色参数。'};
  const resolved = view.resolved;
  if (!resolved || !sameFace(resolved.face_ref, selected.face_ref)
    || selected.face_ref.asset_sha256 !== view.binding.asset_sha256
    || resolved.state_revision !== view.revision || resolved.association_revision !== view.association_revision) {
    return {value: null, override, overridePresent, reason: '人脸或参数状态已变化，正在等待当前照片的权威读数。'};
  }
  if (resolved.conflicts.some(conflict => conflict.operation_id === SKIN_COLOUR_OPERATION && conflict.parameter_path === path)) {
    return {value: null, override, overridePresent, reason: '此项存在分组优先级冲突，请在人物栏确认编辑范围并解决冲突。'};
  }
  const source = resolved.operations[SKIN_COLOUR_OPERATION]?.[path];
  if (!source || !signedValue(source.value)) {
    return {value: null, override, overridePresent, reason: '引擎尚未提供此脸的有效肤色参数；不会用中性占位值冒充实际读数。'};
  }
  return {value: source.value, source, override, overridePresent};
}

/** Zero recovery still needs an extant, source-owned target, even without analysis. */
export function skinColourTargetReady(view: PeopleView | null | undefined): boolean {
  const target = view?.editing_target;
  if (!view || !target || !view.binding.document_id || !view.binding.document_epoch || !view.binding.asset_sha256) return false;
  if (target.scope === 'all_people') return target.face_ref === null && target.target_id === view.binding.asset_sha256;
  if (target.scope === 'group') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.groups, target.target_id ?? '');
  if (target.scope === 'person') return target.face_ref === null && Object.prototype.hasOwnProperty.call(view.persons, target.target_id ?? '');
  if (target.scope !== 'face') return false;
  const face = view.faces.find(item => item.face_ref.face_instance_id === target.target_id);
  return !!face && face.face_ref.asset_sha256 === view.binding.asset_sha256 && sameFace(face.face_ref, target.face_ref);
}

export type SkinColourFences = {
  enabled: boolean; pending: boolean; uncertain: boolean; externalBusy: boolean;
  faceOk: boolean; faceWhy?: string;
};
export function skinColourAccess(view: PeopleView | null | undefined, key: SkinColourKey,
  capability: SkinColourCapability | null | undefined, fences: SkinColourFences) {
  const reading = skinColourReading(view, key), core = skinColourReadiness(capability);
  const resetDisabled = !fences.enabled || fences.pending || fences.uncertain
    || fences.externalBusy || !skinColourTargetReady(view);
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const measuredFace = !!selected?.enabled && selected.analysis_status === 'verified' && fences.faceOk;
  const changeDisabled = resetDisabled || !measuredFace || reading.value === null || !core.available;
  const reason = fences.uncertain ? '上一项人物修改结果尚未确认，请查询原请求，不要重发。'
    : fences.pending || fences.externalBusy ? '其他修改尚在处理，请等待确认后继续。'
    : !fences.enabled ? '当前人物编辑尚不可用，请等待照片与引擎状态就绪。'
    : !skinColourTargetReady(view) ? '请在人物栏选择当前照片的有效编辑范围。'
    : reading.reason ?? (!measuredFace ? fences.faceWhy || '所选人脸尚未启用或未完成真实分析。' : core.reason);
  return {reading, core, resetDisabled, changeDisabled, reason};
}

/** Remount only the input draft when its authoritative binding changes. */
export function skinColourBindingKey(view: PeopleView | null | undefined): string {
  if (!view) return 'unavailable';
  return JSON.stringify([view.binding, view.revision, view.association_revision, view.editing_target,
    view.selected_face_id, view.resolved?.face_ref]);
}

export function skinColourPatch(key: SkinColourKey, value: number): ParameterPatch {
  if (!SKIN_COLOUR_KEYS.includes(key) || !signedValue(value)) throw Error('肤色参数必须是 -1 到 1 的有限数值。');
  return {operation_id: SKIN_COLOUR_OPERATION, parameter_path: `/${key}`, unset: false, value};
}
