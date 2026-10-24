// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, type ComponentType} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SKIN_GLOSS_CONTROL_ID, skinGlossAccess, skinGlossBindingKey, skinGlossPatch,
  type SkinGlossCapability} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};

/** Existing people transactions remain the only mutation, receipt, undo and replay owner. */
export function SkinGlossControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: SkinGlossCapability | null; blocked: boolean;
  faceOk: boolean; faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = skinGlossBindingKey(view);
  const access = skinGlossAccess(view, capability, {enabled: people.enabled,
    pending: people.state.pending, uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access}); current.current = {binding, access};
  const mounted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const {reading} = access;
  function commit(value: number) {
    if (!mounted.current || current.current.binding !== binding
      || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {people.patch([skinGlossPatch(value)]);} catch (error) {note(String(error));}
  }
  const refusals = view?.refusals?.filter(refusal => refusal.face_instance_id === view.selected_face_id) ?? [];
  return <section data-control-id={SKIN_GLOSS_CONTROL_ID} aria-label="光泽度（面部已有高光）">
    <p>仅在当前有效来源图像（原图或已返回合成图）的真实面部皮肤范围内，保守估计并抑制或增强已有高光。不会绘制新高光，不是全图曝光、肤色色温色调、美白红润或磨皮的替代。</p>
    <p className="muted">仅作用于面部皮肤，不扩展到身体，也不沿用其他皮肤功能的身体范围。缺少可观察到的原有高光时，调整可能没有可见效果；非零数值不保证像素发生变化。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方显示所选人脸的实际有效值，不代表所有人物或共享默认值。</p>}
    {reading.value !== null && <>
      <div className="prow" aria-hidden="true"><span>抑制已有高光</span><span>0 无效果</span><span>增强已有高光</span></div>
      <Slider key={binding} label="光泽度（面部已有高光）" value={Math.round(reading.value * 100)} min={-100} max={100}
        disabled={access.changeDisabled} title={access.reason ?? '负值抑制已有高光，正值增强已有高光；0 不改变画面。'}
        onChange={value => commit(value / 100)} onReset={() => commit(0)}/>
      {reading.source && <p className="muted">有效值来源：{sourceLabel(reading.source)}。</p>}
    </>}
    {view && <p className="muted">此编辑范围的光泽度设置：{reading.override === null
      ? reading.overridePresent ? '显式值无效，请刷新或归零' : '未设显式值，保留继承'
      : `${Math.round(reading.override * 100)}`}。归零写入此范围的中性覆盖，不恢复继承，也不清除其他范围或其他参数。</p>}
    <button type="button" className="specBtn" disabled={access.resetDisabled}
      title="只将当前编辑范围的光泽度设为 0；缺少核心或有效面部分析时仍可归零，不清除其他范围的覆盖。"
      onClick={() => commit(0)}>归零当前范围的光泽度</button>
    {!access.core.available && <p className="muted">若其他范围仍保留非中性光泽度，引擎可能继续拒绝；不会替你清除它们。</p>}
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {refusals.map((refusal, index) => <p key={`${refusal.reason}:${index}`} role="status">{refusal.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn"
      onClick={() => void people.check().catch(error => note(String(error)))}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要当前来源的真实面部皮肤语义分割及 478 点人脸分析；核心就绪不等于此脸可用。已有高光估计不是精确镜面反射分割，不保证完美去油或恢复过曝细节。当前仅支持 RGB SDR，不宣称 HDR 支持。显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定。真实照片效果验收尚未运行，皮肤功能族仍未完整验收。</p>
  </section>;
}
