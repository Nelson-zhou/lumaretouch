// SPDX-License-Identifier: GPL-3.0-or-later
import {validBodyScalarReceiptState} from '../bodyScalar/transferModel';
import {sameDecorationPresetAliasMarker,type DecorationPresetAliasMarker} from './presetAliasHistoryRegistry';
export type DecorationPresetAliasHistoryRequest={decorationPresetAliasWrite?:boolean;decorationPresetAliasEpoch?:string|null;
 decorationPresetAliasMarker?:DecorationPresetAliasMarker|null;decorationPresetAliasMemberCount?:number|null;batchId?:string;action:string};
/** Composite full-recipe + graph history must never downgrade to graph-only restoration. */
export function checkDecorationPresetAliasHistoryReceipt(result:{face_decoration_preset_alias_review?:unknown;batch_id?:string|null;action:string;success:boolean;outcome_unknown?:boolean;
 no_write?:boolean;rolled_back?:boolean;module_scope?:string[];restored?:number[];conflicts?:{path:string;reason:string}[];error?:string},request:DecorationPresetAliasHistoryRequest):void{
 if(Object.hasOwn(result,'face_decoration_preset_alias_review')&&(!request.decorationPresetAliasWrite||!request.decorationPresetAliasMarker
  ||!sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,request.decorationPresetAliasMarker)))throw Error('未请求或不匹配的装饰混合预设完整历史标记');
 if(!request.decorationPresetAliasWrite)return;
 if(!validBodyScalarReceiptState(result)||!['undo','redo'].includes(request.action)||result.action!==request.action
  ||(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId
  ||['face_style_alias_review','eye_bag_alias_review','eye_bag_batch_review','eye_bag_cohort_review','eye_bag_preset_alias_review','eye_bag_recovery_alias_review',
   'face_decoration_alias_review','face_decoration_batch_review','face_decoration_cohort_review','face_decoration_support_alias_review'].some(field=>Object.hasOwn(result,field)))throw Error('装饰混合预设历史终态、批次或历史所有者不一致，只能查询原请求');
 if(result.outcome_unknown){
  if(result.no_write===true||result.rolled_back===true)throw Error('装饰混合预设未知历史不能同时声明未写入或完整回滚');
  return;
 }
 if(!request.decorationPresetAliasMarker||request.decorationPresetAliasMemberCount==null
  ||!sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,request.decorationPresetAliasMarker)
  ||result.batch_id!==request.batchId||JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])
  ||!Array.isArray(result.restored)||!result.restored.every(index=>Number.isSafeInteger(index)&&index>=0)||new Set(result.restored).size!==result.restored.length
  ||result.conflicts!==undefined&&(!Array.isArray(result.conflicts)||!result.conflicts.every(row=>!!row&&typeof row.path==='string'&&typeof row.reason==='string'&&!!row.reason.trim())))throw Error('装饰混合预设历史缺少原当前配方与全成员完整恢复证明');
 if(result.success){
  if(result.no_write===true||result.rolled_back===true||result.restored.length!==request.decorationPresetAliasMemberCount||!Array.isArray(result.conflicts)||result.conflicts.length!==0)throw Error('装饰混合预设未证明全部原成员一起恢复');
 }else if(!(result.no_write===true&&result.rolled_back!==true||result.no_write===false&&result.rolled_back===true)
  ||result.restored.length!==0||result.conflicts!==undefined&&result.conflicts.length!==0||typeof result.error!=='string'||!result.error.trim()
  ||['doc_state','before','after','applied','committed','operation_committed'].some(field=>Object.hasOwn(result,field)))throw Error('装饰混合预设历史失败未证明未发布或完整回滚，只能查询原请求');
}
