// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {PHILTRUM_CONTROL_ID, philtrumAccess, philtrumBindingKey, philtrumPatch,
  philtrumResetPatches, parsePhiltrumChoice, type PhiltrumCapability} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** Starts blank. No selected-face prefill, mount write, blur write or blank-to-zero conversion. */
function AmountChoice({changeDisabled, resetDisabled, onChoose}: {
  changeDisabled: boolean; resetDisabled: boolean; onChoose: (value: number) => void;
}) {
  const [text, setText] = useState(''), choice = parsePhiltrumChoice(text);
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>为当前范围明确选择人中调整</legend>
    <label>人中新数值（-100 至 100）
      <input className="pnum" type="number" min={-100} max={100} step="any" value={text}
        aria-label="当前范围的人中新数值" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>应用我选择的人中调整</button>
    <p className="muted">留空不会被当成 0，也不会借用所选人脸的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** The existing people owner alone owns mutation, queue, receipts, undo and replay. */
export function PhiltrumControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: PhiltrumCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check) {
    owner.current = {patch: people.patch, check: people.check, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([philtrumBindingKey(view), owner.current.generation]);
  const access = philtrumAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch, check: people.check});
  current.current = {binding, access, patch: people.patch, check: people.check};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Owner snapshots also observe confirmed fast failures with batched pending transitions.
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
    try {dispatch([philtrumPatch(value)]);} catch (error) {note(String(error));}
  }
  function resetAmount() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(philtrumResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={PHILTRUM_CONTROL_ID} aria-label="人中（鼻下至唇上局部间距）">
    <p>人中沿头部局部纵向调整鼻下至唇上间距。正值拉长，负值缩短，0 无效果；不是嘴巴上下位置、中庭、下庭、下巴长短或尖下巴的别名。</p>
    <p className="muted">使用每个目标当前有效来源图像（原图或已返回合成图）的真实分析。固定上边界位于全部 24 个鼻部顶点下方，下边界位于全部 40 个嘴唇顶点上方，并留出边界余量；两条边界之间的实测间隙决定支撑。这里不是鼻点 2 至唇点 0 的简单距离，也不是临床人中长度或精确解剖分割。</p>
    <p className="muted">本次新增映射保持固定上边界以上的实测鼻部不动，间隙内平滑、非均匀增加纵向位移，同高度脸颊也可能改变。嘴唇和下方脸部在横向核心区共同等量平移，再向颈部与背景平滑衰减；不是只移动上唇，也不是只对人中皮肤进行分割后变形。</p>
    <p className="muted">本映射保持局部横向坐标；头部倾斜时画面横坐标仍可能改变。先前几何编辑可能已把鼻部或其他像素移入本次过渡带，因此不承诺最终叠加结果的鼻部、嘴唇、上半脸或背景完全不变。不是 AI 重建、3D 塑颜或新增分割，不补造遮挡、截断或画面外的部位。</p>
    <p className="muted">核心保留保守的 P ≤ 8 支撑界限，较短间隙可能被拒绝；不能保证所有正面人像可用，也没有实拍拒绝比例数据。界面不捏造间隙长度、可见性或质量测量，关键点本身也不能证明遮挡区域可见。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸实际值和来源只代表此脸，不代表共享范围内每个人；每个目标必须通过自己的来源、支撑与组合检查。</p>}
    <p className="muted">所选人脸实际人中数值：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
    <p className="muted">当前编辑范围的显式值：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新数值或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null ? <>
      <div className="prow" aria-hidden="true"><span>缩短人中</span><span>0 无效果</span><span>拉长人中</span></div>
      <Slider key={`${binding}:amount`} label="人中 · 当前范围的局部纵向间距" value={access.editValue * 100}
        min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '负值缩短人中，正值拉长人中；嘴唇与下方脸部共同平移，同高度脸颊可能改变。'}
        onChange={value => commit(value / 100)} onReset={resetAmount}/>
    </> : <AmountChoice key={`${binding}:choice`} changeDisabled={access.changeDisabled}
      resetDisabled={access.resetDisabled} onChoose={commit}/>}
    <p className="muted">独立人脸可从此脸实际值调整；共享范围仅使用该范围的显式值或你输入的新数值，不把所选人脸的继承参数复制给其他人物。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetAmount}
      title="只将当前范围的 lnx.philtrum.v1 /amount 写为 0，保留其他脸型、五官、旧配方和编辑范围。">仅归零当前范围的人中</button>
    <p className="muted">归零写入中性覆盖，不恢复继承，不清除其他范围或其他效果，不迁移或重置任何旧操作。缺少核心、有效读数或面部分析时仍可归零，但照片、编辑范围、原请求和其他修改必须已确认。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">已有几何调整与当前有效来源由引擎统一检查和组合。界面不绕过手动液化等兼容性限制；核心就绪不代表此脸或当前组合可用，请以引擎原始拒绝原因和实拍检查为准。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是官方标定或实测解剖比例。间隙边界、增益与过渡形状均为本产品局部策略。真实照片、正负方向、鼻部边界、嘴唇与下方脸部平移、同高度脸颊、边缘背景、短间隙拒绝、历史回放、预览导出一致性与交互验收均未运行（UNRUN），面部重塑功能族仍未完整验收。</p>
  </section>;
}
