import type {EyeBagAliasCommit} from '../eyeBagPreserve/model';
import type {EyeBagCohortAck} from '../eyeBagPreserve/cohortModel';
import type {EyeBagBatchAck} from '../eyeBagPreserve/batchModel';
import type {PortraitCohortAck} from '../portraitCohort/model';
import type {CollarboneAck} from '../collarbone/transferModel';
import type {FaceStyleBatchAck} from '../faceStyle/batchModel';
import type {FaceStyleAliasCommit} from '../faceStyle/model';
import type {ShadowTransferAck} from '../originalShadow/transferModel';
import type {TorsoTransferAck} from '../torsoLength/transferModel';
import type {WaistTransferAck} from '../waistLength/transferModel';
import type {HeadTransferAck} from '../headSize/transferModel';
import {useEffect,useRef,useState} from 'react';
import type {SpillTransferAck} from '../spillRemoval/transferModel';
import {createBatchWorkflow,type BatchContext,type BatchUi} from './batchWorkflow';
import {runBatch,readBatchResult} from '../native';
import {batchCompletionRequest} from './completion';
export function useBatchWorkflow(context:BatchContext,onComplete:()=>void){
  const [ui,setUi]=useState<BatchUi>({phase:'closed',operation:'preflight',plan:null,result:null,message:'',scopeLabel:''});
  const latest=useRef({context,onComplete});latest.current={context,onComplete};
  const ref=useRef<ReturnType<typeof createBatchWorkflow>|null>(null);
  useEffect(()=>{
    let live=true,reported="";
    const flow=createBatchWorkflow({request:runBatch,read:readBatchResult},state=>{
      if(!live)return;setUi(state);
      const completion=batchCompletionRequest(state,reported);
      if(completion){reported=completion;latest.current.onComplete();}
    });
    ref.current=flow;flow.updateContext(latest.current.context);
    return()=>{live=false;ref.current=null;flow.dispose();};
  },[]);
  const contextKey=JSON.stringify(context);
  useEffect(()=>{ref.current?.updateContext(context);},[contextKey]);
  const current=()=>{ref.current?.updateContext(latest.current.context);return ref.current;};
  return {ui,start:()=>current()?.start(),commit:(ack?:SpillTransferAck[],shadowAck?:ShadowTransferAck[],torsoAck?:TorsoTransferAck[],waistAck?:WaistTransferAck[],headAck?:HeadTransferAck[],collarboneAck?:CollarboneAck[],faceStyleAck?:FaceStyleBatchAck[],portraitAck?:PortraitCohortAck[],eyeBagAck?:EyeBagBatchAck[],eyeCohortAck?:EyeBagCohortAck[])=>current()?.commit(ack,shadowAck,torsoAck,waistAck,headAck,collarboneAck,faceStyleAck,portraitAck,eyeBagAck,eyeCohortAck),undo:(id:string)=>current()?.undo(id),redo:(id:string)=>current()?.redo(id),
    query:()=>current()?.query(),protectEyeBagAlias:(commit:EyeBagAliasCommit)=>current()?.protectEyeBagAlias(commit)??false,protectFaceStyleAlias:(commit:FaceStyleAliasCommit)=>current()?.protectFaceStyleAlias(commit)??false,
    acknowledgeInspection:()=>ref.current?.acknowledgeInspection(),close:()=>ref.current?.close()};
}
