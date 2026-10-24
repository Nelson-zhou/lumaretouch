// SPDX-License-Identifier: GPL-3.0-or-later
import {runTorsoLength} from '../native';
import type {Binding,BodyRef,Result,TorsoLengthView} from './model';
import type {SourcePreview} from './sourcePreview';
export type {SourcePreview} from './sourcePreview';
export type BackendAction='view'|'select'|'status'|'edit';
export type Command={action:BackendAction;request_id:string;request:Record<string,unknown>};
export type Payload={view?:TorsoLengthView;view_error?:string;source_preview?:SourcePreview;receipt?:Result};
export type Reply={event:'torso_length_result';protocol:1;action:BackendAction;request_id:string;success:boolean;outcome_unknown:boolean;error?:string;result?:Payload};
export type Mailbox={phase:'pending'|'done'|'unavailable';request_id:string;result?:Reply;error?:string;outcome_unknown?:boolean};
const delay=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function deadline<T>(promise:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('上身长度通信尚未确认，请查询原请求，不会重复提交。')),10000);promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
function terminal(mail:Mailbox,id:string):Reply|null{
 if(mail.request_id!==id)throw Error('上身长度回执身份不一致');
 if(mail.phase==='unavailable')throw Error(mail.error??'上身长度回执不可查询，不能据此认定没有执行');
 if(mail.phase==='pending')return null;
 const value=mail.result;
 if(mail.phase!=='done'||!value||value.event!=='torso_length_result'||value.protocol!==1||value.request_id!==id||typeof value.success!=='boolean'||typeof value.outcome_unknown!=='boolean')throw Error('上身长度回执协议无效');
 return value;
}
/** Timeout retains the original identity. A mutation is never re-enqueued. */
export function createTorsoLengthPort(){
 const retained=new Map<string,Reply>();
 const status=async(id:string)=>{const cached=retained.get(id);if(cached)return cached;const reply=terminal(await deadline(runTorsoLength({action:'mailbox_status',request_id:id})),id);if(reply)retained.set(id,reply);return reply;};
 return {
  async send(command:Command):Promise<Reply>{
   let first:Mailbox|null=null;
   try{first=await deadline(runTorsoLength(command));}catch{/* Lost acceptance is reconciled by ID only. */}
   const until=Date.now()+25000;
   while(Date.now()<until){const reply=first?terminal(first,command.request_id):await status(command.request_id);first=null;if(reply){if(reply.action!==command.action)throw Error('上身长度回执动作不匹配');retained.set(command.request_id,reply);return reply;}await delay(150);}
   throw Error('上身长度结果仍待确认，请查询本次请求，不要重新提交。');
  },
  status,
  async release(id:string){retained.delete(id);try{await deadline(runTorsoLength({action:'release',request_id:id}));}catch{/* Optional terminal cleanup never repeats an edit. */}},
 };
}
export function command(action:BackendAction,request:Record<string,unknown>):Command{return {action,request_id:`torso-length-${crypto.randomUUID()}`,request};}
export function boundCommand(action:'view'|'select',binding:Binding,body_ref?:BodyRef):Command{return command(action,action==='view'?{}:{binding,...(body_ref?{body_ref}:{})});}
