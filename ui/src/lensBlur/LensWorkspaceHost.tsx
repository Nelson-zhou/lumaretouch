// SPDX-License-Identifier: GPL-3.0-or-later
import {LensBlurWorkspace} from './LensBlurWorkspace';
import type {useLensBlur} from './useLensBlur';
type Owner=ReturnType<typeof useLensBlur>;
/** Presentation only; App owns pending requests and source lifetime. */
export function LensWorkspaceHost({owner,open,onOpen,onClose}:{owner:Owner;open:boolean;onOpen:()=>void;onClose:()=>void}){
  return <div data-lens-blur-workflow>
    {owner.busy&&!open&&<aside role="status"><span>镜头虚化原请求仍待确认。</span><button type="button" onClick={onOpen}>查看原请求</button><button type="button" onClick={()=>void owner.check()}>查询回执</button></aside>}
    {open&&<section className="lens-host" role="dialog" aria-modal="true" aria-label="镜头虚化审核">
      <header><h3>镜头虚化 · 深度与效果审核</h3><button type="button" onClick={onClose}>隐藏面板</button></header>
      <p>可显式安装并核对 Small 模型后生成 AI 相对深度，先检查深度图再审核实际效果。未就绪时仍可明确选择人工基准面；两者不会混称。主体自动对焦与物理距离估计不在本范围。</p>
      <p role="status">{owner.message}</p>
      <button type="button" disabled={!owner.canAcquire} onClick={()=>void owner.acquireCurrent()}>获取当前完整修图结果</button>
      {owner.acquisition&&<button type="button" onClick={()=>void owner.cancelCurrent()}>请求取消来源获取</button>}
      {owner.busy&&<button type="button" onClick={()=>void owner.check()}>查询原请求</button>}
      <LensBlurWorkspace workflow={owner.workflow} onExit={onClose}/>
    </section>}
  </div>;
}
