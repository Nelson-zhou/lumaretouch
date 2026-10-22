import {invoke} from '@tauri-apps/api/core';
import type {Port} from './model';
type ObjectValue=Record<string,unknown>;
type Reply={protocol:1;request_id:string;success:boolean;outcome_unknown:boolean;committed?:boolean|null;result?:unknown;error?:string;action:'request'};
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));
function object(value:unknown):ObjectValue{if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('AI 追色回执格式无效');return value as ObjectValue;}
function deadline<T>(promise:Promise<T>,ms=10_000):Promise<T>{return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('AI 追色本机通信未确认，不能认定未执行')),ms);promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
function terminal(value:unknown,id:string):Reply|null{
 const outer=object(value);if(outer.request_id!==id)throw new Error('AI 追色回执身份不匹配');if(outer.phase!=='done')return null;
 const reply=object(outer.result) as unknown as Reply;
 if(reply.protocol!==1||reply.request_id!==id||reply.action!=='request'||typeof reply.success!=='boolean'||typeof reply.outcome_unknown!=='boolean')throw new Error('AI 追色回执协议无效');return reply;
}
/** No automatic mutation retry. Terminal receipts are consumed then explicitly released. */
export function createNativeSemanticColour(canUse:()=>boolean):Port{
 const captures=new Map<string,string>(),unresolved=new Set<string>(),unreleased=new Set<string>();
 const call=(action:string,id:string,request?:ObjectValue)=>deadline(invoke<unknown>('semantic_colour',{request:{action,request_id:id,...(request?{request}:{})}}));
 const release=async(id:string)=>{unreleased.add(id);try{const reply=object(await call('release',id));if(reply.released===true)unreleased.delete(id);}catch{/* Retry only idempotent receipt cleanup, never the original command. */}};
 async function reconcile(){
  for(const id of [...unresolved]){
   const stopped=await call('cancel',id);let receipt=terminal(stopped,id);
   if(!receipt){const status=await call('status',id);receipt=terminal(status,id);}
   if(!receipt)throw new Error('上一操作尚未确认结束，当前配方不能作为最终结果；稍后刷新，不要重发应用');
   await release(id);unresolved.delete(id);
  }
 }
 return {async request(action,payload){
  if(!canUse())throw new Error('当前引擎未声明 AI 语义追色协议，请启动配套引擎');
  if(action==='cancel'&&typeof payload.session_id==='string'){
   const pending=captures.get(payload.session_id);if(pending)await call('cancel',pending);
  }
  if(action==='state'){for(const oldId of [...unreleased])await release(oldId);await reconcile();}
  else if((action==='commit'||action==='edit')&&unresolved.size)throw new Error('旧操作结果仍待核对，先刷新，不会重复提交');
  const id=`semantic-${crypto.randomUUID()}`,body={action,...payload};let sent=false,seen=false;
  const session=action==='capture'&&typeof payload.session_id==='string'?payload.session_id:null;
  if(session)captures.set(session,id);
  try{
   let raw:unknown=null;sent=true;
   try{raw=await call('request',id,body);}catch{/* Reconcile by ID, never resend. */}
   const end=Date.now()+(action==='capture'?180_000:60_000);
   while(Date.now()<end){
    if(raw!==null){const reply=terminal(raw,id);if(reply){seen=true;await release(id);if(!reply.success||reply.outcome_unknown)throw new Error(reply.error||'AI 追色未完成，请核对当前配方');return reply.result;}
     const status=object(raw);if(status.phase==='unavailable')throw new Error('AI 追色回执不可查询，实际执行结果未知');if(status.phase!=='pending')throw new Error('AI 追色回执状态无效');}
    await sleep(150);try{raw=await call('status',id);}catch{raw=null;}
   }
   throw new Error('AI 追色最终回执超时，已请求停止；未确认结果不得重发');
  }catch(error){
   if(sent&&!seen){
    unresolved.add(id);
    // Cancelling an unseen native request creates a tombstone, fencing late admission.
    await call('cancel',id).catch(()=>undefined);
   }
   throw error;
  }finally{if(session&&captures.get(session)===id)captures.delete(session);}
 }};
}
