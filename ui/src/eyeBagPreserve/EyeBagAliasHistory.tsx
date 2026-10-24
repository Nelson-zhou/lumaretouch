// SPDX-License-Identifier: GPL-3.0-or-later
import type {PeopleOwner} from '../people/usePeopleWorkflow';
/** Uses the people owner's one existing batch controller, not local document undo. */
export function EyeBagAliasHistory({people, blocked}: {people: PeopleOwner; blocked: boolean}) {
  const history = people.eyeBagAliasHistory;
  if (!history.receipt && history.state.phase === 'closed') return null;
  return <section aria-label="共享来源祛眼袋受保护批次历史">
    <h5>共享来源祛眼袋修改记录</h5>
    {history.receipt && <p role="status">引擎已确认全部 {history.receipt.review.members.length} 张成员，批次 {history.receipt.batchId}。
      {history.ledger ? history.ledger.undone ? '当前台账标记已撤销。' : '当前台账标记未撤销。'
        : '尚无匹配的完整批次台账，暂不开放撤销或重做。'}</p>}
    <p>共享来源修改不进入当前照片的本地撤销栈。撤销或重做必须恢复全部原成员；后续编辑、来源、修补或成员变化可能拒绝整个操作，不会跳过成员或强行覆盖。重新打开项目后仍使用引擎批次历史。</p>
    <button type="button" disabled={blocked || !history.canUndo} onClick={() => void history.undo()}>撤销此共享来源祛眼袋批次</button>
    <button type="button" disabled={blocked || !history.canRedo} onClick={() => void history.redo()}>重做此共享来源祛眼袋批次</button>
    {history.state.phase === 'committing' && <p role="status">正在等待原批次历史回执，尚未确认完成。</p>}
    {history.state.phase === 'uncertain' && <p role="alert">结果尚未确认，只能查询原请求，不能重复撤销、重做或应用。
      <button type="button" onClick={() => void history.query()}>查询原批次请求</button></p>}
    {history.state.phase === 'done' && history.state.result && <p role="status">引擎确认本次{history.state.operation === 'undo' ? '撤销' : '重做'}恢复全部 {history.state.result.restored?.length ?? 0} 张原成员。</p>}
    {history.state.message && <p role="alert">{history.state.message}</p>}
    {history.refreshError && <p role="alert">{history.refreshError}</p>}
    {history.refreshError && <button type="button" disabled={history.refreshing} onClick={() => void history.refresh()}>刷新批次状态，不重复提交</button>}
  </section>;
}
