// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import type {Source} from '../legShape/model';
import {matchesSource,sourceViewport,type SourceImage} from './sourcePreview';
import type {Review,Point} from './model';
const empty=():Review=>({left:{iris:[],pupil:[],highlights:[],confirmed:false},right:{iris:[],pupil:[],highlights:[],confirmed:false}});
export function IrisMakeupSupportEditor({faceKey,source,image,disabled,onReview}:{faceKey:string;source:Source;image:SourceImage|null;disabled:boolean;onReview:(r:Review)=>Promise<void>}){
 const [review,setReview]=useState(empty),[side,setSide]=useState<'left'|'right'>('left'),[field,setField]=useState<'iris'|'pupil'|'highlight'>('iris');
 const [highlight,setHighlight]=useState<Point[]>([]),[loaded,setLoaded]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false),[zoom,setZoom]=useState(1);
 const key=image?`${faceKey}:${image.url}:${source.sha256}:${source.width}:${source.height}`:'';
 useEffect(()=>{setReview(empty());setHighlight([]);setLoaded('');setError('');},[key]);
 const available=!disabled&&!saving&&!!key&&loaded===key&&matchesSource(image,source);
 function pick(e:MouseEvent<SVGSVGElement>){if(!available)return;const m=e.currentTarget.getScreenCTM();if(!m)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());const point:Point=[p.x/(source.width-1),p.y/(source.height-1)];if(point.some(n=>n<0||n>1))return;
  if(field==='highlight')setHighlight(v=>[...v,point].slice(0,128));else setReview(v=>({...v,[side]:{...v[side],[field]:[...v[side][field],point].slice(0,128),confirmed:false}}));
 }
 function addHighlight(){if(highlight.length<3)return;setReview(v=>({...v,[side]:{...v[side],highlights:[...v[side].highlights,highlight].slice(0,16),confirmed:false}}));setHighlight([]);}
 async function save(){if(!available)return;if(highlight.length){setError('请先保存或清空当前高光轮廓');return;}if(Object.values(review).some(e=>!e.confirmed||e.iris.length<3||e.pupil.length<3)){setError('两眼均需独立描出可见虹膜和实测瞳孔，再确认');return;}setSaving(true);try{await onReview(review);}catch(e){setError(String(e));}finally{setSaving(false);}}
 const points=(p:Point[])=>p.map(([x,y])=>`${x*(source.width-1)},${y*(source.height-1)}`).join(' ');
 return <fieldset disabled={disabled||saving}><legend>本地安全审核：虹膜环、实测瞳孔和原有高光</legend>
  <p>放大未修饰眼部源图裁切参考，逐点描出当前人物每侧可见虹膜外边界、完整瞳孔边界及所有高光。不要补全眼皮后隐藏虹膜。478 点只定位虹膜，不代表瞳孔分割；此审核不会借用眼神光范围。</p>
  <label>审核放大<input type="range" min={1} max={8} step={.5} value={zoom} onChange={e=>setZoom(Number(e.target.value))}/></label>
  {image&&matchesSource(image,source)&&<div style={{overflow:'auto',maxHeight:520}}><div style={{position:'relative',width:`${zoom*100}%`,aspectRatio:`${image.displayWidth}/${image.displayHeight}`}}>
   <img key={key} src={image.url} alt="未修饰源图眼部裁切参考，独立审核虹膜和瞳孔" style={{width:'100%',height:'100%'}} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(key);}} onError={()=>setLoaded('')}/>
   <svg style={{position:'absolute',inset:0,width:'100%',height:'100%'}} viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="描绘实测轮廓">{(['left','right'] as const).map(s=><g key={s} fill="none" strokeWidth={1/zoom} vectorEffect="non-scaling-stroke"><polygon points={points(review[s].iris)} stroke="#00ffc8"/><polygon points={points(review[s].pupil)} stroke="#ff6090"/>{review[s].highlights.map((p,i)=><polygon key={i} points={points(p)} stroke="#ffed80"/>)}</g>)}<polyline points={points(highlight)} fill="none" stroke="#ffed80" strokeWidth={1}/></svg>
  </div></div>}
  <label>人物侧<select value={side} onChange={e=>{setSide(e.target.value as 'left'|'right');setHighlight([]);}}><option value="left">人物左眼</option><option value="right">人物右眼</option></select></label>
  <label>轮廓<select value={field} onChange={e=>{setField(e.target.value as typeof field);setHighlight([]);}}><option value="iris">可见虹膜外边界（青）</option><option value="pupil">实测瞳孔排除（粉）</option><option value="highlight">原有高光排除（黄）</option></select></label>
  <button type="button" disabled={!available||highlight.length<3} onClick={addHighlight}>保存这块高光</button>
  <button type="button" onClick={()=>{setHighlight([]);setReview(v=>({...v,[side]:{...v[side],...(field==='highlight'?{highlights:[]}:{[field]:[]}),confirmed:false}}));}}>清空当前轮廓</button>
  <label><input type="checkbox" checked={review[side].confirmed} disabled={!available||highlight.length>0} onChange={e=>setReview(v=>({...v,[side]:{...v[side],confirmed:e.target.checked}}))}/>此眼属于选中人物、清晰无遮挡；瞳孔完整实测且高光已排除，没有猜测隐藏区域</label>
  <button type="button" disabled={!available} onClick={()=>void save()}>保存双眼安全审核</button>
  {!available&&<p role="status">等待当前源图加载或编辑回执。</p>}{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
