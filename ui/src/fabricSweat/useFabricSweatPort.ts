// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useRef,useState} from 'react';
import {fabricSweatRequest,fabricSweatStatus} from '../native';
import {canonical,validImage,previewMatches,type FabricSweatPort,type Snapshot,type Reference,type Preview,type PreviewPayload,type ConfirmPayload,type Image} from './model';
export type FabricSweatContext={bindingKey:string|null;documentId:string|null;revision:string;enabled:boolean;blocked:boolean};
export type FabricSweatRequest={cmd:'fabric_sweat';protocol:1;request_id:string;action:'reference'|'preview'|'confirm'|'clear';document_id:string;revision:string;payload:Record<string,unknown>};
type Pending={request:FabricSweatRequest;binding:string;reference:Reference|null;preview:Snapshot['preview']};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const id=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
const revision=(v:unknown):v is string=>typeof v==='string'&&/^(0|[1-9]\d{0,15})$/.test(v)&&BigInt(v)<=BigInt(Number.MAX_SAFE_INTEGER);
const unit=(v:unknown):v is number=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=1;
const delay=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
async function bounded<T>(promise:Promise<T>):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  try{return await Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待原请求回执超时')),15000);})]);}
  finally{if(timer)clearTimeout(timer);}
}
async function verifyImage(raw:unknown):Promise<Image>{
  if(!object(raw)||!validImage(raw as Image))throw Error('汗渍对比图格式无效');
  const image=raw as Image,binary=atob(image.base64),bytes=Uint8Array.from(binary,c=>c.charCodeAt(0));
  if(bytes.length<33||bytes.length>4*1024*1024)throw Error('汗渍图像超过传输范围');
  const view=new DataView(bytes.buffer);
  if(view.getUint32(0)!==0x89504e47||view.getUint32(4)!==0x0d0a1a0a||view.getUint32(8)!==13||view.getUint32(12)!==0x49484452
    ||view.getUint32(16)!==image.width||view.getUint32(20)!==image.height)throw Error('汗渍图像尺寸与声明不符');
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==image.sha256)throw Error('汗渍图像摘要不符');return image;
}
async function checkedReference(raw:unknown):Promise<Reference>{
  if(!object(raw)||raw.protocol!==1||raw.family!=='fabric_sweat'||!id(raw.reference_id)||!hash(raw.fence)||!object(raw.source)
    ||!hash(raw.source.sha256)||![raw.source.width,raw.source.height].every(v=>typeof v==='number'&&Number.isSafeInteger(v)&&v>0&&v<=65536)
    ||!unit(raw.current_amount)||!object(raw.capability)||typeof raw.capability.available!=='boolean'
    ||!(raw.capability.reason===null||typeof raw.capability.reason==='string'))throw Error('汗渍来源回执无效');
  await verifyImage(raw.source_image);return raw as Reference;
}
/** App-lifetime adapter. It owns request reconciliation only, never image/history state. */
export function useFabricSweatPort(context:FabricSweatContext,refresh:()=>Promise<unknown>|void):FabricSweatPort{
  const [snapshot,setSnapshot]=useState<Snapshot>({bindingKey:context.bindingKey,reference:null,preview:null,pending:false,uncertain:false,refreshRequired:false});
  const state=useRef(snapshot),live=useRef({context,refresh}),pending=useRef<Pending|null>(null),polling=useRef(false),accepting=useRef(false),mounted=useRef(true);
  const refreshFence=useRef<{document:string;revision:string}|null>(null);
  live.current={context,refresh};
  const publish=(patch:Partial<Snapshot>)=>{state.current={...state.current,...patch};if(mounted.current)setSnapshot(state.current);};
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useEffect(()=>{
    if(state.current.bindingKey!==context.bindingKey)publish({bindingKey:context.bindingKey,reference:null,preview:null});
    const fence=refreshFence.current;
    if(fence&&context.documentId===fence.document&&revision(context.revision)&&BigInt(context.revision)>=BigInt(fence.revision)){
      refreshFence.current=null;publish({refreshRequired:false});
    }else if(fence&&context.documentId!==fence.document){refreshFence.current=null;publish({refreshRequired:false});}
  },[context.bindingKey,context.documentId,context.revision]);
  const acceptResult=async(raw:unknown,entry:Pending):Promise<boolean>=>{
    if(pending.current!==entry)return true;
    if(!object(raw)||raw.event!=='fabric_sweat_result'||raw.protocol!==1||raw.request_id!==entry.request.request_id||raw.action!==entry.request.action
      ||raw.document_id!==entry.request.document_id||raw.revision!==entry.request.revision||canonical(raw.fabric_sweat_request)!==canonical(entry.request)
      ||typeof raw.success!=='boolean'||typeof raw.outcome_unknown!=='boolean')throw Error('汗渍回执不匹配原请求');
    if(raw.outcome_unknown){publish({uncertain:true,message:'原汗渍请求结果仍未知，正在查询同一请求。'});return false;}
    if(!raw.success){pending.current=null;publish({pending:false,uncertain:false,message:typeof raw.error==='string'?raw.error:'汗渍操作被拒绝，未作为成功发布。'});return true;}
    const same=()=>live.current.context.bindingKey===entry.binding;
    if(entry.request.action==='reference'){
      const reference=await checkedReference(raw.payload);
      if(same())publish({reference,preview:null,message:''});
    }else if(entry.request.action==='preview'){
      if(!entry.reference||!object(raw.payload))throw Error('缺少原始来源审核');
      const preview=raw.payload as Preview;
      for(const key of ['before','after','mask'] as const)await verifyImage(preview[key]);
      const row={request:entry.request.payload as PreviewPayload,value:preview};
      if(!id(preview.preview_id)||!previewMatches(row,row.request,entry.reference))throw Error('汗渍预览与原始来源不一致');
      if(same())publish({preview:row,message:''});
    }else{
      const payload=raw.payload,doc=raw.doc_state;
      if(!object(payload)||payload.protocol!==1||payload.family!=='fabric_sweat'||!unit(payload.amount)||!hash(payload.candidate_sha256)
        ||!object(doc)||doc.document_id!==entry.request.document_id||!object(doc.fabric_sweat)||doc.fabric_sweat.protocol!==1
        ||!revision(doc.fabric_sweat.revision)||!unit(doc.fabric_sweat.amount)||doc.fabric_sweat.amount!==payload.amount
        ||doc.fabric_sweat.recipe_sha256!==payload.candidate_sha256||BigInt(doc.fabric_sweat.revision)<BigInt(entry.request.revision))throw Error('汗渍修改缺少匹配的规范文档状态');
      if(entry.request.action==='confirm'&&(!entry.preview||payload.candidate_sha256!==entry.preview.value.candidate_sha256||payload.amount!==entry.preview.request.amount))throw Error('汗渍应用结果与已检查候选不符');
      if(entry.request.action==='clear'&&payload.amount!==0)throw Error('汗渍清除未返回零值');
      refreshFence.current={document:entry.request.document_id,revision:doc.fabric_sweat.revision};
      publish({reference:null,preview:null,refreshRequired:true,message:'汗渍操作已确认，正在刷新照片。'});
      pending.current=null;publish({pending:false,uncertain:false});
      try{await live.current.refresh();}catch{publish({message:'汗渍操作已确认，但照片刷新失败；请刷新当前文档。'});}
      const current=live.current.context,fence=refreshFence.current;
      if(fence&&(current.documentId!==fence.document||revision(current.revision)&&BigInt(current.revision)>=BigInt(fence.revision))){refreshFence.current=null;publish({refreshRequired:false});}
      return true;
    }
    pending.current=null;publish({pending:false,uncertain:false});return true;
  };
  const accept=async(raw:unknown,entry:Pending):Promise<boolean>=>{
    if(accepting.current)return false;accepting.current=true;
    try{return await acceptResult(raw,entry);}finally{accepting.current=false;}
  };
  const check=async()=>{
    const entry=pending.current;if(!entry||polling.current)return;polling.current=true;
    try{
      const raw=await bounded(fabricSweatStatus(entry.request.request_id));
      if(pending.current!==entry)return;
      if(!object(raw)||raw.request_id!==entry.request.request_id||!['pending','done','unavailable'].includes(String(raw.phase)))throw Error('汗渍查询回执无效');
      if(raw.phase==='done')await accept(raw.result,entry);
      else if(raw.phase==='unavailable')publish({uncertain:true,message:'原请求记录暂不可用；结果仍未知，不会重新提交。'});
    }catch(error){if(pending.current===entry)publish({uncertain:true,message:String(error)});}
    finally{polling.current=false;}
  };
  const checkRef=useRef(check);checkRef.current=check;
  useEffect(()=>{let active=true;const poll=async()=>{while(active){await delay(1500);if(active)await checkRef.current();}};void poll();return()=>{active=false;};},[]);
  const submit=async(action:FabricSweatRequest['action'],payload:Record<string,unknown>)=>{
    const current=live.current.context,s=state.current;
    if(!current.enabled||current.blocked||!current.bindingKey||!current.documentId||!revision(current.revision)||pending.current||s.uncertain||s.refreshRequired)throw Error('当前照片未就绪或已有汗渍请求待核对');
    if(action==='preview'&&(!s.reference||payload.reference_id!==s.reference.reference_id))throw Error('请先读取当前来源');
    if(action==='confirm'&&(!s.preview||payload.reviewed!==true||payload.preview_id!==s.preview.value.preview_id||payload.candidate_sha256!==s.preview.value.candidate_sha256||payload.before_sha256!==s.preview.value.before.sha256||payload.after_sha256!==s.preview.value.after.sha256||payload.mask_sha256!==s.preview.value.mask.sha256))throw Error('请更新并检查当前候选');
    const request:FabricSweatRequest={cmd:'fabric_sweat',protocol:1,request_id:crypto.randomUUID().replaceAll('-',''),action,document_id:current.documentId,revision:current.revision,payload:structuredClone(payload)};
    if(new TextEncoder().encode(JSON.stringify(request)).byteLength>256*1024)throw Error('汗渍草稿超过有界请求大小，尚未发送');
    const entry:Pending={request,binding:current.bindingKey,reference:s.reference,preview:s.preview};pending.current=entry;
    publish({pending:true,uncertain:false,preview:action==='preview'?null:s.preview,message:'正在处理汗渍请求。'});
    // Set pending before invoke; a rejected Promise does not prove no mutation happened.
    try{
      const ack=await bounded(fabricSweatRequest(request));
      if(!object(ack)||ack.requested!==true||ack.request_id!==request.request_id)throw Error('汗渍入队回执不匹配，正在核对原请求');
    }
    catch(error){if(pending.current===entry)publish({uncertain:true,message:String(error)});}
    if(pending.current===entry)await check();
  };
  return {snapshot:snapshot.bindingKey===context.bindingKey?snapshot:{...snapshot,bindingKey:context.bindingKey,reference:null,preview:null},reference:()=>submit('reference',{}),preview:(payload:PreviewPayload)=>submit('preview',payload),
    confirm:(payload:ConfirmPayload)=>submit('confirm',payload),clear:()=>submit('clear',{})};
}
