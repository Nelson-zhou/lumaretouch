import React, {useEffect,useRef,useState} from 'react';
import {check,Control,labels,names,neutral,receipt,Request,requirements,same,Spec} from './model';
export type Props={documentId:string;revision:number;spec:Spec;monochrome:boolean;disabled?:boolean;reason?:string;send:(r:Request)=>Promise<unknown>;query:(id:string)=>Promise<unknown>;refresh:()=>Promise<void>;readback:()=>Promise<{document_id:string;spec:Spec}>;cancel:(id:string)=>Promise<void>};
const pendingKey='lrt.extended-tone.pending.v1';
function savedRequest():Request|null {try{const raw=sessionStorage.getItem(pendingKey);if(!raw)return null;const r=JSON.parse(raw) as Request;if(r.cmd!=='extended_tone'||!r.request_id||!r.document_id||!Number.isSafeInteger(r.revision)||!['set','reset'].includes(r.action))throw Error('bad request');if(r.spec!==null)check(r.spec);return r;}catch{return null;}}
const deadline=<T,>(p:Promise<T>,ms=12000):Promise<T>=>{let timer:ReturnType<typeof setTimeout>;return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('结果尚未确认，请查询原操作；不会自动重发')),ms);})]).finally(()=>clearTimeout(timer));};
export function ExtendedTonePanel(props:Props){
  const [reconciled,setReconciled]=useState<{document_id:string;spec:Spec}|null>(null);
  const [draft,setDraft]=useState<Spec>(()=>check(props.spec));const [message,setMessage]=useState('');
  const [busy,setBusy]=useState(false);const [pending,setPending]=useState<Request|null>(savedRequest);
  const mounted=useRef(true);const lock=useRef(false);const pendingRef=useRef<Request|null>(pending);const currentDocument=useRef(props.documentId);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;const r=pendingRef.current;if(r)void props.cancel(r.request_id).catch(()=>{});};},[]);
  useEffect(()=>{currentDocument.current=props.documentId;setDraft(check(props.spec));},[props.documentId,props.spec]);
  const show=(text:string)=>{if(mounted.current)setMessage(text);};
  async function accept(raw:unknown,r:Request){
    const answer=receipt(raw,r);
    if(answer.outcome_unknown||answer.requires_reload)throw Error(answer.error??'调整状态未确认，需要重新载入并检查历史');
    if(sessionStorage.getItem(pendingKey)===JSON.stringify(r))sessionStorage.removeItem(pendingKey);
    pendingRef.current=null;if(mounted.current)setPending(null);
    if(!answer.success){show(answer.error??'调整未提交');return;}
    if(mounted.current&&currentDocument.current===r.document_id)setDraft(check(answer.spec));
    show(currentDocument.current===r.document_id?'影调调整已提交':'上一张照片的影调调整已提交');
    try{await deadline(props.refresh());}catch{show('调整已提交，状态刷新失败，请刷新照片状态');}
  }
  async function query(){const r=pendingRef.current;if(!r||lock.current)return;lock.current=true;setBusy(true);
    try{const raw=await deadline(props.query(r.request_id));if(!raw||typeof raw!=='object')throw Error('回执不可用');const packet=raw as {phase?:string;request_id?:string;result?:unknown};if(packet.request_id!==r.request_id||packet.phase!=='done')throw Error('操作结果仍未确认，未自动重发');await accept(packet.result,r);}catch(e){show(String(e));}finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  async function apply(reset=false){if(lock.current||pendingRef.current||props.disabled||!props.documentId)return;
    const r:Request={cmd:'extended_tone',request_id:crypto.randomUUID(),document_id:props.documentId,revision:props.revision,action:reset?'reset':'set',spec:reset?null:check(draft)};
    try{sessionStorage.setItem(pendingKey,JSON.stringify(r));}catch{show('无法保存操作身份，未发送调整');return;}
    lock.current=true;pendingRef.current=r;setPending(r);setBusy(true);show('正在提交影调…');
    try{await accept(await deadline(props.send(r)),r);}catch(e){show(String(e));}finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  const disabled=!!props.disabled||busy||!!pending;
  const edit=(key:Control,value:number)=>{if(Number.isFinite(value)&&value>=-100&&value<=100)setDraft(old=>({...old,[key]:value}));};
  return <section aria-label="扩展影调" className="extended-tone-panel">
    <p>亮度、白黑场与局部细节独立调整。当前范围 −100 至 100 为原创产品范围，并非官网披露数值。</p>
    <label><input type="checkbox" checked={draft.enabled} disabled={disabled} onChange={e=>setDraft({...draft,enabled:e.target.checked})}/>启用扩展影调</label>
    <label><input type="checkbox" checked={draft.monochrome} disabled={disabled} onChange={e=>setDraft({...draft,monochrome:e.target.checked})}/>黑白输出（原创模式，不是 XMP 配置文件）</label>
    {names.map(key=><div key={key} data-tool-anchor={'影调/'+labels[key]} data-requirement={'LNX-REF-PC-32455-C-'+requirements[key]}>
      <label htmlFor={'extended-'+key}>{labels[key]}</label>
      <input id={'extended-'+key} type="range" min={-100} max={100} step={1} value={draft[key]} disabled={disabled||(draft.monochrome&&key==='vibrance')} onChange={e=>edit(key,Number(e.target.value))}/>
      <input aria-label={labels[key]+'数值'} type="number" min={-100} max={100} step={1} value={draft[key]} disabled={disabled||(draft.monochrome&&key==='vibrance')} onChange={e=>edit(key,e.target.valueAsNumber)}/>
      <button type="button" disabled={disabled||(draft.monochrome&&key==='vibrance')} onClick={()=>edit(key,0)}>归零</button>
    </div>)}
    {draft.monochrome&&<p>黑白输出下鲜艳度不生效，原数值保留。</p>}
    <p>纹理处理细节频带，清晰度处理更大尺度的局部反差；祛雾可能在无雾画面产生不自然效果。</p>
    <button type="button" disabled={disabled||same(draft,props.spec)} onClick={()=>void apply()}>应用</button>
    <button type="button" disabled={disabled} onClick={()=>setDraft(check(props.spec))}>放弃未应用修改</button>
    <button type="button" disabled={disabled} onClick={()=>void apply(true)}>重置本组</button>
    {pending&&<><button type="button" disabled={busy} onClick={()=>void query()}>查询原操作结果</button>
      <button type="button" onClick={()=>{void props.cancel(pending.request_id).then(()=>show('已请求取消，仍需查询终态或回读核对')).catch(e=>show(String(e)));}}>取消原操作</button>
      <button type="button" disabled={busy} onClick={()=>{void props.readback().then(value=>{setReconciled(value);show('当前照片状态已回读，请核对下方参数；此步骤不会重发旧操作');}).catch(e=>show(String(e)));}}>读取当前状态以核对</button>
      {reconciled&&<div><p>当前照片：{reconciled.document_id}；{names.map(k=>labels[k]+' '+reconciled.spec[k]).join('，')}；黑白输出 {reconciled.spec.monochrome?'开':'关'}</p>
      <button type="button" disabled={reconciled.document_id!==props.documentId||!same(reconciled.spec,props.spec)} onClick={()=>{sessionStorage.removeItem(pendingKey);pendingRef.current=null;setPending(null);setDraft(check(reconciled.spec));setReconciled(null);show('已按你的确认保留回读状态并放弃旧回执；没有重发操作');}}>我已核对，保留当前状态并放弃旧回执</button></div>}
    </>}
    <p role="status" aria-live="polite">{message||props.reason||''}</p>
  </section>;
}
