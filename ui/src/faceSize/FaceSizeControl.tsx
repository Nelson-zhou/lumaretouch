// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {FACE_SIZE_CONTROL_ID, faceSizeAccess, faceSizeBindingKey, faceSizeLocalScale,
  faceSizePatch, faceSizeResetPatches, parseFaceSizeChoice, type FaceSizeCapability} from './model';

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
  const choice = parseFaceSizeChoice(text);
  return <fieldset disabled={disabled}>
    <legend>为当前范围明确选择整脸大小</legend>
    <label>小脸新数值（-100 至 100）
      <input className="pnum" type="number" min={-100} max={100} step="any" value={text}
        aria-label="当前范围的小脸新数值" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled || choice === null}
      onClick={() => {if (choice !== null) onChoose(choice);}}>应用我选择的整脸大小</button>
    <p className="muted">留空不会被当成 0，也不会借用所选人脸的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** The existing people owner alone owns mutation, queue, receipts, undo and replay. */
export function FaceSizeControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: FaceSizeCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = faceSizeBindingKey(view);
  const access = faceSizeAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
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
    try {dispatch([faceSizePatch(value)]);} catch (error) {note(String(error));}
  }
  function resetAmount() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(faceSizeResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={FACE_SIZE_CONTROL_ID} aria-label="小脸（局部整脸大小）">
    <p>小脸调整整张脸的整体大小。正值整体缩小，负值整体放大，0 不改变大小；不是只收窄轮廓，也不是分别调整眼、鼻、嘴。</p>
    <p className="muted">使用当前有效来源图像（原图或已返回合成图）的真实面部分析。核心区内整张脸与内部五官按同一比例缩放；外部以平滑过渡连接原图，附近背景、头发和颈部过渡带也会移动。</p>
    <p className="muted">只支持正脸与轻度偏转的可靠实测面部。不是 AI 重建、3D 塑颜或脸部/身体分割，不补造遮挡、截断或画面外的部位，也不缩放整张图像。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸实际值和来源只代表此脸，不代表共享范围内每个人的实际效果；每个目标必须使用自己的真实分析。</p>}
    <p className="muted">所选人脸实际小脸数值：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。
      {reading.value !== null ? `对应核心区局部比例 ${Number(faceSizeLocalScale(reading.value).toFixed(6))}；这不是实拍效果验收结果。` : ''}</p>
    <p className="muted">当前编辑范围的显式值：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新数值或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null ? <>
      <div className="prow" aria-hidden="true"><span>整体放大</span><span>0 无效果</span><span>整体缩小</span></div>
      <Slider key={`${binding}:amount`} label="小脸 · 当前范围的整体大小" value={access.editValue * 100}
        min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '负值整脸放大，正值整脸缩小；不单独改变五官比例。'}
        onChange={value => commit(value / 100)} onReset={resetAmount}/>
    </> : <AmountChoice key={`${binding}:choice`} disabled={access.changeDisabled} onChoose={commit}/>}
    <p className="muted">独立人脸可从此脸实际值调整；共享范围仅从该范围的显式值或你新输入的数值写入，不把所选人脸的继承参数复制给其他人物。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetAmount}
      title="只将当前范围的小脸 amount 写为 0，保留其他脸型、五官、旧配方和编辑范围。">归零当前范围的小脸</button>
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
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定；局部比例为 1 − 0.06 × amount，核心区从 1.06 到 0.94，不是整图缩放，也不是官方质量指标。真实照片、边缘背景、预览导出一致性与交互验收均未运行（UNRUN），面部重塑功能族仍未完整验收。</p>
  </section>;
}
