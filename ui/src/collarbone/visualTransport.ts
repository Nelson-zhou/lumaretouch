// SPDX-License-Identifier: GPL-3.0-or-later
import type {SpillImage} from '../spillRemoval/model';
import {verifyCollarboneImage,validCollarboneImageMetadata,type CollarboneImage} from './transferModel';
export type CollarboneImageRequest={preflightToken:string;documentId:string;revision:string;side:'before'|'after';sha256:string;requestId:string};
export type CollarboneImageReply={request_id:string;action:'collarbone_visual';success:boolean;outcome_unknown?:boolean;error?:string;preflight_token:string;document_id:string;revision:string;side:'before'|'after';sha256:string;image:SpillImage};
export type CollarboneImageTransport={request:(value:CollarboneImageRequest)=>Promise<{requested:boolean}>;read:(id:string)=>Promise<{phase:string;request_id:string;result?:CollarboneImageReply;error?:string}>};
/** A bounded read only. Never retries a mutation or substitutes a newer token. */
export async function fetchCollarboneImage(api:CollarboneImageTransport,request:CollarboneImageRequest,expected:CollarboneImage,live:()=>boolean=()=>true):Promise<SpillImage>{
 if(!validCollarboneImageMetadata(expected)||request.sha256!==expected.sha256||!['before','after'].includes(request.side))throw Error('读取请求与冻结图像元数据不一致');
 const deadline=Date.now()+30000;
 async function bounded<T>(promise:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('读取审核图像超时，请重新读取本目标。')),Math.max(1,deadline-Date.now()));promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
 const accepted=await bounded(api.request(request));if(!accepted.requested)throw Error('审核图像读取未确认入队');
 while(live()){
  const response=await bounded(api.read(request.requestId));if(!live())throw Error('审核图像请求已失效');
  if(response.request_id!==request.requestId)throw Error('审核图像请求身份不匹配');
  if(response.phase==='done'){
   const r=response.result;
   if(!r||r.request_id!==request.requestId||r.action!=='collarbone_visual'||r.success!==true||r.outcome_unknown===true||r.preflight_token!==request.preflightToken
      ||r.document_id!==request.documentId||r.revision!==request.revision||r.side!==request.side||r.sha256!==request.sha256
      ||!r.image||r.image.mime!==expected.mime||r.image.width!==expected.width||r.image.height!==expected.height||r.image.sha256!==expected.sha256
      ||!await verifyCollarboneImage(r.image))throw Error(r?.error||'审核图像不属于本次冻结目标，或 PNG 内容未通过校验');
   return r.image;
  }
  if(response.phase!=='pending'||Date.now()>=deadline)throw Error(response.error||'审核图像暂不可读取；请保留当前审核并重试读取。');
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('审核图像请求已失效');
}
