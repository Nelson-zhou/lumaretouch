// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from the project current-photo fabric UI; canonical ownership is unchanged.
import {useEffect,useRef,useState} from 'react';
import {LimbVeinMaskEditor} from './LimbVeinMaskEditor';
import {emptyMasks,LIMB_LABELS,imageUrl,maskHasPaint,previewMatches,validImage,type LimbVeinPort,type LimbKind,type Image,type Masks,type PreviewPayload,type Reference} from './model';

/** The outer owner provides verified receipts and owns all writes, recovery and history. */
export function LimbVeinPanel({port,disabled=false}:{port:LimbVeinPort;disabled?:boolean}) {
  const ref=port.snapshot.reference;
  const valid=!!ref&&ref.protocol===1&&ref.family==='limb_vein'&&/^[a-f0-9]{32}$/.test(ref.reference_id)
    &&/^[a-f0-9]{64}$/.test(ref.fence)&&/^[a-f0-9]{64}$/.test(ref.source.sha256)
    &&Number.isSafeInteger(ref.source.width)&&ref.source.width>0&&Number.isSafeInteger(ref.source.height)&&ref.source.height>0
    &&Number.isFinite(ref.current_amount)&&ref.current_amount>=0&&ref.current_amount<=1&&validImage(ref.source_image)
    &&Math.abs(ref.source_image.width*ref.source.height-ref.source_image.height*ref.source.width)<=Math.max(ref.source.width,ref.source.height);
  const key=`${port.snapshot.bindingKey??'none'}:${valid?ref!.reference_id:'unread'}`;
  return <LimbVeinEditor key={key} port={port} reference={valid?ref:null} disabled={disabled}/>;
}
function ProofImage({image,label,onLoaded}:{image:Image;label:string;onLoaded:(ready:boolean)=>void}) {
  return <figure style={{margin:0}}><figcaption>{label}</figcaption><img src={imageUrl(image)} alt={label} draggable={false}
    style={{display:'block',width:'100%',height:'auto'}} onLoad={event=>onLoaded(event.currentTarget.naturalWidth===image.width&&event.currentTarget.naturalHeight===image.height)}
    onError={()=>onLoaded(false)}/></figure>;
}
function LimbVeinEditor({port,reference,disabled}:{port:LimbVeinPort;reference:Reference|null;disabled:boolean}) {
  const {snapshot}=port;
  const [masks,setMasks]=useState<Masks>(emptyMasks),[amount,setAmount]=useState(reference?.current_amount||.5),[radius,setRadius]=useState(16);
  const [limbKind,setLimbKind]=useState<LimbKind>('hand');
  const [sameLimb,setSameLimb]=useState(false),[cleanReference,setCleanReference]=useState(false),[sourceReady,setSourceReady]=useState(false);
  const [reviewed,setReviewed]=useState(false),[localBusy,setLocalBusy]=useState(false),[error,setError]=useState('');
  const [loaded,setLoaded]=useState<Record<string,boolean>>({});
  const inFlight=useRef(false),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  // Asynchronous ownership is outside the panel; local busy prevents duplicate clicks before its next snapshot.
  const blocked=disabled||localBusy||snapshot.pending||snapshot.uncertain||snapshot.refreshRequired||!snapshot.bindingKey;
  const invalidate=()=>{setReviewed(false);setLoaded({});};
  const request:PreviewPayload|null=reference&&sameLimb&&cleanReference&&sourceReady&&['limb','target','reference'].every(role=>maskHasPaint(masks[role as keyof Masks]))
    ?{reference_id:reference.reference_id,amount,radius_px:radius,review:{version:1,domain:'source-normalized',...masks,limb_kind:limbKind,same_limb_confirmed:true,clean_reference_confirmed:true}}:null;
  const preview=reference&&previewMatches(snapshot.preview,request,reference)?snapshot.preview.value:null;
  const previewKey=preview?`${preview.preview_id}:${preview.candidate_sha256}`:'';
  const imagesReady=!!preview&&['before','after','mask'].every(role=>loaded[`${previewKey}:${role}`]);
  const run=async(action:()=>Promise<void>)=>{
    if(blocked||inFlight.current)return;inFlight.current=true;setLocalBusy(true);setError('');
    try{await action();}catch(caught){if(mounted.current)setError(String(caught));}
    finally{inFlight.current=false;if(mounted.current)setLocalBusy(false);}
  };
  return <section className="limbVeinPanel" aria-label="参考辅助手脚青筋减淡">
    <strong>手脚青筋减淡</strong>
    <p><small>手动标记同一手背、前臂或脚背的青筋与干净皮肤参考。低强度先减淡色偏，超过 50% 后逐步增加有界明暗软化；不是自动血管识别、几何塑形或医疗处理。最终质感尚未验收。</small></p>
    <button type="button" disabled={blocked} onClick={()=>void run(port.reference)}>读取当前照片来源</button>
    {reference&&<>
      <label>当前部位<select value={limbKind} disabled={blocked} onChange={event=>{setLimbKind(event.target.value as LimbKind);setSameLimb(false);setCleanReference(false);invalidate();}}>{(Object.keys(LIMB_LABELS) as LimbKind[]).map(kind=><option key={kind} value={kind}>{LIMB_LABELS[kind]}</option>)}</select></label>
      <LimbVeinMaskEditor binding={`${snapshot.bindingKey}:${reference.reference_id}`} source={reference.source} image={reference.source_image}
        masks={masks} disabled={blocked} onReady={value=>{setSourceReady(value);if(!value)invalidate();}} onDraftStart={invalidate}
        onChange={next=>{setMasks(next);invalidate();}}/>
      <label><input type="checkbox" checked={sameLimb} disabled={blocked} onChange={event=>{setSameLimb(event.target.checked);invalidate();}}/>各区域属于当前照片同一处可见皮肤，已保护指甲、饰品、纹身和肢体边缘</label>
      <label><input type="checkbox" checked={cleanReference} disabled={blocked} onChange={event=>{setCleanReference(event.target.checked);invalidate();}}/>绿色参考为同一部位的干净皮肤，光照可比较，不含青筋、纹身或强高光</label>
      <label>修正强度 {Math.round(amount*100)}%<input type="range" min="0" max="100" step="1" value={Math.round(amount*100)} disabled={blocked}
        onChange={event=>{setAmount(Number(event.target.value)/100);invalidate();}}/></label>
      <label>低频半径（原图像素）<input type="number" min="2" max="128" step="1" value={radius} disabled={blocked}
        onChange={event=>{const value=Number(event.target.value);if(Number.isInteger(value)&&value>=2&&value<=128){setRadius(value);invalidate();}}}/></label>
      <p><small>半径 2–128 是本地算法范围，不是官方产品参数。画笔与参数修改仅是草稿，点击更新后才生成对比图。</small></p>
      <div className="prow"><button type="button" disabled={blocked||!request||amount<=0||reference.capability.available!==true}
        onClick={()=>{if(request){invalidate();void run(()=>port.preview(request));}}}>更新效果</button>
        <button type="button" disabled={blocked||reference.current_amount<=0} onClick={()=>void run(port.clear)}>清除本照片青筋修正</button></div>
      {!reference.capability.available&&<p role="status">{reference.capability.reason||'青筋修正运行库不可用；不使用替代滤镜。'}</p>}
    </>}
    {preview&&<div key={previewKey}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(180px,1fr))',gap:8}}>
        {(['before','after','mask'] as const).map(role=><ProofImage key={`${previewKey}:${role}`} image={preview[role]}
          label={role==='before'?'修改前（完整合成）':role==='after'?'修改后（完整合成）':'原图坐标蒙版（未裁剪／旋转）'}
          onLoaded={ready=>{setLoaded(old=>({...old,[`${previewKey}:${role}`]:ready}));if(!ready)setReviewed(false);}}/>)}
      </div>
      <label><input type="checkbox" disabled={blocked||!imagesReady} checked={reviewed} onChange={event=>setReviewed(event.target.checked)}/>
        已检查前后效果和实际范围，没有误改关节、指甲、饰品、纹身或肢体边缘</label>
      <button type="button" disabled={blocked||!imagesReady||!reviewed} onClick={()=>void run(()=>port.confirm({preview_id:preview.preview_id,reviewed:true,
        before_sha256:preview.before.sha256,after_sha256:preview.after.sha256,mask_sha256:preview.mask.sha256,candidate_sha256:preview.candidate_sha256}))}>确认应用</button>
    </div>}
    {reference&&!request&&<p role="status"><small>请选择部位，标记可见皮肤范围、青筋与干净参考，并确认参考条件后更新效果。</small></p>}
    {(snapshot.uncertain||snapshot.refreshRequired)&&<p role="status">{snapshot.uncertain?'上一操作结果尚未确定，请等待现有请求核对，不要重复提交。':'照片状态正在刷新，暂不接受新的修改。'}</p>}
    {(error||snapshot.message)&&<p role="status">{error||snapshot.message}</p>}
  </section>;
}
