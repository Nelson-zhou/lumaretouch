// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import type {Source} from '../legShape/model';
import {matchesSource,sourceViewport,type SourceImage} from '../legShape/sourcePreview';
type Side='left'|'right';type Region='brow'|'forehead';type Key=`${Side}-${Region}`;
type Recipe={version:1;domain:'source-normalized';objects:unknown[]};
type BrowReview={recipe:Recipe;forehead_recipe:Recipe;visible:true;unoccluded:true;ownership_confirmed:true;forehead_visible:true};
type Props={faceKey:string;source:Source;image:SourceImage|null;disabled:boolean;onReview:(brows:Partial<Record<Side,BrowReview>>)=>Promise<void>};
const KEYS:Key[]=['left-brow','left-forehead','right-brow','right-forehead'];
const empty=():Record<Key,[number,number][]>=>({'left-brow':[],'left-forehead':[],'right-brow':[],'right-forehead':[]});
export function BrowMakeupSupportEditor({faceKey,source,image,disabled,onReview}:Props){
 const [side,setSide]=useState<Side>('left'),[region,setRegion]=useState<Region>('brow'),[points,setPoints]=useState(empty);
 const [radius,setRadius]=useState(3),[flags,setFlags]=useState<Record<Side,boolean>>({left:false,right:false});
 const [loaded,setLoaded]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const active:Key=`${side}-${region}`;
 const imageKey=image?`${image.url}:${image.source.sha256}:${image.displayWidth}:${image.displayHeight}`:'';
 const context=`${faceKey}:${source.sha256}:${source.width}:${source.height}`;
 useEffect(()=>{setPoints(empty());setFlags({left:false,right:false});setLoaded('');setError('');},[context,imageKey]);
 const available=!disabled&&!saving&&matchesSource(image,source)&&loaded===imageKey&&imageKey!=='';
 function pick(e:MouseEvent<SVGSVGElement>){if(!available)return;const matrix=e.currentTarget.getScreenCTM();if(!matrix)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(matrix.inverse());const x=p.x/(source.width-1),y=p.y/(source.height-1);if(x<0||y<0||x>1||y>1)return;setPoints(old=>({...old,[active]:[...old[active],[x,y] as [number,number]].slice(0,1024)}));setFlags(old=>({...old,[side]:false}));}
 function recipe(key:Key):Recipe{return {version:1,domain:'source-normalized',objects:[{id:`brow-makeup-${key}`,name:key,enabled:true,operation:'add',kind:'brush',opacity:1,feather:20,points:points[key],axes:[[radius/(source.width-1),0],[0,radius/(source.height-1)]]}]};}
 async function save(){
  const brows:Partial<Record<Side,BrowReview>>={};
  for(const key of ['left','right'] as const){
   if(!points[`${key}-brow`].length&&!points[`${key}-forehead`].length)continue;
   if(!points[`${key}-brow`].length||!points[`${key}-forehead`].length||!flags[key]){setError('每侧必须分别画出可见眉毛和邻近额头，再确认。');return;}
   brows[key]={visible:true,unoccluded:true,ownership_confirmed:true,forehead_visible:true,recipe:recipe(`${key}-brow`),forehead_recipe:recipe(`${key}-forehead`)};
  }
  if(!available||!Object.keys(brows).length)return;setSaving(true);try{await onReview(brows);setError('');}catch(e){setError(e instanceof Error?e.message:'审核未保存');}finally{setSaving(false);}
 }
 return <fieldset disabled={disabled||saving}><legend>眉毛与额头独立可见范围审核</legend>
  <p>在当前源图分别涂选原有眉毛与其上方约一至两倍眉厚的清晰额头皮肤。不要把两区连成一笔，不要包含头发、镜框、手或其他遮挡物。审核不会生成隐藏眉毛；浅色或证据不足的眉毛可能被拒绝。</p>
  {!available&&<p role="status">等待当前人物匹配的当前源图参考加载。</p>}
  {image&&matchesSource(image,source)&&<div style={{position:'relative',width:'100%',aspectRatio:`${image.displayWidth}/${image.displayHeight}`}}>
   <img key={imageKey} src={image.url} alt="未应用当前修图的源图，用于独立眉毛和额头审核" style={{width:'100%',height:'100%'}} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(imageKey);else setError('当前源图参考回执尺寸不符');}} onError={()=>setLoaded('')}/>
   <svg style={{position:'absolute',inset:0,width:'100%',height:'100%'}} viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点选当前区域笔划">
    {KEYS.map(k=><g key={k} stroke={k.endsWith('brow')?'#35dfd0':'#ffd16c'} fill="none" strokeWidth={radius*2} strokeLinecap="round" strokeLinejoin="round" opacity={k===active ? 0.7 : 0.3}><polyline points={points[k].map(p=>`${p[0]*(source.width-1)},${p[1]*(source.height-1)}`).join(' ')}/>{points[k].map((p,i)=><circle key={i} cx={p[0]*(source.width-1)} cy={p[1]*(source.height-1)} r={radius} stroke="none" fill={k.endsWith('brow')?'#35dfd0':'#ffd16c'}/>)}</g>)}
   </svg>
  </div>}
  <label>人物眉侧<select value={side} onChange={e=>setSide(e.target.value as Side)}><option value="left">人物左眉</option><option value="right">人物右眉</option></select></label>
  <label>独立区域<select value={region} onChange={e=>setRegion(e.target.value as Region)}><option value="brow">原有眉毛</option><option value="forehead">邻近额头皮肤</option></select></label>
  <label>笔刷半径（当前源图像素）<input type="number" min={1} max={50} value={radius} onChange={e=>{const n=Number(e.target.value);if(Number.isFinite(n)&&n>=1&&n<=50){setRadius(n);setFlags({left:false,right:false});}}}/></label>
  <button type="button" onClick={()=>{setPoints(p=>({...p,[active]:[]}));setFlags(f=>({...f,[side]:false}));}}>清空当前区域笔划</button>
  <label><input type="checkbox" disabled={!available||!points[`${side}-brow`].length||!points[`${side}-forehead`].length} checked={flags[side]} onChange={e=>setFlags(f=>({...f,[side]:e.target.checked}))}/>当前侧眉毛与额头均清晰可见、无遮挡，两个区域分别绘制且属于选中人物</label>
  <button type="button" disabled={!available} onClick={()=>void save()}>保存逐眉审核</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
