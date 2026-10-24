// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect, useRef, useState, type ComponentType} from 'react';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
import {sourceLabel, type ParameterPatch, type PeopleAction} from '../people/model';
import {EyeMakeupEnhanceSupportEditor} from './EyeMakeupEnhanceSupportEditor';
import {OP, CONTROLS, CONTROL_IDS, LABELS, SIDES, access, adjustPatches, bindingKey, canonical, command, linkPatches,
  parseChoice, referenceCurrent, resetPatches, unlockPatch, zeroSidePatches, type Capability, type Control, type Side, type View} from './model';
type SliderProps = {label: string; value: number; min: number; max: number; disabled?: boolean; title?: string;
  onChange: (value: number) => void; onReset: () => void};
function LinkChoice({control, disabled, allowed, onChoose}: {control: Control; disabled: boolean;
  allowed: (value: number) => boolean; onChoose: (value: number) => void}) {
  const [text,setText]=useState(''),value=parseChoice(text);
  return <fieldset disabled={disabled}><legend>明确选择左右共同数值后联动</legend>
    <input aria-label={`${LABELS[control]}共同数值`} type="number" min={-100} max={100} step="any" value={text} onChange={e=>setText(e.target.value)}/>
    <button type="button" disabled={value===null||!allowed(value)} onClick={()=>{if(value!==null&&allowed(value))onChoose(value);}}>同时设定两侧并联动</button>
    <small>留空不是 0，不会把任何一侧的继承数值复制或平均到另一侧。</small>
  </fieldset>;
}
/** Four controls, each with its own bilateral link intent. Existing owner owns all receipts/history. */
export function EyeMakeupEnhanceControl({people,capability,blocked,faceOk,faceWhy,note,Slider}: {
  people: PeopleOwner; capability?: Capability | null; blocked: boolean; faceOk: boolean; faceWhy?: string;
  note: (message: string) => void; Slider: ComponentType<SliderProps>;
}) {
  const view=people.value as View|null,report=view?.eye_makeup_enhance,binding=bindingKey(view);
  const state=access(view,capability,{enabled:people.enabled,pending:people.state.pending,uncertain:people.state.uncertain,blocked,faceOk,faceWhy});
  const [reference,setReference]=useState<{request:PeopleAction;binding:string}|null>(null),[error,setError]=useState('');
  const alive=useRef(false),opening=useRef(false),submitted=useRef(false),serial=useRef(0);
  const activeReference=useRef(reference);activeReference.current=reference;
  const releasedRequestId=people.state.eyeMakeupEnhanceReleasedRequestId;
  // Owner functions are fresh wrappers on render. Never mistake their identity
  // for a source/revision change; use the latest callbacks with exact data fences.
  const current=useRef({view,state,binding,releasedRequestId,patch:people.patch,submit:people.submitCaptured,check:people.check});
  current.current={view,state,binding,releasedRequestId,patch:people.patch,submit:people.submitCaptured,check:people.check};
  useLayoutEffect(()=>{alive.current=true;return()=>{alive.current=false;serial.current+=1;};},[]);
  useLayoutEffect(()=>{serial.current+=1;setReference(null);setError('');},[binding]);
  useLayoutEffect(()=>{
    if(reference&&releasedRequestId===reference.request.request_id){
      serial.current+=1;activeReference.current=null;setReference(null);setError('');
    }
  },[releasedRequestId,reference]);
  useLayoutEffect(()=>{if(!people.state.pending&&!people.state.uncertain)submitted.current=false;},[binding,people.state]);
  const stillCurrent=()=>alive.current&&current.current.binding===binding;
  function dispatch(patches:ParameterPatch[],allowed:boolean) {
    if(!stillCurrent()||!allowed||submitted.current)return;
    submitted.current=true;serial.current+=1;setReference(null);
    try {current.current.patch(patches);setError('');}catch(cause){submitted.current=false;setError(String(cause));note(String(cause));}
  }
  function adjust(control:Control,side:Side,value:number) {
    const r=current.current.state.recipe;if(!r)return;
    dispatch(adjustPatches(control,side,value,r[control].linked),current.current.state.permitted(control,side,value,r[control].linked));
  }
  async function openReference() {
    const latest=current.current;
    if(!stillCurrent()||opening.current||latest.state.reviewDisabled||!latest.view)return;
    const request=command(latest.view,'eye_makeup_enhance_reference',crypto.randomUUID(),{}),sequence=++serial.current;
    opening.current=true;setReference({request,binding});setError('');
    try {await latest.submit(request);}catch(cause){if(stillCurrent()&&serial.current===sequence)setError(String(cause));}
    finally {opening.current=false;}
  }
  // A known released read is never reusable authority, even if refreshing the
  // document failed and left the old proof in view. Fence render before effects.
  const actualReference=!!reference&&releasedRequestId!==reference.request.request_id&&reference.binding===binding&&referenceCurrent(reference.request,view);
  return <section aria-label="原有眼妆增强（人物左右独立）" data-control-id={CONTROL_IDS.amount}>
    <p>只调整原图中确实可见的眼妆，不添加美瞳、眼线、睫毛或眼神光。四项控件各自联动，左右指人物自身，不是画面左右。</p>
    {CONTROLS.map(control=>{
      const row=state.recipe?.[control];
      return <fieldset key={control} data-control-id={CONTROL_IDS[control]}><legend>{LABELS[control]}</legend>
        <p>此控件当前模式：{row?(row.linked?'左右联动':'左右独立'):'等待真实读数'}。</p>
        {row&&SIDES.map(side=><div key={side}>
          <Slider label={`人物${side==='left'?'左':'右'}侧${LABELS[control]}`} min={-100} max={100} value={row[side]*100}
            disabled={!state.permitted(control,side,row[side] === 0 ? .01 : row[side],row.linked)}
            title={control==='amount'?'负值减淡，正值增强；两块独立干净皮肤参考必须一致。':undefined}
            onChange={value=>adjust(control,side,value/100)} onReset={()=>adjust(control,side,0)}/>
          <button type="button" disabled={state.resetDisabled} onClick={()=>dispatch(zeroSidePatches(control,side),!current.current.state.resetDisabled)}>解除本项联动并只归零{side==='left'?'左':'右'}侧</button>
        </div>)}
        <button type="button" disabled={state.resetDisabled||!row||!row.linked} onClick={()=>dispatch([unlockPatch(control)],!current.current.state.resetDisabled)}>只解除本项左右联动</button>
        <LinkChoice key={`${binding}:${control}`} control={control} disabled={state.resetDisabled}
          allowed={value=>state.permitted(control,'left',value,true)}
          onChoose={value=>dispatch(linkPatches(control,value),current.current.state.permitted(control,'left',value,true))}/>
        <button type="button" disabled={state.resetDisabled} onClick={()=>dispatch(resetPatches(control),!current.current.state.resetDisabled)}>只归零本项两侧，保留联动状态</button>
        {view&&<details><summary>有效参数来源</summary>{(['linked',...SIDES] as const).map(field=>{
          const source=view.resolved?.operations[OP]?.[`/${control}/${field}`],own=view.editing_overrides[OP]?.[`/${control}/${field}`];
          return <p key={field}>{field}：{source?sourceLabel(source):'无匹配读数'}；此脸{own===undefined?'继承该值':`显式值 ${String(own)}`}。</p>;
        })}</details>}
      </fieldset>;
    })}
    <button type="button" disabled={state.resetDisabled} onClick={()=>dispatch(resetPatches(),!current.current.state.resetDisabled)}>归零当前人物四项眼妆控件</button>
    <p>归零不需要原生核心或可见性通过，只清零本操作数值，保留各项联动、审核及其他操作。当前入口仅支持所选人物独立范围；多个共享来源文档会明确拒绝，不暗中修改其他文档。</p>
    <button type="button" disabled={state.reviewDisabled||opening.current} onClick={()=>void openReference()}>{report?.reviewed?'重新读取源图并审核眼妆':'读取源图并独立审核眼妆'}</button>
    {reference&&releasedRequestId!==reference.request.request_id&&!actualReference&&<p role="status">等待本次请求、来源、人物与分析完全匹配的原图裁切。</p>}
    {actualReference&&reference&&report&&<EyeMakeupEnhanceSupportEditor key={`${binding}:${reference.request.request_id}`} report={report}
      disabled={state.reviewDisabled||people.state.pending||people.state.uncertain} onReview={async eyes=>{
        const latest=current.current;
        if(!stillCurrent()||activeReference.current!==reference||latest.releasedRequestId===reference.request.request_id||latest.state.reviewDisabled||!referenceCurrent(reference.request,latest.view))
          throw Error('审核期间人物、来源或文档已经变化，请重新读取原图。');
        const proof=latest.view!.eye_makeup_enhance!.reference_proof!;
        if(canonical(proof)!==canonical(report.reference_proof))throw Error('原图显示证明改变，请重新审核。');
        await latest.submit(command(latest.view!,'eye_makeup_enhance_review',crypto.randomUUID(),{eyes,reference_proof:structuredClone(proof)}));
        if(stillCurrent()&&activeReference.current===reference)setReference(null);
      }}/>}
    {reference&&<button type="button" onClick={()=>{serial.current+=1;setReference(null);setError('');}}>关闭审核（不取消已提交请求）</button>}
    {state.reason&&<p role="status">{state.reason}</p>}
    {report?.suspended&&report.suspended!==state.reason&&<p role="status">{report.suspended}</p>}
    {view?.refusals?.filter(r=>r.face_instance_id===view.selected_face_id).map((r,i)=><p key={i} role="status">{r.reason}</p>)}
    {people.state.message&&<p role="status">{people.state.message}</p>}
    {people.state.uncertain&&<button type="button" onClick={()=>void current.current.check().catch(cause=>{if(alive.current)setError(String(cause));})}>查询原请求结果（不重发）</button>}
    {error&&error!==people.state.message&&<p role="alert">{error}</p>}
    <small>肤色参考不是被妆容遮住的真实皮肤。减淡仅降低估计的原有妆色差，不是完整卸妆。边缘、毛孔细节、眼球、眉毛与睫毛受保护；强光、深影、侧脸、遮挡、参考不一致或尺度不足时拒绝。-100 至 100 是本产品量程，不是官方标定。真实照片、左右方向、构建、交互及预览导出一致性验收均未运行（UNRUN）。</small>
  </section>;
}
