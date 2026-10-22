import {useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as Pointer} from 'react';
import {createPortal} from 'react-dom';
import {captureRect} from '../colorSampleGeometry';
import {normalizedPoint,type Point} from '../sourcePatch/geometry';
import type {CloneStampOwner} from './useCloneStampWorkflow';
import {CLONE_STAMP_LABEL} from './workflow';
import '../sourcePatch/sourcePatch.css';
interface Gesture {pointer:number;key:string;points:Point[];source:Point}
export function CloneStampOverlay({owner,clip,box,view}:{owner:CloneStampOwner;clip:HTMLDivElement|null;box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const {state,workflow}=owner,frame=state.frame;
  const canvas=useRef<HTMLCanvasElement|null>(null),surface=useRef<HTMLDivElement|null>(null),gesture=useRef<Gesture|null>(null);
  const [draft,setDraft]=useState<Point[]>([]),[hover,setHover]=useState<Point|null>(null);
  const rect=frame?captureRect(box,view,frame.descriptor):{left:0,top:0,width:0,height:0};
  const visible=box.width>0&&box.height>0&&rect.width>0&&rect.height>0;
  const key=[frame?.descriptor.capture_id,frame?.descriptor.ticket,box.left,box.top,rect.left,rect.top,rect.width,rect.height,state.size,state.hardness,state.opacity,state.source?.join(',')].join(':');
  useLayoutEffect(()=>{
    gesture.current=null;setDraft([]);setHover(null);
    if(!frame||!clip||!canvas.current||!visible)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const context=node.getContext('2d');if(!context)throw Error('无法创建图章取样画布');
      context.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(frame.descriptor);});});
      surface.current?.focus({preventScroll:true});
    }catch(error){workflow.failed(error);}
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,workflow,visible]);
  useLayoutEffect(()=>{const blur=()=>{if(gesture.current)workflow.gestureCancelled('窗口失焦，未提交的笔划已取消');gesture.current=null;setDraft([]);};window.addEventListener('blur',blur);return()=>window.removeEventListener('blur',blur);},[workflow]);
  useLayoutEffect(()=>{if(gesture.current&&gesture.current.key!==key){gesture.current=null;setDraft([]);}},[key]);
  useLayoutEffect(()=>{if(state.phase!=='target'){gesture.current=null;setDraft([]);}},[state.phase]);
  if(!frame||!clip)return null;
  const d=frame.descriptor,editable=state.phase==='target',radius=state.size*Math.min(d.width,d.height)/2;
  const local=(x:number,y:number)=>normalizedPoint(x-box.left,y-box.top,rect,d.width,d.height);
  const stop=(event:Pointer<HTMLDivElement>)=>{event.preventDefault();event.stopPropagation();};
  const release=(event:Pointer<HTMLDivElement>)=>{if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);};
  const abandon=()=>{gesture.current=null;setDraft([]);};
  const move=(event:Pointer<HTMLDivElement>)=>{
    stop(event);const point=local(event.clientX,event.clientY);setHover(point);
    const down=gesture.current;if(!down||!editable||down.pointer!==event.pointerId)return;
    if(down.key!==key||!point){abandon();workflow.gestureCancelled('笔划离开取样画面或视图变化，整笔未提交');return;}
    const last=down.points.at(-1)!;
    if(Math.hypot((last[0]-point[0])*d.width,(last[1]-point[1])*d.height)<.5)return;
    if(down.points.length>=1024){abandon();workflow.failed('笔划过长，未提交；请分成多笔');return;}
    down.points=[...down.points,point];setDraft(down.points);
  };
  const donor:Point|null=state.source&&hover&&draft.length?[state.source[0]+hover[0]-draft[0][0],state.source[1]+hover[1]-draft[0][1]]:state.source;
  const ring=(p:Point,color:string)=><g><circle cx={p[0]*d.width} cy={p[1]*d.height} r={radius} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke"/><circle cx={p[0]*d.width} cy={p[1]*d.height} r={radius*state.hardness} fill="none" stroke={color} strokeDasharray="3 3" vectorEffect="non-scaling-stroke"/></g>;
  return <>
    <div ref={surface} className={`sourcePatchSurface ${editable?'editable':'waiting'}`} tabIndex={0} role="application" aria-label="仿制图章：Alt 点击取样，涂抹后松手提交，Esc 取消未提交笔划"
      onWheel={event=>event.stopPropagation()} onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
      onPointerDown={event=>{
        stop(event);if(event.button!==0||!editable||gesture.current)return;
        event.currentTarget.focus({preventScroll:true});const point=local(event.clientX,event.clientY);if(!point)return;
        if(event.altKey||!state.source){workflow.setSource(point);setHover(point);return;}
        gesture.current={pointer:event.pointerId,key,points:[point],source:[...state.source]};setDraft([point]);setHover(point);
        event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={move} onPointerLeave={()=>{if(!gesture.current)setHover(null);}}
      onPointerUp={event=>{
        stop(event);const down=gesture.current;if(!down||down.pointer!==event.pointerId)return;
        move(event);const current=gesture.current;abandon();release(event);
        if(current&&current.key===key&&editable)void workflow.apply(current.points);
      }}
      onPointerCancel={event=>{stop(event);abandon();release(event);workflow.gestureCancelled('手势中断，整笔未提交');}}
      onLostPointerCapture={event=>{if(gesture.current?.pointer===event.pointerId){abandon();workflow.gestureCancelled('指针控制中断，整笔未提交');}}}
      onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();abandon();workflow.cancel();}}}/>
    {createPortal(<div className="sourcePatchPreview" aria-hidden="true">
      <canvas ref={canvas} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}}/>
      <svg className="sourcePatchShapes" width={rect.width} height={rect.height} viewBox={`0 0 ${d.width} ${d.height}`} preserveAspectRatio="none" style={{left:rect.left,top:rect.top}}>
        {draft.length>0&&<polyline points={draft.map(p=>`${p[0]*d.width},${p[1]*d.height}`).join(' ')} fill="none" stroke="#ffb35c" strokeOpacity={Math.max(.1,state.opacity*.35)} strokeWidth={radius*2} strokeLinecap="round" strokeLinejoin="round"/>}
        {hover&&ring(hover,'#ffb35c')}{donor&&ring(donor,'#74dcff')}
        {donor&&<path d={`M ${donor[0]*d.width-5} ${donor[1]*d.height} h 10 M ${donor[0]*d.width} ${donor[1]*d.height-5} v 10`} stroke="#74dcff" vectorEffect="non-scaling-stroke"/>}
      </svg>
      <div className="sourcePatchViewLabel">{CLONE_STAMP_LABEL}</div>
      <div className="sourcePatchViewHint">{state.source?'橙色：目标笔刷；蓝色：来源。松手提交一笔，Esc 取消。':'Alt/Option 点击或直接点击画面设置来源（不会修改照片）。'}</div>
    </div>,clip)}
  </>;
}
