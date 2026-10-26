// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from the project current-photo fabric UI; canonical ownership is unchanged.
import {useEffect,useRef,useState,type PointerEvent} from 'react';
import {LIMITS,ROLE_LABELS,imageUrl,type Brush,type Image,type Masks,type Role,type Source} from './model';
type Draft = {role:Role;brush:Brush;pointer:number;binding:string};
const ROLES:Role[]=['limb','target','protect'];
const COLORS:Record<Role,string>={limb:'#4ab4ff',target:'#ffb43c',protect:'#ff4d90'};
export function HandToneMaskEditor({binding,source,image,masks,disabled,onChange,onReady,onDraftStart}:{
  binding:string;source:Source;image:Image;masks:Masks;disabled:boolean;
  onChange:(next:Masks)=>void;onReady:(ready:boolean)=>void;onDraftStart:()=>void;
}) {
  const canvas=useRef<HTMLCanvasElement>(null),active=useRef<Draft|null>(null);
  const [draft,setDraft]=useState<Draft|null>(null),[role,setRole]=useState<Role>('limb');
  const [subtract,setSubtract]=useState(false),[radius,setRadius]=useState(1.5),[showMask,setShowMask]=useState(true);
  const [loaded,setLoaded]=useState(false);
  const latest=useRef({binding,disabled,masks,onChange,onReady,onDraftStart});latest.current={binding,disabled,masks,onChange,onReady,onDraftStart};
  useEffect(()=>{active.current=null;setDraft(null);},[binding,disabled]);
  useEffect(()=>()=>{active.current=null;},[]);
  useEffect(()=>{
    const node=canvas.current,ctx=node?.getContext('2d');if(!node||!ctx)return;
    node.width=image.width;node.height=image.height;ctx.clearRect(0,0,node.width,node.height);
    if(!showMask)return;
    for(const r of ROLES){
      // Each role is separately composited so subtract removes only its own draft mask.
      const layer=document.createElement('canvas');layer.width=node.width;layer.height=node.height;const c=layer.getContext('2d');if(!c)continue;
      const brushes=[...masks[r].objects,...(draft?.role===r?[draft.brush]:[])];
      c.scale(node.width,node.height);c.lineCap='round';c.lineJoin='round';
      for(const brush of brushes){
        if(!brush.enabled||!brush.points.length)continue;
        const [[a,b],[d,e]]=brush.axes,det=a*e-b*d;if(Math.abs(det)<1e-12)continue;
        c.save();c.transform(a,b,d,e,0,0);c.globalCompositeOperation=brush.operation==='subtract'?'destination-out':'source-over';
        c.strokeStyle=COLORS[r];c.fillStyle=COLORS[r];c.lineWidth=2;c.beginPath();
        const points=brush.points.map(([x,y])=>[(e*x-d*y)/det,(-b*x+a*y)/det]);
        points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));
        if(points.length===1){c.arc(points[0][0],points[0][1],1,0,Math.PI*2);c.fill();}else c.stroke();c.restore();
      }
      ctx.globalAlpha=r===role ? .55 : .22;ctx.drawImage(layer,0,0);ctx.globalAlpha=1;
    }
  },[masks,draft,showMask,role,image.width,image.height]);
  const ready=loaded&&!disabled;
  const point=(event:PointerEvent<HTMLCanvasElement>):[number,number]|null=>{
    const rect=event.currentTarget.getBoundingClientRect();if(rect.width<=0||rect.height<=0)return null;
    const x=(event.clientX-rect.left)/rect.width,y=(event.clientY-rect.top)/rect.height;
    return x>=0&&x<=1&&y>=0&&y<=1?[x,y]:null;
  };
  const cancel=(event:PointerEvent<HTMLCanvasElement>)=>{active.current=null;setDraft(null);if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);};
  const finish=(event:PointerEvent<HTMLCanvasElement>)=>{
    const row=active.current;if(!row||row.pointer!==event.pointerId)return;cancel(event);
    if(latest.current.binding!==row.binding||latest.current.disabled)return;
    const old=latest.current.masks;latest.current.onChange({...old,[row.role]:{...old[row.role],objects:[...old[row.role].objects,row.brush]}});
  };
  const pointsCount=ROLES.reduce((sum,r)=>sum+masks[r].objects.reduce((n,b)=>n+b.points.length,0),0);
  return <section aria-label="手部中性灰蒙版编辑">
    <div className="prow">{ROLES.map(r=><button type="button" key={r} disabled={!ready||!!draft} aria-pressed={role===r}
      onClick={()=>{setRole(r);if(r==='protect')setSubtract(false);}}>{ROLE_LABELS[r]}</button>)}</div>
    <div className="prow"><button type="button" disabled={!ready||!!draft} aria-pressed={!subtract} onClick={()=>setSubtract(false)}>添加画笔</button>
      <button type="button" disabled={!ready||!!draft||role==='protect'} aria-pressed={subtract} onClick={()=>setSubtract(true)}>减去画笔</button>
      <button type="button" disabled={!!draft} aria-pressed={showMask} onClick={()=>setShowMask(!showMask)}>{showMask?'显示原图':'显示蒙版'}</button></div>
    <label>画笔半径 {radius.toFixed(2)}%<input type="range" min="0.1" max="8" step="0.1" value={radius} disabled={!ready||!!draft} onChange={e=>setRadius(Number(e.target.value))}/></label>
    <p><small>蓝：同一只手的可见皮肤；橙：局部明暗／关节纹；粉：保护。请保护指甲、饰品、纹身和边缘，勿跨人物或跨手绘制。</small></p>
    <div style={{position:'relative',width:'100%',aspectRatio:`${image.width}/${image.height}`}}>
      <img src={imageUrl(image)} alt="当前照片的完整手部中性灰标记来源" draggable={false} style={{display:'block',width:'100%',height:'100%'}}
        onLoad={event=>{const ok=event.currentTarget.naturalWidth===image.width&&event.currentTarget.naturalHeight===image.height;setLoaded(ok);latest.current.onReady(ok);}}
        onError={()=>{setLoaded(false);latest.current.onReady(false);}}/>
      <canvas ref={canvas} aria-label="在原图绘制手部皮肤、局部明暗与保护区域" style={{position:'absolute',inset:0,width:'100%',height:'100%',touchAction:'none'}}
        onPointerDown={event=>{
          if(!ready||active.current||event.button!==0||pointsCount>=LIMITS.totalPoints||masks[role].objects.length>=LIMITS.strokes)return;
          const p=point(event);if(!p)return;event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);latest.current.onDraftStart();
          const px=radius/100*Math.min(source.width,source.height);
          const brush:Brush={id:crypto.randomUUID().replaceAll('-',''),name:ROLE_LABELS[role],enabled:true,operation:subtract&&role!=='protect'?'subtract':'add',kind:'brush',opacity:1,feather:0,points:[p],axes:[[px/source.width,0],[0,px/source.height]]};
          const row={role,brush,pointer:event.pointerId,binding};active.current=row;setDraft(row);
        }} onPointerMove={event=>{
          const row=active.current;if(!row||row.pointer!==event.pointerId||!ready||row.binding!==binding||row.brush.points.length>=LIMITS.pointsPerStroke||row.brush.points.length+pointsCount>=LIMITS.totalPoints)return;
          const p=point(event);if(!p)return;const last=row.brush.points[row.brush.points.length-1];if(Math.hypot(p[0]-last[0],p[1]-last[1])<.0005)return;
          const next={...row,brush:{...row.brush,points:[...row.brush.points,p]}};active.current=next;setDraft(next);
        }} onPointerUp={finish} onPointerCancel={cancel} onLostPointerCapture={()=>{active.current=null;setDraft(null);}}/>
    </div>
    <div className="prow"><button type="button" disabled={!ready||!!draft||!masks[role].objects.length} onClick={()=>onChange({...masks,[role]:{...masks[role],objects:masks[role].objects.slice(0,-1)}})}>撤销当前区域最后一笔</button>
      <button type="button" disabled={!ready||!!draft||!masks[role].objects.length} onClick={()=>onChange({...masks,[role]:{...masks[role],objects:[]}})}>清空当前区域草稿</button></div>
  </section>;
}
