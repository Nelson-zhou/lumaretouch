/** One receipt owner shared by crop dialog and spec controls, surviving unmounts. */
import {useSyncExternalStore} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import type {FlipReport} from './model';
export type FlipRequest = {cmd:'final_canvas_flip';request_id:string;document_id:string;revision:string;horizontal:boolean;vertical:boolean};
type State = {pending:FlipRequest|null;busy:boolean;message:string;recoveryAvailable:boolean};
const storageKey='lrt.final-canvas-flip.pending.v1';
const fields=['cmd','request_id','document_id','revision','horizontal','vertical'] as const;
function validRequest(value:unknown):value is FlipRequest {
  if(!value||typeof value!=='object')return false;
  const r=value as FlipRequest;
  return Object.keys(r).length===fields.length&&fields.every(k=>Object.hasOwn(r,k))&&r.cmd==='final_canvas_flip'
    &&typeof r.request_id==='string'&&r.request_id.length>0&&r.request_id.length<=128
    &&typeof r.document_id==='string'&&r.document_id!=='0'&&/^[A-Za-z0-9_-]{1,128}$/.test(r.document_id)
    &&typeof r.revision==='string'&&r.revision.length<=20&&/^(0|[1-9][0-9]*)$/.test(r.revision)&&BigInt(r.revision)<=18446744073709551615n
    &&typeof r.horizontal==='boolean'&&typeof r.vertical==='boolean';
}
function restored():FlipRequest|null {try{const raw=sessionStorage.getItem(storageKey);if(!raw)return null;const r:unknown=JSON.parse(raw);return validRequest(r)?r:null;}catch{return null;}}
let state:State={pending:restored(),busy:false,message:'',recoveryAvailable:false};
const listeners=new Set<()=>void>();
function update(next:Partial<State>){state={...state,...next};listeners.forEach(fn=>fn());}
export function useFlipOperation(){return useSyncExternalStore(fn=>{listeners.add(fn);return()=>{listeners.delete(fn);};},()=>state);}
export function showFlipMessage(message:string){update({message});}
const deadline=<T,>(promise:Promise<T>):Promise<T>=>{let timer:ReturnType<typeof setTimeout>;return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('翻转结果未确认；只能查询原操作，不会重发')),12000);})]).finally(()=>clearTimeout(timer));};
function accept(raw:unknown,request:FlipRequest):boolean {
  if(!raw||typeof raw!=='object')throw Error('翻转回执不可用；请查询原操作');
  const r=raw as Record<string,unknown>;
  const original=r.original_request;
  if(r.event!=='final_canvas_flip_result'||r.protocol!==1||r.request_id!==request.request_id||!validRequest(original)
    ||!fields.every(k=>original[k]===request[k])||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean'||typeof r.requires_reload!=='boolean')throw Error('翻转回执身份不匹配；旧结果未覆盖当前照片');
  if(r.outcome_unknown||r.requires_reload||r.phase==='unknown')throw Error(String(r.error??'翻转事务未确认；请查询原操作或重新载入已确认的工程'));
  if(r.success){
    const spec=r.spec as {horizontal?:unknown;vertical?:unknown}|undefined;
    const before=BigInt(request.revision), after=r.result_revision;
    if(!['applied','no_change'].includes(String(r.phase))||typeof after!=='string'||!/^(0|[1-9][0-9]*)$/.test(after)
      ||BigInt(after)!==before+(r.phase==='applied'?1n:0n)||!spec||Object.keys(spec).length!==2||spec.horizontal!==request.horizontal||spec.vertical!==request.vertical)throw Error('翻转提交证明无效；请查询原操作');
  }else if(!['rejected','rolled_back','not_sent'].includes(String(r.phase))||typeof r.error!=='string'||(r.phase==='not_sent'&&r.authority!=='native-admission'))throw Error('翻转失败回执无效；请查询原操作');
  // Do not unlock merely because a frame happens to look like the desired state.
  sessionStorage.removeItem(storageKey);
  update({pending:null,recoveryAvailable:false,message:r.success?(r.frame_delivery_unknown?'翻转已提交，画面传递未确认，请刷新状态':'翻转已提交'):String(r.error)});
  return r.success;
}
async function queryOnce(request:FlipRequest):Promise<boolean|null>{
  const raw=await deadline(invoke<{request_id:string;phase:string;result:unknown;reason?:string;recovery_available?:boolean;recovery_hint?:string}>('final_canvas_flip_status',{request}));
  if(raw.request_id!==request.request_id)throw Error('翻转查询身份不匹配');
  update({recoveryAvailable:raw.recovery_available===true});
  if(raw.phase==='abandoned'){acceptAbandoned(raw,request);return false;}
  if(raw.phase==='done'){try{return accept(raw.result,request);}catch(e){throw Error(`${String(e)} ${raw.recovery_hint??''}`);}}
  if(raw.phase==='unknown')throw Error(raw.reason??'翻转回执未知；保留原请求，只能查询，不会重发');
  if(raw.phase!=='pending')throw Error('翻转查询状态无效');
  update({message:`翻转仍在等待终态；请查询原操作，不会重发。 ${raw.recovery_hint??''}`});
  return null;
}
export async function queryFlip():Promise<boolean>{
  const r=state.pending;if(!r||state.busy)return false;update({busy:true});
  try{const answer=await queryOnce(r);return answer===true;}
  catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
export async function submitFlip(report:FlipReport,horizontal:boolean,vertical:boolean):Promise<boolean>{
  if(state.busy||state.pending)return false;
  const request:FlipRequest={cmd:'final_canvas_flip',request_id:crypto.randomUUID(),document_id:report.document_id,revision:report.revision,horizontal,vertical};
  if(!validRequest(request)){update({message:'当前翻转照片/版本绑定无效；未发送，请刷新状态'});return false;}
  try{sessionStorage.setItem(storageKey,JSON.stringify(request));}catch{update({message:'无法保存翻转请求身份；未发送'});return false;}
  update({pending:request,busy:true,recoveryAvailable:false,message:'已请求翻转，等待准确提交回执；不会自动重试'});
  try{
    notifyInspectionEditIntent();
    const ack=await deadline(invoke<{requested:boolean;request_id:string;phase?:string;result?:unknown}>('final_canvas_flip',{request}));
    if(ack.request_id!==request.request_id||typeof ack.requested!=='boolean')throw Error('翻转原生入队回执无效；请查询原操作');
    if(ack.phase==='done'&&ack.requested===false)return accept(ack.result,request); // Proved native not_sent, not an ACK.
    if(ack.requested!==true)throw Error('翻转入队结果未确认；请查询原操作');
    // requested:true remains an ACK only, never success.
    const end=Date.now()+10000;
    while(Date.now()<end){const answer=await queryOnce(request);if(answer!==null)return answer;await new Promise(r=>setTimeout(r,100));}
    throw Error('翻转回执等待超时；原请求保留，请查询，不会自动重发');
  }catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}

function acceptAbandoned(raw:unknown,request:FlipRequest){
  if(!raw||typeof raw!=='object')throw Error('工作区恢复证明不可用');
  const r=raw as Record<string,unknown>, original=r.original_request;
  if(r.phase!=='abandoned'||r.request_id!==request.request_id||r.previous_outcome!=='unknown'
    ||!validRequest(original)||!fields.every(k=>original[k]===request[k]))throw Error('工作区恢复原请求不匹配');
  sessionStorage.removeItem(storageKey);
  update({pending:null,recoveryAvailable:false,message:'已按新引擎/已验证重新打开的工程放弃旧等待；旧结果仍未知，没有重发。现在可明确提交新的翻转。'});
}
export async function abandonFlip():Promise<boolean>{
  const request=state.pending;if(!request||state.busy||!state.recoveryAvailable)return false;
  update({busy:true});
  try{acceptAbandoned(await deadline(invoke('final_canvas_flip_abandon',{request})),request);return true;}
  catch(e){update({message:String(e)});return false;}finally{update({busy:false});}
}
