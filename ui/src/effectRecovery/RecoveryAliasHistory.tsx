// SPDX-License-Identifier: GPL-3.0-or-later
import {recoveryAliasHistoryClass} from './aliasHistoryRegistry';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
/** Presentation only: all undo/redo goes through the existing people-owned batch controller. */
export function RecoveryAliasHistory({people,blocked}:{people:PeopleOwner;blocked:boolean}){
  const history=people.recoveryEyeBagAliasHistory;
  if(!history.batches.length&&!history.writePending&&!history.needsRefresh&&history.state.phase==='closed')return null;
  return <section aria-label="去眼袋效果恢复共享来源完整成员历史">
    <h5>共享来源去眼袋恢复 · 全成员历史</h5>
    <p>只恢复或重放这位人物的去眼袋 v2 恢复向量，保留各成员自己的裁剪、修补、参数及卧蚕保护。必须恢复全部原成员；来源、成员或后续编辑有冲突时拒绝整个批次，不跳过成员，也不另建当前照片撤销记录。</p>
    {history.batches.map(batch=>{const marker=recoveryAliasHistoryClass(batch.batch_id)?.marker;return <div key={batch.batch_id}>
      <p>批次 {batch.batch_id} · {batch.undone?'已撤销':'未撤销'}{marker?` · ${marker.member_count} 张原成员`:' · 标记不完整，禁止恢复'}</p>
      <button type="button" disabled={blocked||!history.canUndo(batch.batch_id)} onClick={()=>void history.undo(batch.batch_id)}>撤销此完整恢复批次</button>
      <button type="button" disabled={blocked||!history.canRedo(batch.batch_id)} onClick={()=>void history.redo(batch.batch_id)}>重做此完整恢复批次</button>
    </div>;})}
    {history.writePending&&<p role="alert">恢复应用仍未获得明确终态，请回到恢复画笔工作区查询同一请求。不能通过重复笔迹、切换照片或撤销其他成员来解除保护。</p>}
    {history.state.phase==='committing'&&<p role="status">正在等待全部成员的原历史请求回执，尚未确认完成。</p>}
    {history.state.phase==='uncertain'&&<p role="alert">历史操作结果未知，只能查询原请求，不能重复撤销或重做。若仍未知，请核对已保存项目后手动重新打开并检查全部成员。<button type="button" onClick={()=>void history.query()}>查询原恢复批次历史请求</button></p>}
    {history.state.phase==='done'&&history.state.result&&<p role="status">引擎已确认本次{history.state.operation==='undo'?'撤销':'重做'}原子恢复全部 {history.state.result.restored?.length??0} 张成员。</p>}
    {history.state.phase==='error'&&history.state.result?.rolled_back===true&&<p>已补偿共享图与向量，但成员版本可能推进；正在刷新真实全成员状态，刷新完成前不能开始新审核。</p>}
    {history.needsRefresh&&!['committing','uncertain'].includes(history.state.phase)&&<p role="status">需要刷新实际成员状态后才能继续。<button type="button" disabled={history.refreshing} onClick={()=>void history.refresh()}>刷新成员状态，不重复历史操作</button></p>}
    {history.state.message&&<p role="alert">{history.state.message}</p>}
    {history.refreshError&&<p role="alert">{history.refreshError}<button type="button" disabled={history.refreshing} onClick={()=>void history.refresh()}>只刷新批次状态</button></p>}
  </section>;
}
