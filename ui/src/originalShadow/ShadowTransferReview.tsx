import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {verifyShadowTransferImage,type ShadowTransferEvidence} from './transferModel';

type ImageStatus='loading'|'ready'|'error';
type ReviewProps={value:ShadowTransferEvidence;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean};
/** Neither verification nor loading alone counts as the user's per-target review. */
export function ShadowTransferReview(props:ReviewProps){return <TargetReview key={props.reviewKey} {...props}/>;}
function TargetReview({value,reviewKey,onReady,disabled=false}:ReviewProps){
  const notify=useRef(onReady);notify.current=onReady;
  const [images,setImages]=useState<{key:string;before:ImageStatus;after:ImageStatus}>({key:reviewKey,before:'loading',after:'loading'});
  const [verified,setVerified]=useState<{key:string;status:ImageStatus}>({key:reviewKey,status:'loading'});
  const [viewed,setViewed]=useState<{key:string;checked:boolean}>({key:reviewKey,checked:false});
  // Payload changes revoke readiness before paint, even if a broken receipt reuses its hash/key.
  useLayoutEffect(()=>{
    notify.current(reviewKey,false);
    setImages({key:reviewKey,before:'loading',after:'loading'});
    setVerified({key:reviewKey,status:'loading'});setViewed({key:reviewKey,checked:false});
    return()=>notify.current(reviewKey,false);
  },[reviewKey,value.before.base64,value.before.sha256,value.after.base64,value.after.sha256]);
  useEffect(()=>{
    let live=true;
    void Promise.all([verifyShadowTransferImage(value.before),verifyShadowTransferImage(value.after)])
      .then(results=>{if(live)setVerified({key:reviewKey,status:results.every(Boolean)?'ready':'error'});})
      .catch(()=>{if(live)setVerified({key:reviewKey,status:'error'});});
    return()=>{live=false;};
  },[reviewKey,value.before.base64,value.before.sha256,value.after.base64,value.after.sha256]);
  const loaded=images.key===reviewKey&&images.before==='ready'&&images.after==='ready';
  const checked=verified.key===reviewKey&&verified.status==='ready';
  const ready=loaded&&checked;
  const confirmed=ready&&viewed.key===reviewKey&&viewed.checked;
  useEffect(()=>{notify.current(reviewKey,confirmed);},[reviewKey,confirmed]);
  const failed=images.key===reviewKey&&(images.before==='error'||images.after==='error')||verified.key===reviewKey&&verified.status==='error';
  function load(which:'before'|'after',image:HTMLImageElement){
    const expected=value[which];
    const status=image.naturalWidth===expected.width&&image.naturalHeight===expected.height?'ready':'error';
    setImages(old=>old.key===reviewKey?{...old,[which]:status}:old);
    if(status==='error'){notify.current(reviewKey,false);setViewed({key:reviewKey,checked:false});}
  }
  function fail(which:'before'|'after'){
    notify.current(reviewKey,false);setImages(old=>old.key===reviewKey?{...old,[which]:'error'}:old);setViewed({key:reviewKey,checked:false});
  }
  return <section aria-label="本目标原图阴影前后审核" style={{flexBasis:'100%'}}>
    <strong>本目标真实前后预览，尚未应用</strong>
    <p>原图阴影：{value.parameters.enabled?'开启':'关闭'} · 强度 {value.parameters.strength}。混合 {value.parameters.blend}。只同步开关、强度和混合，不复制源图地面样本、主体或保留范围。</p>
    <p>启用时目标必须已独立审核同一均匀漫反射地面的样本、主体和阴影范围；同色污渍、纹理与反光仍可能产生误判。这不是 AI 提取。</p>
    <div style={{display:'flex',flexWrap:'wrap',gap:12}}>{(['before','after'] as const).map(which=><figure key={`${reviewKey}:${which}`} style={{margin:0}}>
      <figcaption>{which==='before'?'应用前':'应用后'} · {value[which==='before'?'before_output_size':'after_output_size'].join(' × ')} 像素</figcaption>
      <img src={`data:image/png;base64,${value[which].base64}`} width={value[which].width} height={value[which].height}
        style={{maxWidth:'100%',height:'auto'}} alt={`本目标${which==='before'?'当前':'候选'}完整编辑链的真实渲染缩略图`}
        onLoad={event=>load(which,event.currentTarget)} onError={()=>fail(which)}/>
    </figure>)}</div>
    {!ready&&<p role="status">{failed?'前后预览未通过 PNG 内容、尺寸或显示校验，不能确认；请重新预检。':'正在校验并显示本目标的两张真实预览…'}</p>}
    <label><input type="checkbox" checked={confirmed} disabled={disabled||!ready}
      onChange={event=>setViewed({key:reviewKey,checked:ready&&event.target.checked})}/>我已逐图查看本目标的前后效果，并确认本次参数</label>
    <p><small>先以完整源像素执行完整编辑链，再生成审核缩略图。缩略图只用于显示，不参与最终出片；同时同步裁剪时，前后构图可能不同。此确认不替代全分辨率验收。</small></p>
  </section>;
}
