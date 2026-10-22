import {useEffect,useState} from 'react';
import type {LocalMaskOwner} from './useLocalMaskWorkflow';
import {drawingKind,geometryDescription,MASK_LABELS,newMask,OPERATION_LABELS,type LocalMaskReport,type MaskKind,type MaskMutation,type MaskObject,type MaskOperation} from './model';
import {RangeControls} from './RangeControls';
import './localMasks.css';
import {PromptedMaskDialog} from '../promptedMasks/PromptedMaskDialog';
export function LocalMaskPanel({owner,report,onStart,blocked=false}:{owner:LocalMaskOwner;report?:LocalMaskReport;onStart:(mutation:MaskMutation|null,draw?:boolean)=>void;blocked?:boolean}){
  const {state,workflow,context,active,pending}=owner;
  const [selected,setSelected]=useState<string|null>(null),[draft,setDraft]=useState<MaskObject>(()=>newMask('brush'));
  const [aiOpen,setAiOpen]=useState(false);
  const [diameter,setDiameter]=useState(.05);
  const objects=report?.recipe?.objects??[],channels=report?.channels??[];
  const stored=objects.find(o=>o.id===selected),storedKey=JSON.stringify(stored??null);
  useEffect(()=>{setSelected(null);setDraft(newMask('brush'));},[context.documentId]);
  useEffect(()=>{if(stored)setDraft(structuredClone(stored));else if(selected){setSelected(null);setDraft(newMask('brush'));}},[storedKey]);
  useEffect(()=>{
    const request=state.request;
    if(state.phase!=='success'||!request||request.document_id!==context.documentId)return;
    const mutation=request.mutation;if(mutation.action!=='upsert')return;
    const saved=objects.find(o=>o.id===mutation.object.id);
    if(saved){setSelected(saved.id);setDraft(structuredClone(saved));}
    else{setSelected(null);setDraft(newMask(mutation.object.kind==='prompted'?'brush':mutation.object.kind,channels[0]??''));}
  },[state.phase,state.request?.request_id]);
  const locked=blocked||active||pending||!context.enabled||context.canStart===false;
  const full=draft.kind==='full';
  const patch=(value:Partial<MaskObject>)=>setDraft({...draft,...value} as MaskObject);
  const create=(kind:MaskKind)=>{setSelected(null);setDraft(newMask(kind,channels[0]??''));};
  const stage=(redraw=false)=>{
    let object=structuredClone(draft);
    if(redraw&&object.kind==='brush')object={...object,points:[],axes:[[diameter/2,0],[0,diameter/2]]};
    onStart({action:'upsert',coordinate_space:selected&&!redraw?'source':'capture',object},redraw);
  };
  const canAdd=objects.length<64&&!(draft.kind==='full'&&objects.some(o=>o.kind==='full'));
  const invalidSemantic=draft.kind==='semantic'&&!channels.includes(draft.channel);
  return <section className="localMaskPanel" aria-label="可组合局部蒙版" data-readonly-scopes>
    <strong>组合蒙版</strong>
    <small>只限制上方色相、饱和、明度与混入比例，不限制全局 LUT。几何与范围基于原始源图，不是形变后的最终画面。</small>
    <div className="localMaskToolbar">
      <button disabled={locked||objects.length>=64} onClick={()=>{setAiOpen(true);onStart(null);}}>AI 提示选区</button>
      <button disabled={locked} onClick={()=>onStart(null)}>查看已保存范围</button>
      <button disabled={locked||!objects.length||report?.bound} onClick={()=>onStart({action:'bind',enabled:true})}>用于本组调色</button>
      <button disabled={locked||!report?.bound} onClick={()=>onStart({action:'bind',enabled:false})}>恢复全图作用</button>
      <span>{report?.bound?'当前：组合蒙版':'当前：未绑定组合蒙版'}</span>
    </div>
    {report?.suspended&&<p className="localMaskWarning" role="status">已暂停：{report.suspended}。不会自动扩大到全图。</p>}
    <small>列表自上而下合成，从空蒙版开始；添加取最大值，减去扣除，交集取最小值。空列表或全部关闭时效果为零。</small>
    <ol className="localMaskList">
      {objects.map((object,index)=><li key={object.id} className={selected===object.id?'selected':''}>
        <button className="localMaskSelect" disabled={active||pending} onClick={()=>{setSelected(object.id);setDraft(structuredClone(object));}} title={geometryDescription(object)}>
          <span>{object.enabled?'●':'○'} {object.name}</span><small>{MASK_LABELS[object.kind]} · {OPERATION_LABELS[object.operation]}</small>
        </button>
        <button aria-label={`${object.name} 上移`} disabled={locked||index===0||object.kind==='full'} onClick={()=>onStart({action:'move',id:object.id,index:index-1})}>↑</button>
        <button aria-label={`${object.name} 下移`} disabled={locked||index===objects.length-1||object.kind==='full'} onClick={()=>onStart({action:'move',id:object.id,index:index+1})}>↓</button>
        <button aria-label={`删除 ${object.name}`} disabled={locked||object.kind==='full'} onClick={()=>onStart({action:'delete',id:object.id})}>删除</button>
      </li>)}
    </ol>
    {!objects.length&&<small>还没有保留的蒙版对象。</small>}
    <fieldset disabled={locked}>
      <legend>{selected?'编辑选中对象':'新建对象'}</legend>
      <label>对象类型<select value={draft.kind} onChange={e=>create(e.target.value as MaskKind)} disabled={!!selected}>
        {(Object.keys(MASK_LABELS) as MaskKind[]).filter(kind=>kind!=='prompted'||selected).map(kind=><option key={kind} value={kind} disabled={kind==='semantic'&&!channels.length}>{MASK_LABELS[kind]}</option>)}
      </select></label>
      {selected&&draft.kind==='prompted'&&<button onClick={()=>create('brush')}>新建普通对象</button>}
      {selected&&draft.kind!=='prompted'&&<button onClick={()=>create(draft.kind)}>新建同类对象</button>}
      <label>名称<input value={draft.name} maxLength={80} disabled={full&&!!selected} onChange={e=>patch({name:e.target.value})}/></label>
      <label><input type="checkbox" checked={draft.enabled} disabled={full} onChange={e=>patch({enabled:e.target.checked})}/>启用对象</label>
      <label>组合方式<select value={draft.operation} disabled={full} onChange={e=>patch({operation:e.target.value as MaskOperation})}>{(Object.keys(OPERATION_LABELS) as MaskOperation[]).map(op=><option key={op} value={op}>{OPERATION_LABELS[op]}</option>)}</select></label>
      <label>不透明度<input type="range" min="0" max="100" value={Math.round(draft.opacity*100)} disabled={full} onChange={e=>patch({opacity:Number(e.target.value)/100})}/>{Math.round(draft.opacity*100)}%</label>
      <label>羽化<input type="range" min="0" max="100" value={draft.feather} disabled={full} onChange={e=>patch({feather:Number(e.target.value)})}/>{draft.feather}</label>
      <small>羽化 0–100 映射为原图短边的 0–5%，不随屏幕缩放改变。</small>
      {draft.kind==='brush'&&<label>重绘笔刷直径（取样图短边）<input type="range" min="0.1" max="40" step="0.1" value={diameter*100} onChange={e=>setDiameter(Number(e.target.value)/100)}/>{(diameter*100).toFixed(1)}%</label>}
      <RangeControls object={draft} onChange={patch}/>
      {draft.kind==='semantic'&&<label>已分析的整图语义类别<select value={draft.channel} onChange={e=>patch({channel:e.target.value})}>
        {!channels.includes(draft.channel)&&<option value={draft.channel}>{draft.channel||'没有可用区域'}（不可用）</option>}
        {channels.map(channel=><option key={channel} value={channel}>{report?.channel_labels?.[channel]??channel}</option>)}
      </select><small>区域覆盖整张照片内该人像类别，不是单个人物、通用主体或宠物分割。仅显示模型实际可用区域；模型不匹配会暂停相关蒙版。</small></label>}
      {selected&&<small>{geometryDescription(draft)}</small>}
      {full&&<small>全图对象加入后不可隐藏、修改或删除；误加可撤销。</small>}
      <div className="localMaskToolbar">
        {drawingKind(draft.kind)&&<button disabled={(!selected&&!canAdd)||!draft.name.trim()} onClick={()=>stage(true)}>{selected?'重绘并替换几何':'在源图绘制'}</button>}
        {(selected||!drawingKind(draft.kind))&&<button disabled={invalidSemantic||(!selected&&!canAdd)||(!!selected&&full)||!draft.name.trim()} onClick={()=>stage(false)}>{selected?'审核参数修改':'审核新增对象'}</button>}
      </div>
      {selected&&drawingKind(draft.kind)&&<small>参数修改保留原有源图几何；重绘会替换选中对象的几何，不增加另一对象。</small>}
    </fieldset>
    {active&&<label><input type="checkbox" checked={state.showOverlay} onChange={e=>workflow.overlay(e.target.checked)}/>显示已保存组合范围（青色）</label>}
    {active&&<small>青色为引擎计算的已保存范围，不包含本次尚未应用的参数或几何。原始源图仅用于定位，关闭编辑视图后查看最终调色结果。</small>}
    {active&&<div className="localMaskReview">
      <strong>{state.mutation?.action==='upsert'?`待应用：${state.mutation.object.name}`:state.mutation?.action==='delete'?`待删除：${objects.find(o=>o.id===(state.mutation as {id:string}).id)?.name??state.mutation.id}`:state.mutation?.action==='move'?`待移到第 ${state.mutation.index+1} 位：${objects.find(o=>o.id===(state.mutation as {id:string}).id)?.name??state.mutation.id}`:state.mutation?.action==='bind'?(state.mutation.enabled?'待绑定组合蒙版':'待恢复全图作用'):'查看已保存组合范围'}</strong>
      <small>{state.mutation?(state.draw?'拖动绘制仅暂存轮廓；重新拖动会替换本次草稿，应用后才写入历史。':'请核对本次操作与当前源图，应用后才写入历史。'):'只查看已保存范围，不修改蒙版或历史。'}</small>
      {state.mutation?.action==='upsert'&&['color_range','luminance_range'].includes(state.mutation.object.kind)&&<fieldset disabled={state.phase!=='target'}><legend>范围吸管与参数</legend>
        <small>点击冻结的原始源图取样。吸管读的是显示用 8 位代理像素，属于近似值；实际范围仍在原始浮点源图上计算。亮度吸管保留当前区间宽度。</small>
        {state.frame&&!state.frame.descriptor.sample_valid_rows&&<small>此画面未提供采样有效域，吸管不可用；手动参数仍可使用。</small>}
        <RangeControls object={state.mutation.object} onChange={workflow.range}/>
      </fieldset>}
      {state.mutation&&<button disabled={state.phase!=='target'||!state.geometryReady} onClick={()=>void workflow.apply()}>应用本次修改</button>}
      <button onClick={()=>workflow.cancel()}>{state.mutation?'取消，不修改':'关闭范围查看'}</button>
    </div>}
    {aiOpen&&<PromptedMaskDialog owner={owner} onClose={()=>setAiOpen(false)}/>}
    {!context.enabled&&context.reason&&<small>{context.reason}</small>}
    {state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&<div className="localMaskWarning"><p>结果未确认，不会重新发送。</p><button onClick={()=>void workflow.check()}>查询原操作结果</button><button disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button></div>}
  </section>;
}
export function LocalMaskStatus({owner}:{owner:LocalMaskOwner}){
  if(!['sending','waiting','uncertain','failure'].includes(owner.state.phase)||!owner.state.message)return null;
  return <div className="sourcePatchStatus" role="status"><span>{owner.state.message}</span>{owner.state.phase==='uncertain'&&<button onClick={()=>void owner.workflow.check()}>查询原蒙版结果</button>}</div>;
}
