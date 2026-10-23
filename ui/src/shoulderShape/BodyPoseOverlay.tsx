// SPDX-License-Identifier: GPL-3.0-or-later
import {observed,refKey,type BodyChoice,type BodyRef} from './model';
const edges=[[11,12],[11,13],[12,14],[11,23],[12,24],[23,24]] as const;
/** Mount in the canonical image viewport; do not place on an already warped frame.
 * Every dot is an actual backend output. No face-derived body box/skeleton. */
export function BodyPoseOverlay({bodies,selected,onSelect}:{bodies:BodyChoice[];selected:BodyRef|null;onSelect:(ref:BodyRef)=>void}){
 return <svg viewBox="0 0 1 1" preserveAspectRatio="none" style={{position:'absolute',inset:0,width:'100%',height:'100%',overflow:'hidden'}} aria-label="真实身体定位点；虚线点不作为变形依据">
  {bodies.map(body=><g key={refKey(body.body_ref)} stroke={refKey(selected)===refKey(body.body_ref)?'#63e6cb':'#f5c56b'} fill="none">
   {edges.map(([a,b])=>observed(body.points[a])&&observed(body.points[b])?<line key={`${a}-${b}`} x1={body.points[a].x} y1={body.points[a].y} x2={body.points[b].x} y2={body.points[b].y} strokeWidth={.002} pointerEvents="none"/>:null)}
   {body.points.filter(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)).map(p=><circle key={p.index} cx={p.x} cy={p.y} r={.004} strokeWidth={.0015} opacity={observed(p)?1:.25} strokeDasharray={observed(p)?undefined:'.002 .001'} pointerEvents="none"/>)}
   {[11,12].filter(i=>observed(body.points[i])).map(i=><circle key={`pick-${i}`} cx={body.points[i].x} cy={body.points[i].y} r={.015} fill="transparent" strokeWidth={.001} role="button" tabIndex={0} aria-label="选择此身体，不推断人脸关联" onClick={()=>onSelect(body.body_ref)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(body.body_ref);}}}/>)}
  </g>)}
 </svg>;
}
