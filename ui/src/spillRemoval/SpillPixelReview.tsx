import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {verifySpillImage,type SpillReview} from './model';

/** A matching receipt, two verified PNGs, two real image loads, then consent. */
export function SpillPixelReview({value,reviewKey,onReady}:{value:SpillReview;reviewKey:string;onReady:(key:string,ready:boolean)=>void}){
 const notify=useRef(onReady);notify.current=onReady;
 const [loaded,setLoaded]=useState({before:false,after:false}),[verified,setVerified]=useState<'loading'|'ready'|'error'>('loading');
 const [failed,setFailed]=useState(false),[acknowledged,setAcknowledged]=useState(false);
 useLayoutEffect(()=>{notify.current(reviewKey,false);return()=>notify.current(reviewKey,false);},[reviewKey]);
 useEffect(()=>{let live=true;void Promise.all([verifySpillImage(value.before),verifySpillImage(value.after)]).then(results=>{
  if(live)setVerified(results.every(Boolean)?'ready':'error');
 },()=>{if(live)setVerified('error');});return()=>{live=false;};},[value.before,value.after,reviewKey]);
 const ready=loaded.before&&loaded.after&&verified==='ready'&&!failed;
 useEffect(()=>{notify.current(reviewKey,ready&&acknowledged);},[reviewKey,ready,acknowledged]);
 return <section className="spillPixelReview" aria-label="背景反光祛染实际前后审核">
  <strong>实际前后图像，尚未应用</strong>
  <p>检查背景色污染、主体边缘及需保留的真实颜色。手工覆盖只限制本次祛染范围，不把范围内所有颜色统一去饱和。</p>
  <div className="spillComparison">{(['before','after'] as const).map(side=>{
   const image=value[side];return <figure key={side}><figcaption>{side==='before'?'修改前':'祛染候选'} · {image.width} × {image.height}</figcaption>
    <img src={`data:image/png;base64,${image.base64}`} width={image.width} height={image.height}
     alt={side==='before'?'当前照片祛染修改前的实际渲染':'相同当前来源的祛染候选实际渲染'}
     onLoad={event=>{const ok=event.currentTarget.naturalWidth===image.width&&event.currentTarget.naturalHeight===image.height;setLoaded(previous=>({...previous,[side]:ok}));if(!ok)setFailed(true);}}
     onError={()=>{setFailed(true);setLoaded(previous=>({...previous,[side]:false}));}}/>
   </figure>;
  })}</div>
  {!ready&&<p role="status">{failed||verified==='error'?'图像加载、尺寸或 SHA-256 校验失败，不能应用。请重新生成审核。':'正在加载并核验两张实际 PNG…'}</p>}
  <label><input type="checkbox" disabled={!ready} checked={acknowledged} onChange={event=>setAcknowledged(event.target.checked)}/>我已查看这次真实前后效果，接受所示祛染结果</label>
  <small>审核图最长边 640 像素，不代表原尺寸画质验收。当前照片、配方或覆盖范围变化后必须重新审核。</small>
  {value.boundaries.map((boundary,index)=><p key={index}>{boundary}</p>)}
 </section>;
}
