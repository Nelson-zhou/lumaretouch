import {useEffect,useState} from 'react';
import type {KeyboardEvent,PointerEvent} from 'react';
import {checked,neutral,ranges,requirements,wheelAt,type Range,type Recipe,type Wheel} from './model';
import type {ColourGradingWorkflow} from './workflow';
import './colourGrading.css';
const labels:Record<Range,string>={shadows:'阴影',midtones:'中间调',highlights:'高光',global:'全局'};
export function ColourGradingPanel({value,workflow,enabled,message}:{value:Recipe;workflow:ColourGradingWorkflow;enabled:boolean;message:string}){
  const [draft,setDraft]=useState(()=>checked(value));const [range,setRange]=useState<Range>('midtones');
  const [,refresh]=useState(0);
  useEffect(()=>workflow.subscribe(()=>refresh(v=>v+1)),[workflow]);
  useEffect(()=>{setDraft(checked(value));},[value]);
  const update=(r:Recipe)=>{if(!enabled||workflow.locked)return;setDraft(r);workflow.preview(r);};
  const setWheel=(w:Wheel)=>update({...draft,[range]:w});const w=draft[range];
  const point=(e:PointerEvent<HTMLDivElement>)=>{const b=e.currentTarget.getBoundingClientRect();setWheel(wheelAt((e.clientX-b.left-b.width/2)/(b.width/2),-(e.clientY-b.top-b.height/2)/(b.height/2),w));};
  const keys=(e:KeyboardEvent<HTMLDivElement>)=>{if(!enabled)return;const d=e.shiftKey?10:1;
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();setWheel({...w,hue:(w.hue+(e.key==='ArrowRight'?d:-d)+360)%360});}
    if(e.key==='ArrowUp'||e.key==='ArrowDown'){e.preventDefault();setWheel({...w,saturation:Math.max(0,Math.min(100,w.saturation+(e.key==='ArrowUp'?d:-d)))});}
    if(e.key==='Home'){e.preventDefault();setWheel({...w,saturation:0});}
  };
  const scalar=(label:string,key:keyof Wheel,min:number,max:number)=> <label data-requirement-id={key==='luminance'?requirements.luminance:undefined}>{label}<input aria-label={`${labels[range]}${label}`} type="range" min={min} max={max} step={1} value={w[key]} onChange={e=>setWheel({...w,[key]:Number(e.target.value)})}/><input aria-label={`${labels[range]}${label}数值`} type="number" min={min} max={max} step={1} value={Number(w[key].toFixed(2))} onChange={e=>{const n=e.target.valueAsNumber;if(Number.isFinite(n)&&n>=min&&n<=max)setWheel({...w,[key]:n});}}/></label>;
  return <section className="colourGrading" data-requirement-id={requirements.parent} aria-label="颜色分级">
    <h3>颜色分级</h3>
    <fieldset disabled={!enabled||workflow.locked}><legend>选择影调区域</legend><div className="colourGradingTabs">{ranges.map(k=><button key={k} type="button" aria-pressed={range===k} data-requirement-id={requirements[k]} onClick={()=>setRange(k)}>{labels[k]}</button>)}</div>
      <div className="colourGradingWheel" role="group" aria-label={`${labels[range]}色轮：左右调整色相，上下调整饱和度，Home 回到中心`} tabIndex={enabled?0:-1} onKeyDown={keys}
        onPointerDown={e=>{if(enabled&&e.button===0){e.currentTarget.setPointerCapture(e.pointerId);point(e);}}}
        onPointerMove={e=>{if(enabled&&e.currentTarget.hasPointerCapture(e.pointerId))point(e);}}
        onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId)){point(e);e.currentTarget.releasePointerCapture(e.pointerId);}}}
        onPointerCancel={()=>{void workflow.cancel();setDraft(checked(value));}}>
        <span className="colourGradingPoint" style={{left:`${50+Math.cos(w.hue*Math.PI/180)*w.saturation/2}%`,top:`${50-Math.sin(w.hue*Math.PI/180)*w.saturation/2}%`}}/>
      </div>
      {scalar('色相','hue',0,360)}{scalar('饱和度','saturation',0,100)}{scalar('明亮度','luminance',-100,100)}
      <button type="button" onClick={()=>setWheel(neutral()[range])}>重置{labels[range]}</button>
      {(['blending','balance'] as const).map(k=><label key={k} data-requirement-id={requirements[k]}>{k==='blending'?'混合':'平衡'}<input aria-label={k==='blending'?'混合':'平衡'} type="range" min={k==='blending'?0:-100} max={100} value={draft[k]} onChange={e=>update({...draft,[k]:Number(e.target.value)})}/><input aria-label={k==='blending'?'混合数值':'平衡数值'} type="number" min={k==='blending'?0:-100} max={100} value={draft[k]} onChange={e=>{const n=e.target.valueAsNumber;if(Number.isFinite(n)&&n>=(k==='blending'?0:-100)&&n<=100)update({...draft,[k]:n});}}/></label>)}
      <p>正平衡扩大高光影响；混合控制影调交界平滑度。全局色轮独立叠加，不受平衡影响。</p>
      <button type="button" onClick={()=>update(neutral())}>全部重置（预览）</button>
      <button type="button" disabled={!workflow.canApply} onClick={()=>void workflow.apply()}>应用</button>
      <button type="button" onClick={()=>{void workflow.cancel();setDraft(checked(value));}}>取消预览</button>
    </fieldset><button type="button" onClick={()=>void workflow.query()}>查询提交结果</button><p role="status">{message}</p><small>采用原创影调分区算法，不保证与其他产品逐像素相同。性能和视觉验收尚待本地验证。</small>
  </section>;
}
