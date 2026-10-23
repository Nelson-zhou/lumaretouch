import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {spillApplyFields,spillNotSent,validSpillReview,type SpillFence,type SpillReview} from '../spillRemoval/model';
import type {Reply,Report} from './model';
const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,100));
type Kind='read'|'preview'|'mutation';
type Pending={id:string;document:string;kind:Kind;action:string;fence:SpillFence|null;reviewEpoch:number};
export function useIdBackground(documentId:string,hostRevision:number,available:boolean,onChanged?:()=>void){
 const [report,setReport]=useState<Report|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false),[spillReview,setSpillReview]=useState<SpillReview|null>(null);
 const current=useRef(documentId);current.current=documentId;const reportRef=useRef(report);reportRef.current=report;
 const generation=useRef(0),flight=useRef(false),pending=useRef<Pending|null>(null),changed=useRef(onChanged);changed.current=onChanged;
 const reviewRef=useRef<SpillReview|null>(null),reviewEpoch=useRef(0),usedTokens=useRef(new Set<string>());
 function clearSpillReview(){reviewEpoch.current++;reviewRef.current=null;setSpillReview(null);}
 async function receipt(id:string):Promise<Reply|null>{
  const status=await invoke<{phase:string;result:Reply|null}>('id_background_status',{requestId:id});
  if(status.phase==='unknown')throw Error('原操作结果未知。不会自动重发；请重新读取状态核对。');
  return status.phase==='done'?status.result:null;
 }
 function accept(reply:Reply,p:Pending,token:number){
  if(current.current!==p.document||generation.current!==token)return;
  if(reply.event!=='id_background_result'||reply.request_id!==p.id||reply.document_id!==p.document||typeof reply.success!=='boolean')throw Error('回执身份或结果无效');
  const spill=p.action==='id_spill_preview'||p.action==='id_spill_apply';
  if(spill&&(reply.protocol!==1||reply.action!==p.action))throw Error('祛染回执协议或操作不匹配');
  if(reply.outcome_unknown||reply.requires_reload){clearSpillReview();setUncertain(true);setMessage('背景回滚结果未确认，已暂停编辑。请保存可恢复记录并重新打开应用核对，不要重复应用。');return;}
  if(p.kind==='preview'&&reply.success){
   if(!p.fence||!validSpillReview(reply.review,p.fence)||!reply.report
    ||reply.report.recipe_document_id!==p.fence.recipe_document_id||reply.report.recipe_revision!==p.fence.recipe_revision)throw Error('祛染预览缺少与当前配方相符的冻结图像');
   if(p.reviewEpoch===reviewEpoch.current&&reportRef.current?.recipe_document_id===p.fence.recipe_document_id&&reportRef.current?.recipe_revision===p.fence.recipe_revision){
    reviewRef.current=reply.review;setSpillReview(reply.review);
   }else{setUncertain(false);pending.current=null;setMessage('预览期间照片或编辑状态已变化，请重新生成祛染审核。');return;}
  }
  if(reply.report){
   if(reviewRef.current&&(reviewRef.current.recipe_document_id!==reply.report.recipe_document_id||reviewRef.current.recipe_revision!==reply.report.recipe_revision))clearSpillReview();
   reportRef.current=reply.report;setReport(reply.report);
  }
  setMessage(reply.success?(p.kind==='preview'?'祛染候选已生成，请审核真实前后图像。':p.action==='id_spill_apply'?'祛染修改已确认。':'已确认当前背景状态。'):(reply.error||'证件照背景未应用'));
  setUncertain(false);pending.current=null;if(p.kind==='mutation'&&reply.success)changed.current?.();
 }
 async function request(action:string,fields:Record<string,unknown>={},read=false){
  const kind:Kind=action==='id_spill_preview'?'preview':read?'read':'mutation';
  if(flight.current||!available||(kind!=='read'&&uncertain))return;
  if(kind==='read'&&uncertain&&pending.current?.kind==='mutation'){
   try{const p=pending.current,reply=await receipt(p.id);if(!reply){setMessage('原修改仍在处理中，请先查询原操作。');return;}accept(reply,p,generation.current);if(reply.outcome_unknown||reply.requires_reload)return;}
   catch(error){setMessage(String(error));return;}
  }
  const doc=current.current,token=generation.current,id=crypto.randomUUID();
  const frozenReview=reviewRef.current,reviewAtStart=reviewEpoch.current;
  if(action==='id_spill_apply'&&(!frozenReview||usedTokens.current.has(frozenReview.token)
   ||Object.entries(spillApplyFields(frozenReview)).some(([key,value])=>fields[key]!==value))){setMessage('请先重新生成并审核当前祛染候选。');return;}
  flight.current=true;setBusy(true);setMessage(kind==='read'?'正在读取背景状态…':kind==='preview'?'正在生成真实祛染前后审核…':'正在处理背景…');
  try{
   if(kind!=='read'){
    await settleCurveEdit();if(doc!==current.current||token!==generation.current)return;
   }
   const saved=reportRef.current,fence=saved?{recipe_document_id:saved.recipe_document_id,recipe_revision:saved.recipe_revision}:null;
   if(kind!=='read'&&(!fence?.recipe_document_id||typeof fence.recipe_revision!=='string')){setMessage('缺少当前配方版本，请重新读取状态');return;}
   if(action==='id_spill_apply'&&(!frozenReview||reviewAtStart!==reviewEpoch.current||reviewRef.current!==frozenReview
    ||frozenReview.recipe_document_id!==fence?.recipe_document_id||frozenReview.recipe_revision!==fence?.recipe_revision)){
    clearSpillReview();setMessage('准备应用时照片配方已变化，请重新生成祛染审核。');return;
   }
   if(kind==='mutation'){
    if(action==='id_spill_apply')usedTokens.current.add(frozenReview!.token);
    clearSpillReview();notifyInspectionEditIntent();
   }else if(kind==='preview')clearSpillReview();
   const p:Pending={id,document:doc,kind,action,fence,reviewEpoch:reviewEpoch.current};pending.current=p;
   const admission=await invoke<unknown>('id_background_request',{request:{...fields,cmd:'background',action,request_id:id,document_id:doc,...(kind!=='read'?fence:{})}});
   if((action==='id_spill_preview'||action==='id_spill_apply')&&spillNotSent(admission,{action,request_id:id,document_id:doc})){
    if(doc===current.current&&token===generation.current){pending.current=null;setUncertain(false);clearSpillReview();setMessage(`未发送，照片未修改：${admission.error}`);}return;
   }
   const until=Date.now()+30000;
   while(Date.now()<until){const reply=await receipt(id);if(reply){accept(reply,p,token);return;}if(doc!==current.current||token!==generation.current)return;await pause();}
   throw Error('操作仍未确认，请查询原操作；不要重复应用。');
  }catch(error){if(doc===current.current&&token===generation.current){if(kind!=='preview'||pending.current?.id!==id)clearSpillReview();setMessage(String(error));setUncertain(true);}}
  finally{flight.current=false;if(doc===current.current&&token===generation.current)setBusy(false);}
 }
 async function query(){const p=pending.current;if(!p||p.document!==current.current||flight.current)return;try{const r=await receipt(p.id);if(r)accept(r,p,generation.current);else setMessage('原操作仍在处理中。');}catch(e){setMessage(String(e));}}
 useEffect(()=>{
  generation.current++;pending.current=null;reportRef.current=null;setReport(null);clearSpillReview();usedTokens.current.clear();setUncertain(false);setBusy(false);setMessage(available?'':'当前引擎未提供证件照背景服务。');
  let live=true;void(async()=>{while(flight.current&&live)await pause();if(live&&available)await request('id_state',{},true);})();return()=>{live=false;generation.current++;};
 },[documentId,available]);
 useEffect(()=>{clearSpillReview();if(available&&!flight.current&&!uncertain)void request('id_state',{},true);},[hostRevision]);
 useEffect(()=>{const edit=()=>clearSpillReview();window.addEventListener(INSPECTION_EDIT_INTENT,edit);return()=>window.removeEventListener(INSPECTION_EDIT_INTENT,edit);},[]);
 return {report,message,busy,uncertain,request,query,spillReview,clearSpillReview,read:()=>request('id_state',{},true)};
}
