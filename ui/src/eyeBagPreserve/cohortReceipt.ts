// SPDX-License-Identifier: GPL-3.0-or-later
import {bodyScalarNoWriteRejection} from '../bodyScalar/transferModel';
import {sameEyeBagCohortAck, type EyeBagCohortAck} from './cohortModel';
import type {BatchAction, BatchPlan, BatchReply} from '../batch/batchWorkflow';
/** A claimed effect cannot masquerade as the small, explicit pre-write rejection. */
export function checkEyeBagCohortReceipt(result: BatchReply, request: {action: BatchAction; token?: string; scope?: string[]; eyeBagCohortAck?: EyeBagCohortAck[]}): void {
  if (result.eye_bag_cohort !== undefined && request.action !== 'preflight' && request.eyeBagCohortAck === undefined
    || result.eye_bag_cohort_ack !== undefined && (request.action !== 'commit' || request.eyeBagCohortAck === undefined))
    throw Error('未请求的祛眼袋完整成员审核回执。');
  const noWrite = bodyScalarNoWriteRejection(result, request.token)
    && !['eye_bag_cohort', 'eye_bag_cohort_ack', 'eye_bag_cohort_visual', 'persistent_association', 'association_source', 'source_outcome',
      'portrait_cohort', 'portrait_cohort_ack', 'eye_bag_review_ack'].some(field => Object.hasOwn(result, field));
  if (request.eyeBagCohortAck !== undefined && !noWrite && (result.preflight_token !== request.token || result.eye_bag_cohort !== true
    || JSON.stringify(result.module_scope) !== JSON.stringify(request.scope) || !sameEyeBagCohortAck(result.eye_bag_cohort_ack, request.eyeBagCohortAck)))
    throw Error('祛眼袋关联回执的完整范围、源成员优先图像对、双向保护或旧版策略不匹配，只能查询原请求。');
}
export function checkEyeBagCohortCommit(result: BatchReply, plan: BatchPlan): void {
  if (plan.eye_bag_cohort !== true) return;
  if (typeof result.batch_id !== 'string' || !result.batch_id.trim() || result.batch_id.length > 128 || /[\u0000-\u001f\u007f]/.test(result.batch_id))
    throw Error('祛眼袋关联提交缺少实际批次身份；相同共同意图必须在写入前拒绝。');
  const before = [plan.association_source, ...plan.targets], after = [result.source_outcome, ...(result.target_outcomes ?? [])];
  if (after.length !== before.length || !before.every((row, index) => row && after[index]?.document_id === row.document_id
    && after[index]?.outcome === 'applied' && after[index]?.path === row.path && after[index]?.expected_revision === row.revision))
    throw Error('祛眼袋关联源成员与全部目标必须按冻结顺序原子提交，不能接受省略、交换或部分成功。');
}
