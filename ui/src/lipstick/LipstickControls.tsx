// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import {PATTERNS,TEXTURES,IDS,neutral,channels,colour,rgb,palette,patches,type LipstickRecipe,type Pattern} from './model';
import type {ParameterPatch} from '../people/model';
import './lipstick.css';
type Props={value:LipstickRecipe;saved:string[];disabled:boolean;busy?:boolean;reason?:string;
  commit:(patches:ParameterPatch[])=>void;save:(colour:string)=>Promise<void>;remove:(colour:string)=>Promise<void>;
  pick:()=>Promise<void>;pickerUnavailable?:string;fact?:{changed_pixels?:number;reason?:string;limitation?:string}};
function Preview({id,colour:c}:{id:Pattern;colour:string}){
 const i=PATTERNS.findIndex(p=>p.id===id);
 // Schematic coverage swatch, not a photographic result or reference asset.
 function gain(u:number,v:number,d:number){switch(i){case 0:return 1;case 1:return .15+.85*(1-d)**2;case 2:return Math.max(.1,1-d*d);case 3:return .15+.85*d**3;case 4:return .2+.8*Math.exp(-5*u*u);case 5:return .25+.75*(1-v)/2;case 6:return .25+.75*(1+v)/2;case 7:return .2+.8*Math.exp(-30*(Math.abs(u)-.3)**2)*(1-v)/2;case 8:return Math.max(.05,1-Math.abs(u)**4);case 9:return .2+.8*(v/2+.5)**2;case 10:return .2+.8*(u/2+.5);case 11:return .2+.8*(2*d-1)**2;default:return .25+.75*Math.max(0,(1-u*u)*(.5+.5*Math.cos(3*u))*(1-.4*v*v));}}
 return <svg viewBox="0 0 100 60" aria-hidden="true">{Array.from({length:20},(_,x)=>Array.from({length:10},(_,y)=>{
 const u=(x+.5)/10-1,v=(y+.5)/5-1,d=Math.abs(v);return <rect key={`${x}:${y}`} x={x*5} y={y*6} width={5} height={6} fill={c} opacity={gain(u,v,d)}/>;
 }))}</svg>;
}
export function LipstickControls({value,saved,disabled,busy,reason,commit,save,remove,pick,pickerUnavailable,fact}:Props){
  const locked=disabled||!!busy;
  const [hex,setHex]=useState(value.colour),[nums,setNums]=useState(channels(value.colour).map(String)),[error,setError]=useState('');
  useEffect(()=>{setHex(value.colour);setNums(channels(value.colour).map(String));setError('');},[value.colour]);
  const material=PATTERNS.find(p=>p.id===value.pattern)!;
  function updateColour(c:string){try{commit(patches({...value,colour:colour(c)},['colour']));setError('');}catch(e){setError(String(e));}}
  function enterRgb(){try{if(nums.some(v=>!/^\d{1,3}$/.test(v)))throw Error('RGB 需要三个整数');updateColour(rgb(nums.map(Number)));}catch(e){setError(String(e));}}
  async function run(action:()=>Promise<void>){try{await action();setError('');}catch(e){setError(String(e));}}
  const colors=palette(saved);
  return <section className="lipstickControls" aria-label="口红" data-control-id={`PC-32471-C-${IDS.family}`}>
    <p>13 款原创空间覆色效果，5 种基于现有唇纹的质地近似；只作用于已审核外唇环，0 为原样。</p>
    <div className="lipstickPatterns" role="group" aria-label="口红图案">{PATTERNS.map(p=><button type="button" key={p.id} disabled={locked} aria-pressed={value.pattern===p.id} onClick={()=>commit(patches({...value,pattern:p.id},['pattern']))}>
      <Preview id={p.id} colour={value.colour}/><span>{p.label}</span></button>)}</div>
    <div role="group" aria-label="口红质地">{TEXTURES.map(([id,label,control])=><button key={id} type="button" data-control-id={`PC-32471-C-${control}`} disabled={locked} aria-pressed={value.texture===id} onClick={()=>commit(patches({...value,texture:id},['texture']))}>{label}</button>)}</div>
    <label>程度 <output>{Math.round(value.strength*100)}</output><input aria-label="口红程度" type="range" min="0" max="100" step="1" value={Math.round(value.strength*100)} disabled={locked}
      onChange={e=>commit(patches({...value,strength:Number(e.target.value)/100},['strength']))}/></label>
    <div data-control-id={`PC-32471-C-${IDS.recommended}`}><span>本图案推荐颜色</span><div className="lipstickColours">{material.recommended.map(c=><button key={c} type="button" disabled={locked} title={c} aria-label={`推荐颜色 ${c}`} aria-pressed={value.colour===c} style={{background:c}} onClick={()=>updateColour(c)}/>)}</div></div>
    <div data-control-id={`PC-32471-C-${IDS.hex}`}><label>HEX <input value={hex} disabled={locked} maxLength={7} onChange={e=>setHex(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')updateColour(hex);}}/></label><button disabled={locked} type="button" onClick={()=>updateColour(hex)}>应用 HEX</button></div>
    <div data-control-id={`PC-32471-C-${IDS.rgb}`} className="lipstickRgb">{['R','G','B'].map((name,i)=><label key={name}>{name}<input aria-label={`口红 ${name}`} type="number" min="0" max="255" step="1" value={nums[i]} disabled={locked} onChange={e=>setNums(nums.map((n,j)=>i===j?e.target.value:n))} onKeyDown={e=>{if(e.key==='Enter')enterRgb();}}/></label>)}<button type="button" disabled={locked} onClick={enterRgb}>应用 RGB</button></div>
    <button type="button" data-control-id={`PC-32471-C-${IDS.eyedropper}`} disabled={locked||!!pickerUnavailable} title={pickerUnavailable??'锁定当前代理浮点画面后取色，非原始文件像素'} onClick={()=>void run(pick)}>吸管取色</button>
    <div data-control-id={`PC-32471-C-${IDS.saved}`}><span>收藏颜色 {colors.length}/6</span><button type="button" disabled={locked||colors.includes(value.colour)||colors.length===6} onClick={()=>void run(()=>save(value.colour))}>☆ 收藏当前颜色</button>
      <div className="lipstickSaved">{colors.map(c=><span key={c}><button type="button" aria-label={`使用收藏 ${c}`} title={c} style={{background:c}} disabled={locked} onClick={()=>updateColour(c)}/><button type="button" aria-label={`移除收藏 ${c}`} disabled={locked} onClick={()=>void run(()=>remove(c))}>×</button></span>)}</div>
      {colors.length===6&&<small>已满 6 色；移除一色后可添加，不会覆盖旧收藏。</small>}</div>
    <button type="button" disabled={locked} onClick={()=>commit(patches(neutral()))}>重置口红</button>
    {(reason||error)&&<p role="alert">{error||reason}</p>}
    {busy&&<p role="status">正在确认人物修改，尚未报告应用成功。</p>}
    {fact?.reason==='no_measurable_change'&&<p role="status">当前颜色与程度未产生可测量变化。</p>}
    <small>色块仅示意空间覆盖，不是效果验收图。严重侧脸、裁切或已审核唇部支持不足会拒绝；遮挡检测并不完整，可用口红恢复画笔排除误选。</small>
  </section>;
}
