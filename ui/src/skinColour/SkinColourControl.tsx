// SPDX-License-Identifier: GPL-3.0-or-later
import {useRef, type ComponentType} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SKIN_COLOUR_CONTROL_IDS, SKIN_COLOUR_KEYS, SKIN_COLOUR_LABELS, skinColourAccess, skinColourBindingKey,
  skinColourPatch, type SkinColourCapability, type SkinColourKey} from './model';

type SliderProps = {
  label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void;
};

/** Stateless operation UI; the existing people owner owns edits, receipts and history. */
export function SkinColourControl({control, people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  control: SkinColourKey; people: PeopleOwner; capability?: SkinColourCapability | null;
  blocked: boolean; faceOk: boolean; faceWhy?: string; note: (message: string) => void;
  Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = skinColourBindingKey(view);
  const access = skinColourAccess(view, control, capability, {enabled: people.enabled,
    pending: people.state.pending, uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access}); current.current = {binding, access};
  const {reading} = access, label = SKIN_COLOUR_LABELS[control];
  const ends = control === 'temperature' ? ['冷', '暖'] : ['绿', '洋红'];
  const commit = (value: number) => {
    // A stale input may not retarget an edit after selection/revision changes.
    if (current.current.binding !== binding
      || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {people.patch([skinColourPatch(control, value)]);} catch (error) {note(String(error));}
  };
  const resetBoth = () => {
    if (current.current.binding !== binding || current.current.access.resetDisabled) return;
    try {people.patch(SKIN_COLOUR_KEYS.map(key => skinColourPatch(key, 0)));} catch (error) {note(String(error));}
  };
  const refusals = view?.refusals?.filter(refusal => refusal.face_instance_id === view.selected_face_id) ?? [];
  return <section data-control-id={SKIN_COLOUR_CONTROL_IDS[control]} aria-label={label}>
    <p className="muted">仅调整已测得的面部皮肤，不覆盖全身皮肤。手动调色，不是 AI 美白或肤色统一；皮肤功能族仍为部分实现。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方显示所选人脸的实际有效值，不代表所有人物或共享默认值。</p>}
    {reading.value !== null && <>
      <div className="prow" aria-hidden="true"><span>{ends[0]}</span><span>0 中性</span><span>{ends[1]}</span></div>
      <Slider key={`${binding}:${control}`} label={label} value={Math.round(reading.value * 100)} min={-100} max={100}
        disabled={access.changeDisabled}
        title={access.reason ?? `${ends[0]} ← 0 → ${ends[1]}；只调整已测得的面部皮肤，数值不是开尔文温度。`}
        onChange={value => commit(value / 100)} onReset={() => commit(0)}/>
      {reading.source && <p className="muted">有效值来源：{sourceLabel(reading.source)}。</p>}
    </>}
    {view && <p className="muted">此编辑范围的本项设置：{reading.override === null
      ? reading.overridePresent ? '显式值无效，请刷新或归零' : '未设显式值，保留继承'
      : `${Math.round(reading.override * 100)}`}。归零写入此范围的中性覆盖，不会清除其他参数或恢复继承。</p>}
    <button type="button" className="specBtn" disabled={access.resetDisabled}
      title={`只将当前编辑范围的${label}设为 0；核心不可用时仍可提交归零，已有逐脸覆盖不会被清除。`}
      onClick={() => commit(0)}>归零当前范围的{label}</button>
    {!access.core.available && <><button type="button" className="specBtn" disabled={access.resetDisabled}
      title="同一请求将此范围的色温、色调同时设为 0，避免另一项仍非中性而依赖缺失的核心。其他人物范围的覆盖保留。"
      onClick={resetBoth}>同时归零当前范围的色温与色调</button>
      <p className="muted">若其他范围仍保留非中性肤色参数，引擎可能继续拒绝；不会替你清除它们。</p></>}
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {refusals.map((refusal, index) => <p key={`${refusal.reason}:${index}`} role="status">{refusal.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn"
      onClick={() => void people.check().catch(error => note(String(error)))}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要当前有效来源图像的真实面部皮肤语义分割及 478 点人脸分析；仅核心就绪不等于此脸可用。缺少证据会拒绝调整，不用全图肤色键替代。遮挡与分割边缘可能不准确，请对比预览。显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定。</p>
  </section>;
}
