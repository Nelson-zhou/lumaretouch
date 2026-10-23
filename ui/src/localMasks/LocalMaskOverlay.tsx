import {useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as Pointer} from 'react';
import {createPortal} from 'react-dom';
import {captureRect} from '../colorSampleGeometry';
import {normalizedPoint,type Point} from '../sourcePatch/geometry';
import type {LocalMaskOwner} from './useLocalMaskWorkflow';
import {MASK_SOURCE_LABEL,objectMutation,type MaskObject} from './model';
import {savedMaskDisplay} from './display';
import '../sourcePatch/sourcePatch.css';
interface Gesture {pointer:number;key:string;points:Point[]}
export function LocalMaskOverlay({owner,clip,box,view}:{owner:LocalMaskOwner;clip:HTMLDivElement|null;box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const {state,workflow}=owner,frame=state.frame;
  const coverage=useRef<HTMLCanvasElement|null>(null);
  const canvas=useRef<HTMLCanvasElement|null>(null),surface=useRef<HTMLDivElement|null>(null),gesture=useRef<Gesture|null>(null);
  const painted=useRef<typeof frame>(null);
  const [draft,setDraft]=useState<Point[]>([]),[hover,setHover]=useState<Point|null>(null);
  const rect=frame?captureRect(box,view,frame.descriptor):{left:0,top:0,width:0,height:0};
  const visible=box.width>0&&box.height>0&&rect.width>0&&rect.height>0;
  const object=objectMutation(state.mutation)?.object??null;
  const key=[frame?.descriptor.capture_id,frame?.descriptor.ticket,box.left,box.top,rect.left,rect.top,rect.width,rect.height,object?.id].join(':');
  const diameter=useRef(.05);
  const showCoverage=state.showOverlay||state.showLuminanceMap;
  useLayoutEffect(()=>{if(frame&&object?.kind==='brush')diameter.current=object.axes[0][0]*2;},[frame]);
  useLayoutEffect(()=>{
    painted.current=null;
    if(!frame||!clip||!canvas.current||!visible)return;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const context=node.getContext('2d');if(!context)throw Error('无法创建原始源图画布');
      if(frame.descriptor.mask_overlay!==true||!coverage.current)throw Error('原始源图缺少真实蒙版覆盖数据');
      if((frame.descriptor.mask_group_id??null)!==state.groupId)throw Error('冻结覆盖不属于当前蒙版组');
      const display=savedMaskDisplay(frame,state.showLuminanceMap);
      context.putImageData(new ImageData(display.base,node.width,node.height),0,0);
      const mask=coverage.current;mask.width=node.width;mask.height=node.height;
      const maskContext=mask.getContext('2d');if(!maskContext)throw Error('无法显示已保存蒙版覆盖');
      maskContext.putImageData(new ImageData(display.coverage,node.width,node.height),0,0);
      painted.current=frame;
    }catch(error){workflow.failed(error);}
  },[frame,clip,workflow,visible,state.showLuminanceMap,state.groupId]);
  useLayoutEffect(()=>{
    gesture.current=null;setDraft([]);setHover(null);
    if(!frame||!clip||!visible||painted.current!==frame)return;
    // A display toggle does not reset a gesture or produce a second source
    // presentation acknowledgement. Only the original frozen frame is proved.
    let live=true,first=0,second=0;
    first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(frame.descriptor);});});
    surface.current?.focus({preventScroll:true});
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,workflow,visible]);
  useLayoutEffect(()=>{const blur=()=>{if(gesture.current)workflow.gestureCancelled('窗口失焦，本次手势未保留');gesture.current=null;setDraft([]);};window.addEventListener('blur',blur);return()=>window.removeEventListener('blur',blur);},[workflow]);
  useLayoutEffect(()=>{if(gesture.current&&gesture.current.key!==key){gesture.current=null;setDraft([]);workflow.gestureCancelled('视图改变，本次手势未保留');}},[key,workflow]);
  useLayoutEffect(()=>{if(state.phase!=='target'){gesture.current=null;setDraft([]);}},[state.phase]);
  if(!frame||!clip)return null;
  const d=frame.descriptor,editable=state.phase==='target'&&state.draw&&!!object;
  const rangeMode=state.phase==='target'&&!!object&&['color_range','luminance_range'].includes(object.kind);
  const sampling=rangeMode&&Array.isArray(d.sample_valid_rows);
  const local=(x:number,y:number)=>normalizedPoint(x-box.left,y-box.top,rect,d.width,d.height);
  const stop=(event:Pointer<HTMLDivElement>)=>{event.preventDefault();event.stopPropagation();};
  const release=(event:Pointer<HTMLDivElement>)=>{if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);};
  const abandon=()=>{gesture.current=null;setDraft([]);};
  const move=(event:Pointer<HTMLDivElement>)=>{
    stop(event);const point=local(event.clientX,event.clientY);setHover(point);
    const down=gesture.current;if(!down||!editable||down.pointer!==event.pointerId)return;
    if(down.key!==key||!point){abandon();workflow.gestureCancelled('手势离开源图，本次几何未保留');return;}
    const last=down.points.at(-1)!;
    if(Math.hypot((last[0]-point[0])*d.width,(last[1]-point[1])*d.height)<.5)return;
    if(object?.kind==='brush'){
      if(down.points.length>=1024){abandon();workflow.gestureCancelled('笔划过长，本次未保留；请缩短笔划');return;}
      down.points=[...down.points,point];
    }else down.points=[down.points[0],point];
    setDraft(down.points);
  };
  const shape=(points:Point[]):MaskObject|null=>{
    if(!object||!points.length)return null;
    const start=points[0],end=points.at(-1)!;
    if(object.kind==='brush')return {...object,points,axes:[[diameter.current*Math.min(d.width,d.height)/(2*d.width),0],[0,diameter.current*Math.min(d.width,d.height)/(2*d.height)]]};
    if(Math.hypot((end[0]-start[0])*d.width,(end[1]-start[1])*d.height)<1)return null;
    if(object.kind==='linear')return {...object,start,end,cross:[-(end[1]-start[1])*d.height/d.width,(end[0]-start[0])*d.width/d.height]};
    if(object.kind==='radial'){
      const rx=Math.abs(end[0]-start[0]),ry=Math.abs(end[1]-start[1]);
      if(rx*d.width<.5||ry*d.height<.5)return null;
      return {...object,center:start,axes:[[rx,0],[0,ry]]};
    }
    return null;
  };
  const shown=draft.length?shape(draft):state.draw&&state.geometryReady?object:null;
  const contours=(mask:MaskObject|null)=>{
    if(mask?.kind==='brush'&&mask.points.length===1)return <circle cx={mask.points[0][0]*d.width} cy={mask.points[0][1]*d.height} r={Math.abs(mask.axes[0][0])*d.width} fill="#ffb35c" fillOpacity=".4"/>;
    if(mask?.kind==='brush')return <polyline points={mask.points.map(p=>`${p[0]*d.width},${p[1]*d.height}`).join(' ')} fill="none" stroke="#ffb35c" strokeOpacity=".4" strokeWidth={2*Math.abs(mask.axes[0][0])*d.width} strokeLinecap="round" strokeLinejoin="round"/>;
    if(mask?.kind==='linear')return <g stroke="#ffb35c" strokeWidth="2" vectorEffect="non-scaling-stroke"><line x1={mask.start[0]*d.width} y1={mask.start[1]*d.height} x2={mask.end[0]*d.width} y2={mask.end[1]*d.height}/><circle cx={mask.start[0]*d.width} cy={mask.start[1]*d.height} r="4" fill="#303035"/><circle cx={mask.end[0]*d.width} cy={mask.end[1]*d.height} r="4" fill="#ffb35c"/></g>;
    if(mask?.kind==='radial')return <ellipse cx={mask.center[0]*d.width} cy={mask.center[1]*d.height} rx={Math.abs(mask.axes[0][0])*d.width} ry={Math.abs(mask.axes[1][1])*d.height} fill="#ffb35c" fillOpacity=".15" stroke="#ffb35c" vectorEffect="non-scaling-stroke"/>;
    return null;
  };
  return <>
    <div ref={surface} className={`sourcePatchSurface ${editable||sampling?'editable':'waiting'}`} tabIndex={0} role="application" aria-label="原始源图蒙版编辑：拖动绘制，面板确认应用，Esc 取消"
      onWheel={event=>event.stopPropagation()} onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
      onPointerDown={event=>{
        stop(event);if(event.button!==0||(!editable&&!sampling)||gesture.current)return;
        event.currentTarget.focus({preventScroll:true});const point=local(event.clientX,event.clientY);if(!point)return;
        if(sampling){workflow.sample(point);setHover(point);return;}
        workflow.beginGeometry();gesture.current={pointer:event.pointerId,key,points:[point]};setDraft([point]);setHover(point);event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={move} onPointerLeave={()=>{if(!gesture.current)setHover(null);}}
      onPointerUp={event=>{
        stop(event);const down=gesture.current;if(!down||down.pointer!==event.pointerId)return;
        move(event);const current=gesture.current;abandon();release(event);
        if(current&&current.key===key&&editable){const next=shape(current.points);if(next)workflow.geometry(next);else workflow.gestureCancelled('拖动距离太小，未生成几何');}
      }} onPointerCancel={event=>{stop(event);abandon();release(event);workflow.gestureCancelled('手势中断，本次几何未保留');}}
      onLostPointerCapture={event=>{if(gesture.current?.pointer===event.pointerId){abandon();workflow.gestureCancelled('指针控制中断，本次几何未保留');}}}
      onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();abandon();workflow.cancel();}}}/>
    {createPortal(<div className="sourcePatchPreview" aria-hidden="true">
      <canvas ref={canvas} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}}/>
      <canvas ref={coverage} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height,display:showCoverage?'block':'none'}}/>
      <svg className="sourcePatchShapes" width={rect.width} height={rect.height} viewBox={`0 0 ${d.width} ${d.height}`} preserveAspectRatio="none" style={{left:rect.left,top:rect.top}}>
        {contours(shown)}
        {sampling&&hover&&<circle cx={hover[0]*d.width} cy={hover[1]*d.height} r="4" fill="none" stroke="#fff" vectorEffect="non-scaling-stroke"/>}
        {editable&&object?.kind==='brush'&&hover&&<circle cx={hover[0]*d.width} cy={hover[1]*d.height} r={diameter.current*Math.min(d.width,d.height)/2} fill="none" stroke="#ffb35c" vectorEffect="non-scaling-stroke"/>}
      </svg>
      <div className="sourcePatchViewLabel">{state.showLuminanceMap?'源图亮度诊断：8 位代理 RGB → 线性 Y → 显示灰度，不是最终效果或当前来源图精度验证':MASK_SOURCE_LABEL}{d.mask_group_id?'；范围：当前独立局部调色组':'；范围：旧编辑器蒙版'}{d.mask_suspended?`；已保存蒙版暂停：${d.mask_suspended}`:showCoverage?'；青色：已保存组合范围（不是本次草稿）':''}</div>
      <div className="sourcePatchViewHint">{state.showLuminanceMap?'灰色棋盘表示构图填充，不参与亮度；吸管仍读原始 RGB，不读灰度或青色。':''}{state.draw?'橙色仅表示本次几何草稿，不代表合成蒙版；拖动可重画，面板点击应用。':sampling?'点击源图取样：8 位代理近似值；参数或反相修改需应用后重新查看已保存范围。':rangeMode?'此画面未提供采样有效域，吸管不可用；可在面板手动设定范围。':'原始源图已冻结；请在蒙版面板确认或关闭。'}</div>
    </div>,clip)}
  </>;
}
