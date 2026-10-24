// SPDX-License-Identifier: GPL-3.0-or-later
import {useRef, type ComponentType} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {SkinBodyPanel} from '../skinColour/SkinBodyPanel';
import {skinBodyAttached, skinBodyReport} from '../skinColour/bodyReviewModel';
import {SKIN_FINISH_CONTROL_IDS, SKIN_FINISH_KEYS, SKIN_FINISH_LABELS, skinFinishAccess, skinFinishBindingKey,
  skinFinishPatch, type SkinFinishCapability, type SkinFinishKey} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};

/** Existing people owner remains the only scalar mutation, receipt and undo owner. */
export function SkinFinishControl({control, people, capability, blocked, faceOk, faceWhy, note, Slider}: {
  control: SkinFinishKey; people: PeopleOwner; capability?: SkinFinishCapability | null;
  blocked: boolean; faceOk: boolean; faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view = people.value, binding = skinFinishBindingKey(view);
  const access = skinFinishAccess(view, control, capability, {enabled: people.enabled,
    pending: people.state.pending, uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access}); current.current = {binding, access};
  const {reading} = access, label = SKIN_FINISH_LABELS[control];
  const attached = skinBodyAttached(view, 'skin_finish'), report = skinBodyReport(view, 'skin_finish');
  function commit(value: number) {
    if (current.current.binding !== binding
      || (value === 0 ? current.current.access.resetDisabled : current.current.access.changeDisabled)) return;
    try {people.patch([skinFinishPatch(control, value)]);} catch (error) {note(String(error));}
  }
  function resetBoth() {
    if (current.current.binding !== binding || current.current.access.resetDisabled) return;
    try {people.patch(SKIN_FINISH_KEYS.map(key => skinFinishPatch(key, 0)));} catch (error) {note(String(error));}
  }
  const refusals = view?.refusals?.filter(refusal => refusal.face_instance_id === view.selected_face_id) ?? [];
  return <section data-control-id={SKIN_FINISH_CONTROL_IDS[control]} aria-label={label}>
    <p>{control === 'whitening'
      ? '美白在已确认的皮肤范围内提亮并向冷白方向调整，不是全图曝光或单独色温替代。效果由你手动选择，不表示更白的肤色更健康或更优。'
      : '红润在已确认的皮肤范围内增加红润外观，不是局部腮红绘制，也不推断疾病、血液循环或健康程度。'}</p>
    <p className="muted">{attached === true ? report?.needs_review === false
      ? '当前使用真实面部皮肤及本功能独立审核的可见身体皮肤，不是自动全身选择。'
      : '本功能的身体范围仍保留，但有效性待核验或需要重新审核，不能视为可用。'
      : attached === false ? '目前仅调整已测得的面部皮肤，不覆盖全身皮肤。'
      : '当前人物的本功能身体范围状态尚未取得，不会默认采用色温色调的身体范围。'}这是手动强度调整与手动辅助身体扩展；尚非手册全身自动化体验的完整实现。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。下方显示所选人脸的实际有效值，不代表所有人物或共享默认值。</p>}
    {reading.value !== null && <>
      <div className="prow" aria-hidden="true"><span>0 无效果</span><span>{control === 'whitening' ? '更亮、更偏冷白' : '增加红润'}</span></div>
      <Slider key={`${binding}:${control}`} label={label} value={Math.round(reading.value * 100)} min={0} max={100}
        disabled={access.changeDisabled} title={access.reason ?? `${label}手动强度；仅作用于此功能当前有效的皮肤范围。`}
        onChange={value => commit(value / 100)} onReset={() => commit(0)}/>
      {reading.source && <p className="muted">有效值来源：{sourceLabel(reading.source)}。</p>}
    </>}
    {view && <p className="muted">此编辑范围的本项设置：{reading.override === null
      ? reading.overridePresent ? '显式值无效，请刷新或归零' : '未设显式值，保留继承'
      : `${Math.round(reading.override * 100)}`}。归零写入此范围的中性覆盖，不会清除其他参数或恢复继承。</p>}
    <button type="button" className="specBtn" disabled={access.resetDisabled}
      title={`只将当前编辑范围的${label}设为 0；核心不可用时仍可归零，不清除其他人物覆盖或身体范围。`}
      onClick={() => commit(0)}>归零当前范围的{label}</button>
    {!access.core.available && <><button type="button" className="specBtn" disabled={access.resetDisabled}
      title="同一人物请求将本范围的美白、红润同时设为 0；不会触碰色温、色调、曝光、腮红或其他人物覆盖。"
      onClick={resetBoth}>同时归零当前范围的美白与红润</button>
      <p className="muted">若其他范围仍保留非中性参数，引擎可能继续拒绝；不会替你清除它们。</p></>}
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    {refusals.map((refusal, index) => <p key={`${refusal.reason}:${index}`} role="status">{refusal.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn"
      onClick={() => void people.check().catch(error => note(String(error)))}>查询原请求结果（不重发修改）</button>}
    <p className="muted">面部需要当前有效来源图像的真实面部皮肤语义分割及 478 点人脸分析。核心就绪不等于此脸可用；缺少证据会拒绝，不用全图肤色键或脸框冒充皮肤。遮挡、肤色与边缘效果仍需真实照片验证。显示 0 至 100 对应内部 0 至 1，是本产品量程，不是手册规定。皮肤功能族仍未完整验收。</p>
    {control === 'whitening' && <SkinBodyPanel family="skin_finish" people={people} blocked={blocked} coreAvailable={access.core.available}/>}
  </section>;
}
