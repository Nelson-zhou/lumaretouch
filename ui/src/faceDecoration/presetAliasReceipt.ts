// SPDX-License-Identifier: GPL-3.0-or-later
import {validBodyScalarReceiptState} from '../bodyScalar/transferModel';
import type {PresetAction,PresetOptions,PresetReply} from '../presets/presetWorkflow';
import {canonical} from './model';
import {sameDecorationPresetAck} from './transferModel';
import {sameDecorationPresetAliasMarker,type DecorationPresetAliasMarker} from './presetAliasHistoryRegistry';
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const token=(v:unknown):v is string=>typeof v==='string'&&!!v.trim()&&!/[\u0000-\u001f\u007f-\u009f]/.test(v)&&new TextEncoder().encode(v).length<=128;
const foreign=['eye_bag_preset_alias_review','eye_bag_alias_review','eye_bag_batch_review','eye_bag_cohort_review','eye_bag_recovery_alias_review','face_style_alias_review','face_decoration_alias_review','face_decoration_batch_review','face_decoration_cohort_review','face_decoration_support_alias_review'];
/** Whole mixed-preset publication has one owner. A diagnostic batch ID never authorizes history. */
export function checkDecorationPresetAliasReceipt(result:PresetReply,action:PresetAction,opts:PresetOptions,expectedScope?:string[]):'none'|'no-write'|'compensated'|'identity-unknown'|'bound'{
 const ack=opts.faceDecorationPresetAck&&'members'in opts.faceDecorationPresetAck?opts.faceDecorationPresetAck:null;
 if(Object.hasOwn(result,'face_decoration_preset_alias_review')&&(action!=='apply'||!ack))throw Error('未请求的脸部装饰混合预设共享来源批次标记');
 if(action!=='apply'||!ack)return 'none';
 const raw=result as unknown as Record<string,unknown>;
 if(foreign.some(field=>Object.hasOwn(raw,field))||opts.eyeBagPresetAck!==undefined)throw Error('装饰混合预设不能混用其他历史所有者，只能查询原请求');
 if(result.face_decoration_visual_required!==true||['no_write','rolled_back','requires_reload','requires_readback'].some(field=>Object.hasOwn(raw,field)&&typeof raw[field]!=='boolean')
  ||result.outcome_unknown&&(raw.no_write===true||result.rolled_back===true)
  ||result.success&&(raw.no_write===true||result.rolled_back===true||raw.no_change===true)||!validBodyScalarReceiptState(result))throw Error('装饰混合预设终态不明确，只能查询原请求');
 if(result.face_decoration_preset_ack!==undefined&&!([['xmp_review_ack',opts.xmpReviewAck],['spill_review_ack',opts.spillReviewAck],['shadow_review_ack',opts.shadowReviewAck]] as const)
  .every(([field,expected])=>expected===undefined?!Object.hasOwn(raw,field):Object.hasOwn(raw,field)&&canonical(raw[field])===canonical(expected)))throw Error('完整混合预设的其他逐图确认与原请求不一致');
 const acceptedIdentity=result.id===opts.id&&result.document_id===opts.documentId&&result.preflight_token===opts.preflightToken&&sameDecorationPresetAck(result.face_decoration_preset_ack,ack);
 const orderedScope=expectedScope!==undefined&&JSON.stringify(result.module_scope)===JSON.stringify(expectedScope);
 const diagnostic=result.success===false&&typeof result.error==='string'&&!!result.error.trim()&&acceptedIdentity
  &&(result.module_scope===undefined||orderedScope)
  &&!['face_decoration_preset_alias_review','alias_members','face_decoration_preset','before','after','doc_state'].some(field=>Object.hasOwn(raw,field))
  &&raw.operation_committed!==true&&raw.committed!==true&&['applied','restored'].every(field=>!Object.hasOwn(raw,field)||Array.isArray(raw[field])&&raw[field].length===0);
 if(diagnostic&&result.outcome_unknown===true&&(!Object.hasOwn(raw,'batch_id')||token(result.batch_id)))return 'identity-unknown';
 const noWrite=diagnostic&&result.outcome_unknown===false&&!Object.hasOwn(raw,'batch_id');
 if(noWrite){
  if(['batch_id','face_decoration_preset_alias_review','alias_members'].some(field=>Object.hasOwn(raw,field)))throw Error('明确未写入回执不能同时宣称装饰共享来源批次');
  if(result.rolled_back===true){if(raw.no_write===true)throw Error('补偿恢复不能同时声称从未写入');return 'compensated';}
  return 'no-write';
 }
 if(!acceptedIdentity||!orderedScope||!result.module_scope||ack.members.length<2||ack.members.length>16)throw Error('装饰混合预设缺少准确模块范围与全部原成员确认');
 const marker:DecorationPresetAliasMarker={version:1,review_sha256:ack.review_sha256,preset_sha256:ack.preset_sha256,applies_sha256:ack.applies_sha256,current_document_id:ack.members[0].document_id,member_count:ack.members.length,selected_modules:[...result.module_scope]};
 if(result.batch_id!==undefined&&result.batch_id!==null&&!token(result.batch_id)
  ||result.face_decoration_preset_alias_review!==undefined&&!sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,marker))throw Error('装饰混合预设批次身份或选定完整范围不匹配');
 if(!result.batch_id||!sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,marker)
  ||!Array.isArray(result.alias_members)||result.alias_members.length!==ack.members.length||!result.alias_members.every((row,index)=>{
   const member=ack.members[index];return object(row)&&Object.keys(row).sort().join('|')==='document_id|expected_revision|result_revision'
    &&row.document_id===member.document_id&&row.expected_revision===member.revision&&typeof row.result_revision==='string'&&/^(0|[1-9]\d{0,15})$/.test(row.result_revision)
    &&BigInt(row.result_revision)<=BigInt(Number.MAX_SAFE_INTEGER)&&BigInt(row.result_revision)===BigInt(member.revision)+1n;
  }))throw Error('装饰混合预设未证明全部原成员一次性发布');
 if(!result.success&&(typeof result.error!=='string'||!result.error.trim()))throw Error('装饰混合预设缺少明确失败原因');
 if(!result.success&&!result.outcome_unknown&&(['batch_id','face_decoration_preset_alias_review','alias_members','before','after','doc_state'].some(field=>Object.hasOwn(raw,field))||result.operation_committed===true))throw Error('装饰混合预设拒绝回执同时含有写入证据');
 if(result.success){
  const people=result.doc_state?.people,binding=object(people)?people.binding:null;
  if(!object(binding)||binding.document_id!==ack.members[0].document_id||binding.document_revision!==Number(BigInt(ack.members[0].revision)+1n)
   ||result.operation_committed===false||result.rolled_back===true)throw Error('装饰混合预设当前绑定与全成员终态不一致');
 }
 return 'bound';
}
