import {useEffect,useState} from 'react';
import {checked,neutral,primaries,requirements,type Primary,type Recipe} from './model';
import type {PrimaryCalibrationWorkflow} from './workflow';
const labels:Record<Primary,string>={red:'红原色',green:'绿原色',blue:'蓝原色'};
export function PrimaryCalibrationPanel({value,workflow,enabled,message}:{value:Recipe;workflow:PrimaryCalibrationWorkflow;enabled:boolean;message:string}){
 const [draft,setDraft]=useState(()=>checked(value));const [,refresh]=useState(0);
 useEffect(()=>workflow.subscribe(()=>refresh(v=>v+1)),[workflow]);
 useEffect(()=>setDraft(checked(value)),[value]);
 const update=(r:Recipe)=>{if(!enabled||workflow.locked)return;setDraft(checked(r));workflow.preview(r);};
 return <section aria-label="RGB 原色校准" data-requirement-id={requirements.parent}>
 <h3>RGB 原色校准</h3><p>改变全局原色基准，灰阶保持中性。这不是按颜色范围选择的 HSL 调节。</p>
 <fieldset disabled={!enabled||workflow.locked}><legend>三原色色相与饱和度</legend>
 {primaries.map(k=><fieldset key={k} data-requirement-id={requirements[k]}><legend>{labels[k]}</legend>
 {(['hue','saturation'] as const).map(f=><label key={f} data-requirement-id={requirements[`${k}_${f}`]}>{f==='hue'?'色相':'饱和度'}
 <input aria-label={`${labels[k]}${f==='hue'?'色相':'饱和度'}`} type="range" min={-100} max={100} step={1} value={draft[k][f]} onChange={e=>update({...draft,[k]:{...draft[k],[f]:Number(e.target.value)}})}/>
 <input aria-label={`${labels[k]}${f==='hue'?'色相':'饱和度'}数值`} type="number" min={-100} max={100} step={1} value={draft[k][f]} onChange={e=>{const n=e.target.valueAsNumber;if(Number.isFinite(n)&&Math.abs(n)<=100)update({...draft,[k]:{...draft[k],[f]:n}});}}/>
 </label>)}<button type="button" onClick={()=>update({...draft,[k]:neutral()[k]})}>重置{labels[k]}</button></fieldset>)}
 <p>色相正值：红向黄、绿向青、蓝向品红。饱和度调整原色至白点的距离。过强组合可能导致无效色域，系统会拒绝而不会暗中修正。</p>
 <button type="button" onClick={()=>update(neutral())}>全部重置（预览）</button>
 <button type="button" disabled={!workflow.canApply} onClick={()=>void workflow.apply()}>应用</button>
 <button type="button" onClick={()=>{void workflow.cancel();setDraft(checked(value));}}>取消预览</button>
 </fieldset><button type="button" onClick={()=>void workflow.query()}>查询提交结果</button><p role="status">{message}</p>
 <small>原创线性 sRGB D65 原色基校准，不替代相机 ICC/DCP 配置文件；视觉效果与性能待本地验收。</small></section>;
}
