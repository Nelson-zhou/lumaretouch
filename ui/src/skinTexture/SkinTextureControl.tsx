// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, type ComponentType} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SKIN_TEXTURE_CONTROL_IDS, SKIN_TEXTURE_LABELS, skinTextureAccess, skinTextureBindingKey,
  skinTexturePatch, skinTextureResetPatches, type SkinTextureCapability, type SkinTextureKey} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};

/** Existing people transactions retain mutation, receipt, history and replay ownership. */
export function SkinTextureControl({control, people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  control: SkinTextureKey; people: PeopleOwner; capability?: SkinTextureCapability | null;
  blocked: boolean; faceOk: boolean; faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = skinTextureBindingKey(view);
  const access = skinTextureAccess(view, control, capability, {enabled: people.enabled,
    pending: people.state.pending, uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, control, access}); current.current = {binding, control, access};
  const mounted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const {reading} = access, label = SKIN_TEXTURE_LABELS[control];
  const stillCurrent = () => mounted.current && current.current.binding === binding && current.current.control === control;
  function commit(value: number) {
    if (!stillCurrent()
      || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {people.patch([skinTexturePatch(control, value)]);} catch (error) {note(String(error));}
  }
  function resetBoth() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    try {people.patch(skinTextureResetPatches());} catch (error) {note(String(error));}
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const refusals = view?.refusals?.filter(refusal => refusal.face_instance_id === view.selected_face_id) ?? [];
  return <section data-control-id={SKIN_TEXTURE_CONTROL_IDS[control]} aria-label={label}>
    <p>{control === 'texture'
      ? '纹理度仅调整当前有效来源图像（原图或已返回合成图）的已有面部皮肤细节：向左减少纹理，向右增加纹理，0 不改变纹理。它独立于质感磨皮的细节保留，不把旧磨皮参数改名当成新功能。'
      : '清晰度仅对当前有效来源图像（原图或已返回合成图）的已有面部皮肤细节进行局部锐化；0 不锐化，向右增强。它不是全图粗尺度对比度，也不替代全图锐化。'}</p>
    <p className="muted">当前实现仅作用于已测得的面部皮肤，不扩展到身体，也不沿用其他皮肤功能的身体范围。官方说明没有明确保证纹理度的身体覆盖，本实现不作该保证。不是 AI 修复，不生成或恢复来源中不存在的皮肤细节。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方显示所选人脸的实际有效值，不代表所有人物或共享默认值。</p>}
    {reading.value !== null && <>
      <div className="prow" aria-hidden="true">{control === 'texture'
        ? <><span>减少已有纹理</span><span>0 无效果</span><span>增加已有纹理</span></>
        : <><span>0 不锐化</span><span>增强皮肤细节锐化</span></>}</div>
      <Slider key={`${binding}:${control}`} label={label} value={Math.round(reading.value * 100)}
        min={control === 'texture' ? -100 : 0} max={100} disabled={access.changeDisabled}
        title={access.reason ?? (control === 'texture' ? '负值减少已有纹理，正值增加已有纹理；0 为中性。' : '仅锐化已有面部皮肤细节；0 为中性。')}
        onChange={value => commit(value / 100)} onReset={() => commit(0)}/>
      {reading.source && <p className="muted">有效值来源：{sourceLabel(reading.source)}。</p>}
    </>}
    {view && <p className="muted">此编辑范围的本项设置：{reading.override === null
      ? reading.overridePresent ? '显式值无效，请刷新或归零' : '未设显式值，保留继承'
      : `${Math.round(reading.override * 100)}`}。归零写入此范围的中性覆盖，不恢复继承，也不清除其他范围或其他参数。</p>}
    <button type="button" className="specBtn" disabled={access.resetDisabled}
      title={`只将当前编辑范围的${label}设为 0；缺少核心或有效面部分析时仍可归零，保留其他参数和范围。`}
      onClick={() => commit(0)}>归零当前范围的{label}</button>
    <button type="button" className="specBtn" disabled={access.resetDisabled}
      title="同一人物请求将本范围的纹理度与清晰度同时设为 0；不会触碰磨皮、光泽度、肤色或其他人物覆盖。"
      onClick={resetBoth}>同时归零当前范围的纹理度与清晰度</button>
    {!access.core.available && <p className="muted">若本范围另一项仍非零，可使用同时归零；若其他范围仍保留非中性参数，引擎可能继续拒绝，不会替你清除它们。</p>}
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {refusals.map((refusal, index) => <p key={`${refusal.reason}:${index}`} role="status">{refusal.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要当前来源的真实面部皮肤语义分割及 478 点人脸分析；核心就绪不等于此脸可用。两项都是对已有细节的调整，非零数值不保证可见变化，也不证明噪声、边缘或彩色光照下的照片效果合格。当前仅支持 RGB SDR，不宣称 HDR 支持。</p>
    <p className="muted">纹理度显示 -100 至 100 对应内部 -1 至 1；清晰度显示 0 至 100 对应内部 0 至 1。这是本产品量程，不是手册规定。噪声、边缘与彩色光照的真实照片验收尚未运行，皮肤功能族仍未完整验收。</p>
  </section>;
}
