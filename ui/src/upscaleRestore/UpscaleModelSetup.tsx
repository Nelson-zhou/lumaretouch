// SPDX-License-Identifier: GPL-3.0-or-later
/** Explicit setup, reusing the one native optional-model subprocess owner. AUTHORED / UNRUN. */
import {useEffect, useRef, useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {UPSCALE_MODEL, upscaleObject as object} from './model';

type Action = 'status' | 'install' | 'check' | 'cancel';
interface SetupStatus {
  running: boolean; action?: string; extension_id: 'upscale-native-v1'; error?: string;
  result?: {model_id?: string; state?: string; phase?: string; ready?: boolean; installed?: boolean;
    error?: string; reason?: string; downloaded_bytes?: number; total_bytes?: number};
}
const EXTENSION = 'upscale-native-v1' as const;
function checked(value: unknown): SetupStatus {
  if (!object(value) || typeof value.running !== 'boolean' || value.extension_id !== EXTENSION
    || value.result !== undefined && (!object(value.result) || value.result.model_id !== undefined && value.result.model_id !== UPSCALE_MODEL))
    throw Error('共享安装器当前属于其他扩展或回执无效；未采用其状态，也不会取消它。');
  return value as unknown as SetupStatus;
}
export function UpscaleModelSetup({disabled}: {disabled: boolean}) {
  const [status, setStatus] = useState<SetupStatus | null>(null), [error, setError] = useState('');
  const alive = useRef(true), serial = useRef(0);
  useEffect(() => {alive.current = true; return () => {alive.current = false; ++serial.current;};}, []);
  async function run(action: Action) {
    const identity = ++serial.current; setError('');
    setStatus(previous => ({...previous, extension_id: EXTENSION, running: true, action}));
    try {
      let next = checked(await invoke<unknown>('prompted_model', {action, extensionId: EXTENSION}));
      while (alive.current && identity === serial.current) {
        setStatus(next);
        if (!next.running) return;
        await new Promise(resolve => setTimeout(resolve, 500));
        if (!alive.current || identity !== serial.current) return;
        next = checked(await invoke<unknown>('prompted_model_status'));
      }
    } catch (reason) {
      if (alive.current && identity === serial.current) {
        setError(String(reason)); setStatus(previous => previous ? {...previous, running: false} : null);
      }
    }
  }
  const result = status?.result;
  const done = result?.downloaded_bytes, total = result?.total_bytes;
  const progress = typeof done === 'number' && typeof total === 'number' && Number.isSafeInteger(done)
    && Number.isSafeInteger(total) && done >= 0 && total > 0 && done <= total;
  return <details aria-label="本地 AI 超清模型设置"><summary>AI 超清模型与基础环境 · {result?.ready === true ? '能力待当前来源重新核对' : '尚未获准使用'}</summary>
    <p>固定 Swin2SR classical SR x2。仅显式安装下载经来源和摘要核验的公开模型，不上传照片；不会安装其他模型或任意社区节点。</p>
    <p>基础环境须已提供 torch 2.7.1+cpu 与 NumPy 2；此入口不会安装或替换基础运行时。文件核验、运行时准入、当前照片推理与实机画质验收是独立状态。完整运行时证据不足时保持不可用；此面板不把文件存在、CPU 检查或安装回执解释成照片质量和速度验收。</p>
    <div className="upscaleRestoreActions">
      <button type="button" disabled={disabled || !!status?.running} onClick={() => void run('status')}>核对超清安装状态</button>
      <button type="button" disabled={disabled || !!status?.running} onClick={() => void run('install')}>安装 / 继续下载 / 重试</button>
      <button type="button" disabled={disabled || !!status?.running || result?.installed !== true} onClick={() => void run('check')}>核对运行时准入</button>
      {status?.running && status.action !== 'status' && <button type="button" onClick={() => void run('cancel')}>取消本扩展准备</button>}
    </div>
    {progress && <label>模型下载 <progress value={done} max={total}/>{done} / {total} 字节</label>}
    <p role="status">{error || status?.error || result?.error || result?.reason || result?.phase || result?.state || '尚未核对。不会在打开面板时开始安装或分析。'}</p>
    <small>安装状态不等于推理可用。完成后点击“重新核对并获取完整来源”，由引擎重新检查运行条件；不会重启引擎或丢弃编辑。关闭面板不取消已开始的共享安装任务。</small>
  </details>;
}
