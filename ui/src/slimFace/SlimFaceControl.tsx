// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SLIM_FACE_CONTROL_ID, SLIM_FACE_SIDES, legacySlimFacePatch, parseSlimFaceChoice,
  replaceLegacySlimFacePatches, slimFaceAccess, slimFaceAdjustPatches, slimFaceBindingKey,
  slimFaceLinkPatch, slimFaceResetPatches, type SlimFaceCapability, type SlimFaceSide} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
const sideLabel = {left: '人物自身左侧', right: '人物自身右侧'} as const;
const linkLabel = (value: boolean | null) => value === null ? '未提供有效读数' : value ? '联动' : '独立';
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}

/** A source-keyed draft, never prefilled from either recipe and never submitted on mount/blur. */
function ReplacementChoice({linked, disabled, onReplace}: {
  linked: boolean | null; disabled: boolean; onReplace: (left: number, right: number) => void;
}) {
  const [left, setLeft] = useState(''), [right, setRight] = useState('');
  const chosenLeft = parseSlimFaceChoice(left), chosenRight = linked ? chosenLeft : parseSlimFaceChoice(right);
  return <fieldset disabled={disabled || linked === null}>
    <legend>明确选择新版数值后替换旧版</legend>
    <p className="muted">这里不是旧参数的自动换算。请输入希望采用的新版数值（-100 至 100）；输入框留空不会被当成 0。</p>
    <label>{linked ? '左右联动的新数值' : '人物自身左侧的新数值'}
      <input className="pnum" type="number" min={-100} max={100} step="any" value={left}
        aria-label={linked ? '替换旧版：左右联动的新数值' : '替换旧版：人物自身左侧的新数值'}
        onChange={event => setLeft(event.target.value)}/></label>
    {linked !== true && <label>人物自身右侧的新数值
      <input className="pnum" type="number" min={-100} max={100} step="any" value={right}
        aria-label="替换旧版：人物自身右侧的新数值" onChange={event => setRight(event.target.value)}/></label>}
    <button type="button" className="specBtn" disabled={disabled || linked === null || chosenLeft === null || chosenRight === null}
      onClick={() => {if (chosenLeft !== null && chosenRight !== null) onReplace(chosenLeft, chosenRight);}}
      title="同一人物修改请求将当前范围的旧版瘦脸写为 0，并写入我明确选择的新版左右值；不改变联动标记。">
      一次替换：归零旧版并应用我选择的新数值
    </button>
  </fieldset>;
}

/** The existing generic people owner remains the only queue, receipt, history and replay authority. */
export function SlimFaceControl({people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  people: PeopleOwner; capability?: SlimFaceCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = slimFaceBindingKey(view);
  const access = slimFaceAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access}); current.current = {binding, access};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Depend on the owner snapshot, not only booleans: a fast confirmed failure
  // can batch pending true -> false before this component renders either state.
  }, [binding, people.state]);
  const stillCurrent = () => mounted.current && current.current.binding === binding;
  function dispatch(patches: ParameterPatch[]) {
    if (!stillCurrent() || submitted.current) return;
    submitted.current = true;
    try {people.patch(patches);} catch (error) {submitted.current = false; note(String(error));}
  }
  function commit(side: SlimFaceSide, value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    const linked = current.current.access.writeLinked;
    if (linked === null) return;
    try {dispatch(slimFaceAdjustPatches(side, value, linked));} catch (error) {note(String(error));}
  }
  function setLinked(linked: boolean) {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    try {dispatch([slimFaceLinkPatch(linked)]);} catch (error) {note(String(error));}
  }
  function resetNew() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(slimFaceResetPatches());
  }
  function commitLegacy(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.legacyChangeDisabled)) return;
    try {dispatch([legacySlimFacePatch(value)]);} catch (error) {note(String(error));}
  }
  function replaceLegacy(left: number, right: number) {
    if (!stillCurrent() || current.current.access.replacementDisabled) return;
    const linked = current.current.access.writeLinked;
    if (linked === null) return;
    try {dispatch(replaceLegacySlimFacePatches(left, right, linked));} catch (error) {note(String(error));}
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  const {reading} = access;
  return <section data-control-id={SLIM_FACE_CONTROL_ID} aria-label="瘦脸（可见二维轮廓，左右可独立）">
    <p>新版瘦脸沿已验证的真实面部椭圆轮廓，组合调整太阳穴、面颊和下颌。正值向内收窄，负值向外扩展，0 不改变轮廓。</p>
    <p className="muted">处理当前有效来源图像（原图或已返回合成图）。左右按人物自身解剖侧定义，不是观看者或画面左右。仅支持正脸与轻度偏转、可见且可靠的轮廓，不补造被遮挡或画面外的部位。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方实际值和来源只代表所选人脸；共享范围内每个目标仍须通过自己的真实分析与可见轮廓检查。</p>}
    <p className="muted">所选人脸实际联动：{linkLabel(reading.linked.value)}
      {reading.linked.source ? `，来源：${provenance(view, reading.linked.source)}` : ''}。</p>
    <p className="muted">当前范围的联动设置：{reading.linked.overridePresent
      ? reading.linked.override === null ? '显式值无效，请重新选择' : linkLabel(reading.linked.override)
      : '未设显式值，保留继承'}。本次写入模式：{access.writeLinked === null ? '尚待明确选择' : linkLabel(access.writeLinked)}。</p>
    <div className="prow" role="group" aria-label="瘦脸写入联动设置">
      <button type="button" className="specBtn" disabled={access.resetDisabled} aria-pressed={access.writeLinked === true}
        onClick={() => setLinked(true)}>联动调整左右</button>
      <button type="button" className="specBtn" disabled={access.resetDisabled} aria-pressed={access.writeLinked === false}
        onClick={() => setLinked(false)}>独立调整左右</button>
    </div>
    <p className="muted">切换联动只改变联动标记，不复制、平均或重置已有的左右值；下一次数值修改才同时写入两侧。共享范围必须明确选择写入模式，不能用某一张脸的继承值替其他人物决定。</p>
    {SLIM_FACE_SIDES.map(side => {
      const item = reading[side];
      return <div key={side}>
        <p className="muted">{sideLabel[side]}实际值：{display(item.value)}
          {item.source ? `，来源：${provenance(view, item.source)}` : ''}。</p>
        {item.value !== null && <>
          <div className="prow" aria-hidden="true"><span>向外扩展</span><span>0 无效果</span><span>向内收窄</span></div>
          <Slider key={`${binding}:${side}`} label={`瘦脸 · ${sideLabel[side]}`} value={item.value * 100}
            min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '按人物自身左右侧调整，0 为中性。'}
            onChange={value => commit(side, value / 100)} onReset={() => commit(side, 0)}/>
        </>}
        <p className="muted">当前范围的{sideLabel[side]}显式值：{item.override === null
          ? item.overridePresent ? '无效，请刷新或归零' : '未设置，保留继承' : display(item.override)}。</p>
      </div>;
    })}
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetNew}
      title="同一请求只将当前范围的新版左右瘦脸设为 0，不改变联动标记或旧版参数。">归零当前范围的新版左右瘦脸</button>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}

    <p className="muted">所选人脸旧版瘦脸实际值：{display(reading.legacy.value)}
      {reading.legacy.source ? `，来源：${provenance(view, reading.legacy.source)}` : ''}。</p>
    <p className="muted">当前范围的旧版显式值：{reading.legacy.override === null
      ? reading.legacy.overridePresent ? '无效，请刷新或归零' : '未设置，保留继承' : display(reading.legacy.override)}。</p>
    <p className="muted">旧版右侧控制点列表含非面部椭圆点和嘴唇点，属于历史错误拓扑；仍按旧配方保留原行为与原数值含义，仅用于已保存作品的外观兼容，不代表与新版同等正确。新版使用真实椭圆轮廓和新的强度标尺，不保证与旧版同值同效果，也不会自动换算。进入此面板不会修改或升级旧效果。</p>
    {access.legacyActive === true && <>
      <ReplacementChoice key={`${binding}:${access.writeLinked}`} linked={access.writeLinked}
        disabled={access.replacementDisabled} onReplace={replaceLegacy}/>
      {access.replacementReason && <p className="muted" role="status">{access.replacementReason}</p>}
      <p className="muted">替换仅在当前范围写入旧版 0 和你选择的新版左右值，不删除历史、不改变联动继承，也不清除其他范围覆盖。若其他范围仍令同一人脸的新旧效果或独立轮廓同时生效，引擎会拒绝整个请求。</p>
    </>}
    <details>
      <summary>保留并调整旧版瘦脸（历史错误拓扑，兼容保留）</summary>
      <p className="muted">这是历史效果编辑入口，不是新版瘦脸；没有左右独立控制，不会把旧配方改写为新版。经典、幼态、英气三个脸型预设也仍是历史预设，数值与原行为保留。</p>
      {reading.legacy.value !== null && <Slider key={`${binding}:legacy`} label="旧版瘦脸（历史错误拓扑）"
        value={reading.legacy.value * 100} min={-100} max={100} disabled={access.legacyChangeDisabled}
        title={access.legacyReason ?? '保留历史配方含义，不与新版瘦脸同时启用。'}
        onChange={value => commitLegacy(value / 100)} onReset={() => commitLegacy(0)}/>}
      {access.legacyReason && <p className="muted" role="status">{access.legacyReason}</p>}
      <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={() => commitLegacy(0)}>
        仅归零当前范围的旧版瘦脸
      </button>
    </details>
    <p className="muted">新版瘦脸不能与非零旧版瘦脸或非零太阳穴、颧骨、下颌独立轮廓叠加。归零不需要核心、有效读数或可用分析，但仍须当前来源和编辑范围有效、原请求与其他修改已确认。归零不是恢复继承，也不会清除其他范围的效果。</p>
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view?.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id) ?? -1;
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
    <p className="muted">这是可见二维局部变形，不是 AI 重建、3D 塑颜或骨骼矫正。轮廓外的邻近背景过渡带可能移动，不能保证背景完全不动；遮挡、截断、过度侧转或邻近其他人脸的区域可能被拒绝。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是手册规定；负值向外扩展也是本产品扩展，不宣称官方同等行为。核心就绪不证明每个人脸和每一侧都可用，也不代表照片质量合格。真实照片、交互与预览导出一致性验收尚未运行，面部重塑功能族仍未完整验收。</p>
  </section>;
}
