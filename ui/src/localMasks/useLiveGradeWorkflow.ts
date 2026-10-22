import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import {createLiveGradeWorkflow,type LiveGradeTransport,type LiveGradeContext} from './liveGradeWorkflow';

let ownIntent=false;
const api:LiveGradeTransport={
  send:async p=>{
    if(p.action==='begin'){
      await settleCurveEdit();
      ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
    }
    return invoke('local_grade_live',{action:p.action,requestId:p.request_id,documentId:p.document_id,
      sessionId:p.session_id,groupId:p.group_id,...(p.grade?{grade:p.grade}:{})});
  },
  result:requestId=>invoke('local_grade_live_result',{requestId}),
};

/** Keep this owner at App scope so panel collapse does not lose pending receipts. */
export function useLiveGradeWorkflow(context:LiveGradeContext,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createLiveGradeWorkflow(api,{refresh:()=>refreshRef.current()}),[]);
  const [state,setState]=useState(workflow.snapshot());
  useLayoutEffect(()=>{setState(workflow.snapshot());return workflow.subscribe(setState);},[workflow]);
  useLayoutEffect(()=>{workflow.context(context);},[workflow,context.enabled,context.documentId,context.canStart]);
  useEffect(()=>{
    const edit=()=>{if(!ownIntent)workflow.cancel('已切换编辑操作，未提交调色已取消');};
    const blur=()=>workflow.cancel('窗口失焦，未提交调色已取消');
    const visibility=()=>{if(document.hidden)blur();};
    const key=(event:KeyboardEvent)=>{
      if(workflow.busy()&&(event.key==='Escape'||((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'))){
        event.preventDefault();event.stopImmediatePropagation();workflow.cancel();
      }
    };
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);
    window.addEventListener('blur',blur);window.addEventListener('keydown',key,true);
    document.addEventListener('visibilitychange',visibility);
    return()=>{
      window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('blur',blur);
      window.removeEventListener('keydown',key,true);document.removeEventListener('visibilitychange',visibility);
      workflow.cancel('编辑器已关闭，未提交调色已取消');
    };
  },[workflow]);
  return {workflow,state,busy:workflow.busy(),enabled:context.enabled};
}
export type LiveGradeOwner=ReturnType<typeof useLiveGradeWorkflow>;
