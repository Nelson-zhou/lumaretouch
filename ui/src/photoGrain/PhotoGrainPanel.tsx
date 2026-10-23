import {useEffect,useState} from 'react';
import {checked,controls,labels,neutral,requirements,type Recipe} from './model';
import type {PhotoGrainWorkflow} from './workflow';
export function PhotoGrainPanel({value,workflow,enabled,message}:{value:Recipe;workflow:PhotoGrainWorkflow;enabled:boolean;message:string}){
 const [draft,setDraft]=useState(()=>checked(value));const [,update]=useState(0);
 useEffect(()=>setDraft(checked(value)),[value]);useEffect(()=>workflow.subscribe(()=>update(n=>n+1)),[workflow]);
 function preview(next:Recipe){const r=checked(next);setDraft(r);workflow.preview(r);}
 return <section aria-label="照片颗粒" data-requirement={requirements.parent}>
  <p>源像素尺寸；预览使用原图颗粒后缩放，不会刷新随机图案。输出尺寸改变时，颗粒随照片一起缩放。缩放导致裁剪取整不一致时将明确拒绝，请使用原尺寸或像素对齐裁剪。</p>
  <fieldset disabled={!enabled||workflow.locked}><legend>颗粒</legend>
   {controls.map(key=><label key={key} data-requirement={requirements[key]}>{labels[key]} <output>{draft[key]}</output>
    <input aria-label={labels[key]} type="range" min={key==='size'?0.5:0} max={key==='size'?16:100} step={key==='size'?0.1:1} value={draft[key]} onChange={e=>preview({...draft,[key]:Number(e.target.value)})}/></label>)}
   <label>固定图案种子<input aria-label="固定图案种子" type="number" min={0} max={4294967295} step={1} value={draft.seed} onChange={e=>{const seed=Number(e.target.value);if(Number.isInteger(seed)&&seed>=0&&seed<=4294967295)preview({...draft,seed});}}/></label>
   <button type="button" onClick={()=>preview({...neutral(),seed:draft.seed})}>复位参数（保留种子）</button>
   <button type="button" disabled={!workflow.canApply} onClick={()=>void workflow.apply()}>应用</button>
   <button type="button" onClick={()=>{setDraft(checked(value));void workflow.cancel();}}>取消预览</button>
  </fieldset>
  <button type="button" onClick={()=>void workflow.query()}>查询未确认结果</button>
  <p role="status">{message}</p>
 </section>;
}
