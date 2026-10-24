// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {sourceLabel, targetLabel, type PeopleAction} from '../people/model';
import {FaceDecorationSupportEditor} from './FaceDecorationSupportEditor';
import {OP, CONTROL_ID, PATTERNS, access, bindingKey, canonical, command, patches, referenceCurrent,
  type Capability, type Recipe} from './model';
import './faceDecoration.css';
/** Canonical people queue owns mutation, uncertain receipts, history and neutral state. */
export function FaceDecorationPanel({people, capability, blocked, faceOk, faceWhy}: {
  people: PeopleOwner; capability?: Capability | null; blocked: boolean; faceOk: boolean; faceWhy?: string;
}) {
  const view = people.value, report = view?.face_decoration, binding = bindingKey(view);
  const state = access(view, capability, {enabled: people.enabled, pending: people.state.pending,
    uncertain: people.state.uncertain, blocked, faceOk, faceWhy});
  const [error, setError] = useState(''), [reference, setReference] = useState<{request: PeopleAction; binding: string} | null>(null);
  const activeReference = useRef(reference); activeReference.current = reference;
  const mounted = useRef(false), opening = useRef(false), serial = useRef(0);
  const releasedRequestId = people.state.faceDecorationReleasedRequestId;
  const current = useRef({binding, state, view, releasedRequestId}); current.current = {binding, state, view, releasedRequestId};
  useLayoutEffect(() => {mounted.current = true; return () => {mounted.current = false; serial.current += 1;};}, []);
  useLayoutEffect(() => {serial.current += 1; setReference(null); setError('');}, [binding]);
  useLayoutEffect(() => {
    if (reference && people.state.faceDecorationReleasedRequestId === reference.request.request_id) {
      serial.current += 1; setReference(null); setError('');
    }
  }, [people.state.faceDecorationReleasedRequestId, reference]);
  const actualReference = !!reference && releasedRequestId !== reference.request.request_id && reference.binding === binding && referenceCurrent(reference.request, view);
  function commit(value: Recipe, keys: ('pattern' | 'strength')[]) {
    const latest = current.current;
    const isReset = keys.length === 1 && keys[0] === 'strength' && value.strength === 0;
    const locked = isReset ? latest.state.resetDisabled : keys[0] === 'pattern' ? latest.state.patternDisabled : latest.state.changeDisabled;
    if (!mounted.current || latest.binding !== binding || locked) return;
    try {serial.current += 1; setReference(null); people.patch(patches(value, keys)); setError('');}
    catch (cause) {setError(String(cause));}
  }
  async function openReference() {
    if (!mounted.current || opening.current || current.current.binding !== binding || current.current.state.reviewDisabled || !view) return;
    const request = command(view, 'face_decoration_reference', crypto.randomUUID(), {}), sequence = ++serial.current;
    opening.current = true; setReference({request, binding}); setError('');
    try {await people.submitCaptured(request);}
    catch (cause) {if (mounted.current && current.current.binding === binding && serial.current === sequence) setError(String(cause));}
    finally {opening.current = false;}
  }
  const recipe = state.recipe;
  const selected = view?.faces.find(face => face.face_ref.face_instance_id === view.selected_face_id);
  const refusals = view?.refusals?.filter(row => row.face_instance_id === view.selected_face_id) ?? [];
  return <section className="faceDecoration" aria-label="脸部装饰" data-control-id={CONTROL_ID}>
    <p>5 款原创雀斑、3 款原创点痣，以程序图案添加装饰，不是 AI 换妆、去瑕疵或妆容减淡。图案与命名为本产品原创；左右指图像左右。</p>
    {view && <p>写入范围：{targetLabel(view)}。下方显示所选人脸实际有效值，不代表共享默认值。只修改你调整的项目。</p>}
    <div className="decorationCatalogue" role="group" aria-label="脸部装饰图案（5 雀斑、3 点痣）">
      {PATTERNS.map(pattern => <button type="button" key={pattern.id} disabled={state.patternDisabled}
        aria-pressed={recipe?.pattern === pattern.id} aria-label={`${pattern.label}，${pattern.kind === 'freckle' ? '雀斑' : '点痣'}图案示意`}
        onClick={() => {if (recipe) commit({...recipe, pattern: pattern.id}, ['pattern']);}}>
        <svg viewBox="-1.1 -0.9 2.2 1.8" aria-hidden="true">{pattern.marks.map((mark, index) =>
          <ellipse key={index} cx={mark[0]} cy={mark[1]} rx={mark[2]} ry={mark[3]} transform={`rotate(${mark[4] * 180 / Math.PI} ${mark[0]} ${mark[1]})`} fill="currentColor" opacity={mark[5]}/>)}</svg>
        <span>{pattern.label}</span><small>图案示意</small>
      </button>)}
    </div>
    <small>以上仅为原始图案排布示意，不是人物效果图。实际随本人关键点、皮肤支持与审核范围定位及裁切，请使用主画面的原图对比核对真实效果。</small>
    {recipe && <label>装饰程度 <output>{Math.round(recipe.strength * 100)} / 100</output>
      <input key={binding} type="range" min={0} max={100} step={1} value={Math.round(recipe.strength * 100)} aria-label="脸部装饰程度" disabled={state.changeDisabled}
        onChange={e => commit({...recipe, strength: Number(e.currentTarget.value) / 100}, ['strength'])}/>
    </label>}
    <button type="button" disabled={state.resetDisabled} onClick={() => commit({version: 1, pattern: recipe?.pattern ?? 'freckle_dust', strength: 0}, ['strength'])}>归零当前范围的装饰程度</button>
    <small>0 不添加装饰。归零只写入当前范围的程度，不改图案、不删除审核、不恢复继承，也不清除其他范围。0–100 对应内部 0–1，是本产品量程，不是手册公布的数值范围。</small>
    {view && <details><summary>当前范围与有效参数来源</summary>
      {(['pattern', 'strength'] as const).map(key => {
        const own = view.editing_overrides[OP]?.[`/${key}`], from = view.resolved?.operations[OP]?.[`/${key}`];
        return <p key={key}>{key === 'pattern' ? '图案' : '程度'}：当前范围{own === undefined ? '未设置覆盖，保留继承' : `显式值 ${String(own)}`}；有效值来源：{from ? sourceLabel(from) : '尚未获得匹配读数'}。</p>;
      })}
    </details>}
    <button type="button" disabled={state.reviewDisabled || opening.current} onClick={() => void openReference()}>{report?.reviewed ? '重新审核此人物装饰范围' : '读取原图并审核装饰范围'}</button>
    {view?.editing_target?.scope !== 'face' && <p>皮肤范围审核需要在人物栏切换为当前人物独立编辑；参数仍按你明确选择的范围保存，每个受影响人物都必须有自己的审核。</p>}
    {reference && !actualReference && <p role="status">等待与本次请求、当前来源和人物完全匹配的原图参考；未提供可审核图像。</p>}
    {actualReference && reference && report && selected && <FaceDecorationSupportEditor key={`${reference.request.request_id}:${binding}`} report={report} faceBox={selected.box}
      disabled={state.reviewDisabled || people.state.pending || people.state.uncertain} onReview={async region => {
        const latest = current.current;
        if (!mounted.current || activeReference.current !== reference || latest.releasedRequestId === reference.request.request_id || latest.binding !== binding || latest.state.reviewDisabled || !referenceCurrent(reference.request, latest.view))
          throw Error('来源、人物、编辑范围或分析已变化，请重新读取并审核。');
        const proof = latest.view!.face_decoration!.reference_proof!;
        if (canonical(proof) !== canonical(report.reference_proof)) throw Error('原图参考证明已变化，请重新审核。');
        const request: PeopleAction = {...reference.request, request_id: crypto.randomUUID(), action: 'face_decoration_review',
          payload: {region, reference_proof: structuredClone(proof)}};
        await people.submitCaptured(request);
        if (mounted.current && current.current.binding === binding) setReference(null);
      }}/>}
    {reference && <button type="button" onClick={() => {serial.current += 1; setReference(null); setError('');}}>关闭审核（不取消已提交请求）</button>}
    {state.reason && <p role="status">{state.reason}</p>}
    {report?.suspended && report.suspended !== state.reason && <p role="status">{report.suspended}</p>}
    {report?.facts.reason === 'no_measurable_change' && <p role="status">当前图案与程度未产生可测量变化，不能把非零数值当作效果已完成。</p>}
    {report?.facts.limitation && <p>{report.facts.limitation}</p>}
    {refusals.map((row, index) => <p key={index} role="status">{row.reason}</p>)}
    {people.state.message && <p role="status">{people.state.message}</p>}
    {people.state.uncertain && <button type="button" onClick={() => void people.check().catch(cause => setError(String(cause)))}>查询原请求结果（不重发）</button>}
    {error && error !== people.state.message && <p role="alert">{error}</p>}
    <small>手绘审核不等于自动分割或效果验收；核心就绪也不代表此脸可用。当前实现面向 RGB SDR，不宣称 HDR 支持。严重侧脸、遮挡或分辨率不足时拒绝；不补绘不可见皮肤。预设和批量仅携带图案与程度，目标逐图、逐人物独立审核，不复制源图像素或笔迹。真实照片与安装版效果验收尚未运行。</small>
  </section>;
}
