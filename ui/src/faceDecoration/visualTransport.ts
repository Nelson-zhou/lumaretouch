// SPDX-License-Identifier: GPL-3.0-or-later
import type {SpillImage} from '../spillRemoval/model';
import {validCollarboneImageMetadata,verifyCollarboneImage,type CollarboneImage} from '../collarbone/transferModel';
export type DecorationImageRequest={id?:string;documentId:string;preflightToken:string;revision:string;side:'before'|'after';sha256:string;requestId:string};
export type DecorationImageReply={protocol?:number;request_id:string;action:'face_decoration_visual'|'face_decoration_cohort_visual';success:boolean;outcome_unknown?:boolean;error?:string;id?:string;document_id:string;preflight_token:string;revision:string;side:'before'|'after';sha256:string;image:SpillImage};
export type DecorationImageTransport={request:(v:DecorationImageRequest)=>Promise<{requested:boolean}>;read:(id:string)=>Promise<{phase:string;request_id:string;result?:DecorationImageReply;error?:string}>};
export async function fetchDecorationImage(api:DecorationImageTransport,request:DecorationImageRequest,expected:CollarboneImage,live:()=>boolean,action:'face_decoration_visual'|'face_decoration_cohort_visual'='face_decoration_visual'):Promise<SpillImage>{
 if(!validCollarboneImageMetadata(expected)||request.sha256!==expected.sha256)throw Error('装饰审核图像元数据不匹配');
 const deadline=Date.now()+30000;
 function bounded<T>(promise:Promise<T>):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('审核图像读取超时，可重试只读获取。')),Math.max(1,deadline-Date.now()));promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
 if(!(await bounded(api.request(request))).requested)throw Error('图像读取未确认入队');
 while(live()){
  const response=await bounded(api.read(request.requestId));if(!live())throw Error('审核目标已变化');
  if(response.request_id!==request.requestId)throw Error('图像请求身份不一致');
  if(response.phase==='done'){
   const r=response.result;
   if(!r||(request.id!==undefined?r.protocol!==1||r.outcome_unknown!==false:(r.protocol!==undefined&&r.protocol!==1)||r.outcome_unknown===true)||r.action!==action||r.request_id!==request.requestId||r.success!==true||r.id!==request.id||r.document_id!==request.documentId||r.preflight_token!==request.preflightToken||r.revision!==request.revision||r.side!==request.side||r.sha256!==request.sha256||!r.image||r.image.width!==expected.width||r.image.height!==expected.height||r.image.sha256!==expected.sha256||!await verifyCollarboneImage(r.image))throw Error(r?.error||'完整图像内容或冻结身份不匹配');
   return r.image;
  }
  if(response.phase!=='pending'||Date.now()>=deadline)throw Error(response.error||'图像尚不可读，请重试只读读取');
  await new Promise(resolve=>setTimeout(resolve,100));
 }
 throw Error('审核图像读取已失效');
}
