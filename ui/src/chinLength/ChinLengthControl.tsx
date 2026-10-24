// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import {sourceLabel, targetLabel, type ParameterPatch, type PeopleView, type ResolvedParameter} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {CHIN_LENGTH_CONTROL_ID, chinLengthAccess, chinLengthBindingKey, chinLengthPatch,
  chinLengthResetPatches, legacySmallChinPatch, parseChinLengthChoice, replaceLegacySmallChinPatches,
  type ChinLengthCapability, type ChinLengthReading} from './model';

type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
type ControlProps = {people: PeopleOwner; capability?: ChinLengthCapability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; note: (message: string) => void; Slider: ComponentType<SliderProps>};
const display = (value: number | null) => value === null ? '未提供有效读数' : String(Number((value * 100).toFixed(6)));
function provenance(view: PeopleView | null, source: ResolvedParameter) {
  const group = source.scope === 'group' ? view?.groups[source.target_id ?? ''] : undefined;
  return `${sourceLabel(source)}${group ? `「${group.label}」` : ''}`;
}
function Readings({view, label, reading}: {view: PeopleView | null; label: string; reading: ChinLengthReading}) {
  return <>
    <p className="muted">所选人脸{label}实际值：{display(reading.value)}
      {reading.source ? `，来源：${provenance(view, reading.source)}` : ''}。</p>
    <p className="muted">当前编辑范围的{label}显式值：{reading.override === null
      ? reading.overridePresent ? '无效，请明确选择新数值或归零' : '未设置，保留继承' : display(reading.override)}。</p>
  </>;
}

/** Always starts blank. No copying, conversion, sign inversion, mount write or blur write. */
function AmountChoice({label, action, changeDisabled, resetDisabled, min = -100, onChoose}: {
  label: string; action: string; changeDisabled: boolean; resetDisabled: boolean; min?: number;
  onChoose: (value: number) => void;
}) {
  const [text, setText] = useState(''), choice = parseChinLengthChoice(text);
  const disabled = choice === null || choice * 100 < min || (choice === 0 ? resetDisabled : changeDisabled);
  return <fieldset disabled={resetDisabled}>
    <legend>{label}</legend>
    <label>新数值（{min} 至 100）
      <input className="pnum" type="number" min={min} max={100} step="any" value={text}
        aria-label={`${label}新数值`} onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled}
      onClick={() => {if (!disabled && choice !== null) onChoose(choice);}}>{action}</button>
    <p className="muted">留空不等于 0，也不借用所选人脸的继承值。只有点击应用才写入当前范围。</p>
  </fieldset>;
}
function ReplacementChoice({disabled, onReplace}: {disabled: boolean; onReplace: (value: number) => void}) {
  const [text, setText] = useState(''), choice = parseChinLengthChoice(text);
  return <fieldset disabled={disabled}>
    <legend>明确选择新版下巴长短数值后替换旧版小下巴</legend>
    <p className="muted">这是你主动选择的新数值，不是旧参数的复制、换算或取反。输入框留空不会被当成 0；不点击替换就保留旧效果。</p>
    <label>新版下巴长短数值（-100 至 100）
      <input className="pnum" type="number" min={-100} max={100} step="any" value={text}
        aria-label="替换旧版小下巴：我选择的新版下巴长短数值" onChange={event => setText(event.target.value)}/></label>
    <button type="button" className="specBtn" disabled={disabled || choice === null}
      onClick={() => {if (!disabled && choice !== null) onReplace(choice);}}
      title="同一人物修改请求只将当前范围的旧版 small_chin 写为 0，并写入我选择的新版 amount。">
      一次替换：归零旧版并应用我选择的新数值
    </button>
  </fieldset>;
}

/** Wrap the existing canonical owner; never create another mutation queue, history or replay path. */
function useChinLengthOwner({people, capability, blocked, faceOk, faceWhy, note}: ControlProps) {
  const view = people.value;
  const owner = useRef({patch: people.patch, check: people.check, generation: 0});
  if (owner.current.patch !== people.patch || owner.current.check !== people.check) {
    owner.current = {patch: people.patch, check: people.check, generation: owner.current.generation + 1};
  }
  const binding = JSON.stringify([chinLengthBindingKey(view), owner.current.generation]);
  const access = chinLengthAccess(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, externalBusy: blocked, faceOk, faceWhy});
  const current = useRef({binding, access, patch: people.patch, check: people.check});
  current.current = {binding, access, patch: people.patch, check: people.check};
  const mounted = useRef(false), submitted = useRef(false);
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useLayoutEffect(() => {
    if (!people.state.pending && !people.state.uncertain) submitted.current = false;
  // Owner snapshot also observes confirmed fast failures with batched pending transitions.
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
    try {dispatch([chinLengthPatch(value)]);} catch (error) {note(String(error));}
  }
  function resetNew() {
    if (!stillCurrent() || current.current.access.resetDisabled) return;
    dispatch(chinLengthResetPatches());
  }
  function commitLegacy(value: number) {
    if (!stillCurrent() || (value === 0 ? current.current.access.resetDisabled : current.current.access.legacyChangeDisabled)) return;
    try {dispatch([legacySmallChinPatch(value)]);} catch (error) {note(String(error));}
  }
  function replaceLegacy(value: number) {
    if (!stillCurrent() || current.current.access.replacementDisabled) return;
    try {dispatch(replaceLegacySmallChinPatches(value));} catch (error) {note(String(error));}
  }
  function checkOriginal() {
    if (!stillCurrent()) return;
    void people.check().catch(error => {if (stillCurrent()) note(String(error));});
  }
  return {view, binding, access, commit, resetNew, commitLegacy, replaceLegacy, checkOriginal};
}
function OwnerStatus({people, checkOriginal}: {people: PeopleOwner; checkOriginal: () => void}) {
  const view = people.value;
  return <>
    {!!view?.refusals?.length && <p className="muted">引擎当前人物拒绝信息（可能包含其他功能；以下保留引擎原始原因）：</p>}
    {view?.refusals?.map((refusal, index) => {
      const faceIndex = view.faces.findIndex(face => face.face_ref.face_instance_id === refusal.face_instance_id);
      return <p key={`${refusal.face_instance_id}:${index}`} role="status">{faceIndex >= 0 ? `人物 ${faceIndex + 1}` : '引擎报告的人物'}：{refusal.reason}</p>;
    })}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" className="specBtn" onClick={checkOriginal}>查询原请求结果（不重发修改）</button>}
  </>;
}

export function ChinLengthControl(props: ControlProps) {
  const {Slider, people} = props;
  const {view, binding, access, commit, resetNew, replaceLegacy, checkOriginal} = useChinLengthOwner(props);
  return <section data-control-id={CHIN_LENGTH_CONTROL_ID} aria-label="下巴长短（嘴唇下方局部纵向长度）">
    <p>下巴长短调整全部嘴唇顶点下方至下巴尖区域的局部纵向长度。正值拉长，负值缩短，0 无效果；不是旧版小下巴（收下巴）、下庭、中庭、小脸或尖下巴的别名。</p>
    <p className="muted">使用当前有效来源图像（原图或已返回合成图）的真实分析，以全部 40 个嘴唇顶点下方的边界和下巴尖 152 测量每个人自己的支撑。这里是来源图像上的代理区域，不是临床解剖测量；界面不捏造长度或可见性读数。</p>
    <p className="muted">本次新增映射在实测头部坐标系中只沿局部纵向平滑移动，保持局部横向坐标及唇部边界以上不动。头部倾斜时画面横坐标仍可能改变；先前编辑可能已把像素移入过渡带，因此不承诺最终叠加结果的嘴唇或上半脸完全不变。</p>
    <p className="muted">引擎使用来源皮肤、图像与排除区域检查下巴支撑，不新增分割或补造遮挡、截断、画面外的部位。邻近颈部、背景与边缘过渡带可能移动；侧转、倾斜、遮挡、裁切和邻近其他人脸都可能导致拒绝。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。所选人脸的实际值与来源只代表此脸，不代表共享范围内每个人；每个目标必须通过自己的来源、支撑与组合检查。</p>}
    <Readings view={view} label="新版下巴长短" reading={access.reading.amount}/>
    {access.editValue !== null ? <>
      <div className="prow" aria-hidden="true"><span>缩短下巴</span><span>0 无效果</span><span>拉长下巴</span></div>
      <Slider key={`${binding}:amount`} label="下巴长短 · 当前范围的纵向长度" value={access.editValue * 100}
        min={-100} max={100} disabled={access.changeDisabled} title={access.reason ?? '负值缩短下巴，正值拉长下巴；不改变旧版配方。'}
        onChange={value => commit(value / 100)} onReset={resetNew}/>
    </> : <AmountChoice key={`${binding}:choice`} label="为当前范围明确选择下巴长短" action="应用我选择的下巴长短"
      changeDisabled={access.changeDisabled} resetDisabled={access.resetDisabled} onChoose={commit}/>}
    <p className="muted">独立人脸可从此脸实际值调整；共享范围仅使用该范围的显式值或你输入的新数值，不把所选人脸的继承参数复制给其他人物。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={resetNew}
      title="只将当前范围的 lnx.chin_length.v1 /amount 写为 0，不改变旧版 small_chin 或其他效果。">仅归零当前范围的新版下巴长短</button>
    <p className="muted">新版归零保留旧版效果，不恢复继承，不清除其他范围或其他功能。缺少核心、有效读数或面部分析时仍可归零，但照片、编辑范围、原请求和其他修改必须已确认。</p>
    {access.reason && <p className="muted" role="status">{access.reason}</p>}
    <Readings view={view} label="旧版小下巴" reading={access.reading.legacy}/>
    <p className="muted">旧版小下巴使用历史错误拓扑，其中 54 和 314 并不是一对下颌支撑点；保留原行为与原数值仅用于旧作品兼容，不代表与新版同等正确。新版不会复制、换算、取反或自动重置旧数值；打开面板或将新版设为 0 都不会改变旧效果。</p>
    {access.replacementNeeded && <>
      <ReplacementChoice key={`${binding}:replacement`} disabled={access.replacementDisabled} onReplace={replaceLegacy}/>
      {access.replacementReason && <p className="muted" role="status">{access.replacementReason}</p>}
      <p className="muted">替换是同一事务写入当前范围的旧版 0 与你选择的新版 amount，不删除历史，不清除其他范围覆盖。所选脸的旧版值可能为 0 而共享范围仍有非零显式设置；两个读数分开显示。若任一目标最终仍同时生效非零新旧效果，引擎拒绝整个请求，不先清旧再试新版。</p>
    </>}
    <p className="muted">新旧非零效果不可叠加。需要保留或单独编辑旧效果时，请使用原来的「收下巴」入口；历史脸型预设也保留旧配方，遇到新旧冲突时拒绝，不自动替换。</p>
    <OwnerStatus people={people} checkOriginal={checkOriginal}/>
    <p className="muted">已有几何、手动液化兼容性与最终共享范围结果由引擎检查。核心就绪不是此脸支撑可用、遮挡安全或质量验收的证明；这是二维局部形变，不是 AI 重建、3D 塑颜、骨骼矫正或医学测量。</p>
    <p className="muted">显示 -100 至 100 对应内部 -1 至 1，是本产品量程，不是官方标定。最大局部纵向增益采用原始唇下边界至下巴尖间距的 0.08 倍，侧缘和颈部平滑衔接，不是整个下巴均匀缩放。真实照片、正负方向、原子替换、共享范围、边缘背景、历史回放、预览导出一致性与交互验收均未运行（UNRUN），面部重塑功能族仍未完整验收。</p>
  </section>;
}

/** The original 收下巴 route keeps its old operation and positive slider, with truthful managed reads. */
export function LegacySmallChinControl(props: ControlProps) {
  const {Slider, people} = props;
  const {view, binding, access, commitLegacy, checkOriginal} = useChinLengthOwner(props);
  return <section aria-label="小下巴（旧版收下巴兼容编辑）">
    <p className="muted">这是原有小下巴（收下巴）入口，保留历史错误拓扑与旧数值含义，不是新版下巴长短。不会自动迁移或替换旧效果。</p>
    {view && <p className="muted">写入范围：{targetLabel(view)}。实际值只代表所选脸；共享范围的显式值另行显示。</p>}
    <Readings view={view} label="旧版小下巴" reading={access.reading.legacy}/>
    {access.legacyEditValue !== null && access.legacyEditValue >= 0
      ? <Slider key={`${binding}:legacy`} label="小下巴" value={access.legacyEditValue * 100} min={0} max={100}
          disabled={access.legacyChangeDisabled} title={access.legacyReason ?? '保留历史数值与原行为，不与新版下巴长短同时启用。'}
          onChange={value => commitLegacy(value / 100)} onReset={() => commitLegacy(0)}/>
      : <AmountChoice key={`${binding}:legacy-choice`} label="为当前范围明确选择旧版小下巴" action="应用旧版小下巴数值"
          min={0} changeDisabled={access.legacyChangeDisabled} resetDisabled={access.resetDisabled} onChoose={commitLegacy}/>}
    <p className="muted">共享范围不从某一张脸的继承值预填；没有有效读数时不显示假 0。已保存的负值仍原样保留，上方实际读数不会被滑杆量程改写。</p>
    <button type="button" className="specBtn" disabled={access.resetDisabled} onClick={() => commitLegacy(0)}>
      仅归零当前范围的旧版小下巴
    </button>
    {access.legacyReason && <p className="muted" role="status">{access.legacyReason}</p>}
    <OwnerStatus people={people} checkOriginal={checkOriginal}/>
  </section>;
}
