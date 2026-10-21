import {useLayoutEffect,useRef} from 'react';
import {createPortal} from 'react-dom';
import {captureRect,capturePoint} from '../colorSampleGeometry';
import type {ColorSampler} from '../useColorSampler';
export function ColorSampleOverlay({sampler,clip,box,view}:{sampler:ColorSampler;clip:HTMLDivElement|null;
  box:{left:number;top:number;width:number;height:number};view:{zoom:number;x:number;y:number}}){
  const canvas=useRef<HTMLCanvasElement|null>(null),down=useRef<{key:string;pointerId:number;x:number;y:number}|null>(null);
  const frame=sampler.ui.frame;
  useLayoutEffect(()=>{
    down.current=null;
    if(!frame||!clip||!canvas.current)return;
    let live=true,first=0,second=0;
    try{
      const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
      const ctx=node.getContext('2d');if(!ctx)throw new Error('无法创建取色画布');
      ctx.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);
      first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void sampler.presented(frame.descriptor);});});
    }catch(error){sampler.failed(error);}
    return ()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[frame,clip,sampler.presented,sampler.failed]);
  if(!frame||!clip)return null;
  const d=frame.descriptor,rect=captureRect(box,view,d);
  const key=[d.capture_id,d.ticket,box.left,box.top,box.width,box.height,rect.left,rect.top,rect.width,rect.height].join(':');
  const eligible=sampler.ui.phase==='eligible'||sampler.ui.phase==='sampling';
  const local=(x:number,y:number)=>capturePoint(x-box.left,y-box.top,rect,d.width,d.height);
  const point=sampler.ui.point;
  return <>
    <div tabIndex={0} role="application" aria-label="点击图片读取颜色；方向键移动取样点，Esc 退出"
      style={{position:'absolute',inset:0,zIndex:4,cursor:eligible?'crosshair':'wait'}}
      onDoubleClick={e=>e.stopPropagation()}
      onPointerDown={e=>{if(e.button!==0)return;e.stopPropagation();e.preventDefault();e.currentTarget.focus();
        const p=local(e.clientX,e.clientY);down.current=eligible&&p?{key,pointerId:e.pointerId,x:e.clientX,y:e.clientY}:null;
        e.currentTarget.setPointerCapture(e.pointerId);}}
      onPointerUp={e=>{if(e.button!==0)return;e.stopPropagation();const start=down.current;down.current=null;
        if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
        const p=local(e.clientX,e.clientY);
        if(eligible&&start&&start.key===key&&start.pointerId===e.pointerId&&p&&Math.hypot(e.clientX-start.x,e.clientY-start.y)<5)sampler.pick({...p,size:sampler.size});}}
      onPointerCancel={()=>{down.current=null;}}
      onKeyDown={e=>{if(!eligible||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Enter'].includes(e.key))return;
        e.preventDefault();e.stopPropagation();const p=point??{x:Math.floor(d.width/2),y:Math.floor(d.height/2)};
        sampler.pick({x:Math.max(0,Math.min(d.width-1,p.x+(e.key==='ArrowRight'?1:e.key==='ArrowLeft'?-1:0))),
          y:Math.max(0,Math.min(d.height-1,p.y+(e.key==='ArrowDown'?1:e.key==='ArrowUp'?-1:0))),size:sampler.size});}} />
    {createPortal(<div style={{position:'absolute',inset:0,background:'#15171b',pointerEvents:'none'}}>
      <canvas ref={canvas} style={{position:'absolute',left:rect.left,top:rect.top,width:rect.width,height:rect.height}} />
      {point&&<span style={{position:'absolute',left:rect.left+(point.x+.5)*rect.width/d.width,
        top:rect.top+(point.y+.5)*rect.height/d.height,width:10,height:10,border:'1px solid white',
        boxShadow:'0 0 0 1px black',borderRadius:'50%',transform:'translate(-50%,-50%)'}}/>}
    </div>,clip)}
  </>;
}
