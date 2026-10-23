import {object, type Request} from './model.ts';

export interface ApplyReceipt extends Request {
  protocol: 1; action: 'apply'; success: boolean; outcome_unknown: boolean; requires_reload: boolean;
  no_change: boolean; history: {undo_steps: number; redo_steps: number} | null; error?: string;
}
export interface ReadbackRequest extends Request {readback_id: string}
export type ReadbackPhase = 'pending' | 'found' | 'missing' | 'epoch_changed' | 'engine_unavailable' | 'failed' | 'unavailable';
export interface ReadbackStatus extends ReadbackRequest {
  protocol: 1; action: 'query'; phase: ReadbackPhase; audit_scope: 'application-process';
  result: unknown | null; original_receipt: unknown | null; error?: string;
}
export interface ReadbackAudit {request: ReadbackRequest; status: ReadbackStatus | null; error: string | null; restored_from_inventory?: boolean}
export interface Audit {
  original_request: Request; original_receipt: unknown | null; latest_original_receipt: unknown | null;
  engine_key?: string; readbacks: ReadbackAudit[]; authoritative_result: ApplyReceipt | null;
  settled_by: 'original-receipt' | 'readback' | null;
  engine_state?: 'same_live_engine' | 'epoch_changed' | 'engine_unavailable';
}
export function auditInventory(raw: unknown): {audit: Audit[]; unresolved: Request[]; clientGeneration: string} {
  if (!object(raw) || raw.protocol !== 1 || raw.audit_scope !== 'application-process' || !Array.isArray(raw.items) ||
      raw.items.length > 4096 || raw.count !== raw.items.length || typeof raw.client_generation !== 'string' ||
      !/^[1-9][0-9]{0,19}$/.test(raw.client_generation) || BigInt(raw.client_generation) > 18446744073709551615n) throw Error('原操作登记清单或界面代次不完整，不能解除编辑保护');
  const audit: Audit[] = [], unresolved: Request[] = [], seen = new Set<string>();
  for (const item of raw.items) {
    if (!object(item) || !object(item.original_request) || typeof item.unresolved !== 'boolean' ||
        !['same_live_engine', 'epoch_changed', 'engine_unavailable'].includes(String(item.engine_state)) ||
        !Object.hasOwn(item, 'original_receipt') || !Object.hasOwn(item, 'readback_result') || !Object.hasOwn(item, 'readback_id')) throw Error('原操作登记项不完整');
    const r = item.original_request;
    if (typeof r.request_id !== 'string' || !r.request_id || r.request_id.length > 128 || seen.has(r.request_id) ||
        typeof r.document_id !== 'string' || !r.document_id || r.document_id.length > 128 ||
        ![r.preview_id, r.session_id].every(v => typeof v === 'string' && /^[0-9a-f]{32}$/.test(v) && !/^0+$/.test(v)) ||
        (item.readback_id !== null && (typeof item.readback_id !== 'string' || !/^[0-9a-f]{32}$/.test(item.readback_id) || /^0+$/.test(item.readback_id)))) throw Error('原操作登记身份无效或重复');
    const request = structuredClone(r) as unknown as Request; seen.add(request.request_id);
    const original = item.original_receipt === null ? null : applyReceipt(item.original_receipt, request);
    const recovered = item.readback_result === null ? null : applyReceipt(item.readback_result, request);
    if (recovered && item.readback_id === null) throw Error('核对记录缺少其独立身份');
    const result = recovered ?? original;
    const known = !!result && !result.outcome_unknown && !result.requires_reload;
    if (item.unresolved === known) throw Error('原操作登记状态与真实回执不一致，继续保留编辑保护');
    if (item.unresolved) unresolved.push(request);
    audit.push({original_request: request, original_receipt: structuredClone(item.original_receipt), latest_original_receipt: structuredClone(item.original_receipt),
      engine_state: item.engine_state as Audit['engine_state'], readbacks: item.readback_id ? [{request: {...request, readback_id: item.readback_id as string},
        status: null, error: null, restored_from_inventory: true}] : [], authoritative_result: result ? structuredClone(result) : null, settled_by: known ? (recovered ? 'readback' : 'original-receipt') : null});
  }
  return {audit, unresolved, clientGeneration: raw.client_generation};
}
export function applyReceipt(raw: unknown, request: Request): ApplyReceipt {
  if (!object(raw) || raw.protocol !== 1 || raw.action !== 'apply' ||
      (['request_id', 'preview_id', 'session_id', 'document_id'] as const).some(key => raw[key] !== request[key]) ||
      typeof raw.success !== 'boolean' || typeof raw.outcome_unknown !== 'boolean' || typeof raw.requires_reload !== 'boolean' ||
      typeof raw.no_change !== 'boolean' || (raw.success && raw.outcome_unknown) ||
      (raw.outcome_unknown && !raw.requires_reload)) throw Error('换底修改回执不完整或身份不符');
  const history = object(raw.history) && [raw.history.undo_steps, raw.history.redo_steps].every(v => Number.isSafeInteger(v) && Number(v) >= 0);
  if ((raw.success && (!history || raw.requires_reload)) || (!raw.success && raw.history !== null && !history)) throw Error('换底修改缺少有效历史证据');
  return raw as unknown as ApplyReceipt;
}
export function readbackStatus(raw: unknown, request: ReadbackRequest): ReadbackStatus {
  if (!object(raw) || raw.protocol !== 1 || raw.action !== 'query' || raw.audit_scope !== 'application-process' ||
      !/^[0-9a-f]{32}$/.test(request.readback_id) || /^0+$/.test(request.readback_id) ||
      (['request_id', 'preview_id', 'session_id', 'document_id', 'readback_id'] as const).some(key => raw[key] !== request[key]) ||
      !['pending', 'found', 'missing', 'epoch_changed', 'engine_unavailable', 'failed', 'unavailable'].includes(String(raw.phase)) ||
      !Object.hasOwn(raw, 'original_receipt') || !Object.hasOwn(raw, 'result') ||
      (raw.phase !== 'found' && raw.result !== null) || (raw.phase === 'found' && !object(raw.result))) throw Error('同引擎核对回执不完整或身份不符');
  if (raw.original_receipt !== null) applyReceipt(raw.original_receipt, request);
  return raw as unknown as ReadbackStatus;
}
/** Missing query registration cannot provide original identities and never proves noncommit. */
export function unavailableReadback(raw: unknown, readbackId: string): boolean {
  return object(raw) && raw.phase === 'unavailable' && raw.readback_id === readbackId && raw.result === null && !Object.hasOwn(raw, 'protocol');
}
export const checkpointRequired = '这不是“未执行”的证据。请从已确认的工程检查点进行明确恢复；原操作仍保留，不会重发。';
export function unresolvedMessage(phase: ReadbackPhase): string {
  const reason: Record<ReadbackPhase, string> = {
    pending: '正在核对同一引擎保存的原操作结果。',
    found: '引擎原记录本身仍为未知或要求重新载入，无法用只读核对修复。',
    missing: '同一引擎未找到原操作结果，可能已超出保留范围。',
    epoch_changed: '引擎已经更换，不能把新引擎的状态当作旧操作结果。',
    engine_unavailable: '原引擎当前不可用，无法读取其保存的结果。',
    failed: '同引擎结果核对失败，原操作仍未确认。',
    unavailable: '核对回执暂不可用，原操作仍未确认。',
  };
  return `${reason[phase]}${phase === 'pending' ? '' : checkpointRequired}`;
}
