import {useLayoutEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {captureRect,capturePoint,neighbourhood} from '../colorSampleGeometry';
import type {ColorActionOwner} from './useColorActionPicker';
import {COLOR_ACTION_NAMES,COLOR_CHANNEL_NAMES} from './model';
import {ColorActionReadout} from './ColorActionControls';
import '../sourcePatch/sourcePatch.css';

/** Frozen bytes are for aiming only. Rust samples the retained float stage, not canvas pixels. */
export function ColorActionOverlay({owner,clip,box,view}:{owner:ColorActionOwner;clip:HTMLDivElement|null;
  box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const canvas=useRef<HTMLCanvasElement|null>(null),surface=useRef<HTMLDivElement|null>(null);
  const drag=useRef<{pointer:number;x:number;y:number;moved:boolean}|null>(null);
  const {workflow,state}=owner,frame=state.frame;
  const rect=frame?captureRect(box,view,frame.descriptor):{left:0,top:0,width:0,height:0};
  const visible=box.width>0&&box.height>0&&rect.width>0&&rect.height>0;
  const editable=owner.active&&['ready','probing'].includes(state.phase);
  useLayoutEffect(()=>{
    if(!frame||!clip||!canvas.current||!visible)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const context=node.getContext('2d');if(!context)throw Error('无法创建工具输入画布');
      context.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(frame.descriptor);});});
      surface.current?.focus({preventScroll:true});
    }catch(error){workflow.failed(error);}
    return()=>{live=false;drag.current=null;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,workflow,visible]);
  if(!frame||!clip||!state.action)return null;
  const d=frame.descriptor,region=state.region;
  const deltaAt=(x:number,y:number)=>{const origin=drag.current;
    if(!origin)return 0;
    return state.action==='hsl'?(x-origin.x)/Math.max(1,rect.width)*120:(origin.y-y)/Math.max(1,rect.height);
  };
  return <>
    <div ref={surface} className={`sourcePatchSurface ${editable?'editable':'waiting'}`} tabIndex={0}
      role="application" aria-label={`${COLOR_ACTION_NAMES[state.action]}：点击取样，曲线上下拖动，色相左右拖动；Esc 取消`}
      onWheel={event=>event.stopPropagation()} onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
      onPointerDown={event=>{
        event.preventDefault();event.stopPropagation();
        if(event.button!==0||!editable)return;
        const point=capturePoint(event.clientX-box.left,event.clientY-box.top,rect,d.width,d.height);
        if(!point)return;
        const sample=neighbourhood({...point,size:5},d.width,d.height);if(!sample)return;
        surface.current?.focus({preventScroll:true});
        drag.current={pointer:event.pointerId,x:event.clientX,y:event.clientY,moved:false};
        event.currentTarget.setPointerCapture(event.pointerId);workflow.select(sample);
      }}
      onPointerMove={event=>{
        event.stopPropagation();const origin=drag.current;if(!origin||origin.pointer!==event.pointerId||!editable)return;
        if(state.action!=='curve'&&state.action!=='hsl')return;
        const distance=state.action==='hsl'?Math.abs(event.clientX-origin.x):Math.abs(event.clientY-origin.y);
        if(distance<2&&!origin.moved)return;origin.moved=true;workflow.adjust(deltaAt(event.clientX,event.clientY));
      }}
      onPointerUp={event=>{
        event.preventDefault();event.stopPropagation();const origin=drag.current;if(!origin||origin.pointer!==event.pointerId)return;
        if(origin.moved)workflow.adjust(deltaAt(event.clientX,event.clientY));
        drag.current=null;workflow.finish();
        if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={event=>{event.stopPropagation();drag.current=null;workflow.cancel();}}
      onLostPointerCapture={()=>{if(drag.current){drag.current=null;workflow.cancel();}}}
      onKeyDown={event=>{
        if(event.key==='Escape'){event.preventDefault();event.stopPropagation();drag.current=null;workflow.cancel();return;}
        if(!editable||!region||(state.action!=='curve'&&state.action!=='hsl'))return;
        const keys=state.action==='curve'?['ArrowUp','ArrowDown']:['ArrowRight','ArrowLeft'];
        if(keys.includes(event.key)){event.preventDefault();event.stopPropagation();
          const step=(state.action==='hsl'?1:.005)*(event.shiftKey?10:1);
          workflow.adjust(workflow.snapshot().delta+(event.key===keys[0]?step:-step));}
      }}
      onKeyUp={event=>{if(event.key.startsWith('Arrow')){event.preventDefault();event.stopPropagation();workflow.finish();}}}/>
    <div className="colorActionFloating" onPointerDown={event=>event.stopPropagation()} onPointerMove={event=>event.stopPropagation()}
      onPointerUp={event=>event.stopPropagation()} onWheel={event=>event.stopPropagation()} onDoubleClick={event=>event.stopPropagation()}>
      <ColorActionReadout owner={owner}/>
    </div>
    {createPortal(<div className="sourcePatchPreview" aria-label="冻结的工具输入与工具阶段预览">
      <canvas ref={canvas} aria-hidden="true" style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}}/>
      {region&&<div className="colorActionMarker" style={{left:rect.left+region.x/d.width*rect.width,top:rect.top+region.y/d.height*rect.height,
        width:Math.max(3,region.width/d.width*rect.width),height:Math.max(3,region.height/d.height*rect.height)}}/>}
      <div className="sourcePatchViewLabel">{COLOR_ACTION_NAMES[state.action]}{state.action==='curve'&&state.channel?` · ${COLOR_CHANNEL_NAMES[state.channel]}`:''}输入：冻结定位画面，非最终调色效果</div>
      <div className="sourcePatchViewHint">{state.message}</div>
    </div>,clip)}
  </>;
}
