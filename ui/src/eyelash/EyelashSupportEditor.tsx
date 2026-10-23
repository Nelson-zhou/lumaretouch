// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState,type MouseEvent} from 'react';
import type {Source} from '../legShape/model';
import {matchesSource,sourceViewport,type SourceImage} from '../legShape/sourcePreview';
import {PARTS,type Side} from './model';
type Zone='root_recipe'|'extension_recipe';
type Point=[number,number];
type Stroke={id:string;name:string;enabled:true;operation:'add'|'subtract';kind:'brush';opacity:1;feather:number;points:Point[];axes:Point[]};
type Stack={version:1;domain:'source-normalized';objects:Stroke[]};
type Review={root_recipe:Stack;extension_recipe:Stack;visible:true;unoccluded:true;ownership_confirmed:true;open_eye:true};
type Draft=Record<Side,Record<Zone,Stroke[]>>;
const fresh=():Draft=>Object.fromEntries(PARTS.map(p=>[p,{root_recipe:[],extension_recipe:[]}])) as Draft;
const labels={left_upper:'人物左上睫毛',left_lower:'人物左下睫毛',right_upper:'人物右上睫毛',right_lower:'人物右下睫毛'};
export function EyelashSupportEditor({faceKey,source,image,disabled,onReview}:{faceKey:string;source:Source;image:SourceImage|null;disabled:boolean;onReview:(eyes:Partial<Record<Side,Review>>)=>Promise<void>}){
 const [part,setPart]=useState<Side>('left_upper'),[zone,setZone]=useState<Zone>('root_recipe'),[draft,setDraft]=useState(fresh),[confirmed,setConfirmed]=useState<Partial<Record<Side,boolean>>>({});
 const [radius,setRadius]=useState(3),[erase,setErase]=useState(false),[loaded,setLoaded]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const imageKey=image?`${image.url}:${image.source.sha256}:${image.displayWidth}:${image.displayHeight}`:'';
 const context=`${faceKey}:${source.sha256}:${source.width}:${source.height}`;
 useEffect(()=>{setDraft(fresh());setConfirmed({});setLoaded('');setError('');},[context,imageKey]);
 const available=!disabled&&!saving&&source.width>1&&source.height>1&&matchesSource(image,source)&&loaded===imageKey&&imageKey!=='';
 function pick(event:MouseEvent<SVGSVGElement>){
  if(!available)return;if(draft[part][zone].length>=64){setError('当前区域已达 64 个点涂记录，请清理后继续。');return;}const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;
  const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),point:Point=[p.x/(source.width-1),p.y/(source.height-1)];if(point.some(n=>!Number.isFinite(n)||n<0||n>1))return;
  const stroke:Stroke={id:crypto.randomUUID(),name:zone==='root_recipe'?'可见根部':'已审核延伸区',enabled:true,operation:erase?'subtract':'add',kind:'brush',opacity:1,feather:0,points:[point],axes:[[radius/(source.width-1),0],[0,radius/(source.height-1)]]};
  setDraft(v=>({...v,[part]:{...v[part],[zone]:[...v[part][zone],stroke]}}));setConfirmed(v=>({...v,[part]:false}));
 }
 async function save(){
  if(!available)return;const eyes:Partial<Record<Side,Review>>={};
  for(const p of PARTS){const d=draft[p];if(!d.root_recipe.length&&!d.extension_recipe.length)continue;
   if(!confirmed[p]||!d.root_recipe.some(s=>s.operation==='add')||!d.extension_recipe.some(s=>s.operation==='add')){setError('每个保存部位都需要根部、延伸区以及独立可见性确认。');return;}
   eyes[p]={visible:true,unoccluded:true,ownership_confirmed:true,open_eye:true,root_recipe:{version:1,domain:'source-normalized',objects:d.root_recipe},extension_recipe:{version:1,domain:'source-normalized',objects:d.extension_recipe}};
  }
  if(!Object.keys(eyes).length)return;setSaving(true);try{await onReview(eyes);setError('');}catch(e){setError(String(e));}finally{setSaving(false);}
 }
 return <fieldset disabled={disabled||saving}><legend>逐部位审核睫毛根部与延伸范围</legend>
  <p>在未变形原图上先点涂真实睫毛根部，再点涂允许睫毛延伸的可见区域（须包含根部）。上下、左右分别审核。延伸区不是狭窄眼线带；不要覆盖眼镜、头发、其他人物、遮挡物或不可见部位。点涂不会跨点连接；用擦除移除不允许的区域。</p>
  {!available&&<p role="status">等待当前人物对应原图参考加载。</p>}
  {image&&matchesSource(image,source)&&<div style={{position:'relative',width:'100%',aspectRatio:`${image.displayWidth}/${image.displayHeight}`}}>
   <img key={imageKey} src={image.url} alt="睫毛逐部位审核原图" style={{width:'100%',height:'100%'}} onLoad={e=>{if(e.currentTarget.naturalWidth===image.displayWidth&&e.currentTarget.naturalHeight===image.displayHeight)setLoaded(imageKey);else setError('原图回执尺寸不匹配');}} onError={()=>setLoaded('')}/>
   <svg style={{position:'absolute',inset:0,width:'100%',height:'100%'}} viewBox={sourceViewport(image)} preserveAspectRatio="none" onClick={pick} aria-label="点涂根部或睫毛延伸区">
    {draft[part][zone].map(s=>s.points.map((p,i)=><ellipse key={`${s.id}:${i}`} cx={p[0]*(source.width-1)} cy={p[1]*(source.height-1)} rx={s.axes[0][0]*(source.width-1)} ry={s.axes[1][1]*(source.height-1)} fill={s.operation==='subtract'?'#ff7b7b':zone==='root_recipe'?'#35dfd0':'#ffd16c'} opacity={.45}/>))}
   </svg>
  </div>}
  <label>部位<select value={part} onChange={e=>setPart(e.target.value as Side)}>{PARTS.map(p=><option key={p} value={p}>{labels[p]}</option>)}</select></label>
  <label>审核区域<select value={zone} onChange={e=>setZone(e.target.value as Zone)}><option value="root_recipe">真实可见睫毛根部</option><option value="extension_recipe">无遮挡延伸区域</option></select></label>
  <label>笔刷半径（源像素）<input type="number" min={1} max={100} value={radius} onChange={e=>{const n=Number(e.target.value);if(Number.isFinite(n)&&n>=1&&n<=100)setRadius(n);}}/></label>
  <label><input type="checkbox" checked={erase} onChange={e=>setErase(e.target.checked)}/>擦除不允许的区域</label>
  <button type="button" onClick={()=>{setDraft(d=>({...d,[part]:{...d[part],[zone]:[]}}));setConfirmed(c=>({...c,[part]:false}));}}>清空当前部位的当前区域</button>
  <label><input type="checkbox" disabled={!available} checked={!!confirmed[part]} onChange={e=>setConfirmed(c=>({...c,[part]:e.target.checked}))}/>当前部位睁眼且清晰可见，两类区域均属于此人物，没有眼镜、头发或其他遮挡</label>
  <p>{PARTS.map(p=>`${labels[p]}：${confirmed[p]?'已确认':'未确认'}`).join('；')}</p>
  <button type="button" disabled={!available} onClick={()=>void save()}>保存逐部位审核</button>{error&&<p role="alert">{error}</p>}
 </fieldset>;
}
