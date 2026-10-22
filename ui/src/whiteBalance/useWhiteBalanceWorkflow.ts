import {useEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {createWhiteBalanceWorkflow,type Context} from './workflow';
export function useWhiteBalanceWorkflow(context:Context,refresh:()=>Promise<void>){
  const refreshRef=useRef(refresh);refreshRef.current=refresh;
  const workflow=useMemo(()=>createWhiteBalanceWorkflow({
    send:r=>invoke('white_balance',{action:r.action,algorithm:r.algorithm??null,requestId:r.request_id,documentId:r.document_id}),
    query:id=>invoke('white_balance_result',{requestId:id}),refresh:()=>refreshRef.current(),
    id:()=>`wb-${crypto.randomUUID()}`,sleep:ms=>new Promise(resolve=>setTimeout(resolve,ms)),
  }),[]);
  workflow.context(context);
  const [state,setState]=useState(workflow.snapshot());
  useEffect(()=>{workflow.activate();setState(workflow.snapshot());const unsubscribe=workflow.subscribe(setState);return()=>{unsubscribe();workflow.stop();};},[workflow]);
  return {workflow,state,context};
}
