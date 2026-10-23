import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {verifyOriginalShadowImage,type OriginalShadowReview} from './model';

type ImageStatus='loading'|'ready'|'error';
type Props={value:OriginalShadowReview;reviewKey:string;disabled:boolean;onReady:(key:string,ready:boolean)=>void};
/** Independent original-shadow review: never presents a spill result as illumination. */
export function OriginalShadowPixelReview(props:Props){return <PixelReview key={props.reviewKey} {...props}/>;}
function PixelReview({value,reviewKey,disabled,onReady}:Props){
 const notify=useRef(onReady);notify.current=onReady;
 // Include payload bytes so even a malformed receipt reusing a token/hash cannot keep consent.
 const contentKey=JSON.stringify([reviewKey,value.before.base64,value.after.base64,value.before.width,value.before.height,value.after.width,value.after.height]);
 const current=useRef(contentKey);current.current=contentKey;
 const [loaded,setLoaded]=useState<{key:string;before:ImageStatus;after:ImageStatus}>({key:contentKey,before:'loading',after:'loading'});
 const [verified,setVerified]=useState<{key:string;status:ImageStatus}>({key:contentKey,status:'loading'});
 const [acknowledged,setAcknowledged]=useState<{key:string;checked:boolean}>({key:contentKey,checked:false});
 useLayoutEffect(()=>{
  notify.current(reviewKey,false);setLoaded({key:contentKey,before:'loading',after:'loading'});
  setVerified({key:contentKey,status:'loading'});setAcknowledged({key:contentKey,checked:false});
  return()=>notify.current(reviewKey,false);
 },[contentKey,reviewKey]);
 useEffect(()=>{let live=true;void Promise.all([verifyOriginalShadowImage(value.before),verifyOriginalShadowImage(value.after)]).then(results=>{
  if(live)setVerified({key:contentKey,status:results.every(Boolean)?'ready':'error'});
 },()=>{if(live)setVerified({key:contentKey,status:'error'});});return()=>{live=false;};},[contentKey]);
 const ready=loaded.key===contentKey&&loaded.before==='ready'&&loaded.after==='ready'&&verified.key===contentKey&&verified.status==='ready';
 const confirmed=ready&&acknowledged.key===contentKey&&acknowledged.checked;
 useEffect(()=>{notify.current(reviewKey,confirmed&&!disabled);},[reviewKey,confirmed,disabled]);
 function load(side:'before'|'after',element:HTMLImageElement){
  if(current.current!==contentKey)return;
  const image=value[side],ok=element.naturalWidth===image.width&&element.naturalHeight===image.height;
  setLoaded(previous=>previous.key===contentKey?{...previous,[side]:ok?'ready':'error'}:previous);
  if(!ok){notify.current(reviewKey,false);setAcknowledged({key:contentKey,checked:false});}
 }
 function fail(side:'before'|'after'){
  if(current.current!==contentKey)return;
  notify.current(reviewKey,false);setLoaded(previous=>previous.key===contentKey?{...previous,[side]:'error'}:previous);setAcknowledged({key:contentKey,checked:false});
 }
 const failed=loaded.key===contentKey&&(loaded.before==='error'||loaded.after==='error')||verified.key===contentKey&&verified.status==='error';
 return <section className="originalShadowPixelReview" aria-label="原图阴影真实前后审核">
  <strong>当前照片的真实前后效果，尚未应用</strong>
  <p>检查脚部与物品接触阴影、半影及主体边缘，尤其确认旧地面纹理、污渍和反光没有被错误保留。显示的是完整编辑链结果，不是源图截图或蒙版示意。</p>
  <div className="originalShadowComparison">{(['before','after'] as const).map(side=><figure key={side}>
   <figcaption>{side==='before'?'修改前':'原图阴影候选'} · {value[side].width} × {value[side].height}</figcaption>
   <img src={`data:image/png;base64,${value[side].base64}`} width={value[side].width} height={value[side].height}
    alt={side==='before'?'当前照片修改原图阴影前的真实渲染':'相同照片原图阴影候选的真实渲染'} onLoad={event=>load(side,event.currentTarget)} onError={()=>fail(side)}/>
  </figure>)}</div>
  {!ready&&<p role="status">{failed?'图像内容、CRC、SHA-256、尺寸或实际加载校验失败，不能应用。请重新生成审核。':'正在校验并加载两张真实 PNG…'}</p>}
  <label><input type="checkbox" disabled={disabled||!ready} checked={confirmed} onChange={event=>setAcknowledged({key:contentKey,checked:ready&&event.target.checked})}/>我已查看这次真实前后效果，接受所示原图阴影结果</label>
  <small>最长边 512 像素的审核图包含最终裁切与旋转，只用于显示。完整源像素处理不等于通过原尺寸画质或性能验收；照片、配方、蒙版或草稿变化后须重新审核。</small>
  {value.boundaries.map((boundary,index)=><p key={index}>{boundary}</p>)}
 </section>;
}
