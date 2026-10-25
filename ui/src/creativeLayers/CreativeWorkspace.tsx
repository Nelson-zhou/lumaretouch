// SPDX-License-Identifier: GPL-3.0-or-later
import {TOOLS, TOOL_CATEGORIES} from '../spec';
import {CreativeLayersPanel} from './CreativeLayersPanel';
import type {CreativeWorkspaceOwner} from './useCreativeWorkspace';

/** Real layer workspace plus the existing tool catalogue, extracted without dropping tools. */
export function CreativeWorkspace({owner, hasImage, available, onBack, onHeal, healBlocked, onLens, lensBlocked}: {
  owner: CreativeWorkspaceOwner; hasImage: boolean; available: boolean;
  onBack: () => void; onHeal: () => void; healBlocked: boolean; onLens: () => void; lensBlocked: boolean;
}) {
  return <section className="creativeView">
    <div className="creativeHead"><div><h2>创意</h2><span>真实图片图层与可恢复的文档编辑</span></div>
      <button className="chip" disabled={!hasImage || owner.pending} onClick={onBack}>回到画布</button></div>
    <div className="creative-connection">
      <button type="button" disabled={!hasImage || !available || owner.busy}
        onClick={() => void (owner.needsReopen ? owner.reopen() : owner.read())}>
        {owner.needsReopen ? '以当前照片重新打开创意文档' : '读取当前图层状态'}</button>
      <button type="button" disabled={owner.busy || !owner.value?.capabilities.fresh_current || !owner.value?.history?.recoverable_delete}
        title="以照片当前完整编辑结果新建图层文档；现有图层保留在撤销历史中，不会改写原片。"
        onClick={() => void owner.freshCurrent()}>以当前照片编辑结果新建图层文档</button>
      {owner.unresolved && <button type="button" disabled={owner.working} onClick={() => void owner.query()}>核对原操作结果</button>}
      {owner.message && <p role={owner.unresolved ? 'alert' : 'status'}>{owner.message}</p>}
    </div>
    <CreativeLayersPanel snapshot={owner.value?.authority.document ?? null} ownershipToken={owner.value?.authority.ownership_token ?? null}
      ports={owner.ports} preview={owner.value?.preview} history={owner.value?.history} busy={owner.busy}
      unavailableReason={!hasImage ? '请先打开一张照片，再进入创意工作区。' : !available ? '当前引擎未提供创意文档协议，请使用配套安装包。' : owner.message || '正在等待当前照片的稳定来源身份。'}/>
    <details className="creative-tool-catalogue"><summary>其他创意工具</summary><div className="creativeCards">
      {TOOL_CATEGORIES.map(category => <div className="cGroup" key={category}><h3>{category}</h3><div className="cCards">
        {TOOLS.filter(tool => tool.category === category).map(tool => {
          const lens = tool.id === '165438';
          const heal = tool.name.includes('智能消除');
          const wired = heal || lens;
          return <button key={tool.id} className={`cCard${wired ? ' on' : ' off'}`} disabled={!wired || !hasImage || owner.pending || (lens ? lensBlocked : healBlocked)}
            title={lens ? '人工镜头散焦与完整图像审核；AI 景深尚不可用' : wired ? '在画布上使用消除笔' : '该工具将在后续版本提供'} onClick={() => {if (lens && !lensBlocked) onLens(); else if (heal && !healBlocked) onHeal();}}>
            <b>{tool.name}</b><span>{(tool.interaction || tool.output || '').slice(0, 46)}</span></button>;
        })}
      </div></div>)}
    </div></details>
  </section>;
}
