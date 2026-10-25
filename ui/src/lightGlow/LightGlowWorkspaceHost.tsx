// SPDX-License-Identifier: GPL-3.0-or-later
import {LightGlowWorkspace} from './LightGlowWorkspace';
import type {LightGlowWorkspaceOwner} from './useLightGlow';

/** Hiding is not cancellation. Owner and its original requests remain in the App. */
export function LightGlowWorkspaceHost({owner, open, onOpen, onClose, unavailableReason}: {
  owner: LightGlowWorkspaceOwner; unavailableReason?: string; open: boolean; onOpen: () => void; onClose: () => void;
}) {
  return <div data-light-glow-workflow>
    {owner.busy && !open && <aside role="status"><span>发光原请求仍待确认。</span>
      <button type="button" onClick={onOpen}>查看原请求</button><button type="button" onClick={() => void owner.check()}>查询回执</button></aside>}
    {open && <section className="lightGlowHost" role="dialog" aria-modal="true" aria-label="光影 · 发光"
      onKeyDown={event => {if (event.key === 'Escape') {event.stopPropagation(); onClose();}}}>
      <header className="lightGlowHeader"><div><h3>光影 · 发光</h3><p>当前照片 · 标量配方 · 完整效果复核</p></div>
        <button type="button" onClick={onClose}>隐藏面板</button></header>
      <p role="status">{unavailableReason || owner.message}</p>
      <div className="lightGlowActions"><button type="button" disabled={!owner.canAcquire} onClick={() => void owner.acquireCurrent()}>获取当前完整修图结果</button>
        {owner.acquisition && <button type="button" onClick={() => void owner.cancelCurrent()}>请求取消来源获取</button>}
        {owner.busy && <button type="button" onClick={() => void owner.check()}>查询原请求</button>}</div>
      <LightGlowWorkspace controller={owner.controller} disabled={owner.refreshing || !!owner.acquisition}/>
    </section>}
  </div>;
}
