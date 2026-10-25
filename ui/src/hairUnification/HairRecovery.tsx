// SPDX-License-Identifier: GPL-3.0-or-later
import {useRef, useState} from 'react';
import {open} from '@tauri-apps/plugin-dialog';
import {runProject} from '../native';

/** Reopening is an explicit destructive-session choice, never inferred rollback. */
export function HairRecovery({engineAlive, onStartEngine}: {
  engineAlive: boolean; onStartEngine: () => Promise<void>;
}) {
  const gate = useRef(false);
  const [path, setPath] = useState<string | null>(null), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  async function choose() {
    if (gate.current) return;
    gate.current = true; setBusy(true); setConfirmed(false);
    try {
      const selected = await open({title: '选择要恢复的已保存工程', filters: [{name: 'LumaRetouch 工程', extensions: ['json']}]});
      if (typeof selected === 'string') setPath(selected);
    } catch (error) {setMessage(String(error));}
    finally {gate.current = false; setBusy(false);}
  }
  async function reopen() {
    if (gate.current || !engineAlive || !path || !confirmed) return;
    gate.current = true; setBusy(true); setConfirmed(false);
    try {
      await runProject('open', {path, force: true});
      setMessage('重开请求已发送，尚未确认完成。请查询原请求；只有真实工程重开回执才允许明确结束旧会话锁。');
    } catch (error) {setMessage(`未确认重开：${String(error)}。原请求仍保留，不重发，也不推断已撤销。`);}
    finally {gate.current = false; setBusy(false);}
  }
  async function restart() {
    if (gate.current) return;
    gate.current = true; setBusy(true);
    try {await onStartEngine();}
    catch (error) {setMessage(String(error));}
    finally {gate.current = false; setBusy(false);}
  }
  return <section aria-label="发色统一未知结果的工程恢复">
    <p role="alert">原请求结果未知。可先查询；如无法确认，可明确放弃当前未保存会话，重开已保存工程。这会丢弃包括可能已应用的发色统一在内的所有未保存编辑，不覆盖工程文件或原片，也不证明旧操作成功或失败。</p>
    {!engineAlive && <button type="button" disabled={busy} onClick={() => void restart()}>启动恢复引擎，不重发旧操作</button>}
    <button type="button" disabled={busy} onClick={() => void choose()}>选择已保存工程</button>
    {path && <><p>{path}</p><label><input type="checkbox" checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)}/>
      我确认放弃当前未保存会话，并按此工程文件恢复。</label>
      <button type="button" disabled={busy || !confirmed || !engineAlive} onClick={() => void reopen()}>确认放弃未保存会话并重开</button></>}
    {message && <p role="status">{message}</p>}
  </section>;
}
