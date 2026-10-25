// SPDX-License-Identifier: GPL-3.0-or-later
import {ExpressionReplacementPanel} from './ExpressionReplacementPanel';
import type {ExpressionReplacementOwner} from './useExpressionReplacement';

/** Visibility never owns request lifetime; the App retains the source controller. */
export function ExpressionWorkspaceHost({owner,open,onOpen,onClose}:{owner:ExpressionReplacementOwner;open:boolean;onOpen:()=>void;onClose:()=>void}){
  return <div data-expression-workflow>
    {owner.busy&&!open&&<aside role="status"><span>表情替换原请求仍待确认。</span><button type="button" onClick={onOpen}>查看原请求</button><button type="button" onClick={()=>void owner.check()}>查询回执</button></aside>}
    {open&&<section className="expression-host" role="dialog" aria-modal="true" aria-label="同场次表情替换">
      <header><h3>同场次表情替换 · 手动审核</h3><button type="button" onClick={onClose}>隐藏面板</button></header>
      <p>使用另一张同人物、同场次真实照片。需手动确认身份、姿态、可见范围和融合笔迹；不提供自动识别身份或生成表情。</p>
      <p role="status">{owner.message}</p>
      <button type="button" disabled={!owner.canAcquire} onClick={()=>void owner.acquireCurrent()}>获取当前完整修图结果并分析</button>
      {owner.acquisition&&<button type="button" onClick={owner.cancelCurrent}>请求取消来源获取</button>}
      {owner.busy&&<button type="button" onClick={()=>void owner.check()}>查询原请求</button>}
      <ExpressionReplacementPanel current={owner.current} controller={owner.controller}/>
    </section>}
  </div>;
}
