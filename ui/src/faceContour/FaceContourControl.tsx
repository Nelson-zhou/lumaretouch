// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, type ComponentType} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {FACE_CONTOUR_CONTROL_IDS, FACE_CONTOUR_LABELS, FACE_CONTOUR_SIDES, faceContourAccess,
  faceContourAdjustPatches, faceContourBindingKey, faceContourLinkPatch, faceContourResetPatches,
  type FaceContourCapability, type FaceContourKey, type FaceContourSide} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const sideLabel = {left: '人物自身左侧', right: '人物自身右侧'} as const;
const linkedLabel = (value: boolean | null) => value === null ? '未提供有效读数' : value ? '联动' : '独立';

/** Generic people.patch remains the sole mutation, receipt, queue, undo and replay owner. */
export function FaceContourControl({control, people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  control: FaceContourKey; people: PeopleOwner; capability?: FaceContourCapability | null;
  blocked: boolean; faceOk: boolean; faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = faceContourBindingKey(view);
  const access = faceContourAccess(view, control, capability, {enabled: people.enabled,
    pending: people.state.pending, uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, control, access}); current.current = {binding, control, access};
  const mounted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  const stillCurrent = () => mounted.current && current.current.binding === binding && current.current.control === control;
  function commit(side: FaceContourSide, value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    const linked = current.current.access.writeLinked;
    if (linked === null) return; // Dedicated neutral buttons remain available without any link readback.
    try {people.patch(faceContourAdjustPatches(control, side, value, linked));} catch (error) {note(String(error));}
  }
  function setLinked(linked: boolean) {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    try {people.patch([faceContourLinkPatch(control, linked)]);} catch (error) {note(String(error));}
  }
  function resetControl() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    try {people.patch(faceContourResetPatches(control));} catch (error) {note(String(error));}
  }
  function resetAll() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    try {people.patch(faceContourResetPatches());} catch (error) {note(String(error));}
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access, label = FACE_CONTOUR_LABELS[control];
  return <section data-control-id={FACE_CONTOUR_CONTROL_IDS[control]} aria-label={`${label}二维轮廓`}>
    <p>{label}只调整当前有效来源图像（原图或已返回合成图）中已测得的可见二维轮廓。
      {control === 'cheekbone' ? '负值向外扩展，正值向内收窄。' : '负值向内收窄，正值向外扩展。'}0 不改变轮廓。</p>
    <p className="muted">左右按人物自身解剖侧定义，不是观看者或画面左右。仅支持正脸与轻度偏转、可见且可靠的轮廓；遮挡、截断、过度侧转或邻近其他人脸的支持区域可能被拒绝，不补造隐藏部位。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方数值和来源仅代表所选人脸，不代表共享范围内每个人的实际效果；每个目标必须使用自己的真实分析与可见轮廓证据。</p>}
    <p className="muted">所选人脸实际联动：{linkedLabel(reading.linked.value)}
      {reading.linked.source ? `，来源：${sourceLabel(reading.linked.source)}` : ''}。</p>
    <p className="muted">此编辑范围的联动设置：{reading.linked.overridePresent
      ? reading.linked.override === null ? '显式值无效，请重新选择' : linkedLabel(reading.linked.override)
      : '未设显式值，保留继承'}。本次写入模式：{access.writeLinked === null ? '尚待明确选择' : linkedLabel(access.writeLinked)}。</p>
    <div className="prow" role="group" aria-label={`${label}写入联动设置`}>
      <button type="button" className="specBtn" disabled={access.resetDisabled} aria-pressed={access.writeLinked === true}
        onClick={() => setLinked(true)}>联动调整左右</button>
      <button type="button" className="specBtn" disabled={access.resetDisabled} aria-pressed={access.writeLinked === false}
        onClick={() => setLinked(false)}>独立调整左右</button>
    </div>
    <p className="muted">切换联动只改变联动标记，不复制、平均或重置两侧数值。联动后下一次数值修改才会在同一请求中写入左右两侧。共享范围没有显式联动设置时，必须先选择，不能拿某一张脸的继承值替其他人物决定。</p>
    {FACE_CONTOUR_SIDES.map(side => {
      const item = reading[side];
      return <div key={side}>
        {item.value !== null && <>
          <div className="prow" aria-hidden="true"><span>{control === 'cheekbone' ? '向外扩展' : '向内收窄'}</span><span>0 无效果</span><span>{control === 'cheekbone' ? '向内收窄' : '向外扩展'}</span></div>
          <Slider key={`${binding}:${control}:${side}`} label={`${label} · ${sideLabel[side]}`} value={Math.round(item.value * 100)}
            min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? `${sideLabel[side]}，不是画面左右；0 为中性。`}
            onChange={value => commit(side, value / 100)} onReset={() => commit(side, 0)}/>
          {item.source && <p className="muted">{sideLabel[side]}有效值来源：{sourceLabel(item.source)}。</p>}
        </>}
        <p className="muted">当前范围的{sideLabel[side]}显式值：{item.override === null
          ? item.overridePresent ? '无效，请刷新或归零' : '未设置，保留继承' : Math.round(item.override * 100)}。</p>
      </div>;
    })}
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetControl}
      title="同一请求仅将本部位左右两侧设为 0，不改变任何联动标记或其他部位。">归零当前范围的{label}左右两侧</button>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetAll}
      title="同一请求将太阳穴、颧骨、下颌共六个数值设为 0，保留全部联动标记与继承关系。">同时归零当前范围的太阳穴、颧骨和下颌</button>
    <p className="muted">归零写入当前范围的中性数值覆盖，不恢复数值继承，不清除其他范围或旧瘦脸，也不会把继承的联动设置变为显式值。缺少核心、有效读数或面部分析时仍可归零，但必须等待原请求和其他修改确认。其他范围的非零参数可能仍令引擎拒绝渲染。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">这是独立二维轮廓调整，不是旧瘦脸别名，不是 AI 重建、3D 塑颜或骨骼矫正。局部变形也会影响轮廓外的邻近背景过渡带，不能保证背景完全不动；无可靠边界、截断或邻人冲突时应拒绝，而不是拉扯其他人脸。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定。核心就绪不代表此脸或每一侧可用；非零参数不保证可见变化或照片质量合格。真实照片、边缘背景、预览导出一致性与交互验收尚未运行，面部重塑功能族仍未完整验收。</p>
  </section>;
}
