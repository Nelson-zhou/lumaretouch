import type {ShadowTransferAck} from '../originalShadow/transferModel';
import {useEffect,useRef,useState} from 'react';
import type {SpillTransferAck} from '../spillRemoval/transferModel';
import {createBatchWorkflow,type BatchContext,type BatchUi} from './batchWorkflow';
import {runBatch,readBatchResult} from '../native';
export function useBatchWorkflow(context:BatchContext,onComplete:()=>void){
  const [ui,setUi]=useState<BatchUi>({phase:'closed',operation:'preflight',plan:null,result:null,message:'',scopeLabel:''});
  const latest=useRef({context,onComplete});latest.current={context,onComplete};
  const ref=useRef<ReturnType<typeof createBatchWorkflow>|null>(null);
  useEffect(()=>{
    let live=true,reported="";
    const flow=createBatchWorkflow({request:runBatch,read:readBatchResult},state=>{
      if(!live)return;setUi(state);
      if(state.result&&state.operation!=='preflight'&&reported!==state.result.request_id){reported=state.result.request_id;latest.current.onComplete();}
    });
    ref.current=flow;flow.updateContext(latest.current.context);
    return()=>{live=false;ref.current=null;flow.dispose();};
  },[]);
  const contextKey=JSON.stringify(context);
  useEffect(()=>{ref.current?.updateContext(context);},[contextKey]);
  const current=()=>{ref.current?.updateContext(latest.current.context);return ref.current;};
  return {ui,start:()=>current()?.start(),commit:(ack?:SpillTransferAck[],shadowAck?:ShadowTransferAck[])=>current()?.commit(ack,shadowAck),undo:(id:string)=>current()?.undo(id),redo:(id:string)=>current()?.redo(id),
    query:()=>current()?.query(),acknowledgeInspection:()=>ref.current?.acknowledgeInspection(),close:()=>ref.current?.close()};
}
