// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {LIP_TEXTURE_CONTROL_ID, lipTextureAccess, lipTextureBindingKey, lipTexturePatch,
  lipTextureResetPatches, parseLipTextureChoice, type LipTextureCapability} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** A blank choice is not zero and never copies the selected face into a shared target. */
function AmountChoice({changeDisabled, resetDisabled, onChoose}: {
  changeDisabled: boolean; resetDisabled: boolean; onChoose: (value: number) => void;
}) {
  const [text, setText] = useState(''), choice = parseLipTextureChoice(text);
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>为当前范围明确选择唇纹修整强度</legend>
    <label>新强度（0 至 100）
      <input className="pnum" type="number" min={0} max={100} step="any" value={text}
        aria-label="唇纹修整新强度" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>应用我选择的强度</button>
    <p className="muted">留空不等于 0，也不借用所选人脸的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** Canonical people transactions remain the only command, receipt, history and replay owner. */
export function LipTextureControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: LipTextureCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check) {
    owner.current = {patch: people.patch, check: people.check, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([lipTextureBindingKey(view), owner.current.generation]);
  const access = lipTextureAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch, check: people.check});
  current.current = {binding, access, patch: people.patch, check: people.check};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Observe confirmed failures even when pending transitions batch into one owner snapshot.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding
    && current.current.patch === people.patch && current.current.check === people.check;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {dispatch([lipTexturePatch(value)]);} catch (error) {note(String(error));}
  }
  function reset() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(lipTextureResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={LIP_TEXTURE_CONTROL_ID} aria-label="唇纹修整（仅淡化已测得的窄暗纹）">
    <p>唇纹修整仅淡化当前有效来源图像（原图或已返回合成图）中已测得的唇部窄暗纹。0 无效果，向右增加淡化强度。</p>
    <p className="muted">官方说明涵盖明显唇纹、干皮死皮和小裂口；当前只实现窄暗纹淡化，不支持干皮修复或完整裂口重建，不代表官方完整效果。</p>
    <p className="muted">它不是唇妆饱和度、明度、立体度或口红素材，也不是大范围模糊或 AI 祛瑕疵。不生成缺失细节，不提供手动涂抹审核，不宣称新增唇部分割。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸的实际强度与来源只代表此脸，不代表共享范围内每个人；每个目标必须独立通过当前来源、唇部支撑与暗纹证据检查。</p>}
    <p className="muted">所选人脸实际强度：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
    <p className="muted">当前编辑范围的显式强度：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新强度或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null
      ? <Slider key={`${binding}:amount`} label="唇纹修整 · 当前范围强度" value={access.editValue * 100}
          min={0} max={100} disabled={access.changeDisabled} title={access.reason ?? '仅淡化已测得的唇部窄暗纹；0 为中性。'}
          onChange={value => commit(value / 100)} onReset={reset}/>
      : <AmountChoice key={`${binding}:choice`} changeDisabled={access.changeDisabled}
          resetDisabled={access.resetDisabled} onChoose={commit}/>}
    <p className="muted">共享范围只使用该范围的显式强度或你选择的新强度，不把某一张脸的继承值复制给其他人物。修改确认后在现有照片预览中查看，不创建另一条预览或导出通道。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={reset}
      title="只将当前范围的唇纹修整强度写为 0，不触碰唇妆、口红、面部祛纹或其他效果。">仅归零当前范围的唇纹修整</button>
    <p className="muted">归零写入本项的中性覆盖，不恢复继承，不清除其他范围或其他效果。缺少核心、有效读数或面部分析时仍可归零，但照片、范围、原请求与其他修改必须已确认。其他范围仍有非零效果时，引擎仍可能拒绝，不会替你清除它们。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要每个人自己的真实唇部支撑和当前 RGB 来源证据；核心就绪不等于此脸可处理。低分辨率、遮挡、唇边界、牙齿、口腔、口红高光、噪声或缺少可靠窄暗纹都可能导致拒绝或保留原样，非零强度不保证可见变化。仅支持 RGB SDR，不宣称 HDR 支持。</p>
    <p className="muted">显示 0 至 100 对应内部 0 至 1，是本产品量程，不是官方标定。真实照片、边界保护、共享范围、历史回放、预览导出一致性与交互验收均未运行（UNRUN），祛除瑕疵功能族仍未完整验收。</p>
  </section>;
}
