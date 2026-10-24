import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {verifyTorsoTransferImage,type TorsoTransferEvidence} from './transferModel';
type ImageStatus='loading'|'ready'|'error';
type ReviewProps={value:TorsoTransferEvidence;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean};
export function TorsoTransferReview(props:ReviewProps){return <TargetReview key={props.reviewKey} {...props}/>;}
function TargetReview({value,reviewKey,onReady,disabled=false}:ReviewProps){
  const notify=useRef(onReady);notify.current=onReady;
  const [images,setImages]=useState<{key:string;before:ImageStatus;after:ImageStatus}>({key:reviewKey,before:'loading',after:'loading'});
  const [verified,setVerified]=useState<{key:string;status:ImageStatus}>({key:reviewKey,status:'loading'});
  const [viewed,setViewed]=useState<{key:string;checked:boolean}>({key:reviewKey,checked:false});
  useLayoutEffect(()=>{
    notify.current(reviewKey,false);setImages({key:reviewKey,before:'loading',after:'loading'});
    setVerified({key:reviewKey,status:'loading'});setViewed({key:reviewKey,checked:false});
    return()=>notify.current(reviewKey,false);
  },[reviewKey,value.before.base64,value.before.sha256,value.after.base64,value.after.sha256]);
  useEffect(()=>{
    let live=true;
    void Promise.all([verifyTorsoTransferImage(value.before),verifyTorsoTransferImage(value.after)])
      .then(results=>{if(live)setVerified({key:reviewKey,status:results.every(Boolean)?'ready':'error'});})
      .catch(()=>{if(live)setVerified({key:reviewKey,status:'error'});});
    return()=>{live=false;};
  },[reviewKey,value.before.base64,value.before.sha256,value.after.base64,value.after.sha256]);
  const ready=images.key===reviewKey&&images.before==='ready'&&images.after==='ready'&&verified.key===reviewKey&&verified.status==='ready';
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
  return <section aria-label="本目标上身长度前后审核" style={{flexBasis:'100%'}}>
    <strong>本目标真实前后预览，尚未应用</strong>
    <p>上身长度：{Math.round(value.parameters.amount*100)}。只同步版本与长度标量，不复制源图身体、关键点、归属、支持范围或审核。</p>
    <p>目标身体：{value.body_ref.body_instance_id} · 身体分析版本 {value.body_ref.analysis_revision}；本人面部：{value.associated_face.associated_face_ref.face_instance_id} · 面部分析版本 {value.associated_face.associated_face_ref.analysis_revision}。</p>
    <p>仅接受一个已启用且已有独立可见身体与本人面部归属审核的目标身体。多个启用身体或归属不明确时拒绝，不自动关联人物，也不补齐遮挡轮廓；其他禁用身体的参数与归属保留，背景、头发、双臂和衣纹仍可能移动。</p>
    <div style={{display:'flex',flexWrap:'wrap',gap:12}}>{(['before','after'] as const).map(which=><figure key={`${reviewKey}:${which}`} style={{margin:0}}>
      <figcaption>{which==='before'?'应用前':'应用后'} · {value[which==='before'?'before_output_size':'after_output_size'].join(' × ')} 像素</figcaption>
      <img src={`data:image/png;base64,${value[which].base64}`} width={value[which].width} height={value[which].height}
        style={{maxWidth:'100%',height:'auto'}} alt={`本目标实际身体及本人面部的${which==='before'?'当前':'候选'}完整编辑链真实渲染缩略图`}
        onLoad={event=>load(which,event.currentTarget)} onError={()=>fail(which)}/>
    </figure>)}</div>
    {!ready&&<p role="status">{failed?'前后预览未通过 PNG 内容、尺寸或显示校验，不能确认；请重新预检。':'正在校验并显示本目标的两张真实预览…'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled||!ready}
      onChange={event=>setViewed({key:reviewKey,checked:ready&&event.target.checked})}/>我已逐图查看本目标身体与本人面部的前后效果，并确认本次长度参数</label>
    <p><small>先用目标完整源像素、实际身体和本人面部执行完整编辑链，再生成审核缩略图。缩略图不参与最终出片；这不是源图效果示意，也不替代全分辨率验收。</small></p>
  </section>;
}
