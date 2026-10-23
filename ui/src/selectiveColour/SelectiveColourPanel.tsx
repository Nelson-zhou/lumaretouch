import {useEffect,useState} from 'react';
import {checked,neutral,ranges,inks,requirements,type Range,type Ink,type Recipe} from './model';
import type {SelectiveColourWorkflow} from './workflow';
import './selectiveColour.css';
const labels:Record<Range,string>={reds:'红',yellows:'黄',greens:'绿',cyans:'青',blues:'蓝',magentas:'洋红',whites:'白',neutrals:'中间色',blacks:'黑'};
const inkLabels:Record<Ink,string>={cyan:'青色量',magenta:'洋红量',yellow:'黄色量',black:'黑色量'};
export function SelectiveColourPanel({value,workflow,enabled,message}:{value:Recipe;workflow:SelectiveColourWorkflow;enabled:boolean;message:string}){
 const [draft,setDraft]=useState(()=>checked(value));const [range,setRange]=useState<Range>('reds');const [,refresh]=useState(0);
 useEffect(()=>workflow.subscribe(()=>refresh(v=>v+1)),[workflow]);useEffect(()=>setDraft(checked(value)),[value]);
 const update=(recipe:Recipe)=>{if(!enabled||workflow.locked)return;const next=checked(recipe);setDraft(next);workflow.preview(next);};
 const setInk=(ink:Ink,v:number)=>{if(Number.isFinite(v)&&v>=-100&&v<=100)update({...draft,ranges:{...draft.ranges,[range]:{...draft.ranges[range],[ink]:v}}});};
 return <section className="selectiveColour" data-requirement-id={requirements.parent} aria-label="可选颜色">
 <h3>可选颜色</h3><fieldset disabled={!enabled||workflow.locked}><legend>九色域 CMYK</legend>
 <div className="selectiveColourRanges">{ranges.map(k=><button type="button" key={k} aria-pressed={k===range} data-requirement-id={requirements[k]} onClick={()=>setRange(k)}>{labels[k]}</button>)}</div>
 <fieldset><legend>调整方式（作用于全部色域）</legend>{(['relative','absolute'] as const).map(method=><label key={method} data-requirement-id={requirements[method]}><input type="radio" name="selective-colour-method" checked={draft.method===method} onChange={()=>update({...draft,method})}/>{method==='relative'?'相对':'绝对'}</label>)}</fieldset>
 {inks.map(ink=><label key={ink} data-requirement-id={requirements[ink]}>{inkLabels[ink]}<input aria-label={`${labels[range]}${inkLabels[ink]}`} type="range" min={-100} max={100} step={1} value={draft.ranges[range][ink]} onChange={e=>setInk(ink,e.target.valueAsNumber)}/><input aria-label={`${labels[range]}${inkLabels[ink]}数值`} type="number" min={-100} max={100} step={1} value={draft.ranges[range][ink]} onChange={e=>setInk(ink,e.target.valueAsNumber)}/><span>%</span></label>)}
 <p>相对：按现有互补色量调整；绝对：按百分点调整。黑色量同时影响 RGB 三通道。色域重叠会平滑混合。</p>
 <button type="button" onClick={()=>update({...draft,ranges:{...draft.ranges,[range]:neutral().ranges[range]}})}>重置{labels[range]}</button>
 <button type="button" onClick={()=>update(neutral())}>全部重置（预览）</button>
 <button type="button" disabled={!workflow.canApply} onClick={()=>void workflow.apply()}>应用</button>
 <button type="button" onClick={()=>{void workflow.cancel();setDraft(checked(value));}}>取消预览</button>
 </fieldset><button type="button" onClick={()=>void workflow.query()}>查询提交结果</button><p role="status">{message}</p>
 <small>原创 RGB 色域算法，非 HSL 或印刷 ICC 分色；不保证与其他产品逐像素相同。视觉及性能待本地验收。</small>
 </section>;
}
