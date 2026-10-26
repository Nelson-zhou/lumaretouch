/** One portrait receipt owner survives panel unmounts; status is read-only and never resends. */
import {useSyncExternalStore} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {validRequest,validControls,validRevision,sameControls,sameRequest} from './model';
import type {ProtectionReport,ProtectionRequest,ProtectionControls} from './model';
type State = {pending:ProtectionRequest|null;busy:boolean;message:string;recoveryAvailable:boolean;storageBlocked:boolean};
const storageKey='lrt.portrait-protection.pending.v1';
let storageBlocked=false;
function restored():ProtectionRequest|null {try{const raw=sessionStorage.getItem(storageKey);if(!raw)return null;const r:unknown=JSON.parse(raw);if(validRequest(r))return r;storageBlocked=true;return null;}catch{storageBlocked=true;return null;}}
const pending=restored();
let state:State={pending,busy:false,message:storageBlocked?'原操作存储不可用；不能证明未发送，禁止新操作。请保存已确认状态并重启应用、重新打开已确认工程。':'',recoveryAvailable:false,storageBlocked};
const listeners=new Set<()=>void>();
function update(next:Partial<State>){state={...state,...next};listeners.forEach(fn=>fn());}
export function useProtectionOperation(){return useSyncExternalStore(fn=>{listeners.add(fn);return()=>{listeners.delete(fn);};},()=>state);}
export function showProtectionMessage(message:string){update({message});}
const deadline=<T,>(promise:Promise<T>):Promise<T>=>{let timer:ReturnType<typeof setTimeout>;return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('人像保护结果未确认；只能查询原操作，不会重发')),12000);})]).finally(()=>clearTimeout(timer));};
function accept(raw:unknown,request:ProtectionRequest):boolean {
  if(!raw||typeof raw!=='object')throw Error('人像保护回执不可用；请查询原操作');
  const r=raw as Record<string,unknown>;
  const original=r.original_request;
  if(r.event!=='portrait_protection_result'||r.protocol!==1||r.request_id!==request.request_id||!validRequest(original)
    ||!sameRequest(original,request)||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean')throw Error('人像保护回执身份不匹配；旧结果未覆盖当前照片');
  if(r.outcome_unknown||r.requires_reload||r.phase==='unknown')throw Error(String(r.error??'人像保护事务未确认；请查询原操作或重新载入已确认的工程'));
  if(r.success){
    const before=BigInt(request.revision), after=r.result_revision;
    if(!['applied','no_change'].includes(String(r.phase))||!validRevision(after)
      ||BigInt(after)!==before+(r.phase==='applied'?1n:0n)||!validControls(r.spec)||!sameControls(r.spec,request.controls))throw Error('人像保护提交证明无效；请查询原操作');
  }else if(!['rejected','rolled_back','not_sent'].includes(String(r.phase))||typeof r.error!=='string'||(r.phase==='not_sent'&&r.authority!=='native-admission'))throw Error('人像保护失败回执无效；请查询原操作');
  // Do not unlock merely because a frame happens to look like the desired state.
  sessionStorage.removeItem(storageKey);
  update({pending:null,recoveryAvailable:false,message:r.success?(r.frame_delivery_unknown?'人像保护已提交，画面传递未确认，请刷新状态':'人像保护已提交'):String(r.error)});
  return r.success;
}
async function queryOnce(request:ProtectionRequest):Promise<boolean|null>{
  const raw=await deadline(invoke<{request_id:string;phase:string;result:unknown;reason?:string;recovery_available?:boolean;recovery_hint?:string}>('portrait_protection_status',{request}));
  if(raw.request_id!==request.request_id)throw Error('人像保护查询身份不匹配');
  update({recoveryAvailable:raw.recovery_available===true});
  if(raw.phase==='abandoned'){acceptAbandoned(raw,request);return false;}
  if(raw.phase==='done'){try{return accept(raw.result,request);}catch(e){throw Error(`${String(e)} ${raw.recovery_hint??''}`);}}
  if(raw.phase==='unknown')throw Error(raw.reason??'人像保护回执未知；保留原请求，只能查询，不会重发');
  if(raw.phase!=='pending')throw Error('人像保护查询状态无效');
  update({message:`人像保护仍在等待终态；请查询原操作，不会重发。 ${raw.recovery_hint??''}`});
  return null;
}
export async function queryProtection():Promise<boolean>{
  const r=state.pending;if(!r||state.busy)return false;update({busy:true});
  try{const answer=await queryOnce(r);return answer===true;}
  catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
export async function submitProtection(report:ProtectionReport,controls:ProtectionControls):Promise<boolean>{
  if(state.busy||state.pending||state.storageBlocked)return false;
  const request:ProtectionRequest={cmd:'portrait_protection',request_id:crypto.randomUUID(),document_id:report.document_id,revision:report.revision,controls:structuredClone(controls)};
  if(!validRequest(request)){update({message:'当前人像保护照片/版本绑定无效；未发送，请刷新状态'});return false;}
  try{sessionStorage.setItem(storageKey,JSON.stringify(request));}catch{update({message:'无法保存人像保护请求身份；未发送'});return false;}
  update({pending:request,busy:true,recoveryAvailable:false,message:'已请求人像保护，等待准确提交回执；不会自动重试'});
  try{
    notifyInspectionEditIntent();
    const ack=await deadline(invoke<{requested:boolean;request_id:string;phase?:string;result?:unknown}>('portrait_protection',{request}));
    if(ack.request_id!==request.request_id||typeof ack.requested!=='boolean')throw Error('人像保护原生入队回执无效；请查询原操作');
    if(ack.phase==='done'&&ack.requested===false)return accept(ack.result,request); // Proved native not_sent, not an ACK.
    if(ack.requested!==true)throw Error('人像保护入队结果未确认；请查询原操作');
    // requested:true remains an ACK only, never success.
    const end=Date.now()+10000;
    while(Date.now()<end){const answer=await queryOnce(request);if(answer!==null)return answer;await new Promise(r=>setTimeout(r,100));}
    throw Error('人像保护回执等待超时；原请求保留，请查询，不会自动重发');
  }catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}

function acceptAbandoned(raw:unknown,request:ProtectionRequest){
  if(!raw||typeof raw!=='object')throw Error('工作区恢复证明不可用');
  const r=raw as Record<string,unknown>, original=r.original_request;
  if(r.phase!=='abandoned'||r.request_id!==request.request_id||r.previous_outcome!=='unknown'
    ||!validRequest(original)||!sameRequest(original,request))throw Error('工作区恢复原请求不匹配');
  sessionStorage.removeItem(storageKey);
  update({pending:null,recoveryAvailable:false,message:'已按新引擎/已验证重新打开的工程放弃旧等待；旧结果仍未知，没有重发。现在可明确提交新的人像保护。'});
}
export async function abandonProtection():Promise<boolean>{
  const request=state.pending;if(!request||state.busy||!state.recoveryAvailable)return false;
  update({busy:true});
  try{acceptAbandoned(await deadline(invoke('portrait_protection_abandon',{request})),request);return true;}
  catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
