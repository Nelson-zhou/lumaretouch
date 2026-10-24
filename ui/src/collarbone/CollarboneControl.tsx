// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SkinBodyPanel} from '../skinColour/SkinBodyPanel';
import {COLLARBONE_CONTROL_ID, COLLARBONE_LABEL, collarboneAccess, collarboneBindingKey,
  collarbonePatch, collarboneResetPatches, parseCollarboneChoice, type CollarboneCapability} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** Blank is not zero or a licence to copy one person's inherited amount into a shared target. */
function AmountChoice({changeDisabled, resetDisabled, onChoose}: {
  changeDisabled: boolean; resetDisabled: boolean; onChoose: (value: number) => void;
}) {
  const [text, setText] = useState(''), choice = parseCollarboneChoice(text);
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>为当前范围明确选择锁骨现有明暗增强强度</legend>
    <label>新强度（0 至 100）
      <input className="pnum" type="number" min={0} max={100} step="any" value={text}
        aria-label="锁骨现有明暗增强新强度" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>应用我选择的强度</button>
    <p className="muted">留空不等于 0，也不借用所选人物的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** Canonical people transactions remain the sole command, receipt, history and replay owner. */
export function CollarboneControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: CollarboneCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, submitCaptured: people.submitCaptured, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check || owner.current.submitCaptured !== people.submitCaptured) {
    owner.current = {patch: people.patch, check: people.check, submitCaptured: people.submitCaptured, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([collarboneBindingKey(view), owner.current.generation]);
  const access = collarboneAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch, check: people.check, submitCaptured: people.submitCaptured});
  current.current = {binding, access, patch: people.patch, check: people.check, submitCaptured: people.submitCaptured};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Observe confirmed fast failures even when pending transitions are batched.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding
    && current.current.patch === people.patch && current.current.check === people.check && current.current.submitCaptured === people.submitCaptured;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {dispatch([collarbonePatch(value)]);} catch (error) {note(String(error));}
  }
  function reset() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(collarboneResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={COLLARBONE_CONTROL_ID} aria-label={COLLARBONE_LABEL}>
    <p>{COLLARBONE_LABEL}</p>
    <p>仅增强当前有效来源图像（原图或已返回合成图）中已经可见的锁骨明暗。请独立画出本人的身体皮肤范围，并逐点标出真实可见的锁骨曲线；0 无效果，向右增加强度。</p>
    <p className="muted">官方“锁骨增强”条目当前仅部分实现。本项是手动审核的现有明暗增强，不是 AI 3D 重建、自动锁骨检测或自动人体分类，不代表官方完整效果或专有算法等效。</p>
    <p className="muted">适用类别必须由你明确选择“女”或“长辈女”并确认；系统不会从外貌推断性别或年龄，也不会改变人物标签；已有明确的“男”或“儿童”标签冲突时会拒绝非零调整，请先核对标签。只允许来源中真实可见的锁骨，不补全衣物下、裁切外、遮挡处或不可见的解剖结构。</p>
    <p className="muted">左右按图像左右标记，不是人物解剖左右。每侧 3 至 8 个手工控制点、共 1 至 2 条曲线；横向半宽独立明确选择（原始来源 4 至 256 像素）。曲线不是自动检测结果，手绘范围和真实对比仍须分别审核。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。共享范围只共享强度；每个人物必须独立拥有本功能审核的身体范围、手工曲线、类别确认与当前来源证据，不借用其他人物或其他功能的支持。</p>}
    <p className="muted">所选人物实际锁骨增强强度：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
    <p className="muted">当前编辑范围的显式强度：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新强度或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null
      ? <Slider key={`${binding}:amount`} label={`${COLLARBONE_LABEL} · 当前范围强度`} value={access.editValue * 100}
          min={0} max={100} disabled={access.changeDisabled} title={access.reason ?? '仅增强同一人物手绘可见锁骨曲线附近已有的来源明暗；0 为中性。'}
          onChange={value => commit(value / 100)} onReset={reset}/>
      : <AmountChoice key={`${binding}:choice`} changeDisabled={access.changeDisabled}
          resetDisabled={access.resetDisabled} onChoose={commit}/>}
    <p className="muted">共享范围只使用该范围的显式强度或你选择的新强度，不把某一人物的继承值、身体范围、类别确认或锁骨曲线复制给其他人物。任一实际启用人物缺少本功能有效审核时，引擎必须拒绝，不能靠所选人物的审核替其授权。修改确认后在现有照片预览中查看。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={reset}
      title="只将当前范围的锁骨现有明暗增强强度写为 0，保留本功能审核范围与手绘曲线，不触碰磨皮、肤色或其他效果。">仅归零当前范围的锁骨现有明暗增强</button>
    <p className="muted">归零写入本项的中性覆盖，不恢复继承，不移除审核范围，不清除其他范围或其他效果。缺少核心、有效读数、身体审核或面部分析时仍可归零，但照片、范围、原请求与其他修改必须已确认。其他范围仍有非零效果时，引擎仍可能拒绝，不会替你清除它们。</p>
    <SkinBodyPanel people={people} blocked={blocked} coreAvailable={access.core.available} family="collarbone"
      reviewBinding={binding} reviewCanSubmit={!access.reviewDisabled} detachNeutral={reading.value === 0}/>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要本人物独立审核的真实可见身体皮肤、手绘锁骨曲线和当前 RGB 来源证据。核心就绪不等于现有明暗足够可靠；低分辨率、遮挡、边缘、裁切、噪声、曝光裁切或缺少可靠明暗都可能导致拒绝或保留原样，非零强度不保证可见变化。仅支持 RGB SDR，不宣称 HDR 支持。</p>
    <p className="muted">显示 0 至 100 对应内部 0 至 1，是本产品量程，不是官方标定。真实照片、明暗与边界保护、共享范围、历史回放、预览导出一致性与交互验收均未运行（UNRUN），皮肤功能族仍未完整验收。</p>
  </section>;
}
