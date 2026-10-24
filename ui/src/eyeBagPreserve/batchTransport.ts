// SPDX-License-Identifier: GPL-3.0-or-later
import type {SpillImage} from '../spillRemoval/model';
import {validCollarboneImageMetadata, verifyCollarboneImage} from '../collarbone/transferModel';
import type {EyeBagBatchImageMetadata} from './batchModel';

export type EyeBagBatchImageRequest = {preflightToken: string; documentId: string; revision: string;
  side: 'before' | 'after'; sha256: string; requestId: string};
export type EyeBagBatchImageReply = {request_id: string; action: 'eye_bag_visual'; success: boolean;
  outcome_unknown?: boolean; error?: string; preflight_token: string; document_id: string; revision: string;
  side: 'before' | 'after'; sha256: string; compact: EyeBagBatchImageMetadata; image: SpillImage};
export type EyeBagBatchImageTransport = {
  request: (value: EyeBagBatchImageRequest) => Promise<{requested: boolean}>;
  read: (id: string) => Promise<{phase: string; request_id: string; result?: EyeBagBatchImageReply; error?: string}>;
};
/** One frozen target and side per read. Never sends or retries a write. */
export async function fetchEyeBagBatchImage(api: EyeBagBatchImageTransport, request: EyeBagBatchImageRequest,
  expected: EyeBagBatchImageMetadata, live: () => boolean = () => true): Promise<SpillImage> {
  if (!request || Object.keys(request).sort().join('|') !== ['preflightToken','documentId','revision','side','sha256','requestId'].sort().join('|')
    || !/^[a-f0-9]{32}$/.test(request.preflightToken) || !/^[a-f0-9]{32}$/.test(request.documentId)
    || !/^(0|[1-9]\d{0,15})$/.test(request.revision) || BigInt(request.revision) > BigInt(Number.MAX_SAFE_INTEGER)
    || typeof request.requestId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(request.requestId)
    || !validCollarboneImageMetadata(expected) || request.sha256 !== expected.sha256 || !['before', 'after'].includes(request.side))
    throw Error('祛眼袋卧蚕保护读取请求与冻结图像不一致');
  const deadline = Date.now() + 30000;
  async function bounded<T>(promise: Promise<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(Error('读取审核图像超时，请重新读取本目标。')), Math.max(1, deadline - Date.now()));
      promise.then(value => {clearTimeout(timer); resolve(value);}, error => {clearTimeout(timer); reject(error);});
    });
  }
  if (!live()) throw Error('审核图像请求已失效');
  const accepted = await bounded(api.request({...request}));
  if (!accepted.requested) throw Error('审核图像读取未确认入队');
  while (live()) {
    const response = await bounded(api.read(request.requestId));
    if (!live()) throw Error('审核图像请求已失效');
    if (response.request_id !== request.requestId) throw Error('审核图像请求身份不匹配');
    if (response.phase === 'done') {
      const r = response.result;
      if (!r || r.request_id !== request.requestId || r.action !== 'eye_bag_visual' || r.success !== true || r.outcome_unknown === true
        || r.preflight_token !== request.preflightToken || r.document_id !== request.documentId || r.revision !== request.revision
        || r.side !== request.side || r.sha256 !== request.sha256 || !validCollarboneImageMetadata(r.compact)
        || r.compact.mime !== expected.mime || r.compact.width !== expected.width || r.compact.height !== expected.height
        || r.compact.sha256 !== expected.sha256 || !r.image || r.image.mime !== expected.mime
        || r.image.width !== expected.width || r.image.height !== expected.height || r.image.sha256 !== expected.sha256
        || !await verifyCollarboneImage(r.image) || !live())
        throw Error(r?.error || '祛眼袋卧蚕保护图像不属于本次冻结目标，或 PNG 内容未通过校验');
      return r.image;
    }
    if (response.phase !== 'pending' || Date.now() >= deadline) throw Error(response.error || '审核图像暂不可读取，请重试本目标的只读图像。');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error('审核图像请求已失效');
}
