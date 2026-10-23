import {useEffect,useRef,useState} from 'react';
import {INSPECTION_EDIT_INTENT,requestColorScopes} from '../native';
import {histogramPoints,matchesScope,type ScopeResult,type ScopeStage} from '../colorScopesModel';
const stages:Record<ScopeStage,string>={original:'工作空间原图（未裁剪）','levels-input':'色阶输入（曝光与扩展影调后）',
  'curves-input':'曲线输入（色阶后）',output:'最终结果（量化前）'};
const colours=['#f47777','#7acc8a','#7aa8ff','#ddd'];
export function HistogramPanel({documentId,snapshotId,revision,result,disabled,onDone}:{
  documentId:string;snapshotId?:string;revision:number;result?:ScopeResult|null;disabled:boolean;onDone:()=>void;
}){
  const [stage,setStage]=useState<ScopeStage>('output'),[channel,setChannel]=useState('rgb');
  const [logarithmic,setLogarithmic]=useState(false),[shown,setShown]=useState<ScopeResult|null>(null);
  const [waiting,setWaiting]=useState(false),[error,setError]=useState('');
  const pending=useRef<{id:string;revision:number}|null>(null);
  const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
  function clearTimer(){if(timer.current!==null){clearTimeout(timer.current);timer.current=null;}}
  useEffect(()=>{const invalidate=()=>{pending.current=null;clearTimer();setShown(null);setWaiting(false);};
    window.addEventListener(INSPECTION_EDIT_INTENT,invalidate);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,invalidate);clearTimer();pending.current=null;};},[]);
  useEffect(()=>{if(pending.current&&pending.current.revision!==revision){pending.current=null;clearTimer();setWaiting(false);}
    if(shown?.host_doc_rev!==revision)setShown(null);
  },[revision]);
  useEffect(()=>{
    if(!matchesScope(result,pending.current?.id,documentId,revision,stage))return;
    pending.current=null;clearTimer();setWaiting(false);
    if(result.success&&result.analysis&&result.quality==='sampled-proxy-float'){setShown(result);setError('');}
    else {setShown(null);setError(result.error??'颜色统计不可用');}
  },[result,documentId,revision,stage]);
  function refresh(){
    if(disabled||!documentId||snapshotId!==documentId)return;
    const id=crypto.randomUUID();pending.current={id,revision};clearTimer();setShown(null);setError('');setWaiting(true);
    timer.current=setTimeout(()=>{if(pending.current?.id===id){pending.current=null;setWaiting(false);setError('统计尚未返回，请稍后刷新');}},30000);
    void requestColorScopes(documentId,id,stage).then(onDone).catch(e=>{
      if(pending.current?.id===id){pending.current=null;clearTimer();setWaiting(false);setError(String(e));}
    });
  }
  const current=shown?.document_id===documentId&&snapshotId===documentId&&shown.host_doc_rev===revision&&shown.stage===stage?shown:null;
  const analysis=current?.analysis;
  const histograms=analysis?[...analysis.rgb,analysis.linear_y]:[];
  const indexes=channel==='rgb'?[0,1,2]:[Number(channel)];
  const maximum=Math.max(1,...indexes.flatMap(i=>histograms[i]?.bins??[]));
  return <fieldset data-readonly-scopes disabled={disabled||!documentId||snapshotId!==documentId} style={{border:'1px solid #45454b',borderRadius:6,padding:8}}>
    <legend>直方图 · 工作 sRGB</legend>
    <select aria-label="直方图处理阶段" value={stage} onChange={e=>{pending.current=null;clearTimer();setWaiting(false);setShown(null);setStage(e.target.value as ScopeStage);}}>
      {Object.entries(stages).map(([key,label])=><option key={key} value={key}>{label}</option>)}
    </select>
    <div style={{display:'flex',gap:6,margin:'8px 0'}}>
      <select aria-label="直方图通道" value={channel} onChange={e=>setChannel(e.target.value)}>
        <option value="rgb">RGB 叠加</option><option value="0">红</option><option value="1">绿</option><option value="2">蓝</option><option value="3">线性亮度 Y</option>
      </select>
      <label><input type="checkbox" checked={logarithmic} onChange={e=>setLogarithmic(e.target.checked)}/>对数纵轴</label>
      <button type="button" disabled={waiting} onClick={refresh}>{waiting?'统计中…':'刷新'}</button>
    </div>
    <svg role="img" aria-label="当前阶段采样直方图" viewBox="0 0 255 100" style={{width:'100%',background:'#202025',display:'block'}}>
      {analysis&&indexes.map(i=><polyline key={i} points={histogramPoints(histograms[i],maximum,logarithmic)} fill="none" stroke={colours[i]} strokeWidth="1"/>)}
    </svg>
    {error&&<p role="status">{error}</p>}
    {!analysis&&!error&&<small>{waiting?'正在分析当前配方…':'点击刷新读取当前配方；编辑后旧统计会立即隐藏。'}</small>}
    {analysis&&<>
      <small>代理浮点采样：{current?.sampled_pixels} / {current?.eligible_pixels} 像素，256 桶。不是全源直方图。</small>
      <div>非有限样本：{analysis.nonfinite_samples}</div>
      {indexes.map(i=><div key={i}>{['R','G','B','Y'][i]}：低于 0 {histograms[i].underflow}，高于 1 {histograms[i].overflow}</div>)}
      <div>采样 RGB 均值：{analysis.mean_srgb?.map(v=>v.toFixed(4)).join(' / ')??'无有效样本'}</div>
      <div>该均值的 Lab（D65）：{analysis.mean_lab_d65?.map(v=>v.toFixed(2)).join(' / ')??'无有效样本'}</div>
      <small>这是采样均值，不是点取色。RGB 横轴为编码值；Y 横轴为线性亮度。范围外计数不混入端点桶。</small>
    </>}
  </fieldset>;
}
