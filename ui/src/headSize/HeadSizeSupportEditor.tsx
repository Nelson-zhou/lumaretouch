// SPDX-License-Identifier: GPL-3.0-or-later
import {useLayoutEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,BOXES,CONFIRMATIONS,FLAGS,canReview,checkBodySupport,checkReviewSupport,refKey,type BodyChoice,type Box,type BoxKey,type MarkedPoint,type ReviewSupport} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
type Target=BoxKey|'pivot';
type Draft=Partial<Pick<ReviewSupport,'head_box'|'transition_box'|'pivot'>>;
const targets:Target[]=['head_box','transition_box','pivot'];
const names:Record<Target,string>={head_box:'① 完整头部及全部头发框（点击两角）',transition_box:'② 独立清晰背景过渡框（点击两角）',pivot:'③ 手工缩小中心（单击）'};
export function HeadSizeSupportEditor({body,image,reviewIdentity,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;reviewIdentity:string;disabled:boolean;onReview:(support:ReviewSupport)=>Promise<void>}){
 const [draft,setDraft]=useState<Draft>({}),[target,setTarget]=useState<Target>('head_box'),[corner,setCorner]=useState<MarkedPoint|null>(null);
 const [flags,setFlags]=useState<Record<string,boolean>>({}),[loaded,setLoaded]=useState(''),[error,setError]=useState(''),[coordinates,setCoordinates]=useState<string[]>([]);
 const context=JSON.stringify([reviewIdentity,refKey(body.body_ref),body.points_sha256,body.source,body.association,body.associated_face,body.reviewed,body.support]);
 const matched=matchesSource(image,body.source),key=matched&&image?`${context}:${image.url}:${image.displayWidth}:${image.displayHeight}`:'';
 // A source/graph/ownership change clears all measurements and confirmations.
 // Never carry guessed hair bounds or an automatically computed centre forward.
 useLayoutEffect(()=>{setDraft({});setFlags({});setCorner(null);setTarget('head_box');setCoordinates([]);setError('');},[context]);
 useLayoutEffect(()=>{setFlags({});setCorner(null);setCoordinates([]);},[key]);
 const ready=matched&&loaded===key&&!!key&&canReview(body)&&!disabled,w=body.source.width-1,h=body.source.height-1;
 function change(next:Draft){setDraft(next);setFlags({});setError('');}
 function choose(next:Target){setTarget(next);setCorner(null);setCoordinates([]);setError('');}
 function measure(x:number,y:number){
  if(!(x>0&&x<1&&y>0&&y<1))throw Error('请选择当前来源图内部；裁切头部、图外头发或隐藏轮廓不受支持。');
  if(target==='pivot'){change({...draft,pivot:[x,y]});return;}
  if(!corner){setCorner([x,y]);setFlags({});setError('');return;}
  const box:Box=[Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])];
  if(box[0]===box[2]||box[1]===box[3])throw Error('轮廓框不能退化，请重新点选两角。');
  setCorner(null);change({...draft,[target]:box});
 }
 function pick(e:MouseEvent<SVGSVGElement>){
  if(!ready)return;
  try{const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());measure(point.x/w,point.y/h);setCoordinates([]);}
  catch(e){setError(e instanceof Error?e.message:'测量未完成。');}
 }
 const dimensions=target==='pivot'?['X','Y']:['左上 X','左上 Y','右下 X','右下 Y'];
 function applyCoordinates(){
  if(!ready)return;
  try{
   if(coordinates.length!==dimensions.length||coordinates.some(n=>n.trim()===''))throw Error('请填写所选项目的全部来源图像素坐标。');
   const values=coordinates.map(Number).map((n,i)=>n/(dimensions[i].endsWith('X')?w:h));
   if(values.some(n=>!Number.isFinite(n)||n<=0||n>=1))throw Error('坐标必须在来源图内部，不能落在图边或图外。');
   if(target==='pivot')change({...draft,pivot:values as MarkedPoint});
   else{if(values[0]>=values[2]||values[1]>=values[3])throw Error('框的左上角必须在右下角左上方。');change({...draft,[target]:values as Box});}
   setCorner(null);setCoordinates([]);
  }catch(e){setError(e instanceof Error?e.message:'坐标未保存。');}
 }
 function loadSaved(){
  if(!ready||!body.reviewed||!body.support)return;
  const saved=body.support;
  // This is a separate explicit action. Never restore flags or engine face facts.
  change({head_box:[...saved.head_box],transition_box:[...saved.transition_box],pivot:[...saved.pivot]});setCorner(null);setCoordinates([]);
 }
 async function save(){
  try{
   if(!ready||corner||coordinates.some(n=>n.trim()!=='')||FLAGS.some(k=>flags[k]!==true))throw Error('请采用或清除正在输入的坐标，并完成完整头发、过渡框、中心测量及全部确认。');
   const support=checkReviewSupport({...draft,version:1,method:'user-reviewed-complete-head-hair-support',confirmations:Object.fromEntries(FLAGS.map(k=>[k,flags[k]]))} as ReviewSupport);
   checkBodySupport(support,body);await onReview(support);setError('');
  }catch(e){setError(e instanceof Error?e.message:'复核未保存。');}
 }
 const chosen=draft[target],face=body.associated_face?.associated_face_box;
 return <fieldset disabled={disabled} className="head-size-support-editor"><legend>完整头部、头发与背景 · 当前来源图独立复核</legend>
  <p>依次手工框入完整头部与全部头发、独立外围背景过渡框，再点选缩小中心。没有默认框、自动中心或推断发际线。灰色人脸框只显示引擎已关联的本人完整脸部，不可当作完整头发范围。</p>
  <p className="head-size-refusal">长发拖到肩部或衣物、头发与手/他人接触、头部裁切或遮挡时，请勿保存复核。不能省略头发、缩小框或标排除区来绕过限制。外围过渡底边必须高于两侧真实肩部。</p>
  {matched&&image?<div className="head-size-source-image"><img key={key} src={image.url} alt="当前未变形完整来源图参考缩略图，用于人工测量全部头发、头部、背景及缩小中心" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(key);else{setLoaded('');setError('参考图尺寸与来源映射回执不符，不能复核。');}}} onError={()=>{setLoaded('');setError('来源图未加载，不能复核。');}}/>
   <svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="在完整来源图点选头发头部框、过渡框及缩小中心">
    {BOXES.map(k=>{const b=draft[k];return b?<rect key={k} x={b[0]*w} y={b[1]*h} width={(b[2]-b[0])*w} height={(b[3]-b[1])*h} fill={k==='head_box'?'#9db2ff':'none'} fillOpacity={.1} stroke={k===target?'#f4cb7c':k==='head_box'?'#9db2ff':'#53e3ce'} strokeDasharray={k==='transition_box'?`${w*.006} ${w*.004}`:undefined} strokeWidth={Math.max(1,w*.002)}/>:null;})}
    {face&&<rect x={face[0]*w} y={face[1]*h} width={(face[2]-face[0])*w} height={(face[3]-face[1])*h} fill="none" stroke="#eee" strokeOpacity={.8} strokeDasharray={`${w*.003} ${w*.003}`} strokeWidth={Math.max(1,w*.001)}/>}
    {ANCHORS.map(i=>{const p=body.points[i];return p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?<circle key={i} cx={p.x*w} cy={p.y*h} r={w*(i>=11 ? .004 : .002)} fill={i>=11?'#53e3ce':'white'}/>:null;})}
    {draft.pivot&&<g stroke="#f4cb7c" strokeWidth={Math.max(1,w*.002)}><circle cx={draft.pivot[0]*w} cy={draft.pivot[1]*h} r={w*.006} fill="none"/><line x1={(draft.pivot[0]-.012)*w} x2={(draft.pivot[0]+.012)*w} y1={draft.pivot[1]*h} y2={draft.pivot[1]*h}/><line x1={draft.pivot[0]*w} x2={draft.pivot[0]*w} y1={draft.pivot[1]*h-w*.012} y2={draft.pivot[1]*h+w*.012}/></g>}
    {corner&&<circle cx={corner[0]*w} cy={corner[1]*h} r={w*.005} fill="#f4cb7c"/>}
   </svg>
  </div>:<p role="status">缺少与当前来源哈希、规范尺寸及方向一致的未变形全图参考，不能复核。</p>}
  {!canReview(body)&&<p role="status">需真实可见的头部 0–10、双肩 11/12 定位与当前本人完整脸部关联。缺失或低置信度不能靠勾选补齐。{body.associated_face_error??''}</p>}
  <label>测量目标<select value={target} disabled={!ready} onChange={e=>choose(e.currentTarget.value as Target)}>{targets.map(k=><option value={k} key={k}>{draft[k]?'✓ ':''}{names[k]}</option>)}</select></label>
  <output aria-live="polite">{corner?'已点选第一角，请点选第二角。':chosen?`已测量：${chosen.map((n,i)=>`${(n*(i%2===0?w:h)).toFixed(2)} px`).join('，')}`:'该项尚未测量'}</output>
  <div className="head-size-coordinate-entry"><span>可直接输入规范来源图像素坐标（X：0–{w}，Y：0–{h}），不是缩略图像素</span>{dimensions.map((label,i)=><label key={`${target}:${i}`}>{label}<input type="number" step="any" min={0} max={label.endsWith('X')?w:h} value={coordinates[i]??''} disabled={!ready} onChange={e=>{const value=e.currentTarget.value;setFlags({});setCoordinates(old=>{const next=Array.from({length:dimensions.length},(_,j)=>old[j]??'');next[i]=value;return next;});}}/></label>)}<button type="button" disabled={!ready} onClick={applyCoordinates}>采用手工坐标</button><button type="button" disabled={!ready} onClick={()=>{setCoordinates([]);setCorner(null);}}>取消未完成输入</button></div>
  <p>已测量 {targets.filter(k=>draft[k]).length}/3 项。蓝框为完整头发/头部恒定缩放区，绿色虚线为独立背景过渡外界，金色十字为手工中心。此处仅显示支撑几何，不是效果预览。</p>
  <div className="head-size-measurement-actions"><button type="button" disabled={!ready||targets.every(k=>draft[k])} onClick={()=>{const next=targets.find(k=>!draft[k]);if(next)choose(next);}}>定位下一项未测量位置</button><button type="button" disabled={!ready} onClick={()=>{const next={...draft};delete next[target];change(next);setCorner(null);setCoordinates([]);}}>清除当前测量</button><button type="button" disabled={!ready} onClick={()=>{change({});setCorner(null);setCoordinates([]);}}>清空全部测量</button>{body.reviewed&&body.support&&<button type="button" disabled={!ready} onClick={loadSaved}>载入本项已存测量，仍需重新确认</button>}</div>
  {FLAGS.map(k=><label key={k}><input type="checkbox" disabled={!ready||!!corner||coordinates.some(n=>n.trim()!=='')} checked={flags[k]===true} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[k]:checked}));}}/>{CONFIRMATIONS[k]}</label>)}
  <button type="button" disabled={!ready||!!corner||coordinates.some(n=>n.trim()!=='')||targets.some(k=>!draft[k])||FLAGS.some(k=>flags[k]!==true)} onClick={()=>void save()}>保存当前来源图的小头独立复核</button>
  {error&&<p role="alert">{error}</p>}
 </fieldset>;
}
