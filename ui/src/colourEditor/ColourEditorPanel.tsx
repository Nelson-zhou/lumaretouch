import {useEffect,useState} from 'react';
import {checked,neutral,smoothing,type Recipe} from './model';
import type {ColourEditorWorkflow} from './workflow';
import './colourEditor.css';
type Props={value:Recipe;workflow:ColourEditorWorkflow;enabled:boolean;message:string;onPick?:()=>void;onDraft?:(r:Recipe)=>void};
export function ColourEditorPanel({value,workflow,enabled,message,onPick,onDraft}:Props){
 const [r,setR]=useState(()=>checked(value));const [show,setShow]=useState(false);const [,tick]=useState(0);
 useEffect(()=>workflow.subscribe(()=>tick(v=>v+1)),[workflow]);useEffect(()=>setR(checked(value)),[value]);
 const edit=(n:Recipe)=>{setR(checked(n));onDraft?.(checked(n));workflow.preview(n);};
 const slider=(label:string,v:number,lo:number,hi:number,step:number,change:(v:number)=>void)=><label>{label}<input aria-label={label} type="range" min={lo} max={hi} step={step} value={v} onChange={e=>change(Number(e.target.value))}/><input aria-label={`${label}数值`} type="number" min={lo} max={hi} step={step} value={v} onChange={e=>{const x=Number(e.target.value);if(Number.isFinite(x)&&x>=lo&&x<=hi)change(x);}}/></label>;
 return <section className="colour-editor" aria-label="色彩编辑器"><h3>色彩编辑器</h3><fieldset disabled={!enabled||workflow.locked}>
 <label>作用范围<select value={r.scope} onChange={e=>edit({...r,scope:e.target.value as Recipe["scope"]})}><option value="all">全图</option><option value="local">当前局部调色蒙版</option></select></label>
 <button type="button" disabled={!onPick} onClick={onPick}>吸取输入画面颜色</button>{!onPick&&<p>输入画面吸管尚未连接，不能从预览输出取色。</p>}
 <div className="colour-editor-wheel" onPointerDown={e=>{if(!enabled||workflow.locked)return;e.currentTarget.setPointerCapture(e.pointerId);const b=e.currentTarget.getBoundingClientRect();const x=e.clientX-b.left-b.width/2,y=e.clientY-b.top-b.height/2;edit({...r,selection:{...r.selection,hue:((Math.atan2(y,x)/(2*Math.PI))+.25+1)%1}});}} onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;const b=e.currentTarget.getBoundingClientRect();const x=e.clientX-b.left-b.width/2,y=e.clientY-b.top-b.height/2;edit({...r,selection:{...r.selection,hue:((Math.atan2(y,x)/(2*Math.PI))+.25+1)%1}});}} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} role="img" aria-label={`连续色域：中心 ${Math.round(r.selection.hue*360)} 度，半宽 ${Math.round(r.selection.half_width*360)} 度`} style={{background:`conic-gradient(red,#ff0,#0f0,#0ff,#00f,#f0f,red)`}}><div aria-hidden="true" style={{position:"absolute",inset:0,borderRadius:"50%",background:`conic-gradient(from ${(r.selection.hue-r.selection.half_width)*360}deg, transparent 0deg ${r.selection.half_width*720}deg, rgba(0,0,0,.65) ${r.selection.half_width*720}deg 360deg)`}}/><span style={{position:"relative",transform:`rotate(${r.selection.hue*360}deg)`}}>↑</span></div>
 {slider('色轮中心',r.selection.hue,0,1,.001,v=>edit({...r,selection:{...r.selection,hue:v}}))}
 {slider('色轮范围',r.selection.half_width,0,.5,.001,v=>edit({...r,selection:{...r.selection,half_width:v}}))}
 {(['saturation','luminance'] as const).map((k,i)=><div key={k}>{([0,1] as const).map(j=>slider(`${i?'亮度':'饱和度'}${j?'上界':'下界'}`,r.selection[k][j],j?r.selection[k][0]:0,j?1:r.selection[k][1],.001,v=>{const a=[...r.selection[k]] as [number,number];a[j]=v;edit({...r,selection:{...r.selection,[k]:a}});} ))}</div>)}
 {slider('色彩平滑',r.colour_smoothness,0,1,.01,v=>edit(smoothing(r,'colour_smoothness',v)))}
 <label><input type="checkbox" checked={r.linked} onChange={e=>edit({...r,linked:e.target.checked,luminance_smoothness:e.target.checked?r.colour_smoothness:r.luminance_smoothness})}/>联动色彩与亮度平滑</label>
 {slider('亮度平滑',r.luminance_smoothness,0,1,.01,v=>edit(smoothing(r,'luminance_smoothness',v)))}
 {(['offsets','uniformity'] as const).map(k=><fieldset key={k}><legend>{k==='offsets'?'HSL 偏移':'色彩均匀度：左侧分散，右侧集中'}</legend>{(['色相','饱和度','明亮度'] as const).map((label,i)=>slider(`${label}${k==='offsets'?'偏移':'均匀度'}`,r[k][i],-100,100,1,v=>{const a=[...r[k]] as [number,number,number];a[i]=v;edit({...r,[k]:a});}))}</fieldset>)}
 <label><input type="checkbox" checked={r.invert} onChange={e=>edit({...r,invert:e.target.checked})}/>反转色彩范围（仍限定于局部蒙版）</label>
 <label><input type="checkbox" checked={show} onChange={e=>{setShow(e.target.checked);workflow.setRangeView(e.target.checked);workflow.preview(r);}}/>显示所选色彩范围（仅查看，不导出）</label>
 <button type="button" onClick={()=>edit(neutral())}>重置配方</button><button type="button" disabled={!workflow.canApply} onClick={()=>void workflow.apply()}>应用</button><button type="button" onClick={()=>void workflow.cancel()}>取消预览</button></fieldset>
 <button type="button" onClick={()=>void workflow.query()}>查询未确认结果</button><p role="status">{message}</p></section>;
}
