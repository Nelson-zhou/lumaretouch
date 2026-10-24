// SPDX-License-Identifier: GPL-3.0-or-later
import {validBodyScalarReceiptState} from '../bodyScalar/transferModel';
import {sameSupportAliasMarker, type SupportAliasMarker} from './supportAliasHistoryRegistry';
export type SupportAliasHistoryRequest = {supportAliasWrite?: boolean; supportAliasEpoch?: string | null;
  supportAliasMarker?: SupportAliasMarker | null; supportAliasMemberCount?: number | null; batchId?: string; action: string};
/** Validate support-bank history separately from graph-only scalar batch receipts. */
export function checkSupportAliasHistoryReceipt(result: {
  face_decoration_support_alias_review?: unknown; batch_id?: string | null; action: string; success: boolean; outcome_unknown?: boolean;
  no_write?: boolean; rolled_back?: boolean; module_scope?: string[]; restored?: number[]; conflicts?: {path: string; reason: string}[]; error?: string;
}, request: SupportAliasHistoryRequest): void {
  if (result.face_decoration_support_alias_review !== undefined && (!request.supportAliasWrite || !request.supportAliasMarker
    || !sameSupportAliasMarker(result.face_decoration_support_alias_review, request.supportAliasMarker)))
    throw Error('未请求或不匹配的装饰范围历史标记，只能查询原请求。');
  if (!request.supportAliasWrite) return;
  if (!validBodyScalarReceiptState(result) || !['undo', 'redo'].includes(request.action)
    || (result.success || result.batch_id != null) && result.batch_id !== request.batchId)
    throw Error('装饰范围历史回执不属于原批次或终态不明确，只能查询原请求。');
  if (result.outcome_unknown) return;
  if (!request.supportAliasMarker || request.supportAliasMemberCount == null
    || !sameSupportAliasMarker(result.face_decoration_support_alias_review, request.supportAliasMarker)
    || result.batch_id !== request.batchId || JSON.stringify(result.module_scope) !== JSON.stringify(['lnx.people_graph.v1'])
    || !Array.isArray(result.restored) || result.conflicts !== undefined && !Array.isArray(result.conflicts)
    || !result.restored.every(index => Number.isSafeInteger(index) && index >= 0) || new Set(result.restored).size !== result.restored.length
    || result.conflicts !== undefined && !result.conflicts.every(row => !!row && typeof row.path === 'string' && typeof row.reason === 'string' && !!row.reason.trim()))
    throw Error('装饰范围历史缺少原批次全部成员与独立支持账本证明，只能查询原请求。');
  if (result.success) {
    if (result.restored.length !== request.supportAliasMemberCount || !Array.isArray(result.conflicts) || result.conflicts.length !== 0)
      throw Error('装饰范围历史未证明全部成员与支持银行一起恢复，只能查询原请求。');
  } else if (!(result.no_write === true && result.rolled_back !== true || result.no_write === false && result.rolled_back === true)
    || result.restored.length !== 0 || result.conflicts !== undefined && result.conflicts.length !== 0 || typeof result.error !== 'string' || !result.error.trim()
    || ['doc_state', 'before', 'after', 'applied', 'committed', 'operation_committed'].some(field => Object.hasOwn(result, field))) {
    throw Error('装饰范围历史失败未证明未发布或完整回滚，只能查询原请求。');
  }
}
