// SPDX-License-Identifier: GPL-3.0-or-later
import {useRef, useState} from 'react';
import {open} from '@tauri-apps/plugin-dialog';
import {runProject} from '../native';

/** Explicit escape stays inside the selection-only event guard. No inferred rollback. */
export function SelectionRecovery({enabled, engineAlive, onStartEngine}: {enabled: boolean; engineAlive: boolean; onStartEngine: () => Promise<void>}) {
  const [path, setPath] = useState<string | null>(null), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const choosing = useRef(false);
  if (!enabled) return null;
  async function choose() {
    if (choosing.current) return;
    choosing.current = true; setBusy(true); setConfirmed(false);
    try {
      const value = await open({title: '选择已保存工程，明确放弃当前未保存会话后重开', filters: [{name: 'LumaRetouch 工程', extensions: ['json']}]});
      if (typeof value === 'string') setPath(value);
    } catch (error) {setMessage(String(error));} finally {choosing.current = false; setBusy(false);}
  }
  async function reopen() {
    if (!path || !confirmed || choosing.current || !engineAlive) return;
    choosing.current = true; setBusy(true); setConfirmed(false);
    try {
      await runProject('open', {path, force: true});
      setMessage('重开请求已发送，尚不代表成功。原选区回执核对必须收到真实工程重开确认，才允许关闭旧会话操作锁。');
    } catch (error) {setMessage(`重开未确认：${String(error)}。未重试，也未解除旧操作锁。`);}
    finally {choosing.current = false; setBusy(false);}
  }
  return <section className="creative-selection" aria-label="选区未知结果的显式工程恢复">
    <p role="alert">原操作结果仍未知。重开已保存工程会丢弃当前会话所有未保存编辑，包括可能已经应用的选区；不会覆盖工程文件或原片。请先确认已保存的工程是你要恢复的版本。</p>
    {!engineAlive && <button type="button" disabled={busy} onClick={() => {setBusy(true); void onStartEngine().finally(() => setBusy(false));}}>启动恢复所需引擎（不重发旧操作）</button>}
    <button type="button" disabled={busy} onClick={() => void choose()}>选择已保存工程</button>
    {path && <><p>{path}</p><label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)}/>我确认放弃当前未保存会话，按此文件重新打开；这不证明旧操作成功或失败。</label>
      <button type="button" disabled={busy || !confirmed || !engineAlive} onClick={() => void reopen()}>确认放弃未保存会话并重开</button></>}
    {message && <p role="status">{message}</p>}
  </section>;
}
