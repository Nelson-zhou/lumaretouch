// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useLayoutEffect,useMemo,useRef,useState,useSyncExternalStore} from 'react';
import type {DocState,EngineStatus} from '../native';
import {WaistController} from './controller';
import {waistBinding} from './context';
import {innerReceipt} from './receipts';
import {boundCommand,command,createWaistPort,type Command,type Reply,type SourcePreview} from './nativeTransport';
import {previewImage} from './sourcePreview';
import type {Binding,BodyRef,WaistView} from './model';
function matches(view:WaistView,binding:Binding|null){return !!binding&&view.binding.document_id===binding.document_id&&view.binding.document_epoch===binding.document_epoch&&view.binding.asset_sha256===binding.asset_sha256;}
export function useWaistWorkflow(status:EngineStatus|null,doc:DocState|null,refresh:()=>Promise<void>,blocked:boolean){
 const binding=waistBinding(status,doc),supported=status?.ready_caps?.waist_shape_protocol===1;
 const enabled=!!status?.engine_alive&&supported&&!!binding&&!status?.export_progress&&!blocked;
 const live=useRef({binding,enabled,refresh});live.current={binding,enabled,refresh};
 const port=useMemo(()=>createWaistPort(),[]);
 const [view,setView]=useState<WaistView|null>(null),[source,setSource]=useState<SourcePreview|null>(null);
 const [task,setTask]=useState<Command|null>(null),[message,setMessage]=useState(''),[uncertain,setUncertain]=useState(false);
 const checking=useRef<Promise<void>|null>(null);
 const inflight=useRef<Command|null>(null),editIds=useRef(new Map<string,string>());
 const adopt=useCallback((reply:Reply)=>{
  const data=reply.result,current=live.current.binding;if(!data)return;
  if(data.view&&matches(data.view,current))setView(old=>old&&matches(old,current)&&(old.state_revision>data.view!.state_revision||old.binding.document_revision>data.view!.binding.document_revision)?old:data.view!);
  if(data.source_preview&&current&&data.source_preview.source_sha256===current.asset_sha256&&previewImage(data.source_preview))setSource(data.source_preview);
 },[]);
 const controller=useMemo(()=>new WaistController({
  send:async request=>{
   const current=live.current;
   if(!current.enabled||!current.binding||request.document_id!==current.binding.document_id||request.document_epoch!==current.binding.document_epoch||request.body_ref.asset_sha256!==current.binding.asset_sha256)
    return {phase:'done',request_id:request.request_id,success:false,outcome_unknown:false,error:'当前照片、身体或其他工具状态已变化，未提交腰部调整。'};
   const wire=command('edit',request);editIds.current.set(request.request_id,wire.request_id);
   const reply=await port.send(wire);adopt(reply);const result=innerReceipt(reply,request.request_id);
   if(result.phase==='done'&&!result.outcome_unknown){void port.release(wire.request_id);editIds.current.delete(request.request_id);void live.current.refresh().catch(()=>undefined);}
   return result;
  },
  status:async id=>{
   const original=editIds.current.get(id);let reply:Reply|null=null;
   if(original){try{reply=await port.status(original);if(!reply)return {phase:'pending',request_id:id,outcome_unknown:true};}catch{/* Lost outer receipt is never negative execution proof. */}}
   let outerId=original;
   if(!reply||innerReceipt(reply,id).phase!=='done'||innerReceipt(reply,id).outcome_unknown){const wire=command('status',{request_id:id});outerId=wire.request_id;reply=await port.send(wire);}
   adopt(reply);const result=innerReceipt(reply,id);
   if(outerId&&outerId!==original)void port.release(outerId);
   if(result.phase==='done'&&!result.outcome_unknown){if(original)void port.release(original);editIds.current.delete(id);void live.current.refresh().catch(()=>undefined);}
   return result;
  },
 }),[port,adopt]);
 const state=useSyncExternalStore(controller.subscribe,controller.snapshot,controller.snapshot);
 const context=JSON.stringify([binding?.document_id,binding?.document_epoch,binding?.asset_sha256]);
 useLayoutEffect(()=>{setView(null);setSource(null);controller.clear();},[context,controller]);
 useLayoutEffect(()=>{if(doc?.waist_shape&&matches(doc.waist_shape,binding)){setView(doc.waist_shape);controller.update(doc.waist_shape);}},[doc?.waist_shape,binding,controller]);
 useLayoutEffect(()=>{if(view&&matches(view,live.current.binding))controller.update(view);},[controller,view]);
 const finish=useCallback(async(wire:Command,reply:Reply)=>{
  if(inflight.current!==wire)return;
  if(reply.request_id!==wire.request_id||reply.outcome_unknown)throw Error(reply.error??'腰部操作结果仍待确认');
  adopt(reply);inflight.current=null;setTask(null);setUncertain(false);await port.release(wire.request_id);
  if(!reply.success){setMessage(reply.error??'腰部操作未完成');return;}
  setMessage('');if(wire.action!=='view')void live.current.refresh().catch(()=>undefined);
 },[adopt,port]);
 const run=useCallback(async(action:'view'|'select',body?:BodyRef)=>{
  if(!live.current.enabled||!live.current.binding)throw Error('请等待当前照片、引擎与其他工具就绪');
  if(inflight.current||controller.snapshot().phase!=='idle')throw Error('请先查询或等待当前腰部请求');
  const wire=boundCommand(action,live.current.binding,body);inflight.current=wire;setTask(wire);setMessage('');setUncertain(false);
  try{await finish(wire,await port.send(wire));}catch(error){if(inflight.current===wire){setUncertain(true);setMessage(error instanceof Error?error.message:'操作结果尚未确认');}}
 },[controller,finish,port]);
 const check=useCallback(()=>{
  if(checking.current)return checking.current;
  const wire=inflight.current;if(!wire)return controller.reconcile();
  const query=(async()=>{try{const reply=await port.status(wire.request_id);if(inflight.current!==wire)return;if(reply)await finish(wire,reply);else setMessage('原请求仍在处理，不会重发。');}catch(error){if(inflight.current===wire)setMessage(error instanceof Error?error.message:'回执仍不可查询');}})();
  checking.current=query;void query.finally(()=>{if(checking.current===query)checking.current=null;});return query;
 },[controller,finish,port]);
 const currentView=state.view&&matches(state.view,binding)?state.view:view&&matches(view,binding)?view:null;
 return {controller,state,view:currentView,source:previewImage(source&&binding&&source.source_sha256===binding.asset_sha256?source:null),supported,enabled,busy:!!task||state.phase!=='idle',task:task?.action??null,uncertain,message,run,check};
}
export type WaistOwner=ReturnType<typeof useWaistWorkflow>;
