import {useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import type {EffectRecoveryOwner} from './useEffectRecoveryWorkflow';
import {newStroke,type BrushSettings,type RecoveryStroke} from './model';
import type {Point} from '../sourcePatch/geometry';

interface Gesture {pointer:number;stroke:RecoveryStroke;key:string;rect:DOMRect}
export function RecoverySource({owner,settings}:{owner:EffectRecoveryOwner;settings:BrushSettings}){
  const {state,workflow}=owner,frame=state.frame;
  const canvas=useRef<HTMLCanvasElement|null>(null),gesture=useRef<Gesture|null>(null);
  const [cursor,setCursor]=useState<Point|null>(null),[path,setPath]=useState<Point[]>([]);
  const key=frame?[frame.descriptor.capture_id,frame.descriptor.ticket].join(':'):'';
  useLayoutEffect(()=>{
    gesture.current=null;setPath([]);setCursor(null);
    if(!frame||!canvas.current)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current,d=frame.descriptor;node.width=d.width;node.height=d.height;
      const context=node.getContext('2d');if(!context)throw Error('无法显示恢复定位原图');
      // Capture alpha is another tool's diagnostic, not source transparency.
      // Make only a display copy opaque; never alter the verified capture bytes.
      const pixels=new Uint8ClampedArray(frame.rgba);
      for(let i=3;i<pixels.length;i+=4)pixels[i]=255;
      context.putImageData(new ImageData(pixels,d.width,d.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.sourcePresented(d);});});
    }catch(error){workflow.failed(error);}
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,workflow]);
  const stop=(event:ReactPointerEvent<HTMLDivElement>)=>{event.preventDefault();event.stopPropagation();};
  const point=(event:ReactPointerEvent<HTMLDivElement>):Point|null=>{
    const r=event.currentTarget.getBoundingClientRect(),x=(event.clientX-r.left)/r.width,y=(event.clientY-r.top)/r.height;
    return r.width>0&&r.height>0&&x>=0&&x<=1&&y>=0&&y<=1?[x,y]:null;
  };
  function cancelGesture(message:string){gesture.current=null;setPath([]);workflow.gestureCancelled(message);}
  const move=(event:ReactPointerEvent<HTMLDivElement>)=>{
    stop(event);const p=point(event);setCursor(p);
    const down=gesture.current;if(!down||down.pointer!==event.pointerId||down.key!==key)return;
    if(!p){cancelGesture('笔迹超出源图定位画布，已丢弃本笔');return;}
    const last=down.stroke.points.at(-1)!;
    const r=event.currentTarget.getBoundingClientRect();
    if((['left','top','width','height'] as const).some(k=>Math.abs(r[k]-down.rect[k])>.5)){
      cancelGesture('定位画布大小或位置变化，未提交本笔');return;
    }
    if(Math.hypot((p[0]-last[0])*r.width,(p[1]-last[1])*r.height)<1.5)return;
    if(down.stroke.points.length>=1024){cancelGesture('本笔超过 1024 个路径点，请分成较短笔划');return;}
    down.stroke={...down.stroke,points:[...down.stroke.points,p]};setPath(down.stroke.points);
    workflow.stroke(down.stroke);
  };
  const aspect=frame?frame.descriptor.presentation_width/frame.descriptor.presentation_height:1;
  return <div className="recoverySourceFrame" style={{aspectRatio:aspect}} role="application" aria-label="恢复画笔原图定位区域"
    onPointerDown={event=>{
      stop(event);if(event.button!==0||gesture.current||!frame)return;
      const p=point(event);if(!p||!workflow.beginStroke())return;
      const r=event.currentTarget.getBoundingClientRect(),stroke=newStroke(p,r.width,r.height,settings);
      gesture.current={pointer:event.pointerId,stroke,key,rect:r};setPath([p]);setCursor(p);
      event.currentTarget.setPointerCapture(event.pointerId);workflow.stroke(stroke);
    }}
    onPointerMove={move}
    onPointerUp={event=>{
      stop(event);const down=gesture.current;if(!down||down.pointer!==event.pointerId)return;
      move(event);const final=gesture.current;gesture.current=null;setPath([]);
      if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
      if(final&&final.key===key)workflow.stroke(final.stroke,true);
    }}
    onPointerCancel={event=>{stop(event);if(gesture.current?.pointer===event.pointerId)cancelGesture('指针手势取消，未提交本笔');}}
    onLostPointerCapture={event=>{if(gesture.current?.pointer===event.pointerId)cancelGesture('指针控制中断，未提交本笔');}}
    onPointerLeave={()=>{if(!gesture.current)setCursor(null);}}>
    <canvas ref={canvas}/>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      {path.length>0&&<polyline points={path.map(p=>`${p[0]*100},${p[1]*100}`).join(' ')} className="recoveryGuide"/>}
      {cursor&&<ellipse cx={cursor[0]*100} cy={cursor[1]*100} rx={settings.size/2*Math.min(1,1/aspect)}
        ry={settings.size/2*Math.min(1,aspect)} className="recoveryCursor"/>}
    </svg>
    {!frame&&<span className="recoverySourceWaiting">正在准备下一笔的源图…</span>}
  </div>;
}
