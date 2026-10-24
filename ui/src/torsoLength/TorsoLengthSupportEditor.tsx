// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,TORSO_ANCHORS,COLUMNS,BOXES,CONFIRMATIONS,FLAGS,canReview,checkReviewSupport,refKey,type BodyChoice,type Column,type BoxKey,type Box,type ReviewSupport} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
type Target=Column|BoxKey;
type Draft=Partial<Record<Column,number>>&Partial<Record<BoxKey,Box>>;
const names:Record<Target,string>={outer_left:'左侧背景不移动边界',inner_left:'完整头臂范围左内界',inner_right:'完整头臂范围右内界',outer_right:'右侧背景不移动边界',upper_zero:'上方背景不移动边界',upper_plateau:'完整头臂移动区起始线',head_box:'完整头部、头发框（点击两角）',left_arm_box:'本人左臂、左手完整框（点击两角）',right_arm_box:'本人右臂、右手完整框（点击两角）'};
const targets:Target[]=[...COLUMNS,...BOXES];
export function TorsoLengthSupportEditor({body,image,reviewIdentity,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;reviewIdentity:string;disabled:boolean;onReview:(support:ReviewSupport)=>Promise<void>}){
 const [draft,setDraft]=useState<Draft>({}),[target,setTarget]=useState<Target>('head_box'),[corner,setCorner]=useState<[number,number]|null>(null);
 const [flags,setFlags]=useState<Record<string,boolean>>({}),[loaded,setLoaded]=useState(''),[error,setError]=useState('');
 const context=`${reviewIdentity}:${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.association)}:${JSON.stringify(body.support)}`;
 const matched=matchesSource(image,body.source),key=matched&&image?`${context}:${image.url}:${image.displayWidth}:${image.displayHeight}`:'';
 useEffect(()=>{
  const next:Draft={};
  // Do not echo or manufacture host-owned face binding facts in a review write.
  if(body.support){for(const k of COLUMNS)next[k]=body.support[k];for(const k of BOXES)next[k]=[...body.support[k]];}
  setDraft(next);setFlags({});setCorner(null);setTarget('head_box');setError('');
 },[context]);
 useEffect(()=>{setFlags({});setCorner(null);},[key]);
 const ready=matched&&loaded===key&&!!key&&canReview(body)&&!disabled;
 function change(next:Draft){setDraft(next);setFlags({});setError('');}
 function pick(e:MouseEvent<SVGSVGElement>){
  if(!ready)return;
  try{
   const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;
   const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse()),x=p.x/(body.source.width-1),y=p.y/(body.source.height-1);
   if(!(x>0&&x<1&&y>0&&y<1))throw Error('请选择当前来源图内部，裁切到图边的轮廓不受支持。');
   if((BOXES as readonly string[]).includes(target)){
    if(!corner){setCorner([x,y]);setFlags({});setError('');return;}
    const box:Box=[Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])];
    if(box[0]===box[2]||box[1]===box[3])throw Error('完整轮廓框不能退化，请重新点选两角。');
    setCorner(null);change({...draft,[target]:box});
   }else change({...draft,[target]:target==='upper_zero'||target==='upper_plateau'?y:x});
  }catch(e){setError(e instanceof Error?e.message:'测量未完成。');}
 }
 async function save(){
  try{
   if(!ready||corner||FLAGS.some(k=>flags[k]!==true))throw Error('请查看匹配的当前来源图，完成全部点选并逐项确认。');
   const support=checkReviewSupport({...draft,version:1,method:'user-reviewed-visible-torso-length-support',confirmations:Object.fromEntries(FLAGS.map(k=>[k,flags[k]]))} as ReviewSupport);
   if(support.head_box[3]>=Math.max(body.points[11].y,body.points[12].y))throw Error('完整头部框必须位于实际肩线以上；不支持低头、遮挡或不清晰分界。');
   await onReview(support);setError('');
  }catch(e){setError(e instanceof Error?e.message:'复核未保存。');}
 }
 const w=body.source.width-1,h=body.source.height-1,chosen=draft[target];
 return <fieldset disabled={disabled} className="torso-length-support-editor"><legend>上身长度独立当前来源图复核</legend>
  <p>在真实参考图上分别框入完整头部和头发、本人左右手臂和双手，再点选包含这些轮廓的左右内界、两侧背景不移动边界，以及头发上方的移动起始线和背景不移动边界。所有位置都需人工测量，没有预填框或推测轮廓。</p>
  <p>肩髋锚点来自实际身体定位。不能用人脸框代替完整头部，也不能借用肩、颈、腰或腿部审核。手臂下伸到髋以下时，下部保持固定；上部按同一连续场衔接，并非整条手臂刚性平移。</p>
  {matched&&image?<div className="torso-length-source-image"><img key={key} src={image.url} alt="未变形的完整来源图参考缩略图，用于人工核对上身与背景" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(key);else{setLoaded('');setError('参考图尺寸与当前来源映射回执不符。');}}} onError={()=>{setLoaded('');setError('来源图未加载，不能复核。');}}/>
   <svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点选完整头臂轮廓及上方、两侧背景支撑">
    {COLUMNS.map(k=>{const n=draft[k];if(n===undefined)return null;const horizontal=k==='upper_zero'||k==='upper_plateau';return <line key={k} x1={horizontal?0:n*w} x2={horizontal?w:n*w} y1={horizontal?n*h:0} y2={horizontal?n*h:h} stroke={k===target?'#f4cb7c':'#53e3ce'} strokeDasharray={k==='outer_left'||k==='outer_right'||k==='upper_zero'?`${w*.006} ${w*.004}`:undefined} strokeWidth={Math.max(1,w*.0015)}/>;})}
    {BOXES.map(k=>{const b=draft[k];return b?<rect key={k} x={b[0]*w} y={b[1]*h} width={(b[2]-b[0])*w} height={(b[3]-b[1])*h} fill="none" stroke={k===target?'#f4cb7c':'#9db2ff'} strokeWidth={Math.max(1,w*.002)}/>:null;})}
    {ANCHORS.map(i=>{const p=body.points[i];return p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?<circle key={i} cx={p.x*w} cy={p.y*h} r={w*((TORSO_ANCHORS as readonly number[]).includes(i) ? .004 : .002)} fill={(TORSO_ANCHORS as readonly number[]).includes(i)?'#53e3ce':'white'}/>:null;})}
    {corner&&<circle cx={corner[0]*w} cy={corner[1]*h} r={w*.005} fill="#f4cb7c"/>}
   </svg>
  </div>:<p role="status">缺少与当前来源哈希、尺寸及方向一致的未变形全图参考，不能复核。</p>}
  {!canReview(body)&&<p role="status">需清晰可见的真实头部、肩髋、双臂与双手定位，并明确关联到唯一人物；人工勾选不能覆盖缺失或低置信度。</p>}
  <label>点选目标<select value={target} disabled={!ready} onChange={e=>{setTarget(e.currentTarget.value as Target);setCorner(null);setError('');}}>{targets.map(k=><option value={k} key={k}>{names[k]}</option>)}</select></label>
  <output>{corner?'已点选第一角，请点选第二角。':chosen===undefined?'该项尚未测量':Array.isArray(chosen)?`已测量：${chosen.map(n=>`${(n*100).toFixed(2)}%`).join('，')}`:`已测量：${(chosen*100).toFixed(2)}%`}</output>
  <p>已测量 {targets.filter(k=>draft[k]!==undefined).length}/{targets.length} 项。绿色大点为实际肩、髋位置；框选必须覆盖可见完整轮廓，并在上方和两侧留下足够背景余量。</p>
  <button type="button" disabled={!ready} onClick={()=>{change({});setCorner(null);}}>清空本次测量，重新点选</button>
  {FLAGS.map(k=><label key={k}><input type="checkbox" disabled={!ready||!!corner} checked={flags[k]===true} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[k]:checked}));}}/>{CONFIRMATIONS[k]}</label>)}
  <button type="button" disabled={!ready||!!corner} onClick={()=>void save()}>保存当前来源图的上身长度独立复核</button>
  {error&&<p role="alert">{error}</p>}
 </fieldset>;
}
