// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import {checkedCreativeDocument, type CreativeAuthority, type CreativeHistory, type CreativePreview,
  type CreativeReceipt, type CreativeRequest} from './model';

export interface CreativeCapabilities {
  command: boolean; import_image: boolean; attach_mask: boolean; remove_mask: boolean;
  history: boolean; return_new: boolean; update_original: boolean;
}
export interface CreativeNativeState {
  authority: CreativeAuthority; preview: CreativePreview | null; history: CreativeHistory | null;
  capabilities: CreativeCapabilities;
}
export type CreativePacket = Record<string, unknown> & {
  event: 'creative_document_state' | 'creative_document_result'; request_id: string; source_uid: string;
};
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
export const MAX_CREATIVE_FILE_BYTES = 128 * 1024 * 1024;
/** The native bridge explicitly confirmed that validation failed BEFORE sending. */
export class CreativeNativeRejected extends Error {}
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
function bounded<T>(promise: Promise<T>, milliseconds = 10000): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([promise, new Promise<T>((_, reject) => {timer = setTimeout(() => reject(Error('创意文档通信超时，请核对原请求。')), milliseconds);})])
    .finally(() => {if (timer !== undefined) clearTimeout(timer);});
}
export async function submitCreativeNative(request: Record<string, unknown>): Promise<void> {
  const result = await bounded(invoke<{requested: boolean; request_id: string; status?: string; message?: string}>('creative_document_request',
    {request: {cmd: 'creative_document', ...request}}));
  if (result?.requested === false && result.request_id === request.request_id && result.status === 'rejected')
    throw new CreativeNativeRejected(result.message || '原生宿主已拒绝请求，未发送到引擎。');
  if (result?.requested !== true || result.request_id !== request.request_id) throw Error('创意文档发送回执身份无效。');
}
export async function queryCreativeNative(requestId: string): Promise<CreativePacket | null> {
  const result = await bounded(invoke<{phase: string; result: unknown}>('creative_document_status', {requestId}));
  if (!result || !['done', 'pending', 'unknown'].includes(result.phase)) throw Error('创意文档查询响应无效。');
  if (result.phase === 'pending') return null;
  if (result.phase === 'unknown') throw Error('原创意文档请求不存在、已过期或引擎已重启；不会重发。');
  const value = result.result;
  if (!object(value) || !['creative_document_state', 'creative_document_result'].includes(String(value.event)) ||
      value.request_id !== requestId || typeof value.source_uid !== 'string') throw Error('创意文档回执身份不符。');
  return value as CreativePacket;
}
export async function awaitCreativeNative(requestId: string): Promise<CreativePacket> {
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const result = await queryCreativeNative(requestId); if (result) return result;
    await sleep(100);
  }
  throw Error('创意文档结果尚未确认，请查询原操作；不会自动重发。');
}
export function creativeNativeState(packet: CreativePacket): CreativeNativeState | null {
  if (!object(packet.authority)) return null;
  const value = packet.authority;
  const document = checkedCreativeDocument(value.document);
  if (document.source_uid !== packet.source_uid || typeof value.ownership_token !== 'string' || !value.ownership_token || typeof value.busy !== 'boolean')
    throw Error('创意文档所有权状态无效。');
  const capabilities = packet.capabilities;
  const names = ['command', 'import_image', 'attach_mask', 'remove_mask', 'history', 'return_new', 'update_original'] as const;
  if (!object(capabilities) || names.some(key => typeof capabilities[key] !== 'boolean')) throw Error('创意文档能力清单不完整。');
  let history: CreativeHistory | null = null;
  if (packet.history !== null && packet.history !== undefined) {
    if (!object(packet.history) || ['can_undo', 'can_redo', 'recoverable_delete'].some(key => typeof (packet.history as Record<string, unknown>)[key] !== 'boolean'))
      throw Error('创意文档历史状态无效。');
    history = packet.history as unknown as CreativeHistory;
  }
  let preview: CreativePreview | null = null;
  if (packet.preview !== null && packet.preview !== undefined) {
    const p = packet.preview;
    if (!object(p) || typeof p.document_id !== 'string' || typeof p.source_uid !== 'string' ||
        typeof p.ownership_token !== 'string' || !Number.isSafeInteger(p.revision) ||
        typeof p.render_id !== 'string' || !p.render_id || typeof p.url !== 'string' || !p.url)
      throw Error('创意文档预览身份不完整。');
    preview = p as unknown as CreativePreview;
  }
  return {authority: {document, ownership_token: value.ownership_token, busy: value.busy}, preview, history,
    capabilities: capabilities as unknown as CreativeCapabilities};
}
export function creativeNativeReceipt(packet: CreativePacket, request: CreativeRequest): CreativeReceipt {
  if (packet.event !== 'creative_document_result' || packet.request_id !== request.request_id || packet.source_uid !== request.source_uid ||
      packet.document_id !== request.document_id || packet.ownership_token !== request.ownership_token || packet.expected_revision !== request.expected_revision)
    throw Error('创意文档操作回执绑定不匹配。');
  if (packet.status === 'rejected' || packet.status === 'unknown') return {...request, status: packet.status,
    message: typeof packet.message === 'string' ? packet.message : '创意文档操作没有成功确认。'};
  if ((packet.status !== 'applied' && packet.status !== 'no_change') || !Number.isSafeInteger(packet.revision) || Number(packet.revision) < 0)
    throw Error('创意文档操作缺少终态修订号。');
  return {...request, status: packet.status, revision: Number(packet.revision),
    ...(object(packet.authority) && object(packet.authority.document) && packet.authority.document.document_id === request.document_id &&
      packet.authority.document.source_uid === request.source_uid && typeof packet.authority.ownership_token === 'string' ?
      {next_ownership_token: packet.authority.ownership_token} : {})};
}
export async function creativeFileFields(file: File): Promise<{bytes_base64: string; filename: string}> {
  if (!file.size || file.size > MAX_CREATIVE_FILE_BYTES) throw Error('图片文件为空或超过 128 MiB 传输安全上限。');
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.byteLength !== file.size) throw Error('读取的图片字节不完整，未提交。');
  const chunks: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += 32768) chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 32768)));
  return {filename: file.name, bytes_base64: btoa(chunks.join(''))};
}
