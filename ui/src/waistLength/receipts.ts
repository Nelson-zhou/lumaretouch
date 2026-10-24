// SPDX-License-Identifier: GPL-3.0-or-later
import type {Result} from './model';
import type {Reply} from './nativeTransport';
/** Saved intent is not an applied effect. Both receipt and canonical publication
 * must prove the same outcome; missing fields never silently become success. */
export function confirmedPublication(receipt:Result):boolean{
 const publication=receipt.view?.publication;
 if(receipt.phase!=='done'||receipt.success!==true||receipt.outcome_unknown!==false||typeof receipt.rendered!=='boolean'||!publication)return false;
 if(receipt.rendered?receipt.unapplied_reason!==null:typeof receipt.unapplied_reason!=='string'||receipt.unapplied_reason.length===0||receipt.unapplied_reason.length>8192)return false;
 return publication.request_id===receipt.request_id&&publication.rendered===receipt.rendered&&publication.unapplied_reason===receipt.unapplied_reason;
}
/** A failed read-only lookup says nothing about whether the original write ran. */
export function innerReceipt(reply:Reply,id:string):Result{
 const receipt=reply.result?.receipt;
 if(receipt?.request_id===id){
  if(receipt.phase==='done'&&typeof receipt.success==='boolean'&&typeof receipt.outcome_unknown==='boolean'){
   if(receipt.success&&!confirmedPublication(receipt))return {phase:'pending',request_id:id,outcome_unknown:true,error:'成功回执缺少一致的实际发布结果，仍待核对；不会重发或声称效果已应用。'};
   return receipt;
  }
  if(receipt.phase==='pending'||receipt.phase==='unavailable')return {...receipt,outcome_unknown:true};
 }
 // Only a confirmed rejection of the original edit is negative execution proof.
 if(!receipt&&reply.action==='edit'&&reply.success===false&&reply.outcome_unknown===false)
  return {phase:'done',request_id:id,success:false,outcome_unknown:false,error:reply.error??'腰部长度修改未提交。'};
 return {phase:'pending',request_id:id,outcome_unknown:true,error:reply.error??reply.result?.view_error??'原修改回执缺失或不匹配，结果仍待确认；不会重新提交。'};
}
