// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import {ANCHORS,CONFIRMATIONS,FLAGS,canReview,checkReviewSupport,refKey,type BodyChoice,type Box,type Vertex,type ReviewSupport} from './model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
export function BodySlimSupportEditor({body,image,reviewIdentity,disabled,onReview}:{body:BodyChoice;image:SourceImage|null;reviewIdentity:string;disabled:boolean;onReview:(support:ReviewSupport)=>Promise<void>}){
 const [outline,setOutline]=useState<Vertex[]>([]),[collar,setCollar]=useState<Box|null>(null),[mode,setMode]=useState<'outline'|'collar'>('outline');
 const [corner,setCorner]=useState<Vertex|null>(null),[flags,setFlags]=useState<Record<string,boolean>>({}),[loaded,setLoaded]=useState(''),[error,setError]=useState('');
 const context=`${reviewIdentity}:${refKey(body.body_ref)}:${body.points_sha256}:${JSON.stringify(body.association)}:${JSON.stringify(body.support)}`;
 const matched=matchesSource(image,body.source),key=matched&&image?`${context}:${image.url}:${image.displayWidth}:${image.displayHeight}`:'';
 useEffect(()=>{setOutline(body.support?structuredClone(body.support.outline):[]);setCollar(body.support?[...body.support.collar_box]:null);setFlags({});setCorner(null);setMode('outline');setError('');},[context]);
 useEffect(()=>{setFlags({});setCorner(null);},[key]);
 const ready=matched&&loaded===key&&!!key&&canReview(body)&&!disabled;
 function pick(e:MouseEvent<SVGSVGElement>){
  if(!ready)return;
  try{
   const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;
   const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse()),x=p.x/(body.source.width-1),y=p.y/(body.source.height-1);
   if(!(x>0&&x<1&&y>0&&y<1))throw Error('轮廓和背景过渡都必须在完整来源图内部，不能裁边。');
   setFlags({});setError('');
   if(mode==='outline'){if(outline.length>=128)throw Error('最多 128 个实测顶点，请撤回或重新测量。');setOutline(old=>[...old,[x,y]]);}
   else if(!corner)setCorner([x,y]);
   else{if(x===corner[0]||y===corner[1])throw Error('背景过渡框不能退化，请重新测量。');setCollar([Math.min(x,corner[0]),Math.min(y,corner[1]),Math.max(x,corner[0]),Math.max(y,corner[1])]);setCorner(null);}
  }catch(e){setError(e instanceof Error?e.message:'测量未完成。');}
 }
 async function save(){
  try{
   if(!ready||corner||!collar||FLAGS.some(k=>flags[k]!==true))throw Error('请查看完整来源图，逐点测量轮廓和四侧过渡，并完成全部确认。');
   const support=checkReviewSupport({version:1,method:'user-traced-complete-person-silhouette-v1',outline,collar_box:collar,confirmations:Object.fromEntries(FLAGS.map(k=>[k,flags[k]]))} as ReviewSupport);
   await onReview(support);setError('');
  }catch(e){setError(e instanceof Error?e.message:'复核未保存。');}
 }
 const w=body.source.width-1,h=body.source.height-1;
 return <fieldset disabled={disabled} className="body-slim-support-editor"><legend>实测完整人物轮廓与背景支撑</legend>
  <p>先按顺序沿真实人物外轮廓逐点描边，包括完整头发、双手和双脚，至少 8 点，不重复首点。需要沿手臂、腿部之间可见的凹部回绕，不能只点四角或用关节点代替轮廓。然后切换背景过渡，点选四侧都有余量的框的两角。</p>
  <p>全身横向统一变宽或变窄，不改变高度。轮廓范围内的背景空隙及明确过渡区也会变形，不是背景完全固定或自动 AI 分割。本版仅接受一张图中完整可见的单人，拒绝多人、接触或遮挡。</p>
  {matched&&image?<div className="body-slim-source-image"><img key={key} src={image.url} alt="完整未变形来源图参考缩略图，用于手工测量全身轮廓" draggable={false} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(key);else{setLoaded('');setError('来源参考尺寸与回执不一致。');}}} onError={()=>{setLoaded('');setError('来源图未加载，不能复核。');}}/>
   <svg viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="逐点描绘真实人物轮廓和四侧背景过渡">
    {outline.length>1&&<polygon points={outline.map(p=>`${p[0]*w},${p[1]*h}`).join(' ')} fill="none" stroke="#53e3ce" strokeWidth={Math.max(1,w*.002)}/>}
    {outline.map((p,i)=><circle key={i} cx={p[0]*w} cy={p[1]*h} r={w*.003} fill={i===0?'#f4cb7c':'#53e3ce'}/>)}
    {collar&&<rect x={collar[0]*w} y={collar[1]*h} width={(collar[2]-collar[0])*w} height={(collar[3]-collar[1])*h} fill="none" stroke="#9db2ff" strokeDasharray={`${w*.006} ${w*.004}`} strokeWidth={Math.max(1,w*.002)}/>}
    {ANCHORS.map(i=>{const p=body.points[i];return p&&Number.isFinite(p.x)&&Number.isFinite(p.y)?<circle key={i} cx={p.x*w} cy={p.y*h} r={w*.0015} fill="white"/>:null;})}
    {corner&&<circle cx={corner[0]*w} cy={corner[1]*h} r={w*.005} fill="#f4cb7c"/>}
   </svg>
  </div>:<p role="status">缺少与当前来源哈希、尺寸及方向匹配的未变形全图参考，不能复核。</p>}
  {!canReview(body)&&<p role="status">需要完整可见的 33 点真实身体定位及明确本人关联；人工勾选不能代替缺失或低置信度证据。</p>}
  <label>测量目标<select value={mode} disabled={!ready} onChange={e=>{setMode(e.currentTarget.value as 'outline'|'collar');setCorner(null);setFlags({});}}><option value="outline">完整人物轮廓逐点描边</option><option value="collar">四侧背景过渡框（点击两角）</option></select></label>
  <output>实测轮廓 {outline.length}/128 点；背景过渡{collar?'已测量':'未测量'}。{corner?'请点选第二角。':''}</output>
  <button type="button" disabled={!ready||!outline.length} onClick={()=>{setOutline(old=>old.slice(0,-1));setFlags({});}}>撤回最后一个轮廓点</button>
  <button type="button" disabled={!ready} onClick={()=>{setOutline([]);setCollar(null);setCorner(null);setFlags({});}}>清空并重新测量</button>
  {FLAGS.map(k=><label key={k}><input type="checkbox" disabled={!ready||!!corner} checked={flags[k]===true} onChange={e=>{const checked=e.currentTarget.checked;setFlags(old=>({...old,[k]:checked}));}}/>{CONFIRMATIONS[k]}</label>)}
  <button type="button" disabled={!ready||!!corner||outline.length<8||!collar} onClick={()=>void save()}>保存当前照片的全身轮廓独立复核</button>
  {error&&<p role="alert">{error}</p>}
 </fieldset>;
}
