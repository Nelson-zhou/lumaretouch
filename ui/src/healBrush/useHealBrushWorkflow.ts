import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createHealBrushWorkflow,type HealBrushCaptureStatus,type HealBrushContext,type HealBrushTransport} from './workflow';

let ownIntent=false;
const api:HealBrushTransport={
  arm:async(captureId,documentId)=>{
    await settleCurveEdit();
    return invoke<{ticket:string}>('source_patch_capture',{action:'arm',captureId,ticket:null,documentId,purpose:'repair'});
  },
  status:(captureId,ticket)=>invoke<HealBrushCaptureStatus>('source_patch_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke<ArrayBuffer>('source_patch_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke<{eligible:boolean}>('source_patch_capture',{action:'presented',captureId,ticket,documentId}),
  cancel:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'cancel',captureId,ticket,documentId}),
  submit:async request=>{
    await settleCurveEdit();
    ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    return invoke('source_patch',{requestId:request.request_id,captureId:request.capture_id,ticket:request.ticket,
      kind:'heal_vector',stroke:request.stroke});
  },
  result:requestId=>invoke('source_patch_result',{requestId}),
};

/** Mount once in App, not in the conditionally mounted repair panel. */
export function useHealBrushWorkflow(context:HealBrushContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createHealBrushWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{
    workflow.activate();setState(workflow.snapshot());
    const unsubscribe=workflow.subscribe(setState);
    return()=>{unsubscribe();workflow.stop();};
  },[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.samplingKey,context.reason]);
  useEffect(()=>{if(workflow.canContinue())void workflow.start();},[workflow,state.phase,context.enabled,context.canStart,context.contextKey]);
  useEffect(()=>{
    const edit=()=>{
      // Our own one-shot submit dispatches this after the request is already owned.
      if(!ownIntent)workflow.externalEdit();
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
  return {workflow,state,context,active:['arming','painting','target'].includes(state.phase),pending:workflow.busy()};
}
export type HealBrushOwner=ReturnType<typeof useHealBrushWorkflow>;
