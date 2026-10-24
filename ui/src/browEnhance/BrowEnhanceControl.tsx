// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {BROW_ENHANCE_CONTROL_ID, BROW_ENHANCE_SIDES, browEnhanceAccess, browEnhanceAdjustPatches,
  browEnhanceBindingKey, browEnhanceLinkedPatches, browEnhanceResetPatches, browEnhanceUnlockPatch,
  browEnhanceZeroSidePatches, parseBrowEnhanceChoice, type BrowEnhanceCapability, type BrowEnhanceSide} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const sideLabel = {left: '人物自身左侧', right: '人物自身右侧'} as const;
const linkLabel = (value: boolean | null) => value === null ? '未提供有效读数' : value ? '联动' : '独立';
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** Blank, source/owner-keyed input; never submits on mount, blur or mode selection. */
function AmountChoice({label, action, changeDisabled, resetDisabled, onChoose}: {
  label: string; action: string; changeDisabled: boolean; resetDisabled: boolean; onChoose: (value: number) => void;
}) {
  const [text, setText] = useState(''), choice = parseBrowEnhanceChoice(text);
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>{label}</legend>
    <label>新数值（-100 至 100）
      <input className="pnum" type="number" min={-100} max={100} step="any" value={text}
        aria-label={`${label}新数值`} onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>{action}</button>
    <p className="muted">留空不会被当成 0，不复制或平均任何一侧的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** Existing people owner alone owns commands, receipts, history, queue and replay. */
export function BrowEnhanceControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: BrowEnhanceCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check) {
    owner.current = {patch: people.patch, check: people.check, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([browEnhanceBindingKey(view), owner.current.generation]);
  const access = browEnhanceAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch, check: people.check});
  current.current = {binding, access, patch: people.patch, check: people.check};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Confirmed fast failures may batch pending true -> false into one snapshot.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding
    && current.current.patch === people.patch && current.current.check === people.check;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(side: BrowEnhanceSide, value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    const linked = current.current.access.writeLinked;
    if (linked === null) return;
    try {dispatch(browEnhanceAdjustPatches(side, value, linked));} catch (error) {note(String(error));}
  }
  function linkWithChoice(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {dispatch(browEnhanceLinkedPatches(value));} catch (error) {note(String(error));}
  }
  function unlock() {
    if (!stillCurrent() || current.current.access.changeDisabled) return;
    dispatch([browEnhanceUnlockPatch()]);
  }
  function zeroSide(side: BrowEnhanceSide) {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(browEnhanceZeroSidePatches(side));
  }
  function resetBoth() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(browEnhanceResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  const linkedValue = access.editLeft !== null && access.editLeft === access.editRight ? access.editLeft : null;
  return <section data-control-id={BROW_ENHANCE_CONTROL_ID} aria-label="眉毛增强（已有眉毛对比，左右可独立）">
    <p>眉毛增强调整原片已有深色眉毛相对邻近额头皮肤的对比：负值减弱已有眉毛，正值加强，0 无效果。</p>
    <p className="muted">左右按人物自身左右侧定义，不是观看者或画面左右。它不是添加眉妆素材、生成毛发、改变眉形、完整去除眉毛或卸妆，也不是通用曝光调整。</p>
    <p className="muted">使用当前有效来源图像（原图或已返回合成图）测量已有深色眉毛和可靠的邻近额头参考。每个目标自己的几何支撑和光度证据由引擎检查；界面不提供测量值，不把核心就绪当成眉毛可见、支撑可靠或照片质量的证明。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸实际值和来源只代表此脸，不代表共享范围内每个人的效果；每个目标都必须独立通过来源、几何和光度检查。</p>}
    <p className="muted">所选人脸实际联动：{linkLabel(reading.linked.value)}
      {reading.linked.source ? `，来源：${provenance(view, reading.linked.source)}` : ''}。</p>
    <p className="muted">当前范围的联动显式值：{reading.linked.overridePresent
      ? reading.linked.override === null ? '无效，请明确选择或归零' : linkLabel(reading.linked.override)
      : '未设置，保留继承'}。本次写入模式：{access.writeLinked === null ? '尚待明确选择' : linkLabel(access.writeLinked)}。</p>
    {BROW_ENHANCE_SIDES.map(side => {
      const item = reading[side];
      return <div key={side}>
        <p className="muted">{sideLabel[side]}实际值：{display(item.value)}
          {item.source ? `，来源：${provenance(view, item.source)}` : ''}。</p>
        <p className="muted">当前范围的{sideLabel[side]}显式值：{item.override === null
          ? item.overridePresent ? '无效，请明确选择或归零' : '未设置，保留继承' : display(item.override)}。</p>
      </div>;
    })}
    <p className="muted">独立人脸可从此脸的实际值调整。共享范围仅从该范围的显式值或你新输入的数值写入，不把所选人脸的继承参数复制给其他人物。</p>
    <div className="prow" aria-hidden="true"><span>减弱已有眉毛</span><span>0 无效果</span><span>加强已有眉毛</span></div>
    {access.writeLinked === true && linkedValue !== null
      ? <Slider key={`${binding}:linked`} label="眉毛增强 · 左右联动" value={linkedValue * 100}
          min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '同一请求写入相同的左右值；负值减弱，正值加强。'}
          onChange={value => commit('left', value / 100)} onReset={resetBoth}/>
      : access.writeLinked === true && <AmountChoice key={`${binding}:linked-choice`}
          label="为当前范围明确选择左右相同的新数值" action="应用左右联动数值"
          changeDisabled={access.changeDisabled} resetDisabled={access.resetDisabled} onChoose={linkWithChoice}/>}
    {access.writeLinked === false && BROW_ENHANCE_SIDES.map(side => {
      const value = side === 'left' ? access.editLeft : access.editRight;
      return value !== null
        ? <Slider key={`${binding}:${side}`} label={`眉毛增强 · ${sideLabel[side]}`} value={value * 100}
            min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '只写入明确选择的这一侧；负值减弱，正值加强。'}
            onChange={amount => commit(side, amount / 100)} onReset={() => commit(side, 0)}/>
        : <AmountChoice key={`${binding}:${side}:choice`} label={`为当前范围明确选择${sideLabel[side]}`}
            action={`应用${sideLabel[side]}数值`} changeDisabled={access.changeDisabled}
            resetDisabled={access.resetDisabled} onChoose={amount => commit(side, amount)}/>;
    })}
    {access.writeLinked !== true && <AmountChoice key={`${binding}:relink-choice`}
      label="为当前范围选择联动及新的相同左右值" action="联动并应用我选择的新数值"
      changeDisabled={access.changeDisabled} resetDisabled={access.resetDisabled} onChoose={linkWithChoice}/>}
    <button type="button" className="specBtn" disabled={access.changeDisabled || access.writeLinked === false}
      aria-pressed={access.writeLinked === false} onClick={unlock}>解除联动，独立调整左右</button>
    <p className="muted">解除联动只写入独立标记，保留左右数值。重新联动必须明确选择一个新数值，并在同一请求写入联动和相同的左右值；不会自动复制、平均、归零或迁移已有参数。联动是参数相同，不保证两侧视觉结果相同。</p>
    <p className="muted">若某一侧缺少可靠支撑或额头参考，必须由你明确解除联动并把该侧归零，不能自动跳过。以下按钮在同一请求写入独立模式和所选侧 0，另一侧保持原值；在共享范围内会作用于该范围，而不是只作用于当前预览人物。</p>
    {BROW_ENHANCE_SIDES.map(side => <button key={`zero:${side}`} type="button" className="specBtn"
      disabled={access.resetDisabled} onClick={() => zeroSide(side)}>解除联动并归零{sideLabel[side]}</button>)}
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetBoth}
      title="同一请求只将当前范围的眉毛增强左右值写为 0，不改变联动标记、眉妆、眉形或其他效果。">归零当前范围的左右眉毛增强</button>
    <p className="muted">归零写入中性覆盖，不恢复继承，不清除其他范围或其他效果。缺少核心、有效读数或面部分析时仍可归零，但照片、范围、原请求和其他修改必须已确认。单侧归零后另一侧的非零效果仍须通过引擎检查；若无法通过，可归零两侧。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">遮挡、裁切、侧脸、浅色或稀疏眉毛、额头纹理与强光阴影都可能导致拒绝。不会补造缺失毛发、恢复遮挡细节或承诺完整卸除眉妆。已有眉妆素材、眉形几何和其他效果保持各自含义；当前来源及叠加兼容性由引擎决定，界面不绕过检查。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定；支撑、对比增益与过渡属于本产品策略，不是官方标定。真实照片、左右方向、联动解锁、共享范围、光度拒绝、叠加边界、预览导出一致性与交互验收均未运行（UNRUN），妆容调整功能族仍未完整验收。</p>
  </section>;
}
