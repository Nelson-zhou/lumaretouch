// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useState} from 'react';
import {PATTERNS,IDS,neutralEye as neutral,channels,colour,rgb,palette,type Eye,type Pattern} from './model';
import '../blushMakeup/blush.css';
type Props={value:Eye;saved:string[];disabled:boolean;busy?:boolean;reason?:string;
  commit:(value:Eye)=>void;save:(colour:string)=>Promise<void>;remove:(colour:string)=>Promise<void>;
  pick:()=>Promise<void>;pickerUnavailable?:string;fact?:{changed_pixels?:number;reason?:string;limitation?:string}};
function Preview({id,colour:c}:{id:Pattern;colour:string}){
  const pattern=PATTERNS.find(p=>p.id===id)!;
  return <svg viewBox="0 0 100 70" aria-hidden="true"><path d="M10 40 Q50 8 90 40 Q50 65 10 40" fill="none" stroke="currentColor" opacity=".35"/>{pattern.widths.slice(0,-1).map((v,i)=><line key={i} x1={10+i*80/7} y1={40-22*Math.sin(i*Math.PI/7)} x2={10+(i+1)*80/7} y2={40-22*Math.sin((i+1)*Math.PI/7)} stroke={c} strokeWidth={v*150}/>)}</svg>;
}
export function EyelinerEyeControls({value,saved,disabled,busy,reason,commit,save,remove,pick,pickerUnavailable,fact}:Props){
  const locked=disabled||!!busy;
  const [hex,setHex]=useState(value.colour),[nums,setNums]=useState(channels(value.colour).map(String)),[error,setError]=useState('');
  useEffect(()=>{setHex(value.colour);setNums(channels(value.colour).map(String));setError('');},[value.colour]);
  const material=PATTERNS.find(p=>p.id===value.pattern)!;
  function updateColour(c:string){try{commit(({...value,colour:colour(c)}));setError('');}catch(e){setError(String(e));}}
  function enterRgb(){try{if(nums.some(v=>!/^\d{1,3}$/.test(v)))throw Error('RGB 需要三个整数');updateColour(rgb(nums.map(Number)));}catch(e){setError(String(e));}}
  async function run(action:()=>Promise<void>){try{await action();setError('');}catch(e){setError(String(e));}}
  const colors=palette(saved);
  return <section className="blushControls" aria-label="眼线" data-control-id={`PC-32471-C-${IDS.family}`}>
    <p>6 款原创眼线曲线。只作用于单独审核的可见眼睑；0 为原样。</p>
    <div className="blushPatterns" role="group" aria-label="眼线图案">{PATTERNS.map(p=><button type="button" key={p.id} disabled={locked} aria-pressed={value.pattern===p.id} onClick={()=>commit(({...value,pattern:p.id}))}>
      <Preview id={p.id} colour={value.colour}/><span>{p.label}</span></button>)}</div>
    <label>程度 <output>{Math.round(value.strength*100)}</output><input aria-label="眼线程度" type="range" min="0" max="100" step="1" value={Math.round(value.strength*100)} disabled={locked}
      onChange={e=>commit(({...value,strength:Number(e.target.value)/100}))}/></label>
    <div data-control-id={`PC-32471-C-${IDS.recommended}`}><span>本图案推荐颜色</span><div className="blushColours">{material.recommended.map(c=><button key={c} type="button" disabled={locked} title={c} aria-label={`推荐颜色 ${c}`} aria-pressed={value.colour===c} style={{background:c}} onClick={()=>updateColour(c)}/>)}</div></div>
    <div data-control-id={`PC-32471-C-${IDS.hex}`}><label>HEX <input value={hex} disabled={locked} maxLength={7} onChange={e=>setHex(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')updateColour(hex);}}/></label><button disabled={locked} type="button" onClick={()=>updateColour(hex)}>应用 HEX</button></div>
    <div data-control-id={`PC-32471-C-${IDS.rgb}`} className="blushRgb">{['R','G','B'].map((name,i)=><label key={name}>{name}<input aria-label={`眼线 ${name}`} type="number" min="0" max="255" step="1" value={nums[i]} disabled={locked} onChange={e=>setNums(nums.map((n,j)=>i===j?e.target.value:n))} onKeyDown={e=>{if(e.key==='Enter')enterRgb();}}/></label>)}<button type="button" disabled={locked} onClick={enterRgb}>应用 RGB</button></div>
    <button type="button" data-control-id={`PC-32471-C-${IDS.eyedropper}`} disabled={locked||!!pickerUnavailable} title={pickerUnavailable??'锁定当前代理浮点画面后取色，非原始文件像素'} onClick={()=>void run(pick)}>吸管取色</button>
    <div data-control-id={`PC-32471-C-${IDS.saved}`}><span>收藏颜色 {colors.length}/6</span><button type="button" disabled={locked||colors.includes(value.colour)||colors.length===6} onClick={()=>void run(()=>save(value.colour))}>☆ 收藏当前颜色</button>
      <div className="blushSaved">{colors.map(c=><span key={c}><button type="button" aria-label={`使用收藏 ${c}`} title={c} style={{background:c}} disabled={locked} onClick={()=>updateColour(c)}/><button type="button" aria-label={`移除收藏 ${c}`} disabled={locked} onClick={()=>void run(()=>remove(c))}>×</button></span>)}</div>
      {colors.length===6&&<small>已满 6 色；移除一色后可添加，不会覆盖旧收藏。</small>}</div>
    <button type="button" disabled={locked} onClick={()=>commit(neutral())}>重置眼线</button>
    {(reason||error)&&<p role="alert">{error||reason}</p>}
    {busy&&<p role="status">正在确认人物修改，尚未报告应用成功。</p>}
    {fact?.reason==='no_measurable_change'&&<p role="status">当前颜色与程度未产生可测量变化。</p>}
    <small>图案预览仅示意形状，不是效果验收图。闭眼、裁切或眼睑支持不足会拒绝；请解除联动并将不可见的一眼归零。不会生成隐藏眼部。</small>
  </section>;
}
