import {useEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import {stroke,type Brush,type Stroke,type Review} from './model';
interface Gesture {pointer:number;rect:DOMRect;stroke:Stroke}
export function StudioCanvas({image,brush,showMask,locked,onStroke}:{image:Review;brush:Brush;showMask:boolean;locked:boolean;onStroke:(s:Stroke)=>void}){
 const gesture=useRef<Gesture|null>(null),[path,setPath]=useState<Stroke|null>(null),[cursor,setCursor]=useState<[number,number]|null>(null);
 const cancel=()=>{gesture.current=null;setPath(null);};
 useEffect(()=>{cancel();},[image.source,locked]);
 useEffect(()=>{const blur=()=>cancel();window.addEventListener('blur',blur);return()=>window.removeEventListener('blur',blur);},[]);
 const point=(e:ReactPointerEvent<HTMLDivElement>):[number,number,number]|null=>{const r=e.currentTarget.getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;return r.width>0&&r.height>0&&x>=0&&y>=0&&x<=1&&y<=1?[x,y,e.pointerType==='pen'?Math.min(1,Math.max(0,e.pressure)):1]:null;};
 function move(e:ReactPointerEvent<HTMLDivElement>,final=false){
  e.preventDefault();e.stopPropagation();const p=point(e);setCursor(p?[p[0],p[1]]:null);const g=gesture.current;if(!g||g.pointer!==e.pointerId)return;
  const r=e.currentTarget.getBoundingClientRect();if(!p||(['left','top','width','height'] as const).some(k=>Math.abs(r[k]-g.rect[k])>.5)){cancel();return;}
  const last=g.stroke.points.at(-1)!;
  if(final&&e.pointerType==='pen')p[2]=last[2];
  if(Math.hypot((p[0]-last[0])*r.width,(p[1]-last[1])*r.height)>=1.5){
   if(g.stroke.points.length>=2048){cancel();return;}
   g.stroke={...g.stroke,points:[...g.stroke.points,p]};setPath(g.stroke);
  }
 }
 const aspect=image.source_width/image.source_height;
 return <div className="studioSource" style={{aspectRatio:aspect}} role="application" aria-label="未裁剪原图标记画布"
  onPointerDown={e=>{e.preventDefault();e.stopPropagation();if(locked||e.button!==0||gesture.current)return;const p=point(e);if(!p)return;const r=e.currentTarget.getBoundingClientRect(),s=stroke(p,r.width,r.height,brush);gesture.current={pointer:e.pointerId,rect:r,stroke:s};setPath(s);e.currentTarget.setPointerCapture(e.pointerId);}}
  onPointerMove={e=>move(e)} onPointerUp={e=>{move(e,true);const g=gesture.current;if(g?.pointer===e.pointerId){gesture.current=null;setPath(null);onStroke(g.stroke);}if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}
  onPointerCancel={cancel} onLostPointerCapture={cancel} onPointerLeave={()=>{if(!gesture.current)setCursor(null);}}>
  <img src={image.source} alt="原始源图，未裁剪、未塑形"/><img className={showMask?'studioMask':'studioMask hidden'} src={image.mask} alt="当前标记覆盖度"/>
  <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
   {path&&<polyline points={path.points.map(p=>`${p[0]*100},${p[1]*100}`).join(' ')} className="studioPath"/>}
   {cursor&&<ellipse cx={cursor[0]*100} cy={cursor[1]*100} rx={brush.size/2*Math.min(1,1/aspect)} ry={brush.size/2*Math.min(1,aspect)} className="studioCursor"/>}
  </svg>
 </div>;
}
