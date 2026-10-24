import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {verifyCollarboneCoverage,type CollarboneVisual} from './transferModel';
import {requestCollarboneImage,readCollarboneImage} from '../native';
import {fetchCollarboneImage} from './visualTransport';
import type {SpillImage} from '../spillRemoval/model';
import type {CollarboneCoverage} from '../people/transferProof';
type ImageStatus='loading'|'ready'|'error';
export type CollarboneImageLoader=(side:'before'|'after',live:()=>boolean)=>Promise<SpillImage>;
type ReviewProps={value:CollarboneVisual;coverage:CollarboneCoverage;preflightToken:string;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean;imageLoader?:CollarboneImageLoader;preset?:boolean};
export function CollarboneTransferReview(props:ReviewProps){return <TargetReview key={props.reviewKey} {...props}/>;}
function TargetReview({value,coverage,preflightToken,reviewKey,onReady,disabled=false,imageLoader,preset=false}:ReviewProps){
  const [pair,setPair]=useState<{before:SpillImage;after:SpillImage}|null>(null),[requestError,setRequestError]=useState('');
  const [loadAttempt,setLoadAttempt]=useState(0);
  const [zoom,setZoom]=useState(false);
  const coverageKey=JSON.stringify(coverage);
  const notify=useRef(onReady);notify.current=onReady;
  const [images,setImages]=useState<{key:string;before:ImageStatus;after:ImageStatus}>({key:reviewKey,before:'loading',after:'loading'});
  const [verified,setVerified]=useState<{key:string;coverage:string;status:ImageStatus}>({key:reviewKey,coverage:coverageKey,status:'loading'});
  const [viewed,setViewed]=useState<{key:string;checked:boolean}>({key:reviewKey,checked:false});
  useLayoutEffect(()=>{
    notify.current(reviewKey,false);setImages({key:reviewKey,before:'loading',after:'loading'});
    setViewed({key:reviewKey,checked:false});
    return()=>notify.current(reviewKey,false);
  },[reviewKey,pair,coverageKey]);
  useEffect(()=>{
    if(!loadAttempt)return;
    let live=true;setPair(null);setRequestError('');notify.current(reviewKey,false);
    const api={request:requestCollarboneImage,read:readCollarboneImage};
    const fetchSide=(side:'before'|'after')=>imageLoader?imageLoader(side,()=>live):fetchCollarboneImage(api,{preflightToken,documentId:value.document_id,revision:value.revision,side,sha256:value[side].sha256,requestId:crypto.randomUUID()},value[side],()=>live);
    void (async()=>{try{
      const before=await fetchSide('before'),after=await fetchSide('after');
      if(!await verifyCollarboneCoverage(value,coverage))throw Error('目标覆盖范围与冻结摘要不一致');
      if(live){setPair({before,after});setVerified({key:reviewKey,coverage:coverageKey,status:'ready'});}
    }catch(error){if(live){setRequestError(String(error));setVerified({key:reviewKey,coverage:coverageKey,status:'error'});}}})();
    return()=>{live=false;};
  },[reviewKey,preflightToken,coverageKey,loadAttempt]);
  const ready=!!pair&&images.key===reviewKey&&images.before==='ready'&&images.after==='ready'&&verified.key===reviewKey&&verified.coverage===coverageKey&&verified.status==='ready';
  const confirmed=ready&&viewed.key===reviewKey&&viewed.checked;
  useEffect(()=>{notify.current(reviewKey,confirmed);},[reviewKey,confirmed]);
  const failed=images.key===reviewKey&&(images.before==='error'||images.after==='error')||verified.key===reviewKey&&verified.status==='error';
  function load(which:'before'|'after',image:HTMLImageElement){
    const expected=value[which],status=image.naturalWidth===expected.width&&image.naturalHeight===expected.height?'ready':'error';
    setImages(old=>old.key===reviewKey?{...old,[which]:status}:old);
    if(status==='error'){notify.current(reviewKey,false);setViewed({key:reviewKey,checked:false});}
  }
  function fail(which:'before'|'after'){
    notify.current(reviewKey,false);setImages(old=>old.key===reviewKey?{...old,[which]:'error'}:old);setViewed({key:reviewKey,checked:false});
  }
  return <section aria-label="本目标锁骨增强前后审核" style={{flexBasis:'100%'}}>
    <strong>本次冻结目标的真实前后预览，尚未应用</strong>
    <p>这里显示预检时冻结目标完整编辑链的实际应用前后效果，{preset?'包含预设所选的人像与非人像模块，不是仅叠加锁骨的示意图。':'包含本次同时选择的其他人物参数。'}只传递数值，不复制源图锁骨曲线、身体蒙版、类别确认或人物关联。零强度也必须审核，因其可能移除目标已有增强。</p>
    <p>每张目标的可见锁骨范围与类别来自其独立审核。下方可切换原尺寸显示并滚动检查细节；图像最长边最多 1024 像素，不替代全分辨率照片验收。预检后若照片或支持证据改变，提交会拒绝，不能用旧图授权新状态。</p>
    <ul>{coverage.targets.map(row=><li key={row.face_ref.face_instance_id}>本人脸 {row.face_ref.face_instance_id}：{row.scope==='neutral-no-effect'
      ?'候选强度为零，不据此声明存在类别或身体审核；应用前的已有作用仍显示在真实前图。'
      :`候选使用本成员独立审核的可见锁骨，用户确认类别 ${row.clavicle_category==='female'?'女':'长辈女'}，图像侧 ${row.clavicle_sides.map(side=>side==='left'?'左':'右').join('、')}。`}</li>)}</ul>
    <button type="button" disabled={disabled||!!loadAttempt&&!pair&&!requestError} onClick={()=>setLoadAttempt(n=>n+1)}>{pair?'重新读取本目标图像':'读取本目标真实前后图像'}</button>
    {!!requestError&&<p role="alert">{requestError}</p>}
    <label><input type="checkbox" checked={zoom} onChange={e=>setZoom(e.target.checked)}/>按审核图原尺寸显示，滚动检查锁骨细节</label>
    {pair&&<div style={{display:'flex',flexWrap:'wrap',gap:12,overflow:'auto',maxHeight:900}}>{(['before','after'] as const).map(which=><figure key={`${reviewKey}:${which}`} style={{margin:0}}>
      <figcaption>{which==='before'?'应用前':'应用后'} · {value[which==='before'?'before_output_size':'after_output_size'].join(' × ')} 像素</figcaption>
      <img src={`data:image/png;base64,${pair[which].base64}`} width={value[which].width} height={value[which].height}
        style={{maxWidth:zoom?'none':'100%',height:'auto'}} alt={`本目标实际锁骨及完整图像的${which==='before'?'当前':'候选'}完整编辑链真实渲染缩略图`}
        onLoad={event=>load(which,event.currentTarget)} onError={()=>fail(which)}/>
    </figure>)}</div>}
    {!ready&&<p role="status">{failed?'前后预览未通过 PNG 内容、尺寸或显示校验，不能确认；请重新预检。':!loadAttempt?'请先读取并检查本目标的两张真实预览。':'正在校验并显示本目标的两张真实预览…'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled||!ready}
      onChange={event=>setViewed({key:reviewKey,checked:ready&&event.target.checked})}/>我已查看本目标锁骨、身体及同时选择参数的真实前后效果，确认{preset?'本次完整预设应用':'本次同步'}</label>
    <p><small>先用目标完整源像素与目标独立审核执行完整编辑链，再生成审核缩略图。缩略图不参与最终出片；这不是源图效果示意，也不替代全分辨率验收。</small></p>
  </section>;
}
