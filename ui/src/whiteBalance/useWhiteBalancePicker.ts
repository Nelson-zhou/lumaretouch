import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createWhiteBalancePickerWorkflow,type WhiteBalancePickerCaptureStatus,type WhiteBalancePickerContext,type WhiteBalancePickerTransport} from './pickerWorkflow';

const api:WhiteBalancePickerTransport={
  arm:async(captureId,documentId)=>{
    await settleCurveEdit();
    return invoke<{ticket:string}>('white_balance_capture',{action:'arm',captureId,ticket:null,documentId});
  },
  status:(captureId,ticket)=>invoke<WhiteBalancePickerCaptureStatus>('white_balance_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke<ArrayBuffer>('white_balance_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke<{eligible:boolean}>('white_balance_capture',{action:'presented',captureId,ticket,documentId}),
  cancel:(captureId,ticket,documentId)=>invoke('white_balance_capture',{action:'cancel',captureId,ticket,documentId}),
  submit:async request=>{
    await settleCurveEdit();
    notifyInspectionEditIntent();
    return invoke('white_balance_pick',{requestId:request.request_id,captureId:request.capture_id,ticket:request.ticket,region:request.region});
  },
  result:requestId=>invoke('white_balance_result',{requestId}),
};

/** Mount once in App, not in the conditionally mounted WB panel. */
export function useWhiteBalancePickerWorkflow(context:WhiteBalancePickerContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createWhiteBalancePickerWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
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
      if(workflow.capturing()&&!workflow.busy())workflow.cancel('照片正在调整，未提交的白平衡取样已取消');
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
  return {workflow,state,context,active:['arming','painting','ready'].includes(state.phase),pending:workflow.busy()};
}
export type WhiteBalancePickerOwner=ReturnType<typeof useWhiteBalancePickerWorkflow>;
