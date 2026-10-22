import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createSkyWorkflow,type SkyContext,type SkyTransport} from './workflow';
let ownIntent=false;
const api:SkyTransport={
  preview:async(action,previewId,sessionId,documentId,mutation)=>{
    if(action==='preview'&&mutation?.action==='view')await settleCurveEdit();
    return invoke('sky_replacement_preview',{action,previewId,sessionId,documentId,mutation:mutation??null});},
  status:previewId=>invoke('sky_replacement_preview_status',{previewId}),
  submit:async r=>{await settleCurveEdit();ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    return invoke('sky_replacement',{requestId:r.request_id,previewId:r.preview_id,sessionId:r.session_id,documentId:r.document_id});},
  result:requestId=>invoke('sky_replacement_result',{requestId}),
};
export function useSkyReplacementWorkflow(context:SkyContext,refresh:()=>Promise<void>,prepare?:()=>void){
  const latest=useRef(refresh),prepareLatest=useRef(prepare);latest.current=refresh;prepareLatest.current=prepare;
  const workflow=useMemo(()=>{const owner=createSkyWorkflow(api,{refresh:()=>latest.current()});return {...owner,start:async()=>{prepareLatest.current?.();await owner.start();}};},[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const off=workflow.subscribe(setState);return()=>{off();workflow.stop();};},[workflow]);
  useLayoutEffect(()=>workflow.context(context),[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{
    const edit=()=>{if(!ownIntent)workflow.externalEdit();};
    const key=(e:KeyboardEvent)=>{if(e.key==='Escape'&&workflow.capturing()){e.preventDefault();workflow.cancel();}};
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);};
  },[workflow]);
  return {workflow,state,context,active:state.open,pending:workflow.busy()};
}
export type SkyReplacementOwner=ReturnType<typeof useSkyReplacementWorkflow>;
