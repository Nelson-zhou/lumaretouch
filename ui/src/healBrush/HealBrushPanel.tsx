import type {HealBrushOwner} from './useHealBrushWorkflow';
import '../sourcePatch/sourcePatch.css';
export function HealBrushPanel({owner,onStart,blocked=false}:{owner:HealBrushOwner;onStart:()=>void;blocked?:boolean}){
  const {state,workflow,context,active,pending}=owner;
  return <section className="sourcePatchPanel" aria-label="修复笔" data-readonly-scopes data-heal-workflow>
    <strong>修复笔</strong>
    <small>在冻结的修复输入画面上涂抹，松手提交一笔，可撤销。使用内置确定性填充与扩散，不是生成式 AI 或 LaMa。</small>
    <label>大小（短边百分比）<input type="range" min="0.1" max="40" step="0.1" value={state.size*100} disabled={pending} onChange={e=>workflow.settings({size:Number(e.target.value)/100})}/>{(state.size*100).toFixed(1)}%</label>
    <label>硬度<input type="range" min="0" max="100" value={state.hardness*100} disabled={pending} onChange={e=>workflow.settings({hardness:Number(e.target.value)/100})}/>{Math.round(state.hardness*100)}%</label>
    <label>覆盖强度<input type="range" min="0" max="100" value={state.opacity*100} disabled={pending} onChange={e=>workflow.settings({opacity:Number(e.target.value)/100})}/>{Math.round(state.opacity*100)}%</label>
    <div className="sourcePatchButtons">
      <button disabled={blocked||!context.enabled||context.canStart===false||active||pending} onClick={onStart}>{state.phase==='success'?'继续下一笔（重新冻结）':'开始修复笔'}</button>
      <button disabled={!active} onClick={()=>workflow.cancel()}>结束 / 取消未提交笔划</button>
    </div>
    <small>每笔取样包含已有修补，不含其后的磨皮、形变或调色；导出按当前来源的完整尺寸重新计算。复杂大区域可能需要多次人工修整。</small>
    {state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&<div className="sourcePatchUncertain"><p>结果未确认，不会重新发送笔划。</p><button onClick={()=>void workflow.check()}>查询原操作结果</button><button disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button></div>}
  </section>;
}
export function HealBrushStatus({owner}:{owner:HealBrushOwner}){
  const {state,workflow}=owner;
  if(!['sending','waiting','uncertain','failure'].includes(state.phase)||!state.message)return null;
  return <div className="sourcePatchStatus" role="status" data-heal-workflow><span>{state.message}</span>{state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原修复结果</button>}</div>;
}
