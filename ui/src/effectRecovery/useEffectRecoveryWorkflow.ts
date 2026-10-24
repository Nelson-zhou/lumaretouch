import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent,runHistory} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createRecoveryWorkflow,type RecoveryContext,type RecoveryTransport} from './workflow';
import type {RecoveryReport} from './model';

let ownIntent=false;
const api:RecoveryTransport={
  arm:async(captureId,documentId)=>{await settleCurveEdit();return invoke('source_patch_capture',{action:'arm',captureId,ticket:null,documentId,purpose:'local-masks'});},
  status:(captureId,ticket)=>invoke('source_patch_capture_status',{captureId,ticket}),
  frame:(captureId,ticket)=>invoke('source_patch_capture_frame',{captureId,ticket}),
  presented:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'presented',captureId,ticket,documentId}),
  cancel:(captureId,ticket,documentId)=>invoke('source_patch_capture',{action:'cancel',captureId,ticket,documentId}),
  preview:(action,previewId,captureId,ticket,mutation,ack)=>invoke('effect_recovery_preview',{action,previewId,captureId,ticket,mutation:mutation??null,...(ack?{protocol:2,ack}:{})}),
  previewStatus:previewId=>invoke('effect_recovery_preview_status',{previewId}),
  aliasImage:{image:request=>invoke('effect_recovery_preview',{action:'image',protocol:2,...request}),
    imageStatus:(previewId,requestId)=>invoke('effect_recovery_preview_status',{previewId,requestId})},
  submit:async request=>{await settleCurveEdit();ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    return invoke('effect_recovery',{requestId:request.request_id,previewId:request.preview_id,captureId:request.capture_id,ticket:request.ticket,
      ...(request.protocol===2?{protocol:2,ack:request.ack}:{})});},
  result:requestId=>invoke('effect_recovery_result',{requestId}),
};

/** App-scoped, not panel-scoped: collapsing a panel cannot lose a pending receipt. */
export function useEffectRecoveryWorkflow(context:RecoveryContext,refresh:()=>Promise<void>,report?:RecoveryReport,prepare?:()=>void){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const prepareRef=useRef(prepare);prepareRef.current=prepare;
  const reportRef=useRef(report);reportRef.current=report;
  const workflow=useMemo(()=>createRecoveryWorkflow(api,{refresh:()=>refreshRef.current(),prepare:()=>prepareRef.current?.()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{workflow.activate();setState(workflow.snapshot());const off=workflow.subscribe(setState);return()=>{off();workflow.stop();};},[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.canStart,context.documentId,context.contextKey,context.reason]);
  useEffect(()=>{if(workflow.canContinue())void workflow.resume();},[workflow,state.phase,context.enabled,context.canStart,context.contextKey]);
  useEffect(()=>{
    const edit=()=>{if(!ownIntent)workflow.externalEdit();};
    const blur=()=>{if(workflow.capturing()&&!workflow.busy())workflow.cancel('窗口失焦，未提交的恢复笔迹已取消');};
    const visibility=()=>{if(document.hidden)blur();};
    const key=(event:KeyboardEvent)=>{
      const workspace=workflow.snapshot(),opened=workspace.open||workflow.busy(),key=event.key.toLowerCase();
      if(event.key==='Escape'&&opened){event.preventDefault();workflow.cancel();return;}
      if(opened&&(event.ctrlKey||event.metaKey)&&!event.altKey&&['z','y'].includes(key)){
        event.preventDefault();event.stopImmediatePropagation();
        const aliasHistory=workflow.usesAliasHistory(),discardOnly=workflow.busy()||workspace.strokeActive||workspace.ending||aliasHistory;
        workflow.cancel(aliasHistory?'已结束恢复画笔并丢弃未提交笔迹。共享来源恢复只能在人物面板的完整成员恢复批次历史中整体撤销或重做，不执行当前照片的局部撤销。':undefined);
        // Mid-stroke undo cancels that uncommitted gesture. Between strokes it
        // must really undo/redo the document, not silently just close the tool.
        if(!discardOnly&&!event.repeat)void runHistory(key==='y'||event.shiftKey?'redo':'undo')
          .then(()=>refreshRef.current()).catch(error=>workflow.failed(error));
        return;
      }
      const element=event.target as HTMLElement|null;
      if(context.enabled&&context.canStart!==false&&event.key.toLowerCase()==='b'&&!event.repeat&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&
        !element?.isContentEditable&&!['INPUT','TEXTAREA','SELECT'].includes(element?.tagName??'')&&
        !workflow.capturing()&&!workflow.busy()){
        const targets=reportRef.current?.targets??[],selected=workflow.snapshot().target;
        const usable=targets.filter(row=>row.active||row.strokes.length>0);
        const target=usable.find(row=>row.target===selected)?.target??usable[0]?.target;
        if(target){event.preventDefault();void workflow.start(target);}
      }
    };
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key,true);
    window.addEventListener('blur',blur);document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key,true);
      window.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);};
  },[workflow,context.enabled,context.canStart]);
  return {workflow,state,context,active:state.open&&!['idle','failure','uncertain'].includes(state.phase),pending:workflow.busy()};
}
export type EffectRecoveryOwner=ReturnType<typeof useEffectRecoveryWorkflow>;
