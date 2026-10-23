import {useEffect,useMemo,useRef,useState} from 'react';
import {checked,type Recipe} from './model';
import {VerifiedPicker} from './VerifiedPicker';
import {ColourEditorPanel} from './ColourEditorPanel';
import {ColourEditorWorkflow} from './workflow';
import {abort,readback,send,show,type Readback} from './nativePort';
export function ConnectedColourEditorPanel({documentId,hostRevision,disabled,available,onPick}:{documentId:string;hostRevision:number;disabled:boolean;available:boolean;onPick?:()=>Promise<Recipe>}){
  const [picker,setPicker]=useState(false);const [value,setValue]=useState<Readback|null>(null);const [message,setMessage]=useState('');
  const context=useRef({document:documentId,revision:0});const currentDocument=useRef(documentId);currentDocument.current=documentId;
  const generation=useRef(0);
  const workflow=useMemo(()=>new ColourEditorWorkflow({abort,send,show,context:()=>context.current,message:setMessage,
    committed:(recipe,revision)=>{context.current={document:documentId,revision};setValue(v=>v?.document_id===documentId?{...v,recipe,revision}:v);}}),[documentId]);
  async function refresh(reconcile=false){const token=++generation.current;const doc=currentDocument.current;const next=await readback();if(token!==generation.current||doc!==currentDocument.current||next.document_id!==doc)return;context.current={document:doc,revision:next.revision};setValue(next);if(reconcile){if(next.requires_reload)throw Error("引擎回滚未确认，请重新打开照片后再核对");workflow.reconcileAfterReadback();}}
  async function pick(){
    if(!onPick||workflow.locked||!value)return;
    const contextBefore={...context.current};const token=generation.current;
    try{const recipe=checked(await onPick());
      if(token!==generation.current||context.current.document!==contextBefore.document||context.current.revision!==contextBefore.revision)return;
      setValue(v=>v?{...v,recipe}:v);workflow.preview(recipe);
    }catch(error){setMessage(String(error));}
  }
  useEffect(()=>{setPicker(false);workflow.invalidate();if(!available){setValue(null);setMessage('当前引擎未提供色彩编辑器 ABI1，请使用完整安装包');return;}
    refresh().catch(e=>setMessage(String(e)));return()=>{++generation.current;};
  },[documentId,hostRevision,available,workflow]);
  useEffect(()=>()=>{void workflow.cancel();workflow.dispose();},[workflow]);
  return <>{value?.document_id===documentId?<ColourEditorPanel value={value.recipe} workflow={workflow} enabled={!disabled&&available&&value.available} message={message} onDraft={recipe=>setValue(v=>v?{...v,recipe}:v)} onPick={()=>{if(onPick)void pick();else setPicker(true);}}/>:<p role="status">{message||'正在读取色彩编辑器状态'}</p>}
    {picker&&value&&<VerifiedPicker documentId={documentId} recipe={value.recipe} onClose={()=>setPicker(false)} onSample={recipe=>{setPicker(false);setValue(v=>v?{...v,recipe}:v);workflow.preview(recipe);}}/>}
    <button type="button" onClick={()=>void refresh(true).catch(e=>setMessage(String(e)))}>核对当前状态并解除未确认锁定</button></>;
}
