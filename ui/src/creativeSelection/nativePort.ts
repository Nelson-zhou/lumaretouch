// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import {SELECTION_PROTOCOL, selectionReplyMatches, type CreativeSelectionPort,
  type SelectionReply, type SelectionRequest} from './model';

const sleep = (milliseconds: number) => new Promise<void>(resolve => setTimeout(resolve, milliseconds));
async function bounded<T>(promise: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {return await Promise.race([promise, new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(Error('选区通信未确认，请查询原请求，不会重发。')), 10000);
  })]);} finally {if (timer !== undefined) clearTimeout(timer);}
}
async function receipt(request: SelectionRequest): Promise<SelectionReply> {
  const value = await bounded(invoke<{phase: string; result: unknown}>('creative_selection_status', {requestId: request.request_id}));
  if (value?.phase === 'pending') return {event: 'creative_selection_result', request_id: request.request_id,
    source_uid: request.source_uid, status: 'pending', message: '原选区请求仍在处理，尚未发布新结果。'};
  if (value?.phase === 'unknown') return {event: 'creative_selection_result', request_id: request.request_id,
    source_uid: request.source_uid, status: 'unknown', message: '原引擎已结束或原回执不可用；不会向新引擎重发。'};
  if (value?.phase !== 'done' || !selectionReplyMatches(value.result, request)) throw Error('选区查询响应身份无效。');
  return value.result;
}
async function request(original: SelectionRequest): Promise<SelectionReply> {
  const result = await bounded(invoke<{requested: boolean; request_id: string; status?: string; message?: string}>(
    'creative_selection_request', {request: {cmd: 'creative_selection', ...original}}));
  if (result?.requested === false && result.request_id === original.request_id && result.status === 'rejected') {
    return {event: 'creative_selection_result', request_id: original.request_id, source_uid: original.source_uid,
      status: 'rejected', message: result.message || '宿主在发送前拒绝了无效请求。',
      ...(original.action === 'cancel' ? {target_request_id: original.target_request_id} : {})};
  }
  if (result?.requested !== true || result.request_id !== original.request_id) throw Error('选区发送回执无效，原操作仍待核对。');
  const until = Date.now() + 120000;
  do {
    const value = await receipt(original);
    if (value.status !== 'pending') return value;
    await sleep(150);
  } while (Date.now() < until);
  return {event: 'creative_selection_result', request_id: original.request_id, source_uid: original.source_uid,
    status: 'pending', message: '原选区任务尚未完成；继续查询或请求取消读取，不会重发。'};
}
/** Stable built-in adapter. Replacing it cannot transfer an unresolved request. */
export const creativeSelectionNativePort: CreativeSelectionPort = Object.freeze({
  protocol: SELECTION_PROTOCOL, context: request, preview: request, apply: request, cancel: request, receipt,
  release: (original: SelectionRequest) => bounded(invoke<void>('creative_selection_release', {requestId: original.request_id})),
});
