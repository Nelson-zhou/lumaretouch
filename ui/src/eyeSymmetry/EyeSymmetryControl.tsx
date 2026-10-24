// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {EYE_SYMMETRY_CONTROL_IDS, EYE_SYMMETRY_LABELS, EYE_SYMMETRY_REFERENCE_LABELS,
  eyeSymmetryAccess, eyeSymmetryBindingKey, eyeSymmetryPatch, eyeSymmetryResetPatches, eyeSymmetrySizePatches,
  parseEyeSymmetryChoice, validEyeSymmetryReference, type EyeSymmetryCapability, type EyeSymmetryReference,
  type EyeSymmetryScalar} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const display = (value: number | EyeSymmetryReference | null) => value === null ? '未提供有效读数'
  : typeof value === 'number' ? String(Number((value * 100).toFixed(6))) : EYE_SYMMETRY_REFERENCE_LABELS[value];
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}
function ReferenceOptions() {
  return <><option value="">请明确选择，不借用其他人物的值</option>
    <option value="auto">自动：每个目标实测面积较大的眼</option>
    <option value="left">人物左眼</option><option value="right">人物右眼</option></>;
}

/** Empty drafts never become zero or auto and never write on mount or blur. */
function ScalarChoice({control, changeDisabled, resetDisabled, onChoose}: {
  control: EyeSymmetryScalar; changeDisabled: boolean; resetDisabled: boolean;
  onChoose: (value: number, reference?: EyeSymmetryReference) => void;
}) {
  const [text, setText] = useState(''), [reference, setReference] = useState('');
  const choice = parseEyeSymmetryChoice(text), needsReference = control === 'size' && choice !== 0;
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled)
    || (needsReference && !validEyeSymmetryReference(reference));
  return <fieldset disabled={resetDisabled}>
    <legend>为当前范围明确选择{EYE_SYMMETRY_LABELS[control]}</legend>
    <label>新强度（0 至 100）<input className="pnum" type="number" min={0} max={100} step="any" value={text}
      aria-label={`当前范围的${EYE_SYMMETRY_LABELS[control]}新强度`} onChange={event => setText(event.target.value)}/></label>
    {control === 'size' && <label>同时选择大小参考眼
      <select aria-label="新大小强度的参考眼" value={reference} onChange={event => setReference(event.target.value)}>
        <ReferenceOptions/>
      </select></label>}
    <button type="button" className="specBtn" disabled={disabled} onClick={() => {
      if (!disabled && choice !== null) onChoose(choice,
        choice !== 0 && validEyeSymmetryReference(reference) ? reference : undefined);
    }}>应用我的选择</button>
    <p className="muted">留空不等于 0 或自动，不借用所选人脸的继承值。{control === 'size'
      ? '新大小强度和所选参考眼在同一个请求中提交；选择 0 只归零本项。' : '点击应用只写入水平强度，保留大小强度和参考眼。'}</p>
  </fieldset>;
}
function ReferenceChoice({value, disabled, onChoose}: {
  value: EyeSymmetryReference | null; disabled: boolean; onChoose: (value: EyeSymmetryReference) => void;
}) {
  const [draft, setDraft] = useState<string>(value ?? '');
  return <fieldset disabled={disabled}>
    <legend>仅修改大小对称的参考眼</legend>
    <select aria-label="当前范围大小对称的参考眼" value={draft} onChange={event => setDraft(event.target.value)}>
      <ReferenceOptions/>
    </select>
    <button type="button" className="specBtn" disabled={disabled || !validEyeSymmetryReference(draft)}
      onClick={() => {if (!disabled && validEyeSymmetryReference(draft)) onChoose(draft);}}>应用参考眼</button>
  </fieldset>;
}

/** One canonical owner owns mutation, queue, receipt, history, undo and replay on original and derived images. */
export function EyeSymmetryControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: EyeSymmetryCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check) {
    owner.current = {patch: people.patch, check: people.check, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([eyeSymmetryBindingKey(view), owner.current.generation]);
  const fences = {enabled: people.enabled, pending: people.state.pending, uncertain: people.state.uncertain,
    externalBusy: blocked, faceOk, faceWhy};
  const access = {horizontal: eyeSymmetryAccess(view, 'horizontal', capability, fences),
    size: eyeSymmetryAccess(view, 'size', capability, fences), reference: eyeSymmetryAccess(view, 'reference', capability, fences)};
  const current = useRef({binding, access, patch: people.patch, check: people.check});
  current.current = {binding, access, patch: people.patch, check: people.check};
  const mounted = useRef(false), submitted = useRef(false), checking = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Also observes a confirmed fast failure when React batches the pending transition.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding
    && current.current.patch === people.patch && current.current.check === people.check;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(control: EyeSymmetryScalar, value: number, reference?: EyeSymmetryReference) {
    if (!stillCurrent() || (value === 0 ? current.current.access[control].resetDisabled
      : current.current.access[control].changeDisabled)) return;
    if (reference !== undefined && (control !== 'size' || current.current.access.reference.changeDisabled)) return;
    try {dispatch(control === 'size' && reference !== undefined ? eyeSymmetrySizePatches(value, reference)
      : [eyeSymmetryPatch(control, value)]);} catch (error) {note(String(error));}
  }
  function commitReference(value: EyeSymmetryReference) {
    // Auto is not a neutral reset while size remains nonzero, so this uses the normal change fence.
    if (!stillCurrent() || current.current.access.reference.changeDisabled) return;
    try {dispatch([eyeSymmetryPatch('reference', value)]);} catch (error) {note(String(error));}
  }
  function resetAll() {
    if (!stillCurrent() || current.current.access.horizontal.resetDisabled) return;
    dispatch(eyeSymmetryResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent() || checking.current) return;
    checking.current = true;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));}).finally(() => {checking.current = false;});
  }
  return <section data-control-id={EYE_SYMMETRY_CONTROL_IDS.family} aria-label="眼睛对称">
    <p>水平对称和大小对称分别调节，0 不改变；参考眼只用于大小对称，不控制水平对称。</p>
    <p className="muted">水平对称使用当前来源独立测得的头部坐标轴，让双眼向共同的头部相对中间高度靠拢，保持双眼中心的中点；不是强制对齐画面水平线，也不是以某只参考眼固定另一眼。头部倾斜时画面横坐标也可能改变。</p>
    <p className="muted">大小对称根据双眼实测开口面积，对非参考眼进行局部等比缩放，而不是只拉宽。自动参考每个目标自身实测面积较大的眼，不按宽度猜测。可手动选择人物左眼或人物右眼；左右指人物自身，不是画面左右。不会把一眼的像素复制、镜像到另一眼。</p>
    <p className="muted">每个目标使用当前有效来源图像（原图或已返回合成图）的真实双眼证据，独立计算头轴、中心与面积；不能从眼睛连线反推水平基准。闭眼、严重遮挡、过大偏转或倾斜、截断及支撑不足会保守拒绝，不生成睁眼，不补造缺失部位。已经对称时真正的无变化是有效结果，不人为添加位移。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸的实际值和来源只代表此脸；共享范围内每个目标都必须通过自己的来源、双眼证据和组合检查。</p>}
    {(['horizontal', 'size'] as const).map(control => {
      const item = access[control], {reading} = item, label = EYE_SYMMETRY_LABELS[control];
      return <section key={control} data-control-id={EYE_SYMMETRY_CONTROL_IDS[control]} aria-label={label}>
        <p>所选人脸实际{label}：{display(reading.value)}{reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
        <p className="muted">当前编辑范围的显式值：{reading.override === null
          ? reading.overridePresent ? '无效，请明确选择新值或归零' : '未设置，保留继承' : display(reading.override)}。</p>
        {item.editValue !== null ? <Slider key={`${binding}:${control}`} label={label} value={item.editValue * 100}
          min={0} max={100} disabled={item.changeDisabled} title={item.reason ?? '0 无效果，增加此项对称调整强度。'}
          onChange={value => commit(control, value / 100)} onReset={() => commit(control, 0)}/>
          : <ScalarChoice key={`${binding}:${control}:choice`} control={control}
            changeDisabled={item.changeDisabled || (control === 'size' && access.reference.changeDisabled)}
            resetDisabled={item.resetDisabled} onChoose={(value, reference) => commit(control, value, reference)}/>}
        <button type="button" className="specBtn" disabled={item.resetDisabled} onClick={() => commit(control, 0)}>仅归零当前范围的{label}</button>
        {item.reason && <p className="muted" role="status">{item.reason}</p>}
      </section>;
    })}
    <section data-control-id={EYE_SYMMETRY_CONTROL_IDS.reference} aria-label={EYE_SYMMETRY_LABELS.reference}>
      <p>所选人脸实际大小参考眼：{display(access.reference.reading.value)}
        {access.reference.reading.source ? `，来源：${provenance(view, access.reference.reading.source)}` : ''}。</p>
      <p className="muted">当前范围的显式参考眼：{access.reference.reading.override === null
        ? access.reference.reading.overridePresent ? '无效，请明确选择' : '未设置，保留各目标继承' : display(access.reference.reading.override)}。</p>
      <ReferenceChoice key={`${binding}:reference`} value={access.reference.editValue}
        disabled={access.reference.changeDisabled} onChoose={commitReference}/>
      {access.reference.reason && <p className="muted" role="status">{access.reference.reason}</p>}
    </section>
    <p className="muted">共享范围只使用自己的显式值或你的明确新选择，不把所选人脸的继承参数复制给其他人物。只调整已有强度滑杆会保留各目标的参考眼；参考眼只影响大小，不改变水平强度。两项强度均为 0 时，无论参考眼为何都无几何效果。</p>
    <button type="button" className="specBtn" disabled={access.horizontal.resetDisabled} onClick={resetAll}>重置当前范围的眼睛对称（0 / 0 / 自动）</button>
    <p className="muted">重置在一个人物请求中写入水平 0、大小 0、参考眼 auto。归零写入中性覆盖，不恢复继承，不清除其他范围、眼形、眼球调整或其他效果。缺少核心、有效读数或双眼分析时仍可重置，但来源、编辑范围和原请求必须已确认。仅将参考眼改为自动不等于归零。</p>
    <p className="muted">若另一项、其他范围或其他效果仍有不支持的非零参数，引擎仍可能拒绝；不会为使请求通过而替你清除它们。</p>
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">核心就绪不代表此脸或当前组合可用；界面不推测测量结果、不绕过手动液化等兼容性检查。局部变形与衰减可能改变眼周邻近像素，不保证先前编辑叠加后其他部位完全不变。显示 0 至 100 对应内部 0 至 1，是本产品强度量程，不是官方标定或临床测量。</p>
    <p className="muted">真实照片、已对称无变化、闭眼拒绝、头部倾斜、左右参考、共享目标、历史回放、预览导出一致性与交互验收均未运行（UNRUN）；眼睛增强功能族仍未完整验收。</p>
  </section>;
}
