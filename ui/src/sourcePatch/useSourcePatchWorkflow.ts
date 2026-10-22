import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createSourcePatchWorkflow,type SourcePatchCaptureStatus,type SourcePatchContext,type SourcePatchTransport} from './workflow';

const api:SourcePatchTransport={
  arm:async(captureId,documentId)=>{
    await settleCurveEdit();
    return invoke<{ticket:string}>('source_patch_capture',{action:'arm',captureId,ticket:null,documentId});
  },
  status:(captureId,ticket)=>invoke<SourcePatchCaptureStatus>('source_patch_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke<ArrayBuffer>('source_patch_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke<{eligible:boolean}>('source_patch_capture',{action:'presented',captureId,ticket,documentId}),
  cancel:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'cancel',captureId,ticket,documentId}),
  submit:async request=>{
    await settleCurveEdit();
    notifyInspectionEditIntent();
    return invoke('source_patch',{requestId:request.request_id,captureId:request.capture_id,ticket:request.ticket,
      polygon:request.polygon,offset:request.offset});
  },
  result:requestId=>invoke('source_patch_result',{requestId}),
};

/** Mount once in App, not in the conditionally mounted repair panel. */
export function useSourcePatchWorkflow(context:SourcePatchContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createSourcePatchWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{
    workflow.activate();setState(workflow.snapshot());
    const unsubscribe=workflow.subscribe(setState);
    return()=>{unsubscribe();workflow.stop();};
  },[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{
    const edit=()=>{
      // Our own one-shot submit dispatches this after the request is already owned.
      if(workflow.capturing()&&!workflow.busy())workflow.cancel('照片正在调整，未提交的修补选区已取消');
    };
    const key=(event:KeyboardEvent)=>{
      if(event.key==='Escape'&&workflow.capturing()){
        event.preventDefault();workflow.cancel();
      }
    };
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);
    window.addEventListener('keydown',key);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);};
  },[workflow]);
  return {workflow,state,context,active:['arming','painting','target','source'].includes(state.phase),pending:workflow.busy()};
}
export type SourcePatchOwner=ReturnType<typeof useSourcePatchWorkflow>;
