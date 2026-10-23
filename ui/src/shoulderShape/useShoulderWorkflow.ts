// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import type {DocState,EngineStatus} from '../native';
import {ShoulderController} from './controller';
import {shoulderBinding} from './context';
import {innerReceipt} from './receipts';
import {useShoulderModel} from './useShoulderModel';
import {boundCommand,command,createShoulderPort,type Command,type ModelStatus,type Reply,type SourcePreview} from './nativePort';
import type {Binding,BodyRef,ShoulderView} from './model';
const unknownModel:ModelStatus={installed:false,state:'unknown',reason:'尚未查询可选模型文件，也未验证 MediaPipe 运行环境。',download_bytes:null,pin_status:'unknown'};
function matches(view:ShoulderView,binding:Binding|null){return !!binding&&view.binding.document_id===binding.document_id&&view.binding.document_epoch===binding.document_epoch&&view.binding.asset_sha256===binding.asset_sha256;}
export function useShoulderWorkflow(status:EngineStatus|null,doc:DocState|null,refresh:()=>Promise<void>){
 const binding=shoulderBinding(status,doc);
 const supported=status?.ready_caps?.shoulder_shape_protocol===1;
 const enabled=!!status?.engine_alive&&supported&&!!binding&&!status?.export_progress;
 const live=useRef({binding,enabled,refresh});live.current={binding,enabled,refresh};
 const port=useMemo(()=>createShoulderPort(),[]);
 const [view,setView]=useState<ShoulderView|null>(null),[model,setModel]=useState(unknownModel),[source,setSource]=useState<SourcePreview|null>(null);
 const [candidates,setCandidates]=useState<import('./nativePort').Payload['analysis_candidates']>();
 const [task,setTask]=useState<Command|null>(null),[message,setMessage]=useState(''),[uncertain,setUncertain]=useState(false);
 const inflight=useRef<Command|null>(null);
 const adopt=useCallback((reply:Reply)=>{
  const data=reply.result;if(!data)return;
  if(data.model)setModel(data.model);
  const current=live.current.binding;
  if(data.view&&matches(data.view,current))setView(old=>old&&matches(old,current)&&old.state_revision>data.view!.state_revision?old:data.view!);
  if(data.source_preview&&current&&data.source_preview.source_sha256===current.asset_sha256)setSource(data.source_preview);
  if(data.analysis_candidates&&data.view&&matches(data.view,current))setCandidates(data.analysis_candidates);
 },[]);
 const editIds=useRef(new Map<string,string>());
 const controller=useMemo(()=>new ShoulderController({
  send:async request=>{
   if(!live.current.enabled)throw Error('当前照片或引擎尚未就绪');
   const wire=command('edit',request);editIds.current.set(request.request_id,wire.request_id);
   const reply=await port.send(wire);adopt(reply);
   const result=innerReceipt(reply,request.request_id);
   if(result.phase==='done'&&!result.outcome_unknown){void port.release(wire.request_id);editIds.current.delete(request.request_id);void live.current.refresh().catch(()=>undefined);}
   return result;
  },
  status:async id=>{
   const original=editIds.current.get(id);let reply:Reply|null=null;
   if(original){try{reply=await port.status(original);if(!reply)return {phase:'pending',request_id:id,outcome_unknown:true};}catch{/* An unavailable outer mailbox is not proof of a failed write. Query the inner ledger. */}}
   let outerId=original;
   if(!reply||innerReceipt(reply,id).phase!=='done'||innerReceipt(reply,id).outcome_unknown){
    const wire=command('status',{request_id:id});outerId=wire.request_id;reply=await port.send(wire);
   }
   adopt(reply);
   const result=innerReceipt(reply,id);
   // A completed read-only lookup may be released even while its original write remains unknown.
   if(outerId&&outerId!==original)void port.release(outerId);
   if(result.phase==='done'&&!result.outcome_unknown){if(original)void port.release(original);editIds.current.delete(id);void live.current.refresh().catch(()=>undefined);}
   return result;
  },
 }),[port,adopt]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const context=JSON.stringify([binding?.document_id,binding?.document_epoch,binding?.asset_sha256]);
 useLayoutEffect(()=>{setView(null);setSource(null);setCandidates(undefined);controller.clear();},[context,controller]);
 useLayoutEffect(()=>{if(doc?.shoulder_shape&&matches(doc.shoulder_shape,binding)){setView(doc.shoulder_shape);controller.update(doc.shoulder_shape);}},[doc?.shoulder_shape,binding,controller]);
 useLayoutEffect(()=>{if(view&&matches(view,live.current.binding))controller.update(view);},[controller,view]);
 const finish=useCallback(async(command:Command,reply:Reply)=>{
  if(reply.request_id!==command.request_id)throw Error('肩部操作回执不匹配');
  if(reply.outcome_unknown)throw Error(reply.error??'肩部操作结果仍待确认');
  if(command.action==='reanalyse'&&reply.success)setCandidates(undefined);
  adopt(reply);inflight.current=null;setTask(null);setUncertain(false);await port.release(command.request_id);
  if(!reply.success){setMessage(reply.error??'肩部操作未完成');return;}
  setMessage('');if(command.action!=='view')void live.current.refresh().catch(()=>undefined);
 },[adopt,port]);
 const run=useCallback(async(action:'view'|'select'|'analyse'|'reanalyse',body?:BodyRef,candidate?:BodyRef)=>{
  if(!live.current.enabled||!live.current.binding)throw Error('请等待当前照片与引擎状态同步');
  if(inflight.current||controller.snapshot().phase!=='idle')throw Error('请先查询或等待当前肩部请求');
  const wire=action==='reanalyse'?command(action,{binding:live.current.binding,body_ref:body,candidate_ref:candidate,run_id:candidates?.run_id,user_confirmed:true}):boundCommand(action,live.current.binding,body);inflight.current=wire;setTask(wire);setMessage('');setUncertain(false);
  try{await finish(wire,await port.send(wire));}catch(error){setUncertain(true);setMessage(error instanceof Error?error.message:'操作结果尚未确认');}
 },[controller,finish,port,candidates]);
 const check=useCallback(async()=>{const command=inflight.current;if(!command){await controller.reconcile();return;}try{const reply=await port.status(command.request_id);if(reply)await finish(command,reply);else setMessage('原请求仍在处理，不会重发。');}catch(error){setMessage(error instanceof Error?error.message:'回执仍不可查询');}},[controller,finish,port]);
 const acquisition=useShoulderModel(()=>{void run('view').catch(error=>setMessage(String(error)));});
 const currentView=state.view&&matches(state.view,binding)?state.view:view&&matches(view,binding)?view:null;
 return {controller,state,view:currentView,model,candidates,dismissCandidates:()=>setCandidates(undefined),acquisition,source:source&&binding&&source.source_sha256===binding.asset_sha256?source:null,supported,enabled,
  busy:!!task||state.phase!=='idle',task:task?.action??null,uncertain,message,run,check};
}
export type ShoulderOwner=ReturnType<typeof useShoulderWorkflow>;
