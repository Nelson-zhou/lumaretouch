// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,CONTEXT_ANCHORS,COLUMNS,BOXES,WAIST_MARKERS,CONFIRMATIONS,FLAGS,canReview,checkReviewSupport,checkBodySupport,refKey,type BodyChoice,type Column,type BoxKey,type Box,type WaistMarker,type MarkedPoint,type ReviewSupport} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
type Target=Column|BoxKey|WaistMarker;
type Draft=Partial<Record<Column,number>>&Partial<Record<BoxKey,Box>>&Partial<Record<WaistMarker,MarkedPoint>>;
const names:Record<Target,string>={
 waist_upper_left:'① 画面左侧 · 上腰端点',waist_upper_right:'② 画面右侧 · 上腰端点',
 waist_lower_left:'③ 画面左侧 · 下腰端点',waist_lower_right:'④ 画面右侧 · 下腰端点',
 head_box:'完整头部、头发框（点击两角）',left_arm_box:'本人左臂、左手完整框（点击两角）',right_arm_box:'本人右臂、右手完整框（点击两角）',
 outer_left:'左侧背景不移动边界',inner_left:'完整上躯干、头臂范围左内界',inner_right:'完整上躯干、头臂范围右内界',outer_right:'右侧背景不移动边界',
 upper_zero:'头发上方的背景不移动边界',upper_plateau:'完整上躯干、头臂移动区起始线',
};
const targets:Target[]=[...WAIST_MARKERS,...BOXES,...COLUMNS];
const isMarker=(key:Target):key is WaistMarker=>(WAIST_MARKERS as readonly string[]).includes(key);
const isBox=(key:Target):key is BoxKey=>(BOXES as readonly string[]).includes(key);
export function WaistLengthSupportEditor({body,image,reviewIdentity,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;reviewIdentity:string;disabled:boolean;onReview:(support:ReviewSupport)=>Promise<void>}){
 const [draft,setDraft]=useState<Draft>({}),[target,setTarget]=useState<Target>('waist_upper_left'),[corner,setCorner]=useState<MarkedPoint|null>(null);
 const [flags,setFlags]=useState<Record<string,boolean>>({}),[loaded,setLoaded]=useState(''),[error,setError]=useState('');
 const [coordinates,setCoordinates]=useState<string[]>([]);
 const context=`${reviewIdentity}:${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.association)}:${JSON.stringify(body.support)}`;
 const matched=matchesSource(image,body.source),key=matched&&image?`${context}:${image.url}:${image.displayWidth}:${image.displayHeight}`:'';
 useEffect(()=>{
  const next:Draft={};
  // Only this operation's existing measured geometry may be restored. Pose33 has
  // no waist joints. Never derive marks from hips, shoulders, face or proportions.
  if(body.support){for(const k of COLUMNS)next[k]=body.support[k];for(const k of BOXES)next[k]=[...body.support[k]];for(const k of WAIST_MARKERS)next[k]=[...body.support[k]];}
  setDraft(next);setFlags({});setCorner(null);setTarget('waist_upper_left');setCoordinates([]);setError('');
 },[context]);
 useEffect(()=>{setFlags({});setCorner(null);setCoordinates([]);},[key]);
 const ready=matched&&loaded===key&&!!key&&canReview(body)&&!disabled;
 const w=body.source.width-1,h=body.source.height-1;
 function change(next:Draft){setDraft(next);setFlags({});setError('');}
 function choose(next:Target){setTarget(next);setCorner(null);setCoordinates([]);setError('');}
 function measure(x:number,y:number){
  if(!(x>0&&x<1&&y>0&&y<1))throw Error('请选择当前来源图内部，裁切到图边的轮廓不受支持。');
  if(isMarker(target))change({...draft,[target]:[x,y]});
  else if(isBox(target)){
   if(!corner){setCorner([x,y]);setFlags({});setError('');return;}
   const box:Box=[Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])];
   if(box[0]===box[2]||box[1]===box[3])throw Error('完整轮廓框不能退化，请重新点选两角。');
   setCorner(null);change({...draft,[target]:box});
  }else change({...draft,[target]:target==='upper_zero'||target==='upper_plateau'?y:x});
 }
 function pick(e:MouseEvent<SVGSVGElement>){
  if(!ready)return;
  try{const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());measure(p.x/w,p.y/h);setCoordinates([]);}
  catch(e){setError(e instanceof Error?e.message:'测量未完成。');}
 }
 const dimensions=isBox(target)?['左上 X','左上 Y','右下 X','右下 Y']:isMarker(target)?['X','Y']:[target==='upper_zero'||target==='upper_plateau'?'Y':'X'];
 function applyCoordinates(){
  if(!ready)return;
  try{
   if(coordinates.length!==dimensions.length||coordinates.some(n=>n.trim()===''))throw Error('请填写所选项目的全部来源图坐标。');
   const values=coordinates.map(Number).map((n,i)=>n/(dimensions[i].endsWith('X')?w:h));
   if(values.some(n=>!Number.isFinite(n)||n<=0||n>=1))throw Error('坐标必须在来源图内部，不能落在图边。');
   if(isBox(target)){
    if(values[0]>=values[2]||values[1]>=values[3])throw Error('轮廓框左上角必须位于右下角左上方。');
    change({...draft,[target]:values as Box});
   }else if(isMarker(target))change({...draft,[target]:values as MarkedPoint});
   else change({...draft,[target]:values[0]});
   setCorner(null);setCoordinates([]);
  }catch(e){setError(e instanceof Error?e.message:'坐标未保存。');}
 }
 async function save(){
  try{
   if(!ready||corner||coordinates.some(n=>n.trim()!=='')||FLAGS.some(k=>flags[k]!==true))throw Error('请采用或清除正在输入的坐标，完成四个腰点、完整轮廓及背景测量，并逐项确认。');
   const support=checkReviewSupport({...draft,version:1,method:'user-reviewed-visible-waist-length-support',confirmations:Object.fromEntries(FLAGS.map(k=>[k,flags[k]]))} as ReviewSupport);
   checkBodySupport(support,body);
   await onReview(support);setError('');
  }catch(e){setError(e instanceof Error?e.message:'复核未保存。');}
 }
 const chosen=draft[target],upperLeft=draft.waist_upper_left,upperRight=draft.waist_upper_right,lowerLeft=draft.waist_lower_left,lowerRight=draft.waist_lower_right;
 const upper=upperLeft&&upperRight?Math.max(upperLeft[1],upperRight[1]):null,lower=lowerLeft&&lowerRight?Math.min(lowerLeft[1],lowerRight[1]):null;
 return <fieldset disabled={disabled} className="waist-length-support-editor"><legend>腰部长度 · 当前来源图独立人工复核</legend>
  <p>先分别点选画面左右两侧的上腰、下腰四个可见端点，再测量完整头发、双臂与双手轮廓，以及容纳完整上躯干的移动内界和上方、两侧背景边界。没有预填腰点或推测轮廓；仅会恢复本项此前保存的测量。</p>
  <p>腰点的“左、右”是画面方向；手臂框的“本人左、右”是人物自身方向。身体定位中的肩髋点仅作参照，不是腰点。上腰线以上的上躯干、肩颈和头部一起平移，腰段改变长度；跨过腰段的手臂局部随连续场变形，下腰线以下固定。</p>
  {matched&&image?<div className="waist-length-source-image"><img key={key} src={image.url} alt="未变形的完整来源图参考缩略图，用于人工测量四个腰部端点及完整上躯干背景范围" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(key);else{setLoaded('');setError('参考图尺寸与当前来源映射回执不符。');}}} onError={()=>{setLoaded('');setError('来源图未加载，不能复核。');}}/>
   <svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点选四个真实腰部端点、完整头臂轮廓及上方两侧背景支撑">
    {upper!==null&&lower!==null&&upper<lower&&draft.inner_left!==undefined&&draft.inner_right!==undefined&&draft.inner_left<draft.inner_right&&<rect x={draft.inner_left*w} y={upper*h} width={(draft.inner_right-draft.inner_left)*w} height={(lower-upper)*h} fill="#f4cb7c" opacity=".12"/>}
    {COLUMNS.map(k=>{const n=draft[k];if(n===undefined)return null;const horizontal=k==='upper_zero'||k==='upper_plateau';return <line key={k} x1={horizontal?0:n*w} x2={horizontal?w:n*w} y1={horizontal?n*h:0} y2={horizontal?n*h:h} stroke={k===target?'#f4cb7c':'#53e3ce'} strokeDasharray={k==='outer_left'||k==='outer_right'||k==='upper_zero'?`${w*.006} ${w*.004}`:undefined} strokeWidth={Math.max(1,w*.0015)}/>;})}
    {BOXES.map(k=>{const b=draft[k];return b?<rect key={k} x={b[0]*w} y={b[1]*h} width={(b[2]-b[0])*w} height={(b[3]-b[1])*h} fill="none" stroke={k===target?'#f4cb7c':'#9db2ff'} strokeWidth={Math.max(1,w*.002)}/>:null;})}
    {[[upperLeft,upperRight],[lowerLeft,lowerRight]].map(([left,right],i)=>left&&right?<line key={i} x1={left[0]*w} y1={left[1]*h} x2={right[0]*w} y2={right[1]*h} stroke="#f4cb7c" strokeWidth={Math.max(1,w*.002)}/>:null)}
    {ANCHORS.map(i=>{const p=body.points[i];return p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?<circle key={i} cx={p.x*w} cy={p.y*h} r={w*((CONTEXT_ANCHORS as readonly number[]).includes(i) ? .003 : .0015)} fill={(CONTEXT_ANCHORS as readonly number[]).includes(i)?'#53e3ce':'white'}/>:null;})}
    {WAIST_MARKERS.map((k,i)=>{const p=draft[k];return p?<g key={k}><circle cx={p[0]*w} cy={p[1]*h} r={w*.006} fill={k===target?'#ffefb7':'#f4cb7c'} stroke="#202020" strokeWidth={Math.max(1,w*.001)}/><text x={p[0]*w+w*.008} y={p[1]*h-w*.006} fontSize={w*.018} fill="#ffefb7" stroke="#202020" strokeWidth={w*.0006} paintOrder="stroke">{i+1}</text></g>:null;})}
    {corner&&<circle cx={corner[0]*w} cy={corner[1]*h} r={w*.005} fill="#f4cb7c"/>}
   </svg>
  </div>:<p role="status">缺少与当前来源哈希、尺寸及方向一致的未变形全图参考，不能复核。</p>}
  {!canReview(body)&&<p role="status">需清晰可见的真实头部、肩髋、双臂与双手定位，并明确关联到唯一人物；人工勾选不能覆盖缺失或低置信度。</p>}
  <label>测量目标<select value={target} disabled={!ready} onChange={e=>choose(e.currentTarget.value as Target)}>{targets.map(k=><option value={k} key={k}>{draft[k]!==undefined?'✓ ':''}{names[k]}</option>)}</select></label>
  <output aria-live="polite">{corner?'已点选第一角，请点选第二角。':chosen===undefined?'该项尚未测量':Array.isArray(chosen)?`已测量：${chosen.map(n=>`${(n*100).toFixed(2)}%`).join('，')}`:`已测量：${(chosen*100).toFixed(2)}%`}</output>
  <div className="waist-length-coordinate-entry"><span>也可输入来源图像素坐标（X：0–{w}，Y：0–{h}）</span>{dimensions.map((label,i)=><label key={`${target}:${i}`}>{label}<input type="number" step="any" min={0} max={label.endsWith('X')?w:h} value={coordinates[i]??''} disabled={!ready} onChange={e=>{const value=e.currentTarget.value;setFlags({});setCoordinates(old=>{const next=Array.from({length:dimensions.length},(_,j)=>old[j]??'');next[i]=value;return next;});}}/></label>)}<button type="button" disabled={!ready} onClick={applyCoordinates}>采用手工坐标</button></div>
  <p>已测量 {targets.filter(k=>draft[k]!==undefined).length}/{targets.length} 项。金色 ①–④ 为人工腰点，绿色肩髋点仅供参照；阴影为两个已测腰界之间的保守变形段，不是效果预览。</p>
  <div className="waist-length-measurement-actions"><button type="button" disabled={!ready||targets.every(k=>draft[k]!==undefined)} onClick={()=>{const next=targets.find(k=>draft[k]===undefined);if(next)choose(next);}}>定位下一项未测量位置</button><button type="button" disabled={!ready} onClick={()=>{const next={...draft};delete next[target];change(next);setCorner(null);setCoordinates([]);}}>清除当前测量</button><button type="button" disabled={!ready} onClick={()=>{change({});setCorner(null);setCoordinates([]);}}>清空全部测量</button></div>
  {FLAGS.map(k=><label key={k}><input type="checkbox" disabled={!ready||!!corner} checked={flags[k]===true} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[k]:checked}));}}/>{CONFIRMATIONS[k]}</label>)}
  <button type="button" disabled={!ready||!!corner||coordinates.some(n=>n.trim()!=='')||targets.some(k=>draft[k]===undefined)||FLAGS.some(k=>flags[k]!==true)} onClick={()=>void save()}>保存当前来源图的腰部长度独立复核</button>
  {error&&<p role="alert">{error}</p>}
 </fieldset>;
}
