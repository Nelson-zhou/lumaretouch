// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type PointerEvent} from 'react';
import {imageUrl,KIND_LABELS,PART_LABELS,type Image,type Source,type Region,type Point,type Kind,type Part,type Proposal} from './model';
type Box=[number,number,number,number];
const kinds:Kind[]=['palm','finger','joint'];
const parts:Part[]=['palm','thumb','index','middle','ring','little'];
const points=['start','end','negative','positive'] as const;
export function HandShapeSupportEditor({source,image,regions,protect,proposal,disabled,onChange,onReady,onDraftStart,onDraftActive}:{source:Source;image:Image;regions:Region[];protect:Box[];proposal:Proposal|null;disabled:boolean;onChange:(regions:Region[],protect:Box[])=>void;onReady:(ready:boolean)=>void;onDraftStart:()=>void;onDraftActive:(active:boolean)=>void}){
 const [loaded,setLoaded]=useState(false),[kind,setKind]=useState<Kind>('palm'),[part,setPart]=useState<Part>('palm'),[mode,setMode]=useState<'region'|'protect'>('region'),[draft,setDraft]=useState<Point[]>([]),[error,setError]=useState('');
 const w=source.width-1,h=source.height-1;
 useEffect(()=>{setDraft([]);},[disabled]);
 useEffect(()=>{onDraftActive(draft.length>0);},[draft.length,onDraftActive]);
 const ready=loaded&&!disabled;
 function click(event:PointerEvent<SVGSVGElement>){
  if(!ready||event.button!==0||mode==='region'&&regions.length>=32||mode==='protect'&&protect.length>=32)return;
  const box=event.currentTarget.getBoundingClientRect();if(box.width<=0||box.height<=0)return;
  const p:Point=[(event.clientX-box.left)/box.width,(event.clientY-box.top)/box.height];
  if(p.some(v=>v<0||v>1))return;event.preventDefault();onDraftStart();setError('');
  const next=[...draft,p];
  if(mode==='protect'&&next.length===2){const [a,b]=next;const region:Box=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];if(region[2]-region[0]<1/w||region[3]-region[1]<1/h){setError('保护框太小，请重新标记。');setDraft([]);return;}onChange(regions,[...protect,region]);setDraft([]);}
  else if(mode==='region'&&next.length===4){onChange([...regions,{id:crypto.randomUUID().replaceAll('-',''),kind,part:kind==='palm'?'palm':part==='palm'?'index':part,start:next[0],end:next[1],negative:next[2],positive:next[3]}],protect);setDraft([]);}
  else setDraft(next);
 }
 function ellipse(row:Region){const sx=row.start[0]*w,sy=row.start[1]*h,ex=row.end[0]*w,ey=row.end[1]*h,dx=ex-sx,dy=ey-sy,l=Math.hypot(dx,dy);if(l<1)return null;const cx=(sx+ex)/2,cy=(sy+ey)/2,nx=-dy/l,ny=dx/l;const widths=[row.negative,row.positive].map(p=>Math.abs((p[0]*w-cx)*nx+(p[1]*h-cy)*ny));return {cx,cy,a:l/2,b:Math.max(...widths)*1.8,angle:Math.atan2(dy,dx)*180/Math.PI};}
 return <section aria-label="手部原图轮廓与保护范围编辑">
  <p><small>只标记一只实际可见的手。每个区域依次点：轴起点、轴终点、轴中部两侧真实轮廓点（第三、四点按引擎定义的负侧、正侧标记；如反向可交换）。局部指节可单独标记，不补全遮挡或缺失手指。</small></p>
  <div className="prow"><button type="button" disabled={!ready} aria-pressed={mode==='region'} onClick={()=>{setMode('region');setDraft([]);onDraftStart();}}>四点局部形状</button><button type="button" disabled={!ready} aria-pressed={mode==='protect'} onClick={()=>{setMode('protect');setDraft([]);onDraftStart();}}>两点保护框</button></div>
  <label>调整类别<select value={kind} disabled={!ready||!!draft.length} onChange={e=>{const k=e.target.value as Kind;setKind(k);if(k==='palm')setPart('palm');else if(part==='palm')setPart('index');}}>{kinds.map(k=><option key={k} value={k}>{KIND_LABELS[k]}</option>)}</select></label>
  <label>可见部位<select value={part} disabled={!ready||!!draft.length||kind==='palm'} onChange={e=>setPart(e.target.value as Part)}>{parts.filter(p=>kind==='palm'?p==='palm':p!=='palm').map(p=><option key={p} value={p}>{PART_LABELS[p]}</option>)}</select></label>
  <p role="status">{mode==='region'?`下一点：${['轴起点','轴终点','负侧轮廓','正侧轮廓'][draft.length]}`:`下一点：保护框${draft.length?'对角':'起'}点`}。区域 {regions.length}/32；保护框 {protect.length}/32。</p>
  <div style={{position:'relative',width:'100%',aspectRatio:`${w}/${h}`}}>
   <img src={imageUrl(image)} alt="当前照片完整原图坐标；非已变形预览" draggable={false} style={{display:'block',width:'100%',height:'100%'}} onLoad={event=>{const ok=event.currentTarget.naturalWidth===image.width&&event.currentTarget.naturalHeight===image.height;setLoaded(ok);onReady(ok);}} onError={()=>{setLoaded(false);onReady(false);}}/>
   <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-label="点选真实可见手部几何支持" style={{position:'absolute',inset:0,width:'100%',height:'100%',touchAction:'none'}} onPointerDown={click} onPointerCancel={()=>setDraft([])}>
    {protect.map((r,i)=><rect key={i} x={r[0]*w} y={r[1]*h} width={(r[2]-r[0])*w} height={(r[3]-r[1])*h} fill="#ff4d9066" stroke="#ff4d90" strokeWidth="2" vectorEffect="non-scaling-stroke"/>)}
    {regions.map(row=>{const e=ellipse(row);return <g key={row.id}>{e&&<ellipse cx={e.cx} cy={e.cy} rx={e.a} ry={e.b} transform={`rotate(${e.angle} ${e.cx} ${e.cy})`} fill="#4ab4ff22" stroke="#4ab4ff" strokeWidth="1" vectorEffect="non-scaling-stroke"/>}<line x1={row.start[0]*w} y1={row.start[1]*h} x2={row.end[0]*w} y2={row.end[1]*h} stroke="#ffffff" strokeWidth="1" vectorEffect="non-scaling-stroke"/>{points.map((key,i)=><circle key={key} cx={row[key][0]*w} cy={row[key][1]*h} r={Math.max(w,h)*.004} fill={i<2?'white':'#ffb43c'}/>)}</g>;})}
    {proposal?.points.filter(p=>p.x>=0&&p.x<=1&&p.y>=0&&p.y<=1).map(p=><g key={p.index}><circle cx={p.x*w} cy={p.y*h} r={Math.max(w,h)*.003} fill="#60ff97"/><text x={p.x*w+Math.max(w,h)*.004} y={p.y*h} fontSize={Math.max(w,h)*.014} fill="#60ff97">{p.index}</text></g>)}
    {draft.map((p,i)=><circle key={i} cx={p[0]*w} cy={p[1]*h} r={Math.max(w,h)*.005} fill="#ffb43c"/>)}
   </svg>
  </div>
  <p><small>蓝色椭圆是原创过渡支持：轴长的一半 × 实测较宽一侧的 1.8 倍；不是皮肤自动分割。绿色点仅为模型建议，不会生成轮廓或证明点可见。最终以引擎范围审核图为准。</small></p>
  <div className="prow"><button type="button" disabled={!ready||!draft.length} onClick={()=>{setDraft([]);onDraftStart();}}>取消未完成标记</button><button type="button" disabled={!ready||!protect.length} onClick={()=>onChange(regions,protect.slice(0,-1))}>撤销最后保护框</button></div>
  {regions.map((row,i)=><details key={row.id}><summary>{i+1}. {PART_LABELS[row.part]} · {KIND_LABELS[row.kind]}（坐标修正）</summary>{points.map(key=><div key={key}>{key}{([0,1] as const).map(axis=><label key={axis}>{axis?'Y':'X'}<input type="number" min="0" max="1" step="0.0001" value={row[key][axis]} disabled={!ready} onChange={event=>{const n=Number(event.target.value);if(!Number.isFinite(n)||n<0||n>1)return;const p:Point=[...row[key]];p[axis]=n;onChange(regions.map(r=>r.id===row.id?{...r,[key]:p}:r),protect);}}/></label>)}</div>)}<button type="button" disabled={!ready} onClick={()=>onChange(regions.map(r=>r.id===row.id?{...r,negative:r.positive,positive:r.negative}:r),protect)}>交换两侧轮廓</button><button type="button" disabled={!ready} onClick={()=>onChange(regions.filter(r=>r.id!==row.id),protect)}>删除本区域</button></details>)}
  {error&&<p role="alert">{error}</p>}
 </section>;
}
