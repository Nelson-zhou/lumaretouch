import {NamedRecipeVersionsPanel} from '../namedRecipeVersions/NamedRecipeVersionsPanel';
import {abandonHistory,dismissHistoryNotice,historyMessage,navigateHistory,queryHistory,readHistory,useHistoryNavigation} from './owner';
export type HistoryOwner=ReturnType<typeof useHistoryNavigation>;
export function HistoryPanel({owner,context,disabled,onChanged,onOpenProject,receiptOnly=false,namedVersionsAvailable=false}:{namedVersionsAvailable?:boolean;receiptOnly?:boolean;owner:HistoryOwner;context:string;disabled:boolean;onChanged:()=>Promise<void>;onOpenProject:()=>void}){
  const view=owner.view,locked=disabled||owner.busy||!!owner.pending;
  const refresh=async(action:Promise<boolean>)=>{if(await action){try{await onChanged();}catch(e){historyMessage(`历史终态已保留，但当前状态刷新失败：${String(e)}`);}}};
  return <section aria-label="保留历史步骤" data-history-navigation-owner>
    {/* Keep the named panel mounted while pending: its completion refresh must survive. */}
    {owner.pending&&!receiptOnly&&<p role="status">历史或命名版本操作结果待确认；请使用窗口顶部的原操作入口。</p>}
    {!receiptOnly&&<><button type="button" disabled={locked} onClick={()=>void readHistory(context)}>读取 / 刷新保留历史</button>
    <p><small>仅当前仍保留的步骤；保留起点不代表原图。点击后逐步执行原有撤销或重做，不恢复任意旧快照。</small></p>
    {view&&<><p>当前：保留第 {view.cursor} 步 · 前 {view.undo_steps} / 后 {view.redo_steps} 步</p>
      {view.undo_steps+view.redo_steps>view.history_max&&<p role="status">两侧总长度超过保留上限；为避免跳转时丢弃端点，此历史暂不支持跳转。</p>}
      <div role="list" style={{maxHeight:240,overflowY:'auto',display:'grid',gap:4}}>{Array.from({length:view.undo_steps+view.redo_steps+1},(_,step)=><div role="listitem" key={`${view.digest}:${step}`}><button type="button" aria-current={step===view.cursor?'step':undefined}
        disabled={locked||step===view.cursor||view.undo_steps+view.redo_steps>view.history_max} onClick={()=>void refresh(navigateHistory(view,step,context))}>
        {step===0?'保留起点（第 0 步）':`保留第 ${step} 步`}{step===view.cursor?' · 当前':''}
      </button></div>)}</div></>}
    {namedVersionsAvailable&&<NamedRecipeVersionsPanel owner={owner} context={context} disabled={disabled} onChanged={onChanged}/>}
    </>}
    {owner.pending&&receiptOnly&&<div><button type="button" disabled={owner.busy} onClick={()=>void refresh(queryHistory())}>只查询原历史跳转结果</button>
      <button type="button" disabled={owner.busy} onClick={onOpenProject}>打开已确认工程（不重发）</button>
      {owner.recoveryAvailable&&<button type="button" disabled={owner.busy} onClick={()=>void refresh(abandonHistory())}>按已验证新工作区放弃旧等待</button>}</div>}
    {receiptOnly&&!owner.pending&&<button type="button" disabled={owner.busy} onClick={dismissHistoryNotice}>收起历史结果</button>}
    {(receiptOnly||!owner.notice)&&owner.message&&<p role="status" aria-live="polite">{owner.message}</p>}
  </section>;
}
