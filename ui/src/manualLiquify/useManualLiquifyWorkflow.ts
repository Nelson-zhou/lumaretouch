import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createLiquifyWorkflow,type LiquifyContext,type LiquifyTransport} from './workflow';
let ownIntent=false;
const api:LiquifyTransport={
  preview:async(action,previewId,sessionId,documentId,mutation)=>{
    if(action==='preview'&&mutation?.action==='view')await settleCurveEdit();
    return invoke('manual_liquify_preview',{action,previewId,sessionId,documentId,mutation:mutation??null});},
  status:previewId=>invoke('manual_liquify_preview_status',{previewId}),
  submit:async r=>{await settleCurveEdit();ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    return invoke('manual_liquify',{requestId:r.request_id,previewId:r.preview_id,sessionId:r.session_id,documentId:r.document_id});},
  result:requestId=>invoke('manual_liquify_result',{requestId}),
};
export function useManualLiquifyWorkflow(context:LiquifyContext,refresh:()=>Promise<void>,prepare?:()=>void){
  const latest=useRef(refresh),prepareLatest=useRef(prepare);latest.current=refresh;prepareLatest.current=prepare;
  const workflow=useMemo(()=>{const owner=createLiquifyWorkflow(api,{refresh:()=>latest.current()});
    return {...owner,start:async()=>{prepareLatest.current?.();await owner.start();}};},[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const off=workflow.subscribe(setState);return()=>{off();workflow.stop();};},[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{if(workflow.canContinue())void workflow.resume();},[workflow,state.phase,context.enabled,context.canStart,context.contextKey]);
  useEffect(()=>{
    const edit=()=>{if(!ownIntent)workflow.externalEdit();};
    const key=(e:KeyboardEvent)=>{
      if(e.key==='Escape'&&workflow.capturing()){e.preventDefault();workflow.cancel();return;}
      const target=e.target as HTMLElement|null;
      if(context.enabled&&context.canStart!==false&&e.key.toLowerCase()==='n'&&!e.repeat&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&
        !target?.isContentEditable&&!['INPUT','TEXTAREA','SELECT'].includes(target?.tagName??'')&&!workflow.capturing()&&!workflow.busy()){
        e.preventDefault();void workflow.start();
      }
    };
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);};
  },[workflow,context.enabled,context.canStart]);
  return {workflow,state,context,active:state.open,pending:workflow.busy()};
}
export type ManualLiquifyOwner=ReturnType<typeof useManualLiquifyWorkflow>;
