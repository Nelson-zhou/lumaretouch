// SPDX-License-Identifier: GPL-3.0-or-later
import React,{useEffect,useState,type MouseEvent} from 'react';
import type {Source} from '../legShape/model';
import {matchesSource,sourceViewport,type SourceImage} from '../legShape/sourcePreview';
type Side='left'|'right';
type CheekReview={recipe:{version:1;domain:'source-normalized';objects:unknown[]};visible:true;unoccluded:true;ownership_confirmed:true};
type Props={faceKey:string;source:Source;image:SourceImage|null;disabled:boolean;onReview:(cheeks:Partial<Record<Side,CheekReview>>)=>Promise<void>};
/** No generated visibility: user paints only directly visible cheek skin on original. */
export function BlushMakeupSupportEditor({faceKey,source,image,disabled,onReview}:Props){
 const [side,setSide]=useState<Side>('left'),[points,setPoints]=useState<Record<Side,[number,number][]>>({left:[],right:[]});
 const [radius,setRadius]=useState(30),[flags,setFlags]=useState<Record<Side,boolean>>({left:false,right:false});
 const [loaded,setLoaded]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const imageKey=image?`${image.url}:${image.source.sha256}:${image.displayWidth}:${image.displayHeight}`:'';
 const context=`${faceKey}:${source.sha256}:${source.width}:${source.height}`;
 useEffect(()=>{setPoints({left:[],right:[]});setFlags({left:false,right:false});setLoaded('');setError('');},[context,imageKey]);
 const available=!disabled&&!saving&&matchesSource(image,source)&&loaded===imageKey&&imageKey!=='';
 function pick(e:MouseEvent<SVGSVGElement>){if(!available)return;const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());const x=p.x/(source.width-1),y=p.y/(source.height-1);if(x<0||y<0||x>1||y>1)return;setPoints(old=>({...old,[side]:[...old[side],[x,y] as [number,number]].slice(0,1024)}));setFlags(old=>({...old,[side]:false}));}
 async function save(){
  const cheeks:Partial<Record<Side,CheekReview>>={};
  for(const key of ['left','right'] as const){if(!points[key].length)continue;if(!flags[key]){setError('请双颊确认所画范围确实可见且没有遮挡。');return;}
   cheeks[key]={visible:true,unoccluded:true,ownership_confirmed:true,recipe:{version:1,domain:'source-normalized',objects:[{id:`blush-makeup-${key}`,name:'可见面颊皮肤手绘范围',enabled:true,operation:'add',kind:'brush',opacity:1,feather:20,points:points[key],axes:[[radius/(source.width-1),0],[0,radius/(source.height-1)]]}]}};
  }
  if(!available)return;if(Object.keys(cheeks).length!==2){setError('请分别涂选并确认两侧面颊；不会借用其他人物的范围。');return;}setSaving(true);try{await onReview(cheeks);setError('');}catch(e){setError(e instanceof Error?e.message:'审核未保存');}finally{setSaving(false);}
 }
 return <fieldset disabled={disabled||saving}><legend>当前人物面颊可见范围审核</legend>
  <p>在未应用当前修图的源图上逐点涂选可见面颊皮肤。两点之间会连接为笔划，请勿跨越眼唇或遮挡物。遮挡、侧脸、低分辨率或缺少真实关键点时，不能靠手动确认解除限制。</p>
  {!available&&<p role="status">需要当前人物匹配的当前源图参考图加载完成。</p>}
  {image&&matchesSource(image,source)&&<div style={{position:'relative',width:'100%',aspectRatio:`${image.displayWidth}/${image.displayHeight}`}}>
   <img key={imageKey} src={image.url} alt="用于腮红可见范围审核的未应用当前修图的源图" style={{width:'100%',height:'100%'}} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(imageKey);else setError('当前源图参考回执尺寸不符');}} onError={()=>setLoaded('')}/>
   <svg style={{position:'absolute',inset:0,width:'100%',height:'100%'}} viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点选可见面颊皮肤笔划">
    {(['left','right'] as const).map(k=><g key={k} stroke={k===side?'#35dfd0':'#ffd16c'} fill="none" strokeWidth={radius*2} strokeLinecap="round" strokeLinejoin="round" opacity={0.5}><polyline points={points[k].map(p=>`${p[0]*(source.width-1)},${p[1]*(source.height-1)}`).join(' ')}/>{points[k].map((p,i)=><circle key={i} cx={p[0]*(source.width-1)} cy={p[1]*(source.height-1)} r={radius} stroke="none" fill={k===side?'#35dfd0':'#ffd16c'}/>)}</g>)}
   </svg>
  </div>}
  <label>人物面颊侧<select value={side} onChange={e=>setSide(e.target.value as Side)}><option value="left">人物左颊</option><option value="right">人物右颊</option></select></label>
  <label>笔刷半径（当前源图像素）<input type="number" min={1} max={500} value={radius} onChange={e=>{const n=Number(e.target.value);if(Number.isFinite(n)&&n>=1&&n<=500){setRadius(n);setFlags({left:false,right:false});}}}/></label>
  <button type="button" onClick={()=>{setPoints(p=>({...p,[side]:[]}));setFlags(f=>({...f,[side]:false}));}}>清空当前面颊笔划</button>
  <label><input type="checkbox" disabled={!available||points[side].length===0} checked={flags[side]} onChange={e=>setFlags(f=>({...f,[side]:e.target.checked}))}/>当前面颊的所画范围清晰可见、没有遮挡，并属于选中的人物</label>
  <button type="button" disabled={!available} onClick={()=>void save()}>保存双颊审核</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
