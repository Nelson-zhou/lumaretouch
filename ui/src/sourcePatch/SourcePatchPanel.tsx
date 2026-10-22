import type {SourcePatchOwner} from './useSourcePatchWorkflow';
import {SOURCE_PATCH_LABEL} from './workflow';
import './sourcePatch.css';

export function SourcePatchPanel({owner,onStart}:{owner:SourcePatchOwner;onStart?:()=>void}){
  const {workflow,state,context,active,pending}=owner;
  // The workflow validates the polygon once and clamps drag offsets; apply revalidates.
  const canApply=state.phase==='source'&&Math.hypot(...state.offset)>=1e-8&&context.enabled&&!pending;
  return <section className="sourcePatchPanel" aria-label="来源区域修补">
    <strong>来源区域修补</strong>
    <small>{SOURCE_PATCH_LABEL}</small>
    <p>圈选目标 → 拖动同形来源 → 应用修补</p>
    <small>只平移来源，不缩放或旋转。松开指针只确认选区，不会修改照片。</small>
    <div className="sourcePatchButtons">
      <button disabled={!context.enabled||context.canStart===false||active||pending} onClick={()=>onStart?onStart():void workflow.start()}>开始选区修补</button>
      <button disabled={!['target','source'].includes(state.phase)} onClick={()=>workflow.resetTarget()}>重画目标</button>
      <button disabled={!canApply} onClick={()=>void workflow.apply()}>应用修补</button>
      <button disabled={!active} onClick={()=>workflow.cancel()}>取消</button>
    </div>
    {state.phase==='source'&&<small>橙色是目标，蓝色是来源；箭头方向为来源 → 目标。也可用方向键微调来源，Shift 加速。</small>}
    {(!context.enabled||(!active&&context.canStart===false))&&<small>{context.reason??'当前编辑状态下无法开始修补'}</small>}
    {state.message&&<p role="status" aria-live="polite">{state.message}</p>}
    {state.phase==='uncertain'&&<div className="sourcePatchUncertain">
      <p>不要重复应用。这里只查询原操作，不会重新发送修补。</p>
      <div className="sourcePatchButtons">
        <button onClick={()=>void workflow.check()}>查询原操作结果</button>
        <button disabled={!context.enabled||context.documentId===state.request?.document_id}
          onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button>
      </div>
    </div>}
  </section>;
}

/** Completion and unresolved receipts remain reachable even when the repair panel is folded. */
export function SourcePatchStatus({owner}:{owner:SourcePatchOwner}){
  const {state,workflow}=owner;
  if(!['sending','waiting','uncertain','success','failure'].includes(state.phase)||!state.message)return null;
  return <div className="sourcePatchStatus" role="status" aria-live="polite">
    <span>{state.message}</span>
    {state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原修补结果</button>}
  </div>;
}
