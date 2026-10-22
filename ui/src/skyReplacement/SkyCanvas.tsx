import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {maskOf,newStroke,TARGET_COLORS,TARGET_LABELS,withMask,type SkyDraft,type SkyStroke,type SkyTarget} from './model';
import type {SkyReplacementOwner} from './useSkyReplacementWorkflow';
interface Gesture {id:number;base:SkyDraft;stroke:SkyStroke;last:number;target:SkyTarget}
export function SkyCanvas({owner,size,erase,opacity,showMask,zoom}:{owner:SkyReplacementOwner;size:number;erase:boolean;opacity:number;showMask:boolean;zoom:number}){
  const {workflow,state}=owner;
  const source=useRef<HTMLImageElement|null>(null),after=useRef<HTMLImageElement|null>(null),mask=useRef<HTMLImageElement|null>(null);
  const gesture=useRef<Gesture|null>(null),[path,setPath]=useState<SkyStroke|null>(null);
  useEffect(()=>{
    const image=state.image,preview=state.previewId;if(!image||!preview)return;let cancelled=false,raf=0;
    Promise.all([source.current,after.current,mask.current].map(el=>el?.decode()??Promise.reject(Error('预览图未装载')))).then(()=>{
      raf=requestAnimationFrame(()=>{raf=requestAnimationFrame(()=>{if(!cancelled)void workflow.presented(preview);});});
    }).catch(error=>{if(!cancelled)workflow.failed(error);});
    return()=>{cancelled=true;cancelAnimationFrame(raf);};
  },[state.previewId,state.image,workflow]);
  useEffect(()=>()=>{gesture.current=null;},[]);
  const point=(event:PointerEvent):[number,number]|null=>{
    const rect=source.current?.getBoundingClientRect();if(!rect||rect.width<=0||rect.height<=0)return null;
    const x=(event.clientX-rect.left)/rect.width,y=(event.clientY-rect.top)/rect.height;
    return x>=0&&x<=1&&y>=0&&y<=1?[x,y]:null;
  };
  const send=(g:Gesture)=>{
    const current=maskOf(g.base,g.target);
    workflow.replace(withMask(g.base,g.target,{...current,objects:[...current.objects,structuredClone(g.stroke)]}),false);
  };
  const down=(event:PointerEvent<HTMLDivElement>)=>{
    if(event.button!==0||gesture.current||!state.locatorReady||!state.draft||!state.image||owner.pending)return;
    const p=point(event);if(!p||!workflow.beginGesture(true))return;
    const g:Gesture={id:event.pointerId,base:structuredClone(state.draft),stroke:newStroke(p,state.image.source_width,state.image.source_height,state.target,size,erase,opacity),last:Date.now(),target:state.target};
    gesture.current=g;setPath(g.stroke);event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault();send(g);
  };
  const move=(event:PointerEvent<HTMLDivElement>)=>{
    const g=gesture.current;if(!g||g.id!==event.pointerId)return;
    const p=point(event);if(!p)return;const previous=g.stroke.points.at(-1)!;
    if(Math.hypot(p[0]-previous[0],p[1]-previous[1])<.001)return;
    if(g.stroke.points.length>=1024){workflow.failed('此笔已达 1024 点，请松手后另起一笔');return;}
    g.stroke={...g.stroke,points:[...g.stroke.points,p]};setPath(g.stroke);
    if(Date.now()-g.last>=100){g.last=Date.now();send(g);}
  };
  const end=(event:PointerEvent<HTMLDivElement>,cancelled=false)=>{
    const g=gesture.current;if(!g||g.id!==event.pointerId)return;gesture.current=null;setPath(null);
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    if(cancelled)workflow.cancelGesture();else{send(g);workflow.endGesture();}
  };
  if(!state.image)return <div className="skyCanvasEmpty" role="status">正在准备定位画面…</div>;
  const img=state.image;
  return <div className="skyViews">
    <figure><figcaption>原照片定位 · {TARGET_LABELS[state.target]} · 未变形/未裁剪</figcaption>
      <div className="skySourceScroll"><div className="skySource" style={{width:`${zoom}%`,minWidth:`${zoom}%`,aspectRatio:`${img.source_width}/${img.source_height}`}}
        onPointerDown={down} onPointerMove={move} onPointerUp={e=>end(e)} onPointerCancel={e=>end(e,true)} onLostPointerCapture={e=>{if(gesture.current)end(e,true);}}
        aria-label={`在原照片涂抹${TARGET_LABELS[state.target]}`}>
        <img ref={source} src={img.source} alt="绑定当前源照片的原图定位画面" draggable={false}/>
        <img ref={mask} src={img.overlay} className="skyMask" style={{opacity:showMask?1:0}} alt="当前标记区域" draggable={false}/>
        {state.draft?.horizon!=null&&<div className="skyHorizon" style={{top:`${state.draft.horizon*100}%`}}><span>地平线</span></div>}
        {path&&<svg className="skyGesture" viewBox={`0 0 ${img.source_width} ${img.source_height}`} preserveAspectRatio="none" aria-hidden="true">
          <polyline points={path.points.map(p=>`${p[0]*img.source_width},${p[1]*img.source_height}`).join(' ')} fill="none" stroke={erase?'#ffffff':TARGET_COLORS[state.target]}
            strokeWidth={size/100*Math.min(img.source_width,img.source_height)} strokeLinecap="round" strokeLinejoin="round" opacity=".5"/>
          {path.points.length===1&&<circle cx={path.points[0][0]*img.source_width} cy={path.points[0][1]*img.source_height} r={size/200*Math.min(img.source_width,img.source_height)} fill={TARGET_COLORS[state.target]} opacity=".5"/>}
        </svg>}
      </div></div>
    </figure>
    <figure><figcaption>{state.error?'天空效果已暂停，显示其他效果':'真实处理输出 · 含既有调色、自动美型、最终液化与构图'}</figcaption>
      <img ref={after} className="skyOutput" src={img.after} alt={state.error?'天空效果暂停时的当前照片':'真实换天空处理结果'} draggable={false}/>
      <small>{img.note}</small>
    </figure>
  </div>;
}
