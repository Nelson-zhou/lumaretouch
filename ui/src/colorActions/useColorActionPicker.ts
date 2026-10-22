import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createColorActionWorkflow} from './workflow';
import type {ColorActionContext,ColorActionTransport} from './model';

const api:ColorActionTransport={
  arm:async(captureId,documentId,pickerAction,pickerChannel)=>{
    await settleCurveEdit();
    return invoke('color_picker_capture',{action:'arm',captureId,ticket:null,documentId,pickerAction,pickerChannel});
  },
  status:(captureId,ticket)=>invoke('color_picker_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke<ArrayBuffer>('color_picker_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke('color_picker_capture',{action:'presented',captureId,ticket,documentId,pickerAction:null,pickerChannel:null}),
  cancel:(captureId,ticket,documentId)=>invoke('color_picker_capture',{action:'cancel',captureId,ticket,documentId,pickerAction:null,pickerChannel:null}),
  submit:async(request,preview)=>{
    if(!preview){await settleCurveEdit();notifyInspectionEditIntent();}
    return invoke('color_picker',{requestId:request.request_id,captureId:request.capture_id,ticket:request.ticket,
      action:request.action,channel:request.channel,region:request.region,delta:request.delta,preview});
  },
  result:(requestId,preview)=>invoke('color_picker_result',{requestId,preview}),
};
/** App-scoped, not a child of any collapsible color panel. */
export function useColorActionPicker(context:ColorActionContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createColorActionWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const unsubscribe=workflow.subscribe(setState);
    return()=>{unsubscribe();workflow.stop();};},[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{
    const edit=()=>{if(workflow.capturing()&&!workflow.busy())workflow.cancel('其他调整已开始，未提交的定向手势已取消');};
    const blur=()=>{if(workflow.capturing()&&!workflow.busy())workflow.cancel('窗口已失去焦点，未提交的定向手势已取消');};
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&workflow.capturing()&&!workflow.busy()){event.preventDefault();workflow.cancel();}};
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key);window.addEventListener('blur',blur);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);window.removeEventListener('blur',blur);};
  },[workflow]);
  return {workflow,state,context,active:['arming','painting','ready','probing'].includes(state.phase),pending:workflow.busy()};
}
export type ColorActionOwner=ReturnType<typeof useColorActionPicker>;
