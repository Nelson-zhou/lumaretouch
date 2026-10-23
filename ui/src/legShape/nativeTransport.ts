// SPDX-License-Identifier: GPL-3.0-or-later
import {runLegShape} from '../native';
import type {Binding, BodyRef, Result, LegView} from './model';
import type {SourcePreview} from './sourcePreview';
export type {SourcePreview} from './sourcePreview';
export type ModelStatus = {installed:boolean;state:string;reason?:string;download_bytes:number|null;pin_status:string;license?:string};
export type BackendAction='view'|'select'|'analyse'|'reanalyse'|'status'|'edit';
export type Command = {action:BackendAction;request_id:string;request:Record<string,unknown>};
export type Payload = {view?:LegView;model?:ModelStatus;view_error?:string;source_preview?:SourcePreview;receipt?:Result;analysis_candidates?:{run_id:string;bodies:import('./model').BodyChoice[]}};
export type Reply = {event:'leg_shape_result';protocol:1;action:BackendAction;request_id:string;success:boolean;outcome_unknown:boolean;error?:string;result?:Payload};
export type Mailbox = {phase:'pending'|'done'|'unavailable';request_id:string;result?:Reply;error?:string;outcome_unknown?:boolean};
const delay=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function deadline<T>(promise:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('腿部通信未确认，请查询原请求，不会重复提交。')),10000);promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});});}
function terminal(mail:Mailbox,id:string):Reply|null{
 if(mail.request_id!==id)throw Error('腿部回执身份不一致');
 if(mail.phase==='unavailable')throw Error(mail.error??'腿部回执不可查询，不能据此认定没有执行');
 if(mail.phase==='pending')return null;
 const value=mail.result;
 if(mail.phase!=='done'||!value||value.protocol!==1||value.request_id!==id||typeof value.success!=='boolean'||typeof value.outcome_unknown!=='boolean')throw Error('腿部回执协议无效');
 return value;
}
/** Query by the original identity after timeout. Never retry a mutation. */
export function createLegPort(){
 const retained=new Map<string,Reply>();
 const status=async(id:string)=>{const cached=retained.get(id);if(cached)return cached;const reply=terminal(await deadline(runLegShape({action:'mailbox_status',request_id:id})),id);if(reply)retained.set(id,reply);return reply;};
 return {
  async send(command:Command):Promise<Reply>{
   let first:Mailbox|null=null;
   try{first=await deadline(runLegShape(command));}catch{/* A lost acceptance is reconciled by ID, never re-enqueued. */}
   const until=Date.now()+(command.action==='analyse'?180000:25000);
   while(Date.now()<until){const reply=first?terminal(first,command.request_id):await status(command.request_id);first=null;if(reply){retained.set(command.request_id,reply);return reply;}await delay(150);}
   throw Error('腿部结果仍待确认，请查询本次请求，不要重新提交。');
  },
  status,
  async release(id:string){retained.delete(id);try{await deadline(runLegShape({action:'release',request_id:id}));}catch{/* Terminal cleanup is optional; never resend the original edit. */}},
 };
}
export function command(action:BackendAction,request:Record<string,unknown>):Command{return {action,request_id:`leg-${crypto.randomUUID()}`,request};}
export function boundCommand(action:'view'|'select'|'analyse',binding:Binding,body_ref?:BodyRef):Command{
 return command(action,action==='view'?{}:{binding,...(body_ref?{body_ref}: {})});
}
