// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect,useLayoutEffect,useMemo,useRef,useSyncExternalStore} from 'react';
import {ExpressionController} from './controller';
import {createExpressionNativePort,type CurrentReply,type ExpressionNativePort} from './nativePort';
import {freeze,type Current,type ExpressionCapability,type Receipt} from './model';

/** All fields come from the existing App/native state, not reconstructed from filenames. */
export interface ExpressionWorkspaceContext {
  sourceUid:string;loadId:string;engineKey:string;hostRevision:number;
  available:boolean;busy:boolean;queueBusy?:boolean;
}
type CopyReceipt=Extract<Receipt,{phase:'committed'}>;
type AcquisitionPhase='idle'|'working'|'pending'|'unknown'|'cancelling';
interface CurrentTask {id:string;scope:string;command_sha256:string|null;cancel_requested:boolean;cancel_sent:boolean}
export type ExpressionAcquisition=Readonly<{request_id:string;phase:Exclude<AcquisitionPhase,'idle'>;cancel_requested:boolean}>;
type OwnerState=Readonly<{
  current:Current|null;current_scope:string|null;capability:ExpressionCapability;phase:AcquisitionPhase;acquisition:ExpressionAcquisition|null;
  message:string;refreshing:boolean;last_result:CopyReceipt|null;
}>;
const scope=(context:ExpressionWorkspaceContext)=>JSON.stringify([context.engineKey,context.sourceUid,context.loadId,context.hostRevision]);
const usable=(context:ExpressionWorkspaceContext)=>!!context.engineKey&&!!context.sourceUid&&!!context.loadId&&Number.isSafeInteger(context.hostRevision)&&context.hostRevision>=0&&context.available&&!context.busy;
const reason=(error:unknown)=>error instanceof Error?error.message:String(error);

/** One owner per App lifetime. Panel visibility never owns its controller or native receipts. */
class ExpressionWorkspaceOwner {
  readonly controller:ExpressionController;
  private readonly listeners=new Set<()=>void>();
  private context:ExpressionWorkspaceContext;
  private state:OwnerState;
  private task:CurrentTask|null=null;
  private checking:Promise<void>|null=null;
  private starting=false;
  private startGeneration=0;
  constructor(private readonly native:ExpressionNativePort,context:ExpressionWorkspaceContext,private readonly changed:()=>Promise<void>){
    this.context={...context};
    this.state=freeze({current:null,current_scope:null,capability:native.capability,phase:'idle',acquisition:null,message:'请明确获取当前完整修图结果，随后独立分析人脸。',refreshing:false,last_result:null});
    this.controller=new ExpressionController(native,{onCommitted:receipt=>{void this.refreshAfterCopy(receipt);}});
  }
  snapshot=():OwnerState=>this.state;
  subscribe=(listener:()=>void):(()=>void)=>{this.listeners.add(listener);return()=>{this.listeners.delete(listener);};};
  private publish(patch:Partial<OwnerState>):void{this.state=freeze({...this.state,...patch});this.listeners.forEach(listener=>listener());}
  private taskState(phase:Exclude<AcquisitionPhase,'idle'>,message:string):void{
    const task=this.task;this.publish({phase,acquisition:task?{request_id:task.id,phase,cancel_requested:task.cancel_requested}:null,message});
  }
  updateContext(next:ExpressionWorkspaceContext):void{
    const changed=scope(next)!==scope(this.context),lost=usable(this.context)&&!usable(next);
    this.context={...next};
    if(!changed&&!lost)return;
    ++this.startGeneration;
    this.publish({current:null,current_scope:null,message:'照片、引擎、修订或其他工具状态已变化；旧来源复核已失效。'});
    // The controller retains an unresolved save and requests cancellation only for reads.
    this.controller.bind(null);
    if(this.task){this.task.cancel_requested=true;this.taskState('cancelling','已请求作废旧来源获取；等待原任务终态，不会自动重新分析。');void this.requestCurrentCancellation(this.task);}
  }
  private async refreshAfterCopy(receipt:CopyReceipt):Promise<void>{
    this.publish({last_result:receipt,refreshing:true,message:`独立副本 ${receipt.result_document_id} 已有匹配保存回执，正在刷新真实文档列表与画面。`});
    try{
      await this.changed();
      this.publish({current:null,current_scope:null,message:`独立副本 ${receipt.result_document_id} 已保存并刷新；原照片保持不变。如需继续替换，请重新获取当前完整来源。`});
      this.controller.bind(null);
    }catch(error){this.publish({message:`副本已保存，但刷新未完成：${reason(error)}。不要重复保存；请刷新文档状态。`});}
    finally{this.publish({refreshing:false});}
  }
  canAcquire():boolean{return usable(this.context)&&!this.context.queueBusy&&!this.starting&&!this.task&&!this.state.refreshing&&this.controller.canDetach();}
  acquireCurrent=async():Promise<void>=>{
    if(!this.canAcquire()){this.publish({message:'请先等待或查询现有任务，并保持当前照片与引擎就绪；不会重复捕获或分析。'});return;}
    this.starting=true;const expected=scope(this.context),generation=++this.startGeneration;
    this.publish({phase:'working',message:'正在核验表情模块；获取来源会执行一次完整当前渲染和独立真实人脸分析。'});
    try{
      const capability=await this.native.refreshCapability();this.publish({capability});
      if(!capability.available){this.publish({phase:'idle',message:capability.reason||'原生表情模块不可用，已有配方未改变。'});return;}
      if(generation!==this.startGeneration||expected!==scope(this.context)||!usable(this.context)){this.publish({phase:'idle',message:'模块核验期间上下文已变化，未启动来源分析。'});return;}
      this.controller.bind(null);this.publish({current:null,current_scope:null});
      const task:CurrentTask={id:crypto.randomUUID(),scope:expected,command_sha256:null,cancel_requested:false,cancel_sent:false};
      this.task=task;this.taskState('working','正在获取完整当前渲染并独立分析人脸；只读取，不写入照片。');
      try{await this.acceptCurrent(await this.native.acquireCurrent(task.id),task);}
      catch(error){if(this.task===task)this.taskState(task.cancel_requested?'cancelling':'unknown',`原来源获取结果未确认：${reason(error)}。只查询原请求，不会自动重跑。`);}
    }finally{this.starting=false;this.publish({});}
  };
  private async acceptCurrent(reply:CurrentReply,task:CurrentTask):Promise<void>{
    if(this.task!==task||reply.request_id!==task.id)return;
    if('command_sha256' in reply&&reply.command_sha256){
      if(task.command_sha256&&task.command_sha256!==reply.command_sha256){this.taskState('unknown','来源获取摘要前后不一致；保持原请求，不采纳结果。');return;}
      task.command_sha256=reply.command_sha256;
    }
    if(reply.phase==='pending'||reply.phase==='unknown'||reply.phase==='cancelling'){
      if(reply.phase==='cancelling')task.cancel_requested=true;
      this.taskState(task.cancel_requested?'cancelling':reply.phase==='unknown'?'unknown':'pending',reply.message);
      if(task.cancel_requested)await this.requestCurrentCancellation(task);
      return;
    }
    this.task=null;
    this.publish({phase:'idle',acquisition:null});
    if(reply.phase==='rejected'||reply.phase==='cancelled'){
      this.publish({message:reply.message||'来源获取已确认终止，没有写入照片。'});return;
    }
    if(task.cancel_requested||task.scope!==scope(this.context)||!usable(this.context)){
      this.publish({message:'原来源获取已结束，但结果已被作废，未用于复核，也未自动重新分析。'});return;
    }
    const current=reply.current;
    // Native canonical revision is not the UI doc_rev event counter. The full
    // binding is verified by the host; UI scope/source/load must remain current.
    if(current.binding.document_id!==this.context.sourceUid||current.binding.load_id!==this.context.loadId){
      this.publish({message:'完整来源回执不属于当前文档、加载会话或修订，未用于复核。'});return;
    }
    this.publish({current,current_scope:task.scope,message:current.available?'完整当前来源及独立人脸分析已就绪，请选择本人和另一张真实素材。':current.unavailable_reason||'当前来源不能进行表情替换。'});
    this.controller.bind(current);
  }
  cancelCurrent=():void=>{
    const task=this.task;
    if(!task){if(this.starting){++this.startGeneration;this.publish({phase:'idle',message:'尚未发送的来源获取已取消，未启动渲染或分析。'});}else this.publish({message:'没有正在获取的来源。'});return;}
    task.cancel_requested=true;this.taskState('cancelling','已请求取消来源获取；等待原任务退出回执，不宣称已强制停止。');void this.requestCurrentCancellation(task);
  };
  private async requestCurrentCancellation(task:CurrentTask):Promise<void>{
    if(this.task!==task||!task.command_sha256||task.cancel_sent)return;
    task.cancel_sent=true;
    try{await this.acceptCurrent(await this.native.cancelCurrent(task.id,task.command_sha256),task);}
    catch(error){if(this.task===task)this.taskState('cancelling',`来源取消尚未确认：${reason(error)}。继续查询原任务，不重发取消或分析。`);}
  }
  check=():Promise<void>=>{
    if(this.checking)return this.checking;
    const operation=(async()=>{
      const task=this.task;
      if(task)try{await this.acceptCurrent(await this.native.currentStatus(task.id),task);}catch(error){if(this.task===task)this.taskState(task.cancel_requested?'cancelling':'unknown',reason(error));}
      if(this.controller.snapshot().request)await this.controller.reconcile();
    })();
    this.checking=operation;void operation.then(()=>{if(this.checking===operation)this.checking=null;},()=>{if(this.checking===operation)this.checking=null;});return operation;
  };
}

/** Mount unconditionally in App. Calling this hook does not capture/render/analyze. */
export function useExpressionReplacement(context:ExpressionWorkspaceContext,onChanged:()=>Promise<void>){
  const changed=useRef(onChanged);changed.current=onChanged;
  const owner=useMemo(()=>new ExpressionWorkspaceOwner(createExpressionNativePort(),context,()=>changed.current()),[]);
  const value=useSyncExternalStore(owner.subscribe,owner.snapshot,owner.snapshot);
  const state=useSyncExternalStore(owner.controller.subscribe,owner.controller.snapshot,owner.controller.snapshot);
  const key=scope(context);
  useLayoutEffect(()=>owner.updateContext(context),[owner,key,context.available,context.busy,context.queueBusy]);
  const pending=!!value.acquisition||!!state.request;
  useEffect(()=>{
    if(!pending)return;
    // Status-only observation continues when the panel is hidden; no per-frame capture.
    const timer=setInterval(()=>{void owner.check().catch(()=>{/* Receipt owner keeps uncertainty visible. */});},1200);
    return()=>clearInterval(timer);
  },[owner,pending]);
  const current=value.current&&value.current_scope===key&&usable(context)&&value.current.binding.document_id===context.sourceUid&&value.current.binding.load_id===context.loadId?value.current:null;
  return {
    controller:owner.controller,current,state,capability:value.capability,acquisition:value.acquisition,
    canAcquire:usable(context)&&owner.canAcquire(),busy:value.phase!=='idle'||value.refreshing||!!state.request,
    message:value.message,lastResult:value.last_result,refreshing:value.refreshing,
    acquireCurrent:owner.acquireCurrent,cancelCurrent:owner.cancelCurrent,check:owner.check,
  };
}
export type ExpressionReplacementOwner=ReturnType<typeof useExpressionReplacement>;
