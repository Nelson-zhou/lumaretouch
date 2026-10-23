// SPDX-License-Identifier: GPL-3.0-or-later
import {runArmShape} from '../native';
import type {ArmView,Binding,BodyRef,Result,ProposalResult} from './model';
import type {SourcePreview as SourcePayload} from '../legShape/sourcePreview';
export type BackendAction='view'|'select'|'execute'|'status'|'proposal_start'|'proposal_status'|'proposal_cancel';
export type Command={action:BackendAction;request_id:string;request:Record<string,unknown>};
export type Payload={view?:ArmView;source_preview?:SourcePayload;receipt?:Result;proposal?:ProposalResult};
export type Reply={event:'arm_shape_result';protocol:1;action:BackendAction;request_id:string;success:boolean;outcome_unknown:boolean;error?:string;result?:Payload};
export type Mailbox={phase:'pending'|'done'|'unavailable';request_id:string;result?:Reply;error?:string;outcome_unknown?:boolean};
const delay=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function deadline<T>(promise:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('手臂通信结果未确认，请查询原请求，不会重复提交。')),10000);promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
function terminal(mail:Mailbox,id:string):Reply|null{
 if(mail.request_id!==id)throw Error('手臂回执身份不一致');
 if(mail.phase==='unavailable')throw Error(mail.error??'原回执不可查询，不能认定操作未执行');
 if(mail.phase==='pending')return null;
 const value=mail.result;
 if(mail.phase!=='done'||!value||value.event!=='arm_shape_result'||value.protocol!==1||value.request_id!==id||typeof value.success!=='boolean'||typeof value.outcome_unknown!=='boolean')throw Error('手臂回执协议无效');
 return value;
}
/** The native mailbox accepts once. All recovery queries retain the original ID. */
export function createArmPort(){
 const retained=new Map<string,Reply>();
 const status=async(id:string)=>{const cached=retained.get(id);if(cached)return cached;const reply=terminal(await deadline(runArmShape({action:'mailbox_status',request_id:id})),id);if(reply)retained.set(id,reply);return reply;};
 return {
  async send(wire:Command):Promise<Reply>{
   let first:Mailbox|null=null;
   try{first=await deadline(runArmShape(wire));}catch{/* A lost acceptance is never re-enqueued. */}
   const until=Date.now()+25000;
   while(Date.now()<until){const reply=first?terminal(first,wire.request_id):await status(wire.request_id);first=null;if(reply){if(reply.action!==wire.action)throw Error('手臂回执操作不一致');retained.set(wire.request_id,reply);return reply;}await delay(150);}
   throw Error('手臂结果仍待确认，请查询原请求。');
  },status,
  async release(id:string){retained.delete(id);try{await deadline(runArmShape({action:'release',request_id:id}));}catch{/* Cleanup failure never resends a mutation. */}},
 };
}
export function command(action:BackendAction,request:Record<string,unknown>):Command{return {action,request_id:`arm-${crypto.randomUUID()}`,request};}
export function boundCommand(action:'view'|'select',binding:Binding,body_ref?:BodyRef):Command{return command(action,action==='view'?{}:{binding,...(body_ref?{body_ref}: {})});}
export function innerReceipt(reply:Reply,id:string):Result{
 if(reply.action!=='execute'&&reply.action!=='status')return {phase:'pending',request_id:id,outcome_unknown:true,error:'原修改回执操作不匹配。'};
 const result=reply.result?.receipt;
 if(result?.request_id===id){
  if(result.phase==='done'&&typeof result.success==='boolean'&&typeof result.outcome_unknown==='boolean')return result;
  if(result.phase==='pending'||result.phase==='unavailable')return {...result,outcome_unknown:true};
 }
 if(reply.action==='execute'&&!reply.success&&!reply.outcome_unknown)return {phase:'done',request_id:id,success:false,outcome_unknown:false,error:reply.error??'手臂调整未提交。'};
 return {phase:'pending',request_id:id,outcome_unknown:true,error:reply.error??'原修改回执缺失或不匹配，不会重新提交。'};
}
