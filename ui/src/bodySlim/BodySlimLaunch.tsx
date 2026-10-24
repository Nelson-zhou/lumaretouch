// SPDX-License-Identifier: GPL-3.0-or-later
import type {BodySlimOwner} from './useBodySlimWorkflow';

export function BodySlimLaunch({owner,blocked,onOpen,onCheck}:{owner:BodySlimOwner;blocked:boolean;onOpen:()=>void;onCheck:()=>void}) {
  return <section data-body-slim-workflow aria-label="整体瘦身" data-feature-id="PC-32473"
    data-control-id="PC-32473-C-bc54b9eb3c" data-requirement-id="LNX-REF-PC-32473-C-bc54b9eb3c" data-tool-anchor="瘦身">
    <p>整体瘦身：沿完整人物轮廓统一调整横向宽度，向左增宽、向右收窄。需要真实全身定位、明确人物关联和独立描画完整人物及过渡区，不是局部瘦腰或自动 AI 分割。</p>
    <p>当前限单人、完整可见身体。手臂和腿之间的背景空隙及审核过渡区可能随之变形，不能承诺背景完全不动。</p>
    <button type="button" disabled={blocked||owner.busy} onClick={onOpen}>打开整体瘦身与当前来源图审核</button>
    {!owner.supported&&<p role="status">当前引擎未提供整体瘦身通信协议，请使用配套版本。</p>}
    {owner.supported&&!owner.coreAvailable&&<p role="status">{owner.unavailableReason}</p>}
    {owner.busy&&<p role="status">{owner.uncertain||owner.state.phase==='uncertain'?'整体瘦身结果待核对，不会重新提交。':'正在处理整体瘦身请求。'}</p>}
    {(owner.uncertain||owner.state.phase==='uncertain')&&<button type="button" onClick={onCheck}>查询原整体瘦身请求</button>}
    {owner.message&&<p role="status">{owner.message}</p>}
  </section>;
}
