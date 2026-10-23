import {useEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import type {Reply,Report} from './model';
const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,100));
export function useIdBackground(documentId:string,hostRevision:number,available:boolean,onChanged?:()=>void){
 const [report,setReport]=useState<Report|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false),[uncertain,setUncertain]=useState(false);
 const current=useRef(documentId);current.current=documentId;const reportRef=useRef(report);reportRef.current=report;const generation=useRef(0),flight=useRef(false),pending=useRef<{id:string;document:string;read:boolean}|null>(null),changed=useRef(onChanged);changed.current=onChanged;
 async function receipt(id:string):Promise<Reply|null>{const status=await invoke<{phase:string;result:Reply|null}>('id_background_status',{requestId:id});if(status.phase==='unknown')throw Error('原操作结果未知。不会自动重发；请重新读取状态核对。');return status.phase==='done'?status.result:null;}
 function accept(reply:Reply,doc:string,token:number,read:boolean){if(current.current!==doc||generation.current!==token)return;if(reply.document_id!==doc)throw Error('回执属于另一张照片');if(reply.outcome_unknown||reply.requires_reload){setUncertain(true);setMessage('背景回滚结果未确认，已暂停编辑。请保存可恢复记录并重新打开应用核对，不要重复应用。');return;}if(reply.report)setReport(reply.report);setMessage(reply.success?'已确认当前背景状态。':(reply.error||'证件照背景未应用'));setUncertain(false);pending.current=null;if(!read&&reply.success)changed.current?.();}
 async function request(action:string,fields:Record<string,unknown>={},read=false){
  if(flight.current||!available||(!read&&uncertain))return;if(read&&uncertain&&pending.current&&!pending.current.read){try{const reply=await receipt(pending.current.id);if(!reply){setMessage('原修改仍在处理中，请先查询原操作。');return;}accept(reply,pending.current.document,generation.current,false);if(reply.outcome_unknown||reply.requires_reload)return;}catch(error){setMessage(String(error));return;}}const doc=current.current,token=generation.current,id=crypto.randomUUID();const fence=reportRef.current;if(!read&&(!fence?.recipe_document_id||typeof fence.recipe_revision!=='string')){setMessage('缺少当前配方版本，请重新读取状态');return;}flight.current=true;setBusy(true);setMessage(read?'正在读取背景状态…':'正在处理背景…');
  try{if(!read){await settleCurveEdit();if(doc!==current.current||token!==generation.current)return;notifyInspectionEditIntent();}pending.current={id,document:doc,read};await invoke('id_background_request',{request:{cmd:'background',action,request_id:id,document_id:doc,...(!read?{recipe_document_id:fence!.recipe_document_id,recipe_revision:fence!.recipe_revision}:{}),...fields}});
   const until=Date.now()+30000;while(Date.now()<until){const reply=await receipt(id);if(reply){accept(reply,doc,token,read);return;}if(doc!==current.current||token!==generation.current)return;await pause();}throw Error('操作仍未确认，请查询原操作；不要重复应用。');
  }catch(error){if(doc===current.current&&token===generation.current){setMessage(String(error));setUncertain(true);}}
  finally{flight.current=false;if(doc===current.current&&token===generation.current)setBusy(false);}
 }
 async function query(){const p=pending.current;if(!p||p.document!==current.current)return;try{const r=await receipt(p.id);if(r)accept(r,p.document,generation.current,p.read);else setMessage('原操作仍在处理中。');}catch(e){setMessage(String(e));}}
 useEffect(()=>{generation.current++;pending.current=null;setReport(null);setUncertain(false);setBusy(false);setMessage(available?'':'当前引擎未提供证件照背景服务。');let live=true;void(async()=>{while(flight.current&&live)await pause();if(live&&available)await request('id_state',{},true);})();return()=>{live=false;generation.current++;};},[documentId,available]);
 useEffect(()=>{if(available&&!flight.current&&!uncertain)void request('id_state',{},true);},[hostRevision]);
 return {report,message,busy,uncertain,request,query,read:()=>request('id_state',{},true)};
}
