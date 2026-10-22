import type {CloneStampOwner} from './useCloneStampWorkflow';
import '../sourcePatch/sourcePatch.css';
export function CloneStampPanel({owner,onStart,blocked=false}:{owner:CloneStampOwner;onStart:()=>void;blocked?:boolean}){
  const {state,workflow,context,active,pending}=owner;
  return <section className="sourcePatchPanel" aria-label="仿制图章" data-readonly-scopes>
    <strong>仿制图章</strong>
    <small>Alt/Option 点击取样，按住涂抹；松手提交一笔，可撤销。保留来源颜色与纹理，不作修复融合。</small>
    <label>大小（短边百分比）<input type="range" min="0.1" max="40" step="0.1" value={state.size*100} disabled={pending} onChange={e=>workflow.settings({size:Number(e.target.value)/100})}/>{(state.size*100).toFixed(1)}%</label>
    <label>硬度<input type="range" min="0" max="100" value={state.hardness*100} disabled={pending} onChange={e=>workflow.settings({hardness:Number(e.target.value)/100})}/>{Math.round(state.hardness*100)}%</label>
    <label>不透明度<input type="range" min="0" max="100" value={state.opacity*100} disabled={pending} onChange={e=>workflow.settings({opacity:Number(e.target.value)/100})}/>{Math.round(state.opacity*100)}%</label>
    <div className="sourcePatchButtons">
      <button disabled={blocked||!context.enabled||context.canStart===false||active||pending} onClick={onStart}>{state.phase==='success'?'继续下一笔（重新冻结）':'开始仿制图章'}</button>
      <button disabled={state.phase!=='target'} onClick={()=>workflow.setSource(null)}>重新设置来源</button>
      <button disabled={!active} onClick={()=>workflow.cancel()}>结束 / 取消未提交笔划</button>
    </div>
    <small>每笔从同一个取样点开始（不对齐）；笔划内来源随笔移动。每笔冻结来源，重叠处不反复累积不透明度；下一笔重新捕获已有结果。</small>
    {state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&<div className="sourcePatchUncertain"><p>结果未确认，不会重新发送图章。</p><button onClick={()=>void workflow.check()}>查询原操作结果</button><button disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button></div>}
  </section>;
}
export function CloneStampStatus({owner}:{owner:CloneStampOwner}){
  const {state,workflow}=owner;
  if(!['sending','waiting','uncertain','failure'].includes(state.phase)||!state.message)return null;
  return <div className="sourcePatchStatus" role="status"><span>{state.message}</span>{state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原图章结果</button>}</div>;
}
