import {useRef,useState,type PointerEvent} from 'react';
import type {CanvasMask,Mark} from './model';
/** Explicit render-normalized marks. Never sends a source-domain mask identity. */
export function CanvasMaskEditor({title,image,mask,onChange,disabled=false,overlay}:{title:string;image:string;mask:CanvasMask;onChange:(mask:CanvasMask)=>void;disabled?:boolean;overlay?:string}){
 const [mode,setMode]=useState<'add'|'subtract'>('add'),[radius,setRadius]=useState(.035),[draft,setDraft]=useState<Mark|null>(null);
 const drawing=useRef<Mark|null>(null);
 const position=(e:PointerEvent<SVGSVGElement>):[number,number]=>{const r=e.currentTarget.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
 const ratio=mask.binding.width/mask.binding.height,remainingPoints=4096-mask.objects.reduce((n,m)=>n+(m.points?.length??0),0);
 const finish=(e:PointerEvent<SVGSVGElement>)=>{const mark=drawing.current;if(!mark)return;drawing.current=null;setDraft(null);if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);onChange({...mask,objects:[...mask.objects,mark]});};
 return <section className="semantic-mask-editor"><strong>{title}</strong><div className="semantic-mask-tools">
  <button disabled={disabled} aria-pressed={mode==='add'} onClick={()=>setMode('add')}>添加</button><button disabled={disabled} aria-pressed={mode==='subtract'} onClick={()=>setMode('subtract')}>擦除</button>
  <label>画笔 <input type="range" min=".005" max=".15" step=".005" value={radius} disabled={disabled} onChange={e=>setRadius(Number(e.target.value))}/></label>
  <button disabled={disabled||!mask.objects.length} onClick={()=>onChange({...mask,objects:mask.objects.slice(0,-1)})}>撤销一笔</button>
  <button disabled={disabled||!mask.objects.length} onClick={()=>onChange({...mask,objects:[]})}>清除手工标记</button></div>
  <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label={`${title}，在图上绘制独立选区`} style={{aspectRatio:ratio}} onPointerDown={e=>{
   if(disabled||mask.objects.length>=32||remainingPoints<1)return;e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);
   const mark:Mark={id:crypto.randomUUID().replaceAll('-',''),name:mode==='add'?'添加画笔':'擦除画笔',enabled:true,operation:mode,kind:'brush',opacity:1,feather:4,points:[position(e)],axes:[[Math.min(radius,4/ratio),0],[0,Math.min(radius*ratio,4)]]};drawing.current=mark;setDraft(mark);
  }} onPointerMove={e=>{if(!drawing.current||drawing.current.points.length>=Math.min(1024,remainingPoints))return;const point=position(e);const old=drawing.current.points.at(-1)!;if(Math.hypot(point[0]-old[0],point[1]-old[1])<.002)return;drawing.current={...drawing.current,points:[...drawing.current.points,point]};setDraft(drawing.current);}} onPointerUp={finish} onPointerCancel={()=>{drawing.current=null;setDraft(null);}}>
   <image href={image} width="1000" height="1000" preserveAspectRatio="none"/>
   {overlay&&<image href={overlay} width="1000" height="1000" preserveAspectRatio="none"/>}
   {[...(overlay?[]:mask.objects),...(draft?[draft]:[])].filter(m=>m.kind==='brush').map(m=><polyline key={m.id} points={m.points.map(p=>`${p[0]*1000},${p[1]*1000}`).join(' ')} fill="none" stroke={m.operation==='subtract'?'#ff725e':'#5ad9d0'} strokeWidth={m.axes[0][0]*2000} opacity=".45" strokeLinecap="round" strokeLinejoin="round"/>)}
  </svg><small>青色添加，红色擦除。标记仅绑定此图的冻结渲染画布；改裁剪或形变后需重新分析。</small>
 </section>;
}
