import {useState} from 'react';
import type {CommonBackgroundOwner} from './useCommonBackgroundWorkflow';

/** Retained evidence remains inspectable after the active mutation lock settles. */
export function CommonBackgroundReceiptPanel({owner}: {owner: CommonBackgroundOwner}) {
  const {state, workflow, context} = owner, [page, setPage] = useState(0);
  const lastPage = Math.max(0, Math.ceil(state.audit.length / 20) - 1), currentPage = Math.min(page, lastPage);
  const records = state.audit.slice().reverse().slice(currentPage * 20, currentPage * 20 + 20);
  const querying = state.receiptQueryPending || state.readbackPending;
  return <div className="commonBackgroundEvidence">
    {state.inventoryPhase !== 'ready' && <div role="status"><p>{state.inventoryMessage || '正在核对应用进程保留的原操作，暂时保护编辑。'}</p>
      <button type="button" disabled={state.inventoryPhase === 'pending'} onClick={() => void workflow.initialize()}>重新读取原操作登记</button></div>}
    {state.request && <>
      <p>仍有 {state.unresolved.length} 笔原操作待确认。当前原操作：{state.request.request_id}</p>
      <div className="specSeg"><button type="button" disabled={querying || state.inventoryPhase !== 'ready'} onClick={() => void workflow.check()}>查询原操作回执，不重复提交</button>
        <button type="button" disabled={querying || state.phase !== 'uncertain' || !context.readbackEnabled || state.inventoryPhase !== 'ready'} onClick={() => void workflow.readback()}>
          {state.readbackPending ? '正在同引擎核对…' : state.readbackId && state.readbackPhase === 'pending' ? '继续查询本次核对' : '同引擎核对原结果（只读）'}</button></div>
      {!context.readbackEnabled && <p>当前引擎未提供同引擎核对能力，原操作仍保留。没有回执不等于没有执行。</p>}
      <p><small>同引擎核对只读取原操作保存的真实结果，不重新应用。若引擎本身回滚失败、记录缺失或引擎已更换，需要明确的工程检查点恢复，不能靠关闭窗口解除。</small></p>
    </>}
    {state.audit.length > 0 && <details className="commonBackgroundAudit"><summary>原操作与核对记录（{state.audit.length}）</summary>
      <p>证据范围：当前应用进程。关闭或重建界面不清除此登记；不承诺整个应用进程重启后的磁盘持久化。</p>
      {records.map(entry => <details key={entry.original_request.request_id}><summary>{entry.settled_by === 'readback' ? '同引擎已核对' : entry.settled_by === 'original-receipt' ? '原回执已确认' : '仍待确认'} · {entry.original_request.request_id}</summary>
        <p>原始回执与独立核对结果分别保留，不用新结果覆盖原始未知记录。</p><pre className="commonBackgroundAuditJson">{JSON.stringify(entry, null, 2)}</pre></details>)}
      {state.audit.length > 20 && <div className="specSeg"><button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>较新记录</button>
        <span>{currentPage + 1} / {lastPage + 1}</span><button type="button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)}>较早记录</button></div>}
    </details>}
  </div>;
}
