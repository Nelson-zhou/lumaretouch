import {useEffect,useMemo,useRef,useState} from 'react';
import {SelectiveColourPanel} from './SelectiveColourPanel';
import {SelectiveColourWorkflow} from './workflow';
import {abort,readback,send,show,type Readback} from './nativePort';
export function ConnectedSelectiveColourPanel({documentId,hostRevision,disabled,available}:{documentId:string;hostRevision:number;disabled:boolean;available:boolean}){
  const [value,setValue]=useState<Readback|null>(null);const [message,setMessage]=useState('');
  const context=useRef({document:documentId,revision:0});const currentDocument=useRef(documentId);currentDocument.current=documentId;
  const generation=useRef(0);
  const workflow=useMemo(()=>new SelectiveColourWorkflow({abort,send,show,context:()=>context.current,message:setMessage,
    committed:(recipe,revision)=>{context.current={document:documentId,revision};setValue(v=>v?.document_id===documentId?{...v,recipe,revision}:v);}}),[documentId]);
  async function refresh(reconcile=false){const token=++generation.current;const doc=currentDocument.current;const next=await readback();if(token!==generation.current||doc!==currentDocument.current||next.document_id!==doc)return;context.current={document:doc,revision:next.revision};setValue(next);if(reconcile){if(next.requires_reload)throw Error("引擎回滚未确认，请重新打开照片后再核对");workflow.reconcileAfterReadback();}}
  useEffect(()=>{workflow.invalidate();if(!available){setValue(null);setMessage('当前引擎未提供可选颜色 ABI1，请使用完整安装包');return;}
    refresh().catch(e=>setMessage(String(e)));return()=>{++generation.current;};
  },[documentId,hostRevision,available,workflow]);
  useEffect(()=>()=>{void workflow.cancel();workflow.dispose();},[workflow]);
  return <>{value?.document_id===documentId?<SelectiveColourPanel value={value.recipe} workflow={workflow} enabled={!disabled&&available&&value.available} message={message}/>:<p role="status">{message||'正在读取可选颜色状态'}</p>}
    <button type="button" onClick={()=>void refresh(true).catch(e=>setMessage(String(e)))}>核对当前状态并解除未确认锁定</button></>;
}
