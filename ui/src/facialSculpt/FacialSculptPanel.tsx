// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState} from 'react';
import {sourceLabel, targetLabel} from '../people/model';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {FacialSculptSupportEditor} from './FacialSculptSupportEditor';
import {OP, KEYS, CONTROL_IDS, access, bindingKey, canonical, command, patch, parseChoice, referenceCurrent,
  type Key, type View, type Capability, type Action} from './model';
import './facialSculpt.css';
const LABEL = {highlight: '高光立体', shadow: '阴影立体'};
function Choice({name, disabled, onApply}: {name: Key; disabled: boolean; onApply: (amount: number) => void}) {
  const [text, setText] = useState(''), amount = parseChoice(text);
  return <div data-control-id={CONTROL_IDS[name]}>
    <label>{LABEL[name]}新强度（0–100）<input type="number" min={0} max={100} step={1} value={text}
      onChange={e => setText(e.currentTarget.value)} disabled={disabled}/></label>
    <button type="button" disabled={disabled || amount === null} onClick={() => {if (amount !== null) onApply(amount);}}>应用这项强度</button>
  </div>;
}
/** The canonical people owner alone submits, queries uncertain outcomes and owns history. */
export function FacialSculptPanel({people, capability, blocked, faceOk, faceWhy, note, control}: {
  people: PeopleOwner; capability?: Capability | null; blocked: boolean; faceOk: boolean;
  faceWhy?: string; control?: Key; note?: (message: string) => void;
}) {
  const view = people.value as View | null, report = view?.facial_sculpt;
  // Callback wrappers are recreated by usePeopleWorkflow. Only canonical
  // document/source/target revisions own this review, never function identity.
  const binding = bindingKey(view);
  const state = access(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, blocked, faceOk, faceWhy});
  const [error, setError] = useState(''), [reference, setReference] = useState<{request: Action; binding: string} | null>(null);
  const alive = useRef(false), busy = useRef(false), generation = useRef(0);
  const current = useRef({binding, state, view, reference, patch: people.patch, submit: people.submitCaptured});
  current.current = {binding, state, view, reference, patch: people.patch, submit: people.submitCaptured};
  useLayoutEffect(() => {alive.current = true; return () => {alive.current = false; generation.current++;};}, []);
  useLayoutEffect(() => {generation.current++; setReference(null); setError('');}, [binding]);
  useLayoutEffect(() => {if (!people.state.pending && !people.state.uncertain) busy.current = false;}, [binding, people.state]);
  useLayoutEffect(() => {
    if (reference && people.state.facialSculptReleasedRequestId === reference.request.request_id) {
      generation.current++; setReference(null); busy.current = false;
    }
  }, [people.state.facialSculptReleasedRequestId, reference]);
  const valid = () => alive.current && current.current.binding === binding;
  function fail(cause: unknown) {if (valid()) {setError(String(cause)); note?.(String(cause));}}
  function commit(key: Key, amount: number) {
    if (!valid() || busy.current || (amount === 0 ? current.current.state.resetDisabled : current.current.state.changeDisabled)) return;
    busy.current = true; generation.current++; setReference(null);
    try {current.current.patch([patch(key, amount)]); setError('');} catch (cause) {busy.current = false; fail(cause);}
  }
  async function openReference() {
    if (!valid() || busy.current || current.current.state.reviewDisabled || !view) return;
    const request = command(view, 'facial_sculpt_reference', crypto.randomUUID(), {}), serial = ++generation.current;
    busy.current = true; setReference({request, binding}); setError('');
    try {await current.current.submit(request);}
    catch (cause) {if (serial === generation.current) fail(cause);}
    finally {if (serial === generation.current) busy.current = false;}
  }
  const actualReference = !!reference && reference.binding === binding && referenceCurrent(reference.request, view);
  const selected = view?.faces.find(f => f.face_ref.face_instance_id === view.selected_face_id);
  return <section className="facialSculpt" aria-label="高光与阴影立体">
    <p>分别加强原片已有的宽尺度面部明暗结构：高光立体增强已有亮部，阴影立体加深已有暗部。不会生成新的光源、恢复过曝细节、改变脸型或重建三维。</p>
    <p>范围限于已测量的额头中央、鼻梁与鼻头、面中、下巴；还要同时通过真实皮肤观察、眼眉唇与其他人物保护，以及本工具独立的可见皮肤审核。</p>
    {view && <p>写入范围：{targetLabel(view)}。下面的有效数值只代表当前所选人物，不会复制给共享范围；每次只写你明确输入的一项。</p>}
    {(control ? [control] : KEYS).map(key => <div key={key}>
      <p>{LABEL[key]}实际有效值：{state.recipe ? Math.round(state.recipe[key]*100) : '未获得有效读数'}。
        当前范围显式值：{view?.editing_overrides[OP]?.[`/${key}`] === undefined ? '未设置，保留继承' : String(view.editing_overrides[OP][`/${key}`])}。
        参数来源：{view?.resolved?.operations[OP]?.[`/${key}`] ? sourceLabel(view.resolved.operations[OP][`/${key}`]) : '待确认'}。</p>
      {(() => {
        const own = view?.editing_overrides[OP]?.[`/${key}`];
        const value = view?.editing_target?.scope === 'face' ? state.recipe?.[key] : own;
        return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
          ? <label>{LABEL[key]}<input type="range" min={0} max={100} step={1} value={value*100}
              disabled={state.changeDisabled} onChange={event => commit(key, Number(event.currentTarget.value)/100)}/>
              <output>{Math.round(value*100)} / 100</output></label> : null;
      })()}
      <Choice key={`${binding}:${key}`} name={key} disabled={state.changeDisabled} onApply={amount => commit(key, amount)}/>
      <button type="button" disabled={state.resetDisabled} onClick={() => commit(key, 0)}>归零当前范围的{LABEL[key]}</button>
    </div>)}
    <p>此版本只修改当前有效来源，不跨照片同步、套用预设或批处理；若人物或分组同时影响其他照片，引擎会拒绝，不能用当前照片的审核代替。</p>
    <small>0 无效果。归零不删除审核、不恢复继承、不改其他功能。空白不是 0。0–100 是本产品强度范围，不是参考手册公布的量程。</small>
    <button type="button" disabled={state.reviewDisabled || busy.current} onClick={() => void openReference()}>读取当前来源并独立审核可见皮肤</button>
    {reference && !actualReference && <p role="status">等待本次来源与人物完全匹配的原图参考；尚不能审核。</p>}
    {actualReference && reference && report && selected && <FacialSculptSupportEditor key={`${reference.request.request_id}:${binding}`}
      report={report} faceBox={selected.box} disabled={state.reviewDisabled} onReview={async region => {
        if (!valid() || current.current.reference !== reference || current.current.state.reviewDisabled
          || !referenceCurrent(reference.request, current.current.view)) throw Error('来源、人物、范围或分析已变化，请重新读取。');
        const proof = current.current.view!.facial_sculpt!.reference_proof!;
        if (canonical(proof) !== canonical(report.reference_proof)) throw Error('参考证明改变，请重新审核。');
        const request: Action = {...reference.request, action: 'facial_sculpt_review', request_id: crypto.randomUUID(),
          payload: {region, reference_proof: structuredClone(proof)}};
        await current.current.submit(request);
        if (valid()) setReference(null);
      }}/>}
    {reference && <button type="button" onClick={() => {generation.current++; setReference(null); setError('');}}>关闭审核（不撤销已提交请求）</button>}
    {state.reason && <p role="status">{state.reason}</p>}
    {report?.facts.reason === 'no_measurable_broad_structure' && <p role="status">当前审核范围没有可测的宽尺度明暗结构；非零数值不代表产生了效果。</p>}
    {view?.refusals?.map((row, i) => <p role="status" key={`${row.face_instance_id}:${i}`}>{row.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" onClick={() => void people.check().catch(fail)}>查询原请求结果（不重发修改）</button>}
    {error && error !== people.state.message && <p role="alert">{error}</p>}
    <small>只改变宽尺度亮暗增益，不替换细节层；不是皮肤光泽的中性高光拟合，也不是磨皮或曝光。审核不等于完整遮挡分割；严重侧脸、裁切、暗噪声或支持不足时拒绝或无可测变化。仅 RGB SDR；真实照片、数值与交互验收均未运行（UNRUN）。</small>
  </section>;
}
