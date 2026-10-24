// SPDX-License-Identifier: GPL-3.0-or-later
import type {Result} from './model';
import type {Reply} from './nativeTransport';
/** A failed read-only lookup says nothing about whether the original write ran. */
export function innerReceipt(reply:Reply,id:string):Result{
 const receipt=reply.result?.receipt;
 if(receipt?.request_id===id){
  if(receipt.phase==='done'&&typeof receipt.success==='boolean'&&typeof receipt.outcome_unknown==='boolean')return receipt;
  if(receipt.phase==='pending'||receipt.phase==='unavailable')return {...receipt,outcome_unknown:true};
 }
 // Only a confirmed rejection of the original edit is negative execution proof.
 if(reply.action==='edit'&&reply.success===false&&reply.outcome_unknown===false)
  return {phase:'done',request_id:id,success:false,outcome_unknown:false,error:reply.error??'上身长度修改未提交。'};
 return {phase:'pending',request_id:id,outcome_unknown:true,error:reply.error??reply.result?.view_error??'原修改回执缺失或不匹配，结果仍待确认；不会重新提交。'};
}
