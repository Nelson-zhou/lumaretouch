import {useEffect,useRef,useState} from 'react';
import type {PointerEvent} from 'react';
import type {HairMask} from './model';
import type {MaskObject} from '../localMasks/model';
type Point=[number,number];
/** Dedicated uncropped SOURCE image. No reverse mapping from the retouched canvas. */
export function HairSourceEditor({source,width,height,value,onChange,disabled}:{source:string;width:number;height:number;value:HairMask;onChange:(v:HairMask)=>void;disabled:boolean}){
  const canvas=useRef<HTMLCanvasElement>(null),stroke=useRef<Point[]|null>(null);
  const [subtract,setSubtract]=useState(false),[radius,setRadius]=useState(2),[draft,setDraft]=useState<Point[]>([]),[zoom,setZoom]=useState(1),[pan,setPan]=useState(false);
  const aspect=height/width;
  const remainingPoints=Math.max(0,8192-value.objects.reduce((total,object)=>total+(object.kind==='brush'?object.points.length:0),0));
  function point(event:PointerEvent<HTMLCanvasElement>):Point {
    const b=event.currentTarget.getBoundingClientRect();
    return [Math.max(0,Math.min(1,(event.clientX-b.left)/b.width)),Math.max(0,Math.min(1,(event.clientY-b.top)/b.height))];
  }
  useEffect(()=>{stroke.current=null;setDraft([]);},[source,disabled]);
  useEffect(()=>{
    const node=canvas.current,ctx=node?.getContext('2d');if(!node||!ctx)return;
    node.width=Math.max(1,Math.round(1200/Math.max(1,aspect)));node.height=Math.max(1,Math.round(1200*Math.min(1,aspect)));ctx.clearRect(0,0,node.width,node.height);
    function draw(points:Point[],axes:[Point,Point],remove:boolean){
      const [[vx,vy],[wx,wy]]=axes,det=vx*wy-vy*wx;
      if(!points.length||Math.abs(det)<1e-12)return;
      const mapped=points.map(([x,y])=>[(wy*x-wx*y)/det,(-vy*x+vx*y)/det] as Point);
      ctx!.save();ctx!.scale(node!.width,node!.height);ctx!.strokeStyle=remove?'rgba(255,105,100,.75)':'rgba(30,220,225,.6)';
      ctx!.fillStyle=ctx!.strokeStyle;ctx!.lineCap='round';ctx!.lineJoin='round';
      // Work in isotropic source-pixel axes, not stretched screen coordinates.
      ctx!.transform(vx,vy,wx,wy,0,0);ctx!.lineWidth=2;ctx!.beginPath();
      mapped.forEach((p,i)=>i?ctx!.lineTo(p[0],p[1]):ctx!.moveTo(p[0],p[1]));
      if(points.length===1){ctx!.arc(mapped[0][0],mapped[0][1],1,0,Math.PI*2);ctx!.fill();}else ctx!.stroke();ctx!.restore();
    }
    for(const object of value.objects){if(object.enabled&&object.kind==='brush')draw(object.points,object.axes,object.operation==='subtract');}
    if(draft.length)draw(draft,[[radius/100*aspect,0],[0,radius/100]],subtract);
  },[value,draft,aspect,radius,subtract]);
  function end(event:PointerEvent<HTMLCanvasElement>){
    const points=stroke.current;stroke.current=null;setDraft([]);
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
    if(!points?.length||disabled)return;
    const object:MaskObject={id:crypto.randomUUID().replaceAll('-',''),name:subtract?'头发范围擦除':'头发范围添加',enabled:true,operation:subtract?'subtract':'add',kind:'brush',opacity:1,feather:1,
      points,axes:[[radius/100*aspect,0],[0,radius/100]]};
    onChange({...value,objects:[...value.objects,object]});
  }
  return <div className="hair-source-editor">
    <p>原始源图选区，青色添加、红色减去。这里只编辑人物归属，不从脸框自动扩张，不会改变原图。</p>
    <div className="hair-toolbar"><button type="button" disabled={disabled} aria-pressed={!subtract} onClick={()=>setSubtract(false)}>添加范围</button>
      <button type="button" disabled={disabled} aria-pressed={subtract} onClick={()=>setSubtract(true)}>擦除范围</button>
      <label>笔刷半径 <input type="range" min=".3" max="10" step=".1" value={radius} disabled={disabled} onChange={e=>setRadius(Number(e.target.value))}/>{radius}% 源图高度</label>
      <button type="button" disabled={disabled||!value.objects.length} onClick={()=>onChange({...value,objects:value.objects.slice(0,-1)})}>撤回最后一笔</button>
      <button type="button" disabled={disabled||!value.objects.length} onClick={()=>onChange({...value,objects:[]})}>清空草稿</button></div>
    <div className="hair-toolbar"><button type="button" disabled={disabled||zoom<=1} onClick={()=>setZoom(Math.max(1,zoom/2))}>缩小</button>
      <button type="button" disabled={disabled||zoom>=8} onClick={()=>setZoom(Math.min(8,zoom*2))}>放大</button>
      <button type="button" disabled={disabled} aria-pressed={pan} onClick={()=>setPan(!pan)}>{pan?'切换画笔':'切换平移'}</button><span>{Math.round(zoom*100)}%</span></div>
    <div className="hair-source-viewport"><div className="hair-source-image" style={{aspectRatio:`${width}/${height}`,width:`${zoom*100}%`}}>
      <img src={source} alt="未裁剪、未变形的原始源图" draggable={false}/>
      <canvas ref={canvas} aria-label="头发源图范围画笔" style={{touchAction:pan?'pan-x pan-y':'none',pointerEvents:pan?'none':'auto'}}
        onPointerDown={e=>{if(disabled||pan||value.objects.length>=64||!remainingPoints||e.button!==0)return;e.currentTarget.setPointerCapture(e.pointerId);stroke.current=[point(e)];setDraft([...stroke.current]);}}
        onPointerMove={e=>{const points=stroke.current;if(!points||points.length>=Math.min(1024,remainingPoints))return;points.push(point(e));setDraft([...points]);}}
        onPointerUp={end} onPointerCancel={e=>{stroke.current=null;setDraft([]);if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}}/>
    </div></div>
    <p>这是源图缩略视图，放大有助定位但不补充原片细节。最多 64 笔，每笔 1024 点，总计 8192 点；还可保留 {remainingPoints} 点。每笔上限可分笔，总量上限需撤回或清理草稿。滚动条可平移放大视图。</p>
    <p>这是笔迹草稿，不是最终头发蒙版。点击“生成审核图”查看与真实头发证据相交的范围，确认没有相邻人物后再提交。</p>
  </div>;
}
