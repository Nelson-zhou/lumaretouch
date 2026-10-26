// SPDX-License-Identifier: GPL-3.0-or-later
import {UpscaleModelSetup} from './UpscaleModelSetup';
import {UpscaleRestoreWorkspace} from './UpscaleRestoreWorkspace';
import type {UpscaleRestoreWorkspaceOwner} from './useUpscaleRestore';

/** Hiding is not cancellation. Owner and its original requests remain in the App. */
export function UpscaleRestoreWorkspaceHost({owner, open, onOpen, onClose, unavailableReason}: {
  owner: UpscaleRestoreWorkspaceOwner; unavailableReason?: string; open: boolean; onOpen: () => void; onClose: () => void;
}) {
  return <div data-upscale-restore-workflow>
    {owner.busy && !open && <aside role="status"><span>AI 超清原请求仍待确认。</span>
      <button type="button" onClick={onOpen}>查看原请求</button><button type="button" onClick={() => void owner.check()}>查询回执</button></aside>}
    {open && <section className="upscaleRestoreHost" role="dialog" aria-modal="true" aria-label="AI 超清 · 原尺寸恢复"
      onKeyDown={event => {if (event.key === 'Escape') {event.stopPropagation(); onClose();}}}>
      <header className="upscaleRestoreHeader"><div><h3>AI 超清 · 原尺寸恢复</h3><p>当前照片 · 原尺寸 AI 候选复核</p></div>
        <button type="button" onClick={onClose}>隐藏面板</button></header>
      <UpscaleModelSetup disabled={owner.busy || owner.refreshing}/>
      <p role="status">{owner.message}</p>
      {!owner.state.context && unavailableReason && <small>启动时状态：{unavailableReason}。可重新核对现场状态。</small>}
      <div className="upscaleRestoreActions"><button type="button" disabled={!owner.canAcquire} onClick={() => void owner.acquireCurrent()}>重新核对并获取完整来源</button>
        {owner.acquisition && <button type="button" onClick={() => void owner.cancelCurrent()}>请求取消来源获取</button>}
        {owner.busy && <button type="button" onClick={() => void owner.check()}>查询原请求</button>}</div>
      <UpscaleRestoreWorkspace controller={owner.controller} disabled={owner.refreshing || !!owner.acquisition}/>
    </section>}
  </div>;
}
