// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SkinBodyPanel} from '../skinColour/SkinBodyPanel';
import {BODY_FACE_MATCH_CONTROL_ID, BODY_FACE_MATCH_LABEL, bodyFaceMatchAccess, bodyFaceMatchBindingKey,
  bodyFaceMatchPatch, bodyFaceMatchResetPatches, parseBodyFaceMatchChoice, type BodyFaceMatchCapability} from './model';

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
  const [text, setText] = useState(''), choice = parseBodyFaceMatchChoice(text);
  const disabled = choice === null || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>为当前范围明确选择身体向本人脸部色度匹配强度</legend>
    <label>新强度（0 至 100）
      <input className="pnum" type="number" min={0} max={100} step="any" value={text}
        aria-label="身体向本人脸部色度匹配新强度" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>应用我选择的强度</button>
    <p className="muted">留空不等于 0，也不借用所选人物的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}

/** Canonical people transactions remain the sole command, receipt, history and replay owner. */
export function BodyFaceMatchControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: BodyFaceMatchCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, submitCaptured: people.submitCaptured, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check || owner.current.submitCaptured !== people.submitCaptured) {
    owner.current = {patch: people.patch, check: people.check, submitCaptured: people.submitCaptured, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([bodyFaceMatchBindingKey(view), owner.current.generation]);
  const access = bodyFaceMatchAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
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
    try {dispatch([bodyFaceMatchPatch(value)]);} catch (error) {note(String(error));}
  }
  function reset() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(bodyFaceMatchResetPatches());
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={BODY_FACE_MATCH_CONTROL_ID} aria-label={BODY_FACE_MATCH_LABEL}>
    <p>{BODY_FACE_MATCH_LABEL}</p>
    <p>只把当前人物独立手绘审核的身体皮肤色度向本人的实测脸部参考调整。参考来自当前有效来源图像（原图或已返回合成图）在肖像效果之前的冻结来源阶段，包含已验证的现有修复（若有），不是其他人物，也不是后续美白、红润或其他修饰后的脸。0 无效果，向右增加强度。</p>
    <p className="muted">官方条目“肤色统一（身体）”对应身体与脸部肤色统一；当前仅部分实现。本项依赖真实脸部与身体观察、人物关联和本功能独立审核，不是学习型 AI 或自动身体皮肤实例识别，不代表官方完整效果或专有算法等效。</p>
    <p className="muted">仅在本项处理阶段保留实际输入的线性亮度，不匹配脸部亮度、不复制脸部 RGB、不承诺其他效果叠加后的最终亮度不变，也不保证身体等同于后续修饰后的脸。不是提亮、美白、大范围模糊或全图染色，也不替代肤色色温、色调、光泽度、纹理度或清晰度。</p>
    <p className="muted">不识别妆容，不分离物理光照与皮肤材质；彩妆、色光、晒痕或原有肤色差异可能被当作色度差异。不会自动判断这些差异是否应当去除，也不会补全衣物下或被遮挡的皮肤。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。共享范围只共享强度；每个人物必须独立拥有本功能审核的身体范围和当前来源中本人的实测脸部参考。没有任意参考脸选择器，不借用其他人物、其他来源或身体色度均匀的审核。</p>}
    <p className="muted">所选人物实际身体强度：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
    <p className="muted">当前编辑范围的显式强度：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新强度或归零' : '未设置，保留继承' : display(reading.override)}。</p>
    {access.editValue !== null
      ? <Slider key={`${binding}:amount`} label={`${BODY_FACE_MATCH_LABEL} · 当前范围强度`} value={access.editValue * 100}
          min={0} max={100} disabled={access.changeDisabled} title={access.reason ?? '仅调整审核身体的色度，参考同一人物的不可变来源脸部；保留本阶段实际亮度，0 为中性。'}
          onChange={value => commit(value / 100)} onReset={reset}/>
      : <AmountChoice key={`${binding}:choice`} changeDisabled={access.changeDisabled}
          resetDisabled={access.resetDisabled} onChoose={commit}/>}
    <p className="muted">共享范围只使用该范围的显式强度或你选择的新强度，不把某一人物的继承值、身体范围或参考色复制给其他人物。任一实际启用人物缺少本功能有效审核时，引擎必须拒绝，不能靠所选人物的审核替其授权。修改确认后在现有照片预览中查看。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={reset}
      title="只将当前范围的身体向本人脸部色度匹配强度写为 0，保留审核范围，不触碰脸部色度均匀、旧版磨皮或其他效果。">仅归零当前范围的身体向本人脸部色度匹配</button>
    <p className="muted">归零写入本项的中性覆盖，不恢复继承，不移除审核范围，不清除其他范围或其他效果。缺少核心、有效读数、身体审核或面部分析时仍可归零，但照片、范围、原请求与其他修改必须已确认。其他范围仍有非零效果时，引擎仍可能拒绝，不会替你清除它们。</p>
    <SkinBodyPanel people={people} blocked={blocked} coreAvailable={access.core.available} family="body_face_match"
      reviewBinding={binding} reviewCanSubmit={!access.reviewDisabled} detachNeutral={reading.value === 0}/>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">需要本人物独立审核的真实可见身体皮肤、本人的实测脸部皮肤和当前 RGB 来源证据；核心就绪不等于身体范围或脸部参考可处理。低分辨率、遮挡、边缘、裁切、噪声、曝光裁切或缺少可靠色度证据都可能导致拒绝或保留原样，非零强度不保证可见变化。仅支持 RGB SDR，不宣称 HDR 支持。</p>
    <p className="muted">显示 0 至 100 对应内部 0 至 1，是本产品量程，不是官方标定。真实照片、亮度与边界保护、共享范围、历史回放、预览导出一致性与交互验收均未运行（UNRUN），皮肤功能族仍未完整验收。</p>
  </section>;
}
