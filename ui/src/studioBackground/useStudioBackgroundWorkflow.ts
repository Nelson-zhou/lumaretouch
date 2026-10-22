import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createWorkflow,type Context,type Transport} from './workflow';
let ownIntent=false;
const api:Transport={
 preview:async(action,previewId,sessionId,documentId,mutation)=>{if(action==='preview'&&mutation?.action==='view')await settleCurveEdit();return invoke('studio_background_preview',{action,previewId,sessionId,documentId,mutation:mutation??null});},
 status:previewId=>invoke('studio_background_preview_status',{previewId}),
 submit:async r=>{await settleCurveEdit();ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}return invoke('studio_background',{requestId:r.request_id,previewId:r.preview_id,sessionId:r.session_id,documentId:r.document_id});},
 result:requestId=>invoke('studio_background_result',{requestId}),
};
export function useStudioBackgroundWorkflow(context:Context,refresh:()=>Promise<void>,prepare?:()=>void){
 const latest=useRef(refresh),before=useRef(prepare);latest.current=refresh;before.current=prepare;
 const workflow=useMemo(()=>{const owner=createWorkflow(api,()=>latest.current());return {...owner,start:async()=>{before.current?.();await owner.start();},capturing:()=>owner.snapshot().open};},[]);
 const [state,setState]=useState(workflow.snapshot());
 useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const off=workflow.subscribe(setState);return()=>{off();workflow.stop();};},[workflow]);
 useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
 useEffect(()=>{const edit=()=>{if(!ownIntent)workflow.externalEdit();};const escape=(e:KeyboardEvent)=>{if(e.key==='Escape'&&workflow.capturing()){e.preventDefault();workflow.cancel();}};
   window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',escape);return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',escape);};},[workflow]);
 return {workflow,state,context,active:state.open,pending:workflow.busy()};
}
export type StudioOwner=ReturnType<typeof useStudioBackgroundWorkflow>;
