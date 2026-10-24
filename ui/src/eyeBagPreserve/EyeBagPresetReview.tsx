// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {verifyEyeBagCoverage,type EyeBagPresetReview as Review} from './presetModel';
import {fetchEyeBagPresetImage} from './presetTransport';
import {requestEyeBagPresetImage,readEyeBagPresetImage} from '../native';
import type {SpillImage} from '../spillRemoval/model';
type Props={value:Review;id:string;token:string;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean};
export function EyeBagPresetReview(props:Props){return <ReviewPair key={props.reviewKey} {...props}/>;}
function ReviewPair({value,id,token,reviewKey,onReady,disabled=false}:Props){
 const [pair,setPair]=useState<{before:SpillImage;after:SpillImage}|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState('');
 const [loaded,setLoaded]=useState({before:false,after:false}),[checked,setChecked]=useState(false),[zoom,setZoom]=useState(false);
 const notify=useRef(onReady);notify.current=onReady;const current=useRef(pair);current.current=pair;
 useEffect(()=>{notify.current(reviewKey,false);return()=>notify.current(reviewKey,false);},[reviewKey]);
 useEffect(()=>{
  if(!attempt)return;let live=true;setPair(null);setError('');setLoaded({before:false,after:false});setChecked(false);notify.current(reviewKey,false);
  void (async()=>{try{
   const api={request:requestEyeBagPresetImage,read:readEyeBagPresetImage};
   const fetchSide=(side:'before'|'after')=>fetchEyeBagPresetImage(api,{id,documentId:value.load_id,preflightToken:token,revision:value.visual.revision,side,sha256:value.visual[side].sha256,requestId:crypto.randomUUID()},value.visual[side],()=>live);
   const before=await fetchSide('before'),after=await fetchSide('after');
   if(!await verifyEyeBagCoverage(value))throw Error('本人物逐眼保护与冻结摘要不一致');
   if(live)setPair({before,after});
  }catch(e){if(live)setError(String(e));}})();return()=>{live=false;};
 },[attempt,reviewKey,id,token,value]);
 const ready=!!pair&&loaded.before&&loaded.after&&!error;
 useEffect(()=>{notify.current(reviewKey,ready&&checked);},[reviewKey,ready,checked]);
 function onLoad(side:'before'|'after',image:HTMLImageElement){if(current.current!==pair)return;const expected=value.visual[side];
  if(image.naturalWidth!==expected.width||image.naturalHeight!==expected.height){setError('审核图像显示尺寸不符');setChecked(false);return;}
  setLoaded(old=>({...old,[side]:true}));}
 return <section aria-label="去眼袋 v2 完整预设当前人物审核">
  <strong>当前照片的完整混合预设前后效果，尚未应用</strong>
  <p>仅转移版本、去眼袋强度和卧蚕保留程度。目标使用自己的逐眼手绘审核；不复制供图的保护蒙版、恢复笔迹或人物分析。未审核眼不据此获得处理资格。</p>
  <p>{value.replace_legacy?'本次已选择显式替换目标旧版去眼袋意图；黑眼圈等其他眼部效果不因此清零。':'不替换旧版去眼袋。若新旧操作存在冲突，应先明确选择替换并重新预检，不能静默重解释旧配方。'}</p>
  {value.coverage.targets.map(row=><p key={row.face_ref.face_instance_id}>目标人物 {row.face_ref.face_instance_id}：{row.scope==='neutral-no-effect'?'候选强度为零；不要求或声称存在活动保护审核。':`使用本目标已审核的本人${row.sides.map(side=>side==='left'?'左':'右').join('、')}眼保护。`}</p>)}
  <button disabled={disabled||!!attempt&&!pair&&!error} onClick={()=>setAttempt(n=>n+1)}>{pair?'重新读取冻结图像':'读取实际完整前后图像'}</button>
  {!!error&&<p role="alert">{error}</p>}
  <label><input type="checkbox" checked={zoom} onChange={e=>setZoom(e.target.checked)}/>按审核图原尺寸查看</label>
  {pair&&<div style={{display:'flex',flexWrap:'wrap',gap:12,maxHeight:900,overflow:'auto'}}>{(['before','after'] as const).map(side=><figure key={`${attempt}:${side}`} style={{margin:0}}>
   <figcaption>{side==='before'?'应用前':'完整预设应用后'} · 完整输出 {value.visual[side==='before'?'before_output_size':'after_output_size'].join(' × ')}</figcaption>
   <img src={`data:image/png;base64,${pair[side].base64}`} width={value.visual[side].width} height={value.visual[side].height} style={{maxWidth:zoom?'none':'100%',height:'auto'}}
    alt={side==='before'?'当前照片完整编辑链应用前':'当前照片完整混合预设候选'} onLoad={e=>onLoad(side,e.currentTarget)} onError={()=>{if(current.current===pair){setError('审核图像未显示');setChecked(false);}}}/>
  </figure>)}</div>}
  <p><small>先计算完整源图及全部所选效果，再生成最长边不超过 1024 像素的 RGB8 审核图；不是眼部原生像素裁剪，不代替全分辨率照片验收。目标手绘审核不是自动解剖分割。</small></p>
  <label><input type="checkbox" disabled={disabled||!ready} checked={ready&&checked} onChange={e=>setChecked(ready&&e.target.checked)}/>我已比较本人物逐眼保护与完整预设前后效果，同意本次冻结应用</label>
 </section>;
}
