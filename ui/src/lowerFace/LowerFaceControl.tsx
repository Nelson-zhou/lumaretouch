// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {LOWER_FACE_CONTROL_ID, lowerFaceAccess, lowerFaceBindingKey, lowerFaceLocalEndpointRatio,
  lowerFacePatch, lowerFaceResetPatches, parseLowerFaceChoice, type LowerFaceCapability} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** No selected-face prefill, mount write, blur write or implicit blank-to-zero conversion. */
function AmountChoice({disabled, onChoose}: {disabled: boolean; onChoose: (value: number) => void}) {
  const [text, setText] = useState('');
  const choice = parseLowerFaceChoice(text);
  return <fieldset disabled={disabled}>
    <legend>为当前范围明确选择下庭调整</legend>
    <label>下庭新数值（-100 至 100）
      <input className="pnum" type="number" min={-100} max={100} step="any" value={text}
        aria-label="当前范围的下庭新数值" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled || choice === null}
      onClick={() => {if (choice !== null) onChoose(choice);}}>应用我选择的下庭调整</button>
    <p className="muted">留空不会被当成 0，也不会借用所选人脸的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** The existing people owner alone owns mutation, queue, receipts, undo and replay. */
export function LowerFaceControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: LowerFaceCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = lowerFaceBindingKey(view);
  const access = lowerFaceAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch}); current.current = {binding, access, patch: people.patch};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // A fast confirmed failure may batch pending true -> false into a single owner snapshot.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding && current.current.patch === people.patch;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {dispatch([lowerFacePatch(value)]);} catch (error) {note(String(error));}
  }
  function resetAmount() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(lowerFaceResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={LOWER_FACE_CONTROL_ID} aria-label="下庭（局部纵向长度）">
    <p>下庭调整鼻基底至下巴区域的纵向长度。正值拉长，负值缩短，0 无效果；不是整脸大小、收下巴、仅下巴长短或以耳朵为依据的短脸调整。</p>
    <p className="muted">使用当前有效来源图像（原图或已返回合成图）的真实 478 点分析，鼻基底与下巴只是该来源的实测代理点，不是临床解剖标志，也不能单凭关键点确认遮挡部位是否可见。</p>
    <p className="muted">鼻基底以下内部区域（包括嘴唇）在头部局部坐标系中沿纵向平滑移动，各位置的位移不相同，并非整个下庭均匀缩放。只有本次新增映射保持横向坐标及鼻基底以上区域不变；先前编辑可能已把点移入过渡带，不能据此承诺最终叠加结果的上半脸完全不变。</p>
    <p className="muted">鼻基底至下巴代理端点间距的改变在横向核心区生效，外缘平滑衔接；邻近颈部与背景过渡带也会移动。不是 AI 重建、3D 塑颜或新增分割，不补造被遮挡、截断或画面外的部位。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸实际值和来源只代表此脸，不代表共享范围内每个人的实际效果；每个目标必须使用自己的真实分析。</p>}
    <p className="muted">所选人脸实际下庭数值：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。
      {reading.value !== null ? `未叠加其他几何时，横向核心区原始鼻基底至下巴代理端点间距的局部比例为 ${Number(lowerFaceLocalEndpointRatio(reading.value).toFixed(6))}；不是所有下庭位置的缩放比例，也不是实拍效果读数。` : ''}</p>
    <p className="muted">当前编辑范围的显式值：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新数值或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null ? <>
      <div className="prow" aria-hidden="true"><span>缩短下庭</span><span>0 无效果</span><span>拉长下庭</span></div>
      <Slider key={`${binding}:amount`} label="下庭 · 当前范围的纵向长度" value={access.editValue * 100}
        min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '负值缩短下庭，正值拉长下庭；嘴唇参与平滑纵向移动，不是仅调整下巴。'}
        onChange={value => commit(value / 100)} onReset={resetAmount}/>
    </> : <AmountChoice key={`${binding}:choice`} disabled={access.changeDisabled} onChoose={commit}/>}
    <p className="muted">独立人脸可从此脸实际值调整；共享范围仅从该范围的显式值或你新输入的数值写入，不把所选人脸的继承参数复制给其他人物。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetAmount}
      title="只将当前范围的下庭 amount 写为 0，保留其他脸型、五官、旧配方和编辑范围。">归零当前范围的下庭</button>
    <p className="muted">归零写入中性覆盖，不恢复继承，不清除其他范围或其他效果。缺少核心、有效读数或面部分析时仍可归零，但照片、范围、原请求和其他修改必须已确认。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">已有几何调整与当前有效来源由引擎统一检查和组合。界面不绕过手动液化等兼容性限制；核心就绪不代表此脸或当前组合可用，请以引擎原始拒绝原因和实拍检查为准。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定。原始局部端点间距比为 1 + 0.08 × amount，从 0.92 到 1.08；平滑非均匀形变不代表整片下庭按此比例缩放，也不是官方质量指标。真实照片、嘴唇参与、边缘背景、预览导出一致性与交互验收均未运行（UNRUN），面部重塑功能族仍未完整验收。</p>
  </section>;
}
