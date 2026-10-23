// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,SEGMENTS,JOINTS,STATIONS,SEGMENT_LABELS,checkSupport,canReview,refKey,type BodyChoice,type Segment,type Support,type SupportSegment} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
export type {SourceImage} from './sourcePreview';
type DraftSegment={negative:[number|null,number|null,number|null];positive:[number|null,number|null,number|null];support_radius:number|null};
type Draft=Record<Segment,DraftSegment>;
type Target={side:'negative'|'positive'|'support_radius';station:0|1|2};
const CONFIRMATIONS={joints_visible:'六个髋、膝、踝关节点在当前来源图均清晰可见',separate_legs:'双腿不交叉、不重叠，轮廓可分别辨认',not_foreshortened:'腿段没有明显朝镜头方向缩短或隐藏',ownership_confirmed:'定位点及四段可见轮廓均属于所选身体',background_support_reviewed:'已查看渐隐区域；接受其内邻近背景可能弯曲'} as const;
function empty():Draft{return Object.fromEntries(SEGMENTS.map(k=>[k,{negative:[null,null,null],positive:[null,null,null],support_radius:null}])) as Draft;}
function initial(body:BodyChoice):Draft{return body.support?structuredClone(body.support.segments):empty();}
function axes(body:BodyChoice,key:Segment){const [a,b]=JOINTS[key],p=body.points[a],q=body.points[b],w=body.source.width-1,h=body.source.height-1;const ax=p.x*w,ay=p.y*h,dx=(q.x-p.x)*w,dy=(q.y-p.y)*h,length=Math.hypot(dx,dy);return {ax,ay,dx,dy,length,nx:-dy/length,ny:dx/length,scale:Math.min(w,h)};}
/** Source-only contour picker. Empty widths remain empty, never bone-derived. */
export function LegSupportEditor({body,image,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;disabled:boolean;onReview:(support:Support)=>Promise<void>}){
 const [draft,setDraft]=useState<Draft>(()=>initial(body));const [segment,setSegment]=useState<Segment>('left_thigh');
 const [target,setTarget]=useState<Target>({side:'negative',station:0});const [flags,setFlags]=useState<Record<string,boolean>>({});const [error,setError]=useState('');const [loadedImage,setLoadedImage]=useState('');
 const context=`${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.support)}`;
 useEffect(()=>{setDraft(initial(body));setFlags({});setError('');setSegment('left_thigh');setTarget({side:'negative',station:0});},[context]);
 const sourceMatches=matchesSource(image,body.source);
 const imageKey=sourceMatches&&image?`${image.source.sha256}:${image.source.width}:${image.source.height}:${image.decodedWidth}:${image.decodedHeight}:${image.displayWidth}:${image.displayHeight}:${image.url}`:'';
 const reliable=canReview(body),available=sourceMatches&&loadedImage===imageKey&&imageKey!==''&&reliable&&!disabled;
 const axis=reliable?axes(body,segment):null;
 const width=axis?(target.side==='support_radius'?draft[segment].support_radius:draft[segment][target.side][target.station]):null;
 function setWidth(value:number){if(!axis||!Number.isFinite(value)||value<=0||value>=axis.scale)throw Error('请在可见轮廓上选择有限正半宽。');setDraft(old=>{const next=structuredClone(old);if(target.side==='support_radius')next[segment].support_radius=value/axis.scale;else next[segment][target.side][target.station]=value/axis.scale;return next;});setError('');}
 function pick(event:MouseEvent<SVGSVGElement>){if(!available||!axis)return;const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;const xy=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());const rx=xy.x-axis.ax,ry=xy.y-axis.ay;const t=(rx*axis.dx+ry*axis.dy)/(axis.length*axis.length);const transverse=rx*axis.nx+ry*axis.ny;const station=target.side==='support_radius'?.5:STATIONS[target.station];try{if(Math.abs(t-station)>.12)throw Error('请沿亮色横截线附近点选，不要跨到关节或其他腿段。');if(target.side==='negative'&&transverse>=0||target.side==='positive'&&transverse<=0)throw Error('请选择亮色横截线指示的另一侧轮廓。');setWidth(Math.abs(transverse));}catch(e){setError(e instanceof Error?e.message:'无法使用此测量。');}}
 async function save(){try{if(!available||Object.keys(CONFIRMATIONS).some(k=>flags[k]!==true))throw Error('请核对当前来源图并完成五项可见性与背景确认。');const value=checkSupport({version:1,method:'user-reviewed-visible-silhouette',stations:[.25,.5,.75],segments:draft as Record<Segment,SupportSegment>,joints_visible:true,separate_legs:true,not_foreshortened:true,ownership_confirmed:true,background_support_reviewed:true});await onReview(value);setError('');}catch(e){setError(e instanceof Error?e.message:'复核未保存。');}}
 const nextTarget=()=>{if(target.side==='support_radius'){setSegment(SEGMENTS[(SEGMENTS.indexOf(segment)+1)%4]);setTarget({side:'negative',station:0});}else if(target.station<2)setTarget({...target,station:(target.station+1) as 1|2});else setTarget({side:target.side==='negative'?'positive':'support_radius',station:0});};
 return <fieldset disabled={disabled} className="leg-support-editor"><legend>当前来源图可见轮廓复核</legend>
  <p>请点选每段在 25%、50%、75% 处的两侧可见轮廓，再点选渐隐范围。宽度不会从骨骼中心推测。裙装遮住腿线、宽松衣物下隐藏的腿型不能补全；这里只改变确实可见的轮廓。</p>
  {!sourceMatches&&<p role="status">需要与本次身体分析匹配、具有完整当前来源图映射回执的未变形参考图，暂不能复核。</p>}{sourceMatches&&loadedImage!==imageKey&&<p role="status">正在等待匹配的当前来源图参考缩略图加载完成，暂不能复核。</p>}{!reliable&&<p role="status">髋、膝或踝定位置信度不足或被裁切，手动确认不能覆盖此限制。</p>}
  {sourceMatches&&image&&<p>参考图 {image.displayWidth} × {image.displayHeight}，源图 {image.source.width} × {image.source.height}；全图缩放对应，没有裁切或局部变形。测量保存为源图归一化坐标。</p>}
  {sourceMatches&&image&&<div className="leg-source-image"><img key={imageKey} src={image.url} alt="用于腿部轮廓复核的未变形当前来源图参考缩略图" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth!==image.displayWidth||e.currentTarget.naturalHeight!==image.displayHeight){setLoadedImage('');setError('参考图实际像素尺寸与源映射回执不一致，不能用来源不明或变形图替代。');}else{setLoadedImage(imageKey);setError('');}}} onError={()=>{setLoadedImage('');setError('当前来源图未能加载，不能进行轮廓复核。');}}/><svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点击亮色横截线处的可见轮廓">
   {reliable&&SEGMENTS.map(key=>{const a=axes(body,key),s=draft[key],r=(s.support_radius??0)*a.scale,active=key===segment;const color=active?'#53e3ce':'#f4cb7c';return <g key={key} stroke={color} fill="none" strokeWidth={Math.max(1,a.scale*.002)}>
    {r>0&&<polygon points={`${a.ax+a.nx*r},${a.ay+a.ny*r} ${a.ax+a.dx+a.nx*r},${a.ay+a.dy+a.ny*r} ${a.ax+a.dx-a.nx*r},${a.ay+a.dy-a.ny*r} ${a.ax-a.nx*r},${a.ay-a.ny*r}`} fill={color} fillOpacity={.09} strokeDasharray={`${a.scale*.008} ${a.scale*.004}`}/>}
    <line x1={a.ax} y1={a.ay} x2={a.ax+a.dx} y2={a.ay+a.dy}/>
    {STATIONS.map((t,i)=><g key={t}>{(['negative','positive'] as const).map(side=>{const distance=s[side][i];if(distance===null)return null;const sign=side==='negative'?-1:1;return <circle key={side} cx={a.ax+a.dx*t+sign*a.nx*distance*a.scale} cy={a.ay+a.dy*t+sign*a.ny*distance*a.scale} r={a.scale*.005} fill={color}/>;})}</g>)}
   </g>;})}
   {axis&&<line x1={axis.ax+axis.dx*(target.side==='support_radius'?.5:STATIONS[target.station])} y1={axis.ay+axis.dy*(target.side==='support_radius'?.5:STATIONS[target.station])} x2={axis.ax+axis.dx*(target.side==='support_radius'?.5:STATIONS[target.station])+axis.nx*axis.length*.45*(target.side==='negative'?-1:1)} y2={axis.ay+axis.dy*(target.side==='support_radius'?.5:STATIONS[target.station])+axis.ny*axis.length*.45*(target.side==='negative'?-1:1)} stroke="#ff5fc7" strokeWidth={Math.max(2,axis.scale*.004)}/>}
   {ANCHORS.map(i=>{const p=body.points[i];return p?<circle key={i} cx={p.x*(body.source.width-1)} cy={p.y*(body.source.height-1)} r={Math.min(body.source.width,body.source.height)*.006} fill={reliable?'#fff':'#e86e6e'}/>:null;})}
  </svg></div>}
  <label>腿段 <select value={segment} disabled={!available} onChange={e=>setSegment(e.currentTarget.value as Segment)}>{SEGMENTS.map(key=><option key={key} value={key}>{SEGMENT_LABELS[key]}</option>)}</select></label>
  <label>点选目标 <select value={`${target.side}:${target.station}`} disabled={!available} onChange={e=>{const [side,station]=e.currentTarget.value.split(':');setTarget({side:side as Target['side'],station:Number(station) as Target['station']});}}>{(['negative','positive'] as const).flatMap(side=>STATIONS.map((t,i)=><option key={`${side}:${i}`} value={`${side}:${i}`}>{side==='negative'?'轴线一侧':'轴线另一侧'} · {t*100}%</option>))}<option value="support_radius:0">渐隐半宽（包含邻近背景）</option></select></label>
  <label>当前来源图半宽（像素）<input type="number" min="1" step=".1" value={width!==null&&axis?Math.round(width*axis.scale*10)/10:''} disabled={!available} onChange={e=>{try{setWidth(e.currentTarget.valueAsNumber);}catch(err){setError(err instanceof Error?err.message:'宽度无效。');}}}/></label><button type="button" disabled={!available} onClick={nextTarget}>下一个测量点</button>
  <p>渐隐半宽需为本腿段已测最大半宽的 1.4–2.5 倍，且不碰另一条腿、其他人物或画面边缘。此范围及阈值是本产品策略。</p>
  {Object.entries(CONFIRMATIONS).map(([key,label])=><label key={key}><input type="checkbox" checked={flags[key]===true} disabled={!available} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[key]:checked}));}}/>{label}</label>)}
  <button type="button" disabled={!available} onClick={()=>void save()}>保存所选身体的腿部复核</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
