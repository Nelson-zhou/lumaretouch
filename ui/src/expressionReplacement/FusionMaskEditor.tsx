// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useId,useRef,useState,type PointerEvent} from 'react';
import {LIMITS,type Face,type FusionMask,type Point,type Source,type Stroke,type Image} from './model';
import {VerifiedImage} from './VerifiedImage';
/** Overlay only: no pixels are read, fetched, edited or promoted to native output here. */
export function FusionMaskEditor({source,image,label,onReady,face,value,disabled,onChange}:{source:Source;image:Image;label:string;onReady:(ready:boolean)=>void;face:Face;value:FusionMask;disabled:boolean;onChange:(value:FusionMask)=>void}){
  const [mode,setMode]=useState<'add'|'erase'>('add'),[radius,setRadius]=useState(12),[drawing,setDrawing]=useState<Stroke|null>(null),[error,setError]=useState('');
  const active=useRef<{pointer:number;stroke:Stroke}|null>(null),maskId=`expression-fusion-${useId().replaceAll(':','')}`;
  const maxRadius=Math.max(1,Math.floor(Math.min(face.crop.width,face.crop.height)/2));
  const context=`${source.asset_sha256}:${face.face_ref.face_instance_id}:${face.landmarks_sha256}`;
  useEffect(()=>{active.current=null;setDrawing(null);setRadius(old=>Math.min(old,maxRadius));setError('');},[context,maxRadius,disabled]);
  const point=(event:PointerEvent<SVGSVGElement>):Point|null=>{
    const matrix=event.currentTarget.getScreenCTM();if(!matrix)return null;
    const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),c=face.crop;
    if(p.x<c.left||p.y<c.top||p.x>c.left+c.width-1||p.y>c.top+c.height-1)return null;
    return [p.x/(source.width-1),p.y/(source.height-1)];
  };
  function begin(event:PointerEvent<SVGSVGElement>){
    if(disabled||active.current||event.button!==0)return;
    const p=point(event);if(!p)return;
    if(value.strokes.length>=LIMITS.strokes){setError('笔迹已达上限，请撤销或清空；不会截断笔迹。');return;}
    event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);
    const stroke:Stroke={mode,radius_px:Math.min(radius,maxRadius),points:[p]};
    active.current={pointer:event.pointerId,stroke};setDrawing(stroke);setError('');
  }
  function move(event:PointerEvent<SVGSVGElement>){
    const draft=active.current;if(disabled||!draft||draft.pointer!==event.pointerId)return;
    const p=point(event);if(!p)return;const old=draft.stroke.points.at(-1)!;
    if(Math.hypot((p[0]-old[0])*(source.width-1),(p[1]-old[1])*(source.height-1))<.5)return;
    if(value.strokes.reduce((n,s)=>n+s.points.length,0)+draft.stroke.points.length>=LIMITS.points){active.current=null;setDrawing(null);setError('本笔迹点数超过上限，整笔已取消；不会静默截断。');return;}
    const stroke:Stroke={...draft.stroke,points:[...draft.stroke.points,p]};active.current={...draft,stroke};setDrawing(stroke);
  }
  function finish(event:PointerEvent<SVGSVGElement>){
    const draft=active.current;if(!draft||draft.pointer!==event.pointerId)return;
    active.current=null;setDrawing(null);if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    if(!disabled)onChange({...value,strokes:[...value.strokes,draft.stroke]});
  }
  function abort(){active.current=null;setDrawing(null);}
  const paths=[...value.strokes,...(drawing?[drawing]:[])];
  function shape(stroke:Stroke,index:number){
    const color=stroke.mode==='add'?'white':'black',points=stroke.points.map(p=>`${p[0]*(source.width-1)},${p[1]*(source.height-1)}`).join(' ');
    return stroke.points.length===1?<circle key={index} cx={stroke.points[0][0]*(source.width-1)} cy={stroke.points[0][1]*(source.height-1)} r={stroke.radius_px} fill={color}/>
      :<polyline key={index} points={points} stroke={color} strokeWidth={stroke.radius_px*2} strokeLinecap="round" strokeLinejoin="round" fill="none"/>;
  }
  return <div className="expression-mask-editor">
    <VerifiedImage image={image} source={source} label={label} onReady={onReady}><svg className="expression-fusion-overlay" viewBox={`-.5 -.5 ${source.width} ${source.height}`} preserveAspectRatio="none"
      role="img" aria-label="在完整当前照片上手绘融合范围，只允许选中面部上下文内的像素" style={{pointerEvents:disabled?'none':'auto'}}
      onPointerDown={begin} onPointerMove={move} onPointerUp={finish} onPointerCancel={abort} onLostPointerCapture={abort}>
      <defs><mask id={maskId} maskUnits="userSpaceOnUse" x={-.5} y={-.5} width={source.width} height={source.height}>
        <rect x={-.5} y={-.5} width={source.width} height={source.height} fill="black"/>{paths.map(shape)}
      </mask></defs>
      <rect x={face.crop.left-.5} y={face.crop.top-.5} width={face.crop.width} height={face.crop.height} fill="#54e8cc" opacity={.35} mask={`url(#${maskId})`}/>
      <rect x={face.crop.left-.5} y={face.crop.top-.5} width={face.crop.width} height={face.crop.height} fill="none" stroke="#f3c66d" strokeWidth={Math.max(1,source.width/700)}/>
    </svg></VerifiedImage>
    <div className="expression-mask-tools">
      <label>融合笔<select value={mode} disabled={disabled} onChange={event=>{abort();setMode(event.currentTarget.value as 'add'|'erase');}}><option value="add">添加融合</option><option value="erase">擦回当前照片</option></select></label>
      <label>源像素半径 <output>{Math.min(radius,maxRadius)}</output><input aria-label="融合笔源像素半径" type="range" min={1} max={maxRadius} step={1} value={Math.min(radius,maxRadius)} disabled={disabled} onChange={event=>{abort();setRadius(Number(event.currentTarget.value));}}/></label>
      <button type="button" disabled={disabled||!value.strokes.length} onClick={()=>{abort();onChange({...value,strokes:value.strokes.slice(0,-1)});}}>撤销最后一笔</button>
      <button type="button" disabled={disabled||!value.strokes.length} onClick={()=>{abort();onChange({...value,strokes:[]});}}>清空融合</button>
      <output>{value.strokes.length}/{LIMITS.strokes} 笔</output>
      <p>青色仅为手绘范围示意，不是最终蒙版。实际融合还受目标及素材的可用范围、保护区和原尺寸采样共同限制；改动后需重新生成并查看候选。</p>
      {error&&<p role="alert">{error}</p>}
    </div>
  </div>;
}
