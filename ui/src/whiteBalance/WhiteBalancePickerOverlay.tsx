import {useLayoutEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {captureRect,capturePoint,neighbourhood} from '../colorSampleGeometry';
import type {WhiteBalancePickerOwner} from './useWhiteBalancePicker';
import {WB_PICKER_LABEL} from './pickerWorkflow';
import '../sourcePatch/sourcePatch.css';

/** Display bytes are only a frozen aiming view. Only integer coordinates go to Rust. */
export function WhiteBalancePickerOverlay({owner,clip,box,view}:{owner:WhiteBalancePickerOwner;clip:HTMLDivElement|null;
  box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const canvas=useRef<HTMLCanvasElement|null>(null),surface=useRef<HTMLDivElement|null>(null);
  const {workflow,state}=owner,frame=state.frame;
  const rect=frame?captureRect(box,view,frame.descriptor):{left:0,top:0,width:0,height:0};
  const visible=box.width>0&&box.height>0&&rect.width>0&&rect.height>0;
  useLayoutEffect(()=>{
    if(!frame||!clip||!canvas.current||!visible)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const context=node.getContext('2d');if(!context)throw Error('无法创建白平衡输入画布');
      context.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(frame.descriptor);});});
      surface.current?.focus({preventScroll:true});
    }catch(error){workflow.failed(error);}
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,workflow,visible]);
  if(!frame||!clip)return null;
  return <>
    <div ref={surface} className={`sourcePatchSurface ${state.phase==='ready'?'editable':'waiting'}`} tabIndex={0}
      role="application" aria-label="白平衡中性吸管：点击灰白区域取样，Esc 取消"
      onWheel={event=>event.stopPropagation()} onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
      onPointerDown={event=>{
        event.preventDefault();event.stopPropagation();
        if(event.button!==0||state.phase!=='ready')return;
        const d=frame.descriptor,point=capturePoint(event.clientX-box.left,event.clientY-box.top,rect,d.width,d.height);
        if(!point)return;const region=neighbourhood({...point,size:5},d.width,d.height);
        if(region)void workflow.apply(region);
      }}
      onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();workflow.cancel();}}}/>
    {createPortal(<div className="sourcePatchPreview" aria-hidden="true">
      <canvas ref={canvas} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}}/>
      <div className="sourcePatchViewLabel">{WB_PICKER_LABEL}</div>
      <div className="sourcePatchViewHint">{state.message}</div>
    </div>,clip)}
  </>;
}
