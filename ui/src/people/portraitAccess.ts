// SPDX-License-Identifier: GPL-3.0-or-later
import type {DocState, EngineStatus} from '../native';
import {faceStateOf} from '../native';
import {browInteraction} from '../browShape/interaction';
import {noseInteraction} from '../noseShape/interaction';
import {eyeInteraction} from '../eyeShape/interaction';
import {mouthInteraction} from '../mouthShape/interaction';

/** Cursor eligibility is separate from the set of enabled faces the engine renders. */
export function portraitAccess(status: EngineStatus | null, doc: DocState | null, geometryWarning: boolean) {
  if (!status?.image) return {ok: false, why: '打开照片后即可使用。'};
  const people = doc?.people;
  if (people) {
    const selected = people.faces.find(face => face.face_ref.face_instance_id === people.selected_face_id);
    if (!selected) return {ok: false, why: '请选择一个人物作为编辑预览光标；其他已启用人物效果会保留。'};
    if (!selected.enabled) return {ok: false, why: '所选人脸已禁用，可在人物栏重新启用。选择禁用的人脸不会删除其历史。'};
    if (selected.analysis_status !== 'verified') return {ok: false, why: '所选区域没有已验证关键点，请在人物栏分析该区域；不会用占位点应用效果。'};
    return {ok: true, why: ''};
  }
  const face = faceStateOf(status, doc), analysis = status.precompute;
  const count = face?.num_faces ?? analysis?.num_faces ?? 0;
  const ok = !!analysis && analysis.backend === 'mediapipe' && analysis.num_landmarks === 478
    && !geometryWarning && (face?.enabled?.length ?? count) >= 1
    && (count === 1 || (!!face?.explicit && !face.blocked)) && !!face?.box;
  return {ok, why: ok ? '' : '请使用配套人物引擎并选择一个已完成真实分析的人脸。'};
}
export function portraitRequestsBusy(): boolean {
  return [browInteraction, noseInteraction, eyeInteraction, mouthInteraction].some(owner => owner.busy());
}
