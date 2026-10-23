// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,STATIONS,CONFIRMATIONS,checkSupport,canReview,refKey,type BodyChoice,type Box,type Support} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
export type {SourceImage} from './sourcePreview';
type Draft={upper:number|null;lower:number|null;negative:(number|null)[];positive:(number|null)[];selection_box:Box|null;exclusions:Box[]};
type Target='upper'|'lower'|'negative'|'positive'|'selection'|'exclusion';
function initial(body:BodyChoice):Draft{const s=body.support;return s?{upper:s.upper,lower:s.lower,negative:[...s.negative],positive:[...s.positive],selection_box:[...s.region.selection_box],exclusions:structuredClone(s.region.exclusions)}:{upper:null,lower:null,negative:Array(9).fill(null),positive:Array(9).fill(null),selection_box:null,exclusions:[]};}
function axes(body:BodyChoice){const p=body.points,w=body.source.width-1,h=body.source.height-1;const ax=(p[11].x+p[12].x)*w/2,ay=(p[11].y+p[12].y)*h/2,dx=(p[23].x+p[24].x)*w/2-ax,dy=(p[23].y+p[24].y)*h/2-ay,length=Math.hypot(dx,dy);return {ax,ay,dx,dy,length,nx:-dy/length,ny:dx/length,scale:Math.min(w,h),w,h};}
export function WaistSupportEditor({body,image,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;disabled:boolean;onReview:(support:Support)=>Promise<void>}){
 const [draft,setDraft]=useState<Draft>(()=>initial(body)),[target,setTarget]=useState<Target>('upper'),[station,setStation]=useState(0),[corner,setCorner]=useState<[number,number]|null>(null);
 const [flags,setFlags]=useState<Record<string,boolean>>({}),[error,setError]=useState(''),[loaded,setLoaded]=useState('');
 const context=`${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.support)}`;
 useEffect(()=>{setDraft(initial(body));setFlags({});setError('');setTarget('upper');setStation(0);setCorner(null);},[context]);
 const matched=matchesSource(image,body.source),imageKey=matched&&image?`${image.source.sha256}:${image.decodedWidth}:${image.decodedHeight}:${image.displayWidth}:${image.displayHeight}:${image.url}`:'';
 const reliable=canReview(body),axis=reliable?axes(body):null;
 const available=!!axis&&axis.length>1&&matched&&loaded===imageKey&&imageKey!==''&&!disabled;
 const bounds=axis&&draft.upper!==null&&draft.lower!==null&&draft.upper<draft.lower;
 function change(next:Draft){setDraft(next);setFlags({});setError('');}
 function pick(event:MouseEvent<SVGSVGElement>){
  if(!available||!axis)return;const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;
  const q=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),x=q.x/axis.w,y=q.y/axis.h;
  try{
   if(x<=0||x>=1||y<=0||y>=1)throw Error('测量点必须位于当前来源图内部。');
   if(target==='selection'||target==='exclusion'){
    if(!corner){setCorner([x,y]);return;}
    const box:Box=[Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])];setCorner(null);
    if(box[2]-box[0]<.002||box[3]-box[1]<.002)throw Error('请分别点击矩形的两个对角，范围不能退化。');
    if(target==='exclusion'&&draft.exclusions.length>=32)throw Error('排除区域最多 32 个。');
    change(target==='selection'?{...draft,selection_box:box}:{...draft,exclusions:[...draft.exclusions,box]});return;
   }
   const rx=q.x-axis.ax,ry=q.y-axis.ay,t=(rx*axis.dx+ry*axis.dy)/(axis.length*axis.length),v=rx*axis.nx+ry*axis.ny;
   if(target==='upper'||target==='lower'){
    if(t<=0||t>=1)throw Error('上下界必须在真实肩中点与髋中点之间，定位点只提供方向。');
    const next={...draft,[target]:t,negative:Array(9).fill(null),positive:Array(9).fill(null)};change(next);setTarget(target==='upper'?'lower':'negative');setStation(0);return;
   }
   if(!bounds||draft.upper===null||draft.lower===null)throw Error('先点选上界和下界，再沿横截线测量双侧轮廓。');
   const expected=draft.upper+STATIONS[station]*(draft.lower-draft.upper);
   if(Math.abs(t-expected)>.035*(draft.lower-draft.upper))throw Error('请准确沿粉色横截线点选可见外轮廓。');
   if(target==='negative'&&v>=0||target==='positive'&&v<=0)throw Error('请测量亮线指定的一侧，不能镜像另一侧。');
   if(Math.abs(v)<2||Math.abs(v)>.8*axis.length)throw Error('轮廓半宽超出本产品可验证范围。');
   const widths=[...draft[target]];widths[station]=Math.abs(v)/axis.scale;change({...draft,[target]:widths});
   if(station<8)setStation(station+1);else if(target==='negative'){setTarget('positive');setStation(0);}else setTarget('selection');
  }catch(e){setError(e instanceof Error?e.message:'当前来源图测量未采纳。');}
 }
 async function save(){try{
  if(!available||Object.keys(CONFIRMATIONS).some(k=>flags[k]!==true))throw Error('请逐项完成源图复核。');
  const support=checkSupport({version:1,upper:draft.upper!,lower:draft.lower!,stations:[...STATIONS],negative:draft.negative as number[],positive:draft.positive as number[],region:{selection_box:draft.selection_box!,exclusions:draft.exclusions},confirmations:flags as Support['confirmations']});
  await onReview(support);setError('');
 }catch(e){setError(e instanceof Error?e.message:'复核未保存。');}}
 const boxShape=(box:Box,color:string,key:string)=><rect key={key} x={box[0]*(body.source.width-1)} y={box[1]*(body.source.height-1)} width={(box[2]-box[0])*(body.source.width-1)} height={(box[3]-box[1])*(body.source.height-1)} fill={color} fillOpacity={.1} stroke={color} strokeWidth={Math.max(1,(axis?.scale??1)*.002)}/>;
 return <fieldset className="leg-support-editor" disabled={disabled}><legend>当前来源图腰部可见轮廓复核</legend>
  <p>先点上界、下界，再分别沿九条截线测量两侧可见轮廓。肩髋点只确定方向，不推算腰线或腰围；修改上下界会清空轮廓测量。松衣只调整衣物外轮廓，不补全隐藏身体。</p>
  {!matched&&<p role="status">缺少匹配源图的完整映射回执，不能复核。</p>}{matched&&loaded!==imageKey&&<p role="status">等待未变形当前来源图参考加载并核对像素尺寸。</p>}{!reliable&&<p role="status">肩髋实际定位不完整或置信度不足，人工勾选不能覆盖此限制。</p>}
  {matched&&image&&<><p>全图参考 {image.displayWidth} × {image.displayHeight}；源图 {image.source.width} × {image.source.height}。显示图非最终效果。</p><div className="leg-source-image"><img key={imageKey} src={image.url} alt="用于腰部轮廓复核的未变形全图参考" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(imageKey);else{setLoaded('');setError('图像实际尺寸不匹配，不允许测量。');}}} onError={()=>{setLoaded('');setError('当前来源图加载失败。');}}/><svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点击源图测量上下界与双侧轮廓">
   {draft.selection_box&&boxShape(draft.selection_box,'#53e3ce','selection')}{draft.exclusions.map((b,i)=>boxShape(b,'#ff6868',`exclusion-${i}`))}
   {corner&&axis&&<circle cx={corner[0]*axis.w} cy={corner[1]*axis.h} r={axis.scale*.006} fill="#f4cb7c"/>}
   {axis&&<g stroke="#f4cb7c" fill="none" strokeWidth={Math.max(1,axis.scale*.002)}><line x1={axis.ax} y1={axis.ay} x2={axis.ax+axis.dx} y2={axis.ay+axis.dy}/>{[draft.upper,draft.lower].map((t,i)=>t!==null?<line key={i} x1={axis.ax+axis.dx*t-axis.nx*axis.length*.4} y1={axis.ay+axis.dy*t-axis.ny*axis.length*.4} x2={axis.ax+axis.dx*t+axis.nx*axis.length*.4} y2={axis.ay+axis.dy*t+axis.ny*axis.length*.4}/>:null)}</g>}
   {axis&&bounds&&(()=>{const radius=1.8*Math.max(0,...draft.negative.map(x=>x??0),...draft.positive.map(x=>x??0))*axis.scale;if(!radius)return null;const corners=[[-1,draft.upper!],[1,draft.upper!],[1,draft.lower!],[-1,draft.lower!]].map(([side,t])=>`${axis.ax+axis.dx*t+side*axis.nx*radius},${axis.ay+axis.dy*t+side*axis.ny*radius}`);return <polygon points={corners.join(' ')} fill="#f4cb7c" fillOpacity={.06} stroke="#f4cb7c" strokeWidth={Math.max(1,axis.scale*.002)} strokeDasharray={`${axis.scale*.008} ${axis.scale*.004}`}/>;})()}
   {axis&&bounds&&STATIONS.map((s,i)=>{const t=draft.upper!+s*(draft.lower!-draft.upper!),x=axis.ax+axis.dx*t,y=axis.ay+axis.dy*t;return <g key={i}>{(['negative','positive'] as const).map(side=>{const width=draft[side][i];return width===null?null:<circle key={side} cx={x+axis.nx*width*axis.scale*(side==='negative'?-1:1)} cy={y+axis.ny*width*axis.scale*(side==='negative'?-1:1)} r={axis.scale*.004} fill="#53e3ce"/>;})}{i===station&&(target==='negative'||target==='positive')&&<line x1={x} y1={y} x2={x+axis.nx*axis.length*.8*(target==='negative'?-1:1)} y2={y+axis.ny*axis.length*.8*(target==='negative'?-1:1)} stroke="#ff5fc7" strokeWidth={Math.max(2,axis.scale*.003)}/>}</g>;})}
   {axis&&ANCHORS.map(i=><circle key={i} cx={body.points[i].x*axis.w} cy={body.points[i].y*axis.h} r={axis.scale*.005} fill="#fff"/>)}
  </svg></div></>}
  <label>测量目标 <select value={target} disabled={!available} onChange={e=>{setTarget(e.currentTarget.value as Target);setCorner(null);}}><option value="upper">上界</option><option value="lower">下界</option><option value="negative">轴线一侧可见轮廓</option><option value="positive">轴线另一侧可见轮廓</option><option value="selection">完整复核范围：点击两个对角</option><option value="exclusion">新增排除矩形：点击两个对角</option></select></label>
  {(target==='negative'||target==='positive')&&<label>截线 <select value={station} disabled={!available||!bounds} onChange={e=>setStation(Number(e.currentTarget.value))}>{STATIONS.map((s,i)=><option key={i} value={i}>{s*100}% · {draft[target][i]===null?'待测':'已测'}</option>)}</select></label>}
  <p>两侧已测 {draft.negative.filter(x=>x!==null).length} / 9、{draft.positive.filter(x=>x!==null).length} / 9。金色虚线是最大半宽 1.8 倍的保守过渡包络（本产品策略）。复核矩形须包含全部过渡区域，不是裁切变形范围；红色矩形标记手臂、其他人物或物品等不能触及区域。</p>
  {draft.exclusions.map((_,i)=><button key={i} type="button" disabled={!available} onClick={()=>change({...draft,exclusions:draft.exclusions.filter((_,j)=>j!==i)})}>移除排除区 {i+1}</button>)}
  {Object.entries(CONFIRMATIONS).map(([key,label])=><label key={key}><input type="checkbox" checked={flags[key]===true} disabled={!available} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[key]:checked}));}}/>{label}</label>)}
  <button type="button" disabled={!available} onClick={()=>void save()}>保存此身体的独立瘦腰复核</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
