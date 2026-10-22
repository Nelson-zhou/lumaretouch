import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createLocalMaskWorkflow,type LocalMaskContext,type LocalMaskTransport} from './workflow';
let ownIntent=false;
const api:LocalMaskTransport={
  arm:async(captureId,documentId)=>{await settleCurveEdit();return invoke('source_patch_capture',{action:'arm',captureId,ticket:null,documentId,purpose:'local-masks'});},
  status:(captureId,ticket)=>invoke('source_patch_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke('source_patch_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'presented',captureId,ticket,documentId}),
  cancel:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'cancel',captureId,ticket,documentId}),
  submit:async request=>{await settleCurveEdit();ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    return invoke('local_masks',{action:'apply',requestId:request.request_id,captureId:request.capture_id,ticket:request.ticket,mutation:request.mutation});},
  result:requestId=>invoke('local_masks_result',{requestId}),
};
export function useLocalMaskWorkflow(context:LocalMaskContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createLocalMaskWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const unsubscribe=workflow.subscribe(setState);return()=>{unsubscribe();workflow.stop();};},[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{const edit=()=>{if(!ownIntent)workflow.externalEdit();};const key=(e:KeyboardEvent)=>{if(e.key==='Escape'&&workflow.capturing()){e.preventDefault();workflow.cancel();}};
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);};},[workflow]);
  return {workflow,state,context,active:['arming','painting','target'].includes(state.phase),pending:workflow.busy()};
}
export type LocalMaskOwner=ReturnType<typeof useLocalMaskWorkflow>;
