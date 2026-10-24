// SPDX-License-Identifier: GPL-3.0-or-later
/** Read-only engine DTO. UI owns drafts and pending requests, never a people graph. */
export type FaceRef = { asset_sha256: string; face_instance_id: string; analysis_revision: number }
export type LinkState = 'candidate' | 'confirmed' | 'rejected' | 'unresolved'
export type PeopleScope = 'all_people' | 'group' | 'person' | 'face'
export type ParameterSource = PeopleScope | 'default'
export type ParameterValue = number | boolean | string
export type ResolvedParameter = {
  value: ParameterValue; scope: ParameterSource; target_id: string | null;
  contributing_targets?: (string | null)[]; overridden: boolean;
}
export type ResolvedFace = {
  face_ref: FaceRef; state_revision: number; association_revision: number;
  operations: Record<string, Record<string, ResolvedParameter>>;
  conflicts: { operation_id: string; parameter_path: string; reason: string; target_ids: string[] }[];
}
export type PeopleTarget = { scope: PeopleScope; target_id: string | null; face_ref: FaceRef | null }
export type PeopleBinding = {
  document_id: string; document_epoch: string; document_revision: number; asset_sha256: string;
}
export type PeopleEnvelope = {
  document_id: string; document_epoch: string; document_revision: number;
  state_revision: number; association_revision: number; request_id: string; target: PeopleTarget;
}
export type PeopleContext = Omit<PeopleEnvelope, 'request_id'>;
export function peopleContext(view: PeopleView | null | undefined): PeopleContext | undefined {
  if (!view?.editing_target) return undefined;
  const {document_id, document_epoch, document_revision} = view.binding;
  return {document_id, document_epoch, document_revision, state_revision: view.revision,
    association_revision: view.association_revision, target: view.editing_target};
}
/** Manual region capture is always pinned to the current photograph, even with no selected face. */
export function peopleAssetContext(view: PeopleView | null | undefined): PeopleContext | undefined {
  if (!view) return undefined;
  return peopleContext({...view, editing_target: {scope: 'all_people', target_id: view.binding.asset_sha256, face_ref: null}});
}
export type ParameterPatch = {
  operation_id: string; parameter_path: string;
} & ({ unset: true } | { unset: false; value: ParameterValue })
export type FaceChoice = {
  face_ref: FaceRef; enabled: boolean; box: [number, number, number, number];
  labels?: Record<string, string | number | boolean>;
  manual: boolean; analysis_status: 'verified' | 'unresolved' | 'synthetic';
}
export type PeopleView = {
  binding: PeopleBinding; revision: number; association_revision: number;
  faces: FaceChoice[];
  groups: Record<string, {label: string; priority: number; face_ids: string[]}>;
  persons: Record<string, {anonymous: true}>;
  links: {face_instance_id: string; person_id: string; state: LinkState; confirmation_revision: number | null}[];
  selected_face_id: string | null; resolved: ResolvedFace | null;
  editing_target: PeopleTarget | null;
  editing_overrides: Record<string, Record<string, ParameterValue>>;
  legacy_unresolved?: {id: string; legacy_key: string; intent: unknown; bindable: boolean}[];
  eyeliner?: import('../eyeliner/model').EyelinerView | null;
  iris_makeup?: import('../irisMakeup/model').IrisView | null;
  eyelash?: import('../eyelash/model').EyelashView | null;
  brow_makeup?: import('../browMakeup/model').BrowMakeupView | null;
  lipstick?: import('../lipstick/model').LipstickView | null;
  blush_makeup?: import('../blushMakeup/model').BlushView | null;
  eye_light?: import('../eyeLight/model').EyeLightView | null;
  skin_body?: import('../skinColour/bodyReviewModel').SkinBodyReport | null;
  skin_finish_body?: import('../skinColour/bodyReviewModel').SkinBodyReport | null;
  analysis_notice?: string; refusals?: {face_instance_id: string; reason: string}[];
}
export type PeopleAction = PeopleEnvelope & {
  action: 'patch' | 'link' | 'group' | 'face_status' | 'manual_add' | 'create_person' | 'select' | 'target' | 'analyse_face' | 'resolve_legacy' | 'eye_light_reference' | 'eye_light_review' | 'blush_palette' | 'blush_reference' | 'blush_review' | 'lipstick_palette' | 'lipstick_reference' | 'lipstick_review' | 'eyeliner_palette' | 'eyeliner_reference' | 'eyeliner_review' | 'iris_reference' | 'iris_review' | 'eyelash_palette' | 'eyelash_reference' | 'eyelash_review' | 'brow_makeup_palette' | 'brow_makeup_reference' | 'brow_makeup_review' | 'skin_body_reference' | 'skin_body_preview' | 'skin_body_confirm' | 'skin_body_detach' | 'skin_finish_body_reference' | 'skin_finish_body_preview' | 'skin_finish_body_confirm' | 'skin_finish_body_detach';
  payload: Record<string, unknown>;
}
export type PeopleResult = {
  protocol: 1; request_id: string; action: PeopleAction['action']; document_id: string;
  success: boolean; outcome_unknown: boolean; error?: string;
  doc_state?: {people?: PeopleView};
  payload?: unknown; payload_released?: boolean;
}
export type PeopleMailbox = {phase: 'pending' | 'done' | 'unavailable'; request_id: string; result?: PeopleResult; error?: string}
export const PEOPLE_CONTROL_IDS = {
  labels: 'PC-47211-C-dacc840b92', single: 'PC-47211-C-7077d6f614',
  all: 'PC-47211-C-06d9ae036b', linkedGroups: 'PC-47211-C-d381bdebf7',
  editableLabels: 'PC-47211-C-84338ba2d8', detectionCorrection: 'PC-47211-C-cb1b252660',
  addDisableFace: 'PC-47211-C-5180dee1ad',
} as const

/** Analysis refusal disables effects, not selecting a face to correct. */
export function canSelectFace(face: FaceChoice, documentBusy: boolean): boolean {
  return !documentBusy && Boolean(face.face_ref.face_instance_id)
}
export function restoreInheritance(operation_id: string, parameter_path: string): ParameterPatch {
  return {operation_id, parameter_path, unset: true}
}
export function sourceLabel(value: ResolvedParameter): string {
  return ({default: '中性默认', all_people: '本照片全部人物默认', group: '用户分组',
    person: '已确认人物关联', face: '此脸独立覆盖'} as const)[value.scope]
}
export function targetLabel(view: PeopleView): string {
  const target = view.editing_target;
  if (!target) return '尚未选择编辑范围';
  if (target.scope === 'all_people') return '本照片全部人物默认';
  if (target.scope === 'group') return `分组「${view.groups[target.target_id ?? '']?.label ?? '未找到'}」默认`;
  if (target.scope === 'person') return '所选匿名人物默认（仅已确认关联）';
  const index = view.faces.findIndex(face => face.face_ref.face_instance_id === target.target_id);
  return index >= 0 ? `人物 ${index + 1} 独立覆盖` : '所选人脸已不在当前照片';
}
export function operationLabel(id: string): string {
  return ({'lnx.deform.v1': '历史基础脸型（旧版瘦脸保留错误拓扑）', 'lnx.enhance.v1': '眼牙与面部增强',
    'lnx.skin_colour.v1': '面部肤色色温与色调',
    'lnx.skin_finish.v1': '肤色美白与皮肤红润（手动强度）',
    'lnx.skin_gloss.v1': '面部已有高光光泽度（抑制与增强）',
    'lnx.skin_texture.v1': '面部纹理度与皮肤清晰度（已有细节）',
    'lnx.face_contour.v1': '太阳穴、颧骨与下颌（可见二维轮廓）',
    'lnx.slim_face.v2': '新版瘦脸（真实可见轮廓，左右独立）',
    'lnx.face_size.v1': '小脸（局部整脸整体大小）',
    'lnx.lower_face.v1': '下庭（局部纵向长度）',
    'lnx.facial_wrinkles.v1': '面部细纹', 'lnx.lip_makeup.v1': '唇妆',
    'lnx.brow_shape.v1': '眉形', 'lnx.nose_shape.v1': '鼻形',
    'lnx.eye_shape.v1': '眼形', 'lnx.mouth_shape.v1': '嘴形',
    'lnx.hair_colour.v1': '发色与已有高光光泽', 'lnx.eye_light.v1': '眼神光素材', 'lnx.blush_makeup.v1': '腮红', 'lnx.lipstick.v1': '口红', 'lnx.eyeliner.v1': '眼线', 'lnx.iris_makeup.v1': '美瞳', 'lnx.eyelash.v1': '睫毛（上下/左右独立）', 'lnx.brow_makeup.v1': '眉妆'} as Record<string, string>)[id] ?? id;
}
export function bindingKey(binding: PeopleBinding): string {
  return `${binding.document_epoch}:${binding.document_id}:${binding.asset_sha256}`;
}
