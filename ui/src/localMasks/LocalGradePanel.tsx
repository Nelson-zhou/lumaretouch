import {useEffect,useRef,useState} from 'react';
import {MASK_LABELS,OPERATION_LABELS,drawingKind,geometryDescription,type LocalGradeReport,type LocalGradeLayer,type MaskMutation,type MaskObject,type MaskOperation} from './model';
import {RangeControls} from './RangeControls';
import {LiveGradeControls} from './LiveGradeControls';
import type {LiveGradeOwner} from './useLiveGradeWorkflow';
export function LocalGradePanel({report,locked,liveLocked,liveGrade,documentId,selectionLocked,onSelectGroup,onStart}:{report?:LocalGradeReport;locked:boolean;liveLocked:boolean;liveGrade?:LiveGradeOwner;documentId:string;selectionLocked:boolean;onSelectGroup:(id:string)=>boolean;onStart:(mutation:MaskMutation|null,draw?:boolean,groupId?:string|null)=>void}){
  const [id,setId]=useState(''),[draft,setDraft]=useState<LocalGradeLayer|null>(null),[object,setObject]=useState<MaskObject|null>(null);
  const layers=report?.layers??[],stored=layers.find(g=>g.id===id),key=JSON.stringify(stored??null);
  const previous=useRef<LocalGradeLayer|null>(null);
  useEffect(()=>{setId('');setDraft(null);setObject(null);previous.current=null;},[documentId]);
  useEffect(()=>{
    const old=previous.current;previous.current=stored?structuredClone(stored):null;
    setDraft(current=>stored?{...structuredClone(stored),
      name:current?.id===stored.id&&current.name!==old?.name?current.name:stored.name,
      enabled:current?.id===stored.id&&current.enabled!==old?.enabled?current.enabled:stored.enabled}:null);
    if(JSON.stringify(old?.mask)!==JSON.stringify(stored?.mask))setObject(null);
  },[key,documentId]);
  if(!layers.length)return null;
  const maskEdit=(mutation:Extract<MaskMutation,{action:'upsert'|'delete'|'move'}>,draw=false)=>{if(draft)onStart({action:'layer_mask',id:draft.id,mutation},draw);};
  return <section className="localGradePanel" aria-label="独立局部调色组"><h4>独立局部调色组</h4>
    <small>旧调色槽之后，按列表顺序各自调色。每组保留自己的蒙版运算顺序，不合并不同组。修改、启停、排序、删除都进入照片撤销历史。</small>
    {report?.suspended&&<p role="alert">独立局部效果已全部暂停：{report.suspended}。不会改成全图。</p>}
    <ol>{layers.map((layer,index)=><li key={layer.id}>
      <button disabled={selectionLocked} onClick={()=>{if(onSelectGroup(layer.id))setId(layer.id);}}>{layer.enabled?'●':'○'} {layer.name} · {layer.mask.recipe.objects.length} 对象</button>
      <button disabled={locked||index===0} aria-label={`${layer.name} 组上移`} onClick={()=>onStart({action:'layer_move',id:layer.id,index:index-1})}>↑</button>
      <button disabled={locked||index===layers.length-1} aria-label={`${layer.name} 组下移`} onClick={()=>onStart({action:'layer_move',id:layer.id,index:index+1})}>↓</button>
      <button disabled={locked} onClick={()=>onStart({action:'layer_delete',id:layer.id})}>删除组</button>
    </li>)}</ol>
    {draft&&stored&&<>
    {liveGrade&&report?<LiveGradeControls owner={liveGrade} layer={stored} limits={report.grade_limits} disabled={liveLocked} documentId={documentId}/>
      :<small>当前引擎未提供实时局部调色，请更新匹配版本。</small>}
    <fieldset disabled={locked}><legend>编辑“{stored.name}”</legend>
      <button onClick={()=>onStart(null,false,draft.id)}>查看本组已保存范围</button>
      <label>名称<input value={draft.name} maxLength={80} onChange={e=>setDraft({...draft,name:e.target.value})}/></label>
      <label><input type="checkbox" checked={draft.enabled} onChange={e=>setDraft({...draft,enabled:e.target.checked})}/>启用本组</label>
      <button disabled={!draft.name.trim()||(draft.name===stored.name&&draft.enabled===stored.enabled)} onClick={()=>onStart({action:'layer_update',id:draft.id,name:draft.name,enabled:draft.enabled,grade:stored.grade})}>审核名称与启用状态</button>
      <ol>{draft.mask.recipe.objects.map((item,index)=><li key={item.id}>
        <button onClick={()=>setObject(structuredClone(item))}>{item.enabled?'●':'○'} {item.name} · {MASK_LABELS[item.kind]} · {OPERATION_LABELS[item.operation]}</button>
        <button disabled={item.kind==='full'||index===0} onClick={()=>maskEdit({action:'move',id:item.id,index:index-1})}>↑</button>
        <button disabled={item.kind==='full'||index===draft.mask.recipe.objects.length-1} onClick={()=>maskEdit({action:'move',id:item.id,index:index+1})}>↓</button>
        <button disabled={item.kind==='full'} onClick={()=>maskEdit({action:'delete',id:item.id})}>删除对象</button>
      </li>)}</ol>
      {object&&<fieldset disabled={object.kind==='full'}><legend>本组对象参数</legend>
        <small>{geometryDescription(object)}。参数编辑保留源图几何；本面板不冒充自动跨照片对齐。</small>
        <label>名称<input value={object.name} maxLength={80} onChange={e=>setObject({...object,name:e.target.value})}/></label>
        <label><input type="checkbox" checked={object.enabled} onChange={e=>setObject({...object,enabled:e.target.checked})}/>启用对象</label>
        <label>运算<select value={object.operation} onChange={e=>setObject({...object,operation:e.target.value as MaskOperation})}>{Object.entries(OPERATION_LABELS).map(([value,label])=><option value={value} key={value}>{label}</option>)}</select></label>
        <label>不透明度<input type="range" min="0" max="1" step=".01" value={object.opacity} onChange={e=>setObject({...object,opacity:Number(e.target.value)})}/></label>
        <label>羽化<input type="range" min="0" max="100" value={object.feather} onChange={e=>setObject({...object,feather:Number(e.target.value)})}/></label>
        <RangeControls object={object} onChange={patch=>setObject({...object,...patch} as MaskObject)}/>
        {drawingKind(object.kind)&&<button onClick={()=>maskEdit({action:'upsert',coordinate_space:'capture',object:object.kind==='brush'?{...object,points:[],axes:[[.025,0],[0,.025]]}:object},true)}>在源图重绘本组对象</button>}
        <button disabled={!object.name.trim()} onClick={()=>maskEdit({action:'upsert',coordinate_space:'source',object})}>审核本组对象修改</button>
      </fieldset>}
    </fieldset></>}
  </section>;
}
