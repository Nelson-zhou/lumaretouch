// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {SpillImage} from '../spillRemoval/model';
import {requestDecorationBatchImage,requestDecorationPresetImage,readDecorationBatchImage,readDecorationPresetImage,requestDecorationCohortImage} from '../native';
import {fetchDecorationImage} from './visualTransport';
import {verifyDecorationCoverage,type DecorationCoverage,type DecorationVisual} from './transferModel';
import {verifySupportAliasCoverage,type SupportAliasCoverage} from './supportAliasModel';
type Props={value:DecorationVisual;coverage:DecorationCoverage|SupportAliasCoverage;token:string;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean;cohort?:boolean;readImage?:(side:'before'|'after',live:()=>boolean)=>Promise<SpillImage>;preset?:{id:string;loadId:string}};
export function DecorationTransferReview(props:Props){return <Review key={props.reviewKey} {...props}/>;}
function Review({value,coverage,token,reviewKey,onReady,disabled=false,preset,cohort=false,readImage}:Props){
 const [pair,setPair]=useState<{before:SpillImage;after:SpillImage}|null>(null),[error,setError]=useState(''),[attempt,setAttempt]=useState(0),[zoom,setZoom]=useState(false);
 const [loaded,setLoaded]=useState({before:false,after:false}),[ack,setAck]=useState(false);
 const activeAttempt=useRef(attempt);activeAttempt.current=attempt;
 const notify=useRef(onReady);notify.current=onReady;const coverageKey=JSON.stringify(coverage);
 const support='support_change' in coverage;
 useLayoutEffect(()=>{notify.current(reviewKey,false);return()=>notify.current(reviewKey,false);},[reviewKey,coverageKey]);
 useEffect(()=>{
  setPair(null);setLoaded({before:false,after:false});setAck(false);setError('');notify.current(reviewKey,false);
  if(!attempt)return;let live=true;
  const api=preset?{request:requestDecorationPresetImage,read:readDecorationPresetImage}:{request:cohort?requestDecorationCohortImage:requestDecorationBatchImage,read:readDecorationBatchImage};
  void(async()=>{try{
   if(support&&!readImage)throw Error('装饰范围审核必须使用独立的完整成员图像读取通道。');
   const read=(side:'before'|'after')=>readImage?readImage(side,()=>live):fetchDecorationImage(api,{...(preset?{id:preset.id}:{}),documentId:preset?.loadId??value.document_id,preflightToken:token,revision:value.revision,side,sha256:value[side].sha256,requestId:crypto.randomUUID()},value[side],()=>live,cohort?'face_decoration_cohort_visual':'face_decoration_visual');
   const before=await read('before'),after=await read('after');
   if(!await (support?verifySupportAliasCoverage(value,coverage as SupportAliasCoverage):verifyDecorationCoverage(value,coverage as DecorationCoverage)))throw Error('目标可见范围与冻结摘要不一致');
   if(live)setPair({before,after});
  }catch(e){if(live)setError(String(e));}})();
  return()=>{live=false;};
 },[reviewKey,coverageKey,token,attempt,cohort]);
 const ready=!!pair&&loaded.before&&loaded.after&&!error,confirmed=ready&&ack;
 useEffect(()=>notify.current(reviewKey,confirmed),[reviewKey,confirmed]);
 function displayed(side:'before'|'after',generation:number,image?:HTMLImageElement){if(activeAttempt.current!==generation)return;const ok=!!image&&image.naturalWidth===value[side].width&&image.naturalHeight===value[side].height;setLoaded(old=>({...old,[side]:ok}));if(!ok){setAck(false);notify.current(reviewKey,false);setError('审核图像解码尺寸不匹配，请重新读取。');}}
 return <section aria-label="脸部装饰完整目标前后审核" style={{flexBasis:'100%'}}>
  <strong>本照片完整编辑链的真实前后效果，尚未应用</strong>{cohort&&<p>持久关联包括源成员及每一目标。更新或解除关联仍检查每张照片保留的装饰；共同参数不复制人物分析、皮肤笔画或恢复向量。</p>}
  <p>{support ? '包含本照片自己的裁切、色彩、修复和其他效果，仅替换所选人物在这组共享来源中的可见皮肤范围。图案、程度及恢复向量不改变；不会给其他人物借用此范围。' : '包含本次全部所选参数和目标已有装饰，不是单独叠加图案的示意图。仅传递图案与程度；每张照片使用自己审核的可见皮肤范围，不复制源图笔刷、坐标或恢复蒙版。'}</p>
  <ul>{coverage.targets.map(row=><li key={row.face_ref.face_instance_id}>人脸 {row.face_ref.face_instance_id}：{'before_visibility_sha256' in row ? row.before_visibility_sha256===row.visibility_sha256?'保留原有支持与装饰配方。':'此次仅改变该人物的可见皮肤支持；完整效果仍须审核。' : row.scope==='neutral-no-effect'?'候选装饰程度为零；已有装饰的移除仍须查看前后图。':'使用该人物自己审核的可见皮肤范围。'}</li>)}</ul>
  <button type="button" disabled={disabled||attempt>0&&!pair&&!error} onClick={()=>setAttempt(n=>n+1)}>{pair?'重新读取前后图':'读取本照片完整前后图'}</button>
  {error&&<p role="alert">{error}</p>}
  {pair&&<><label><input type="checkbox" checked={zoom} onChange={e=>setZoom(e.target.checked)}/>按审核图原尺寸滚动查看</label>
   <div style={{display:'flex',flexWrap:'wrap',gap:12,overflow:'auto',maxHeight:900}}>{(['before','after'] as const).map(side=><figure key={`${attempt}:${side}`} style={{margin:0}}>
    <figcaption>{side==='before'?'当前真实效果':'完整候选，尚未应用'} · 原输出 {value[side==='before'?'before_output_size':'after_output_size'].join(' × ')} 像素</figcaption>
    <img src={`data:image/png;base64,${pair[side].base64}`} width={value[side].width} height={value[side].height} style={{maxWidth:zoom?'none':'100%',height:'auto'}} alt={`本照片完整${side==='before'?'修改前':'候选修改后'}审核图`} onLoad={e=>displayed(side,attempt,e.currentTarget)} onError={()=>displayed(side,attempt)}/>
   </figure>)}</div></>}
  <label><input type="checkbox" checked={confirmed} disabled={disabled||!ready} onChange={e=>{if(ready&&!disabled)setAck(e.target.checked);}}/>我已查看各人物、脸部图案、邻近人物与背景及全部所选效果，同意本照片的完整候选</label>
  <p><small>最长边最多 1024 像素的 RGB8 审核显示，不替代全分辨率照片验收。来源、修复、人物支持或参数变化后必须重新预检。人工范围不等于自动遮挡分割。</small></p>
 </section>;
}
