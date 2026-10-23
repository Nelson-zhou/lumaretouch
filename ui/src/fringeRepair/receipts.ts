import {object, opaqueId, readReceipt, type FringeReceipt, type FringeRequest} from './model';
import {bounded, type FringeTransport, type WaitOptions} from './protocol';

export interface AuditEntry {
  original_request: FringeRequest; original_receipt: FringeReceipt | null;
  engine_state: 'same_live_engine' | 'epoch_changed' | 'engine_unavailable'; unresolved: boolean;
}
/** Required native process inventory, not localStorage and not inferred document
 * state. Every successful bootstrap fences any old owner's late submission. */
export function readInventory(raw: unknown): {generation: string; entries: AuditEntry[]} {
  if (!object(raw) || raw.protocol !== 1 || raw.audit_scope !== 'application-process' ||
      typeof raw.client_generation !== 'string' || !/^[1-9][0-9]{0,19}$/.test(raw.client_generation) ||
      BigInt(raw.client_generation) > 18446744073709551615n || !Array.isArray(raw.items) ||
      raw.items.length > 4096 || raw.count !== raw.items.length) throw Error('祛边原操作登记不完整，继续保护编辑');
  const seen = new Set<string>();
  const entries = raw.items.map((item: unknown): AuditEntry => {
    if (!object(item) || !object(item.original_request) || typeof item.unresolved !== 'boolean' ||
        !['same_live_engine', 'epoch_changed', 'engine_unavailable'].includes(String(item.engine_state)) ||
        !Object.hasOwn(item, 'original_receipt')) throw Error('祛边原操作登记项不完整');
    const request = item.original_request;
    if (typeof request.request_id !== 'string' || !request.request_id || request.request_id.length > 128 ||
        seen.has(request.request_id) || typeof request.document_id !== 'string' || !request.document_id ||
        request.document_id.length > 128 || !opaqueId(request.preview_id) || !opaqueId(request.session_id))
      throw Error('祛边原操作登记身份无效');
    seen.add(request.request_id);
    const typed = request as unknown as FringeRequest;
    const receipt = item.original_receipt === null ? null : readReceipt(item.original_receipt, typed);
    const known = receipt !== null && !receipt.outcome_unknown && !receipt.requires_reload;
    if (item.unresolved === known) throw Error('祛边登记与原始回执矛盾，不能解除编辑保护');
    return {original_request: structuredClone(typed), original_receipt: receipt,
      engine_state: item.engine_state as AuditEntry['engine_state'], unresolved: item.unresolved};
  });
  return {generation: raw.client_generation, entries};
}
export async function awaitReceipt(api: FringeTransport, request: FringeRequest, options: WaitOptions): Promise<FringeReceipt | null> {
  const deadline = Date.now() + options.timeout;
  while (options.current()) {
    if (Date.now() >= deadline) throw Error('等待祛边原操作回执超时');
    const raw = await bounded(api.result(request.request_id), deadline - Date.now());
    if (!options.current()) return null;
    if (!object(raw) || raw.request_id !== request.request_id) throw Error('祛边原操作查询身份不符');
    if (raw.phase === 'pending') {await bounded(options.sleep(100), deadline - Date.now()); continue;}
    if (raw.phase !== 'done' || !object(raw.result)) throw Error('原操作回执未找到；这不能证明未执行，不会重新提交');
    return readReceipt(raw.result, request);
  }
  return null;
}
