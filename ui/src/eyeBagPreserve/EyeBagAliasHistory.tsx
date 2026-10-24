// SPDX-License-Identifier: GPL-3.0-or-later
import {eyeBagPresetAliasHistoryClass} from './presetAliasHistoryRegistry';
import {RecoveryAliasHistory} from '../effectRecovery/RecoveryAliasHistory';
import type {PeopleOwner} from '../people/usePeopleWorkflow';
/** Uses the people owner's one existing batch controller, not local document undo. */
export function EyeBagAliasHistory({people, blocked}: {people: PeopleOwner; blocked: boolean}) {
  const history = people.eyeBagAliasHistory;
  if (!history.receipt && history.state.phase === 'closed') return <><PresetAliasHistory people={people} blocked={blocked}/><RecoveryAliasHistory people={people} blocked={blocked}/></>;
  return <><section aria-label="共享来源祛眼袋受保护批次历史">
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
  </section><PresetAliasHistory people={people} blocked={blocked}/><RecoveryAliasHistory people={people} blocked={blocked}/></>;
}

/** Presentation only. All actions use the people owner's existing, single batch controller. */
function PresetAliasHistory({people,blocked}:{people:PeopleOwner;blocked:boolean}){
 const history=people.presetEyeBagAliasHistory;
 if(!history.batches.length&&!history.writePending&&history.state.phase==='closed')return null;
 return <section aria-label="混合预设共享来源全成员批次历史">
  <h5>混合预设共享来源全成员历史</h5>
  <p>每个批次同时管理当时当前照片的所选色彩、裁剪等配方和全部成员的共享人物图。其他成员自己的裁剪、修补及当前配方保留。撤销/重做必须恢复全部原成员，不使用当前照片本地撤销，不跳过冲突成员。</p>
  {history.batches.map(batch=>{const proof=eyeBagPresetAliasHistoryClass(batch.batch_id)?.marker;return <div key={batch.batch_id}>
   <p>批次 {batch.batch_id} · {batch.undone?'已撤销':'未撤销'}{proof?` · ${proof.member_count} 张成员 · 原当前文档 ${proof.current_document_id}`:' · 标记不完整，禁止恢复'}</p>
   {proof&&<p><small>原当前照片所选模块：{proof.selected_modules.join('、')}。其他来源别名只跟随共享图。</small></p>}
   <button type="button" disabled={blocked||!history.canUndo(batch.batch_id)} onClick={()=>void history.undo(batch.batch_id)}>撤销此完整混合预设批次</button>
   <button type="button" disabled={blocked||!history.canRedo(batch.batch_id)} onClick={()=>void history.redo(batch.batch_id)}>重做此完整混合预设批次</button>
  </div>;})}
  {history.writePending&&<p role="alert">混合预设应用尚未获得明确终态，不能撤销、重做或重发人物修改。请回到模块预设面板查询同一笔请求。若原生回执仍未知，请核对已保存项目后手动重新打开并检查全部成员，不能通过重复应用恢复。</p>}
  {history.state.phase==='committing'&&<p role="status">正在等待全成员历史回执，尚未确认恢复。</p>}
  {history.state.phase==='uncertain'&&<p role="alert">历史操作结果未知，只能查询原请求，不能重复撤销或重做。原生未知回执可能保持不变；若仍未知，请核对已保存项目后手动重新打开并检查全部成员。<button type="button" onClick={()=>void history.query()}>查询原批次请求</button></p>}
  {history.state.phase==='done'&&history.state.result&&<p role="status">引擎确认本次{history.state.operation==='undo'?'撤销':'重做'}原子恢复全部 {history.state.result.restored?.length??0} 张成员。</p>}
  {history.state.message&&<p role="alert">{history.state.message}</p>}
  {history.refreshError&&<p role="alert">{history.refreshError}<button type="button" disabled={history.refreshing} onClick={()=>void history.refresh()}>只刷新批次状态</button></p>}
 </section>;
}
