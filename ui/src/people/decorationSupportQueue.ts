// SPDX-License-Identifier: GPL-3.0-or-later
/** Proof lifecycle only. The existing people queue owns requests and uncertainty. */
import type {PeopleAction,PeopleResult,PeopleView} from './model';
import {canonical} from '../faceDecoration/model';
import {isSupportAliasAction,supportAliasEchoMatches,validSupportAliasReview,verifySupportAliasReview,
 supportAliasAck,validSupportAliasConfirmation,supportAliasReceiptCurrent,supportAliasHistoryDigest,
 type SupportAliasReview} from '../faceDecoration/supportAliasModel';
import {registerSupportAliasReceipt,setSupportAliasWritePending} from '../faceDecoration/supportAliasHistoryRegistry';
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const draft=(review:SupportAliasReview)=>({region:review.region,reference_proof:review.reference_proof});
export function createDecorationSupportQueue(){
 let review:SupportAliasReview|null=null,captured:SupportAliasReview|null=null,previewView:PeopleView|null=null;
 return {
  prepare(command:PeopleAction,current:PeopleView|null){
   if(!isSupportAliasAction(command.action))return;
   captured=null;
   if(command.action==='face_decoration_support_alias_confirm'){
    if(!review||!validSupportAliasReview(review,current,draft(review))||command.payload.token!==review.token
      ||canonical(command.payload.ack)!==canonical(supportAliasAck(review)))throw Error('共享可见范围审核已失效，请重新查看全部照片，未提交修改。');
    captured=structuredClone(review);
   }
   if(command.action==='face_decoration_support_alias_preview'){review=null;previewView=structuredClone(current);}
  },
  sent(command:PeopleAction){if(command.action==='face_decoration_support_alias_confirm')setSupportAliasWritePending(command.request_id,true,command.document_epoch);},
  async validate(command:PeopleAction,result:PeopleResult,current:()=>PeopleView|null){
   if(!isSupportAliasAction(command.action))return;
   if(!supportAliasEchoMatches(command,result)||result.outcome_unknown||!result.success&&result.batch_id!=null)
    throw Error('共享可见范围原请求尚未获得准确终态，只能查询原请求。');
   if(!result.success){
    const failure=result as PeopleResult&{no_write?:unknown;rolled_back?:unknown;requires_reload?:unknown};
    if(typeof failure.no_write!=='boolean'||typeof failure.rolled_back!=='boolean'||failure.requires_reload!==false
      ||failure.no_write===failure.rolled_back||result.payload!==undefined||result.doc_state!==undefined)
      throw Error('共享可见范围失败回执未证明没有写入或完整补偿，只能查询原请求。');
   }
   if(command.action!=='face_decoration_support_alias_confirm'&&(result.batch_id!=null
     ||command.action==='face_decoration_support_alias_image'&&result.doc_state!==undefined))
    throw Error('共享可见范围只读审核不能发布修改或批次。');
   if(result.success&&command.action==='face_decoration_support_alias_preview'){
    const p=result.payload,next=result.doc_state?.people;
    if(!object(p)||p.kind!==command.action||!validSupportAliasReview(p.review,previewView,command.payload)
      ||!next||canonical(next.binding)!==canonical(previewView?.binding)
      ||canonical(next.editing_target)!==canonical(previewView?.editing_target)||next.revision!==previewView?.revision
      ||next.association_revision!==previewView?.association_revision
      ||canonical(next.face_decoration?.support_alias_review)!==canonical(p.review)
      ||!await verifySupportAliasReview(p.review))throw Error('共享可见范围审核与原始笔画、来源或完整成员不一致。');
    if(supportAliasReceiptCurrent(command,result,current())&&validSupportAliasReview(p.review,current(),command.payload))review=structuredClone(p.review);
   }
   if(result.success&&command.action==='face_decoration_support_alias_confirm'){
    if(!captured||!validSupportAliasConfirmation(captured,result))throw Error('共享可见范围确认缺少精确图像、支持资产或完整成员证明。');
    const digest=await supportAliasHistoryDigest(captured),terminal=result as unknown as Record<string,unknown>;
    const marker={version:1 as const,review_sha256:digest,member_count:captured.members.length};
    if(!object(result.payload)||result.payload.history_review_sha256!==digest
      ||canonical(terminal.face_decoration_support_alias_review)!==canonical(marker)
      ||canonical(terminal.alias_members)!==canonical(result.payload.alias_members)
      ||canonical(terminal.module_scope)!==canonical(['lnx.people_graph.v1'])
      ||!registerSupportAliasReceipt(command.document_epoch,result.batch_id!,marker))
      throw Error('共享可见范围受保护历史身份不一致，只能查询原请求。');
   }
  },
  complete(command:PeopleAction){
   if(command.action==='face_decoration_support_alias_confirm'){setSupportAliasWritePending(command.request_id,false);review=null;captured=null;}
   if(command.action==='face_decoration_support_alias_preview')previewView=null;
  },
  retire(){review=null;captured=null;previewView=null;},
  update(current:PeopleView|null){if(review&&!validSupportAliasReview(review,current,draft(review)))review=null;},
 };
}
