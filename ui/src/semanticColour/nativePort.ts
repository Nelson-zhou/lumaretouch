import {invoke} from '@tauri-apps/api/core';
import type {ExportReceipt,Progress,WorkflowPort} from './workflowModel';
type ObjectValue=Record<string,unknown>;
type Reply={protocol:1;request_id:string;success:boolean;outcome_unknown:boolean;committed?:boolean|null;result?:unknown;error?:string;action:'request'};
type Pending={action:string;payload:ObjectValue};
const MAX_TARGETS=128,WORKER_BUDGET_MS=240_000,ARCHIVE_BUDGET_MS=600_000;
const mutations=new Set(['commit','edit','batch_apply','batch_restore']);
const prepares=new Set(['batch_prepare','preset_prepare']);
// All panels address the same native engine mailbox. Navigation must not erase
// unresolved request IDs, inspected-write gates or immutable export recovery.
let sharedPort:WorkflowPort|null=null;
let capability={single:()=>false,workflow:()=>false};
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function object(value:unknown):ObjectValue{if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('AI 追色回执格式无效');return value as ObjectValue;}
function deadline<T>(promise:Promise<T>,ms=10_000):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('AI 追色本机通信未确认，不能认定未执行')),ms);promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
function terminal(value:unknown,id:string):Reply|null{
 const outer=object(value);if(outer.request_id!==id)throw new Error('AI 追色回执身份不匹配');if(outer.phase!=='done')return null;
 const reply=object(outer.result) as unknown as Reply;
 if(reply.protocol!==1||reply.request_id!==id||reply.action!=='request'||typeof reply.success!=='boolean'||typeof reply.outcome_unknown!=='boolean')throw new Error('AI 追色回执协议无效');return reply;
}
/** Deadline includes every serial worker, not a fixed single-photo wait. */
function waitBudget(action:string,payload:ObjectValue):number{
 if(prepares.has(action)){
  const count=action==='preset_prepare'?1:Array.isArray(payload.targets)?payload.targets.length:0;
  if(count<1||count>MAX_TARGETS)throw new Error('一次明确选择 1–128 张目标，不会截断或自动分组');
  return (count+1)*(WORKER_BUDGET_MS+30_000)+180_000;
 }
 if(action.startsWith('preset_export_')||action==='preset_import'||action==='batch_apply'||action==='batch_restore')return ARCHIVE_BUDGET_MS;
 return action==='capture'||action==='workflow_inspect'?180_000:60_000;
}
/** No original command is resent. Unknown writes stay fenced until inspection. */
export function createNativeSemanticColour(canUse:()=>boolean,canWorkflow:()=>boolean=()=>false):WorkflowPort{
 capability={single:canUse,workflow:canWorkflow};if(sharedPort)return sharedPort;
 const sessions=new Map<string,string>(),unresolved=new Map<string,Pending>(),unreleased=new Set<string>();
 const unknownMutations=new Map<string,string>(),unknownExports=new Map<string,string>();
 const stagedExports=new Map<string,ExportReceipt>(),exportPaths=new Map<string,string>();
 let inspectedIds:string[]=[];
 let reconciling:Promise<void>|null=null;
 const progressListeners=new Set<(session:string,value:Progress)=>void>(),inspectionListeners=new Set<(required:boolean)=>void>();
 const call=(action:string,id:string,request?:ObjectValue)=>deadline(invoke<unknown>('semantic_colour',{request:{action,request_id:id,...(request?{request}:{})}}));
 const notifyInspection=()=>{for(const listener of inspectionListeners)listener(unknownMutations.size>0||[...unresolved.values()].some(v=>mutations.has(v.action)));};
 const release=async(id:string)=>{unreleased.add(id);try{const reply=object(await call('release',id));if(reply.released===true)unreleased.delete(id);}catch{/* Only idempotent receipt cleanup may be repeated. */}};
 const uncertain=(id:string,pending:Pending)=>{
  if(mutations.has(pending.action)){unknownMutations.set(id,pending.action);inspectedIds=[];}
  if(pending.action==='preset_export_write'&&typeof pending.payload.export_id==='string'&&typeof pending.payload.path==='string')unknownExports.set(pending.payload.export_id,pending.payload.path);
  notifyInspection();
 };
 const consume=(id:string,pending:Pending,reply:Reply)=>{
  const nested=reply.result&&typeof reply.result==='object'?reply.result as ObjectValue:null;
  if(reply.outcome_unknown||nested?.outcome_unknown===true)uncertain(id,pending);
  if(reply.success&&!reply.outcome_unknown&&pending.action==='preset_export_prepare'&&typeof nested?.export_id==='string')stagedExports.set(nested.export_id,nested as unknown as ExportReceipt);
  if(reply.success&&!reply.outcome_unknown&&pending.action==='preset_export_release'&&typeof pending.payload.export_id==='string'){stagedExports.delete(pending.payload.export_id);exportPaths.delete(pending.payload.export_id);unknownExports.delete(pending.payload.export_id);}
  if(reply.success&&!reply.outcome_unknown&&pending.action==='workflow_release'){stagedExports.clear();exportPaths.clear();unknownExports.clear();}
 };
 async function reconcile(){
  if(reconciling)return reconciling;
  const work=(async()=>{
   for(const [id,pending] of [...unresolved]){
    // Cancel is control-lane metadata, never a repeat of the original write.
    let receipt=terminal(await call('cancel',id),id);
    if(!receipt)receipt=terminal(await call('status',id),id);
    if(!receipt)throw new Error('上一操作尚未确认结束，当前配方或文件不能作为最终结果；稍后核对，不要重发');
    consume(id,pending,receipt);await release(id);unresolved.delete(id);
   }
   notifyInspection();
  })();
  reconciling=work;
  try{await work;}finally{if(reconciling===work)reconciling=null;}
 }
 const port:WorkflowPort={
  pendingExport(){const receipt=stagedExports.values().next().value;return receipt?{receipt,path:exportPaths.get(receipt.export_id)??null}:null;},
  subscribeProgress(listener){progressListeners.add(listener);return()=>{progressListeners.delete(listener);};},
  subscribeInspection(listener){inspectionListeners.add(listener);listener(unknownMutations.size>0||[...unresolved.values()].some(v=>mutations.has(v.action)));return()=>{inspectionListeners.delete(listener);};},
  async inspectMutationOutcome(){
   await reconcile();const inspected=[...unknownMutations.keys()];
   const workflow=[...unknownMutations.values()].some(action=>action.startsWith('batch_'))?await port.request('workflow_inspect',{}):null;
   const state=await port.request('state',{});inspectedIds=inspected;
   return {state,workflow};
  },
  acknowledgeInspection(){
   if(unresolved.size)throw new Error('操作仍待终态，不能确认检查完成');
   for(const id of inspectedIds)unknownMutations.delete(id);inspectedIds=[];notifyInspection();
  },
  async request(action,payload){
   if(!capability.single())throw new Error('当前引擎未声明 AI 语义追色协议，请启动配套引擎');
   if(/^(batch_|preset_|workflow_)/.test(action)&&!capability.workflow())throw new Error('当前引擎未声明追色批量/便携预设协议');
   const wait=waitBudget(action,payload);
   if((action==='cancel'||action==='workflow_cancel')&&typeof payload.session_id==='string'){
    const pending=sessions.get(payload.session_id);if(pending)await call('cancel',pending);
   }
   if(action==='state'||action==='preset_export_status'||action==='workflow_inspect'){
    for(const oldId of [...unreleased])await release(oldId);await reconcile();
   }
   if(mutations.has(action)&&(unresolved.size||unknownMutations.size))throw new Error('旧操作结果仍待明确核对，请先点击“核对当前结果”，不会重复提交');
   if(action==='preset_export_prepare'&&stagedExports.size)throw new Error('已有不可变待保存预设，请先核对、保存或明确释放');
   if(action==='preset_export_write'&&(unresolved.size||unknownExports.size))throw new Error('旧保存结果仍待精确文件核对，不会再次写入');
   const id=`semantic-${crypto.randomUUID()}`,body={...payload,action},pending={action,payload};let sent=false,seen=false;
   const session=(action==='capture'||prepares.has(action))&&typeof payload.session_id==='string'?payload.session_id:null;
   if(session)sessions.set(session,id);
   if(action==='preset_export_write'&&typeof payload.export_id==='string'&&typeof payload.path==='string')exportPaths.set(payload.export_id,payload.path);
   let previousProgress='';
   try{
    let raw:unknown=null;sent=true;
    try{raw=await call('request',id,body);}catch{/* Observe by ID, never resend. */}
    const end=Date.now()+wait;
    while(Date.now()<end){
     if(raw!==null){const reply=terminal(raw,id);if(reply){
       seen=true;consume(id,pending,reply);await release(id);
       if(!reply.success||reply.outcome_unknown)throw new Error(reply.error||'AI 追色未完成，请核对当前配方或文件');
       const result=reply.result&&typeof reply.result==='object'?reply.result as ObjectValue:null;
       if(result?.outcome_unknown===true)throw new Error(typeof result.error==='string'?result.error:'实际提交结果未知，必须核对后继续');
       if(action==='preset_export_status'&&typeof payload.export_id==='string'&&unknownExports.get(payload.export_id)===payload.path
          &&(result?.state==='matching'||result?.state==='missing'||result?.state==='different')){unknownExports.delete(payload.export_id);exportPaths.delete(payload.export_id);}
       if(action==='preset_export_status'&&typeof payload.export_id==='string'&&exportPaths.get(payload.export_id)===payload.path
          &&(result?.state==='matching'||result?.state==='missing'||result?.state==='different'))exportPaths.delete(payload.export_id);
       if(action==='preset_export_release'&&typeof payload.export_id==='string')unknownExports.delete(payload.export_id);
       if(action==='workflow_release')unknownExports.clear();
       if(action==='workflow_cancel'||action==='workflow_release')await reconcile();
       return reply.result;
      }
      const status=object(raw);if(status.phase==='unavailable')throw new Error('AI 追色回执不可查询，实际执行结果未知');if(status.phase!=='pending')throw new Error('AI 追色回执状态无效');
      if(session&&prepares.has(action)&&status.session_id===session&&status.progress){
       const value=object(status.progress),serial=JSON.stringify(value);
       if(serial.length<=4096&&serial!==previousProgress&&['reference_analysis','target_fit'].includes(String(value.stage))
          &&Number.isInteger(value.targets)&&Number(value.targets)>=0&&Number(value.targets)<=MAX_TARGETS){
        previousProgress=serial;for(const listener of progressListeners)listener(session,value as unknown as Progress);
       }
      }
     }
     await sleep(prepares.has(action)?350:150);try{raw=await call('status',id);}catch{raw=null;}
    }
    throw new Error('AI 追色最终回执超时，已请求停止；未确认结果不得重发');
   }catch(error){
    if(sent&&!seen){
     unresolved.set(id,pending);uncertain(id,pending);
     // A tombstone fences a native request that reaches admission after timeout.
     await call('cancel',id).catch(()=>undefined);
    }
    throw error;
   }finally{if(session&&sessions.get(session)===id)sessions.delete(session);}
  },
 };
 sharedPort=port;return port;
}
