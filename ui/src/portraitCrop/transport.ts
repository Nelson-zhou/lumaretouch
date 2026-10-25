// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import {notifyInspectionEditIntent} from '../native';
import {isCurveEditBusy, settleCurveEdit} from '../curveEditBarrier';
import {checkedReceipt, checkedWorkspaceReopened, digest, equal, record, PortraitCropNotSentError, type Receipt, type Request, type Transport, type WorkspaceReopened} from './model';
type Entry = {original: Request; hash: string | null; started: boolean; settledWithoutSend: boolean};
export type PortraitCropTransportOptions = {canUse: () => boolean; contextKey: () => string | null};
const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
function bounded<T>(promise: Promise<T>, milliseconds = 10000): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('原生人像裁剪响应尚未确认，请查询原请求，不会重发。')), milliseconds);
    promise.then(value => {clearTimeout(timer); resolve(value);}, error => {clearTimeout(timer); reject(error);});
  });
}
/** Actual native receipt transport. It owns no document, renderer, crop or history. */
export function createPortraitCropTransport(options: PortraitCropTransportOptions): Transport {
  const originals = new Map<string, Entry>();
  function retained(original: Request): Entry {
    const entry = originals.get(original.request_id);
    if (!entry || !equal(entry.original, original)) throw Error('没有一致的原人像裁剪请求，不能重构或重新发送。');
    return entry;
  }
  function accept(entry: Entry, value: unknown): Receipt | WorkspaceReopened {
    if (record(value) && value.workspace_reopened === true) return checkedWorkspaceReopened(value, entry.original);
    if (record(value) && value.action === 'status') {
      if (!record(value.original_request) || value.original_request.target_request_id !== entry.original.request_id || value.original_request.cmd !== 'portrait_crop' || value.original_request.action !== 'status') throw Error('原生查询回执目标不一致。');
      checkedReceipt(value, value.original_request as Request, null);
      if (value.phase !== 'status') throw Error(typeof value.message === 'string' ? value.message : '原请求回执缺失，不能判断是否已执行。');
      value = value.receipt;
    }
    const result = checkedReceipt(value, entry.original, entry.hash);
    entry.hash = result.command_sha256;
    return result;
  }
  async function status(original: Request): Promise<unknown> {
    const entry = retained(original);
    if (!entry.started) throw Error(entry.settledWithoutSend ? '此请求确认未发送，请返回重新开始。' : '正在等待已有曲线编辑结束，本次人像裁剪尚未入队。');
    // Never gate recovery by current photo, open state, engine admission or edit barriers.
    return accept(entry, await bounded(invoke<unknown>('portrait_crop_status', {original: structuredClone(entry.original)})));
  }
  return {
    status,
    async send(request, onReceipt) {
      if (originals.has(request.request_id)) {
        // Accidental repeat calls query the retained command, never invoke it again.
        retained(request); return status(request);
      }
      if (originals.size >= 512 || new TextEncoder().encode(JSON.stringify(request)).byteLength > 60 * 1024) throw new PortraitCropNotSentError('人像裁剪请求身份或体积已达本地上限，尚未发送。');
      const entry: Entry = {original: structuredClone(request), hash: null, started: false, settledWithoutSend: false};
      originals.set(request.request_id, entry);
      const context = options.contextKey();
      try {
        if (request.action !== 'cancel' && (!context || !options.canUse())) throw Error('当前照片或其他编辑工具未就绪。');
        if (request.action === 'current' || request.action === 'apply') {
          if (isCurveEditBusy()) await settleCurveEdit();
          if (!options.canUse() || !context || context !== options.contextKey()) throw Error('曲线编辑结束后来源或文档状态已变化。');
        }
      } catch (error) {
        entry.settledWithoutSend = true;
        throw new PortraitCropNotSentError(`${error instanceof Error ? error.message : '前置编辑未完成。'} 本次人像裁剪确认尚未发送。`);
      }
      // Notification precedes enqueue and is never a crop mutation itself.
      if (request.action === 'apply') {
        try {notifyInspectionEditIntent();} catch {
          entry.settledWithoutSend = true;
          throw new PortraitCropNotSentError('裁剪前的检查状态切换失败，本次请求确认尚未发送。');
        }
      }
      // Set BEFORE invoke. A lost/rejected native Promise is never proof of no enqueue.
      entry.started = true;
      let result: Receipt | WorkspaceReopened;
      try {result = accept(entry, await bounded(invoke<unknown>('portrait_crop', {request: structuredClone(entry.original)})));}
      catch {result = await status(entry.original) as Receipt | WorkspaceReopened;}
      const until = Date.now() + 120000;
      while (!('workspace_reopened' in result) && (result.phase === 'working' || result.phase === 'unknown')) {
        onReceipt?.(result);
        if (Date.now() >= until) return result;
        await pause(250);
        result = await status(entry.original) as Receipt | WorkspaceReopened;
      }
      return result;
    },
    async cancelRead(original, commandSha256) {
      const entry = retained(original);
      if (!['current', 'preview'].includes(entry.original.action) || !entry.started || !digest(commandSha256) || commandSha256 !== entry.hash) throw Error('取消只适用于已保留摘要的原始来源或预览请求。');
      // This acknowledges reader ingress only; controller still queries the original outcome.
      return bounded(invoke<unknown>('portrait_crop_cancel_read', {original: structuredClone(entry.original), command_sha256: commandSha256}));
    },
  };
}
