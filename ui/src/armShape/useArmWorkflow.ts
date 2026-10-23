// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useEffect,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import type {DocState,EngineStatus} from '../native';
import {ArmController} from './controller';
import {armBinding} from './context';
import {boundCommand,command,createArmPort,innerReceipt,type Command,type Reply} from './nativeTransport';
import {armSourcePreview,type SourcePreview} from './sourcePreview';
import {createProposalJobs} from './proposalJobs';
import type {ArmView,Binding,BodyRef,Request,Transport} from './model';
function matches(view:ArmView,binding:Binding|null){return !!binding&&view.binding.document_id===binding.document_id&&view.binding.document_epoch===binding.document_epoch&&view.binding.asset_sha256===binding.asset_sha256;}
export function useArmWorkflow(status:EngineStatus|null,doc:DocState|null,refresh:()=>Promise<void>,blocked:boolean){
 const binding=armBinding(status,doc),supported=status?.ready_caps?.arm_shape_protocol===1;
 const enabled=!!status?.engine_alive&&supported&&!!binding&&!status?.export_progress&&!blocked;
 const live=useRef({binding,enabled,refresh});live.current={binding,enabled,refresh};
 const port=useMemo(()=>createArmPort(),[]),inflight=useRef<Command|null>(null),editIds=useRef(new Map<string,string>()),checking=useRef<Promise<void>|null>(null);
 const [view,setView]=useState<ArmView|null>(null),[source,setSource]=useState<SourcePreview|null>(null),[task,setTask]=useState<Command|null>(null),[message,setMessage]=useState(''),[uncertain,setUncertain]=useState(false),[proposalRevision,setProposalRevision]=useState(0);
 const controllerRef=useRef<ArmController|null>(null);
 const valid=useCallback((request:Request)=>{const current=live.current;return current.enabled&&!!current.binding&&!inflight.current&&request.document_id===current.binding.document_id&&request.document_epoch===current.binding.document_epoch&&request.body_ref.asset_sha256===current.binding.asset_sha256;},[]);
 const proposals=useMemo(()=>createProposalJobs(port,request=>valid(request)&&controllerRef.current?.snapshot().phase==='idle',()=>setProposalRevision(n=>n+1)),[port,valid]);
 const adopt=useCallback((reply:Reply)=>{
  const data=reply.result,current=live.current.binding;if(!data)return;
  const next=data.view??data.receipt?.view;
  if(next&&matches(next,current))setView(old=>old&&matches(old,current)&&(old.state_revision>next.state_revision||old.binding.document_revision>next.binding.document_revision)?old:next);
  if(data.source_preview&&current&&data.source_preview.source_sha256===current.asset_sha256){const image=armSourcePreview(data.source_preview);if(image)setSource(image);}
 },[]);
 const transport=useMemo<Transport>(()=>({
  send:async request=>{
   if(!valid(request)||proposals.active().length)return {phase:'done',request_id:request.request_id,success:false,outcome_unknown:false,error:'照片、身体或其他工具状态已变化，未提交手臂调整。'};
   const wire=command('execute',request);editIds.current.set(request.request_id,wire.request_id);
   const reply=await port.send(wire);adopt(reply);const result=innerReceipt(reply,request.request_id);
   if(result.phase==='done'&&!result.outcome_unknown){void port.release(wire.request_id);editIds.current.delete(request.request_id);void live.current.refresh().catch(()=>undefined);}return result;
  },
  status:async id=>{
   const original=editIds.current.get(id);let reply:Reply|null=null;
   if(original){try{reply=await port.status(original);if(!reply)return {phase:'pending',request_id:id,outcome_unknown:true};}catch{/* Missing outer receipt is not negative execution proof. */}}
   let outerId=original;
   if(!reply||innerReceipt(reply,id).phase!=='done'||innerReceipt(reply,id).outcome_unknown){const wire=command('status',{request_id:id});outerId=wire.request_id;reply=await port.send(wire);}
   adopt(reply);const result=innerReceipt(reply,id);if(outerId&&outerId!==original)void port.release(outerId);
   if(result.phase==='done'&&!result.outcome_unknown){if(original)void port.release(original);editIds.current.delete(id);void live.current.refresh().catch(()=>undefined);}return result;
  },startProposal:proposals.start,proposalStatus:proposals.status,cancelProposal:proposals.cancel,
 }),[adopt,port,proposals,valid]);
 const controller=useMemo(()=>new ArmController(transport),[transport]);controllerRef.current=controller;
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot),context=JSON.stringify([binding?.document_id,binding?.document_epoch,binding?.asset_sha256]);
 useLayoutEffect(()=>{setView(null);setSource(null);controller.clear();for(const id of proposals.retained())void proposals.cancel(id).catch(()=>undefined);},[context,controller,proposals]);
 useLayoutEffect(()=>{if(doc?.arm_shape&&matches(doc.arm_shape,binding)){setView(old=>old&&matches(old,binding)&&(old.state_revision>doc.arm_shape!.state_revision||old.binding.document_revision>doc.arm_shape!.binding.document_revision)?old:doc.arm_shape!);controller.update(doc.arm_shape);}},[doc?.arm_shape,binding,controller]);
 useLayoutEffect(()=>{if(view&&matches(view,live.current.binding))controller.update(view);},[controller,view]);
 const proposalBusy=proposals.active().length>0;
 useEffect(()=>{if(!proposalBusy)return;const timer=setInterval(()=>{for(const id of proposals.active())void proposals.status(id).catch(error=>setMessage(error instanceof Error?error.message:'选区任务仍待核对'));},1200);return ()=>clearInterval(timer);},[proposalBusy,proposals]);
 useEffect(()=>()=>{for(const id of proposals.retained())void proposals.cancel(id).catch(()=>undefined);},[proposals]);
 const finish=useCallback(async(wire:Command,reply:Reply)=>{
  if(inflight.current!==wire)return;
  if(reply.request_id!==wire.request_id||reply.action!==wire.action||reply.outcome_unknown)throw Error(reply.error??'手臂操作结果仍待确认');
  adopt(reply);inflight.current=null;setTask(null);setUncertain(false);void port.release(wire.request_id);
  setMessage(reply.success?'':reply.error??'手臂操作未完成');if(reply.success&&wire.action!=='view')void live.current.refresh().catch(()=>undefined);
 },[adopt,port]);
 const run=useCallback(async(action:'view'|'select',body?:BodyRef)=>{
  if(!live.current.enabled||!live.current.binding)throw Error('请等待当前照片、引擎与其他工具就绪');
  if(inflight.current||controller.snapshot().phase!=='idle'||proposals.active().length)throw Error('请先等待或查询原手臂请求');
  const wire=boundCommand(action,live.current.binding,body);inflight.current=wire;setTask(wire);setMessage('');setUncertain(false);
  try{await finish(wire,await port.send(wire));}catch(error){if(inflight.current===wire){setUncertain(true);setMessage(error instanceof Error?error.message:'操作结果尚未确认');}}
 },[controller,finish,port,proposals]);
 const check=useCallback(()=>{
  if(checking.current)return checking.current;
  const query=(async()=>{const wire=inflight.current;try{if(wire){const reply=await port.status(wire.request_id);if(reply)await finish(wire,reply);else setMessage('原请求仍在处理，不会重发。');}else await controller.reconcile();for(const id of proposals.active())await proposals.status(id);}catch(error){setMessage(error instanceof Error?error.message:'原回执仍不可查询');}})();
  checking.current=query;void query.then(()=>{if(checking.current===query)checking.current=null;},()=>{if(checking.current===query)checking.current=null;});return query;
 },[controller,finish,port,proposals]);
 const currentView=state.view&&matches(state.view,binding)?state.view:view&&matches(view,binding)?view:null;
 return {controller,transport,state,view:currentView,source:source&&binding&&source.source_sha256===binding.asset_sha256?source:null,supported,enabled,busy:!!task||state.phase!=='idle'||proposalBusy,proposalBusy,proposalRevision,task:task?.action??null,uncertain:uncertain||proposals.uncertain(),message,run,check};
}
export type ArmOwner=ReturnType<typeof useArmWorkflow>;
