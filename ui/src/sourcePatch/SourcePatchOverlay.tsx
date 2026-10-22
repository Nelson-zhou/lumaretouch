import {useId,useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {createPortal} from 'react-dom';
import {captureRect} from '../colorSampleGeometry';
import type {SourcePatchOwner} from './useSourcePatchWorkflow';
import {appendLasso,center,insidePolygon,normalizedPoint,type Point} from './geometry';
import {SOURCE_PATCH_LABEL} from './workflow';
import './sourcePatch.css';

interface Gesture {kind:'target'|'source';pointerId:number;key:string;start:Point;offset:Point;points:Point[]}
export function SourcePatchOverlay({owner,clip,box,view}:{owner:SourcePatchOwner;clip:HTMLDivElement|null;
  box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const canvas=useRef<HTMLCanvasElement|null>(null),surface=useRef<HTMLDivElement|null>(null);
  const gesture=useRef<Gesture|null>(null),[draft,setDraft]=useState<Point[]>([]);
  const arrowId=`source-patch-arrow-${useId().replaceAll(':','')}`;
  const {workflow,state}=owner,frame=state.frame;
  const rect=frame?captureRect(box,view,frame.descriptor):{left:0,top:0,width:0,height:0};
  const hasVisibleArea=box.width>0&&box.height>0&&rect.width>0&&rect.height>0;
  const key=[frame?.descriptor.capture_id,frame?.descriptor.ticket,box.left,box.top,rect.left,rect.top,rect.width,rect.height].join(':');
  useLayoutEffect(()=>{
    gesture.current=null;setDraft([]);
    if(!frame||!clip||!canvas.current||!hasVisibleArea)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const context=node.getContext('2d');if(!context)throw Error('无法创建修补取样画布');
      context.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(frame.descriptor);});});
      surface.current?.focus({preventScroll:true});
    }catch(error){workflow.failed(error);}
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,workflow,hasVisibleArea]);
  useLayoutEffect(()=>{
    const down=gesture.current;
    if(down&&down.key!==key){gesture.current=null;setDraft([]);workflow.cancel('视图尺寸已变化，未提交的手势已取消');}
  },[key,workflow]);
  useLayoutEffect(()=>{
    if(state.phase!=='target'&&state.phase!=='source'){gesture.current=null;setDraft([]);}
  },[state.phase]);
  if(!frame||!clip)return null;
  const d=frame.descriptor,editable=state.phase==='target'||state.phase==='source';
  const local=(x:number,y:number)=>normalizedPoint(x-box.left,y-box.top,rect,d.width,d.height);
  const pointString=(points:Point[],offset:Point=[0,0])=>points.map(([x,y])=>`${(x+offset[0])*rect.width},${(y+offset[1])*rect.height}`).join(' ');
  const target=center(state.polygon),source:Point=[target[0]+state.offset[0],target[1]+state.offset[1]];
  const release=(event:ReactPointerEvent<HTMLDivElement>)=>{
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  };
  const stop=(event:ReactPointerEvent<HTMLDivElement>)=>{event.stopPropagation();event.preventDefault();};
  const move=(event:ReactPointerEvent<HTMLDivElement>)=>{
    stop(event);const down=gesture.current;if(!editable||!down||down.pointerId!==event.pointerId||down.key!==key)return;
    if(down.kind==='target'){
      const point=local(event.clientX,event.clientY);if(!point)return;
      down.points=appendLasso(down.points,point);setDraft(down.points);
    }else{
      // Extrapolate pointer motion, then clamp the complete source polygon inside the frame.
      const p:Point=[(event.clientX-box.left-rect.left)/rect.width,(event.clientY-box.top-rect.top)/rect.height];
      workflow.setOffset([down.offset[0]+p[0]-down.start[0],down.offset[1]+p[1]-down.start[1]]);
    }
  };
  return <>
    <div ref={surface} className={`sourcePatchSurface ${editable?'editable':'waiting'}`} tabIndex={0} role="application"
      aria-label="来源区域修补：圈选目标，拖动来源；应用按钮才提交，Esc 取消"
      onWheel={event=>{event.stopPropagation();}}
      onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
      onPointerDown={event=>{
        stop(event);if(event.button!==0||!editable||gesture.current)return;
        event.currentTarget.focus({preventScroll:true});const point=local(event.clientX,event.clientY);if(!point)return;
        if(state.phase==='source'&&!insidePolygon(point,state.polygon,state.offset))return;
        gesture.current={kind:state.phase==='target'?'target':'source',pointerId:event.pointerId,key,start:point,offset:[...state.offset],points:[point]};
        if(state.phase==='target')setDraft([point]);
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={move}
      onPointerUp={event=>{
        stop(event);const down=gesture.current;if(!down||down.pointerId!==event.pointerId)return;
        move(event);gesture.current=null;release(event);
        if(down.key!==key){setDraft([]);return;}
        if(down.kind==='target'){
          let points=down.points;
          if(points.length>3&&Math.hypot(points[0][0]-points.at(-1)![0],points[0][1]-points.at(-1)![1])<0.0005)points=points.slice(0,-1);
          workflow.setPolygon(points);setDraft([]);
        }
      }}
      onPointerCancel={event=>{stop(event);gesture.current=null;setDraft([]);release(event);workflow.cancel('手势已取消，未提交修补');}}
      onLostPointerCapture={event=>{
        if(gesture.current?.pointerId===event.pointerId){gesture.current=null;setDraft([]);workflow.cancel('指针控制已中断，未提交修补');}
      }}
      onKeyDown={event=>{
        if(event.key==='Escape'){event.preventDefault();event.stopPropagation();gesture.current=null;setDraft([]);workflow.cancel();return;}
        if(state.phase!=='source'||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
        event.preventDefault();event.stopPropagation();const step=event.shiftKey?10:1;
        workflow.setOffset([state.offset[0]+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0)/d.width,
          state.offset[1]+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0)/d.height]);
      }} />
    {createPortal(<div className="sourcePatchPreview" aria-hidden="true">
      <canvas ref={canvas} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}}/>
      <svg className="sourcePatchShapes" width={rect.width} height={rect.height} viewBox={`0 0 ${rect.width||1} ${rect.height||1}`}
        style={{left:rect.left,top:rect.top}}>
        <defs><marker id={arrowId} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#74dcff"/>
        </marker></defs>
        {draft.length>0&&<polyline className="sourcePatchTarget" points={pointString(draft)}/>}
        {state.polygon.length>0&&<>
          <polygon className="sourcePatchTarget" points={pointString(state.polygon)}/>
          <polygon className="sourcePatchSource" points={pointString(state.polygon,state.offset)}/>
          <line className="sourcePatchArrow" x1={source[0]*rect.width} y1={source[1]*rect.height}
            x2={target[0]*rect.width} y2={target[1]*rect.height} markerEnd={`url(#${arrowId})`}/>
          <text className="sourcePatchTargetLabel" x={target[0]*rect.width} y={target[1]*rect.height+18}>目标</text>
          <text className="sourcePatchSourceLabel" x={source[0]*rect.width} y={source[1]*rect.height-12}>来源</text>
        </>}
      </svg>
      <div className="sourcePatchViewLabel">{SOURCE_PATCH_LABEL}</div>
      <div className="sourcePatchViewHint">{state.message}</div>
    </div>,clip)}
  </>;
}
